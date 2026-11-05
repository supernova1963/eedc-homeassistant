"""RF-73 … RF-74 (Komplexitäts-Paket 3, Session P3-D2): benannte Proben für die Phasen von
``core/berechnungen/tagesbilanz.py::bilanz_aus_stundenrows`` und
``services/energie_profil/lts_tagesverlauf.py::lade_tagesverlauf_aus_lts``.

Sie halten die Zweige fest, die die direkten Testdateien nicht oder nur mittelbar betreten (Bogen-Spur am HEAD
34f3b102): Batterie-Vorzeichen und Speicher-Effizienz-Schwelle 0,1 kWh, die N-92-Abdeckungsregel für Eigenverbrauch und
Autarkie, R7-Total-Fall und ``verworfen``-Sperren, EV-Quote bei PV-Summe 0, Einmal-Iterator, V2H nur mit Regelmarke;
im LTS-Weg die drei Gründe, den Vortagsrand (Read ab dem Vortag, Stunde 23), PV Gesamt als Fallback, Kombi neben
dedizierten Netz-Sensoren, Invertierung, ``nur_tage`` und die Tagesauswahl aktiver Investitionen. Alle Proben sind am
HEAD vor dem Schnitt grün. Der Verdacht «LTS-Kurve ohne BKW-Kürzung» (``_stunden_werte``) ist hier bewusst NICHT
festgehalten — er steht als Fall im Fixture-GM ``lts-tagesverlauf``, eine Probe würde einen späteren Fix blockieren.

Schwesterdateien: test_tagesbilanz_pv_nicht_erfasst.py, test_v2h_tageswert.py, test_n635_eine_eigenverbrauchs_formel.py,
test_stundenbilanz_sot.py (Tagesbilanz); test_zaehlerluecken_s2_8b_wallbox_je_tag.py, test_reparatur_lts_reichweite.py,
test_serien_aufbau_symmetrie_m1.py, test_n687_kombi_zaehler_vorrang.py (LTS-Kurve).
"""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.core.berechnungen.tagesbilanz import bilanz_aus_stundenrows
from backend.models.investition import Investition
from backend.services.energie_profil.lts_tagesverlauf import lade_tagesverlauf_aus_lts


def _z(pv=None, v=None, e=None, n=None, b=None, **kw):
    return SimpleNamespace(pv_kw=pv, verbrauch_kw=v, einspeisung_kw=e, netzbezug_kw=n, batterie_kw=b, **kw)


# ── RF-73: Tagesbilanz ────────────────────────────────────────────────────────────────────────────────────────────

def test_t1_direktverbrauch_ueberschuss_defizit_nur_mit_pv_und_verbrauch():
    b = bilanz_aus_stundenrows([_z(3.0, 1.0), _z(1.0, 2.5), _z(pv=4.0), _z(v=9.0)])
    assert b.direktverbrauch_kwh == 2.0          # Σ min(PV, V) = 1,0 + 1,0
    assert b.ueberschuss_kwh == 2.0              # Σ max(0, PV − V)
    assert b.defizit_kwh == 1.5                  # Σ max(0, V − PV)
    assert b.erzeugung_kwh == 8.0 and b.gesamtverbrauch_kwh == 12.5


def test_t2_batterie_vorzeichen_und_effizienz():
    b = bilanz_aus_stundenrows([_z(b=-2.0), _z(b=1.5), _z(b=0.0), _z(b=None)])
    assert (b.speicher_ladung_kwh, b.speicher_entladung_kwh) == (2.0, 1.5)
    assert b.speicher_effizienz_prozent == 75.0


@pytest.mark.parametrize("ladung, erwartet", [(0.1, None), (0.05, None), (0.11, 50.0)])
def test_t3_speicher_effizienz_erst_ab_ladung_ueber_0_1_kwh(ladung, erwartet):
    b = bilanz_aus_stundenrows([_z(b=-ladung), _z(b=ladung / 2)])
    if erwartet is None:
        assert b.speicher_effizienz_prozent is None
    else:
        assert b.speicher_effizienz_prozent == pytest.approx(erwartet)


def test_t4_n92_eigenverbrauch_nur_bei_gleicher_abdeckung():
    teil = [_z(pv=2.0, e=1.0 if h >= 6 else None, v=1.0, n=0.0) for h in range(24)]
    assert bilanz_aus_stundenrows(teil).eigenverbrauch_kwh is None          # nicht 48 − 18 = 30
    voll = [_z(pv=2.0, e=1.0, v=1.0, n=0.0) for h in range(24)]
    assert bilanz_aus_stundenrows(voll).eigenverbrauch_kwh == 24.0


