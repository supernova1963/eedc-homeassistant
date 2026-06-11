"""eedc-eigene PV-Prognose-Werte für den HA-Export (#150 Slice A).

Liefert die Vorausschau-Sensoren für `calculate_anlage_sensors()`:
  - Tagesprognose heute, rollend (IST bisher + Σ Rest-Stunden der eedc-Prognose)
  - Rest-Ertrag heute (NUR Σ Prognose der verbleibenden Stunden — Rainer-PN
    2026-06-11: der alte „Rest heute" enthielt das IST und war damit faktisch
    der Tageswert unter irreführendem Namen)
  - Tagesprognose morgen / übermorgen / in 3 Tagen
  - „Speicher voll um" (SoC-Simulation ab AKTUELLEM Speicherstand)
  - das eedc-Stundenprofil heute (als Sensor-Attribut, kein eigenes Topic)

Quellen-Regel (Export-Rahmen): es wird IMMER nur die **eedc-eigene** Prognose
(OpenMeteo × Lernfaktor) exportiert — nie Solcast/SFML, die liegen via eigene
HA-Integration schon in HA. Die gewählte Anzeige-Quelle der Anlage ist hier
deshalb bewusst irrelevant.

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
        (str "HH:00" | None) und ``stundenprofil_heute`` (24 kWh-Werte) —
        oder ``None``.
    """
    if not anlage.latitude or not anlage.longitude:
        return None

    try:
        from backend.services.solar_forecast_service import get_solar_prognose
        from backend.services.pv_orientation import (
            get_pv_kwp,
            get_pv_neigung,
            get_pv_azimut,
            resolve_system_losses,
        )
        from backend.services.prognose_adapter import ist_profil
        from backend.services.verbrauch_prognose_service import get_verbrauch_prognose
        from backend.models.pvgis_prognose import PVGISPrognose
        from backend.api.routes.live_wetter import _get_lernfaktor
        from backend.core.berechnungen.speicher_simulation import simuliere_speicher_tag

        heute = date.today()

        # Aktive PV-/Balkonkraftwerk-Module — kWp + dominante Orientierung
        # (gleicher Pfad wie die Tagesprognose in energie_profil/views.py).
        res = await db.execute(
            select(Investition).where(
                Investition.anlage_id == anlage.id,
                Investition.typ.in_(["pv-module", "balkonkraftwerk"]),
                Investition.aktiv.is_(True),
            )
        )
        invs = [
            i for i in res.scalars().all()
            if not i.stilllegungsdatum or i.stilllegungsdatum >= heute
        ]
        kwp = sum(get_pv_kwp(i) for i in invs)
        if kwp <= 0:
            kwp = anlage.leistung_kwp or 0.0
        if kwp <= 0:
            return None

        pvgis_res = await db.execute(
            select(PVGISPrognose).where(
                PVGISPrognose.anlage_id == anlage.id,
                PVGISPrognose.ist_aktiv == True,  # noqa: E712 (SQLAlchemy-Vergleich)
            ).order_by(PVGISPrognose.abgerufen_am.desc()).limit(1)
        )
        system_losses = resolve_system_losses(pvgis_res.scalar_one_or_none())
        neigung = get_pv_neigung(invs[0]) if invs else 35
        azimut = get_pv_azimut(invs[0]) if invs else 0

        # eedc-Basis = OpenMeteo-GTI; Tag 0..3 (heute + 3 Folgetage)
        prognose = await get_solar_prognose(
            latitude=anlage.latitude,
            longitude=anlage.longitude,
            kwp=kwp,
            neigung=neigung,
            ausrichtung=azimut,
            days=4,
            system_losses=system_losses,
        )
        if not prognose or not prognose.tageswerte:
            return None

        # eedc = OpenMeteo × Lernfaktor (MOS-Kaskade). Kein Lernfaktor → 1.0.
        lernfaktor = await _get_lernfaktor(anlage.id, db) or 1.0
        by_datum = {t.datum: t for t in prognose.tageswerte}

        def _tageswert(offset: int) -> Optional[float]:
            tag = by_datum.get((heute + timedelta(days=offset)).isoformat())
            if not tag or tag.pv_ertrag_kwh is None:
                return None
            return round(tag.pv_ertrag_kwh * lernfaktor, 1)

        heute_tag = by_datum.get(heute.isoformat())
        stunden_kwh_heute = [
            round(
                (
                    heute_tag.stunden_kw[h]
                    if heute_tag and heute_tag.stunden_kw and h < len(heute_tag.stunden_kw)
                    else 0.0
                )
                * lernfaktor,
                3,
            )
            for h in range(24)
        ]

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
