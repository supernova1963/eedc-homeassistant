"""Wächter W-8 (Etappe E2 «Daten-Checker: ein Handgriff je Befund», Bauplan §4; E0-Bericht (2), Lesart C des Masters).

Die Texte der **HA-gebundenen** Befunde erscheinen auf den Standalone-Kopien des Text-Golden-Masters nie — sie hält je
Code eine eingefrorene Fixture `fixtures/daten_checker_texte/<code>.json` (Kategorie, Schwere, Meldung, Details, Code,
Soll-Klasse aus dem Katalog, Laufzeit-Klasse). 12 Kategorien, seit E5 25 Fälle, 24 Codes (33/34 sind zwei Wortlaute von
`tageswerte_ok`; Restzeilen und Nr 116/123 entfallen, V2/V3). Je Erzeuger ein Fall gegen Fake-HA —
die Szenarien nehmen die Helfer der Tests, die den Text bisher hielten. Fehlt eine Fixture ⇒ rot; weicht der Text ab ⇒ rot.

Fixtures neu schreiben (nur, wenn eine Etappe Texte bewusst ändert — E2 ändert keine):

    cd eedc && EEDC_FIXTURES_SCHREIBEN=1 backend/venv/bin/python -m pytest backend/tests/test_daten_checker_texte_fixtures.py

Kalender: die Prüfungen auf Tageszeilen (Tageswerte, Batterie-Vorzeichen) lesen `date.today()` in einem Funktions-Import;
ihre Szenarien stellen den Tag über `datetime.date` fest (`_FesterTag`, Muster `test_n593_wp_tagesfaktor.py`), sonst
trügen die Fixtures das Datum des Laufs. Die übrigen Szenarien haben feste Daten.
"""

from __future__ import annotations

import datetime as _dt_modul
import json
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "daten_checker_texte"
SCHREIBEN = os.environ.get("EEDC_FIXTURES_SCHREIBEN") == "1"
FEST = date(2026, 3, 31)


class _FesterTag(date):
    @classmethod
    def today(cls):
        return cls(FEST.year, FEST.month, FEST.day)


def _kalender(monkeypatch):
    monkeypatch.setattr(_dt_modul, "date", _FesterTag)


# ─── Szenarien je Familie (Helfer der bisherigen Text-Tests) ──────────────────────────────────────────────────────

async def _drift_ok(db, mp):
    from backend.tests.test_rf64_daten_checker_phasen import T0, _drift, _inv
    return await _drift({T0: {"pv_3": 30.0}}, lambda d, _i: {"pv_3": 30.0}, [_inv(3, "pv-module")])


async def _drift_kappung(db, mp):
    from backend.tests.test_rf64_daten_checker_phasen import T0, _drift, _inv
    eedc, ha = {}, {}
    for i in range(23):
        d = T0 + timedelta(days=i)
        eedc[d] = {"pv_3": 50.0, "wallbox_5": 10.0}
        ha[d] = {"pv_3": 50.0 + 3 + i, "wallbox_5": 10.0 + (5.0 if i == 4 else 0.0)}
    return await _drift(eedc, lambda d, _i: ha[d], [_inv(3, "pv-module"), _inv(5, "wallbox", "Box")])


async def _ha_sprung(db, mp):
    from backend.models.anlage import Anlage
    from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
    from backend.services.daten_checker.datenquelle.ha_sprung import HaZaehlersprungChecks
    from backend.tests.test_n586_checker_ha_zaehlersprung import JETZT, _reihe

    a = Anlage(anlagenname="N-586", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    k = Kanal(anlage_id=a.id, key="basis:pv_gesamt", einheit="kWh", art=ART_SUM)
    db.add(k)
    await db.flush()
    z = _reihe(48, reset_bei=20, rueckkehr_bei=23)
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=z[0][0] - 3600, familie=FAMILIE_SPIEGEL,
                       statistic_id="sensor.pv_gesamt", offset=0.0))
    db.add_all([KanalStatistik(kanal_id=k.id, start_ts=ts, state=st, sum=su, familie=FAMILIE_SPIEGEL) for ts, st, su in z])
    await db.commit()

    class _P(HaZaehlersprungChecks):
        def __init__(self, db_):
            self.db = db_
    return await _P(db)._check_ha_zaehlersprung(a, jetzt=JETZT)


