"""Energie-Profil — Debug- und Diagnose-Endpunkte.

GET /api/energie-profil/{anlage_id}/debug-rohdaten          — Rohdaten TagesEnergieProfil (7 Tage)
GET /api/energie-profil/{anlage_id}/verfuegbare-monate      — Jahr/Monat-Kombis mit Daten
GET /api/energie-profil/{anlage_id}/stats                   — Datenbestand fuer Settings
GET /api/energie-profil/{anlage_id}/reaggregate-tag/preview — Diff-Vorschau Reaggregate
GET /api/energie-profil/{anlage_id}/kraftstoffpreis-status  — Anzahl offener Zeilen
"""
# Reiner Umzug aus `api/routes/energie_profil/views.py` (18.09.2026, Vorlage 4 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `views.py` haengt den Router ein und
# exportiert die Endpunkt-Namen weiter, die Aufrufer und Tests bisher von dort importierten.

from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from ._shared import (
    ReaggregatePreviewBoundary,
    ReaggregatePreviewCounterTagesdelta,
    ReaggregatePreviewResponse,
    ReaggregatePreviewSlot,
    logger,
)

router = APIRouter()


# ── Debug + Diagnose-Endpoints ───────────────────────────────────────────────

@router.get("/{anlage_id}/debug-rohdaten")
async def get_debug_rohdaten(
    anlage_id: int,
    tage: int = Query(7, ge=1, le=30, description="Anzahl Tage zurück"),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt TagesEnergieProfil-Rohdaten zurück (für Diagnose falsch gespeicherter Werte).

    Zeigt pv_kw, verbrauch_kw, netzbezug_kw, einspeisung_kw pro Stunde + Datum.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise not_found("Anlage")

    start = date.today() - timedelta(days=tage)

    rows_result = await db.execute(
        select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= start,
        ).order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    rows = rows_result.scalars().all()

    alle_verbrauch = [r.verbrauch_kw for r in rows if r.verbrauch_kw is not None]
    median_verbrauch = None
    if alle_verbrauch:
        sv = sorted(alle_verbrauch)
        median_verbrauch = sv[len(sv) // 2]

    return {
        "anlage_id": anlage_id,
        "anzahl_zeilen": len(rows),
        "median_verbrauch_kw": median_verbrauch,
        "plausibel": median_verbrauch is None or median_verbrauch <= 100,
        "zeilen": [
            {
                "datum": r.datum.isoformat(),
                "stunde": r.stunde,
                "pv_kw": r.pv_kw,
                "verbrauch_kw": r.verbrauch_kw,
                "netzbezug_kw": r.netzbezug_kw,
                "einspeisung_kw": r.einspeisung_kw,
                "batterie_kw": r.batterie_kw,
                "waermepumpe_kw": r.waermepumpe_kw,
            }
            for r in rows
        ],
    }

@router.get("/{anlage_id}/verfuegbare-monate")
async def verfuegbare_monate(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert alle Jahr/Monat-Kombinationen mit TagesZusammenfassung-Einträgen.

    Für Jahr-/Monats-Selektoren, die nur Werte mit Daten anbieten sollen.
    Sortierung: neueste zuerst.
    """
    from sqlalchemy import func

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    jahr = func.extract("year", TagesZusammenfassung.datum)
    monat = func.extract("month", TagesZusammenfassung.datum)
    rows = (await db.execute(
        select(jahr.label("jahr"), monat.label("monat"), func.count().label("tage"))
        .where(TagesZusammenfassung.anlage_id == anlage_id)
        .group_by(jahr, monat)
        .order_by(jahr.desc(), monat.desc())
    )).all()

    return [
        {"jahr": int(r.jahr), "monat": int(r.monat), "tage": int(r.tage)}
        for r in rows
    ]

@router.get("/{anlage_id}/stats")
async def get_anlage_stats(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Anlage-spezifische Profildaten-Statistik für die Energieprofil-Seite.

    Zählt Stundenwerte, Tageszusammenfassungen und Monatsdaten nur für diese
    Anlage und liefert den Abdeckungs-Zeitraum aus TagesZusammenfassung.
    """
    from sqlalchemy import func
    from backend.models.monatsdaten import Monatsdaten

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    stundenwerte = await db.scalar(
        select(func.count(TagesEnergieProfil.id)).where(TagesEnergieProfil.anlage_id == anlage_id)
    ) or 0
    tageszusammenfassungen = await db.scalar(
        select(func.count(TagesZusammenfassung.id)).where(TagesZusammenfassung.anlage_id == anlage_id)
    ) or 0
    monatswerte = await db.scalar(
        select(func.count(Monatsdaten.id)).where(Monatsdaten.anlage_id == anlage_id)
    ) or 0

    zeitraum = None
    if tageszusammenfassungen > 0:
        row = (await db.execute(
            select(
                func.min(TagesZusammenfassung.datum),
                func.max(TagesZusammenfassung.datum),
                func.count(func.distinct(TagesZusammenfassung.datum)),
            ).where(TagesZusammenfassung.anlage_id == anlage_id)
        )).one()
        von_datum, bis_datum, tage_mit_daten = row
        if von_datum:
            tage_gesamt = (bis_datum - von_datum).days + 1
            zeitraum = {
                "von": von_datum.isoformat(),
                "bis": bis_datum.isoformat(),
                "tage_mit_daten": tage_mit_daten,
                "tage_gesamt": tage_gesamt,
                "abdeckung_prozent": round(tage_mit_daten / tage_gesamt * 100, 1) if tage_gesamt > 0 else 0,
            }

    return {
        "stundenwerte": int(stundenwerte),
        "tageszusammenfassungen": int(tageszusammenfassungen),
        "monatswerte": int(monatswerte),
        "zeitraum": zeitraum,
        "wachstum_pro_monat": 750,  # 24h + 1 Tagessumme × 30 Tage
    }

@router.get("/{anlage_id}/reaggregate-tag/preview", response_model=ReaggregatePreviewResponse)
async def reaggregate_tag_preview(
    anlage_id: int,
    datum: date = Query(..., description="Tag, fuer den die Vorschau erzeugt werden soll"),
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert eine alt/neu-Vergleichstabelle der Snapshot-Werte und Slot-Deltas,
    die ein Reload des Tages produzieren WÜRDE — ohne irgendetwas zu schreiben.

    Damit der Nutzer vor der Übernahme sieht, welche Werte aus HA kommen und
    wie sich die Tagesbilanz ändert. Erst nach manueller Bestätigung
    (`POST /reaggregate-tag`) werden die Werte tatsächlich übernommen.

    Range: Vortag 23:00 .. Folgetag 00:00 (25 Boundaries pro Counter, 24 Slots).
    Slot 0 = snap(Tag 00:00) − snap(Vortag 23:00). Damit ist die Slot-0-
    Boundary in der Tabelle sichtbar — der ehemalige Hauptverdächtige für
    persistente Counter-Spikes (Befund Rainer 1.5.2026).
    """
    from backend.services.sensor_snapshot_service import get_reaggregate_preview

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    # N-619: nur die am Tag aktiven Investitionen — dieselbe Menge, mit der
    # `POST /reaggregate-tag` (`aggregate_day`, `aktiv_am_tag`) rechnet, und
    # dieselbe wie die Vorschau der Reparatur-Werkbank. Mit allen nannte die
    # Vorschau Zählerstände von Geräten, die es an diesem Tag noch nicht gab.
    invs_by_id = {
        str(inv.id): inv for inv in inv_result.scalars().all() if inv.ist_aktiv_an(datum)
    }

    try:
        preview = await get_reaggregate_preview(db, anlage, invs_by_id, datum)
    except Exception as e:
        logger.error(
            f"Reaggregate-Preview Anlage {anlage_id} {datum}: {type(e).__name__}: {e}"
        )
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    return ReaggregatePreviewResponse(
        datum=datum.isoformat(),
        boundaries=[
            ReaggregatePreviewBoundary(
                sensor_key=b["sensor_key"],
                kategorie=b["kategorie"],
                zeitpunkt=b["zeitpunkt"].isoformat(),
                alt_kwh=b["alt_kwh"],
                neu_kwh=b["neu_kwh"],
            )
            for b in preview["boundaries"]
        ],
        slot_deltas=[
            ReaggregatePreviewSlot(
                stunde=s["stunde"],
                kategorie=s["kategorie"],
                alt_kwh=s["alt_kwh"],
                neu_kwh=s["neu_kwh"],
            )
            for s in preview["slot_deltas"]
        ],
        tagesumme_alt=preview["tagesumme_alt"],
        tagesumme_neu=preview["tagesumme_neu"],
        ha_verfuegbar=preview["ha_verfuegbar"],
        counter_tagesdelta=[
            ReaggregatePreviewCounterTagesdelta(
                feld=c["feld"],
                alt=c["alt"],
                neu=c["neu"],
            )
            for c in preview.get("counter_tagesdelta", [])
        ],
    )

@router.get("/{anlage_id}/kraftstoffpreis-status")
async def kraftstoffpreis_status(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert die Anzahl offener Zeilen ohne Kraftstoffpreis für die UI-Sichtbarkeit.
    """
    from sqlalchemy import func
    from backend.models.monatsdaten import Monatsdaten

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    tages_offen = await db.scalar(
        select(func.count(TagesZusammenfassung.id)).where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.kraftstoffpreis_euro.is_(None),
        )
    )
    monats_offen = await db.scalar(
        select(func.count(Monatsdaten.id)).where(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.kraftstoffpreis_euro.is_(None),
        )
    )
    return {
        "tages_offen": int(tages_offen or 0),
        "monats_offen": int(monats_offen or 0),
        "land": anlage.standort_land or "DE",
    }
