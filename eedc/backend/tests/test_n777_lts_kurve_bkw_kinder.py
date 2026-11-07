"""N-777 — LTS-Stundenkurve (Vollbackfill, Reparatur-Werkbank): ein Balkonkraftwerk mit Leistungssensor und seine
messenden Modul-Kinder zählen je Stunde nicht doppelt.

`services/energie_profil/lts_tagesverlauf.py::lade_tagesverlauf_aus_lts` baut je `leistung_w`-Entity der Typen
`pv-module`/`balkonkraftwerk` eine PV-Serie (`baue_investitions_serien`). Bis N-777 standen BKW und Kinder nebeneinander —
BKW 0,8 kW + Kinder 0,4 + 0,4 ⇒ 1,6 kW je Stunde. Seitdem dieselbe Werte-Regel wie im Live-Zwilling
(`live_tagesverlauf_service._bkw_kuerzung_slot`, Regel N-536): je Stunde trägt das BKW über `kuerze_bkw_in_werte_map` nur
``max(0, BKW − Σ Kinder mit Wert in dieser Stunde)``, Rest 0 ⇒ kein Wert; fehlt den Kindern die Stunde, bleibt der BKW-Wert.

In-Process wie `test_rf73_tagesbilanz_lts_phasen.py`: gestellte Investitionen (echtes Modell, damit `ist_aktiv_an` und
die Elternschaft echt rechnen) und gestellte HA-Langzeitstatistik.
"""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.models.investition import Investition
from backend.services.energie_profil.lts_tagesverlauf import lade_tagesverlauf_aus_lts

D = date(2026, 5, 14)
BKW, K1, K2 = "sensor.bkw", "sensor.modul1", "sensor.modul2"


class _Res:
    def __init__(self, objs):
        self._objs = objs

    def scalars(self):
        return self

    def all(self):
        return list(self._objs)


class _Db:
    def __init__(self, invs):
        self.invs = list(invs)

    async def execute(self, stmt):
        return _Res(self.invs)


class _Ha:
    is_available = True

    def __init__(self, daten):
        self.daten = daten

    def get_hourly_sensor_data(self, ids, von, bis):
        return {eid: {d: dict(h) for d, h in self.daten[eid].items()} for eid in ids if eid in self.daten}


def _invs(kind2_ab=None):
    return [
        Investition(id=7, typ="balkonkraftwerk", aktiv=True),
        Investition(id=11, typ="pv-module", aktiv=True, parent_investition_id=7),
        Investition(id=12, typ="pv-module", aktiv=True, parent_investition_id=7, anschaffungsdatum=kind2_ab),
    ]


def _anlage(*sensoren):
    """Leistungssensoren je Investition: ``("7", BKW), ("11", K1)`` …"""
    return SimpleNamespace(id=1, sensor_mapping={"basis": {"live": {}},
                                                 "investitionen": {i: {"live": {"leistung_w": s}} for i, s in sensoren}})


async def _werte(anlage, daten, invs=None, stunde=12, d=D):
    with patch("backend.services.ha_statistics_service.get_ha_statistics_service", return_value=_Ha(daten)):
        erg = await lade_tagesverlauf_aus_lts(_Db(invs if invs is not None else _invs()), anlage, d, d)
    return {p["zeit"]: p["werte"] for p in erg.tage[d]["punkte"]}.get(f"{stunde:02d}:00"), erg.tage[d]


def _h(**werte_je_sensor):
    return {eid: {D.isoformat(): {12: w}} for eid, w in werte_je_sensor.items()}


@pytest.mark.asyncio
async def test_bkw_und_zwei_messende_kinder_zaehlen_einmal():
    werte, tag = await _werte(_anlage(("7", BKW), ("11", K1), ("12", K2)), _h(**{BKW: 0.8, K1: 0.4, K2: 0.4}))
    assert werte == {"pv_11": 0.4, "pv_12": 0.4}          # 0,8 — bis N-777 1,6 (pv_7 0,8 daneben)
    assert sum(werte.values()) == pytest.approx(0.8)
    assert "pv_7" in [s["key"] for s in tag["serien"]]   # die Serie bleibt beschrieben, sie trägt nur keinen Wert


@pytest.mark.asyncio
async def test_bkw_ohne_messende_kinder_traegt_selbst():
    werte, _ = await _werte(_anlage(("7", BKW)), _h(**{BKW: 0.8}))
    assert werte == {"pv_7": 0.8}


