"""Balkonkraftwerk im Prognose-Kanon: kWp zählt mit, AC-Grenze kappt stündlich.

Zwei Befunde, ein Paket (Gernot 2026-07-29) — sie zeigen in entgegengesetzte
Richtungen und trafen dieselben Anlagen:

**Befund A (zu niedrig).** ``orientierungs_gruppen`` las die kWp über
``get_pv_kwp``. Das BKW-Formular schreibt aber nur ``leistung_wp``/``anzahl``
ins ``parameter``-JSON — Spalte und ``parameter["kwp"]`` bleiben leer. Ein
Balkonkraftwerk lieferte dort also 0 und fiel **ganz aus der Gruppierung**:
im gesamten Kanon-Pfad (Tagesprognose, Stundenprofil, Live-Wetter, Prefetch,
MQTT-/HA-Prognosesensoren). Die 14-Tage-Aussichten zählten es mit
(``aussichten.py`` ist mit A24-2 auf ``get_erzeuger_kwp`` umgestellt worden) —
dieselbe Anlage hatte damit zwei Wahrheiten.

**#347 (zu hoch).** Ein BKW ist regelmäßig überbelegt (3 × 420 Wp an einem
600-W-Wechselrichter, Rainer). Ohne AC-Grenze prognostiziert eedc die volle
Modulleistung. Die Kappung ist **stündlich**: die Mittagsspitze wird
abgeschnitten, die Randstunden bleiben unberührt.
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen.wr_kappung import (
    Mitglied,
    hat_kappung,
    kappe_profile,
    kappe_stunde,
    kappungs_faktoren,
    zuordne_grenzen,
)
from backend.core.investition_kennwerte import (
    get_erzeuger_kwp,
    get_pv_kwp,
    get_wr_grenze_kw,
)
from backend.services.pv_orientation import orientierungs_gruppen


class _Inv:
    """Investition-Double mit genau den Attributen, die die Helper lesen."""

    _naechste_id = [1]

    def __init__(self, typ="balkonkraftwerk", **kw):
        self.typ = typ
        self.leistung_kwp = None
        self.neigung_grad = None
        self.ausrichtung = None
        self.parameter = {}
        self.parent_investition_id = None
        self.id = self._naechste_id[0]
        self._naechste_id[0] += 1
        self.__dict__.update(kw)


def _bkw(**params):
    """BKW so, wie das Formular es anlegt: nur leistung_wp + anzahl."""
    basis = {"leistung_wp": 420, "anzahl": 3, "ausrichtung": "Süd", "neigung_grad": 30}
    basis.update(params)
    return _Inv(parameter=basis)


# ------------------------------------------------------------------ Befund A

def test_bkw_faellt_nicht_mehr_aus_der_orientierungsgruppierung():
    """Rainers Anlage: 8 kWp PV + 1,26 kWp BKW, gleiche Orientierung."""
    pv = _Inv(typ="pv-module", leistung_kwp=8.0, ausrichtung="Süd", neigung_grad=30)
    gruppen = orientierungs_gruppen([pv, _bkw()])

    assert len(gruppen) == 1
    assert gruppen[0].kwp == pytest.approx(9.26), "BKW-Anteil fehlt in der Gruppe"


def test_reine_bkw_anlage_bildet_eine_gruppe():
    """Vorher: leere Gruppenliste ⇒ Fallback auf die Anlagen-Gesamtleistung."""
    gruppen = orientierungs_gruppen([_bkw()])

    assert len(gruppen) == 1
    assert gruppen[0].kwp == pytest.approx(1.26)
    assert (gruppen[0].neigung, gruppen[0].ausrichtung) == (30, 0)


def test_die_gruppierung_nutzt_denselben_kwp_wert_wie_die_aussichten():
    """Symmetrie: der Kanon darf für dieselbe Komponente nichts anderes lesen
    als der 14-Tage-Pfad (`aussichten.py` rechnet mit `get_erzeuger_kwp`)."""
    bkw = _bkw()
    assert get_pv_kwp(bkw) == 0.0, "Vorbedingung des Befunds — sonst greift der Test daneben"
    assert orientierungs_gruppen([bkw])[0].kwp == pytest.approx(get_erzeuger_kwp(bkw))


# ------------------------------------------------------------------- #347

def test_wr_grenze_wird_nur_gepflegt_gelesen():
    assert get_wr_grenze_kw(_bkw()) is None, "ohne Pflege darf nicht gekappt werden"
    assert get_wr_grenze_kw(_bkw(wechselrichter_leistung_w=600)) == pytest.approx(0.6)
    assert get_wr_grenze_kw(_bkw(wechselrichter_leistung_w=0)) is None
    assert get_wr_grenze_kw(_bkw(wechselrichter_leistung_w="unfug")) is None
    # Ein PV-String trägt selbst KEINE Grenze — sie gehört seinem
    # Wechselrichter und gilt für alle Strings daran gemeinsam (#354).
    assert get_wr_grenze_kw(_Inv(typ="pv-module", leistung_kwp=8.0)) is None


def test_kappung_trifft_die_mittagsspitze_und_laesst_die_randstunden():
    """Der Kern von #347: kein kWp-Deckel, sondern eine stündliche Grenze."""
    mitglieder = [[Mitglied(1.26, 0.6)]]
    # Morgens 0,2 kW, mittags 1,1 kW (beides auf 1,26 kWp gerechnet)
    assert kappe_stunde([0.2], [1.26], mitglieder) == pytest.approx([0.2])
    assert kappe_stunde([1.1], [1.26], mitglieder) == pytest.approx([0.6])


