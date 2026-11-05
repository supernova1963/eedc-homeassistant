"""N-775 — Cockpit → Tag «Peak PV»: ein Balkonkraftwerk mit Leistungssensor und seine messenden Modul-Kinder zählen im
Tages-Peak aus der HA-Langzeitstatistik nicht doppelt.

`services/energie_profil/_helpers.py::_get_tagespeaks_aus_ha_lts` (Etappe 5, Phasen seit RF-53) summiert je Stunde die
Maxima der gewählten PV-Entities. Bis N-775 nahm die Auswahl jede `leistung_w`-Entity der Typen `pv-module`/
`balkonkraftwerk` — BKW 0,8 kW + Kinder 0,4 + 0,4 ⇒ `peak_pv` 1,6 statt 0,8. Seitdem gilt die Regel von N-536
(`core/berechnungen/erzeuger_traeger.py`): messen **alle** Kinder selbst, wird die BKW-Entity nicht gelesen
(`bkw_kinder_decken_vollstaendig`, wie `live_verbrauchsprofil_service._history_je_sensor`); misst nur ein Teil, trägt das
BKW je Stunde den Rest `max(0, BKW − Σ messende Kinder)` (`bkw_restwerte`, wie Live/Stunde und der W-Sample-Pfad
`live_tagesverlauf_service._bkw_kuerzung_slot`).

In-Process wie `test_etappe_5_peaks.py`: gestellte Investitions-Zeilen (zwei Abfragen — `(id, typ)` und die Elternschaft
`(id, parent_investition_id)` der Module) und gestellte LTS-Min/Max.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.services.energie_profil._helpers import _get_tagespeaks_aus_ha_lts

D = date(2026, 5, 15)
# BKW 7 mit den Modul-Kindern 8 und 9.
_ZEILEN = [(7, "balkonkraftwerk", None), (8, "pv-module", 7), (9, "pv-module", 7)]


class _Db:
    """AsyncSession-Attrappe: die Investitions-Abfrage liefert ``(id, typ)``, die Elternschafts-Abfrage ``(id, parent)``."""

    def __init__(self, zeilen):
        self.zeilen, self.abfragen = zeilen, []

    async def execute(self, stmt):
        sql = str(stmt)
        self.abfragen.append(sql)
        if "parent_investition_id" in sql:
            rows = [(i, p) for i, t, p in self.zeilen if t == "pv-module" and p is not None]
        else:
            rows = [(i, t) for i, t, _ in self.zeilen]
        res = MagicMock()
        res.all = MagicMock(return_value=rows)
        return res


def _mapping(*inv_ids: int) -> dict:
    return {"investitionen": {str(i): {"live": {"leistung_w": f"sensor.inv{i}"}} for i in inv_ids}}


def _stats(max_je_inv: dict[int, float]):
    svc = MagicMock()
    svc.is_available = True
    mm = {f"sensor.inv{i}": {D.isoformat(): {12: {"min": 0.0, "max": v}}} for i, v in max_je_inv.items()}
    svc.get_hourly_minmax_sensor_data.side_effect = lambda ids, von, bis: {e: mm[e] for e in ids if e in mm}
    return svc


async def _peak_pv(mapping: dict, max_je_inv: dict[int, float], zeilen=_ZEILEN):
    db = _Db(zeilen)
    svc = _stats(max_je_inv)
    with patch("backend.services.ha_statistics_service.get_ha_statistics_service", return_value=svc):
        p = await _get_tagespeaks_aus_ha_lts(SimpleNamespace(id=1, sensor_mapping=mapping), D, db)
    return p.pv, db, svc


async def test_bkw_und_beide_kinder_messen_zaehlt_einmal():
    """Fall 1 (der Fund): BKW 0,8 + Kinder 0,4/0,4, alle gemappt ⇒ 0,8 (am HEAD 6e763b7a5: 1,6)."""
    pv, _, svc = await _peak_pv(_mapping(7, 8, 9), {7: 0.8, 8: 0.4, 9: 0.4})
    assert pv == pytest.approx(0.8)
    gelesen = set(svc.get_hourly_minmax_sensor_data.call_args.args[0])
    assert "sensor.inv7" not in gelesen, "voll gedecktes BKW: seine Entity wird nicht gelesen (N-536)"


async def test_voll_gedeckt_liest_das_bkw_nicht_auch_wenn_es_mehr_zeigt():
    """Fall 1b: alle Kinder messen, das BKW-Maximum liegt über ihrer Summe ⇒ Σ Kinder (die BKW-Entity zählt nicht)."""
    pv, _, _ = await _peak_pv(_mapping(7, 8, 9), {7: 0.8, 8: 0.3, 9: 0.3})
    assert pv == pytest.approx(0.6)


async def test_bkw_ohne_messende_kinder_zaehlt_selbst():
    """Fall 2: nur das BKW gemappt ⇒ 0,8 — die einzige Quelle bleibt, keine Elternschafts-Abfrage nötig."""
    pv, db, _ = await _peak_pv(_mapping(7), {7: 0.8})
    assert pv == pytest.approx(0.8)
    assert len(db.abfragen) == 1, "ohne gemapptes Modul kein zweiter DB-Zugriff"


async def test_kinder_ohne_bkw_sensor_zaehlen_als_summe():
    """Fall 3: nur die Kinder gemappt ⇒ Σ Kinder 0,8."""
    pv, _, _ = await _peak_pv(_mapping(8, 9), {8: 0.4, 9: 0.4})
    assert pv == pytest.approx(0.8)


async def test_ein_kind_misst_bkw_traegt_den_rest():
    """Fall 4 (Teil-Deckung): BKW 0,8 + Kind 8 0,4, Kind 9 ohne Sensor. N-536-Regel: das BKW zählt nie neben seinen
    Kindern; mit Lücke trägt es den Rest max(0, 0,8 − 0,4) = 0,4 ⇒ 0,4 + 0,4 = 0,8 (am HEAD 1,2)."""
    pv, _, _ = await _peak_pv(_mapping(7, 8), {7: 0.8, 8: 0.4})
    assert pv == pytest.approx(0.8)


async def test_teil_deckung_klemmt_den_rest_auf_null():
    """Fall 4b: das messende Kind zeigt mehr als das BKW (andere Minute im Stunden-Bucket) ⇒ Rest 0, Peak = Kind 0,9."""
    pv, _, _ = await _peak_pv(_mapping(7, 8), {7: 0.8, 8: 0.9})
    assert pv == pytest.approx(0.9)


async def test_bkw_ohne_kinder_in_der_anlage_unveraendert():
    """Gegenprobe: BKW und ein Modul ohne Elternschaft (Modul am Wechselrichter) ⇒ beide zählen wie bisher."""
    zeilen = [(7, "balkonkraftwerk", None), (8, "pv-module", None)]
    pv, _, _ = await _peak_pv(_mapping(7, 8), {7: 0.8, 8: 3.0}, zeilen=zeilen)
    assert pv == pytest.approx(3.8)


# ── Mit echter Datenbank: die Elternschafts-Abfrage selbst (die Attrappe oben beantwortet sie nur) ──────────────────

async def _peak_pv_db(db, kinder_ab: date, max_je_inv: dict[int, float]):
    from backend.models.anlage import Anlage
    from backend.models.investition import Investition

    anlage = Anlage(anlagenname="N775", leistung_kwp=0.8, sensor_mapping=_mapping(7, 8, 9))
    db.add(anlage)
    await db.flush()
    db.add(Investition(id=7, anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="BKW", aktiv=True,
                       anschaffungsdatum=date(2024, 1, 1)))
    for i in (8, 9):
        db.add(Investition(id=i, anlage_id=anlage.id, typ="pv-module", bezeichnung=f"Modul {i}", aktiv=True,
                           anschaffungsdatum=kinder_ab, parent_investition_id=7))
    await db.commit()
    svc = _stats(max_je_inv)
    with patch("backend.services.ha_statistics_service.get_ha_statistics_service", return_value=svc):
        return (await _get_tagespeaks_aus_ha_lts(anlage, D, db)).pv


async def test_echte_abfrage_bkw_und_kinder_zaehlt_einmal(db):
    """Fall 1 über die echte Abfrage (Kinder seit 2025 aktiv) ⇒ 0,8."""
    assert await _peak_pv_db(db, date(2025, 1, 1), {7: 0.8, 8: 0.4, 9: 0.4}) == pytest.approx(0.8)


async def test_kinder_erst_nach_dem_tag_angeschafft_treten_nichts_ab(db):
    """Zeitfilter vor dem Selektor (P11, N-615): am Tag waren die Module noch nicht angeschafft, ihre Sensoren haben keine
    Werte ⇒ keine Abtretung, das BKW zählt (0,8). Ohne den Zeitfilter fiele die BKW-Entity weg und der Tag hätte keinen
    PV-Peak (None)."""
    assert await _peak_pv_db(db, date(2026, 6, 1), {7: 0.8}) == pytest.approx(0.8)
