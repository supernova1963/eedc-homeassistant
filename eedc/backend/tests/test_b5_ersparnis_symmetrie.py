"""B5 (05.09.2026) — die Wärmepumpen-Ersparnis ist in Hub, Cockpit-Monat und
HA-Export dieselbe Zahl (SOLL §3.3 S1).

X-4: Die fixen Zusatzkosten der Altheizung (`alternativ_zusatzkosten_jahr`, #141)
standen im HA-Export-Sensor, in den Aussichten und in BERECHNUNGEN.md — der
Monats-Layer `berechne_wp_ersparnis` (Hub, Cockpit Monat/Jahr, Komponenten,
Vorjahr) kannte sie nicht. Gemessen: 166,67 € gegen 176,67 € für dieselbe
Wärmepumpe im selben Monat.

Schwesterdateien: test_b3_hub_matrix.py (die Sprossen), test_b5_export_matrix.py
(Export gegen Hub je Sprosse), test_ha_export_wp_ersparnis_sensor.py (der
Export-Pin 31,11 €, der die Zusatzkosten immer schon enthielt).
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

ZUSATZ_JAHR = 120.0


async def _anlage(db, name, parameter, daten, prov, tarife):
    a = Anlage(anlagenname=name, leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(a)
    await db.flush()
    inv = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP",
                      anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
                      parameter=parameter)
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR, monat=MONAT,
                                  verbrauch_daten=daten, source_provenance=prov or {}))
    for t in tarife:
        t.anlage_id = a.id
        db.add(t)
    await db.commit()
    return a, inv


async def _drei_sichten(db, a, inv, tarif, strompreis_cent):
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.ha_export import calculate_investition_sensors
    from backend.api.routes.investitionen.dashboards import get_waermepumpe_dashboard

    export = {sv.definition.key: sv for sv in await calculate_investition_sensors(db, inv, tarif)}
    hub = (await get_waermepumpe_dashboard(a.id, strompreis_cent=strompreis_cent, db=db))[0].zusammenfassung
    monat = await get_aktueller_monat(a.id, jahr=JAHR, monat=MONAT, db=db)
    ex = export.get("wp_ersparnis_euro")
    return (round(ex.value, 2) if ex is not None else None), hub.get("ersparnis_euro"), monat.wp_ersparnis_euro


@pytest.mark.asyncio
async def test_x4_zusatzkosten_der_altheizung_zaehlen_in_allen_drei_sichten(db):
    """F6 (Wärme 3.500, Strom 1.000, Gas 10 ct, η 0,75) mit 120 €/Jahr Zusatzkosten:
    466,67 + 10 − 300 = 176,67 € — in Hub, Cockpit-Monat und Export."""
    parameter, daten, prov = SPROSSEN["F6_wmz_gesamt"]
    parameter = {**parameter, "alternativ_zusatzkosten_jahr": ZUSATZ_JAHR}
    tarif = Strompreis(netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
                       gueltig_ab=date(2025, 1, 1))
    a, inv = await _anlage(db, "zusatz", parameter, daten, prov, [tarif])
    export, hub, monat = await _drei_sichten(db, a, inv, tarif, 30.0)
    assert hub == pytest.approx(176.67, abs=0.01)
    assert monat == pytest.approx(176.67, abs=0.01)
    assert export == pytest.approx(176.67, abs=0.01)


@pytest.mark.asyncio
async def test_x4_nichts_ersetzt_bekommt_auch_keine_zusatzkosten(db):
    """N-88 bleibt: Zusatzkosten einer Anlage, die es nie gab, zählen nicht."""
    from backend.core.berechnungen.alternativkosten import ERSETZT_NICHTS
    from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis
    r = berechne_wp_ersparnis(
        wp_waerme_kwh=3500.0, wp_strom_kwh=1000.0, wp_strompreis_cent=30.0,
        wp_parameter={"alter_energietraeger": ERSETZT_NICHTS, "alternativ_zusatzkosten_jahr": ZUSATZ_JAHR},
    )
    assert r.bewertbar is False
    assert r.alte_heizung_kosten_euro == 0.0


@pytest.mark.asyncio
async def test_x1_der_export_bewertet_jeden_monat_mit_dem_tarif_seines_stichtags(db):
    """P8: Juli-Daten, Tarif 30 ct bis August und 40 ct ab September — der Export
    rechnete den Juli mit 40 ct (66,67 € statt 166,67 €)."""
    parameter, daten, prov = SPROSSEN["F6_wmz_gesamt"]
    t1 = Strompreis(netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
                    gueltig_ab=date(2025, 1, 1), gueltig_bis=date(2025, 8, 31))
    t2 = Strompreis(netzbezug_arbeitspreis_cent_kwh=40.0, einspeiseverguetung_cent_kwh=8.0,
                    gueltig_ab=date(2025, 9, 1))
    a, inv = await _anlage(db, "tarif", parameter, daten, prov, [t1, t2])
    export, hub, monat = await _drei_sichten(db, a, inv, t2, 40.0)
    assert hub == pytest.approx(166.67, abs=0.01)
    assert export == pytest.approx(166.67, abs=0.01)


@pytest.mark.asyncio
async def test_x5_die_jahresformel_und_der_vorjahresvergleich_kennen_e_b(db):
    """F8 als Vorjahr (2024-07) und im Jahresaggregat: Kühlstrom 300 kWh × 30 ct
    bleibt aus dem Vergleich — anlagenweite Alternativkosten wie Monats-Layer."""
    from backend.core.berechnungen.alternativkosten import berechne_wp_alternativkosten_ersparnis
    parameter, daten, prov = SPROSSEN["F8_kaeltemenge"]
    a, inv = await _anlage(db, "x5", parameter, daten, prov, [
        Strompreis(netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
                   gueltig_ab=date(2024, 1, 1)),
    ])
    summe = berechne_wp_alternativkosten_ersparnis(
        [inv], {(inv.id, JAHR, MONAT): daten}, {}, {(JAHR, MONAT): 30.0}, 30.0,
    )
    # 400 € (alt) − (1300 − 300) × 0,5 × 0,30 = 400 − 150 = 250 (mit dem
    # PV-Anteil-Default der Jahresformel); vorher 400 − 195 = 205.
    assert summe == pytest.approx(250.0, abs=0.01)


@pytest.mark.asyncio
async def test_x5_cockpit_monat_vorjahr_und_komponenten_detail_kennen_e_b(db):
    """F8 in 2024-07 (Vorjahr) und 2025-07: der Vorjahresvergleich und der
    Komponenten-Detailblock rechneten den Kühlstrom mit (10 € statt 100 €)."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.models import Monatsdaten

    parameter, daten, prov = SPROSSEN["F8_kaeltemenge"]
    a = Anlage(anlagenname="x5-cockpit", leistung_kwp=10.0, installationsdatum=date(2024, 1, 1))
    db.add(a)
    await db.flush()
    inv = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP",
                      anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=12000.0,
                      parameter=parameter)
    db.add(inv)
    await db.flush()
    for jahr in (2024, 2025):
        db.add(Monatsdaten(anlage_id=a.id, jahr=jahr, monat=7, einspeisung_kwh=0.0, netzbezug_kwh=0.0))
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=jahr, monat=7,
                                      verbrauch_daten=daten, source_provenance={}))
    db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0, gueltig_ab=date(2024, 1, 1)))
    await db.commit()
    r = await get_aktueller_monat(a.id, jahr=2025, monat=7, db=db)
    assert r.wp_ersparnis_euro == pytest.approx(100.0, abs=0.01)
    assert r.vorjahr is not None
    assert r.vorjahr.get("wp_ersparnis_euro") == pytest.approx(100.0, abs=0.01)
    detail = next(f for f in r.investitionen_financials if f.typ == "waermepumpe")
    assert detail.ersparnis_euro == pytest.approx(100.0, abs=0.01)
