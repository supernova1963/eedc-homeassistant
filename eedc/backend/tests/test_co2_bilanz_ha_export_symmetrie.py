"""DI-2 — Kennzahlen-Drift-Inventur: der HA-Export-Sensor „CO2 Einsparung"
trägt die volle Cockpit-CO₂-Bilanz (PV-Eigenverbrauch + WP + E-Mobilität).

Vorher rechnete `api/routes/ha_export.py` nur `pv_erzeugung × 0,38` — WP und
E-Mobilität fehlten ganz, und die PV-Basis war die Erzeugung statt des
Eigenverbrauchs. Gernot-Entscheid (2026-07-20): Sensor liefert künftig den
App-Headline-Wert (Cockpit-Konvention). Umgesetzt über den kanonischen Helper
`berechne_co2_bilanz` (ADR-001), den auch das Cockpit nutzt.

Symmetrie-Test: für eine Anlage mit PV + WP + E-Auto liefern Cockpit-Übersicht
und HA-Export denselben CO₂-Gesamtwert.

DI-2-B (2026-07-20) hat die breitere HA-Export↔Cockpit-Drift geschlossen: die
Eigenverbrauchs-Aggregation zählte NUR `pv-module` zur Erzeugung — Balkonkraft-
werk und sonstige Erzeuger (Mini-BHKW hinter dem EINEN Hauszähler) fehlten, so
dass Eigenverbrauch/Autarkie/EV-Quote und der daraus abgeleitete CO₂-Sensor bei
solchen Anlagen vom Cockpit abwichen. Der HA-Export nutzt jetzt dieselbe
Netzpunkt-Bilanz (`erzeugung_hinter_zaehler_kwh`, v3.45.4) wie das Cockpit;
`test_cockpit_ha_export_kennzahlen_symmetrisch_mit_bkw_bhkw` deckt das ab.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.calculations import (
    CO2_FAKTOR_BENZIN_KG_LITER,
    CO2_FAKTOR_STROM_KG_KWH,
    berechne_co2_bilanz,
    co2_wp_ersparnis_kg,
)
from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
)


# ── Helper-Kontrakt: Gesamt = PV(EV) + max(0,WP) + max(0,E-Mob) ──────────────

def test_berechne_co2_bilanz_komposition():
    b = berechne_co2_bilanz(
        eigenverbrauch_kwh=1000.0,
        wp_waerme_kwh=12000.0, wp_strom_kwh=3000.0,
        emob_km=10000.0, emob_netz_ladung_kwh=1000.0,
        benzin_verbrauch_liter=750.0,
    )
    assert b.co2_pv_kg == pytest.approx(1000.0 * CO2_FAKTOR_STROM_KG_KWH)
    assert b.co2_wp_kg == pytest.approx(co2_wp_ersparnis_kg(12000.0, 3000.0))
    assert b.co2_emob_kg == pytest.approx(
        750.0 * CO2_FAKTOR_BENZIN_KG_LITER - 1000.0 * CO2_FAKTOR_STROM_KG_KWH
    )
    assert b.co2_gesamt_kg == pytest.approx(
        b.co2_pv_kg + max(0.0, b.co2_wp_kg) + max(0.0, b.co2_emob_kg)
    )


def test_berechne_co2_bilanz_klammert_negative_komponenten():
    """Negative WP-/E-Mob-Komponenten dürfen die Gesamtbilanz nicht drücken."""
    b = berechne_co2_bilanz(
        eigenverbrauch_kwh=500.0,
        wp_waerme_kwh=1000.0, wp_strom_kwh=3000.0,   # schlechte JAZ → co2_wp < 0
        emob_km=1000.0, emob_netz_ladung_kwh=5000.0,  # viel Netz → co2_emob < 0
        benzin_verbrauch_liter=10.0,
    )
    assert b.co2_wp_kg < 0 and b.co2_emob_kg < 0
    assert b.co2_gesamt_kg == pytest.approx(500.0 * CO2_FAKTOR_STROM_KG_KWH)


def test_co2_emob_nur_bei_gefahrenen_km():
    b = berechne_co2_bilanz(
        eigenverbrauch_kwh=0.0, emob_km=0.0,
        emob_netz_ladung_kwh=500.0, benzin_verbrauch_liter=100.0,
    )
    assert b.co2_emob_kg == 0.0


# ── Cross-Endpoint-Symmetrie: Cockpit == HA-Export ──────────────────────────

async def _seed_pv_wp_emob(db) -> int:
    """Anlage mit PV + WP + E-Auto (KEIN Balkonkraftwerk, s. Modul-Doc)."""
    anlage = Anlage(anlagenname="CO2-Bilanz-Symmetrie", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="PV",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    ea = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Auto",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    db.add_all([pv, wp, ea])
    await db.flush()

    # Zählerwerte (für Eigenverbrauch): PV 5000, Einspeisung 3000, Netzbezug 1500
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=1,
        einspeisung_kwh=3000, netzbezug_kwh=1500,
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2025, monat=1,
        verbrauch_daten={"pv_erzeugung_kwh": 5000},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2025, monat=1,
        verbrauch_daten={"heizung_kwh": 10000, "warmwasser_kwh": 2000,
                         "stromverbrauch_kwh": 3000},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=ea.id, jahr=2025, monat=1,
        verbrauch_daten={"km_gefahren": 15000, "ladung_kwh": 2500,
                         "ladung_pv_kwh": 1000, "ladung_netz_kwh": 1500},
    ))
    await db.commit()
    return anlage.id


async def test_cockpit_ha_export_co2_symmetrisch(db):
    """Cockpit-Übersicht und HA-Export-Sensor „CO2 Einsparung" liefern für
    dieselbe Anlage (PV + WP + E-Auto) denselben CO₂-Gesamtwert."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export import calculate_anlage_sensors
    from backend.models import Anlage as _Anlage
    from sqlalchemy import select

    anlage_id = await _seed_pv_wp_emob(db)

    ueb = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)

    anlage = (await db.execute(
        select(_Anlage).where(_Anlage.id == anlage_id)
    )).scalar_one()
    svs = await calculate_anlage_sensors(db, anlage)
    co2_sensor = next(s for s in svs if s.definition.key == "co2_ersparnis_kg")

    assert ueb.co2_gesamt_kg > 0
    assert co2_sensor.value == pytest.approx(ueb.co2_gesamt_kg, abs=0.1)


