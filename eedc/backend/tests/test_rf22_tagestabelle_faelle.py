"""RF-22 (Serie «Funktion vor Datei»): Fälle für Zweige von `baue_tagestabelle`, die keine andere Probe der Suite erreicht.

Gemessen am 13./14.10.2026 (Vorlage RF-22, Spur über 301 Testdateien, 472 Tests mit Aufruf): R3 auf die **Achsensumme**
(die Achse fällt samt ihrer Kategorien) und ein Slot außerhalb 0..23 kamen in keinem Test vor; Sprengsätze auf die
geteilten Zustände der Phasen (Stunden-Sammler, N-623-Sammler, Nachtrag, Sperre aus R3/R4) blieben in der Suite still.
Jeder Test hier ist eine Regel, kein Beispiel: die Zahlen sind so gewählt, dass genau die eine Weiche entscheidet.

Schwesterdateien: test_zaehlerluecken_r3_deckel_spanne.py (R3 je Sensor-Slot, Deckel wächst mit der Spanne),
test_zaehlerluecken_deckel_fenster.py (Fenster des Deckels, Nachträge II), test_n567_nachtrag_benannt.py (N-567 Nachtrag),
test_n623_tageswert_gemessen.py (N-623 Aggregat-Tag), test_n536_bkw_traegt_nur_den_rest.py (N-536 BKW-Rest und Kinder-Deckung),
test_v2h_tageswert.py (#110 V2H, ruft die Funktion direkt), test_rf20_tage_werte_faelle.py (dieselbe Fall-Probe für den Leser der Tageszeile).
"""
from datetime import date
from types import SimpleNamespace as NS

import pytest

from backend.services.provenance import ABGELEITET_KWP_ANTEIL
from backend.services.snapshot.tages_tabelle import TabellenEintrag as E, baue_tagestabelle

TAG = date(2026, 7, 1)


def _inv(i, typ, kwp, parent=None):
    return NS(id=i, typ=typ, leistung_kwp=kwp, parent_investition_id=parent, parameter={},
              ist_aktiv_an=lambda _d: True)


def _kurve(spitze, von=6, bis=20):
    mitte = (von + bis) / 2
    return {h: (round(max(0.0, spitze * (1 - abs(h - mitte) / (mitte - von + 1))), 3), 1) for h in range(von, bis + 1)}


def _summe(slots):
    return sum(d for d, _n in slots.values())


M1, M2 = _inv(1, "pv-module", 6.0), _inv(2, "pv-module", 4.0)
E_M1 = E("s.m1", "pv", None, "inv:1:pv_erzeugung_kwh", "pv_1", 1)
E_M2 = E("s.m2", "pv", None, "inv:2:pv_erzeugung_kwh", "pv_2", 1)
E_AGG = E("s.agg", "pv", None, "basis:pv_gesamt", "pv_gesamt", 1)
E_SE = E("s.se", "erzeugung_sonstiges", None, "inv:9:erzeugung_kwh", "sonstige_9", 1)
E_EINSP = E("s.einsp", "einspeisung", None, "basis:einspeisung", "einspeisung", 1)
E_NETZ = E("s.netz", "netzbezug", None, "basis:netzbezug", "netzbezug", 1)


def test_achsensumme_ueber_dem_deckel_faellt_mit_allen_kategorien():
    """R3 auf die Achsensumme: je Zähler unter dem Deckel (kWp 2 × 1,5 = 3), zusammen darüber ⇒ die PV-Achse der Stunde
    fällt ganz — Module UND Sonstiges-Erzeuger, in der Stunde und im Tageswert; die Menge steht in `verworfen`."""
    slots = {"s.m1": {11: (1.0, 1), 12: (1.8, 1)}, "s.m2": {11: (0.5, 1), 12: (0.9, 1)},
             "s.se": {11: (0.1, 1), 12: (0.4, 1)}}
    t = baue_tagestabelle(NS(id=1, leistung_kwp=2.0), {"1": M1, "2": M2}, TAG, [E_M1, E_M2, E_SE], slots)
    assert t.stunden[12]["pv"] is None and t.stunden[12]["erzeugung_sonstiges"] is None
    assert t.stunden[11]["pv"] == pytest.approx(1.6)
    assert t.verworfen == {"pv": pytest.approx(3.1)}
    assert t.komponenten_kwh == {"pv_1": pytest.approx(1.0), "pv_2": pytest.approx(0.5), "sonstige_9": pytest.approx(0.1)}


