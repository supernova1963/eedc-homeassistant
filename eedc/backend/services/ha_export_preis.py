"""eedc-eigener Börsenpreis-Rang für den HA-Export (#150 Slice B).

Liefert die Trigger-Sensoren für `calculate_anlage_sensors()`:
  - Rang der aktuellen Stunde (1–5 = günstigste je Fenster UND unter der
    Günstig-Schwelle, 99 = teuer/Rest — Schwelle seit Rainer-PN 2026-06-11;
    Default 10 % unter Ø-ohne-3-Peaks, pro Anlage einstellbar via
    ``Anlage.guenstig_schwelle_prozent``)
  - Anzahl als günstig markierter Stunden (gesamt + Tag/Nacht getrennt)
  - das Rang-Profil des Tages + die Günstig-Schwelle (als Sensor-Attribute,
    kein eigenes Topic)

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

from sqlalchemy import select

from backend.models.tages_energie_profil import TagesEnergieProfil

logger = logging.getLogger(__name__)


async def berechne_preis_export(db, anlage) -> Optional[dict]:
    """Berechnet die Börsenpreis-Rang-Exportwerte einer Anlage.

    Returns:
        dict mit ``preis_rang`` (int | None), ``guenstige_stunden_anzahl``,
        ``guenstige_stunden_tag``, ``guenstige_stunden_nacht`` (int),
        ``guenstig_schwelle_cent``, ``preis_aktuell_cent``,
        ``optimierter_durchschnitt_cent``, ``abstand_prozent``
        (float | None) und ``rang_profil``
        (Liste ``{stunde, rang, preis_cent, unter_schwelle}``) — oder ``None``.
    """
    if not anlage.latitude or not anlage.longitude:
        return None

    try:
        from backend.services.strompreis_markt_service import fetch_marktpreise, _markt_tz
        from backend.services.solar_forecast_service import sonnenauf_unter_stunde
        from backend.core.berechnungen.preis_rang import berechne_preis_rang

        markt = (anlage.standort_land or "DE").upper()
        if markt not in ("DE", "AT"):
            markt = "DE"

        # Datum UND Stunde aus derselben Zone — der Zone, in der auch die
        # Börsenpreise ihren Tag zählen (F-6). Vorher kam der Tag aus der
        # Prozesszone (`date.today()`) und die Stunde hart aus Europe/Berlin:
        # auf einem UTC-Container fragte eedc zwischen 00:00 und 02:00
        # Ortszeit die Preise von **gestern** ab und suchte darin die Stunde 0
        # von heute.
        now = datetime.now(_markt_tz(markt))
        heute = now.date()

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

        # Günstig-Faktor pro Anlage (Prozent unter Ø → Faktor); None/aus dem
        # Schema-Rahmen gefallene Werte → Default 10 %.
        prozent = anlage.guenstig_schwelle_prozent
        if prozent is None or not (0 <= prozent <= 50):
            prozent = 10.0
        schwelle_faktor = 1.0 - prozent / 100.0

        ergebnis = berechne_preis_rang(
            preise, tag_stunden, nacht_stunden, now.hour,
            schwelle_faktor=schwelle_faktor,
        )

        # Das Profil trägt seit v4.1 (#335/N-105) das Rohmaterial mit: den
        # Stundenpreis und die ungekappte Günstig-Markierung. Vorher stand je
        # Stunde nur `1–5` oder `99` — damit ließ sich in HA weder eine eigene
        # Schwelle noch ein eigenes Zeitfenster auswerten, obwohl die
        # Sensor-Referenz genau das anbot. Muster: `stundenprofil_kwh` der
        # Prognose-Sensoren.
        rang_profil = [
            {
                "stunde": h,
                "rang": ergebnis.rang_profil[h],
                "preis_cent": preise.get(h),
                "unter_schwelle": ergebnis.unter_schwelle_profil.get(h, False),
            }
            for h in sorted(ergebnis.rang_profil)
        ]
        return {
            "preis_rang": ergebnis.rang_aktuell,
            "guenstige_stunden_anzahl": ergebnis.guenstige_stunden_anzahl,
            "guenstige_stunden_tag": ergebnis.guenstige_stunden_tag,
            "guenstige_stunden_nacht": ergebnis.guenstige_stunden_nacht,
            "guenstig_schwelle_cent": ergebnis.schwelle_cent,
            "preis_aktuell_cent": ergebnis.preis_aktuell_cent,
            "optimierter_durchschnitt_cent": ergebnis.optimierter_durchschnitt_cent,
            "abstand_prozent": ergebnis.abstand_prozent,
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
