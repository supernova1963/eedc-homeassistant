"""
Wetter-Backfill aus Open-Meteo Archive.

Füllt fehlende stündliche Wetter-Spalten (bewoelkung_prozent, niederschlag_mm,
wetter_code) in TagesEnergieProfil rückwirkend aus Open-Meteo Archive nach.

Strikt additiv: existierende Werte werden NICHT überschrieben — nur Zellen mit
NULL-Wert werden befüllt. Mehrfachaufruf ist idempotent.

Hintergrund: Stündliche Wetter-Felder wurden v3.26 zur Datenbasis ergänzt.
Bestehende Anlagen haben mehrjährige Energie-Historie ohne Wetter-Klassifikation;
dieser Service füllt sie aus den Open-Meteo Archive-Daten (ERA5-Reanalyse, gratis,
2 Jahre rückwirkend).

Quota: ein Range-Call pro Anlage deckt die ganze Historie ab. Bei 2 Jahren
~17500 Stundenwerte in einer JSON-Antwort — Open-Meteo Free-Tier (10000 Calls/Tag)
unkritisch.

Lag: Archive hängt 2-5 Tage hinter Echtzeit. Letzte Tage werden hier nicht
angefasst — sie laufen normal über den Live-Forecast-Pfad in
energie_profil_service.aggregate_day().

⚑ Wer den vorläufigen Forecast-Wert später durch den endgültigen ersetzt, ist
NICHT dieser Dienst (er ist strikt additiv und kennt `globalstrahlung_wm2`
ohnehin nicht), sondern `services/energie_profil/archiv_nachzug.py` — er
aggregiert nächtlich den einen Tag neu, der `archive_cutoff()` gerade passiert
hat. Bis dahin (N-388, 2026-09-04) blieb ein vorläufiger Strahlungswert für
immer stehen; an bewölkten Tagen war er bis Faktor 8,7 zu klein.
"""

from datetime import date, timedelta
import logging
from typing import Optional

import httpx
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil

logger = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
ARCHIVE_LAG_TAGE = 5  # letzte N Tage aus Forecast-Pfad, nicht aus Archive
DEFAULT_MAX_TAGE = 730  # 2 Jahre


def archive_cutoff(heute: Optional[date] = None) -> date:
    """SoT-Cutoff: Tage älter als das gehen über Archive, jüngere über Forecast.

    Wird auch in `energie_profil_service._get_wetter_ist` und im
    Stratifizierungs-Endpoint genutzt, damit alle Read-/Write-Pfade
    konsistent denselben Lag-Begriff haben.
    """
    return (heute or date.today()) - timedelta(days=ARCHIVE_LAG_TAGE)