def test_t5_n92_autarkie_nur_bei_gleicher_abdeckung_und_netzbezug():
    disjunkt = [_z(pv=1.0, e=0.2, v=1.0 if h < 12 else None, n=None if h < 12 else 0.5) for h in range(24)]
    assert bilanz_aus_stundenrows(disjunkt).autarkie_prozent is None
    ohne_netz = [_z(v=1.0) for _ in range(24)]
    assert bilanz_aus_stundenrows(ohne_netz).autarkie_prozent is None    # keine 100 % aus der fehlenden Spalte
    gleich = [_z(v=2.0, n=0.5) for _ in range(4)]
    assert bilanz_aus_stundenrows(gleich).autarkie_prozent == 75.0


def test_t6_r7_total_fall_ohne_einspeisung():
    b = bilanz_aus_stundenrows([_z(pv=1.0, v=1.0, n=0.5) for _ in range(3)], verworfen={})
    assert b.regelmarke is True
    assert b.gesamtverbrauch_kwh == 0.0 and b.verbrauch_erfasst is False
    assert b.eigenverbrauch_kwh is None and b.autarkie_prozent is None


def test_t7_r7_verworfen_sperren():
    zeilen = [_z(pv=2.0, v=1.5, e=0.6, n=0.1, b=-0.2) for _ in range(4)]
    batt = bilanz_aus_stundenrows(zeilen, verworfen={"batterie": 1.0})
    assert batt.eigenverbrauch_kwh is not None and batt.autarkie_prozent is None
    einsp = bilanz_aus_stundenrows(zeilen, verworfen={"einspeisung": 1.0})
    assert einsp.eigenverbrauch_kwh is None and einsp.ev_quote_prozent is None
    fremd = bilanz_aus_stundenrows(zeilen, verworfen={"wp": 1.0})
    assert fremd.eigenverbrauch_kwh is not None and fremd.autarkie_prozent is not None


def test_t8_ev_quote_bei_pv_summe_null_ist_keine_zahl():
    b = bilanz_aus_stundenrows([_z(pv=0.0, v=0.5, e=0.0, n=0.5) for _ in range(3)])
    assert b.pv_erfasst is True and b.eigenverbrauch_kwh == 0.0
    assert b.ev_quote_prozent is None


def test_t9_regelmarke_leeres_dict_ist_r7():
    zeilen = [_z(pv=2.0, v=1.0, e=1.0, n=0.0)]
    assert bilanz_aus_stundenrows(zeilen, verworfen={}).regelmarke is True
    assert bilanz_aus_stundenrows(zeilen).regelmarke is False


def test_t10_einmal_iterator_gleich_liste():
    zeilen = [_z(pv=h * 0.3, v=1.0, e=0.1, n=0.2, b=(h % 3) - 1.0, waermepumpe_kw=0.4) for h in range(24)]
    assert bilanz_aus_stundenrows(iter(zeilen), verworfen={}) == bilanz_aus_stundenrows(zeilen, verworfen={})
    assert bilanz_aus_stundenrows(z for z in zeilen) == bilanz_aus_stundenrows(zeilen)


def test_t11_v2h_nur_mit_regelmarke():
    zeilen = [_z(pv=2.0, v=1.5, e=0.6, n=0.3) for _ in range(4)]
    alt = bilanz_aus_stundenrows(zeilen, v2h_entladung_kwh=2.0)
    assert alt.v2h_entladung_kwh == 0.0
    ohne = bilanz_aus_stundenrows(zeilen, verworfen={})
    mit = bilanz_aus_stundenrows(zeilen, verworfen={}, v2h_entladung_kwh=2.0)
    assert mit.v2h_entladung_kwh == 2.0
    assert mit.gesamtverbrauch_kwh == pytest.approx(ohne.gesamtverbrauch_kwh + 2.0)


def test_t12_wp_fehlt_ist_nicht_erfasst_null_ist_erfasst():
    assert bilanz_aus_stundenrows([_z(pv=1.0)]).wp_erfasst is False
    b = bilanz_aus_stundenrows([_z(pv=1.0, waermepumpe_kw=0.0)])
    assert b.wp_erfasst is True and b.wp_strom_kwh == 0.0
    assert bilanz_aus_stundenrows([_z(), _z(), _z()]).stunden == 3


# ── RF-74: LTS-Kurve ──────────────────────────────────────────────────────────────────────────────────────────────

D = date(2026, 5, 14)