async def _ha_rueckgang(db, mp):
    from backend.tests.test_n639_checker_ha_rueckgang import RUECKGANG_STUNDE, _anlage, _kanal, _Pruefer, _reihe
    a = await _anlage(db)
    await _kanal(db, a, "basis:netzbezug", "sensor.netzbezug", _reihe(rueckgaenge={RUECKGANG_STUNDE: 540.0}))
    return await _Pruefer(db)._check_ha_rueckgang(a)


async def _zeitzone(db, mp):
    from backend.services import ha_connection
    from backend.tests.test_daten_checker_zeitzone import _befunde, _eigener_offset, _ha_antwortet, _ha_verbindung
    _ha_verbindung(mp, kind=ha_connection.HA_CONNECTOR)
    _ha_antwortet(mp, {"time_zone": "Asia/Tokyo"})   # ohne Sommerzeit: die Fixture hängt nicht am Datum
    _eigener_offset(mp, timedelta(hours=7))
    return await _befunde(mp)


async def _lts_befunde(db, mp):
    from backend.tests.test_rf64_daten_checker_phasen import _Ha, _lts, _lts_anlage
    ha = _Ha(fehlend={"s.e_out", "s.starts", "s.gas"}, ohne_sum={"s.e_in", "s.stunden"})
    return await _lts(_lts_anlage(), ha, mp)


async def _lts_ok(db, mp):
    from backend.tests.test_rf64_daten_checker_phasen import _Ha, _lts, _lts_anlage
    return await _lts(_lts_anlage(), _Ha(), mp)


async def _lts_ohne_ha(db, mp):
    from types import SimpleNamespace

    from backend.tests.test_rf64_daten_checker_phasen import _anlage, _lts, _s
    return await _lts(_anlage([], {"basis": {"einspeisung": _s("s.e")}}), SimpleNamespace(is_available=False), mp)


async def _einheit_energie_im_leistungsslot(db, mp):
    from backend.tests.test_daten_checker_sensor_mapping_einheit import _patch_units, _run_check, _seed_anlage
    anlage = await _seed_anlage(db, sensor_mapping={"basis": {"live": {"einspeisung_w": "sensor.einsp_zaehler"}}})
    _patch_units(mp, {"sensor.einsp_zaehler": "kWh"})
    return await _run_check(db, anlage)


async def _einheit_leistung_im_energieslot(db, mp):
    from backend.tests.test_daten_checker_sensor_mapping_einheit import _patch_units, _run_check, _seed_anlage, _sensor
    anlage = await _seed_anlage(db, sensor_mapping={"basis": {"einspeisung": _sensor("sensor.einsp_leistung")}})
    _patch_units(mp, {"sensor.einsp_leistung": "W"})
    return await _run_check(db, anlage)


async def _klima_modus_wert(db, mp):
    from backend.tests.test_p433_0_betriebsmodus_werte import _MODUS, _anlage_mit_modus, _FakeHa, _meldungen
    anlage, _inv = await _anlage_mit_modus(db)
    return await _meldungen(db, anlage, mp, _FakeHa({_MODUS: ("heating", None)}))


async def _emob_zustand(db, mp):
    from backend.tests.test_p433_2b_k1_emob import _anlage, _meldungen, _stelle_ha
    anlage, _wb, _ = await _anlage(db, wb_live={"ladezustand": "sensor.wb_status"})
    _stelle_ha(mp, {"sensor.wb_status": ("charging_paused", None)})
    return await _meldungen(db, anlage)


async def _emob_kennung(db, mp):
    from backend.tests.test_p433_2b_k2a_fahrzeug import FELD, _anlage, _checker, _stelle_ha
    anlage, _wb, _ea = await _anlage(db, wb_live={FELD: "select.evcc_carport_vehicle_name"}, kennung="Smart")
    _stelle_ha(mp, {"select.evcc_carport_vehicle_name": ("fremd", None)})
    return await (await _checker(db))._check_emob_kennung_unbekannt(anlage)


