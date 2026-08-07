"""Die AC-Kappung setzt aus, wo ein DC-gekoppelter Speicher den Überschuss aufnimmt (F-11).

**Der Befund.** Die AC-Grenze begrenzt, was ein Wechselrichter **ins Haus
abgibt** — nicht, was die Module ernten. Bei einem **DC**-gekoppelten Speicher
läuft der Überschuss über der Grenze gleichstromseitig in den Akku, ohne je
durch den Wechselrichter zu müssen. `kappe_profile` schnitt ihn trotzdem vom
Erzeugungsprofil ab: das SOLL war zu niedrig, die Performance Ratio zu hoch.
Betroffen war genau der BKW-Kanon-Fall (2,0 kWp DC an 800 W AC mit Akku) und
jeder Hybrid-Wechselrichter am Dach.

**Warum die Größe wirklich die Ernte VOR dem Speicher ist**, und nicht die
AC-Abgabe — das entscheidet nicht der Hersteller, sondern eedcs eigene Bilanz:

    direktverbrauch = max(0, pv − einspeisung − speicher_ladung)
    (`core/berechnungen/verbrauch.py`)

Die Speicherladung wird von der PV-Summe **abgezogen**; sie muss darin also
enthalten sein. Die Sensor-Referenz sagt dasselbe in Worten („erzeugte Energie
dieses PV-Strings/Moduls"), und der BKW-Akku-Kanon führt Ladung/Entladung als
eigene Speicher-Investition daneben.

⚠ **Damit liest erstmals eine ADR-001-Formel `get_speicher_kopplung`** — dessen
Docstring hielt bis dahin fest, der Helper „ändert keine Zahl". Der Vermerk dort
ist angepasst; die Wirkung bleibt auf SOLL-Werte beschränkt (Prognose-Kanon und
PVGIS-Monatsprognose), kein IST-Pfad und keine Finanzrechnung lesen ihn.

Die AC-Seite ist die tragende Abgrenzung: dort MUSS weiter gekappt werden, weil
die Energie tatsächlich durch den Wechselrichter läuft.
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen.wr_kappung import zuordne_grenzen


class _Inv:
    """Investition-Double mit genau den Attributen, die die Helper lesen."""

    _naechste_id = [1]

    def __init__(self, typ, **kw):
        self.typ = typ
        self.leistung_kwp = None
        self.parameter = {}
        self.parent_investition_id = None
        self.id = self._naechste_id[0]
        self._naechste_id[0] += 1
        self.__dict__.update(kw)


def _bkw(grenze_w=800):
    """Anker-Solarbank-Muster: 4 × 500 Wp an 800 W AC."""
    return _Inv("balkonkraftwerk", parameter={
        "leistung_wp": 500, "anzahl": 4, "wechselrichter_leistung_w": grenze_w,
    })


def _wr(grenze_kw=7.0):
    return _Inv("wechselrichter", parameter={"max_leistung_kw": grenze_kw})


def _speicher(parent, kopplung=None):
    param = {} if kopplung is None else {"kopplung": kopplung}
    return _Inv("speicher", parent_investition_id=parent.id, parameter=param)


# ── Balkonkraftwerk mit Akku — der Melder-Fall ─────────────────────────────

def test_bkw_mit_dc_akku_wird_nicht_gekappt():
    """Der Überschuss über 800 W läuft in die Solarbank, nicht ins Nichts."""
    bkw = _bkw()
    akku = _speicher(bkw, kopplung="dc")

    grenze, grenz_id = zuordne_grenzen([bkw], [], [akku])[bkw.id]

    assert grenze is None, "Die Kappung rechnet die Akku-Ladung weg"
    assert grenz_id is None


def test_bkw_mit_ac_akku_wird_weiter_gekappt():
    """**Die tragende Abgrenzung.** Bei AC-Kopplung muss alles durch den
    Wechselrichter — dort ist die Kappung physikalisch richtig und bleibt."""
    bkw = _bkw()
    akku = _speicher(bkw, kopplung="ac")

    grenze, grenz_id = zuordne_grenzen([bkw], [], [akku])[bkw.id]

    assert grenze == pytest.approx(0.8)
    assert grenz_id == f"inv:{bkw.id}"


def test_bkw_ohne_akku_wird_weiter_gekappt():
    """Ohne Speicher ist der Überschuss tatsächlich verloren — #347 unverändert."""
    bkw = _bkw()

    grenze, _ = zuordne_grenzen([bkw], [], [])[bkw.id]

    assert grenze == pytest.approx(0.8)