@pytest.mark.asyncio
async def test_kinder_ohne_bkw_sensor_summieren():
    werte, _ = await _werte(_anlage(("11", K1), ("12", K2)), _h(**{K1: 0.4, K2: 0.4}))
    assert werte == {"pv_11": 0.4, "pv_12": 0.4}


@pytest.mark.asyncio
async def test_teil_deckung_bkw_traegt_den_rest():
    werte, _ = await _werte(_anlage(("7", BKW), ("11", K1)), _h(**{BKW: 0.8, K1: 0.3}))
    assert werte == {"pv_7": 0.5, "pv_11": 0.3}          # Rest 0,8 − 0,3; Kind 12 misst nicht


@pytest.mark.asyncio
async def test_teil_deckung_rest_nie_negativ():
    werte, _ = await _werte(_anlage(("7", BKW), ("11", K1)), _h(**{BKW: 0.3, K1: 0.5}))
    assert werte == {"pv_11": 0.5}                       # Rest max(0, 0,3 − 0,5) = 0 ⇒ kein Wert


@pytest.mark.asyncio
async def test_kind_erst_nach_dem_tag_angeschafft_zieht_nichts_ab():
    """Kind 12 ist am Tag noch nicht angeschafft und hat deshalb keine Serie; es zieht nichts ab."""
    werte, _ = await _werte(_anlage(("7", BKW), ("11", K1), ("12", K2)), _h(**{BKW: 0.5, K1: 0.4, K2: 0.4}),
                            invs=_invs(kind2_ab=D + timedelta(days=1)))
    # 0,5: Rest = BKW 0,5 − Σ Kinder mit Wert am Tag (nur Kind 11, 0,4) = 0,1, dazu Kind 11 mit 0,4 — die BKW-Messung bleibt ganz.
    assert werte == {"pv_7": 0.1, "pv_11": 0.4}
    assert sum(werte.values()) == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_kinder_ohne_wert_in_der_stunde_bkw_deckt_die_luecke():
    """Die Kinder haben Sensoren, aber in Stunde 12 keinen Wert: das BKW bleibt ganz (wie der Live-Pfad)."""
    daten = {BKW: {D.isoformat(): {11: 0.8, 12: 0.8}}, K1: {D.isoformat(): {11: 0.4}}, K2: {D.isoformat(): {11: 0.4}}}
    werte, tag = await _werte(_anlage(("7", BKW), ("11", K1), ("12", K2)), daten)
    assert werte == {"pv_7": 0.8}
    assert [p["werte"] for p in tag["punkte"] if p["zeit"] == "11:00"] == [{"pv_11": 0.4, "pv_12": 0.4}]


@pytest.mark.asyncio
async def test_bkw_ueber_der_kinder_summe_traegt_den_rest():
    """Benannt: BKW 0,9, Kinder 0,4 + 0,4 ⇒ 0,9 (Rest 0,1 bleibt beim BKW, wie `kuerze_bkw_in_werte_map` im Live)."""
    werte, _ = await _werte(_anlage(("7", BKW), ("11", K1), ("12", K2)), _h(**{BKW: 0.9, K1: 0.4, K2: 0.4}))
    assert werte == {"pv_7": 0.1, "pv_11": 0.4, "pv_12": 0.4}


@pytest.mark.asyncio
async def test_bkw_null_ohne_kind_wert_faellt_weg():
    """Benannte Grenze: BKW meldet 0,0, kein Kind hat einen Wert ⇒ Rest 0 ⇒ kein Key; die Stunde ohne anderen Wert fehlt
    (dieselbe Löschung wie `kuerze_bkw_in_werte_map` im Live-Pfad)."""
    daten = {BKW: {D.isoformat(): {11: 0.8, 12: 0.0}}, K1: {D.isoformat(): {11: 0.4}}}
    werte, tag = await _werte(_anlage(("7", BKW), ("11", K1)), daten)
    assert werte is None
    assert [p["zeit"] for p in tag["punkte"]] == ["11:00"]


@pytest.mark.asyncio
async def test_vortagsrand_nach_derselben_regel():
    vortag = (D - timedelta(days=1)).isoformat()
    daten = {BKW: {vortag: {23: 0.8}, D.isoformat(): {12: 0.8}},
             K1: {vortag: {23: 0.4}, D.isoformat(): {12: 0.4}},
             K2: {vortag: {23: 0.4}, D.isoformat(): {12: 0.4}}}
    _, tag = await _werte(_anlage(("7", BKW), ("11", K1), ("12", K2)), daten)
    assert tag["vortagsrand"] == [{"zeit": "23:00", "werte": {"pv_11": 0.4, "pv_12": 0.4}}]