# ── DI-2-B: HA-Export == Cockpit bei Balkonkraftwerk + sonstigem Erzeuger ────

async def _seed_bkw_bhkw(db) -> int:
    """Anlage mit PV + Balkonkraftwerk + sonstigem Erzeuger (Mini-BHKW).

    Alle drei speisen hinter den EINEN Hauszähler → ihre Erzeugung gehört in
    die Eigenverbrauchs-/Autarkie-Bilanz (Netzpunkt-Bilanz)."""
    anlage = Anlage(anlagenname="BKW-BHKW-Symmetrie", leistung_kwp=8.0)
    db.add(anlage)
    await db.flush()

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="PV",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
                      anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    bhkw = Investition(anlage_id=anlage.id, typ="sonstiges", bezeichnung="Mini-BHKW",
                       parameter={"kategorie": "erzeuger"},
                       anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    db.add_all([pv, bkw, bhkw])
    await db.flush()

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=1,
        einspeisung_kwh=2000, netzbezug_kwh=1200,
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2025, monat=1,
        verbrauch_daten={"pv_erzeugung_kwh": 4000},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=bkw.id, jahr=2025, monat=1,
        verbrauch_daten={"pv_erzeugung_kwh": 800, "eigenverbrauch_kwh": 700},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=bhkw.id, jahr=2025, monat=1,
        verbrauch_daten={"erzeugung_kwh": 1500},
    ))
    await db.commit()
    return anlage.id


async def test_cockpit_ha_export_kennzahlen_symmetrisch_mit_bkw_bhkw(db):
    """DI-2-B: Bei Balkonkraftwerk + sonstigem Erzeuger liefern Cockpit und
    HA-Export dieselbe PV-Erzeugung (inkl. BKW), Eigenverbrauch, Autarkie,
    EV-Quote und CO₂-Bilanz — die Netzpunkt-Erzeugung geht in beide Bilanzen."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export import calculate_anlage_sensors
    from backend.models import Anlage as _Anlage
    from sqlalchemy import select

    anlage_id = await _seed_bkw_bhkw(db)

    ueb = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    anlage = (await db.execute(
        select(_Anlage).where(_Anlage.id == anlage_id)
    )).scalar_one()
    svs = {s.definition.key: s.value for s in await calculate_anlage_sensors(db, anlage)}

    # BKW zählt zur PV-Erzeugung (Cockpit-Konvention), BHKW nicht.
    assert svs["pv_erzeugung_gesamt_kwh"] == pytest.approx(ueb.pv_erzeugung_kwh, abs=0.1)
    assert svs["eigenverbrauch_gesamt_kwh"] == pytest.approx(ueb.eigenverbrauch_kwh, abs=0.1)
    assert svs["autarkie_prozent"] == pytest.approx(ueb.autarkie_prozent, abs=0.1)
    assert svs["eigenverbrauch_quote_prozent"] == pytest.approx(
        ueb.eigenverbrauch_quote_prozent, abs=0.1
    )
    assert svs["co2_ersparnis_kg"] == pytest.approx(ueb.co2_gesamt_kg, abs=0.1)
    # Die Erzeuger hinter dem Zähler heben den Eigenverbrauch über die reine
    # PV-Modul-Bilanz — sonst würde der Test die Drift nicht fangen.
    assert ueb.eigenverbrauch_kwh > 4000 - 2000
