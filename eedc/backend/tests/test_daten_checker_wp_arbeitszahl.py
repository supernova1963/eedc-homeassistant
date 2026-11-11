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

import pytest

from backend.core.berechnungen.betriebsart_gemessen import modus_strom_zeile
from backend.core.field_definitions import (
    get_wp_strom_kwh,
    get_wp_warmwasser_kwh,
)
from backend.core.berechnungen.waermepumpe_kennzahl import arbeitszahl
from backend.services.daten_checker.waermepumpe import WaermepumpeChecks


def _anlage(verbrauch_daten: dict, parameter: dict | None = None):
    """Anlage mit genau einer Wärmepumpe und einer Monatszeile.

    Bewusst ohne DB: der Prüfer liest nur Attribute, und eine Fixture, die eine
    Session braucht, würde die Aussage dieser Proben nicht schärfer machen.

    ⚠ **`parameter` gehört dazu, seit N-450 die Lesetüren mit `params` ruft.**
    Bis zum 12.09.2026 trug dieses Double das Feld nicht — eine echte
    `Investition` hat es **immer** (Spalte mit Default), das Double war
    unvollständig und nicht der Prüfer zu großzügig.
    """
    imd = SimpleNamespace(jahr=2026, monat=8, verbrauch_daten=verbrauch_daten)
    inv = SimpleNamespace(
        id=1, typ="waermepumpe", bezeichnung="Split-Klima", monatsdaten=[imd],
        parameter=parameter if parameter is not None else {},
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


# ── N-450: die getrennt messenden Anlagen waren für den Prüfer unsichtbar ──


#: Eine F5-Anlage mit einer Arbeitszahl, die es nicht gibt: 3600 kWh Wärme auf
#: 400 kWh gemessenem Strom ⇒ **9,0**. Der Strom steht ausschließlich in den
#: zwei feinen Feldern — genau die Lage, in der `get_wp_strom_kwh` **ohne**
#: `params` den nicht-getrennten Zweig nimmt, `stromverbrauch_kwh` nicht findet
#: und **0** liefert.
F5_UNPLAUSIBEL = {
    "strom_heizen_kwh": 300.0,
    "strom_warmwasser_kwh": 100.0,
    "heizenergie_kwh": 3000.0,
    "warmwasser_kwh": 600.0,
}
F5_PARAMS = {"getrennte_strommessung": True}


def test_n450_die_getrennt_messende_anlage_wird_ueberhaupt_gesehen():
    """**N-450 — `get_wp_strom_kwh(daten)` ohne `params` liefert an F5 eine 0.**

    Folge bis zum 12.09.2026: `if not strom: continue` — die
    Plausibilitätsprüfung sah **jede** Anlage mit getrennter Strommessung nie.
    Ausgerechnet die sorgfältigst eingerichteten; und ausgerechnet dort
    beschreibt das Handbuch die Umgebungswärme-Falle, die diese Meldung fängt.
    """
    ergebnisse = WaermepumpeChecks()._check_wp_arbeitszahl_unplausibel(
        _anlage(F5_UNPLAUSIBEL, F5_PARAMS),
    )

    assert len(ergebnisse) == 1, (
        "Der Prüfer hat die Anlage nicht gesehen — `params` fehlt an der Lesetür."
    )
    assert "9,0" in ergebnisse[0].meldung
    assert "08/2026" in ergebnisse[0].meldung


def test_n450_die_lesetuer_ist_der_unterschied_nicht_die_zahl():
    """Die **Einzelwerte** hinter dem Befund — kein nachgebildeter Ausdruck.

    Beide Aufrufe stehen nebeneinander: mit `params` findet die Lesetür die
    zwei feinen Zähler, ohne sie sucht sie `stromverbrauch_kwh` und findet
    nichts. Genau diese 0 hat den Prüfer stumm gemacht.
    """
    assert get_wp_strom_kwh(F5_UNPLAUSIBEL, F5_PARAMS) == pytest.approx(400.0)
    assert get_wp_strom_kwh(F5_UNPLAUSIBEL) == pytest.approx(0.0)


def test_n450_eine_plausible_f5_anlage_bleibt_still():
    """Gegenprobe — sichtbar heißt nicht gemeldet.

    Dieselbe Ausstattung, dieselbe Lesetür, eine Arbeitszahl von 4,0: still.
    Ohne sie belegte die Probe darüber nur, dass F5-Anlagen jetzt *irgendetwas*
    auslösen.
    """
    gesund = {**F5_UNPLAUSIBEL, "heizenergie_kwh": 1000.0, "warmwasser_kwh": 600.0}
    assert get_wp_strom_kwh(gesund, F5_PARAMS) == pytest.approx(400.0)
    assert WaermepumpeChecks()._check_wp_arbeitszahl_unplausibel(
        _anlage(gesund, F5_PARAMS),
    ) == []


def test_n450_der_warmwasser_filter_gilt_auch_hier():
    """Die zweite Lesetür — `get_wp_warmwasser_kwh` ohne `params` filtert nicht.

    Ein an einer **Luft-Luft**-Anlage gepflegter Warmwasser-Wert ist nach N-379
    keine Wärme dieses Geräts. Ohne `params` zählte der Prüfer ihn mit und
    meldete eine Arbeitszahl, die es an diesem Gerät gar nicht gibt.
    """
    daten = {"stromverbrauch_kwh": 100.0, "warmwasser_kwh": 900.0}
    luft_luft = {"wp_art": "luft_luft"}

    assert get_wp_warmwasser_kwh(daten) == pytest.approx(900.0)
    assert get_wp_warmwasser_kwh(daten, luft_luft) == pytest.approx(0.0)
    assert WaermepumpeChecks()._check_wp_arbeitszahl_unplausibel(
        _anlage(daten, luft_luft),
    ) == []


# ── SOLL-§9-E7/Option A: der Prüfer zieht den ABZUG ab, nicht die Menge ────


def test_e7_der_pruefer_kuerzt_keinen_gemessenen_f5_nenner():
    """**Dieselbe Anlage, zwei Erfassungswege — der Prüfer darf nicht driften.**

    F5 (400 kWh gemessen) **plus** ein abgeleiteter Kühlanteil von 200 kWh. Die
    Anzeige rechnet seit Option A `3600 ÷ 400 = 9,0` und nicht `3600 ÷ 200 =
    18,0`; zöge der Prüfer weiter die Rohmenge ab, meldete er eine Zahl, die
    auf keiner Fläche steht — genau der #411-Befund, nur in der Gegenrichtung.
    """
    mit_modus = {
        **F5_UNPLAUSIBEL,
        "modus_strom_kuehlen_kwh": 200.0,
        "modus_abdeckung_h": 700.0,
    }
    ergebnisse = WaermepumpeChecks()._check_wp_arbeitszahl_unplausibel(
        _anlage(mit_modus, F5_PARAMS),
    )

    assert len(ergebnisse) == 1
    assert "9,0" in ergebnisse[0].meldung, (
        "Der Prüfer hat den abgeleiteten Kühlanteil vom gemessenen F5-Nenner "
        "abgezogen — Option A verbietet genau das."
    )


# ── E6.D D4: der gesetzte Fremdanteil entlastet die Meldung ─────────────────────
#
# Der Docstring des Prüfers verspricht seit Paket b: *„Gibt der Layer einen Grund statt eines Werts zurück (Abgrenzung
# verletzt …), ist der Fall bereits behandelt."* Bis E6.D übergab der Aufruf `abgrenzung_verletzt` nicht — die Warnung
# blieb stehen, obwohl der Anwender den vorgesehenen Weg «Abgrenzung» am Gerät gegangen war (Lesedurchgang 11.11.2026,
# Code-Verdacht 6). Die Anzeige (`waermepumpe_kennzahlen_je_geraet`) übergibt den Grund aus derselben Angabe.

#: Ein Gaskessel speist denselben Heizkreis (SOLL §3.2b A7): 1200 kWh Wärme gegen 100 kWh Strom ⇒ Arbeitszahl 12.
BIVALENT = {"stromverbrauch_kwh": 100.0, "heizenergie_kwh": 1200.0}


def test_d4_ohne_fremdanteil_meldet_die_zahl():
    (m,) = WaermepumpeChecks()._check_wp_arbeitszahl_unplausibel(_anlage(BIVALENT))
    assert m.code == "wp_arbeitszahl_zu_hoch" and "12" in m.meldung


@pytest.mark.parametrize("abgrenzung", ["fremdwaerme", "fremdstrom"])
def test_d4_mit_fremdanteil_entfaellt_die_meldung(abgrenzung):
    assert WaermepumpeChecks()._check_wp_arbeitszahl_unplausibel(_anlage(BIVALENT, {"abgrenzung": abgrenzung})) == []


def test_d4_unbekannter_wert_entlastet_nicht():
    """Ein Wert, den das Formular nicht setzen kann, ist keine Angabe (`abgrenzung_stoerung` ⇒ ``None``)."""
    assert len(WaermepumpeChecks()._check_wp_arbeitszahl_unplausibel(_anlage(BIVALENT, {"abgrenzung": "gas"}))) == 1
