"""Das gemessene Fenster eines Kalendermonats — wie viele seiner Tage schon vorbei sind.

Reine Mathematik (ADR-001), keine DB/IO.

**Wozu.** Ein abgeschlossener Monat und der laufende Monat sehen in einer
Response gleich aus: beide tragen zwölf Monatsgrößen. Nur ist im laufenden
Monat der **Zähler** jeder Quote angefangen und der **Nenner** vollständig —
und ein Quotient aus beidem sagt nichts über die Anlage, sondern über das
Datum. Am 4. August meldete die SOLL-Erfüllung von Gernots Anlage so **19 %**
(264,8 IST gegen das volle Monats-SOLL von 1.387,9 kWh), obwohl dieselbe
Anlage über Jan–Jul auf **119 %** kam; in der Jahres-Kachel wurden daraus
104 % statt 119 % (gemessen 2026-08-04, Fund N-69).

**Die Wahl.** Es gibt zwei Wege, Zähler und Nenner auf dasselbe Fenster zu
bringen: den Zähler-Zeitraum beschneiden (den laufenden Monat auslassen) oder
den Nenner kürzen. Entscheid Gernot 2026-08-04: **den Nenner kürzen** — sonst
verlöre die Monatssicht ihre einzige Einordnung des PV-Werts bis zum
Monatsabschluss. Das ist dieselbe Doktrin, die
`KONZEPT-UNVOLLSTAENDIGE-WERTE.md` §3 für Quotienten formuliert, in ihrer
ehrlich-machenden statt unterdrückenden Variante — und dieselbe, die die
Speicher-Auslastung (#358 Phase 1) seit dem 2026-08-04 anwendet („die Basis
wächst mit"). Sie stand dort **inline** in der Route; nach dem vierten
ADR-001-Nachtrag ist eine Formel nicht durchgesetzt, solange eine Kopie
danebensteht, deshalb liegt sie jetzt hier und hat zwei Aufrufer.

**Der laufende Tag zählt voll mit.** Er ist die konservative Wahl: ihn
wegzulassen machte den Nenner kleiner und die Quote **höher** — also genau die
Richtung, aus der der Fehler kam. Dieselbe Begründung trägt die
Abdeckungs-Angabe des Connectors („2 von 31 Tagen", #360).

**Ein Monat in der Zukunft hat null Tage.** Anteilig ist sein SOLL dann 0, und
die Anzeige-Sites lassen die Quote weg (sie prüfen `> 0`), statt eine
0-%-Erfüllung für einen Monat zu melden, der noch gar nicht stattgefunden hat.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class Monatsfenster:
    """Der gemessene Teil eines Kalendermonats.

    `tage` = 0 (Zukunft) · `tage` < `tage_gesamt` (laufender Monat) ·
    `tage` == `tage_gesamt` (abgeschlossen).
    """

    tage: int
    tage_gesamt: int

    @property
    def ist_angefangen(self) -> bool:
        """True, solange der Monat nicht vollständig vergangen ist."""
        return self.tage < self.tage_gesamt

    @property
    def anteil(self) -> float:
        """Anteil des Monats, der schon gemessen ist (0.0 … 1.0)."""
        return self.tage / self.tage_gesamt if self.tage_gesamt else 0.0


def monatsfenster(jahr: int, monat: int, heute: Optional[date] = None) -> Monatsfenster:
    """Wie viele Tage des Monats (jahr, monat) am Stichtag `heute` vorbei sind.

    `heute` ist ein Parameter und kein `date.today()` im Rumpf, damit Tests die
    Uhr nicht brauchen ([[feedback_tests_ci_hermetisch]]).
    """
    heute = heute or date.today()
    tage_gesamt = monthrange(jahr, monat)[1]
    if (jahr, monat) > (heute.year, heute.month):
        return Monatsfenster(tage=0, tage_gesamt=tage_gesamt)
    if (jahr, monat) < (heute.year, heute.month):
        return Monatsfenster(tage=tage_gesamt, tage_gesamt=tage_gesamt)
    return Monatsfenster(tage=min(heute.day, tage_gesamt), tage_gesamt=tage_gesamt)


def anteilig(wert: Optional[float], fenster: Monatsfenster) -> Optional[float]:
    """Skaliert eine **Monatssumme** auf das gemessene Fenster.

    Nur für Größen sinnvoll, die über den Monat verteilt anfallen — ein SOLL aus
    dem PVGIS-Klimamittel ist so eine. Die Verteilung innerhalb des Monats gilt
    als gleichmäßig: im Hochsommer und Winter trägt das, im März und Oktober
    verschiebt sich der Ertrag innerhalb des Monats spürbar. Die Alternative
    (zwischen den Nachbarmonaten interpolieren) ist ohne zusätzlichen Abruf
    baubar — sie ist bewusst **nicht** gebaut: an der gemessenen Anlage lag der
    Gleichverteilungs-Weg über das Jahr bei 119,8 % gegen 119,2 % aus den
    abgeschlossenen Monaten, also 0,6 Prozentpunkte daneben.

    `None` bleibt `None` — ein fehlendes SOLL wird nicht zu 0.
    """
    if wert is None:
        return None
    return wert * fenster.anteil