async def wetter_backfill_anlage(
    anlage: Anlage,
    db: AsyncSession,
    max_tage: int = DEFAULT_MAX_TAGE,
) -> dict:
    """
    Füllt fehlende stündliche Wetter-Felder einer Anlage aus Open-Meteo Archive.

    Args:
        anlage: Anlage mit lat/lon. Ohne Koordinaten wird übersprungen.
        db: Async-Session mit aktiver Transaction.
        max_tage: Maximale Rückwärts-Tiefe in Tagen.

    Returns:
        dict mit status, tage_geupdated, stunden_geupdated, von, bis, fehler.
    """
    if not anlage.latitude or not anlage.longitude:
        return {"status": "skipped", "grund": "keine Koordinaten"}

    cutoff_alt = date.today() - timedelta(days=max_tage)
    cutoff_neu = archive_cutoff()

    # Tage mit fehlenden Wetter-Feldern bis heute (Archive UND letzte Tage).
    # Den Lag-Cutoff im SELECT NICHT mehr setzen — die letzten Tage holen wir
    # über den Forecast-Endpoint (Reanalyse-Approximation).
    result = await db.execute(
        select(TagesEnergieProfil.datum)
        .where(
            and_(
                TagesEnergieProfil.anlage_id == anlage.id,
                TagesEnergieProfil.datum >= cutoff_alt,
                TagesEnergieProfil.datum < date.today(),
                TagesEnergieProfil.bewoelkung_prozent.is_(None),
            )
        )
        .distinct()
    )
    fehlende_tage = sorted({r[0] for r in result.all()})

    if not fehlende_tage:
        return {"status": "ok", "tage_geupdated": 0, "stunden_geupdated": 0}

    archive_tage = [d for d in fehlende_tage if d < cutoff_neu]
    forecast_tage = [d for d in fehlende_tage if d >= cutoff_neu]

    stunden_total = 0
    tage_total: set[date] = set()
    fehler: Optional[str] = None

    if archive_tage:
        s, t, err = await _fetch_und_update(
            anlage, db, ARCHIVE_URL, archive_tage[0], archive_tage[-1], set(archive_tage)
        )
        stunden_total += s
        tage_total |= t
        if err and not fehler:
            fehler = err

    if forecast_tage:
        forecast_url = "https://api.open-meteo.com/v1/forecast"
        s, t, err = await _fetch_und_update(
            anlage, db, forecast_url, forecast_tage[0], forecast_tage[-1], set(forecast_tage)
        )
        stunden_total += s
        tage_total |= t
        if err and not fehler:
            fehler = err

    await db.commit()

    von = fehlende_tage[0]
    bis = fehlende_tage[-1]
    logger.info(
        f"Wetter-Backfill Anlage {anlage.id}: "
        f"{stunden_total} Stunden / {len(tage_total)} Tage geupdated "
        f"({von}–{bis}; archive={len(archive_tage)}, forecast={len(forecast_tage)})"
    )

    if stunden_total == 0 and fehler:
        return {"status": "error", "fehler": fehler}

    return {
        "status": "ok",
        "tage_geupdated": len(tage_total),
        "stunden_geupdated": stunden_total,
        "von": von.isoformat(),
        "bis": bis.isoformat(),
    }


async def _fetch_und_update(
    anlage: Anlage,
    db: AsyncSession,
    url: str,
    von: date,
    bis: date,
    fehlende_set: set[date],
) -> tuple[int, set[date], Optional[str]]:
    """Holt Wetter-Range und schreibt additiv in TagesEnergieProfil.

    Returns: `(stunden_geupdated, tage_geupdated, fehler_msg_or_None)`.
    """
    params = {
        "latitude": anlage.latitude,
        "longitude": anlage.longitude,
        "timezone": "Europe/Berlin",
        "start_date": von.isoformat(),
        "end_date": bis.isoformat(),
        "hourly": "cloud_cover,precipitation,weather_code",
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(
            f"Wetter-Backfill Anlage {anlage.id} ({von}–{bis}): {url} fehlgeschlagen: {e}"
        )
        return 0, set(), str(e)

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    cloud_cover = hourly.get("cloud_cover", [])
    precip = hourly.get("precipitation", [])
    wcode = hourly.get("weather_code", [])

    stunden_geupdated = 0
    tage_geupdated: set[date] = set()

    for i, t in enumerate(times):
        try:
            datum_obj = date.fromisoformat(t[:10])
            stunde = int(t[11:13])
        except Exception:
            continue
        if datum_obj not in fehlende_set:
            continue

        cc = cloud_cover[i] if i < len(cloud_cover) else None
        pr = precip[i] if i < len(precip) else None
        wc = wcode[i] if i < len(wcode) else None

        update_values: dict = {}
        if cc is not None:
            update_values["bewoelkung_prozent"] = round(cc, 0)
        if pr is not None:
            update_values["niederschlag_mm"] = round(pr, 2)
        if wc is not None:
            update_values["wetter_code"] = int(wc)
        if not update_values:
            continue

        await db.execute(
            update(TagesEnergieProfil)
            .where(
                and_(
                    TagesEnergieProfil.anlage_id == anlage.id,
                    TagesEnergieProfil.datum == datum_obj,
                    TagesEnergieProfil.stunde == stunde,
                    TagesEnergieProfil.bewoelkung_prozent.is_(None),
                )
            )
            .values(**update_values)
        )
        stunden_geupdated += 1
        tage_geupdated.add(datum_obj)

    return stunden_geupdated, tage_geupdated, None
