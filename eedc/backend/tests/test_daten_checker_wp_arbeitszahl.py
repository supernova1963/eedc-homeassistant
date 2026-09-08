"""Der WP-Arbeitszahl-Checker rechnet mit denselben Eingängen wie die Anzeige (#411).

`WaermepumpeChecks` hatte bis zum 08.09.2026 **keine** Probe — gebaut in Paket b
(07.09.), gemessen nie. Aufgefallen ist das an OB73-gifs Zeile: Der Checker rief
`arbeitszahl(Q, E)` ohne `strom_funktionsfremd_kwh`, während Kachel und Cockpit
den Kühl-, Lüft- und Entfeuchtungsstrom aus dem Nenner ziehen (W-14/E4). Er
rechnete **3,5** und schwieg, während die Anzeige **107,0** zeigte.

Schwesterdateien: `test_waerme_vorschlag_b1.py` (der Symmetriepartner — dort
entsteht die Zahl, hier wird sie gemeldet), `test_daten_checker_zeitzone.py`,
`test_daten_checker_connector_monatswert.py`.

Der eigene Docstring der geprüften Methode nennt genau diese Falle: *„Ein
Checker, der seinen eigenen Quotienten bildet, meldet irgendwann etwas anderes,
als die Kachel zeigt."* Er nahm den richtigen Layer — nur mit anderen Zahlen.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.berechnungen.betriebsart_gemessen import modus_strom_zeile
from backend.core.berechnungen.waermepumpe_kennzahl import arbeitszahl
from backend.services.daten_checker.waermepumpe import WaermepumpeChecks


def _anlage(verbrauch_daten: dict):
    """Anlage mit genau einer Wärmepumpe und einer Monatszeile.

    Bewusst ohne DB: der Prüfer liest nur Attribute, und eine Fixture, die eine
    Session braucht, würde die Aussage dieser Proben nicht schärfer machen.
    """
    imd = SimpleNamespace(jahr=2026, monat=8, verbrauch_daten=verbrauch_daten)
    inv = SimpleNamespace(
        id=1, typ="waermepumpe", bezeichnung="Split-Klima", monatsdaten=[imd],
    )
    return SimpleNamespace(investitionen=[inv])


#: OB73-gifs Zeile (#411): 214 kWh Strom, davon 207 kWh Kühlbetrieb aus dem
#: Betriebsmodus-Sensor, dazu 749 kWh Heizwärme aus dem alten Vorschlag.
KUEHLMONAT = {
    "stromverbrauch_kwh": 214.0,
    "modus_strom_kuehlen_kwh": 207.0,
    "heizenergie_kwh": 749.0,
}


def test_checker_und_anzeige_rechnen_dieselbe_zahl():
    """Die eigentliche Aussage: gleiche Eingänge, gleiches Ergebnis.

    Ohne den Kühlabzug wäre es 3,5 — plausibel, und der Checker bliebe stumm.
    """
    zeile = modus_strom_zeile(KUEHLMONAT)
    anzeige = arbeitszahl(749.0, 214.0, strom_funktionsfremd_kwh=zeile.funktionsfremd_kwh)
    assert anzeige.wert == 107.0
    assert arbeitszahl(749.0, 214.0).wert == 3.5  # was der Checker vorher sah


def test_meldet_die_unmoegliche_arbeitszahl_des_kuehlmonats():
    ergebnisse = WaermepumpeChecks()._check_wp_arbeitszahl_unplausibel(_anlage(KUEHLMONAT))
    assert len(ergebnisse) == 1
    assert "Split-Klima" in ergebnisse[0].meldung
    assert "08/2026" in ergebnisse[0].meldung
    # Die Zahl in der Meldung ist die der Anzeige, nicht eine eigene.
    assert "107" in ergebnisse[0].meldung


def test_schweigt_bei_einer_plausiblen_anlage():
    """Gegenprobe — der Prüfer muss auch still sein können.

    Ohne sie belegt die Probe darüber nur, dass irgendetwas gemeldet wird.
    """
    gesund = {"stromverbrauch_kwh": 1000.0, "heizenergie_kwh": 3500.0}
    assert WaermepumpeChecks()._check_wp_arbeitszahl_unplausibel(_anlage(gesund)) == []


def test_kuehlstrom_allein_macht_noch_keine_meldung():
    """Derselbe Kühlanteil, aber eine Wärme, die dazu passt ⇒ still.

    Trennt den Befund („Nenner falsch gefüllt") von der bloßen Anwesenheit eines
    Kühlstroms — sonst meldete der Prüfer jede kühlende Anlage.
    """
    passend = {
        "stromverbrauch_kwh": 214.0,
        "modus_strom_kuehlen_kwh": 207.0,
        "heizenergie_kwh": 24.5,  # 7 kWh Heizstrom × 3,5
    }
    assert WaermepumpeChecks()._check_wp_arbeitszahl_unplausibel(_anlage(passend)) == []