def test_slot_ausserhalb_des_tages_zaehlt_nicht():
    """Ein Slot h = 24 geht in keine Stunde und in keinen Tageswert."""
    t = baue_tagestabelle(NS(id=1, leistung_kwp=10.0), {}, TAG, [E_NETZ], {"s.netz": {10: (0.5, 1), 24: (9.0, 1)}})
    assert t.komponenten_kwh == {"netzbezug": pytest.approx(0.5)}
    assert set(t.stunden) == set(range(24))


def test_nachtrag_nach_nullstunden_wird_benannt_und_zaehlt():
    """N-567: vier Nullzeilen, dann 5 kWh bei kWp 2 — über Schwelle × n (3), unter Schwelle × Fenster: die Menge zählt
    (Stunde und Tag) und steht in `nachtrag`, nicht in `verworfen`."""
    slots = {"s.einsp": {**{h: (0.0, 1) for h in range(8, 12)}, 12: (5.0, 1)}}
    t = baue_tagestabelle(NS(id=1, leistung_kwp=2.0), {}, TAG, [E_EINSP], slots)
    assert t.stunden[12]["einspeisung"] == pytest.approx(5.0)
    assert t.nachtrag == {"einspeisung": pytest.approx(5.0)}
    assert t.verworfen == {}


def test_aggregat_tag_ruecksprung_sperrt_den_gemessenen_erzeuger():
    """N-623 + R4: Modul 1 deckt jede Aggregat-Stunde, hat aber nachts einen Rücksprung ⇒ am Tag ohne Aussage, beide
    Module bekommen den kWp-Anteil; die verworfene Menge steht auf 3 Stellen."""
    slots = {"s.agg": _kurve(4.0), "s.m1": {**_kurve(2.4), 2: (-0.013, 1)}}
    t = baue_tagestabelle(NS(id=1, leistung_kwp=10.0), {"1": M1, "2": M2}, TAG, [E_AGG, E_M1], slots)
    assert t.pv_marken == {"pv_1": ABGELEITET_KWP_ANTEIL, "pv_2": ABGELEITET_KWP_ANTEIL}
    assert t.verworfen == {"pv": 0.013}


def test_aggregat_tag_buendel_ueber_dem_daemmerungsrest_ist_keine_messung():
    """N-623: 0,5 kWh eigene Bündel-Energie (n = 2) bei 32 kWh Anlagen-Tag liegt über 1 % ⇒ nicht gemessen."""
    slots = {"s.agg": _kurve(4.0), "s.m1": {**_kurve(2.4), 6: (0.5, 2)}}
    t = baue_tagestabelle(NS(id=1, leistung_kwp=10.0), {"1": M1, "2": M2}, TAG, [E_AGG, E_M1], slots)
    assert t.pv_marken == {"pv_1": ABGELEITET_KWP_ANTEIL, "pv_2": ABGELEITET_KWP_ANTEIL}


def test_aggregat_tag_gemessener_erzeuger_behaelt_seinen_wert():
    """N-623, Gegenstück: ohne Rücksprung und ohne Bündel ist Modul 1 gemessen (keine Marke), Modul 2 trägt den Rest."""
    slots = {"s.agg": _kurve(4.0), "s.m1": _kurve(2.4)}
    t = baue_tagestabelle(NS(id=1, leistung_kwp=10.0), {"1": M1, "2": M2}, TAG, [E_AGG, E_M1], slots)
    assert t.pv_marken == {"pv_2": ABGELEITET_KWP_ANTEIL}
    assert t.komponenten_kwh["pv_1"] == pytest.approx(_summe(_kurve(2.4)))
    assert t.komponenten_kwh["pv_1"] + t.komponenten_kwh["pv_2"] == pytest.approx(_summe(_kurve(4.0)))


