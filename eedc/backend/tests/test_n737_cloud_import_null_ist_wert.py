"""N-737 — Cloud-Importer: eine gelieferte 0 ist ein Wert, kein «fehlt».

**Der Defekt.** Vier Cloud-Importer bauten ihre Monatswerte mit ``round(x, 2) or None`` (EcoFlow PowerStream,
EcoFlow PowerOcean, Viessmann Gridbox) bzw. ``round(f, 2) if f > 0 else None`` (Growatt). Eine gelieferte
Einspeisung 0 (Balkonkraftwerk ohne Einspeisung, Nulleinspeiser) wurde damit zu ``None``; der Portal-Import schreibt
für ``None`` keinen Herkunfts-Eintrag, die Monatszeile trägt die DB-Default-0 ohne Herkunft — und seit N-734 gilt sie
als «nicht erfasst»: Cockpit → Monat zeigte Einspeisung, Eigenverbrauch und Autarkie leer, der Checker meldete
«Einspeisung nicht erfasst» (gemessen: PowerStream, Grid Feed-in 0.0 ⇒ (1500, None, None, None) statt
(1500, 0, 480, 24,2 %)).

**Die Regel** wie die Portal-Parser (N-714, ``import_parsers/base.py::monatswert``): **Anwesenheit entscheidet** —
liefert die Antwort das Feld, ist auch 0 ein Wert; fehlt es, bleibt es ``None``. Ein Monat erscheint weiter nur mit
mindestens einem Wert > 0 (``monat_hat_wert_ueber_null``), damit Jahres-Arrays mit Null-Monaten keine leeren Monate
erzeugen. Hoymiles S-Miles (``grid_eq or feed_in_eq``) verlor eine numerische 0 auf demselben Weg.

Schwestern: ``test_ecoflow_diagnose_log.py``, ``test_viessmann_gridbox.py``, ``test_n734_netzfeld_ohne_herkunft.py``.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.routes.data_import import ApplyMonthInput, ApplyRequest, apply_import
from backend.models import Anlage, Investition, Monatsdaten
from backend.services.cloud_import import ecoflow_powerocean as epo
from backend.services.cloud_import import ecoflow_powerstream as eps
from backend.services.cloud_import import growatt as gw
from backend.services.cloud_import import hoymiles_smiles as hm
from backend.services.cloud_import import viessmann_gridbox as vg
from backend.tests import factories

J, M = 2025, 7


# ── Parser-Ebene je Importer ────────────────────────────────────────────────────────────────────────────────────


async def _ecoflow_monat(provider_cls, block: list[tuple[str, float]]):
    provider = provider_cls()

    async def fake_block(host, access_key, secret_key, serial_number, begin, end):  # noqa: ARG001
        return block

    provider._fetch_history_block = fake_block
    md, _ = await provider._fetch_single_month("https://example.test", "AK", "SK", "SN", J, M)
    return md


async def test_powerstream_einspeisung_null_bleibt_null():
    md = await _ecoflow_monat(eps.EcoFlowPowerStreamProvider,
                              [("Solar Generation", 80.0), ("Grid Feed-in", 0.0), ("Grid Consumption", 250.0)])
    blocks = len(list(eps.iter_history_blocks(J, M)))
    assert md.einspeisung_kwh == 0.0, "vorher None"
    assert md.pv_erzeugung_kwh == pytest.approx(80.0 * blocks)
    assert md.netzbezug_kwh == pytest.approx(250.0 * blocks)


async def test_powerstream_ohne_feld_bleibt_none():
    md = await _ecoflow_monat(eps.EcoFlowPowerStreamProvider,
                              [("Solar Generation", 80.0), ("Grid Consumption", 250.0)])
    assert md.einspeisung_kwh is None
    assert md.batterie_ladung_kwh is None


async def test_powerstream_monat_nur_mit_nullen_erscheint_nicht():
    md = await _ecoflow_monat(eps.EcoFlowPowerStreamProvider, [("Solar Generation", 0.0), ("Grid Feed-in", 0.0)])
    assert md is None


async def test_powerocean_einspeisung_null_bleibt_null():
    md = await _ecoflow_monat(epo.EcoFlowPowerOceanProvider,
                              [("From Solar", 80.0), ("To Grid", 0.0), ("From Grid", 250.0)])
    assert md.einspeisung_kwh == 0.0, "vorher None"
    assert md.netzbezug_kwh > 0


async def test_powerocean_ohne_feld_bleibt_none():
    md = await _ecoflow_monat(epo.EcoFlowPowerOceanProvider, [("From Solar", 80.0), ("From Grid", 250.0)])
    assert md.einspeisung_kwh is None


class _Resp:
    def __init__(self, data) -> None:
        self.status_code = 200
        self._data = data
        self.text = ""

    def json(self):
        return self._data


def _viessmann_client(monkeypatch, eintraege: list[dict]) -> None:
    class _Client:
        def __init__(self, *a, **k) -> None:  # noqa: ARG002
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def get(self, url, headers=None):  # noqa: ARG002
            return _Resp(eintraege)

    monkeypatch.setattr(vg.httpx, "AsyncClient", _Client)


async def _viessmann_monat(monkeypatch, eintraege: list[dict]):
    _viessmann_client(monkeypatch, eintraege)
    provider = vg.ViessmannGridBoxProvider()
    return await provider._fetch_month({}, "sys", J, M)


async def test_viessmann_einspeisung_null_bleibt_null(monkeypatch):
    md = await _viessmann_monat(monkeypatch, [{"photovoltaic": 5000, "gridFeedIn": 0, "gridPurchase": 3000}] * 2)
    assert (md.pv_erzeugung_kwh, md.einspeisung_kwh, md.netzbezug_kwh) == (10.0, 0.0, 6.0), "vorher ES None"


async def test_viessmann_netto_grid_misst_beide_richtungen(monkeypatch):
    md = await _viessmann_monat(monkeypatch, [{"photovoltaic": 5000, "grid": 3000}, {"photovoltaic": 5000, "grid": 1000}])
    assert (md.einspeisung_kwh, md.netzbezug_kwh) == (0.0, 4.0), "Netto-Bezug an jedem Tag ⇒ Einspeisung 0, nicht None"


async def test_viessmann_ohne_feld_bleibt_none(monkeypatch):
    md = await _viessmann_monat(monkeypatch, [{"photovoltaic": 5000, "gridPurchase": 3000}])
    assert md.einspeisung_kwh is None
    assert md.batterie_ladung_kwh is None


async def test_viessmann_null_im_ersten_schluessel_faellt_nicht_auf_den_zweiten(monkeypatch):
    md = await _viessmann_monat(monkeypatch, [{"photovoltaic": 5000, "gridFeedIn": 0, "purchase": 2000}])
    assert (md.einspeisung_kwh, md.netzbezug_kwh) == (0.0, 2.0)


async def _growatt_jahr(charts: dict):
    class _Client:
        async def get(self, *a, **k):  # noqa: ARG002
            return _Resp({"obj": {"charts": charts}})

    return await gw.GrowattProvider()._fetch_year_data(_Client(), {}, "plant", J)


async def test_growatt_einspeisung_null_bleibt_null():
    pv = [80.0] * 6 + [0.0] * 6
    monate = await _growatt_jahr({"ppv": pv, "pacToGrid": [0.0] * 12, "pacToUser": [250.0] * 6 + [0.0] * 6})
    assert [m.monat for m in monate] == [1, 2, 3, 4, 5, 6], "Monate nur mit Nullen erscheinen weiter nicht"
    assert (monate[0].pv_erzeugung_kwh, monate[0].einspeisung_kwh, monate[0].netzbezug_kwh) == (80.0, 0.0, 250.0)


async def test_growatt_ohne_feld_bleibt_none():
    monate = await _growatt_jahr({"ppv": [80.0] * 12, "pacToUser": [250.0] * 12})
    assert monate[0].einspeisung_kwh is None


async def test_hoymiles_numerische_null_bleibt_null(monkeypatch):
    async def fake(client, token, station_id, year, month):  # noqa: ARG001
        return {"total_eq": 80.0, "grid_eq": 0, "grid_purchase_eq": 250.0}

    monkeypatch.setattr(hm, "_get_station_monthly_data", fake)
    md = await hm.HoymilesSmilesProvider()._fetch_single_month(None, "t", "s", J, M)
    assert md.einspeisung_kwh == 0.0, "vorher None (`grid_eq or feed_in_eq`)"


async def test_hoymiles_ohne_feld_bleibt_none(monkeypatch):
    async def fake(client, token, station_id, year, month):  # noqa: ARG001
        return {"total_eq": 80.0, "grid_purchase_eq": 250.0}

    monkeypatch.setattr(hm, "_get_station_monthly_data", fake)
    md = await hm.HoymilesSmilesProvider()._fetch_single_month(None, "t", "s", J, M)
    assert md.einspeisung_kwh is None


# ── Ende zu Ende: PowerStream-Monat ⇒ Portal-Import ⇒ Cockpit → Monat und Checker ───────────────────────────────


async def _anlage(db) -> Anlage:
    a = await factories.anlage(db)
    await factories.strompreis(db, a.id, date(2024, 1, 1),
                               netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0)
    await factories.investition(db, a.id, "pv-module", bezeichnung="Dach", leistung_kwp=10.0)
    await factories.investition(db, a.id, "wallbox", bezeichnung="WB")
    await db.commit()
    return a


async def test_powerstream_null_einspeisung_ende_zu_ende(db, monkeypatch):
    import backend.api.routes.aktueller_monat as am
    from backend.services.daten_checker import DatenChecker

    async def _block(self, host, ak, sk, sn, begin, end):  # noqa: ARG001
        return [("Solar Generation", 80.0), ("Grid Feed-in", 0.0), ("Grid Consumption", 250.0)]

    monkeypatch.setattr(eps.EcoFlowPowerStreamProvider, "_fetch_history_block", _block)
    pm, _ = await eps.EcoFlowPowerStreamProvider()._fetch_single_month("h", "a", "s", "sn", J, M)

    a = await _anlage(db)
    r = await apply_import(anlage_id=a.id, data=ApplyRequest(monate=[ApplyMonthInput(
        jahr=J, monat=M, pv_erzeugung_kwh=pm.pv_erzeugung_kwh, einspeisung_kwh=pm.einspeisung_kwh,
        netzbezug_kwh=pm.netzbezug_kwh)]), ueberschreiben=False, datenquelle="portal_import", db=db)
    assert r.erfolg, r.fehler
    await db.commit()

    md = (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == a.id)
                           .execution_options(populate_existing=True))).scalar_one()
    assert "einspeisung_kwh" in (md.source_provenance or {}), "die gelieferte 0 ist gestempelt"

    async def _leer(*_a, **_k):
        return {}

    monkeypatch.setattr(am, "_collect_connector_data", _leer)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _leer)
    res = await am.get_aktueller_monat(anlage_id=a.id, jahr=J, monat=M, db=db)
    assert (res.netzbezug_kwh, res.einspeisung_kwh, res.eigenverbrauch_kwh, round(res.autarkie_prozent, 1)) == (
        1500.0, 0.0, 480.0, 24.2), "vorher (1500, None, None, None)"

    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == a.id)
    )).scalar_one()
    mds = list((await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == a.id))).scalars().all())
    erg = await DatenChecker(db)._check_monatsdaten_plausibilitaet(anlage, mds)
    assert [e.meldung for e in erg if "nicht erfasst" in e.meldung] == []
