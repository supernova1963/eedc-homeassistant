"""Phase 2a — Pflicht-Symmetrie-Test: alle E-Mob-Read-Sites liefern für
dieselbe Anlage denselben Heimladungs-Wert.

Hintergrund (`docs/KONZEPT-WALLBOX-EAUTO.md`, Etappe 2): die Heimladungs-Quelle
wurde von einer datenabhängigen Magnituden-Heuristik (`wb >= ea`) auf eine
strukturelle Regel (Wallbox vorhanden + hat Heimladung → Wallbox) umgestellt.
Jede Read-Site routet ihre Quellen-Entscheidung über genau EINEN von zwei
Helfern — `get_emob_heimladung_canonical` (Aggregat-Sichten) oder
`compute_emob_pool_attribution` + km-Attribution (E-Auto-Sichten). Dieser Test
sichert ab, dass beide Pfade dieselbe Zahl ergeben — sonst stille Drift zwischen
Cockpit, Dashboards, Monatsbericht, HA-Export und PDF.

Zwei Ebenen:
  A. Helfer-Kontrakt (pur): die beiden Quellen-Helfer entscheiden identisch,
     und die km-Attribution erhält den Heimladungs-Gesamtwert.
  B. Cross-Endpoint: ein evcc-Setup (Ladung auf der Wallbox) ergibt dieselbe
     Heimladung im Wallbox-Dashboard, E-Auto-Dashboard (Σ) und aktueller_monat.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen import (
    QUELLE_GEMESSEN,
    QUELLE_KEINE,
    QUELLE_LADUNG,
    eauto_effizienz_100km,
)
from backend.models import Anlage, Investition, InvestitionMonatsdaten
from backend.services.eauto_wirtschaftlichkeit import (
    attribute_emob_pool_by_km,
    compute_emob_pool_attribution,
    get_emob_heimladung_canonical,
)


# ── A. Helfer-Kontrakt: beide Quellen-Helfer entscheiden identisch ──────────

# (label, eauto_imd, wallbox_imd, erwartete_quelle)
_FIXTURES = [
    (
        "evcc_ladung_auf_wallbox",
        [{"km_gefahren": 1000}],
        [{"ladung_kwh": 500, "ladung_pv_kwh": 300, "ladung_netz_kwh": 200}],
        "wallbox",
    ),
    (
        "dual_daten_unmigriert_eauto_groesser",
        [{"ladung_kwh": 3300, "ladung_pv_kwh": 1000, "ladung_netz_kwh": 2300,
          "km_gefahren": 1000}],
        [{"ladung_kwh": 500, "ladung_pv_kwh": 200, "ladung_netz_kwh": 300}],
        "wallbox",   # strukturell: Wallbox gewinnt trotz kleinerer Ladung
    ),
    (
        "steckerlader_keine_wallbox",
        [{"ladung_kwh": 800, "ladung_pv_kwh": 500, "ladung_netz_kwh": 300,
          "km_gefahren": 1200}],
        [],
        "e-auto",
    ),
    (
        "wallbox_ohne_heimladung",
        [{"ladung_kwh": 400, "ladung_pv_kwh": 250, "ladung_netz_kwh": 150,
          "km_gefahren": 900}],
        [{"ladung_kwh": 0}],
        "e-auto",
    ),
]


@pytest.mark.parametrize("label,eauto_imd,wb_imd,erwartete_quelle", _FIXTURES)
def test_quellen_helfer_entscheiden_identisch(label, eauto_imd, wb_imd, erwartete_quelle):
    """`get_emob_heimladung_canonical` und `compute_emob_pool_attribution`
    wählen für dieselben Daten dieselbe Quelle (Wallbox ⟺ use_wb_pool)."""
    canonical = get_emob_heimladung_canonical(
        eauto_imd_data=eauto_imd, wallbox_imd_data=wb_imd,
    )
    attr = compute_emob_pool_attribution(
        eauto_imd_data=eauto_imd, wallbox_imd_data=wb_imd,
    )
    assert canonical.quelle == erwartete_quelle, label
    assert attr.use_wb_pool is (erwartete_quelle == "wallbox"), label
    # Trias-Garantie der kanonischen Quelle
    assert abs(canonical.pv_kwh + canonical.netz_kwh - canonical.ladung_kwh) < 1e-9


def test_km_attribution_erhaelt_heimladungs_gesamtwert():
    """Wenn die Wallbox die Quelle ist, summieren sich die km-anteiligen
    E-Auto-Shares exakt zum kanonischen Heimladungs-Gesamtwert (keine Leckage)."""
    eauto_imd = [{"km_gefahren": 600}, {"km_gefahren": 400}]
    wb_imd = [{"ladung_kwh": 500, "ladung_pv_kwh": 300, "ladung_netz_kwh": 200}]

    canonical = get_emob_heimladung_canonical(
        eauto_imd_data=eauto_imd, wallbox_imd_data=wb_imd,
    )
    attr = compute_emob_pool_attribution(
        eauto_imd_data=eauto_imd, wallbox_imd_data=wb_imd,
    )
    assert attr.use_wb_pool is True

    summe_pv = sum(
        attribute_emob_pool_by_km(attr, d["km_gefahren"]).pv_kwh for d in eauto_imd
    )
    summe_netz = sum(
        attribute_emob_pool_by_km(attr, d["km_gefahren"]).netz_kwh for d in eauto_imd
    )
    assert abs(summe_pv - canonical.pv_kwh) < 1e-9
    assert abs(summe_netz - canonical.netz_kwh) < 1e-9
    assert abs(summe_pv + summe_netz - canonical.ladung_kwh) < 1e-9


# ── B. Cross-Endpoint: dieselbe Anlage, dieselbe Heimladung ─────────────────

async def _seed_evcc_anlage(db) -> int:
    """evcc-Setup: Wallbox trägt 500 kWh (PV 300 / Netz 200), zwei E-Autos
    tragen nur km (600 / 400) — wie nach Phase-2a-Migration / evcc-Import."""
    anlage = Anlage(anlagenname="Symmetrie", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    wb = Investition(
        anlage_id=anlage.id, typ="wallbox", bezeichnung="SMA eCharger",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    ea1 = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Auto A",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    ea2 = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Auto B",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    db.add_all([wb, ea1, ea2])
    await db.flush()

    db.add(InvestitionMonatsdaten(
        investition_id=wb.id, jahr=2026, monat=4,
        verbrauch_daten={"ladung_kwh": 500, "ladung_pv_kwh": 300, "ladung_netz_kwh": 200},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=ea1.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 600},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=ea2.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 400},
    ))
    await db.commit()
    return anlage.id


async def test_cross_endpoint_heimladung_symmetrisch(db):
    """Wallbox-Dashboard, E-Auto-Dashboard (Σ) und aktueller_monat liefern für
    dieselbe evcc-Anlage dieselbe Heimladung (500 / PV 300 / Netz 200).
    Heimladung ist reine Energie → preis-/tarifunabhängig vergleichbar."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.investitionen import (
        get_eauto_dashboard,
        get_wallbox_dashboard,
    )

    anlage_id = await _seed_evcc_anlage(db)

    # Wallbox-Dashboard (1 Wallbox = ganze Anlage)
    wb_dash = await get_wallbox_dashboard(anlage_id=anlage_id, strompreis_cent=30.0, db=db)
    assert len(wb_dash) == 1
    wb_z = wb_dash[0].zusammenfassung
    assert wb_z["gesamt_heim_ladung_kwh"] == 500.0
    assert wb_z["ladung_pv_kwh"] == 300.0
    assert wb_z["ladung_netz_kwh"] == 200.0

    # E-Auto-Dashboard: Σ über beide Autos (km-anteilig 60/40)
    ea_dash = await get_eauto_dashboard(anlage_id=anlage_id, strompreis_cent=30.0, db=db)
    summe_heim = sum(r.zusammenfassung["ladung_heim_kwh"] for r in ea_dash)
    summe_pv = sum(r.zusammenfassung["ladung_pv_kwh"] for r in ea_dash)
    summe_netz = sum(r.zusammenfassung["ladung_netz_kwh"] for r in ea_dash)
    assert abs(summe_heim - 500.0) < 0.2
    assert abs(summe_pv - 300.0) < 0.2
    assert abs(summe_netz - 200.0) < 0.2

    # aktueller_monat (Anlage-KPI)
    am = await get_aktueller_monat(anlage_id=anlage_id, jahr=2026, monat=4, db=db)
    assert abs(am.emob_ladung_kwh - 500.0) < 0.2
    assert abs(am.emob_ladung_pv_kwh - 300.0) < 0.2
    assert abs(am.emob_ladung_netz_kwh - 200.0) < 0.2