def test_bkw_zaehler_deckt_das_kind_ohne_zaehler():
    """N-536: BKW mit zwei Modul-Kindern, das BKW und ein Kind haben Zähler ⇒ das zweite Kind ist gedeckt, der Tag
    gehört den Einzelzählern (kein Aggregat-Tag, keine Marke), das BKW trägt nur den Rest."""
    bkw, k1, k2 = _inv(11, "balkonkraftwerk", 0.8), _inv(12, "pv-module", 0.4, 11), _inv(13, "pv-module", 0.4, 11)
    e = [E_AGG, E("s.bkw", "pv", None, "inv:11:pv_erzeugung_kwh", "bkw_11", 1),
         E("s.k1", "pv", None, "inv:12:pv_erzeugung_kwh", "pv_12", 1)]
    slots = {"s.agg": _kurve(0.7), "s.bkw": _kurve(0.6), "s.k1": _kurve(0.25)}
    t = baue_tagestabelle(NS(id=1, leistung_kwp=0.8), {"11": bkw, "12": k1, "13": k2}, TAG, e, slots)
    assert t.pv_marken == {}
    assert set(t.komponenten_kwh) == {"bkw_11", "pv_12"}
    assert t.komponenten_kwh["bkw_11"] == pytest.approx(_summe(_kurve(0.6)) - _summe(_kurve(0.25)))


def test_batterie_mit_anderer_spanne_laesst_den_stundenverbrauch_offen():
    """R6: PV, Netz und Einspeisung mit n = 1, die Batterie mit n = 2 ⇒ Verbrauch der Stunde `None`, Spanne benannt."""
    e = [E_M1, E_NETZ, E_EINSP, E("s.ent", "entladung_batterie", None, "inv:3:entladung_kwh", "batterie_3", 1)]
    slots = {"s.m1": {20: (0.5, 1)}, "s.netz": {20: (0.3, 1)}, "s.einsp": {20: (0.1, 1)}, "s.ent": {20: (0.7, 2)}}
    t = baue_tagestabelle(NS(id=1, leistung_kwp=10.0), {"1": M1}, TAG, e, slots)
    assert t.stunden[20]["verbrauch"] is None
    assert t.stunden[20]["spannen"] == {"batterie": 2}
    ohne = baue_tagestabelle(NS(id=1, leistung_kwp=10.0), {"1": M1}, TAG, e, {**slots, "s.ent": {20: (0.7, 1)}})
    assert ohne.stunden[20]["verbrauch"] == pytest.approx(0.5 + 0.3 - 0.1 + 0.7)


def test_aggregat_tag_tagesreset_sperrt_den_gemessenen_erzeuger():
    """N-623 + Tagesreset: ein Zähler in `ohne_tageswert` trägt am Tag keine Aussage — auch nicht als gemessener
    Erzeuger am Aggregat-Tag; beide Module bekommen den kWp-Anteil."""
    slots = {"s.agg": _kurve(4.0), "s.m1": _kurve(2.4)}
    t = baue_tagestabelle(NS(id=1, leistung_kwp=10.0), {"1": M1, "2": M2}, TAG, [E_AGG, E_M1], slots,
                          ohne_tageswert=frozenset({"s.m1"}))
    assert t.pv_marken == {"pv_1": ABGELEITET_KWP_ANTEIL, "pv_2": ABGELEITET_KWP_ANTEIL}


def test_aggregat_tag_halber_eigener_tag_ist_keine_messung():
    """N-623: Modul 1 hat nur Slots bis 12 Uhr; die Anlagen-Energie der Stunden ohne eigenen Slot liegt weit über 1 % ⇒
    nicht gemessen (die Stunden des Aggregats gehen in die Prüfung ein)."""
    slots = {"s.agg": _kurve(4.0), "s.m1": _kurve(2.4, 6, 12)}
    t = baue_tagestabelle(NS(id=1, leistung_kwp=10.0), {"1": M1, "2": M2}, TAG, [E_AGG, E_M1], slots)
    assert t.pv_marken == {"pv_1": ABGELEITET_KWP_ANTEIL, "pv_2": ABGELEITET_KWP_ANTEIL}


