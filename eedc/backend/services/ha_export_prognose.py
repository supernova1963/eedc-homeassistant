"""eedc-eigene PV-Prognose-Werte für den HA-Export (#150 Slice A).

Liefert die Vorausschau-Sensoren für `calculate_anlage_sensors()`:
  - Tagesprognose heute, rollend (IST bisher + Σ Rest-Stunden der eedc-Prognose)
  - Rest-Ertrag heute (NUR Σ Prognose der verbleibenden Stunden — Rainer-PN
    2026-06-11: der alte „Rest heute" enthielt das IST und war damit faktisch
    der Tageswert unter irreführendem Namen)
  - Tagesprognose morgen / übermorgen / in 3 Tagen
  - „Speicher voll um" (SoC-Simulation ab AKTUELLEM Speicherstand)
  - die eedc-Stundenprofile heute + Tag+1/2/3 (als Sensor-Attribut, kein
    eigenes Topic)

Prognose-Basis: ``eedc_prognose_service`` — OpenMeteo-GTI-Stundenprofil ×
Korrekturprofil-Kaskade pro Stunde (Legacy-Skalar als Fallback), Tageswert =
Σ korrigierte Stunden-Slots (Invariante: Sensor-State == Σ Attribut-Slots).
Gleicher Pfad wie die „eedc"-Spalte im Prognosen-Vergleich.

Quellen-Regel (Export-Rahmen): es wird IMMER nur die **eedc-eigene** Prognose
exportiert — nie Solcast/SFML, die liegen via eigene HA-Integration schon in
HA. Die gewählte Anzeige-Quelle der Anlage ist hier deshalb bewusst
irrelevant.

Robustheit: fehlende Koordinaten / keine PV / Netzwerkfehler → ``None``; die
Sensoren entfallen dann lautlos (Export bleibt für die übrigen Sensoren grün).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil

logger = logging.getLogger(__name__)

_BERLIN_TZ = ZoneInfo("Europe/Berlin")


async def berechne_prognose_export(db, anlage) -> Optional[dict]:
    """Berechnet die eedc-eigenen PV-Prognose-Exportwerte einer Anlage.

    Returns:
        dict mit ``heute_kwh`` (rollender Tageswert = IST bisher + Rest),
        ``rest_today_kwh`` (nur Σ verbleibende Stunden), ``day_plus_1_kwh``,
        ``day_plus_2_kwh``, ``day_plus_3_kwh``, ``speicher_voll_um``
        (str "HH:00" | None), ``stundenprofil_heute`` und
        ``stundenprofil_day_plus_1/2/3`` (je 24 kWh-Slots) — oder ``None``.
    """
    try:
        from backend.services.eedc_prognose_service import berechne_eedc_prognose
        from backend.services.prognose_adapter import ist_profil
        from backend.services.verbrauch_prognose_service import get_verbrauch_prognose
        from backend.core.berechnungen.speicher_simulation import simuliere_speicher_tag

        heute = date.today()

        prognose = await berechne_eedc_prognose(db, anlage, days=4)
        if not prognose:
            return None

        def _tageswert(offset: int) -> Optional[float]:
            tag = prognose.tage[offset] if offset < len(prognose.tage) else None
            return tag.tageswert_kwh if tag else None

        def _stundenprofil(offset: int) -> Optional[list]:
            tag = prognose.tage[offset] if offset < len(prognose.tage) else None
            if tag is None or tag.profil is None:
                return None
            return list(tag.profil.stundenprofil_export_kwh)

        heute_tag = prognose.tage[0] if prognose.tage else None
        stunden_kwh_heute = (
            list(heute_tag.profil.stunden_kwh)
            if heute_tag and heute_tag.profil
            else [0.0] * 24
        )

        # Rest = Σ Prognose-Slots der verbleibenden Stunden; rollender
        # Tageswert „heute" = IST bisher + Rest.
        now = datetime.now(_BERLIN_TZ)
        ist_res = await db.execute(
            select(TagesEnergieProfil).where(
                TagesEnergieProfil.anlage_id == anlage.id,
                TagesEnergieProfil.datum == heute,
            ).order_by(TagesEnergieProfil.stunde)
        )
        ist_p = ist_profil(ist_res.scalars().all(), jetzt_stunde=now.hour, datum=heute)
        ist_bisher = ist_p.tageswert_kwh or 0.0
        rest_today = round(sum(stunden_kwh_heute[h] for h in range(now.hour + 1, 24)), 1)
        heute_kwh = round(ist_bisher + rest_today, 1)

        # „Speicher voll um" — Simulation ab aktuellem SoC (nicht Mitternacht).
        speicher_voll_um = None
        speicher_kap, akt_soc = await _aktueller_speicher(db, anlage.id, heute)
        if speicher_kap > 0 and akt_soc is not None:
            vp = await get_verbrauch_prognose(anlage.id, heute, db)
            verbrauch_stunden = vp["stunden_kw"] if vp else [0.0] * 24
            sim = simuliere_speicher_tag(
                pv_stunden=stunden_kwh_heute,
                verbrauch_stunden=verbrauch_stunden,
                speicher_kap_kwh=speicher_kap,
                start_soc_prozent=akt_soc,
                start_stunde=now.hour,
            )
            speicher_voll_um = sim.speicher_voll_um

        return {
            "heute_kwh": heute_kwh,
            "rest_today_kwh": rest_today,
            "day_plus_1_kwh": _tageswert(1),
            "day_plus_2_kwh": _tageswert(2),
            "day_plus_3_kwh": _tageswert(3),
            "speicher_voll_um": speicher_voll_um,
            "stundenprofil_heute": [round(v, 2) for v in stunden_kwh_heute],
            "stundenprofil_day_plus_1": _stundenprofil(1),
            "stundenprofil_day_plus_2": _stundenprofil(2),
            "stundenprofil_day_plus_3": _stundenprofil(3),
        }
    except Exception as e:  # Export bleibt für die übrigen Sensoren grün
        logger.warning(
            "HA-Export PV-Prognose fehlgeschlagen (Anlage %s): %s: %s",
            getattr(anlage, "id", "?"), type(e).__name__, e,
        )
        return None


async def _aktueller_speicher(db, anlage_id: int, heute: date) -> tuple[float, Optional[float]]:
    """(Speicher-Kapazität kWh, aktueller SoC %).

    Der „aktuelle SoC" ist der zuletzt gespeicherte Stunden-SoC (heute, sonst
    gestern) aus ``TagesEnergieProfil`` — robust und ohne Live-Abhängigkeit.
    """
    res = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "speicher",
            Investition.aktiv.is_(True),
        )
    )
    speicher = [
        i for i in res.scalars().all()
        if not i.stilllegungsdatum or i.stilllegungsdatum >= heute
    ]
    kap = sum((i.parameter or {}).get("kapazitaet_kwh", 0) or 0 for i in speicher)
    if kap <= 0:
        return 0.0, None

    soc_res = await db.execute(
        select(TagesEnergieProfil.soc_prozent).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= heute - timedelta(days=1),
            TagesEnergieProfil.soc_prozent.isnot(None),
        ).order_by(
            TagesEnergieProfil.datum.desc(), TagesEnergieProfil.stunde.desc()
        ).limit(1)
    )
    return float(kap), soc_res.scalar_one_or_none()
