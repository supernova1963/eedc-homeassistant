"""RF-16 — zwei Fälle des E-Auto-Hubs, die weder die übrige Suite noch die Golden-Master-Bestände erreichen.

Der Schnitt von ``get_eauto_dashboard`` (RF-16, Serie „Funktion vor Datei", 13.10.2026) ist ein reiner Umzug. Die Vorlage
(§4.5/§4.6) hat gemessen, dass zwei Zweige der Monatstabelle sonst ungedeckt bleiben:

* **F1** — eine Zeile trägt das Feld ``ladung_extern_kwh`` (hier 0, ohne Euro), der Topf hat kein Extern: die Tabelle
  zeigt das Extern-Paar als ``0,0 / 0,0`` (das Feld war da, also keine erfundene 0 — P4, N-728). Ohne die Bedingung
  ``'ladung_extern_kwh' in d`` bliebe das rohe ``0`` ohne Euro-Feld stehen (Sprengsatz S3 der Vorlage).
* **F2** — ein privates Auto mit Fahrverbrauch und ohne Ladefelder, die Wallbox ohne Wert im Monat: die Zeile trägt die
  Schätzung aus dem Fahrverbrauch und ist ``ladung_geschaetzt`` (N-555); mit Tages-PV-Quote anteilig PV, ohne ganz Netz.

Schwesterdateien: test_n728_eauto_hub_extern_kopf_gleich_reihe.py (Extern-Paar), test_n564_eauto_hub_kachel_gleich_tabelle.py
(Kachel = Σ Tabelle), test_emob_pv_anteil_sichten_symmetrie.py (Tages-PV-Quote).
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.dashboard_eauto import get_eauto_dashboard
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.tages_energie_profil import TagesZusammenfassung

J, M = 2026, 4


async def _anlage(db, wb_zeile: dict | None, auto_zeile: dict, tages_pv_netz: tuple[float, float] | None = None):
    """Anlage mit einer privaten Wallbox in Betrieb (Zeile im Monat nur, wenn ``wb_zeile``) und einem privaten Auto."""
    a = Anlage(anlagenname="RF16", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1), parameter={})
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Auto", anschaffungsdatum=date(2024, 1, 1), parameter={})
    db.add_all([wb, ea])
    await db.flush()
    if wb_zeile is not None:
        db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=J, monat=M, verbrauch_daten=dict(wb_zeile)))
    db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=J, monat=M, verbrauch_daten=dict(auto_zeile)))
    if tages_pv_netz is not None:
        db.add(TagesZusammenfassung(
            anlage_id=a.id, datum=date(J, M, 15),
            emob_ladung_pv_abgeleitet_kwh=tages_pv_netz[0],
            emob_ladung_netz_abgeleitet_kwh=tages_pv_netz[1],
        ))
    await db.commit()
    return a


@pytest.mark.asyncio
async def test_f1_extern_feld_ohne_euro_und_topf_ohne_extern_steht_als_null_paar(db):
    a = await _anlage(db, {"ladung_kwh": 200.0, "ladung_pv_kwh": 100.0}, {"km_gefahren": 800, "ladung_extern_kwh": 0})
    (karte,) = await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    (zeile,) = karte.monatsdaten
    d = zeile.verbrauch_daten
    # Das Feld war in der Zeile ⇒ das Paar steht vollständig da, gerundet als float (nicht das rohe int 0 ohne Euro).
    assert "ladung_extern_euro" in d
    assert d["ladung_extern_kwh"] == 0.0 and isinstance(d["ladung_extern_kwh"], float)
    assert d["ladung_extern_euro"] == 0.0 and isinstance(d["ladung_extern_euro"], float)
    z = karte.zusammenfassung
    assert (z["ladung_extern_kwh"], z["ladung_extern_euro"]) == (0.0, 0.0)
    # Die Heimladung der Wallbox geht ganz an das eine Auto (Rest, km-Anteil 1).
    assert d["ladung_kwh"] == pytest.approx(200.0)
    assert z["ladung_heim_kwh"] == pytest.approx(200.0)


@pytest.mark.asyncio
async def test_f1_gegenrichtung_ohne_extern_feld_bleibt_ohne_feld(db):
    a = await _anlage(db, {"ladung_kwh": 200.0, "ladung_pv_kwh": 100.0}, {"km_gefahren": 800})
    (karte,) = await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    (zeile,) = karte.monatsdaten
    # Kein Feld, kein Paar ⇒ keine erfundene 0 (P4).
    assert "ladung_extern_kwh" not in zeile.verbrauch_daten
    assert "ladung_extern_euro" not in zeile.verbrauch_daten


@pytest.mark.asyncio
async def test_f2_schaetzung_aus_fahrverbrauch_ohne_tages_quote_ist_ganz_netz(db):
    a = await _anlage(db, None, {"km_gefahren": 1000, "verbrauch_kwh": 150.0})
    (karte,) = await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    (zeile,) = karte.monatsdaten
    d = zeile.verbrauch_daten
    assert d.get("ladung_geschaetzt") is True
    assert (d["ladung_pv_kwh"], d["ladung_netz_kwh"], d["ladung_kwh"]) == (0.0, 150.0, 150.0)
    z = karte.zusammenfassung
    assert z["ladung_heim_kwh"] == pytest.approx(150.0)
    assert z["ladung_pv_kwh"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_f2_schaetzung_aus_fahrverbrauch_mit_tages_quote_teilt_pv_und_netz(db):
    # Tagesebene 300 PV / 100 Netz ⇒ Quote 0,75 ⇒ 150 kWh Fahrverbrauch = 112,5 PV + 37,5 Netz.
    a = await _anlage(db, None, {"km_gefahren": 1000, "verbrauch_kwh": 150.0}, tages_pv_netz=(300.0, 100.0))
    (karte,) = await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    (zeile,) = karte.monatsdaten
    d = zeile.verbrauch_daten
    assert d.get("ladung_geschaetzt") is True
    assert d["ladung_pv_kwh"] == pytest.approx(112.5)
    assert d["ladung_netz_kwh"] == pytest.approx(37.5)
    assert d["ladung_kwh"] == pytest.approx(150.0)
    z = karte.zusammenfassung
    assert z["ladung_heim_kwh"] == pytest.approx(150.0)
    assert z["pv_anteil_heim_prozent"] == pytest.approx(75.0)