def test_tagesreset_ziel_ohne_tageswert_aber_stunden_zaehlen():
    """Tagesreset (Snapshot, R4): der Zähler zählt in der Stunde, sein Ziel-Schlüssel trägt keinen Tageswert."""
    t = baue_tagestabelle(NS(id=1, leistung_kwp=10.0), {}, TAG, [E_NETZ, E_EINSP],
                          {"s.netz": {10: (0.4, 1)}, "s.einsp": {10: (0.2, 1)}}, ohne_tageswert=frozenset({"s.netz"}))
    assert t.stunden[10]["netzbezug"] == pytest.approx(0.4)
    assert t.komponenten_kwh == {"einspeisung": pytest.approx(0.2)}


def test_either_or_nimmt_den_ersten_zaehler_der_gruppe_mit_daten():
    """Either-Or je Tag: Gruppe g1 — der erste Zähler hat keine Slots, der zweite trägt; Gruppe g2 — beide haben Slots,
    der erste trägt allein."""
    e = [E("s.g1a", "verbrauch_wp", "g1", "inv:4:a", "waermepumpe_4", 1),
         E("s.g1b", "verbrauch_wp", "g1", "inv:4:b", "waermepumpe_4", 1),
         E("s.g2a", "verbrauch_sonstiges", "g2", "inv:8:a", "sonstige_8", 1),
         E("s.g2b", "verbrauch_sonstiges", "g2", "inv:8:b", "sonstige_8", 1)]
    slots = {"s.g1b": {7: (0.2, 1)}, "s.g2a": {1: (0.1, 1)}, "s.g2b": {1: (9.0, 1)}}
    t = baue_tagestabelle(NS(id=1, leistung_kwp=10.0), {}, TAG, e, slots)
    assert t.komponenten_kwh == {"sonstige_8": pytest.approx(0.1), "waermepumpe_4": pytest.approx(0.2)}


def test_wallbox_spalte_der_stunde_traegt_wallbox_und_e_auto():
    """Stundenzeile: `wallbox` = Wallbox-Ladung + Heimladung des E-Autos (beide Zähler der Achse `wallbox`)."""
    e = [E("s.wb", "ladung_wallbox", None, "inv:5:ladung_kwh", "wallbox_5", 1),
         E("s.ea", "verbrauch_eauto", None, "inv:6:ladung_kwh", "eauto_6", 1)]
    t = baue_tagestabelle(NS(id=1, leistung_kwp=10.0), {}, TAG, e, {"s.wb": {18: (1.1, 1)}, "s.ea": {18: (0.7, 1)}})
    assert t.stunden[18]["wallbox"] == pytest.approx(1.8)


def test_schluesselfolge_und_r4_log():
    """Die Folge der Rollup-Schlüssel ist die Folge, in der die Stunden sie zuerst tragen (sie wird als JSON persistiert);
    ein Rücksprung schreibt eine Warnung mit Zähler und Stunde."""
    import logging
    e = [E_NETZ, E_M1, E_EINSP]
    slots = {"s.netz": {0: (0.3, 1), 3: (-1.0, 1)}, "s.m1": {9: (0.5, 1)}, "s.einsp": {9: (0.2, 1)}}
    fang = []

    class _H(logging.Handler):
        def emit(self, r):
            fang.append(r.getMessage())
    log = logging.getLogger("backend.services.snapshot.tages_tabelle")
    h, alt_level, alt_disabled, alt_global = _H(), log.level, log.disabled, logging.root.manager.disable
    log.addHandler(h)
    log.setLevel(logging.WARNING)
    log.disabled = False
    logging.disable(logging.NOTSET)
    try:
        t = baue_tagestabelle(NS(id=1, leistung_kwp=10.0), {"1": M1}, TAG, e, slots)
    finally:
        logging.disable(alt_global)
        log.removeHandler(h)
        log.setLevel(alt_level)
        log.disabled = alt_disabled
    assert list(t.komponenten_kwh) == ["netzbezug", "einspeisung", "pv_1"]
    assert any("h=3 s.netz" in m and "verworfen (R4)" in m for m in fang)
