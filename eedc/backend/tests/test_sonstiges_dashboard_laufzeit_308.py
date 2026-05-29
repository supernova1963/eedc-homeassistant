"""Sonstiges-Dashboard: Laufzeit-Filter (#308-Klasse).

`get_sonstiges_dashboard` summierte als einziges der sechs Dashboards die
Monatsdaten ohne `ist_aktiv_im_monat`-Filter — Monate vor Anschaffung bzw.
nach Stilllegung flossen in die gesamt_*-KPIs (Erzeugung, Ersparnis, CO2).
Dieselbe Bug-Klasse wie #308 (WP-Counter), hier ohne Lebensdauer-Kollision.
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.investitionen.dashboards import get_sonstiges_dashboard
from backend.models import Anlage, Investition, InvestitionMonatsdaten


async def test_sonstiges_dashboard_respektiert_laufzeit(db):
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    inv = Investition(
        anlage_id=anlage.id, typ="sonstiges", bezeichnung="Mini-BHKW",
        anschaffungsdatum=date(2025, 1, 1),
        stilllegungsdatum=date(2025, 12, 31),
        parameter={"kategorie": "erzeuger", "beschreibung": "Test"},
    )
    db.add(inv)
    await db.flush()

    # 12 Monate IM Fenster: je 100 kWh → Σ 1.200 kWh.
    for monat in range(1, 13):
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=2025, monat=monat,
            verbrauch_daten={"erzeugung_kwh": 100.0, "eigenverbrauch_kwh": 60.0},
        ))
    # Spuk-Monat vor Anschaffung — muss raus.
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2024, monat=12,
        verbrauch_daten={"erzeugung_kwh": 5000.0, "eigenverbrauch_kwh": 5000.0},
    ))
    # Spuk-Monat nach Stilllegung — muss raus.
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=1,
        verbrauch_daten={"erzeugung_kwh": 5000.0, "eigenverbrauch_kwh": 5000.0},
    ))
    await db.flush()

    dashboards = await get_sonstiges_dashboard(
        anlage_id=anlage.id, strompreis_cent=30.0,
        einspeiseverguetung_cent=8.0, db=db,
    )
    assert len(dashboards) == 1
    z = dashboards[0].zusammenfassung
    # Nur die 12 In-Fenster-Monate: 1.200 kWh, nicht 11.200 kWh.
    assert z["gesamt_erzeugung_kwh"] == 1200.0
    assert z["anzahl_monate"] == 12
