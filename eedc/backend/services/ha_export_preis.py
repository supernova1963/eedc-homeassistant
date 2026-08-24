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
        ``optimierter_durchschnitt_cent``, ``abstand_prozent``, ``abstand_cent``
        (float | None), ``rang_profil``
        (Liste ``{stunde, rang, preis_cent, unter_schwelle, abstand_cent}``),
        ``datum`` (ISO) sowie — sobald die Auktion sie veröffentlicht hat — den
        Satz für **morgen** (``morgen_verfuegbar``, ``datum_morgen``,
        ``rang_profil_morgen``, ``guenstig_schwelle_cent_morgen``,
        ``optimierter_durchschnitt_cent_morgen``) — oder ``None``.

    **Warum morgen mitreist (N-104, Melder rapahl).** Bis v4.0.26 endete der
    Export am laufenden Tag, während ``preis_tag.bewerte_preistag`` jedes Datum
    annimmt und der Preis-Chart auf *Cockpit → Live* längst beide Tage zeigt.
    Wer in HA die Nachtladung für den Folgetag planen wollte, musste sich die
    Kurve selbst holen — rapahl tat das mit einem eigenen Template-Sensor
    (``ladepreis akku morgen``). Die Zahlen dafür hatte eedc, es lieferte sie nur
    nicht aus.

    **Je Tag eine eigene Schwelle.** Day-Ahead ist ein Tagesprodukt; der
    optimierte Ø wird je Kalendertag gebildet (s. Klassen-Docstring von
    ``PreisTag``). Deshalb reist für morgen **auch** die Schwelle und ihre
    Bezugsgröße mit — ohne sie ist im Morgen-Profil keine eigene Regel rechenbar,
    dasselbe Argument wie bei #335/N-105 für heute.

    **Der Kalendertag steht dabei, für beide Tage.** Ein Rang-Profil ohne sein
    Datum ist nach Mitternacht nicht von einem stehengebliebenen zu
    unterscheiden — eine Automation, die dann auf „morgen" plant, plant auf
    gestern.
    """
    try:
        from datetime import timedelta

        from backend.services.preis_tag import (
            DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE, bewerte_preistag,
            jetzt_im_markt, markt_der_anlage,
        )

        markt = markt_der_anlage(anlage)
        now = jetzt_im_markt(markt)

        bewertet = await bewerte_preistag(db, anlage, now.date(), now.hour)
        if bewertet is None:
            return None
        tag, ergebnis = bewertet

        werte = {
            "preis_rang": ergebnis.rang_aktuell,
            "guenstige_stunden_anzahl": ergebnis.guenstige_stunden_anzahl,
            "guenstige_stunden_tag": ergebnis.guenstige_stunden_tag,
            "guenstige_stunden_nacht": ergebnis.guenstige_stunden_nacht,
            "guenstig_schwelle_cent": ergebnis.schwelle_cent,
            "preis_aktuell_cent": ergebnis.preis_aktuell_cent,
            "tages_durchschnitt_cent": ergebnis.tages_durchschnitt_cent,
            "optimierter_durchschnitt_cent": ergebnis.optimierter_durchschnitt_cent,
            "abstand_prozent": ergebnis.abstand_prozent,
            "abstand_cent": ergebnis.abstand_cent,
            "rang_profil": _profil(tag),
            "datum": tag.datum.isoformat(),
        }

        # Vor der Auktion gibt es morgen nicht — dann wird auch nicht gefragt.
        # `fetch_marktpreise` cacht ein LEERES Ergebnis nicht, ein Abruf vor der
        # Veröffentlichung würde also bei jedem Publish-Takt erneut an die
        # Markt-API gehen (Takt-Default 60 min, konfigurierbar bis 5).
        werte["morgen_verfuegbar"] = False
        if now.hour >= DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE:
            morgen = now.date() + timedelta(days=1)
            # Die Stunde ist für morgen bedeutungslos (es gibt dort keine
            # „laufende"); 0 hält `rang_aktuell` deterministisch, benutzt wird
            # aus dem Morgen-Ergebnis nur das Profil und die Tageswerte.
            bewertet_morgen = await bewerte_preistag(db, anlage, morgen, 0)
            if bewertet_morgen is not None:
                tag_m, ergebnis_m = bewertet_morgen
                if tag_m.stunden:
                    werte.update({
                        "morgen_verfuegbar": True,
                        "datum_morgen": tag_m.datum.isoformat(),
                        "rang_profil_morgen": _profil(tag_m),
                        "guenstig_schwelle_cent_morgen": ergebnis_m.schwelle_cent,
                        "optimierter_durchschnitt_cent_morgen":
                            ergebnis_m.optimierter_durchschnitt_cent,
                    })

        return werte
    except Exception as e:  # Export bleibt für die übrigen Sensoren grün
        logger.warning(
            "HA-Export Börsenpreis-Rang fehlgeschlagen (Anlage %s): %s: %s",
            getattr(anlage, "id", "?"), type(e).__name__, e,
        )
        return None


def _profil(tag) -> list[dict]:
    """Ein Tagesprofil in Attribut-Form — dieselbe Gestalt für heute und morgen.

    Das Profil trägt seit v4.0.10 (#335/N-105) das Rohmaterial mit: den
    Stundenpreis und die ungekappte Günstig-Markierung. Vorher stand je Stunde
    nur ``1–5`` oder ``99`` — damit ließ sich in HA weder eine eigene Schwelle
    noch ein eigenes Zeitfenster auswerten, obwohl die Sensor-Referenz genau das
    anbot. Muster: ``stundenprofil_kwh`` der Prognose-Sensoren.

    ``abstand_cent`` je Stunde kam mit N-173 dazu — damit sich eine ct-Schwelle
    („5 ct unter dem Schnitt") über den ganzen Tag auswerten lässt, nicht nur für
    die laufende Stunde.
    """
    return [
        {
            "stunde": s.stunde,
            "rang": s.rang,
            "preis_cent": s.preis_cent,
            "unter_schwelle": s.unter_schwelle,
            "abstand_cent": s.abstand_cent,
        }
        for s in tag.stunden
    ]
