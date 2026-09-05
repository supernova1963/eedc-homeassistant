"""B5 (05.09.2026) — der HA-Export je Wärmepumpe sagt dasselbe wie der Hub.

Matrix-Durchgang Paket 5 über dieselben Sprossen wie B3/B4 (SOLL Wärme/Klima
§3.2a, §3.3 S1): Arbeitszahl, Ersparnis, Strom je Betriebsart und der Vorbehalt
an der Ersparnis müssen im Export-Sensor und in der Hub-Zusammenfassung
übereinstimmen — je Sprosse, nicht nur im Normalfall.

Gemessen vor dem Bau: F8 (Kühlstrom 300 kWh) Export 10 € gegen Hub 100 € —
der Export rechnete die Ersparnis selbst, ohne den Kühlstrom-Abzug (E-B).

Schwesterdateien: test_b3_hub_matrix.py (die Sprossen, Hub gegen Cockpit),
test_b4_cockpit_matrix.py (Monat gegen Jahr), test_b5_ersparnis_symmetrie.py
(Tarif je Monat, Zusatzkosten, drei Sichten).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: F401
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung  # noqa: F401
from backend.tests.test_b3_hub_matrix import SPROSSEN, JAHR, MONAT


async def _aufbau(db, name, parameter, daten, prov):
    a = Anlage(anlagenname=name, leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(a)
    await db.flush()
    inv = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="Wärmepumpe",
                      anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
                      parameter=parameter)
    db.add(inv)
    await db.flush()
    if daten is not None:
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR, monat=MONAT,
                                      verbrauch_daten=daten, source_provenance=prov or {}))
    tarif = Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30.0,
                       einspeiseverguetung_cent_kwh=8.0, gueltig_ab=date(2025, 1, 1))
    db.add(tarif)
    await db.commit()
    return a, inv, tarif


def _wert(export, key):
    sv = export.get(key)
    return None if sv is None else sv.value


def _rund(x):
    return None if x is None else round(x, 2)


# Export-Schlüssel → Hub-Schlüssel, für dieselbe Größe.
MODUS_PAARE = (
    ("wp_strom_heizen_modus_kwh", "modus_strom_heizen_kwh"),
    ("wp_strom_kuehlen_modus_kwh", "modus_strom_kuehlen_kwh"),
    ("wp_strom_warmwasser_modus_kwh", "modus_strom_warmwasser_kwh"),
)


@pytest.mark.asyncio
@pytest.mark.parametrize("sprosse", list(SPROSSEN))
async def test_export_und_hub_sagen_dasselbe(db, sprosse):
    from backend.api.routes.ha_export import calculate_investition_sensors
    from backend.api.routes.investitionen.dashboards import get_waermepumpe_dashboard

    parameter, daten, prov = SPROSSEN[sprosse]
    a, inv, tarif = await _aufbau(db, sprosse, parameter, daten, prov)
    export = {sv.definition.key: sv for sv in await calculate_investition_sensors(db, inv, tarif)}
    hub = (await get_waermepumpe_dashboard(a.id, strompreis_cent=30.0, db=db))[0].zusammenfassung

    # Arbeitszahl: gleicher Wert, und gesperrt ist gesperrt (beide leer).
    assert _rund(_wert(export, "wp_cop_durchschnitt")) == _rund(hub.get("durchschnitt_cop")), sprosse
    # Ersparnis: gleicher Wert — inkl. E-B (F8) und N-88 (leer bleibt leer).
    assert _rund(_wert(export, "wp_ersparnis_euro")) == _rund(hub.get("ersparnis_euro")), sprosse
    # Vorbehalt: dieselben Worte, als Attribut.
    sv = export.get("wp_ersparnis_euro")
    vorbehalt = (sv.zusatz_attribute or {}).get("vorbehalt") if sv is not None else None
    assert vorbehalt == hub.get("ersparnis_vorbehalt"), sprosse
    # Strom je Betriebsart: wo der Export einen Sensor liefert, ist es die Hub-Zahl.
    for ex_key, hub_key in MODUS_PAARE:
        if ex_key in export:
            assert _rund(export[ex_key].value) == _rund(hub.get(hub_key)), (sprosse, ex_key)


@pytest.mark.asyncio
async def test_f8_der_kuehlstrom_steht_nicht_im_vergleich_und_die_berechnung_sagt_es(db):
    """E-B im Export: 400 € (alt) − 300 € (WP ohne Kühlstrom) = 100 €, nicht 10 €."""
    from backend.api.routes.ha_export import calculate_investition_sensors

    parameter, daten, prov = SPROSSEN["F8_kaeltemenge"]
    a, inv, tarif = await _aufbau(db, "f8", parameter, daten, prov)
    export = {sv.definition.key: sv for sv in await calculate_investition_sensors(db, inv, tarif)}
    sv = export["wp_ersparnis_euro"]
    assert sv.value == pytest.approx(100.0, abs=0.01)
    assert "Kühlstrom" in (sv.berechnung or "")


@pytest.mark.asyncio
async def test_f2b_und_f12_tragen_den_vorbehalt_als_attribut_und_hinweis(db):
    from backend.api.routes.ha_export import SensorExportItem, calculate_investition_sensors

    for sprosse, erwartet in (
        ("F2b_gesamtstrom_plus_schaetzung", "Wärme geschätzt"),
        ("F12_bivalent", "zweiter Erzeuger"),
    ):
        parameter, daten, prov = SPROSSEN[sprosse]
        a, inv, tarif = await _aufbau(db, sprosse, parameter, daten, prov)
        export = {sv.definition.key: sv for sv in await calculate_investition_sensors(db, inv, tarif)}
        sv = export["wp_ersparnis_euro"]
        assert erwartet in sv.zusatz_attribute["vorbehalt"], sprosse
        # REST trägt denselben Satz als `hinweis`.
        from backend.api.routes.ha_export import _hinweis
        item = SensorExportItem(
            key=sv.definition.key, name=sv.definition.name, value=sv.value,
            unit=sv.definition.unit, icon=sv.definition.icon,
            category=sv.definition.category.value, formel=sv.definition.formel,
            berechnung=sv.berechnung, hinweis=_hinweis(sv),
        )
        assert item.hinweis == sv.zusatz_attribute["vorbehalt"]