async def _sensor_ohne_lts(db, mp):
    from backend.tests.test_p433_3_s1_live_temperaturen import MATHEK, _anlage_mathek, _FakeHa, _meldungen
    anlage, _inv = await _anlage_mathek(db)
    fake = _FakeHa({MATHEK["vorlauf_temperatur_c"]: "measurement", MATHEK["ruecklauf_temperatur_c"]: "",
                    MATHEK["heizstab_leistung_w"]: "total"})
    return await _meldungen(db, anlage, mp, fake)


def _tage(n: int, ab: int = 1) -> list[date]:
    return [FEST - timedelta(days=i) for i in range(ab, ab + n)]


async def _tageswerte(tz_tage, ha_func, mp):
    from backend.tests.test_daten_checker_leere_tage_trotz_zaehler import _make_anlage, _make_inv, _make_tz, _run_check
    _kalender(mp)
    voll = {"einspeisung": 20.0, "netzbezug": 2.0, "pv_7": 30.0}
    tz = [_make_tz(d, dict(tz_tage.get(d, voll))) for d in _tage(90) if tz_tage.get(d, voll) is not None]
    erg, _ = await _run_check(_make_anlage(), tz, [_make_inv()], ha_func)
    return erg


async def _tageswerte_alle_da(db, mp):
    return await _tageswerte({}, lambda d: {}, mp)


async def _tageswerte_ha_hat_nichts(db, mp):
    return await _tageswerte({FEST - timedelta(days=1): {"pv_7": 29.0, "einspeisung": 0.0, "netzbezug": 0.0}},
                             lambda d: {}, mp)


async def _tageswerte_luecken(db, mp):
    leer = {d: {"pv_7": 29.0, "einspeisung": 0.0, "netzbezug": 0.0} for d in _tage(17)}
    return await _tageswerte(leer, lambda d: {"einspeisung": 22.0, "netzbezug": 3.4, "pv_7": 29.0}, mp)


async def _batterie(tage: int, gespeichert: float, frisch: float, mp):
    from backend.tests.test_batterie_vorzeichen_historie_check import _make_inv, _make_tz, _run_check
    _kalender(mp)
    return await _run_check([_make_tz(d, gespeichert) for d in _tage(tage)], [_make_inv()],
                            lambda d: {"batterie_5": frisch})


async def _batterie_ok(db, mp):
    return await _batterie(1, 3.0, 8.0, mp)


async def _batterie_konflikt(db, mp):
    return await _batterie(40, -4.0, 4.0, mp)


#: (Nr Teil B, Code, Szenario) — die Erzeuger der 12 HA-gebundenen Kategorien (E0 (2)). E5: die Restzeilen Nr 23, 30, 37
#: (V2) und die übersprungene LTS-Prüfung Nr 116 (V3 ⇒ Kopfzeile «nicht ausführbar», V4) sind entfallen, Nr 123 ist in
#: Nr 122 aufgegangen (eine OK-Zeile mit beiden Zahlen). 33/34 bleiben zwei Wortlaute EINER Stelle.
FAELLE = [
    (22, "drift_ok", _drift_ok), (24, "drift_tag", _drift_kappung),
    (25, "drift_komponente", _drift_kappung), (3, "ha_zaehlersprung", _ha_sprung), (2, "ha_zaehler_rueckgang", _ha_rueckgang),
    (39, "zeitzone_abweichung", _zeitzone),
    (117, "kwh_sensoren_nicht_in_lts", _lts_befunde), (118, "counter_ohne_state_class", _lts_befunde),
    (119, "kwh_ohne_summen_spalte", _lts_befunde), (120, "counter_ohne_summen_spalte", _lts_befunde),
    (121, "stand_sensoren_nicht_in_lts", _lts_befunde), (122, "stand_sensoren_ok", _lts_ok),
    (124, "leistungs_slot_energie_sensor", _einheit_energie_im_leistungsslot),
    (125, "energie_slot_leistungssensor", _einheit_leistung_im_energieslot), (4, "klima_modus_wert_unbekannt", _klima_modus_wert),
    (50, "emob_zustand_wert_unbekannt", _emob_zustand), (111, "sensor_ohne_langzeitstatistik", _sensor_ohne_lts),
    (33, "tageswerte_ok", _tageswerte_alle_da), (34, "tageswerte_ok", _tageswerte_ha_hat_nichts),
    (35, "tageswerte_fehlen_tage", _tageswerte_luecken), (36, "tageswerte_fehlen_tag", _tageswerte_luecken),
    (27, "batterie_vorzeichen_ok", _batterie_ok),
    (28, "batterie_vorzeichen_tage", _batterie_konflikt), (29, "batterie_vorzeichen_tag", _batterie_konflikt),
    (51, "emob_kennung_unbekannt", _emob_kennung),
]
#: Je Code mit mehreren Erzeugern: welcher Treffer des Szenarios zu welcher Nr gehört (Reihenfolge der Ausgabe).
_INDEX: dict = {}


