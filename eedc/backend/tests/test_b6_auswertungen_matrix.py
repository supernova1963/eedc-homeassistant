"""B6 (05.09.2026) — Auswertungen und PDF sagen über die Wärmepumpe dasselbe wie der Hub.

Matrix-Durchgang Paket 6 über sechs Leser (Tabelle, Komponenten-Zeitreihe, CO₂,
Cockpit-Detailblock, PDF-Monatsbericht, PDF-Jahresbericht) und sechs Sprossen.
Gemessen vor dem Bau: der Monatsbericht schrieb „teilweise abgeleitet" statt der
Layer-Herkunft und keinen Vorbehalt an die Ersparnis (Y-1); der Detailblock
nannte bei F8 einen Rechenweg, der 10 € ergab, neben dem Wert 100 € (Y-3); die
CO₂-Sicht trug bei geschätzter Wärme keinen Vorbehalt (Y-4).

Schwesterdateien: test_b3_hub_matrix.py (die Sprossen), test_b5_export_matrix.py
(dieselbe Form für den HA-Export), test_b6_jahresbericht_symmetrie.py (der
Jahresbericht gegen die Jahresroute).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: F401
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung  # noqa: F401
from backend.tests.test_b3_hub_matrix import SPROSSEN, JAHR, MONAT

FAELLE = ["F2b_gesamtstrom_plus_schaetzung", "F6_wmz_gesamt", "F7_wmz_je_funktion",
          "F8_kaeltemenge", "F11_fremdstrom", "F12_bivalent"]


async def _anlage(db, sprosse, **param_extra):
    parameter, daten, prov = SPROSSEN[sprosse]
    a = Anlage(anlagenname=sprosse, leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(a)
    await db.flush()
    inv = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP",
                      anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
                      parameter={**parameter, **param_extra})
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR, monat=MONAT,
                                  verbrauch_daten=daten, source_provenance=prov or {}))
    db.add(Monatsdaten(anlage_id=a.id, jahr=JAHR, monat=MONAT, einspeisung_kwh=100.0,
                       netzbezug_kwh=50.0, pv_erzeugung_kwh=500.0))
    db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0, gueltig_ab=date(2025, 1, 1)))
    await db.commit()
    return a


def _wp_abschnitt(abschnitte):
    for ab in abschnitte:
        v = vars(ab)
        if "waermepumpe" in [x for x in v.values() if isinstance(x, str)]:
            return {z.label: (z.wert, z.hinweis) for z in next(x for x in v.values() if isinstance(x, list))}
    return {}


@pytest.mark.asyncio
@pytest.mark.parametrize("sprosse", FAELLE)
async def test_tabelle_zeitreihe_und_monatsbericht_folgen_dem_hub(db, sprosse):
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
    from backend.api.routes.investitionen.dashboards import get_waermepumpe_dashboard
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    from backend.services.pdf.builders.monatsbericht import _abschnitte_komponenten

    a = await _anlage(db, sprosse)
    hub = (await get_waermepumpe_dashboard(a.id, strompreis_cent=30.0, db=db))[0].zusammenfassung
    r = (await list_monatsdaten_aggregiert(anlage_id=a.id, jahr=JAHR, db=db))[0]
    assert r.wp_arbeitszahl == hub["durchschnitt_cop"], sprosse
    assert r.wp_arbeitszahl_grund == hub["durchschnitt_cop_grund"], sprosse
    z = (await get_komponenten_zeitreihe(a.id, JAHR, db)).monatswerte[0]
    assert z.wp_cop == hub["durchschnitt_cop"] and z.wp_cop_grund == hub["durchschnitt_cop_grund"], sprosse
    assert z.wp_ersparnis_euro == hub["ersparnis_euro"], sprosse
    d = await get_aktueller_monat(a.id, jahr=JAHR, monat=MONAT, db=db)
    wp = _wp_abschnitt(_abschnitte_komponenten(d))
    # Y-1: Herkunft und Vorbehalt aus dem Layer, dieselben Worte wie der Hub.
    assert wp["Wärmemenge"][1] == (hub["waerme_herkunft"] if d.wp_waerme_abgeleitet else None), sprosse
    assert wp["Ersparnis"][1] == hub["ersparnis_vorbehalt"], sprosse
    assert wp["Arbeitszahl"][1] == (hub["durchschnitt_cop_grund"] or d.wp_jaz_hinweis), sprosse


@pytest.mark.asyncio
async def test_y3_der_rechenweg_ergibt_die_zahl_die_daneben_steht(db):
    """F8 mit 120 €/Jahr Zusatzkosten: 400 + 10 (alt) − (1300 − 300) × 0,30 = 110 €.
    Der Text nennt Kühlstrom und Zusatzkosten — und die anlagenweite Zahl trägt
    denselben Text."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    a = await _anlage(db, "F8_kaeltemenge", alternativ_zusatzkosten_jahr=120.0)
    d = await get_aktueller_monat(a.id, jahr=JAHR, monat=MONAT, db=db)
    det = next(f for f in d.investitionen_financials if f.typ == "waermepumpe")
    assert det.ersparnis_euro == pytest.approx(110.0, abs=0.01)
    assert "Kühlstrom" in det.berechnung and "Zusatzkosten" in det.berechnung, det.berechnung
    assert "300.0 Kühlstrom" in det.berechnung and "10.00 € Zusatzkosten" in det.berechnung
    assert "Kühlstrom" in det.formel and "Zusatzkosten" in det.formel
    assert d.wp_ersparnis_berechnung == det.berechnung


@pytest.mark.asyncio
async def test_y3_ohne_kuehlstrom_und_zusatzkosten_bleibt_der_text_schlicht(db):
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    a = await _anlage(db, "F6_wmz_gesamt")
    d = await get_aktueller_monat(a.id, jahr=JAHR, monat=MONAT, db=db)
    det = next(f for f in d.investitionen_financials if f.typ == "waermepumpe")
    assert "Kühlstrom" not in det.berechnung and "Zusatzkosten" not in det.berechnung
    assert det.berechnung.startswith("3500.0 kWh / 0.90 × 12.0 ct − 1000.0 kWh × 30.00 ct")


@pytest.mark.asyncio
@pytest.mark.parametrize("sprosse, erwartet", [
    ("F2b_gesamtstrom_plus_schaetzung", "Wärme geschätzt"),
    ("F12_bivalent", "zweiter Erzeuger"),
    ("F6_wmz_gesamt", None),
])
async def test_y4_die_co2_sicht_traegt_den_vorbehalt(db, sprosse, erwartet):
    from backend.api.routes.cockpit.nachhaltigkeit import get_nachhaltigkeit

    a = await _anlage(db, sprosse)
    nh = await get_nachhaltigkeit(a.id, db)
    assert nh.co2_wp_kg > 0
    if erwartet is None:
        assert nh.co2_wp_vorbehalt is None
    else:
        assert erwartet in (nh.co2_wp_vorbehalt or ""), nh.co2_wp_vorbehalt