class _Res:
    def __init__(self, objs):
        self._objs = objs

    def scalars(self):
        return self

    def all(self):
        return list(self._objs)


class _Db:
    def __init__(self, invs=()):
        self.invs = list(invs)

    async def execute(self, stmt):
        return _Res(self.invs)


class _Ha:
    def __init__(self, daten, verfuegbar=True):
        self.daten, self.is_available, self.aufrufe = daten, verfuegbar, []

    def get_hourly_sensor_data(self, ids, von, bis):
        self.aufrufe.append((sorted(ids), von, bis))
        return {eid: {d: dict(h) for d, h in self.daten[eid].items()} for eid in ids if eid in self.daten}


def _anlage(live=None, inv=None, invert=None):
    m = {"basis": {"live": live or {}}}
    if invert:
        m["basis"]["live_invert"] = invert
    if inv:
        m["investitionen"] = inv
    return SimpleNamespace(id=1, sensor_mapping=m)


async def _lauf(anlage, ha, invs=(), von=D, bis=D, nur_tage=None):
    with patch("backend.services.ha_statistics_service.get_ha_statistics_service", return_value=ha):
        return await lade_tagesverlauf_aus_lts(_Db(invs), anlage, von, bis, nur_tage)


def _tag(werte, d=D):
    return {d.isoformat(): dict(werte)}


@pytest.mark.asyncio
async def test_l1_gruende_ohne_zuordnung_ohne_entity_ohne_ha_ohne_daten():
    ha = _Ha({})
    assert (await _lauf(SimpleNamespace(id=1, sensor_mapping=None), ha)).grund == "keine_live_zuordnung"
    assert (await _lauf(_anlage(live={"aussentemperatur_c": "sensor.t"}), ha)).grund == "keine_live_zuordnung"
    assert ha.aufrufe == []
    aus = _Ha({"sensor.pv": _tag({12: 1.0})}, verfuegbar=False)
    assert (await _lauf(_anlage(live={"pv_gesamt_w": "sensor.pv"}), aus)).grund == "ha_nicht_verfuegbar"
    leer = await _lauf(_anlage(live={"pv_gesamt_w": "sensor.pv"}), _Ha({}))
    assert leer.grund == "keine_daten" and leer.tage == {}


@pytest.mark.asyncio
async def test_l2_read_ab_vortag_und_vortagsrand_stunde_23():
    vortag = D - timedelta(days=1)
    ha = _Ha({"sensor.netz": {vortag.isoformat(): {22: 9.0, 23: 0.5}, D.isoformat(): {5: 1.25}}})
    erg = await _lauf(_anlage(live={"netz_kombi_w": "sensor.netz"}), ha)
    assert ha.aufrufe == [(["sensor.netz"], vortag, D)]
    t = erg.tage[D]
    assert t["punkte"] == [{"zeit": "05:00", "werte": {"netz": 1.25}}]
    assert t["vortagsrand"] == [{"zeit": "23:00", "werte": {"netz": 0.5}}]


@pytest.mark.asyncio
async def test_l3_tag_nur_mit_vortagsrand_fehlt():
    vortag = D - timedelta(days=1)
    ha = _Ha({"sensor.netz": {vortag.isoformat(): {23: 0.5}}})
    erg = await _lauf(_anlage(live={"netz_kombi_w": "sensor.netz"}), ha)
    assert erg.grund == "ok" and erg.tage == {}


@pytest.mark.asyncio
async def test_l4_pv_gesamt_nur_ohne_eigene_pv_serie():
    ha = _Ha({"sensor.pvg": _tag({12: 5.0}), "sensor.m": _tag({12: 2.0})})
    allein = await _lauf(_anlage(live={"pv_gesamt_w": "sensor.pvg"}), ha)
    assert [s["key"] for s in allein.tage[D]["serien"]] == ["pv_gesamt"]
    inv = Investition(id=3, typ="pv-module", aktiv=True)
    mit = await _lauf(_anlage(live={"pv_gesamt_w": "sensor.pvg"}, inv={"3": {"live": {"leistung_w": "sensor.m"}}}), ha, [inv])
    assert [s["key"] for s in mit.tage[D]["serien"]] == ["pv_3"]
    assert mit.tage[D]["punkte"][0]["werte"] == {"pv_3": 2.0}