def _eintrag(e) -> dict:
    from backend.services.daten_checker.handgriffe import handgriff
    soll = handgriff(e.code)
    return {"kategorie": getattr(e.kategorie, "value", e.kategorie), "schwere": getattr(e.schwere, "value", e.schwere),
            "meldung": e.meldung, "details": e.details, "code": e.code,
            "klasse_katalog": soll.klasse if soll else None, "klasse_laufzeit": e.klasse}


def test_fuenfundzwanzig_faelle_vierundzwanzig_codes():
    """E5: 30 − 3 Restzeilen − Nr 116 − Nr 123 = 25 Fälle, 28 − 4 = 24 Codes (12 Kategorien unverändert)."""
    assert len(FAELLE) == 25 and len({nr for nr, _c, _s in FAELLE}) == 25
    assert len({c for _n, c, _s in FAELLE}) == 24


async def test_lts_ohne_ha_ohne_eigene_zeile(db, monkeypatch):
    """E5 V3/V4 (Teil B Nr 116 ⇒ 21): ohne Home Assistant steht in der Kategorie keine Zeile «übersprungen» mehr — die
    Prüfung zählt der Kopf als nicht ausführbar (`test_daten_checker_verdichtung.py`)."""
    assert await _lts_ohne_ha(db, monkeypatch) == []


def test_jede_fixture_existiert_und_keine_waise():
    if SCHREIBEN:
        pytest.skip("Schreib-Lauf")
    soll = {f"{c}.json" for _n, c, _s in FAELLE}
    ist = {p.name for p in FIXTURES.glob("*.json")}
    assert soll - ist == set(), f"Fixture fehlt: {sorted(soll - ist)}"
    assert ist - soll == set(), f"Fixture ohne Fall: {sorted(ist - soll)}"


@pytest.mark.parametrize("nr,code,szenario", FAELLE, ids=[f"{n}-{c}" for n, c, _s in FAELLE])
async def test_text_gleich_fixture(nr, code, szenario, db, monkeypatch):
    erg = [e for e in await szenario(db, monkeypatch) if e.code == code]
    assert erg, f"Szenario liefert keinen Befund {code}"
    ist = _eintrag(erg[_INDEX.get(nr, 0)])
    pfad = FIXTURES / f"{code}.json"
    if SCHREIBEN:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        daten = json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {"code": code, "faelle": {}}
        daten["faelle"][str(nr)] = ist
        daten["faelle"] = dict(sorted(daten["faelle"].items(), key=lambda kv: int(kv[0])))
        pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return
    assert pfad.exists(), f"Fixture fehlt: {pfad.name}"
    soll = json.loads(pfad.read_text(encoding="utf-8"))["faelle"].get(str(nr))
    assert soll is not None, f"Fixture {pfad.name} ohne Fall Nr {nr}"
    assert ist == soll