def test_kappung_rechnet_je_komponente_nicht_ueber_die_gruppensumme():
    """Gemischte Gruppe: ungekapptes PV-Dach neben gekapptem BKW.

    `min(a + b, grenze)` wäre falsch — die Grenze gehört zum Wechselrichter,
    nicht zur Himmelsrichtung.
    """
    mitglieder = [[Mitglied(8.0, None), Mitglied(1.26, 0.6)]]
    gruppen_kwp = 9.26
    # Mittagsstunde: 0,8 kW je kWp ⇒ PV 6,4 kW (frei), BKW 1,008 → 0,6
    gekappt = kappe_stunde([0.8 * gruppen_kwp], [gruppen_kwp], mitglieder)
    assert gekappt == pytest.approx([6.4 + 0.6])


def test_ohne_grenze_bleibt_das_profil_unveraendert():
    profil = [0.0, 0.3, 1.1, 0.4]
    ohne = [[Mitglied(1.26, None)]]
    assert not hat_kappung(ohne)
    assert kappe_profile([profil], [1.26], ohne)[0] == pytest.approx(profil)
    assert kappungs_faktoren([profil], [1.26], ohne)[0] == pytest.approx(1.0)


def test_kappungs_faktor_traegt_die_kappung_auf_den_tageswert():
    """Der Tageswert wird über das Verhältnis gekappt, nicht neu gebildet —
    die Prognose-Tagessumme ist nicht zwangsläufig die Σ der Stundenwerte."""
    profil = [0.0, 0.2, 1.1, 0.2]  # Σ 1,5
    faktor = kappungs_faktoren([profil], [1.26], [[Mitglied(1.26, 0.6)]])[0]
    assert faktor == pytest.approx((0.0 + 0.2 + 0.6 + 0.2) / 1.5)
    assert faktor < 1.0


def test_kappung_vertraegt_leere_und_entartete_eingaben():
    eins = [[Mitglied(1.26, 0.6)]]
    assert kappe_stunde([0.0], [1.26], eins) == pytest.approx([0.0])
    assert kappe_stunde([1.0], [0.0], eins) == pytest.approx([1.0])
    assert kappe_stunde([1.0], [1.26], [[]]) == pytest.approx([1.0])
    assert kappungs_faktoren([[0.0, 0.0]], [1.26], eins)[0] == pytest.approx(1.0)


# --------------------------------------------------------- #354: geteilte Grenze

def _wr(max_leistung_kw=7.0, **kw):
    return _Inv(typ="wechselrichter", parameter={"max_leistung_kw": max_leistung_kw}, **kw)