@pytest.mark.asyncio
async def test_l5_kombi_entfaellt_neben_bezug_und_vorzeichen():
    ha = _Ha({"sensor.netz": _tag({12: -3.0}), "sensor.bezug": _tag({12: 0.75})})
    erg = await _lauf(_anlage(live={"netz_kombi_w": "sensor.netz", "netzbezug_w": "sensor.bezug"}), ha)
    assert ha.aufrufe[0][0] == ["sensor.bezug"]
    assert erg.tage[D]["punkte"][0]["werte"] == {"netz": 0.75}
    kombi = await _lauf(_anlage(live={"netz_kombi_w": "sensor.netz"}), _Ha({"sensor.netz": _tag({12: -3.0})}))
    assert kombi.tage[D]["punkte"][0]["werte"] == {"netz": -3.0}      # Kombi negativ ⇒ Einspeisung


@pytest.mark.asyncio
async def test_l6_invertierung_basis_und_investition():
    erg = await _lauf(_anlage(live={"netz_kombi_w": "sensor.netz"}, invert={"netz_kombi_w": True}),
                      _Ha({"sensor.netz": _tag({12: -3.0})}))
    assert erg.tage[D]["punkte"][0]["werte"] == {"netz": 3.0}
    inv = Investition(id=4, typ="speicher", aktiv=True)
    m = {"4": {"live": {"leistung_w": "sensor.bat"}, "live_invert": {"leistung_w": True}}}
    erg = await _lauf(_anlage(inv=m), _Ha({"sensor.bat": _tag({12: 1.5})}), [inv])
    assert erg.tage[D]["punkte"][0]["werte"] == {"batterie_4": 1.5}   # invertiert −1,5, bidirektional ⇒ −(−1,5)


@pytest.mark.asyncio
async def test_l7_nur_tage_und_aktive_investition_je_tag():
    von, bis = date(2026, 9, 20), date(2026, 9, 23)
    inv = Investition(id=4, typ="speicher", aktiv=True, stilllegungsdatum=date(2026, 9, 21))
    daten = {"sensor.bat": {(von + timedelta(days=i)).isoformat(): {12: -1.0} for i in range(-1, 4)},
             "sensor.netz": {(von + timedelta(days=i)).isoformat(): {12: 0.5} for i in range(-1, 4)}}
    ha = _Ha(daten)
    erg = await _lauf(_anlage(live={"netz_kombi_w": "sensor.netz"}, inv={"4": {"live": {"leistung_w": "sensor.bat"}}}), ha,
                      [inv], von, bis, nur_tage={date(2026, 9, 21), date(2026, 9, 22)})
    assert ha.aufrufe[0][1:] == (von - timedelta(days=1), bis)              # der Read umfasst die ganze Range
    assert sorted(erg.tage) == [date(2026, 9, 21), date(2026, 9, 22)]
    assert [s["key"] for s in erg.tage[date(2026, 9, 21)]["serien"]] == ["batterie_4", "netz"]
    assert [s["key"] for s in erg.tage[date(2026, 9, 22)]["serien"]] == ["netz"]   # nach der Stilllegung


@pytest.mark.asyncio
async def test_l8_dedizierter_bezug_und_einspeisung_netto_und_klemme():
    ha = _Ha({"sensor.bezug": _tag({3: 0.8, 4: -0.2, 12: 0.1}), "sensor.einsp": _tag({12: 2.5, 13: -1.0})})
    erg = await _lauf(_anlage(live={"netzbezug_w": "sensor.bezug", "einspeisung_w": "sensor.einsp"}), ha)
    assert sorted(ha.aufrufe[0][0]) == ["sensor.bezug", "sensor.einsp"]
    punkte = {p["zeit"]: p["werte"] for p in erg.tage[D]["punkte"]}
    assert punkte == {"03:00": {"netz": 0.8}, "12:00": {"netz": -2.4}}   # negative Werte je Seite auf 0 geklemmt


@pytest.mark.asyncio
async def test_l9_invert_flag_ohne_zuordnung_und_sensor_ohne_daten_bleiben_folgenlos():
    m = {"basis": {"live": {"pv_gesamt_w": "sensor.pvg", "netz_kombi_w": "sensor.netz"},
                   "live_invert": {"netzbezug_w": True, "netz_kombi_w": True}},
         "investitionen": {"3": {"live_invert": {"leistung_w": True}}, "4": {"live": {"leistung_w": "sensor.bat"},
                                                                          "live_invert": {"soc": True}}}}
    inv = Investition(id=4, typ="speicher", aktiv=True)
    erg = await _lauf(SimpleNamespace(id=1, sensor_mapping=m), _Ha({"sensor.pvg": _tag({12: 4.0}), "sensor.bat": _tag({12: 1.0})}), [inv])
    assert erg.tage[D]["punkte"][0]["werte"] == {"batterie_4": -1.0, "pv_gesamt": 4.0}
