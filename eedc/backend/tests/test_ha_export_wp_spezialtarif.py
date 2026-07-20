"""DI-4 — Kennzahlen-Drift-Inventur: der HA-Export bewertet WP-Strom mit dem
WP-Spezialtarif (Fallback allgemein), nicht pauschal mit dem allgemeinen
Netzbezugspreis.

Vorher rechnete `api/routes/ha_export.py` die WP-Kosten (Anlage-Aggregat UND
per-Investition-Sensor `wp_ersparnis_euro`) mit
`strompreis.netzbezug_arbeitspreis_cent_kwh` (allgemein) — anders als
`aktueller_monat.py`, das `tarife.get("waermepumpe")` bevorzugt. Bei gepflegtem
WP-Spezialtarif (oft günstiger, §14a) war die HA-WP-Ersparnis dadurch falsch.

Fix: beide Stellen lösen den Preis über den SoT-Helper
`resolve_strompreis_for_komponente(tarife, "waermepumpe", fallback=…)` auf.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.wirtschaftlichkeit_defaults import WP_WIRKUNGSGRAD_GAS_DEFAULT
from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
    Strompreis,
)


async def _seed_wp(db, *, mit_wp_tarif: bool) -> tuple[int, int]:
    anlage = Anlage(anlagenname="WP-Tarif-Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        anschaffungskosten_gesamt=15000,
        parameter={},
    )
    db.add(wp)
    await db.flush()

    # Wärme 10.000 (Heizung 8000 + WW 2000), Strom 2.500
    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2025, monat=1,
        verbrauch_daten={"heizenergie_kwh": 8000, "warmwasser_kwh": 2000,
                         "stromverbrauch_kwh": 2500},
    ))
    # Gaspreis fix 10 ct/kWh → alte_kosten deterministisch
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       einspeisung_kwh=0, netzbezug_kwh=2500,
                       gaspreis_cent_kwh=10.0))
    # Allgemeiner Tarif 30 ct
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein",
                      gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0))
    if mit_wp_tarif:
        # WP-Spezialtarif 20 ct
        db.add(Strompreis(anlage_id=anlage.id, verwendung="waermepumpe",
                          gueltig_ab=date(2024, 1, 1),
                          netzbezug_arbeitspreis_cent_kwh=20.0,
                          einspeiseverguetung_cent_kwh=8.0))
    await db.commit()
    return anlage.id, wp.id


def _erwartete_ersparnis(wp_preis_cent: float) -> float:
    alte_kosten = 10000 / WP_WIRKUNGSGRAD_GAS_DEFAULT * 10 / 100   # Gas @ 10 ct
    wp_kosten = 2500 * wp_preis_cent / 100
    return round(alte_kosten - wp_kosten, 2)


async def _wp_ersparnis_sensor(db, anlage_id: int, wp_id: int) -> float:
    from backend.api.routes.ha_export import calculate_investition_sensors
    from backend.models import Investition as _Inv, Strompreis as _SP
    from sqlalchemy import select

    wp = (await db.execute(select(_Inv).where(_Inv.id == wp_id))).scalar_one()
    strompreis = (await db.execute(
        select(_SP).where(_SP.anlage_id == anlage_id, _SP.verwendung == "allgemein")
    )).scalar_one()
    svs = await calculate_investition_sensors(db, wp, strompreis)
    return next(s.value for s in svs if s.definition.key == "wp_ersparnis_euro")


async def test_wp_ersparnis_nutzt_spezialtarif(db):
    """Mit gepflegtem WP-Tarif (20 ct) rechnet der Sensor mit 20, nicht 30."""
    anlage_id, wp_id = await _seed_wp(db, mit_wp_tarif=True)
    value = await _wp_ersparnis_sensor(db, anlage_id, wp_id)
    assert value == pytest.approx(_erwartete_ersparnis(20.0), abs=0.05)
    # und eben NICHT der allgemeine-Tarif-Wert
    assert value != pytest.approx(_erwartete_ersparnis(30.0), abs=0.05)


async def test_wp_ersparnis_fallback_allgemein(db):
    """Ohne WP-Tarif fällt der Sensor auf den allgemeinen Tarif (30 ct) zurück."""
    anlage_id, wp_id = await _seed_wp(db, mit_wp_tarif=False)
    value = await _wp_ersparnis_sensor(db, anlage_id, wp_id)
    assert value == pytest.approx(_erwartete_ersparnis(30.0), abs=0.05)
