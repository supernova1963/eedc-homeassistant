"""DI-3 — Kennzahlen-Drift-Inventur: der Jahres-/Anlagenbericht schließt
Dienstwagen aus der E-Mobilitäts-Aggregation aus.

Vorher summierte die IMD-Schleife in `services/pdf/builders/jahresbericht.py`
`km_gefahren` + Heimladung + V2H über ALLE E-Autos/Wallboxen — ohne
`ist_dienstlich`-Filter. Dienstwagen flossen dadurch in km, CO₂ und die
Heimladungs-Kennzahlen des Berichts ein, obwohl ihre Ladung eine Ausgabe (kein
Ertrag) ist. Cockpit, Komponenten-Sicht und HA-Export filtern längst
(`ist_dienstlich`, [[feedback_dienstwagen_alle_checks]]).

Der Test verifiziert an einer Anlage mit EINEM privaten + EINEM dienstlichen
E-Auto, dass der Bericht nur das private Fahrzeug zählt — und dass km/CO₂/
Heimladung deckungsgleich mit dem Cockpit sind.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten


async def _seed_privat_und_dienstwagen(db) -> int:
    anlage = Anlage(anlagenname="Dienstwagen-Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    privat = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Privat-Auto",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parameter={"ist_dienstlich": False},
    )
    dienst = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Dienstwagen",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parameter={"ist_dienstlich": True},
    )
    db.add_all([privat, dienst])
    await db.flush()

    # Privat: 10.000 km, Heimladung 2.000 (PV 1.200 / Netz 800), V2H 300
    db.add(InvestitionMonatsdaten(
        investition_id=privat.id, jahr=2025, monat=1,
        verbrauch_daten={"km_gefahren": 10000, "ladung_kwh": 2000,
                         "ladung_pv_kwh": 1200, "ladung_netz_kwh": 800,
                         "v2h_entladung_kwh": 300},
    ))
    # Dienstwagen: 40.000 km, Heimladung 5.000 — darf NICHT in den Bericht
    db.add(InvestitionMonatsdaten(
        investition_id=dienst.id, jahr=2025, monat=1,
        verbrauch_daten={"km_gefahren": 40000, "ladung_kwh": 5000,
                         "ladung_pv_kwh": 2000, "ladung_netz_kwh": 3000,
                         "v2h_entladung_kwh": 500},
    ))
    # Zählerwerte (damit eine Bilanz existiert)
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=1,
        einspeisung_kwh=1000, netzbezug_kwh=2000,
    ))
    await db.commit()
    return anlage.id


async def test_jahresbericht_ignoriert_dienstwagen(db):
    """km/Heimladung/V2H des Berichts enthalten nur das private Fahrzeug."""
    from backend.services.pdf.builders.jahresbericht import (
        build_jahresbericht_context,
    )

    anlage_id = await _seed_privat_und_dienstwagen(db)
    ctx = await build_jahresbericht_context(db, anlage_id, 2025)
    emob = ctx["emob"]

    assert emob["vorhanden"] is True
    assert emob["km"] == pytest.approx(10000.0)          # nur privat, nicht 50.000
    assert emob["ladung_kwh"] == pytest.approx(2000.0)   # nur privat, nicht 7.000
    assert emob["v2h_kwh"] == pytest.approx(300.0)       # Dienst-V2H raus
    # CO₂ (emob_km × 0,12) nur auf privater km-Basis
    assert ctx["co2"]["emob_kg"] == pytest.approx(10000.0 * 0.12, abs=0.1)


async def test_jahresbericht_emob_deckungsgleich_cockpit(db):
    """Bericht und Cockpit zählen dieselbe (private) E-Mob-km/Heimladung."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.services.pdf.builders.jahresbericht import (
        build_jahresbericht_context,
    )

    anlage_id = await _seed_privat_und_dienstwagen(db)

    ctx = await build_jahresbericht_context(db, anlage_id, 2025)
    ueb = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=2025, db=db)

    assert ctx["emob"]["km"] == pytest.approx(ueb.emob_km, abs=0.5)
    assert ctx["emob"]["ladung_kwh"] == pytest.approx(ueb.emob_ladung_kwh, abs=0.5)


async def test_jahresbericht_alle_dienstlich_keine_emob(db):
    """Sind ALLE Fahrzeuge dienstlich, weist der Bericht keine E-Mob aus."""
    from backend.services.pdf.builders.jahresbericht import (
        build_jahresbericht_context,
    )

    anlage = Anlage(anlagenname="Nur-Dienst", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    dienst = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Dienstwagen",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parameter={"ist_dienstlich": True},
    )
    db.add(dienst)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=dienst.id, jahr=2025, monat=1,
        verbrauch_daten={"km_gefahren": 40000, "ladung_kwh": 5000},
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       einspeisung_kwh=1000, netzbezug_kwh=2000))
    await db.commit()

    ctx = await build_jahresbericht_context(db, anlage.id, 2025)
    assert ctx["emob"]["vorhanden"] is False
    assert ctx["emob"]["km"] == 0.0
    assert ctx["co2"]["emob_kg"] == 0
