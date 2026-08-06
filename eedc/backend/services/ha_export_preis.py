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

⚠ **Beschaffung und Bewertung liegen seit #335 nicht mehr hier**, sondern in
``services/preis_tag.py`` — geteilt mit dem Preis-Chart auf *Cockpit → Live*.
Diese Datei ist damit nur noch die **Export-Formung**: sie wählt den Tag (heute),
die aktuelle Stunde und übersetzt das Ergebnis in die Sensor-/Attribut-Form. Wer
hier eine Zahl ändert, ändert sie für den Chart mit — und das ist der Zweck.
"""

from __future__ import annotations

import logging
from typing import Optional

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
    try:
        from backend.services.preis_tag import (
            bewerte_preistag, jetzt_im_markt, markt_der_anlage,
        )

        markt = markt_der_anlage(anlage)
        now = jetzt_im_markt(markt)

        bewertet = await bewerte_preistag(db, anlage, now.date(), now.hour)
        if bewertet is None:
            return None
        tag, ergebnis = bewertet

        # Das Profil trägt seit v4.1 (#335/N-105) das Rohmaterial mit: den
        # Stundenpreis und die ungekappte Günstig-Markierung. Vorher stand je
        # Stunde nur `1–5` oder `99` — damit ließ sich in HA weder eine eigene
        # Schwelle noch ein eigenes Zeitfenster auswerten, obwohl die
        # Sensor-Referenz genau das anbot. Muster: `stundenprofil_kwh` der
        # Prognose-Sensoren.
        rang_profil = [
            {
                "stunde": s.stunde,
                "rang": s.rang,
                "preis_cent": s.preis_cent,
                "unter_schwelle": s.unter_schwelle,
            }
            for s in tag.stunden
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