def test_bkw_akku_ohne_gepflegte_kopplung_gilt_als_dc():
    """Ungepflegt fällt auf die Ableitung zurück: Parent gesetzt ⇒ DC. Für den
    BKW-Akku-Kanon (Speicher MIT Balkonkraftwerk als Parent) trifft das zu."""
    bkw = _bkw()
    akku = _speicher(bkw)  # keine Kopplung gepflegt

    grenze, _ = zuordne_grenzen([bkw], [], [akku])[bkw.id]

    assert grenze is None


# ── Dach: Hybrid-Wechselrichter ────────────────────────────────────────────

def test_strings_am_hybrid_wr_mit_dc_speicher_werden_nicht_gekappt():
    """22 × 440 Wp an 7 kW AC mit DC-Speicher: der Überschuss lädt den Akku."""
    wr = _wr(7.0)
    ost = _Inv("pv-module", leistung_kwp=5.0, parent_investition_id=wr.id)
    west = _Inv("pv-module", leistung_kwp=5.0, parent_investition_id=wr.id)
    akku = _speicher(wr, kopplung="dc")

    z = zuordne_grenzen([ost, west], [wr], [akku])

    assert z[ost.id] == (None, None)
    assert z[west.id] == (None, None)


def test_strings_am_wr_mit_ac_speicher_werden_weiter_gekappt():
    """AC-Speicher am Hybrid-Wechselrichter — der Fall, für den #351 das
    Kopplungsfeld überhaupt eingeführt hat. Die Ableitung („Parent ⇒ DC") läge
    hier falsch; die **gepflegte** Angabe gewinnt."""
    wr = _wr(7.0)
    ost = _Inv("pv-module", leistung_kwp=5.0, parent_investition_id=wr.id)
    akku = _speicher(wr, kopplung="ac")

    grenze, grenz_id = zuordne_grenzen([ost], [wr], [akku])[ost.id]

    assert grenze == pytest.approx(7.0)
    assert grenz_id == f"wr:{wr.id}"


def test_eigenstaendiger_speicher_hebt_keine_grenze_auf():
    """Ein Speicher ohne Zuordnung hängt an keinem Wechselrichter — er kann den
    Überschuss eines bestimmten Erzeugers nicht aufnehmen."""
    wr = _wr(7.0)
    ost = _Inv("pv-module", leistung_kwp=5.0, parent_investition_id=wr.id)
    frei_stehend = _Inv("speicher", parameter={"kopplung": "dc"})

    grenze, _ = zuordne_grenzen([ost], [wr], [frei_stehend])[ost.id]

    assert grenze == pytest.approx(7.0)


def test_speicher_am_fremden_wr_hebt_die_grenze_nicht_auf():
    """Zwei Wechselrichter, ein DC-Speicher: nur dessen eigene Strings gehen
    ungekappt. Sonst hätte ein einziger Akku die Kappung anlagenweit
    ausgeschaltet."""
    wr_mit = _wr(7.0)
    wr_ohne = _wr(5.0)
    string_mit = _Inv("pv-module", leistung_kwp=8.0, parent_investition_id=wr_mit.id)
    string_ohne = _Inv("pv-module", leistung_kwp=6.0, parent_investition_id=wr_ohne.id)
    akku = _speicher(wr_mit, kopplung="dc")

    z = zuordne_grenzen([string_mit, string_ohne], [wr_mit, wr_ohne], [akku])

    assert z[string_mit.id] == (None, None)
    assert z[string_ohne.id][0] == pytest.approx(5.0), (
        "Der Akku am anderen Wechselrichter hat die Grenze mit aufgehoben"
    )
