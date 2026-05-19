"""
Akzeptanztest: aktueller_monat Komponenten-Loop attribuiert Wallbox-Pool
km-anteilig auf die E-Auto-Komponente bei evcc-Setup (#260 NongJoWo-Folge).

Hintergrund: v3.31.3 hat den Hauptwert (`emob_ersparnis_euro` aus Pool-Max)
gefixt, aber die per-Investition-Komponente im T-Konto las weiterhin
`data.get("ladung_extern_euro", 0)` aus der E-Auto-IMD — die ist bei evcc-
Portal-Import leer, weil dort die Ladedaten auf der Wallbox-IMD landen.
Folge: Pool-Tile 2676 €, E-Auto-Komponente 2949 € — Drift gleicher Sicht.

Geprüft:
  1. Helper-Logik `compute_emob_pool_attribution` + `attribute_emob_pool_by_km`
  2. Integration: evcc-Setup → E-Auto-Komponente nutzt WB-Pool-Anteile,
     ergibt dieselbe Ersparnis wie Pool-Hauptwert
  3. Premium-Setup (Daten auf E-Auto): unverändert, kein Pool-Override
  4. Multi-Car: km-anteilig
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis,
)


# ── Helper-Logik (pure) ──────────────────────────────────────────────────

def test_helper_evcc_setup_use_wb_pool_true():
    """WB hat Heimladung, E-Auto leer → use_wb_pool=True."""
    from backend.services.eauto_wirtschaftlichkeit import compute_emob_pool_attribution

    attr = compute_emob_pool_attribution(
        eauto_imd_data=[{"km_gefahren": 1000}],
        wallbox_imd_data=[{
            "ladung_kwh": 500, "ladung_pv_kwh": 200, "ladung_netz_kwh": 300,
            "ladung_extern_kwh": 50, "ladung_extern_euro": 25.0,
        }],
    )
    assert attr.use_wb_pool is True
    assert attr.wb_pool_pv == 200
    assert attr.wb_pool_netz == 300
    assert attr.wb_pool_extern_kwh == 50
    assert attr.wb_pool_extern_euro == 25.0
    assert attr.eauto_total_km == 1000


def test_helper_premium_setup_use_wb_pool_false():
    """E-Auto hat eigene Ladedaten > WB → use_wb_pool=False."""
    from backend.services.eauto_wirtschaftlichkeit import compute_emob_pool_attribution

    attr = compute_emob_pool_attribution(
        eauto_imd_data=[{
            "ladung_kwh": 500, "ladung_pv_kwh": 300, "ladung_netz_kwh": 200,
            "km_gefahren": 1000,
        }],
        wallbox_imd_data=[{
            "ladung_kwh": 100, "ladung_pv_kwh": 50, "ladung_netz_kwh": 50,
        }],
    )
    assert attr.use_wb_pool is False


def test_helper_attribute_by_km_share_single_car():
    """1 E-Auto bekommt 100 % des Pools."""
    from backend.services.eauto_wirtschaftlichkeit import (
        EmobPoolAttribution, attribute_emob_pool_by_km,
    )

    attr = EmobPoolAttribution(
        wb_pool_pv=200, wb_pool_netz=300,
        wb_pool_extern_kwh=50, wb_pool_extern_euro=25.0,
        eauto_total_km=1000, use_wb_pool=True,
    )
    share = attribute_emob_pool_by_km(attr, eauto_km=1000)
    assert share.pv_kwh == 200
    assert share.netz_kwh == 300
    assert share.extern_euro == 25.0


def test_helper_attribute_by_km_share_multi_car():
    """2 E-Autos (600/400 km) → 60/40 Aufteilung."""
    from backend.services.eauto_wirtschaftlichkeit import (
        EmobPoolAttribution, attribute_emob_pool_by_km,
    )

    attr = EmobPoolAttribution(
        wb_pool_pv=300, wb_pool_netz=200,
        wb_pool_extern_kwh=0, wb_pool_extern_euro=100.0,
        eauto_total_km=1000, use_wb_pool=True,
    )
    a = attribute_emob_pool_by_km(attr, eauto_km=600)
    b = attribute_emob_pool_by_km(attr, eauto_km=400)
    assert a.pv_kwh == 180  # 60% von 300
    assert b.pv_kwh == 120  # 40% von 300
    assert a.extern_euro == 60.0
    assert b.extern_euro == 40.0


def test_helper_pool_false_returns_zero_share():
    """use_wb_pool=False → Share ist überall 0 (Aufrufer darf bedenkenlos abrufen)."""
    from backend.services.eauto_wirtschaftlichkeit import (
        EmobPoolAttribution, attribute_emob_pool_by_km,
    )

    attr = EmobPoolAttribution(
        wb_pool_pv=200, wb_pool_netz=300,
        wb_pool_extern_kwh=0, wb_pool_extern_euro=25.0,
        eauto_total_km=1000, use_wb_pool=False,
    )
    share = attribute_emob_pool_by_km(attr, eauto_km=1000)
    assert share.pv_kwh == 0
    assert share.netz_kwh == 0
    assert share.extern_euro == 0


# ── Integration: aktueller_monat E-Auto-Komponente ─────────────────────────

async def _seed_anlage(db: AsyncSession) -> int:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0,
        einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=4,
        netzbezug_kwh=100.0, einspeisung_kwh=200.0,
    ))
    return anlage.id


def _eauto_komponente(financials, bezeichnung):
    return next((f for f in financials if f.bezeichnung == bezeichnung), None)


async def test_aktueller_monat_eauto_komponente_nutzt_wb_pool_bei_evcc(db):
    """evcc-Setup: WB hat Ladung+Extern, E-Auto hat nur km. Vor dem Fix
    rechnete die E-Auto-Komponente mit netz=0+extern=0 und zeigte volle
    Benzin-Ersparnis (2949 €). Nach dem Fix nutzt sie km-anteilig die
    Wallbox-Pool-Werte und liefert den korrekten Wert (2676 €)."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage_id = await _seed_anlage(db)
    wb = Investition(
        anlage_id=anlage_id, typ="wallbox", bezeichnung="Wallbox",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    ea = Investition(
        anlage_id=anlage_id, typ="e-auto", bezeichnung="Cupra Born",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parameter={
            "vergleich_verbrauch_l_100km": 7.0,
            "benzinpreis_euro": 1.70,
        },
    )
    db.add_all([wb, ea])
    await db.flush()

    # evcc-Pattern: Ladung + extern auf WB, nur km auf E-Auto
    db.add(InvestitionMonatsdaten(
        investition_id=wb.id, jahr=2026, monat=4,
        verbrauch_daten={
            "ladung_kwh": 500, "ladung_pv_kwh": 200, "ladung_netz_kwh": 300,
            "ladung_extern_kwh": 50, "ladung_extern_euro": 25.0,
        },
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=ea.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 1244},
    ))
    await db.commit()

    result = await get_aktueller_monat(
        anlage_id=anlage_id, jahr=2026, monat=4, db=db,
    )

    ea_komp = _eauto_komponente(result.investitionen_financials, "Cupra Born")
    assert ea_komp is not None, "E-Auto-Komponente fehlt im T-Konto"
    assert ea_komp.ersparnis_label == "Ersparnis vs. Verbrenner"

    # Erwartete Werte (km-anteilig, anteil=1.0):
    #   benzin_kosten = 1244 km / 100 × 7.0 L × 1.70 € = 148.04 €
    #   strom_heim    = 300 kWh × 30 ct/kWh / 100 = 90.00 €
    #   strom_extern  = 25.00 €
    #   ersparnis     = 148.04 − 90.00 − 25.00 = 33.04 €
    # Vor dem Fix (extern=0, netz=0): ersparnis = 148.04 €.
    assert 32 <= ea_komp.ersparnis_euro <= 34, (
        f"E-Auto-Komponente sollte ~33 € sein (Pool-attribuiert), "
        f"war {ea_komp.ersparnis_euro} € — Drift wie vor dem Fix?"
    )

    # Hauptwert (Pool) und Komponente konsistent
    assert result.emob_ersparnis_euro is not None
    assert abs(result.emob_ersparnis_euro - ea_komp.ersparnis_euro) < 1.0, (
        f"Pool-Tile {result.emob_ersparnis_euro} ≠ Komponente "
        f"{ea_komp.ersparnis_euro} (Drift gleicher Sicht)"
    )