# ── C. Ø Verbrauch (kWh/100 km) — Helper-Unit + Read-Site-Symmetrie ─────────

@pytest.mark.parametrize("verbrauch,ladung,km,erw_wert,erw_quelle", [
    (4000.0, 5000.0, 20000.0, 20.0, QUELLE_GEMESSEN),   # gemessen hat Vorrang
    (0.0, 5276.8, 24416.0, 21.6, QUELLE_LADUNG),        # leer → Ladungs-Näherung (Gernot)
    (0.0, 0.0, 24416.0, None, QUELLE_KEINE),            # keine Energie-Basis
    (0.0, 5000.0, 0.0, None, QUELLE_KEINE),             # km = 0 → nie 0,0 erfinden
])
def test_eauto_effizienz_helper(verbrauch, ladung, km, erw_wert, erw_quelle):
    """Helper-Kontrakt: gemessener Fahrverbrauch > Ladungs-Näherung > keine Basis."""
    eff = eauto_effizienz_100km(verbrauch, ladung, km)
    assert eff.quelle == erw_quelle
    if erw_wert is None:
        assert eff.wert is None
    else:
        assert eff.wert == pytest.approx(erw_wert, abs=0.05)


async def test_cross_endpoint_verbrauch_100km_symmetrisch(db):
    """Ohne Verbrauchssensor (verbrauch_kwh leer) liefern E-Auto-Dashboard,
    aktueller_monat, Komponenten-Aggregat UND Cockpit-Übersicht denselben
    Ø Verbrauch aus der Ladungs-Näherung — kein 0,0 mehr im E-Auto-Dashboard
    (Anlass 2026-06-05: drei Karten, zwei Formeln). km=1000, Ladung=500 →
    50,0 kWh/100 km, Quelle 'ladung' in allen vier Read-Sites."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.investitionen import get_eauto_dashboard

    anlage_id = await _seed_evcc_anlage(db)

    # E-Auto-Dashboard: jede Auto-Karte fällt auf Σ Ladung / Σ km zurück (= 50)
    ea_dash = await get_eauto_dashboard(anlage_id=anlage_id, strompreis_cent=30.0, db=db)
    for r in ea_dash:
        assert r.zusammenfassung["verbrauch_quelle"] == "ladung"
        assert r.zusammenfassung["durchschnitt_verbrauch_kwh_100km"] == pytest.approx(50.0, abs=0.2)

    # aktueller_monat (Monatsbericht-Quelle)
    am = await get_aktueller_monat(anlage_id=anlage_id, jahr=2026, monat=4, db=db)
    assert am.emob_verbrauch_quelle == "ladung"
    assert am.emob_verbrauch_100km == pytest.approx(50.0, abs=0.2)

    # Komponenten-Aggregat (Auswertungen → Komponenten)
    komp = await get_komponenten_zeitreihe(anlage_id=anlage_id, jahr=None, db=db)
    assert komp.emob_verbrauch_quelle_gesamt == "ladung"
    assert komp.emob_verbrauch_100km_gesamt == pytest.approx(50.0, abs=0.2)

    # Cockpit-Übersicht
    ueb = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    assert ueb.emob_verbrauch_quelle == "ladung"
    assert ueb.emob_verbrauch_100km == pytest.approx(50.0, abs=0.2)
