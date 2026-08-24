"""Die anlagenweite Nennleistung in kWp — EIN Nenner für alle Kennzahlen (F-58).

SoT für die Frage „durch welche kWp teile ich?" (ADR-001: Aggregat-Formeln
leben in `core/berechnungen/`). Konsumenten sind alle Stellen, die eine
anlagenweite Energiemenge auf die installierte Leistung beziehen —
spezifischer Ertrag, Performance Ratio, Auslastung, Plausibilitätsschwellen.

**Warum es diesen Helper gibt.** Bis dahin standen zwei Nenner nebeneinander:

* `Anlage.leistung_kwp` — ein manuell gepflegter Skalar. Sein eigener
  Model-Docstring nennt ihn „Referenzwert, echte Leistung = Summe der
  PV-Module"; der Setup-Wizard *erzeugt* die PV-Modul-Investitionen aus ihm
  (`InvestitionenStep.tsx`). Danach ist er eine Kopie, die veraltet, sobald
  jemand die Investitionen korrigiert — und **nichts** im Baum hielt die
  beiden Zahlen noch gegeneinander (der Summenvergleich im Stammdaten-Check
  ist am 04.08. mit N-76 Stufe 1 entfallen, ohne dass sein Wegfall auffiel).
* Die Σ über die Erzeuger-Investitionen — kannte Stilllegung, Anschaffung
  und die BKW-Abtretung, stand aber nur an vier von fünfzehn Stellen.

Gemeldet hat es NoahPaulick (simon42 T89667 #188, v4.0.26): nach dem Trennen
einer ursprünglich gemeinsamen Anlage meldete der Daten-Checker vier Tage mit
„PV-Doppelerfassung" bei einem spezifischen Tagesertrag, der um exakt den
Faktor 2 danebenlag. Seine Rohdaten waren korrekt — der Nenner war es nicht.

**Die Grundgesamtheit muss zum Zähler passen.** Das ist der Grund für
`mit_bkw`: `summe_pv_bkw_kwh` zählt Balkonkraftwerke mit, `summe_pv_anlage_kwh`
nicht. Ein BKW-Ertrag über einer BKW-freien kWp ergibt einen zu hohen
spezifischen Ertrag — dieselbe Falschmeldung wie oben, nur mit anderer
Ursache. Wer den Nenner zieht, sagt hier ausdrücklich, welchen Zähler er hat.

**Der Referenzwert bleibt als Fallback.** Wer keine Erzeuger-Investitionen
gepflegt hat, bekommt weiterhin eine Zahl statt einer Division durch 0 — und
`Anlage.leistung_kwp` bleibt Pflichtfeld (Gernots Entscheid zu N-76 vom
19.08.: „beim Pflichtfeld bleiben"). Dieser Helper ersetzt das Feld nicht, er
ordnet nur, wer davon rechnet: die **Community-Payload** bleibt bewusst auf dem
gepflegten Wert, weil der Anlagen-Hash des Benchmark-Servers aus ihm gebildet
wird (SHA256 aus kwp + Datum + PLZ2 + Secret) — eine abgeleitete Zahl würde
jeder betroffenen Anlage ihre Benchmark-Historie nehmen.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional, Sequence

from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
from backend.core.investition_kennwerte import get_erzeuger_kwp

# Spiegel zu `spez_ertrag.PV_ERZEUGER_TYPEN` — dort für dieselbe Menge, hier
# zusätzlich in der BKW-freien Variante.
PV_MODUL_TYP: str = "pv-module"
BKW_TYP: str = "balkonkraftwerk"


def summe_erzeuger_kwp(
    investitionen: Sequence[Any],
    stichtag: date,
    *,
    mit_bkw: bool,
) -> float:
    """Σ kWp der an ``stichtag`` aktiven PV-Erzeuger — **ohne** Fallback.

    ``mit_bkw=False`` liefert nur die PV-Module (Zähler `summe_pv_anlage_kwh`),
    ``mit_bkw=True`` zusätzlich die Balkonkraftwerke (Zähler
    `summe_pv_bkw_kwh`).

    `erzeuger_traeger` läuft **nach** dem Aktiv-Filter (N-266): ein BKW, dessen
    Modul-Kinder ihre kWp tragen, hat seine eigene abgetreten und würde sonst
    doppelt zählen.

    Gibt 0.0 zurück, wenn nichts aktiv ist — das ist eine Aussage
    („keine Erzeuger an diesem Tag"), keine Lücke. Wer eine Division davor
    schützen will, nimmt {@link anlagen_kwp}.
    """
    typen = (PV_MODUL_TYP, BKW_TYP) if mit_bkw else (PV_MODUL_TYP,)
    aktive = [
        inv for inv in (investitionen or ())
        if getattr(inv, "typ", None) in typen and inv.ist_aktiv_an(stichtag)
    ]
    return sum(get_erzeuger_kwp(inv) for inv in erzeuger_traeger(aktive))


def anlagen_kwp(
    investitionen: Sequence[Any],
    stichtag: date,
    *,
    mit_bkw: bool,
    referenzwert: Optional[float] = None,
) -> float:
    """Der Kennzahlen-Nenner: Σ der Erzeuger, sonst der gepflegte Referenzwert.

    ``referenzwert`` ist `Anlage.leistung_kwp`. Er greift **nur** bei Σ = 0 —
    also für Bestände ohne gepflegte Erzeuger-Investitionen. Bei gemischter
    Pflege (ein Modul gepflegt, eins nicht) gewinnt die Summe, weil sie die
    einzige Zahl ist, die Stilllegung und Anschaffungsdatum kennt.

    Das Ergebnis kann 0.0 sein (nichts gepflegt) — der Aufrufer prüft das,
    genau wie bisher beim Referenzwert (`if kwp <= 0`).
    """
    summe = summe_erzeuger_kwp(investitionen, stichtag, mit_bkw=mit_bkw)
    if summe > 0:
        return summe
    return referenzwert or 0.0
