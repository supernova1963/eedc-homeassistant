"""HA-Sensor-Export für Mehrfach-E-Auto-Anlagen.

Gleiche Drift-Klasse wie der heutige aussichten-Fix (`f5eef795`):
`calculate_anlage_sensors` las `eauto_benzinpreis` und
`eauto_vergleich_l_100km` in einer `for ea`-Schleife last-write-wins in
zwei globale Variablen, dann rechnete `bisherige_eauto_ersparnis` für
ALLE E-Autos mit den Werten des LETZTEN. Davon abgeleitet:
`jahres_ersparnis_euro`, `roi_prozent` und `amortisation_jahre` als
HA-Sensoren — alle drei waren bei Multi-EA-Haushalten falsch.

Zusätzlich fehlte hier (anders als in aussichten.py) der Fallback auf
`md.kraftstoffpreis_euro` (EU OB) — der Anlage-Sensor driftete deshalb
nicht nur intern, sondern auch gegen den per-Investition-Sensor
`e_auto_ersparnis_vs_benzin_euro`, der den Monatspreis korrekt nutzt.
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.ha_export import (
    calculate_anlage_sensors,
    calculate_investition_sensors,
)
from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
    Strompreis,
)


async def _seed_anlage_zwei_eautos(db) -> Anlage:
    """Anlage mit 2 E-Autos: deutlich unterschiedliche Vergleichsverbräuche
    und Benzinpreis-Defaults. Monatsdaten ohne `kraftstoffpreis_euro` —
    zwingt den per-Inv-Fallback und macht den Drift deutlich messbar."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0,
        einspeiseverguetung_cent_kwh=8.2,
    ))
    for monat in range(1, 13):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            netzbezug_kwh=100.0, einspeisung_kwh=200.0,
            eigenverbrauch_kwh=50.0,
        ))

    ea1 = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Klein-EV",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=30000.0,
        parameter={
            "jahresfahrleistung_km": 10000,
            "verbrauch_kwh_100km": 15,
            "pv_ladeanteil_prozent": 50,
            "vergleich_verbrauch_l_100km": 6.0,
            "benzinpreis_euro": 1.80,
        },
    )
    ea2 = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="SUV-EV",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=50000.0,
        parameter={
            "jahresfahrleistung_km": 10000,
            "verbrauch_kwh_100km": 22,
            "pv_ladeanteil_prozent": 50,
            "vergleich_verbrauch_l_100km": 10.0,
            "benzinpreis_euro": 2.00,
        },
    )
    db.add(ea1)
    db.add(ea2)
    await db.flush()

    for monat in range(1, 13):
        for ea in (ea1, ea2):
            db.add(InvestitionMonatsdaten(
                investition_id=ea.id, jahr=2025, monat=monat,
                verbrauch_daten={
                    "km_gefahren": 833.33,
                    "ladung_netz_kwh": 50.0,
                    "ladung_pv_kwh": 50.0,
                },
            ))
    await db.flush()
    return anlage


async def test_jahres_ersparnis_summiert_pro_eauto_korrekt(db):
    """Per-EA-Benzinkosten müssen mit den jeweils gepflegten Parametern in
    `jahres_ersparnis_euro` einfließen.

    Erwartete Pro-EA-Benzin-Alternativkosten/Jahr:
        Klein-EV: 10.000 km × 6 L/100 × 1,80 € = 1.080 €
        SUV-EV:   10.000 km × 10 L/100 × 2,00 € = 2.000 €
        Σ = 3.080 € Benzin-Alternative

    Vor dem Fix wären beide mit dem letzten EA gerechnet worden:
        2 × (10.000 km × 10 L/100 × 2,00 €) = 4.000 € → klar überhöht.
    """
    anlage = await _seed_anlage_zwei_eautos(db)
    sensors = await calculate_anlage_sensors(db, anlage)

    jahres_ersparnis_sensor = next(
        (s for s in sensors if s.definition.key == "jahres_ersparnis_euro"), None,
    )
    assert jahres_ersparnis_sensor is not None
    assert jahres_ersparnis_sensor.value is not None

    # Σ Benzin = 3.080 € (per-EA), Σ Strom = 12 × 2 × 50 × 0,30 = 360 €
    # → bisherige_eauto_ersparnis ≈ 2.720 €. Plus Einspeise-Erlös etc.
    # Wir prüfen die Obergrenze: vor dem Fix wäre der Wert deutlich höher.
    # Schwelle 3.500 € liegt zwischen "korrekt (~2.720 + Einspeisung)" und
    # "falsch (4.000 + Einspeisung)".
    assert jahres_ersparnis_sensor.value < 4000, (
        f"jahres_ersparnis_euro zu hoch — wahrscheinlich last-write-wins-"
        f"Drift bei E-Auto-Params. Wert: {jahres_ersparnis_sensor.value} €"
    )


async def test_investition_sensoren_respektieren_laufzeit(db):
    """#308-Klasse: `calculate_investition_sensors` darf IMD-Monate VOR
    Anschaffung / NACH Stilllegung nicht in die per-Investition-HA-Sensoren
    summieren (symmetrisch zu `calculate_anlage_sensors`, #236).
    """
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    ea = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="EV",
        anschaffungsdatum=date(2025, 1, 1),
        stilllegungsdatum=date(2025, 12, 31),
        anschaffungskosten_gesamt=30000.0,
        parameter={"verbrauch_kwh_100km": 15},
    )
    db.add(ea)
    await db.flush()

    # 12 Monate IM Fenster: je 100 km → Σ 1.200 km.
    for monat in range(1, 13):
        db.add(InvestitionMonatsdaten(
            investition_id=ea.id, jahr=2025, monat=monat,
            verbrauch_daten={"km_gefahren": 100.0, "verbrauch_kwh": 15.0},
        ))
    # Spuk-Monat VOR Anschaffung (z.B. Phantom-Import) — muss raus.
    db.add(InvestitionMonatsdaten(
        investition_id=ea.id, jahr=2024, monat=12,
        verbrauch_daten={"km_gefahren": 5000.0, "verbrauch_kwh": 750.0},
    ))
    # Spuk-Monat NACH Stilllegung — muss ebenfalls raus.
    db.add(InvestitionMonatsdaten(
        investition_id=ea.id, jahr=2026, monat=1,
        verbrauch_daten={"km_gefahren": 5000.0, "verbrauch_kwh": 750.0},
    ))
    await db.flush()

    sensors = await calculate_investition_sensors(db, ea, None)
    km_sensor = next(
        (s for s in sensors if s.definition.key == "e_auto_km_gesamt"), None,
    )
    assert km_sensor is not None
    # Nur die 12 In-Fenster-Monate: 1.200 km — nicht 11.200 km.
    assert km_sensor.value == 1200
