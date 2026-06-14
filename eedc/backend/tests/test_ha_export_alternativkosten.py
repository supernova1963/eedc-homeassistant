"""Charakterisierungs-Netz für die Alternativkosten-Ersparnis in
`calculate_anlage_sensors` (HA-Anlage-Sensoren).

`jahres_ersparnis_euro`/`roi_prozent`/`amortisation_jahre` summieren neben dem
PV-Netto-Ertrag auch die **historische Alternativkosten-Ersparnis** der
Komponenten: Wärmepumpe vs. Gas/Öl, E-Auto vs. Benzin, BKW-Eigenverbrauch. Der
E-Auto-Pfad ist bereits in `test_ha_export_multi_eauto.py` charakterisiert (inkl.
evcc-Pool-Symmetrie); WP und BKW waren ungetestet. Dieses Netz pinnt sie
**differentiell**: gleiche Anlage einmal mit, einmal ohne die Komponente —
die Delta-`jahres_ersparnis_euro` MUSS exakt der hand-gerechneten Komponenten-
Ersparnis entsprechen. Der gemeinsame Finanz-/§51-Apparat kürzt sich weg, daher
braucht der Test ihn nicht nachzurechnen.

Vorbereitung für die verhaltensneutrale Extraktion der Alternativkosten-Logik
nach `core/berechnungen/` (ADR-001, Refactoring-Plan 2026-06-14 Spur A).

Schwester-Test-Dateien des Moduls (`calculate_anlage_sensors`):
`test_ha_export_multi_eauto.py`, `test_ha_export_eigenverbrauch_imd_304.py`,
`test_ha_export_spez_ertrag_symmetrie.py`, `test_finanz_aggregat_sot_326.py`,
`test_ha_export_prognose_150.py`, `test_ha_export_preis_150.py`,
`test_eedc_prognose_kaskade.py`, `test_mqtt_publish_consolidation_655.py`.
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.ha_export import calculate_anlage_sensors
from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
    Strompreis,
)


def _sensor(sensors, key):
    return next((s for s in sensors if s.definition.key == key), None)


async def _seed_basis_anlage(db, name: str) -> Anlage:
    """Anlage mit identischer Zähler-/Preis-Grundlage, OHNE Komponenten.
    12× Monatsdaten (netzbezug 100, einspeisung 200, eigenverbrauch 50);
    keine PV-Module → PV-Erzeugung läuft über den Fallback. Diese Basis ist in
    beiden Vergleichs-Anlagen identisch, sodass sich der Finanz-Netto-Ertrag im
    Delta vollständig wegkürzt."""
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
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
    await db.flush()
    return anlage


async def _jahres_ersparnis(db, anlage: Anlage) -> float:
    sensors = await calculate_anlage_sensors(db, anlage)
    s = _sensor(sensors, "jahres_ersparnis_euro")
    assert s is not None and s.value is not None
    return s.value


async def test_wp_alternativkosten_ersparnis_pinned(db):
    """WP vs. Gas: pro Monat gas_kosten − wp_stromkosten_netz.

    Pro Monat (Default-Gas-WP, Wirkungsgrad 0,90, Gaspreis 12 ct, PV-Anteil 50 %):
        thermisch = 200 (heiz) + 50 (ww) = 250 kWh
        gas_kosten = 250 / 0,90 × 12 ct / 100 = 33,3333 €
        wp_stromkosten_netz = 80 kWh × (1−0,5) × 30 ct / 100 = 12,00 €
        Ersparnis/Monat = 21,3333 € → ×12 = 256,00 €/Jahr
    Bei 12 Monatsdaten kürzt sich die Annualisierung (÷12 ×12), also muss die
    Delta-`jahres_ersparnis_euro` exakt 256,00 € betragen."""
    basis = await _seed_basis_anlage(db, "wp-basis")
    mit_wp = await _seed_basis_anlage(db, "wp-mit")

    wp = Investition(
        anlage_id=mit_wp.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=20000.0,
        parameter={},  # Defaults: Gas, Wirkungsgrad 0,90, 12 ct, PV-Anteil 50 %
    )
    db.add(wp)
    await db.flush()
    for monat in range(1, 13):
        db.add(InvestitionMonatsdaten(
            investition_id=wp.id, jahr=2025, monat=monat,
            verbrauch_daten={
                "heizenergie_kwh": 200.0,
                "warmwasser_kwh": 50.0,
                "stromverbrauch_kwh": 80.0,
            },
        ))
    await db.flush()

    delta = await _jahres_ersparnis(db, mit_wp) - await _jahres_ersparnis(db, basis)
    assert abs(delta - 256.0) < 0.01, (
        f"WP-Alternativkosten-Beitrag zu jahres_ersparnis_euro driftet: "
        f"Delta {delta:.4f} €, erwartet 256,00 €."
    )


async def test_bkw_alternativkosten_ersparnis_pinned(db):
    """BKW-Eigenverbrauch × Netzbezugspreis, über alle erfassten Monate.

        12 × 40 kWh × 30 ct / 100 = 144,00 €/Jahr
    Annualisierung kürzt sich (12 Monate) → Delta-`jahres_ersparnis_euro` = 144 €."""
    basis = await _seed_basis_anlage(db, "bkw-basis")
    mit_bkw = await _seed_basis_anlage(db, "bkw-mit")

    bkw = Investition(
        anlage_id=mit_bkw.id, typ="balkonkraftwerk", bezeichnung="BKW",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=800.0,
        parameter={},
    )
    db.add(bkw)
    await db.flush()
    for monat in range(1, 13):
        db.add(InvestitionMonatsdaten(
            investition_id=bkw.id, jahr=2025, monat=monat,
            verbrauch_daten={"eigenverbrauch_kwh": 40.0},
        ))
    await db.flush()

    delta = await _jahres_ersparnis(db, mit_bkw) - await _jahres_ersparnis(db, basis)
    assert abs(delta - 144.0) < 0.01, (
        f"BKW-Alternativkosten-Beitrag zu jahres_ersparnis_euro driftet: "
        f"Delta {delta:.4f} €, erwartet 144,00 €."
    )


async def test_wp_oel_wirkungsgrad_und_monats_gaspreis(db):
    """Öl-Energieträger (Wirkungsgrad 0,85) + Monats-Gaspreis aus Monatsdaten
    schlagen den WP-Parameter-Default. Pro Monat:
        gas_kosten = 250 / 0,85 × 15 ct / 100 = 44,1176 €
        wp_stromkosten_netz = 80 × 0,5 × 30 ct / 100 = 12,00 €
        Ersparnis/Monat = 32,1176 € → ×12 = 385,41 €/Jahr
    Der Monats-Gaspreis (15 ct) überstimmt den Parameter-Default."""
    basis = await _seed_basis_anlage(db, "wp-oel-basis")
    anlage = Anlage(anlagenname="wp-oel", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.2,
    ))
    for monat in range(1, 13):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            netzbezug_kwh=100.0, einspeisung_kwh=200.0, eigenverbrauch_kwh=50.0,
            gaspreis_cent_kwh=15.0,
        ))
    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP-Öl",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=20000.0,
        parameter={"alter_energietraeger": "oel"},
    )
    db.add(wp)
    await db.flush()
    for monat in range(1, 13):
        db.add(InvestitionMonatsdaten(
            investition_id=wp.id, jahr=2025, monat=monat,
            verbrauch_daten={
                "heizenergie_kwh": 200.0, "warmwasser_kwh": 50.0,
                "stromverbrauch_kwh": 80.0,
            },
        ))
    await db.flush()

    delta = await _jahres_ersparnis(db, anlage) - await _jahres_ersparnis(db, basis)
    assert abs(delta - 385.41) < 0.05, (
        f"WP-Öl/Monats-Gaspreis-Beitrag driftet: Delta {delta:.4f} €, "
        f"erwartet 385,41 €."
    )
