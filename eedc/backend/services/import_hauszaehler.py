"""Hauszähler-Werte beim gerätegebundenen Import — übernehmen statt summieren.

**Warum es diese Datei gibt.** Der Cloud-Import kann seit N-229 (#349, OliS2811) auf
eine **Station** gerichtet werden: „diese Quelle misst diesen Wechselrichter". Die
Werte gehen dann an dessen PV-Module und Speicher, nicht an die Anlage — richtig, denn
Erzeugung und Speicherumsatz sind **stationsspezifisch**, und ein Anlagen-Aggregat aus
einer von zwei Stationen wäre die von ADR-002/**P7** verbotene Teilsumme.

⛔ **Für Einspeisung und Netzbezug galt dieselbe Begründung — fachlich falsch** (Gernot,
2026-08-12). Ein Wechselrichter *misst* diese Größen nicht: er bekommt sie vom
**Smartmeter am Hausanschluss** oder aus einem abgelesenen Zählerstand. Zwei
Wechselrichter an einem Anschluss liefern deshalb **denselben** Wert, nicht zwei Teile
davon — sie sind **redundant, nicht partiell**. Verboten ist allein das **Summieren**
(die zweite Einfuhr würde den Hausanschluss verdoppeln); das **Übernehmen** ist richtig,
weil eine Station bereits den vollständigen Anlagenwert trägt.

Die Folge des Fehlers war ein Anwender ohne Monatsabschluss: sein Import lief durch, die
Modulwerte kamen an, die Zählerzeile entstand nie — und jeder erneute Import wiederholte
das. Sichtbar wurde es als „Monat fehlt" im Daten-Checker bei gleichzeitig korrekten
Zahlen im Cockpit.

**Was hier NICHT entschieden wird:** ob überhaupt geschrieben werden *darf*. Die
Hierarchie (manuell gepflegt schlägt Import) bleibt Sache von
``services/provenance.py::write_with_provenance``. Diese Funktion sagt nur, *welcher*
Wert der Wahrheit am nächsten kommt — und wann eedc lieber fragt, als zu raten.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Zwei Stationen am selben Hausanschluss melden denselben Zählerstand, aber jede
# rundet ihn selbst (Solarman auf eine Dezimale). Unterhalb dieser Schwelle ist
# eine Abweichung Rundung und keine Meldung wert; darüber ist sie ein Sachverhalt,
# den der Anwender kennen muss.
TOLERANZ_KWH = 1.0
TOLERANZ_ANTEIL = 0.01


@dataclass(frozen=True)
class HauszaehlerEntscheid:
    """Was der gerätegebundene Import mit den Hauszähler-Größen tun soll."""

    einspeisung_kwh: Optional[float]
    netzbezug_kwh: Optional[float]
    warnung: Optional[str] = None
    #: Diagnose-Schlüssel, damit Tests und Logs den Zweig benennen können.
    grund: str = ""

    @property
    def schreiben(self) -> bool:
        """Ob überhaupt ein Feld geschrieben werden soll."""
        return self.einspeisung_kwh is not None or self.netzbezug_kwh is not None


def _hat_messung(einspeisung: Optional[float], netzbezug: Optional[float]) -> bool:
    """Trägt diese Station überhaupt einen Hauszähler?

    Ein Wechselrichter **ohne** angebundenes Smartmeter meldet für beide Größen
    ``None`` oder ``0`` — die Cloud reicht durch, was das Gerät sieht. Beide
    Größen gleichzeitig echt 0 gibt es an einem bewohnten Hausanschluss nicht:
    ohne Einspeisung fällt Netzbezug an und umgekehrt. Genau diese Station darf
    einen bereits vorhandenen, echten Wert nicht überschreiben.
    """
    return any(w is not None and w > 0 for w in (einspeisung, netzbezug))


def _weicht_ab(neu: Optional[float], bestand: Optional[float]) -> bool:
    """Abweichung jenseits von Rundung? ``None`` auf einer Seite ist keine."""
    if neu is None or bestand is None:
        return False
    grenze = max(TOLERANZ_KWH, abs(bestand) * TOLERANZ_ANTEIL)
    return abs(neu - bestand) > grenze


def _zahl(wert: Optional[float]) -> str:
    """Deutsche Schreibweise für den Warntext (Dezimalkomma)."""
    if wert is None:
        return "—"
    return f"{wert:.1f}".replace(".", ",")


def entscheide_hauszaehler(
    *,
    neu_einspeisung_kwh: Optional[float],
    neu_netzbezug_kwh: Optional[float],
    bestand_einspeisung_kwh: Optional[float] = None,
    bestand_netzbezug_kwh: Optional[float] = None,
    hat_bestandszeile: bool = False,
    ueberschreiben: bool = False,
    quelle_bezeichnung: str = "Diese Quelle",
) -> HauszaehlerEntscheid:
    """Entscheidet, welche Hauszähler-Werte der Stationsimport schreibt.

    Args:
        neu_einspeisung_kwh: Was die importierte Station für den Monat meldet.
        neu_netzbezug_kwh: dito.
        bestand_einspeisung_kwh: Was in der Monatszeile bereits steht (z. B. von
            der zuerst importierten Station).
        bestand_netzbezug_kwh: dito.
        hat_bestandszeile: Ob für den Monat schon eine ``Monatsdaten``-Zeile
            existiert. Ohne sie sind die Bestandswerte bedeutungslos.
        ueberschreiben: Der Haken des Wizards. Er entscheidet **nur** den
            Konfliktfall — nie, ob eine leere Station gewinnen darf.
        quelle_bezeichnung: Name der Station für den Warntext.

    Returns:
        Ein ``HauszaehlerEntscheid``. ``schreiben=False`` heißt: diese Station
        hat zu den Hauszähler-Größen nichts beizutragen.
    """
    # 1) Station ohne Smartmeter — sie darf nie gewinnen, auch nicht mit Haken.
    #    Ihre 0 ist ein „weiß nicht", kein gemessener Nullwert.
    if not _hat_messung(neu_einspeisung_kwh, neu_netzbezug_kwh):
        if hat_bestandszeile:
            # Der Monat ist versorgt; dass diese Station nichts liefert, ist
            # dann kein Ereignis.
            return HauszaehlerEntscheid(None, None, grund="keine_messung_bestand_bleibt")
        return HauszaehlerEntscheid(
            None,
            None,
            warnung=(
                f"{quelle_bezeichnung} liefert keine Zählerwerte (Einspeisung/Netzbezug). "
                "Erzeugung und Speicher wurden übernommen; für den Monatsabschluss fehlen "
                "die Hauszähler-Werte — trage sie im Monatsabschluss nach oder ordne einen "
                "HA-Sensor am Hausanschluss zu."
            ),
            grund="keine_messung_kein_bestand",
        )

    # 2) Noch kein Monat vorhanden — die Station begründet ihn.
    if not hat_bestandszeile:
        return HauszaehlerEntscheid(
            neu_einspeisung_kwh, neu_netzbezug_kwh, grund="neu"
        )

    # 3) Monat vorhanden. Gleiche Werte sind der Normalfall: zwei Stationen am
    #    selben Hausanschluss sehen denselben Zähler. Schreiben ist dann
    #    idempotent — der Wert bleibt, was er war.
    konflikte = [
        (feld, neu, bestand)
        for feld, neu, bestand in (
            ("Einspeisung", neu_einspeisung_kwh, bestand_einspeisung_kwh),
            ("Netzbezug", neu_netzbezug_kwh, bestand_netzbezug_kwh),
        )
        if _weicht_ab(neu, bestand)
    ]

    if not konflikte:
        return HauszaehlerEntscheid(
            neu_einspeisung_kwh, neu_netzbezug_kwh, grund="deckungsgleich"
        )

    # 4) Konflikt. eedc rät nicht, welcher Zähler recht hat — es sagt es.
    #    Über das Ergebnis entscheidet der Haken des Anwenders; gemeldet wird
    #    in BEIDEN Fällen, sonst hinge das Ergebnis still an der
    #    Import-Reihenfolge.
    details = " · ".join(
        f"{feld} {_zahl(bestand)} → {_zahl(neu)} kWh" for feld, neu, bestand in konflikte
    )
    if ueberschreiben:
        return HauszaehlerEntscheid(
            neu_einspeisung_kwh,
            neu_netzbezug_kwh,
            warnung=(
                f"{quelle_bezeichnung} meldet andere Zählerwerte als bereits erfasst "
                f"({details}) — der neue Wert wurde übernommen, weil „Bestehende Monate "
                "überschreiben\" gesetzt ist. Zwei Wechselrichter an einem Hausanschluss "
                "sollten denselben Zähler sehen; prüfe, ob beide dasselbe Smartmeter lesen."
            ),
            grund="konflikt_ueberschrieben",
        )
    return HauszaehlerEntscheid(
        None,
        None,
        warnung=(
            f"{quelle_bezeichnung} meldet andere Zählerwerte als bereits erfasst "
            f"({details}) — die vorhandenen Werte wurden behalten. Zwei Wechselrichter an "
            "einem Hausanschluss sollten denselben Zähler sehen; prüfe, ob beide dasselbe "
            "Smartmeter lesen."
        ),
        grund="konflikt_bestand_behalten",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Zweiter Pfad: der Cloud-Abruf im Monatsabschluss
# ═══════════════════════════════════════════════════════════════════════════
#
# Dort wird nicht geschrieben, sondern **vorgeschlagen** — mehrere gespeicherte
# Quellen liefern nebeneinander. Bis 2026-08-12 galt dieselbe falsche Regel wie
# im Import: nur eine Quelle **ohne** Geräte-Zuordnung durfte Hauszähler-Größen
# beisteuern. Wer wie der Melder ausschließlich zugeordnete Stationen führt,
# bekam für Einspeisung und Netzbezug also nie einen Vorschlag — obwohl jede
# seiner Stationen den Wert kennt.


@dataclass(frozen=True)
class HauszaehlerQuelle:
    """Was eine Cloud-Quelle zu den Größen des Hausanschlusses beiträgt."""

    herkunft: str
    #: Quelle ohne Geräte-Zuordnung — sie misst erklärtermaßen die ganze Anlage.
    ohne_ziel: bool
    einspeisung_kwh: Optional[float]
    netzbezug_kwh: Optional[float]


@dataclass(frozen=True)
class HauszaehlerWahl:
    einspeisung_kwh: Optional[float]
    netzbezug_kwh: Optional[float]
    herkunft: Optional[str] = None
    hinweis: Optional[str] = None


def waehle_hauszaehler_quelle(
    kandidaten: "list[HauszaehlerQuelle]",
) -> HauszaehlerWahl:
    """Welche Quelle liefert den Vorschlag für Einspeisung und Netzbezug?

    * Quellen **ohne** Messung (kein Smartmeter am Gerät) scheiden aus — ihre 0
      ist ein „weiß nicht".
    * Eine Quelle **ohne Geräte-Zuordnung** hat Vorrang: sie ist erklärtermaßen
      für die ganze Anlage eingerichtet.
    * Sonst gewinnt die erste Station mit Messung. Das ist keine Willkür: an
      einem Hausanschluss sehen alle denselben Zähler.
    * Weichen zwei Quellen voneinander ab, sagt eedc es, statt still eine zu
      nehmen.
    """
    mit_messung = [
        k for k in kandidaten if _hat_messung(k.einspeisung_kwh, k.netzbezug_kwh)
    ]
    if not mit_messung:
        return HauszaehlerWahl(None, None)

    gewaehlt = next((k for k in mit_messung if k.ohne_ziel), mit_messung[0])

    abweichler = [
        k.herkunft
        for k in mit_messung
        if k is not gewaehlt
        and (
            _weicht_ab(k.einspeisung_kwh, gewaehlt.einspeisung_kwh)
            or _weicht_ab(k.netzbezug_kwh, gewaehlt.netzbezug_kwh)
        )
    ]
    hinweis = None
    if abweichler:
        hinweis = (
            f"Einspeisung und Netzbezug stammen aus '{gewaehlt.herkunft}'. "
            f"Abweichende Werte meldet außerdem: {', '.join(abweichler)}. "
            "An einem Hausanschluss sollten alle Geräte denselben Zähler sehen — "
            "prüfe die Werte, bevor du den Monat abschließt."
        )

    return HauszaehlerWahl(
        gewaehlt.einspeisung_kwh, gewaehlt.netzbezug_kwh,
        herkunft=gewaehlt.herkunft, hinweis=hinweis,
    )
