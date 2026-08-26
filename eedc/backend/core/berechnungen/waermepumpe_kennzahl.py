"""Arbeitszahl einer Wärmepumpe — **die eine Definitionsstelle** (ADR-001).

Die Zahl ist ein Quotient aus zwei Zeilen, und genau deshalb steht sie hier:
Ihr Wert ist trivial, ihre **Sperre** ist es nicht. Ob aus Q und E überhaupt
ein Quotient gebildet werden darf, ist eine Abgrenzungsfrage (SOLL Wärme/Klima
§3.2b, Regel **R2**) — und die war bis 2026-08-26 an **drei** Stellen
nachgebaut, davon einer im Client:

======================================  ===================================
Stelle                                  Sperre
======================================  ===================================
``cockpit/komponenten.py:216`` (Hub)    ``jaz_belastbar``
``cockpit/uebersicht.py:456``           ``wp_waerme_abgeleitet <= 0``
``v4/KomponentenSektionen.tsx:311``     **keine**
======================================  ===================================

Die dritte ist die Sicht, die die Melder tatsächlich ansehen (*Cockpit →
Tag/Monat/Jahr*). Sie **konnte** die Sperre nicht kennen: Die Response lieferte
``wp_waerme_kwh`` und ``wp_strom_kwh``, sonst nichts. Folge — dieselbe Anlage
zeigte im Hub „—" und im Cockpit eine Zahl (Befund W-3).

⭐ **Der Fall ist der Lehrsatz von ADR-001 in Reinform:** Nicht die Formel ist
gedriftet, sondern ihre **Voraussetzung**. Eine Aggregat-Formel gehört in den
Layer, damit ihre Bedingungen mitwandern — nicht nur ihr Rechenweg.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

#: Unterhalb dieser Arbeitszahl bekommt die Zahl einen erklärenden Satz
#: (SOLL §2.2.1, Fall **H-B**). Die Grenze ist bewusst großzügig: Eine
#: Wärmepumpe erreicht 3–4, ein elektrischer Heizstab ≈ 1. Alles unter 2 heißt,
#: dass ein erheblicher Teil der Wärme direkt elektrisch erzeugt wurde.
JAZ_HEIZSTAB_SCHWELLE = 2.0


@dataclass(frozen=True)
class Arbeitszahl:
    """Die Arbeitszahl **mit ihrer Begründung** — nie nur die Zahl.

    ``wert`` ist ``None``, wo keine Kennzahl gebildet werden darf; ``grund``
    sagt dann warum. Beides zusammen, weil ein „—" ohne Grund die häufigste
    Beschwerde dieser Fläche ist (SOLL §3.3/**S3**).
    """

    wert: Optional[float]
    #: Warum es die Zahl nicht gibt. **Bewusst kurz** — der Text steht als
    #: sichtbare Zeile unter dem „—", nicht in einem Hover-Tooltip: S3 verlangt
    #: *„nicht ‚—', sondern der Grund"*, und ein Tooltip ist auf dem Telefon
    #: keine Auskunft. Was ausführlicher erklärt werden muss, gehört ins
    #: Handbuch, nicht auf die Kachel.
    grund: Optional[str] = None
    #: Die Zahl ist gebildet, aber erklärungsbedürftig (Fall H-B, Heizstab).
    #: **Kein** Fehler und keine Bewertung — eine Anlage, die ihr Warmwasser
    #: über den Heizstab macht, *hat* eine Arbeitszahl nahe 1.
    hinweis: Optional[str] = None

    @property
    def belastbar(self) -> bool:
        return self.wert is not None


#: Der Satz für Fall H-B. Er erklärt die **Zahl**, er bewertet nicht den
#: Anwender — eedc ist nicht die Strom-Polizei.
HEIZSTAB_HINWEIS = (
    "Eine Arbeitszahl nahe 1 entsteht, wenn ein großer Teil der Wärme direkt "
    "elektrisch erzeugt wurde (Heizstab, Zusatz- oder Notheizung). Die Zahl "
    "beschreibt die Anlage in diesem Zeitraum, sie ist kein Fehler."
)


def waerme_gesamt_kwh(
    waerme_kwh: Optional[float],
    heizung_kwh: Optional[float],
    warmwasser_kwh: Optional[float],
) -> float:
    """Die Wärme **gesamt** — Gesamtwert vor Summanden (D1, kanonisch).

    Liegt eine gemessene Gesamtwärme vor, gilt sie. Sonst ist die Wärme die
    Summe ihrer beiden Achsen.

    ⭐ **Warum das eine Funktion ist:** Die Regel stand im Layer
    (`imd_monatsaggregat`) **und** im Client (`v4/TagKomponenten.tsx:89`, dort
    seit der ersten Fassung der Datei). Der Client hatte nur die zweite Hälfte —
    für den Tag richtig, weil es dort keine gepflegte Gesamtwärme gibt, aber
    eine zweite Stelle für dieselbe Regel (Befund W-9, ADR-001/S1). Seit
    2026-08-26 liefert der Tages-Endpoint die Größe fertig.
    """
    if waerme_kwh:
        return float(waerme_kwh)
    return float(heizung_kwh or 0.0) + float(warmwasser_kwh or 0.0)


#: Grund für die Abgrenzungs-Sperre, wenn der Block Strom von Geräten trägt,
#: deren Wärme fehlt (SOLL §4.2 Fall 1). Kurz — er steht sichtbar auf der Kachel.
GRUND_GERAETE_OHNE_WAERME = "nicht alle Geräte melden Wärme"


def arbeitszahl(
    waerme_kwh: Optional[float],
    strom_kwh: Optional[float],
    *,
    waerme_abgeleitet_kwh: float = 0.0,
    abgrenzung_verletzt: Optional[str] = None,
) -> Arbeitszahl:
    """Q ÷ E — oder der Grund, warum es diese Zahl nicht gibt (**R2**).

    Args:
        waerme_kwh: abgegebene Nutzenergie (thermisch) im Zeitraum.
        strom_kwh: elektrische Energie im selben Zeitraum, am selben Gerät.
        waerme_abgeleitet_kwh: der Anteil von ``waerme_kwh``, der aus
            ``Strom × JAZ`` gerechnet statt gemessen wurde.
        abgrenzung_verletzt: kurzer Grund, wenn Q und E **nicht dieselbe
            Abgrenzung** tragen — anderes Gerät, andere Funktion, anderer
            Zeitraum. ``None`` heißt „keine bekannte Abweichung".

            ⭐ **Bewusst EIN Eingang für alle Abweichungen und keine Liste von
            Flags.** R2 ist *eine* Regel; §4.2 zählt nur Beispiele auf. Ein
            Parameter je Beispiel hätte die Fallsammlung in den Code geholt —
            genau die Bauform, die den bivalenten Fall jahrelang unsichtbar
            gelassen hat. Wer eine weitere Abweichung erkennt, reicht ihren
            Grund hier herein; die Regel selbst bleibt unverändert.

    ⚠ **Der abgeleitete Anteil wird NICHT abgezogen**, sondern sperrt die ganze
    Zahl. Zöge man ihn ab, teilte man gemessene Wärme durch den **Gesamt**strom
    und bekäme eine zu kleine Arbeitszahl — **falsch statt unbekannt**. Die
    Begründung steht ausführlich bei ``WpFakten.jaz_belastbar``, das dieselbe
    Regel für die Monats-Fakten trägt und unverändert bleibt.
    """
    e = float(strom_kwh or 0.0)
    q = float(waerme_kwh or 0.0)
    if e <= 0:
        return Arbeitszahl(None, "kein Stromverbrauch erfasst")
    if q <= 0:
        return Arbeitszahl(None, "kein Wärmemengenzähler zugeordnet")
    if waerme_abgeleitet_kwh > 0:
        return Arbeitszahl(None, "Wärme ist gerechnet, nicht gemessen")
    if abgrenzung_verletzt:
        return Arbeitszahl(None, abgrenzung_verletzt)
    wert = q / e
    return Arbeitszahl(
        wert,
        hinweis=HEIZSTAB_HINWEIS if wert < JAZ_HEIZSTAB_SCHWELLE else None,
    )
