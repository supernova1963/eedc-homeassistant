"""B6/Y-2 (05.09.2026) — der PDF-Jahresbericht sagt über die Wärmepumpe dasselbe
wie Cockpit → Jahr: Arbeitszahl MIT Grund, je Funktion, Kühlen, Herkunft, Vorbehalt.

Gemessen vor dem Bau: der Bericht rechnete eine eigene Arbeitszahl und warf den
Grund weg — an F2b/F11/F12 stand „–" ohne Grund (SOLL §3.3 S3); die Kennzahlen je
Funktion (F7: 4,0 / 2,4) und die Kühl-Arbeitszahl (F8: 3,0) fehlten ganz, obwohl
der Monatsbericht und Cockpit → Jahr (B4) sie tragen. Jetzt lesen Jahresroute und
Bericht `services/waermepumpe_jahreskennzahlen.py` — eine Faltung, zwei Leser.

Schwesterdateien: test_b4_cockpit_matrix.py (Monat ≡ Jahr-Backend, dieselben
Sprossen), test_pdf_jahresbericht_f43_waerme_nullen.py (der Bericht rendert mit
dem echten Template), test_b6_auswertungen_matrix.py (die Messung).
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


async def _anlage(db, sprosse):
    parameter, daten, prov = SPROSSEN[sprosse]
    a = Anlage(anlagenname=sprosse, leistung_kwp=10.0, installationsdatum=date(2025, 1, 1),
               standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(a)
    await db.flush()
    inv = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP",
                      anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=12000.0,
                      parameter=parameter)
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


def _r(x):
    return None if x is None else round(x, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("sprosse", FAELLE)
async def test_jahresbericht_und_jahresroute_sagen_dasselbe(db, sprosse):
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    a = await _anlage(db, sprosse)
    route = await get_cockpit_uebersicht(a.id, jahr=JAHR, db=db)
    wp = (await build_jahresbericht_context(db, a.id, JAHR))["waermepumpe"]

    assert _r(wp["cop"]) == _r(route.wp_cop), sprosse
    assert wp["cop_grund"] == route.wp_cop_grund, sprosse
    assert wp["cop_hinweis"] == route.wp_cop_hinweis, sprosse
    assert _r(wp["jaz_heizen"]) == _r(route.wp_jaz_heizen), sprosse
    assert wp["jaz_heizen_grund"] == route.wp_jaz_heizen_grund, sprosse
    assert _r(wp["jaz_warmwasser"]) == _r(route.wp_jaz_warmwasser), sprosse
    assert _r(wp["jaz_kuehlen"]) == _r(route.wp_jaz_kuehlen), sprosse
    assert wp["jaz_kuehlen_grund"] == route.wp_jaz_kuehlen_grund, sprosse
    assert (wp["waerme_herkunft"] is not None) == bool(route.wp_waerme_abgeleitet), sprosse
    if route.wp_waerme_abgeleitet:
        assert wp["waerme_herkunft"] == route.wp_waerme_herkunft
    assert wp["ersparnis_vorbehalt"] == route.wp_ersparnis_vorbehalt, sprosse


@pytest.mark.asyncio
async def test_gesperrte_arbeitszahl_steht_mit_grund_im_bericht(db):
    """F11: „–" allein war die Beschwerde; der Grund steht jetzt daneben —
    und F7 druckt die Kennzahlen je Funktion, F8 die Kühl-Arbeitszahl."""
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context
    from backend.services.pdf.engine import render_html

    a = await _anlage(db, "F11_fremdstrom")
    html = render_html("jahresbericht.html", await build_jahresbericht_context(db, a.id, JAHR))
    assert "Heizstab-Strom auf dem WP-Zähler" in html

    a7 = await _anlage(db, "F7_wmz_je_funktion")
    html7 = render_html("jahresbericht.html", await build_jahresbericht_context(db, a7.id, JAHR))
    assert "Arbeitszahl Heizen" in html7 and "4,00" in html7 and "2,40" in html7

    a8 = await _anlage(db, "F8_kaeltemenge")
    html8 = render_html("jahresbericht.html", await build_jahresbericht_context(db, a8.id, JAHR))
    assert "Arbeitszahl Kühlen" in html8 and "3,00" in html8

    a2 = await _anlage(db, "F2b_gesamtstrom_plus_schaetzung")
    html2 = render_html("jahresbericht.html", await build_jahresbericht_context(db, a2.id, JAHR))
    assert "geschätzt: Strom × JAZ 3,5" in html2
    assert "Ersparnis und CO₂ folgen aus der Schätzung" in html2


@pytest.mark.asyncio
async def test_ohne_getrennte_messung_stehen_die_zeilen_mit_grund(db):
    """F6: die Zeilen je Funktion und Kühlen bleiben — mit dem Grund statt einer
    Zahl (S3), dieselbe Regel wie Monatsbericht und Cockpit → Jahr."""
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context
    from backend.services.pdf.engine import render_html

    a = await _anlage(db, "F6_wmz_gesamt")
    html = render_html("jahresbericht.html", await build_jahresbericht_context(db, a.id, JAHR))
    assert "Arbeitszahl Heizen" in html and "Strom nicht getrennt je Funktion gemessen" in html
    assert "Arbeitszahl Kühlen" in html and "kein Kühlbetrieb in diesem Zeitraum" in html
