"""Bewerteter Börsenpreis-Tag — die gemeinsame Quelle von HA-Export und Live-Chart (#335).

**Warum diese Datei existiert.** Bis v4.0.9 gab es genau *einen* Konsumenten der
Rang-Logik: ``ha_export_preis.berechne_preis_export`` für die HA-Sensoren. Mit dem
Preis-Chart auf *Cockpit → Live* kommt ein zweiter dazu — und beide müssen dieselbe
Antwort auf „ist diese Stunde günstig?" geben. Ein Chart, der andere Stunden grün
färbt als der Sensor ``eedc_preis_rang`` meldet, ist kein Darstellungsdetail, sondern
zwei Wahrheiten über dieselbe Größe. Genau diese Klasse (dieselbe Kennzahl an zwei
Stellen nachgebaut) hat in diesem Projekt mehrfach Drift erzeugt; deshalb liegt die
Beschaffung **und** die Bewertung eines Tages hier, und beide Aufrufer rufen sie.

**Was hier passiert und was nicht.** Diese Schicht beschafft (Markt-API mit Fallback
auf das persistierte Tagesprofil), bestimmt das Tag-/Nacht-Fenster solar-basiert und
ruft die reine Formel ``core.berechnungen.preis_rang`` — sie rechnet selbst nichts
(ADR-001). Die Zeitzone ist die der **Gebotszone**, nicht die des Prozesses (F-6).

**Der Tag ist die Bemessungsgrenze.** Schwelle und optimierter Ø werden je Kalendertag
gebildet, auch wenn der Chart zwei Tage nebeneinander zeigt: Day-Ahead ist ein
Tagesprodukt, und der HA-Sensor rechnet ebenso. Ein 48-Stunden-Topf würde an einem
teuren Tag *keine* günstige Stunde markieren und am billigen Tag fast alle — und
beides stünde im Widerspruch zu dem, was die Sensoren derselben Anlage melden.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select

from backend.models.tages_energie_profil import TagesEnergieProfil

logger = logging.getLogger(__name__)

# Fallback-Günstig-Faktor, wenn die Anlage keinen (oder einen aus dem Rahmen
# gefallenen) Prozentwert trägt — deckungsgleich mit dem Default in
# `core/berechnungen/preis_rang.py`.
GUENSTIG_PROZENT_DEFAULT = 10.0


@dataclass
class PreisStunde:
    """Eine bewertete Stunde des Tages."""

    stunde: int
    preis_cent: float
    rang: int
    unter_schwelle: bool


@dataclass
class PreisTag:
    """Ein vollständig bewerteter Börsenpreis-Tag.

    ``stunden`` trägt nur Stunden mit Preis. Am Ende der Sommerzeit fehlt die
    zweite Zwei-Uhr-Stunde (die erste gewinnt), im Frühjahr fehlt die Stunde 2
    ganz — der Tag hat dann 23 Einträge, und das ist richtig so. Wer die Länge
    prüft, prüft **nicht** auf 24 (F-6).
    """

    datum: date
    stunden: list[PreisStunde]
    schwelle_cent: Optional[float]
    optimierter_durchschnitt_cent: Optional[float]
    markt: str


async def lade_preistag(
    db,
    anlage,
    datum: date,
    aktuelle_stunde: int = 0,
) -> Optional[PreisTag]:
    """Beschafft und bewertet die Börsenpreise **eines** Tages.

    Args:
        db: DB-Session (für den Fallback auf persistierte Preise).
        anlage: Anlage — liefert Markt, Koordinaten und Günstig-Schwelle.
        datum: der zu bewertende Tag, in der Zeitzone der Gebotszone.
        aktuelle_stunde: nur für ``rang_aktuell`` des Aufrufers relevant; die
            Stundenbewertung selbst hängt nicht davon ab.

    Returns:
        ``PreisTag`` oder ``None``, wenn weder Markt-API noch Tagesprofil
        Preise liefern (bzw. die Anlage keine Koordinaten hat — ohne sie gibt
        es kein Tag-/Nacht-Fenster).
    """
    ergebnis = await bewerte_preistag(db, anlage, datum, aktuelle_stunde)
    return None if ergebnis is None else ergebnis[0]


async def bewerte_preistag(db, anlage, datum: date, aktuelle_stunde: int):
    """Wie :func:`lade_preistag`, gibt zusätzlich das rohe Rang-Ergebnis zurück.

    Der HA-Export braucht Felder, die der Chart nicht zeigt (``rang_aktuell``,
    ``guenstige_stunden_tag/_nacht``, ``abstand_prozent``). Statt sie in
    ``PreisTag`` mitzuschleppen — wo sie für den Chart bedeutungslos wären und
    die Frage aufwürfen, auf welche Stunde sie sich bei zwei Tagen beziehen —
    reicht diese Funktion das Original durch.

    Returns:
        ``(PreisTag, PreisRangErgebnis)`` oder ``None``.
    """
    if not anlage.latitude or not anlage.longitude:
        return None

    from backend.services.strompreis_markt_service import fetch_marktpreise
    from backend.services.solar_forecast_service import sonnenauf_unter_stunde
    from backend.core.berechnungen.preis_rang import berechne_preis_rang

    markt = markt_der_anlage(anlage)

    # Day-Ahead-Kurve (ganztägig bekannt) bevorzugt; sonst das, was bereits im
    # Tagesprofil persistiert ist. Für morgen greift der Fallback nie — dort
    # gibt es noch keine Aggregation.
    preise = await fetch_marktpreise(datum, markt)
    if not preise:
        preise = await persistierte_preise(db, anlage.id, datum)
    if not preise:
        return None

    sonnenaufgang, sonnenuntergang = sonnenauf_unter_stunde(
        datum.isoformat(), anlage.latitude, anlage.longitude
    )
    tag_stunden = {h for h in range(24) if sonnenaufgang <= h < sonnenuntergang}
    nacht_stunden = set(range(24)) - tag_stunden

    ergebnis = berechne_preis_rang(
        preise, tag_stunden, nacht_stunden, aktuelle_stunde,
        schwelle_faktor=schwelle_faktor(anlage),
    )

    stunden = [
        PreisStunde(
            stunde=h,
            preis_cent=preise[h],
            rang=ergebnis.rang_profil[h],
            unter_schwelle=ergebnis.unter_schwelle_profil.get(h, False),
        )
        for h in sorted(ergebnis.rang_profil)
        if preise.get(h) is not None
    ]
    tag = PreisTag(
        datum=datum,
        stunden=stunden,
        schwelle_cent=ergebnis.schwelle_cent,
        optimierter_durchschnitt_cent=ergebnis.optimierter_durchschnitt_cent,
        markt=markt,
    )
    return tag, ergebnis


def markt_der_anlage(anlage) -> str:
    """Gebotszone der Anlage — heute nur DE und AT, alles andere fällt auf DE."""
    markt = (getattr(anlage, "standort_land", None) or "DE").upper()
    return markt if markt in ("DE", "AT") else "DE"


def schwelle_faktor(anlage) -> float:
    """Günstig-Faktor der Anlage (Prozent unter Ø → Faktor).

    ⚠ **0 % schaltet die Schwelle nicht ab**, sondern legt sie genau auf den
    optimierten Ø: ``1,0 − 0/100 = 1,0``. Der gegenteilige Satz stand bis v4.0
    in Oberfläche und Handbuch und war seit v3.44 falsch; der Top-5-Deckel hat
    ihn verdeckt.
    """
    prozent = getattr(anlage, "guenstig_schwelle_prozent", None)
    if prozent is None or not (0 <= prozent <= 50):
        prozent = GUENSTIG_PROZENT_DEFAULT
    return 1.0 - prozent / 100.0


async def persistierte_preise(db, anlage_id: int, datum: date) -> dict[int, float]:
    """Fallback: stündliche Börsenpreise aus dem persistierten Tagesprofil."""
    res = await db.execute(
        select(
            TagesEnergieProfil.stunde, TagesEnergieProfil.boersenpreis_cent
        ).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum == datum,
            TagesEnergieProfil.boersenpreis_cent.isnot(None),
        )
    )
    return {stunde: preis for stunde, preis in res.all() if preis is not None}


def jetzt_im_markt(markt: str) -> datetime:
    """Aktuelle Zeit in der Zeitzone der Gebotszone (F-6).

    Datum **und** Stunde stammen aus derselben Zone. Vorher kam der Tag aus der
    Prozesszone und die Stunde hart aus ``Europe/Berlin``: auf einem
    UTC-Container fragte eedc zwischen 00:00 und 02:00 Ortszeit die Preise von
    *gestern* ab und suchte darin die Stunde 0 von *heute*.
    """
    from backend.services.strompreis_markt_service import _markt_tz

    return datetime.now(_markt_tz(markt))
