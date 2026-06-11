"""Symmetrie-Test: Spezifischer Ertrag HA-Export == Cockpit-Kachel.

Rainer-PN 2026-06-11: der HA-Sensor rechnete Lebenszeit-kWh ÷ heutiges kWp
(1.955 kWh/kWp bei 36 Monaten Historie), während das Cockpit saisonal
gewichtet annualisiert. Beide Pfade laufen jetzt über den SoT-Helper
``core/berechnungen/spez_ertrag.py`` — dieser Test hält sie deckungsgleich
([[feedback_aggregator_symmetrie]]).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)
from backend.models.pvgis_prognose import PVGISPrognose

# Typische 52°N-Monatsverteilung (Prozent des Jahresertrags).
SEASON_52N = {
    1: 2.5, 2: 4.5, 3: 8.0, 4: 11.5, 5: 13.0, 6: 13.5,
    7: 13.5, 8: 12.0, 9: 9.0, 10: 6.5, 11: 3.5, 12: 2.5,
}


async def test_ha_export_spez_ertrag_wie_cockpit(db):
    """3 volle Jahre à 5000 kWh auf 5 kWp → beide Pfade ~1000 kWh/kWp.

    Der alte Export-Bug hätte 15000 / 5 = 3000 kWh/kWp geliefert.
    """
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export import calculate_anlage_sensors

    anlage = Anlage(
        anlagenname="SymmetrieAnlage", leistung_kwp=5.0,
        latitude=52.0, longitude=10.0,
    )
    db.add(anlage)
    await db.flush()

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="PV-Modul",
        leistung_kwp=5.0, anschaffungsdatum=date(2023, 1, 1),
    )
    db.add(pv)
    await db.flush()

    db.add(PVGISPrognose(
        anlage_id=anlage.id,
        abgerufen_am=datetime(2025, 12, 1),
        latitude=52.0, longitude=10.0,
        neigung_grad=30.0, ausrichtung_grad=0.0,
        system_losses=14.0,
        jahresertrag_kwh=5000.0,
        spezifischer_ertrag_kwh_kwp=1000.0,
        gesamt_leistung_kwp=5.0,
        monatswerte=[
            {"monat": m, "e_m": 5000.0 * (anteil / 100.0), "h_m": 0.0, "sd_m": 0.0}
            for m, anteil in SEASON_52N.items()
        ],
        ist_aktiv=True,
    ))

    for jahr in (2023, 2024, 2025):
        for m in range(1, 13):
            db.add(InvestitionMonatsdaten(
                investition_id=pv.id, jahr=jahr, monat=m,
                verbrauch_daten={"pv_erzeugung_kwh": 5000.0 * (SEASON_52N[m] / 100.0)},
            ))
            # Monatsdaten sind Pflicht, damit calculate_anlage_sensors rechnet.
            db.add(Monatsdaten(
                anlage_id=anlage.id, jahr=jahr, monat=m,
                netzbezug_kwh=100.0, einspeisung_kwh=200.0,
            ))
    await db.commit()

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}
    export_wert = by_key["spezifischer_ertrag_kwh_kwp"].value

    assert cockpit.spezifischer_ertrag_kwh_kwp == pytest.approx(1000.0, abs=1.0)
    # Export rundet auf 0 Stellen — Toleranz 1 kWh/kWp.
    assert export_wert == pytest.approx(cockpit.spezifischer_ertrag_kwh_kwp, abs=1.0)
    # Sicherheitsnetz: alter Bug (Lebenszeit ÷ kWp) wäre ~3000.
    assert export_wert < 1500