async def test_aktueller_monat_premium_setup_unveraendert(db):
    """Premium-Setup (Daten auf E-Auto-IMD): kein Pool-Override, E-Auto
    eigene Werte bleiben gültig."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage_id = await _seed_anlage(db)
    wb = Investition(
        anlage_id=anlage_id, typ="wallbox", bezeichnung="Wallbox",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    ea = Investition(
        anlage_id=anlage_id, typ="e-auto", bezeichnung="Premium",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parameter={
            "vergleich_verbrauch_l_100km": 7.0,
            "benzinpreis_euro": 1.70,
        },
    )
    db.add_all([wb, ea])
    await db.flush()

    # E-Auto hat eigene Ladedaten (mehr als WB) → use_wb_pool=False
    db.add(InvestitionMonatsdaten(
        investition_id=wb.id, jahr=2026, monat=4,
        verbrauch_daten={"ladung_kwh": 100, "ladung_pv_kwh": 50, "ladung_netz_kwh": 50},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=ea.id, jahr=2026, monat=4,
        verbrauch_daten={
            "ladung_kwh": 500, "ladung_pv_kwh": 200, "ladung_netz_kwh": 300,
            "ladung_extern_euro": 25.0,
            "km_gefahren": 1244,
        },
    ))
    await db.commit()

    result = await get_aktueller_monat(
        anlage_id=anlage_id, jahr=2026, monat=4, db=db,
    )
    ea_komp = _eauto_komponente(result.investitionen_financials, "Premium")
    assert ea_komp is not None

    # Erwartete Ersparnis (netz=300 + extern=25, wie evcc-Test):
    #   benzin 148.04 − strom 90 − extern 25 = 33.04 €
    # Premium-Werte stimmen mit evcc-Werten überein in diesem Setup — der
    # Punkt ist, dass kein Pool-Override stattfindet.
    assert 32 <= ea_komp.ersparnis_euro <= 34


async def test_aktueller_monat_multi_car_km_anteilig(db):
    """2 E-Autos teilen sich den WB-Pool nach km."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage_id = await _seed_anlage(db)
    wb = Investition(
        anlage_id=anlage_id, typ="wallbox", bezeichnung="Wallbox",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    ea1 = Investition(
        anlage_id=anlage_id, typ="e-auto", bezeichnung="Auto A",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parameter={"vergleich_verbrauch_l_100km": 7.0, "benzinpreis_euro": 1.70},
    )
    ea2 = Investition(
        anlage_id=anlage_id, typ="e-auto", bezeichnung="Auto B",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        parameter={"vergleich_verbrauch_l_100km": 7.0, "benzinpreis_euro": 1.70},
    )
    db.add_all([wb, ea1, ea2])
    await db.flush()

    db.add(InvestitionMonatsdaten(
        investition_id=wb.id, jahr=2026, monat=4,
        verbrauch_daten={
            "ladung_kwh": 1000, "ladung_pv_kwh": 400, "ladung_netz_kwh": 600,
            "ladung_extern_euro": 50.0,
        },
    ))
    # 60/40 Aufteilung nach km
    db.add(InvestitionMonatsdaten(
        investition_id=ea1.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 600},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=ea2.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 400},
    ))
    await db.commit()

    result = await get_aktueller_monat(
        anlage_id=anlage_id, jahr=2026, monat=4, db=db,
    )
    a = _eauto_komponente(result.investitionen_financials, "Auto A")
    b = _eauto_komponente(result.investitionen_financials, "Auto B")
    assert a is not None and b is not None

    # Auto A (60 %): benzin 600/100×7×1.70=71.40 − 360×0.30=108 − 30 = -66.60
    # Auto B (40 %): benzin 400/100×7×1.70=47.60 − 240×0.30=72 − 20 = -44.40
    # Ersparnis kann auch negativ sein (mehr Strom als Benzin würde kosten).
    # Wichtig ist die 60/40-Verteilung relativ zueinander.
    assert a.ersparnis_euro is not None and b.ersparnis_euro is not None
    assert abs(a.ersparnis_euro / 1.5 - b.ersparnis_euro) < 1.0, (
        f"Verhältnis sollte ~1.5:1 sein (km-Anteil 60:40), "
        f"war Auto A={a.ersparnis_euro}, Auto B={b.ersparnis_euro}"
    )
