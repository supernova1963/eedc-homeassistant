"""Die Arbeitszahl reicht die Zahlen heraus, mit denen sie gebildet wurde.

Schwesterdateien: `test_soll_waerme_klima_w4_arbeitszahl_je_funktion.py` und
`test_soll_waerme_klima_w5_arbeitszahl_kuehlen.py` — dort steht, *wann* es eine
Arbeitszahl gibt und wann ihr Grund. Gegenstand hier ist allein die
**Herleitung**: welche zwei Zahlen die Kachel daneben zeigen darf.

## Warum das nicht im Client gerechnet werden darf

Der Nenner ist **nicht** der ausgewiesene Stromverbrauch. `arbeitszahl` zieht
den funktionsfremden Anteil ab — Kühlen, Lüften, Entfeuchten (W-14) —, weil Q
und E dieselbe Abgrenzung tragen müssen. Wer die Herleitung aus den beiden
Anzeigefeldern `wp_waerme_kwh` und `wp_strom_kwh` nachbaut, zeigt bei jeder
Anlage mit erfasstem Betriebsmodus eine Rechnung, die **nicht auf die Zahl
daneben führt**.

Das ist die W-3-Klasse, und diese Fläche kennt sie: Bis 2026-08-26 stand die
JAZ-Sperre an drei Orten, einer davon im Client — dieselbe Anlage zeigte im Hub
„—" und im Cockpit eine Zahl. Die Herleitung geht deshalb denselben Weg wie
`grund` und `hinweis`: aus dem Layer heraus, nicht im Client nachgebaut.

## Der Anlass

Ein Melder (dietmar1968, simon42 T89667 #283) sah über Monate Arbeitszahlen von
0,7 · 0,9 · 1,1. Eine Wärmepumpe kann nicht weniger Wärme abgeben, als sie Strom
aufnimmt — die Zahlen waren also ein sicheres Zeichen für einen falsch
zugeordneten Zähler. Die Kachel nannte als Formel nur „JAZ = Wärme ÷ Strom".

⛔ **Bewusst keine Warnschranke** (Entscheid 01.09.2026). Eine Regel „unter 1 ⇒
Warnung" würde ausgerechnet Anlagen mit Heizen und Kühlen auf einem Zähler
falsch anschreien, und eedc bewertet den Anwender nicht — es zeigt seine
Rechnung. Dieselbe Haltung wie bei `HEIZSTAB_HINWEIS`.
"""

from __future__ import annotations

from backend.core.berechnungen.waermepumpe_kennzahl import (
    arbeitszahl,
    arbeitszahl_je_funktion,
    arbeitszahl_kuehlen,
)


def test_die_herleitung_geht_auf():
    """Zähler ÷ Nenner ergibt genau den ausgewiesenen Wert.

    Die Grundforderung an eine angezeigte Rechnung: Wer sie nachrechnet, muss
    auf die Zahl daneben kommen.
    """
    a = arbeitszahl(209.7, 313.6)
    assert a.wert is not None
    assert a.zaehler_kwh == 209.7
    assert a.nenner_kwh == 313.6
    assert abs(a.zaehler_kwh / a.nenner_kwh - a.wert) < 1e-9


def test_der_nenner_ist_der_bereinigte_strom_nicht_der_gesamte():
    """**Der eigentliche Gegenstand dieser Datei.**

    100 kWh Wärme, 300 kWh Strom, davon 200 im Kühlbetrieb ⇒ die Arbeitszahl
    ist 1,0 (100 ÷ 100). Eine Herleitung aus den Anzeigefeldern zeigte
    „100 ÷ 300 = 0,33" — eine andere Zahl als die Kachel.
    """
    a = arbeitszahl(100.0, 300.0, strom_funktionsfremd_kwh=200.0)
    assert a.wert == 1.0
    assert a.nenner_kwh == 100.0, "Der Nenner muss der bereinigte Strom sein"
    assert a.nenner_kwh != 300.0, "Der Gesamtstrom wäre die falsche Herleitung"
    assert abs(a.zaehler_kwh / a.nenner_kwh - a.wert) < 1e-9


def test_ohne_zahl_keine_herleitung():
    """Eine gesperrte Arbeitszahl führt keine Rechnung mit sich.

    Zweite Regelhälfte, eigene Probe: Die Prüfungen oben wären auch dann grün,
    wenn im Sperrfall Zahlen mitliefen — die Kachel baute daraus eine Rechnung
    ohne Ergebnis. Präzedenz für diese Haltung ist `MonatBilanz.tsx:156`:
    „0 kWh × — ct/kWh wäre keine Rechnung, sondern Rauschen."
    """
    for gesperrt in (
        arbeitszahl(None, 300.0),                                   # keine Wärme
        arbeitszahl(100.0, None),                                   # kein Strom
        arbeitszahl(100.0, 300.0, strom_funktionsfremd_kwh=300.0),  # nur Kühlen
        arbeitszahl(100.0, 300.0, waerme_abgeleitet_kwh=50.0),      # Wärme gerechnet
        arbeitszahl(100.0, 300.0, abgrenzung_verletzt="Heizstab am Zähler"),
    ):
        assert gesperrt.wert is None
        assert gesperrt.grund
        assert gesperrt.zaehler_kwh is None, gesperrt.grund
        assert gesperrt.nenner_kwh is None, gesperrt.grund


def test_je_funktion_traegt_die_herleitung_ebenfalls():
    """Heizen und Warmwasser erben sie über `arbeitszahl` — ohne zweite Rechenstelle."""
    je = arbeitszahl_je_funktion(
        heizung_kwh=800.0, strom_heizen_kwh=200.0,
        warmwasser_kwh=300.0, strom_warmwasser_kwh=100.0,
        hat_split=True,
    )
    assert (je.heizen.zaehler_kwh, je.heizen.nenner_kwh) == (800.0, 200.0)
    assert (je.warmwasser.zaehler_kwh, je.warmwasser.nenner_kwh) == (300.0, 100.0)
    assert je.heizen.wert == 4.0 and je.warmwasser.wert == 3.0


def test_kuehlen_traegt_sie_auch():
    """Die Kühl-Arbeitszahl rechnet bewusst selbst — und muss deshalb selbst liefern.

    Sie delegiert **nicht** an `arbeitszahl` (kein funktionsfremder Abzug, der
    Kühlstrom *ist* hier der Nenner). Genau daran ist die erste Fassung dieses
    Bauschritts vorbeigelaufen: Zähler und Nenner blieben leer, obwohl ein Wert
    dastand. Gemessen am 01.09.2026, nicht vermutet.
    """
    k = arbeitszahl_kuehlen(500.0, 150.0)
    assert k.wert is not None
    assert (k.zaehler_kwh, k.nenner_kwh) == (500.0, 150.0)
    assert abs(k.zaehler_kwh / k.nenner_kwh - k.wert) < 1e-9
