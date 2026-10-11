"""N-659 (Option A, Gernot 11.10.2026) — HA-Export und *Cockpit → Übersicht* rechnen die Bilanz aus EINER Fakten-Menge.

Einspeisung und Netzbezug gibt es nur in Monaten mit Zählerzeile. Die PV kam in beiden Sichten aus ALLEN Monats-Fakten:
ein Monat mit Erzeugung, aber ohne Zählerzeile, zählte damit ganz als Eigenverbrauch, die Ersparnis (nur Monate mit
Zählerzeile) rechnete ihn nicht — und im HA-Export zogen Ersparnis und CO₂ verschiedene Verlustmengen ab. Jetzt gehen
alle Bilanz-Eingänge (PV, Speicher, V2H, Abgabe, Wandlungsverluste) über die Monate mit Zählerzeile und aktivem
Erzeuger — dieselbe Menge wie Ersparnis und USt. Die Anzeige „PV-Erzeugung" bleibt über alle Fakten.

Probe (Messung aus Bericht K3): Mai 2025 mit Zählerzeile (Einspeisung 300, Netzbezug 200) und PV 500, Juni 2025 nur
PV 600 (keine Zählerzeile), 30 ct. Vorher in beiden Sichten Eigenverbrauch 800, Autarkie 80 %, CO₂ (HA) 304 kg.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.api.routes.cockpit.nachhaltigkeit import get_nachhaltigkeit
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.ha_export import calculate_anlage_sensors
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.strompreis import Strompreis


async def _anlage(db) -> Anlage:
    anlage = Anlage(anlagenname="N659", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=12000.0)
    db.add(pv)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=5, einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    for monat, kwh in ((5, 500.0), (6, 600.0)):
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=monat,
                                      verbrauch_daten={"pv_erzeugung_kwh": kwh}))
    await db.commit()
    return (await db.execute(select(Anlage).where(Anlage.id == anlage.id))).scalar_one()


@pytest.mark.asyncio
async def test_monat_ohne_zaehlerzeile_bilanz_in_beiden_sichten_gleich(db):
    anlage = await _anlage(db)
    ueb = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)
    svs = {s.definition.key: s.value for s in await calculate_anlage_sensors(db, anlage)}

    # Bilanz nur aus dem Mai: 500 − 300 = 200 kWh, Autarkie 200 / (200 + 200).
    assert (round(ueb.eigenverbrauch_kwh, 1), round(svs["eigenverbrauch_gesamt_kwh"], 1)) == (200.0, 200.0)
    assert (round(ueb.autarkie_prozent, 1), round(svs["autarkie_prozent"], 1)) == (50.0, 50.0)
    assert (round(ueb.ev_ersparnis_euro, 2), round(svs["eigenverbrauch_ersparnis_euro"], 2)) == (60.0, 60.0)
    # CO₂ auf derselben Menge: 200 kWh × 0,38.
    assert round(svs["co2_ersparnis_kg"], 1) == 76.0
    # Die Anzeige „PV-Erzeugung" zählt beide Monate.
    assert (round(ueb.pv_erzeugung_kwh, 1), round(svs["pv_erzeugung_gesamt_kwh"], 1)) == (1100.0, 1100.0)


@pytest.mark.asyncio
async def test_co2_in_uebersicht_ha_sensor_und_nachhaltigkeit_gleich(db):
    """Derselbe Fall: 200 kWh × 0,38 = 76 kg in allen drei Sichten (vorher Nachhaltigkeit 304: Juni ganz als EV)."""
    anlage = await _anlage(db)
    ueb = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)
    svs = {s.definition.key: s.value for s in await calculate_anlage_sensors(db, anlage)}
    nh = await get_nachhaltigkeit(anlage_id=anlage.id, db=db)
    assert (round(ueb.co2_gesamt_kg, 1), round(svs["co2_ersparnis_kg"], 1), round(nh.co2_gesamt_kg, 1)) == (
        76.0, 76.0, 76.0,
    )
