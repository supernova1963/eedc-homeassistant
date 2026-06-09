"""eedc-eigener Börsenpreis-Rang für den HA-Export (#150 Slice B).

Liefert die Trigger-Sensoren für `calculate_anlage_sensors()`:
  - Rang der aktuellen Stunde (1–5 = fünf günstigste je Fenster, 99 = teuer/Rest)
  - Anzahl als günstig markierter Stunden
  - das Rang-Profil des Tages (als Sensor-Attribut, kein eigenes Topic)

Tag- und Nacht-Fenster werden **solar-basiert** getrennt bewertet
(Sonnenauf→-untergang = Tag), das Fenster wandert damit saisonal. eedc liefert
nur den Trigger-Wert — die Lade-/Entlade-Strategie baut der Nutzer in HA.

Robustheit: fehlende Koordinaten / keine Preise → ``None``; die Sensoren
entfallen dann lautlos.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.models.tages_energie_profil import TagesEnergieProfil

logger = logging.getLogger(__name__)

_BERLIN_TZ = ZoneInfo("Europe/Berlin")


async def berechne_preis_export(db, anlage) -> Optional[dict]:
    """Berechnet die Börsenpreis-Rang-Exportwerte einer Anlage.

    Returns:
        dict mit ``preis_rang`` (int | None), ``guenstige_stunden_anzahl`` (int)
        und ``rang_profil`` (Liste ``{stunde, rang}``) — oder ``None``.
    """
    if not anlage.latitude or not anlage.longitude:
        return None

    try:
        from backend.services.strompreis_markt_service import fetch_marktpreise
        from backend.services.solar_forecast_service import sonnenauf_unter_stunde
        from backend.core.berechnungen.preis_rang import berechne_preis_rang

        heute = date.today()
        markt = (anlage.standort_land or "DE").upper()
        if markt not in ("DE", "AT"):
            markt = "DE"

        # Day-Ahead-Kurve (ganztägig bekannt) bevorzugt; sonst das, was bereits
        # im Tagesprofil persistiert ist.
        preise = await fetch_marktpreise(heute, markt)
        if not preise:
            preise = await _persistierte_preise(db, anlage.id, heute)
        if not preise:
            return None

        sonnenaufgang, sonnenuntergang = sonnenauf_unter_stunde(
            heute.isoformat(), anlage.latitude, anlage.longitude
        )
        tag_stunden = {h for h in range(24) if sonnenaufgang <= h < sonnenuntergang}
        nacht_stunden = set(range(24)) - tag_stunden

        now = datetime.now(_BERLIN_TZ)
        ergebnis = berechne_preis_rang(preise, tag_stunden, nacht_stunden, now.hour)

        rang_profil = [
            {"stunde": h, "rang": ergebnis.rang_profil[h]}
            for h in sorted(ergebnis.rang_profil)
        ]
        return {
            "preis_rang": ergebnis.rang_aktuell,
            "guenstige_stunden_anzahl": ergebnis.guenstige_stunden_anzahl,
            "rang_profil": rang_profil,
        }
    except Exception as e:  # Export bleibt für die übrigen Sensoren grün
        logger.warning(
            "HA-Export Börsenpreis-Rang fehlgeschlagen (Anlage %s): %s: %s",
            getattr(anlage, "id", "?"), type(e).__name__, e,
        )
        return None


async def _persistierte_preise(db, anlage_id: int, heute: date) -> dict[int, float]:
    """Fallback: stündliche Börsenpreise aus dem persistierten Tagesprofil."""
    res = await db.execute(
        select(
            TagesEnergieProfil.stunde, TagesEnergieProfil.boersenpreis_cent
        ).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum == heute,
            TagesEnergieProfil.boersenpreis_cent.isnot(None),
        )
    )
    return {stunde: preis for stunde, preis in res.all() if preis is not None}
