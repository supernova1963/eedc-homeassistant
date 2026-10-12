"""N-728 — E-Auto-Hub: die externe Ladung im Kopf ist die Summe der Monatsreihe (eine Quelle).

Am HEAD `7fb9b026` gemessen (Triage 12.10., Nr. 101): der Kopf nahm die Topf-Regel ``waehle_extern_paar`` EINMAL über den
ganzen Zeitraum, Verlauf, Tabelle und Jahresvergleich lasen das rohe ``ladung_extern_kwh`` der Zeilen des Autos
(``EAutoCharts.tsx``, ``EAutoJahresvergleich.tsx``):

* Fall A — extern am Auto 50 + 30 kWh ohne Euro, Wallbox ohne Extern: Kopf **0** (Gleichstand 0 € ⇒ Wallbox), Σ Reihe **80**.
* Fall C — extern an der Wallbox-Zeile (Altbestand) 40 kWh / 20 €: Kopf **40**, Σ Reihe **0**.

Jetzt rechnen Kopf und Zeilen je Monat über ``emob_extern_im_monat`` (dieselbe Funktion wie HA-Export und Aussichten);
die Zeilen tragen das gewählte Paar, der Kopf ist ihre Summe. Und bei Kosten-Gleichstand (0 € gegen 0 €) gewinnt die
größere Menge (Entscheid Master 12.10., ``waehle_extern_paar``) — Fall A zählt damit 80 kWh in jeder Sicht.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.dashboard_eauto import get_eauto_dashboard
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten

J = 2026


async def _anlage(db, wb_zeilen: dict[int, dict], auto_zeilen: dict[int, dict]):
    a = Anlage(anlagenname="N728", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1), parameter={})
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Auto", anschaffungsdatum=date(2024, 1, 1), parameter={})
    db.add_all([wb, ea])
    await db.flush()
    for m, z in wb_zeilen.items():
        db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=J, monat=m, verbrauch_daten=dict(z)))
    for m, z in auto_zeilen.items():
        db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=J, monat=m, verbrauch_daten=dict(z)))
    await db.commit()
    return a


def _sigma(karte, feld):
    return sum((m.verbrauch_daten.get(feld) or 0) for m in karte.monatsdaten)


@pytest.mark.asyncio
async def test_fall_a_extern_am_auto_ohne_euro(db):
    a = await _anlage(
        db,
        {4: {"ladung_kwh": 200.0, "ladung_pv_kwh": 100.0}, 5: {"ladung_kwh": 200.0, "ladung_pv_kwh": 100.0}},
        {4: {"km_gefahren": 1000.0, "ladung_extern_kwh": 50.0}, 5: {"km_gefahren": 800.0, "ladung_extern_kwh": 30.0}},
    )
    (karte,) = await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    z = karte.zusammenfassung
    assert z["ladung_extern_kwh"] == pytest.approx(80.0)          # am HEAD 0 (Gleichstand ⇒ Wallbox-Seite)
    assert _sigma(karte, "ladung_extern_kwh") == pytest.approx(80.0)
    assert z["ladung_extern_euro"] == pytest.approx(round(_sigma(karte, "ladung_extern_euro"), 2))
    assert z["gesamt_ladung_kwh"] == pytest.approx(round(z["ladung_heim_kwh"] + 80.0, 1))
    # Dieselbe Regel in Cockpit → Monat (Monats-Fakten) — „überall 80".
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    extern = [(await get_aktueller_monat(anlage_id=a.id, jahr=J, monat=m, db=db)).emob_ladung_extern_kwh for m in (4, 5)]
    assert extern == [pytest.approx(50.0), pytest.approx(30.0)]


@pytest.mark.asyncio
async def test_fall_b_extern_mit_euro(db):
    a = await _anlage(
        db,
        {4: {"ladung_kwh": 200.0, "ladung_pv_kwh": 100.0}},
        {4: {"km_gefahren": 1000.0, "ladung_extern_kwh": 50.0, "ladung_extern_euro": 25.0}},
    )
    (karte,) = await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    z = karte.zusammenfassung
    assert (z["ladung_extern_kwh"], z["ladung_extern_euro"]) == (50.0, 25.0)
    assert _sigma(karte, "ladung_extern_kwh") == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_fall_c_extern_an_der_wallbox_zeile(db):
    a = await _anlage(
        db,
        {4: {"ladung_kwh": 200.0, "ladung_pv_kwh": 100.0, "ladung_extern_kwh": 40.0, "ladung_extern_euro": 20.0}},
        {4: {"km_gefahren": 1000.0}},
    )
    (karte,) = await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    z = karte.zusammenfassung
    assert (z["ladung_extern_kwh"], z["ladung_extern_euro"]) == (40.0, 20.0)
    assert _sigma(karte, "ladung_extern_kwh") == pytest.approx(40.0)
    assert _sigma(karte, "ladung_extern_euro") == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_extern_je_monat_gewaehlt_nicht_ueber_den_zeitraum(db):
    """April: Wallbox-Extern 40 kWh / 20 €, Auto ohne · Mai: Auto 30 kWh / 15 €, Wallbox ohne. Je Monat gewinnt das
    teurere Paar (wie Cockpit → Monat, HA-Export, Aussichten) ⇒ 70 kWh / 35 €; über den Zeitraum gewählt waren es 40 / 20."""
    a = await _anlage(
        db,
        {4: {"ladung_kwh": 200.0, "ladung_pv_kwh": 100.0, "ladung_extern_kwh": 40.0, "ladung_extern_euro": 20.0},
         5: {"ladung_kwh": 200.0, "ladung_pv_kwh": 100.0}},
        {4: {"km_gefahren": 1000.0}, 5: {"km_gefahren": 800.0, "ladung_extern_kwh": 30.0, "ladung_extern_euro": 15.0}},
    )
    (karte,) = await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    z = karte.zusammenfassung
    assert (z["ladung_extern_kwh"], z["ladung_extern_euro"]) == (70.0, 35.0)
    assert _sigma(karte, "ladung_extern_kwh") == pytest.approx(70.0)


def test_topf_regel_gleichstand_groessere_menge():
    """Die Regel selbst (`waehle_extern_paar`): höhere Kosten gewinnen; bei Kostengleichstand die größere Menge, erst
    dann die Wallbox."""
    from backend.services.eauto_wirtschaftlichkeit import waehle_extern_paar

    assert waehle_extern_paar(40.0, 20.0, 50.0, 10.0) == (40.0, 20.0)
    assert waehle_extern_paar(40.0, 10.0, 50.0, 20.0) == (50.0, 20.0)
    assert waehle_extern_paar(0.0, 0.0, 80.0, 0.0) == (80.0, 0.0)      # am HEAD (0, 0)
    assert waehle_extern_paar(30.0, 0.0, 30.0, 0.0) == (30.0, 0.0)