def test_wechselrichter_traegt_jetzt_seine_ac_grenze():
    """#354: das Feld „Max. Leistung (kW)" gab es immer — gelesen hat es niemand."""
    assert get_wr_grenze_kw(_wr(7.0)) == pytest.approx(7.0)
    assert get_wr_grenze_kw(_Inv(typ="wechselrichter", parameter={})) is None
    # Legacy-Schlüssel aus dem toten `parameter_schema` — der Daten-Checker
    # liest ihn, also darf die Prognose bei ihm nicht blind sein.
    assert get_wr_grenze_kw(
        _Inv(typ="wechselrichter", parameter={"leistung_ac_kw": 5.0})
    ) == pytest.approx(5.0)
    # Spalte als Fallback: `leistung_kwp` trägt beim Wechselrichter kW (AC).
    assert get_wr_grenze_kw(
        _Inv(typ="wechselrichter", parameter={}, leistung_kwp=10.0)
    ) == pytest.approx(10.0)


def test_strings_erben_die_grenze_ihres_wechselrichters():
    wr = _wr(7.0)
    ost = _Inv(typ="pv-module", leistung_kwp=5.0, parent_investition_id=wr.id)
    west = _Inv(typ="pv-module", leistung_kwp=5.0, parent_investition_id=wr.id)
    frei = _Inv(typ="pv-module", leistung_kwp=3.0)

    z = zuordne_grenzen([ost, west, frei], [wr])

    assert z[ost.id] == z[west.id], "dieselbe Grenze, dieselbe Kennung"
    assert z[ost.id][0] == pytest.approx(7.0)
    assert z[frei.id] == (None, None), "ohne Wechselrichter keine Grenze"


def test_bkw_behaelt_die_eigene_grenze_auch_mit_parent():
    """Das eigene Gerät ist das nähere — ein BKW teilt seine Grenze mit niemandem."""
    wr = _wr(7.0)
    bkw = _bkw(wechselrichter_leistung_w=600)
    bkw.parent_investition_id = wr.id

    grenze, grenz_id = zuordne_grenzen([bkw], [wr])[bkw.id]

    assert grenze == pytest.approx(0.6)
    assert grenz_id == f"inv:{bkw.id}"


def test_ein_wechselrichter_kappt_seine_strings_gemeinsam():
    """Der Kern von #354: 7 kW gelten für die SUMME beider Strings.

    Ost und West liegen in **verschiedenen** Orientierungsgruppen — eine
    Kappung je Gruppe ließe denselben Wechselrichter zweimal 7 kW liefern.
    """
    mitglieder = [
        [Mitglied(5.0, 7.0, "wr:1")],   # Ost
        [Mitglied(5.0, 7.0, "wr:1")],   # West
    ]
    # Mittagsstunde: je Gruppe 5 kW ⇒ zusammen 10 kW an einem 7-kW-Gerät
    gekappt = kappe_stunde([5.0, 5.0], [5.0, 5.0], mitglieder)

    assert sum(gekappt) == pytest.approx(7.0), "die Summe trägt die Grenze"
    # Anteilig gekürzt: der Wechselrichter entscheidet nicht, wer zuerst verliert
    assert gekappt[0] == pytest.approx(3.5)
    assert gekappt[1] == pytest.approx(3.5)


def test_zwei_wechselrichter_kappen_unabhaengig():
    """Gegenprobe: verschiedene `grenz_id` ⇒ getrennte Pools."""
    mitglieder = [
        [Mitglied(5.0, 7.0, "wr:1")],
        [Mitglied(5.0, 7.0, "wr:2")],
    ]
    gekappt = kappe_stunde([8.0, 8.0], [5.0, 5.0], mitglieder)

    assert gekappt == pytest.approx([7.0, 7.0])


def test_geteilte_grenze_greift_erst_ueber_der_summe():
    """Unterhalb der Grenze bleibt alles unangetastet — auch bei zwei Strings."""
    mitglieder = [
        [Mitglied(5.0, 7.0, "wr:1")],
        [Mitglied(5.0, 7.0, "wr:1")],
    ]
    gekappt = kappe_stunde([2.0, 1.5], [5.0, 5.0], mitglieder)

    assert gekappt == pytest.approx([2.0, 1.5])
