"""Charakterisierung des `wp_ersparnis_euro`-Sensors in
`calculate_investition_sensors` (HA-Export, per-WP).

Pinnt den Wert VOR der Migration der Altanlagen-Gaskosten-Formel auf den
SoT-Helper `gas_kosten_altanlage`. Dieser per-WP-Sensor verwendet bewusst
die VOLLEN WP-Stromkosten (ohne PV-Anteil-Split) — anderer WP-Kosten-Term
als die Aggregat-Alternativkosten; nur die Gaskosten-Teilformel ist geteilt.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.ha_export import calculate_investition_sensors
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten


def _sensor(sensors, key):
    return next((s for s in sensors if s.definition.key == key), None)


async def test_wp_ersparnis_euro_sensor_wert_gepinnt(db):
    """Ein Monat: Wärme 1000 (Heiz 800 + WW 200), WP-Strom 300, Gaspreis 10 ct,
    Gas-η 0,90, Zusatzkosten 120 €/Jahr, Netzbezug 30 ct (Default ohne Tarif).

      alte_kosten = (1000 / 0,90) * 10 / 100 + 120 * 1/12 = 111,111 + 10 = 121,111 €
      wp_kosten   = 300 * 30 / 100                          =  90,000 €
      ersparnis                                             =  31,111… €

    Der Produzent liefert seit P-4 **ungerundet** — gerundet wird erst an der
    Export-Grenze (`SensorExportItem` bzw. `publish_sensor`), wo aus dieser
    Zahl die ausgelieferten 31,11 € werden. Gepinnt ist hier die Formel, nicht
    die Darstellung; die Rundung deckt `test_export_rundung_rest_mqtt_gleich`.
    """
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=1,
        netzbezug_kwh=0.0, einspeisung_kwh=0.0, gaspreis_cent_kwh=10.0,
    ))
    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Test-WP",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=12000.0,
        parameter={
            "alter_energietraeger": "gas",
            "alternativ_zusatzkosten_jahr": 120.0,
        },
    )
    db.add(wp)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2026, monat=1,
        verbrauch_daten={
            "heizenergie_kwh": 800.0,
            "warmwasser_kwh": 200.0,
            "stromverbrauch_kwh": 300.0,
        },
    ))
    await db.flush()

    sensors = await calculate_investition_sensors(db, wp, None)
    s = _sensor(sensors, "wp_ersparnis_euro")
    assert s is not None
    assert s.value == pytest.approx(31.1111, abs=0.0001)
