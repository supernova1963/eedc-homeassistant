"""N-670 — ein Monat mit Wärmepumpen-Strom ohne Wärme (Standby) ist eine Gerätezeile mit 0 €, in jeder Sicht.

**Der Fund** (Kandidat 34 der Konsolidierungsliste, Analyse 10.10.2026): ``wp_ersparnis_zeile`` bildete bei Wärme 0 keine
Zeile; Cockpit, Übersicht und Hub trugen den Monat damit als 0 (bzw. die Ergebnis-Leiter als „WP-Ersparnis fehlt"),
HA-Export (Sensor je Wärmepumpe) und die Jahresformel (Aussichten, ROI-Fortschritt, Jahres-Ersparnis des HA-Exports)
zogen den Strom des Monats von der Ersparnis ab. Gemessen am HEAD 8b759a70, Juni Heizmonat 25 € + Juli Strom 40 kWh /
Wärme 0 bei 30 ct: Monat Juli ``None`` und ``fehlende_posten = ['WP-Ersparnis']``, Sensor 13,00 € (25 − 12),
Aussichten-Erträge 361 statt 373 €.

**Das Soll** (Fachentscheid Master Wärme/Klima, Auftrag K5): Strom wie gemessen, Wärme 0, Ersparnis 0 €, Etikett
„Standby"; keine Sicht belastet den Strom anders als die Zeile. Datenstand wie im Betrieb (echter Schreibweg
``create_monatsdaten``, Datei-Datenbank, kein HA) — die Bausteine des N-609-Probenstands.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import date

import pytest
from sqlalchemy import select

from backend.models import Anlage, Investition
from backend.tests import pv_achse_matrix as mx
from backend.tests.test_n609_wp_ersparnis_je_geraet import H, _bau


def _standby(strom: float) -> dict:
    return {"heizenergie_kwh": 0.0, "warmwasser_kwh": 0.0, "stromverbrauch_kwh": strom}


def test_layer_standby_zeile():
    """Die eine Zeilenregel: Strom 40 / Wärme 0 gemessen ⇒ Zeile mit 0 €, echten Stromkosten, Etikett Standby; ohne
    Messmarke (``null_ist_kein_betrieb=False``) bleibt es bei „keine Zeile", Wärme fehlt (``None``) ebenso."""
    from backend.services.wp_wirtschaftlichkeit import WP_ETIKETT_STANDBY, wp_ersparnis_zeile

    kw = dict(strom_kuehlen_kwh=0.0, strompreis_cent=30.0, parameter={"alter_energietraeger": "gas"},
              gaspreis_cent=10.0)
    z = wp_ersparnis_zeile(waerme_kwh=0.0, strom_kwh=40.0, null_ist_kein_betrieb=True, **kw)
    assert z is not None
    assert (z.ersparnis_euro, round(z.wp_kosten_euro, 2), z.alte_heizung_kosten_euro) == (0.0, 12.0, 0.0)
    assert (z.etikett, z.bewertbar) == (WP_ETIKETT_STANDBY, False)
    assert wp_ersparnis_zeile(waerme_kwh=0.0, strom_kwh=40.0, null_ist_kein_betrieb=False, **kw) is None
    assert wp_ersparnis_zeile(waerme_kwh=None, strom_kwh=40.0, null_ist_kein_betrieb=True, **kw) is None
    # Die gewöhnliche Zeile trägt kein Etikett.
    assert wp_ersparnis_zeile(waerme_kwh=900.0, strom_kwh=250.0, null_ist_kein_betrieb=True, **kw).etikett is None


def test_jahresformel_belastet_den_standby_strom_nicht():
    """``berechne_wp_alternativkosten_ersparnis`` (Aussichten · ROI · HA-Export-Jahresersparnis): der Standby-Monat
    trägt 0 — weder Strom noch Zusatzkosten-Zwölftel. Mit Zusatzkosten 120 €/Jahr: vorher 33,00 € (Juni 25 + Juli
    −12 + 2/12 × 120), nachher 35,00 € (Juni 25 + 1/12 × 120) = derselbe Bestand ohne den Standby-Monat."""
    from types import SimpleNamespace

    from backend.core.berechnungen import berechne_wp_alternativkosten_ersparnis

    wp = SimpleNamespace(id=1, parameter={"alter_energietraeger": "gas", "alter_preis_cent_kwh": 10.0,
                                          "alternativ_zusatzkosten_jahr": 120.0})
    imd = {(1, 2025, 6): dict(H), (1, 2025, 7): _standby(40.0)}
    mit = berechne_wp_alternativkosten_ersparnis([wp], imd, {}, {}, 30.0)
    ohne = berechne_wp_alternativkosten_ersparnis([wp], {(1, 2025, 6): dict(H)}, {}, {}, 30.0)
    assert round(mit, 2) == round(ohne, 2) == 35.0, (mit, ohne)


async def _sichten(strom_standby: float) -> dict:
    import backend.api.routes.aktueller_monat as am
    from backend.api.routes.aussichten.finanzen import get_finanz_prognose
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export.investition_sensoren import calculate_investition_sensors

    monate = {(2025, 6): (H, {}), (2025, 7): (_standby(strom_standby), {})}
    verz = tempfile.mkdtemp(prefix="eedc-n670-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            with mx._umgebung(mx._ha_aus()):
                aid, ids = await _bau(db, [(date(2024, 1, 1), None, 30.0)], monate, {}, False, kuehl_nachtrag=False)
                r = await am.get_aktueller_monat(anlage_id=aid, jahr=2025, monat=7, db=db)
                inv = (await db.execute(select(Investition).where(Investition.id == ids["WP"]))).scalar_one()
                sens = await calculate_investition_sensors(db, inv, None)
                u = await get_cockpit_uebersicht(anlage_id=aid, jahr=2025, db=db)
                fp = await get_finanz_prognose(anlage_id=aid, monate=12, db=db)
                return {
                    "monat": r.wp_ersparnis_euro,
                    "strom": r.wp_strom_kwh,
                    "zeilen": [z.ersparnis_euro for z in r.investitionen_financials if z.typ == "waermepumpe"],
                    "fehlend": list(r.fehlende_posten),
                    "ha": next(s.value for s in sens if s.definition.key == "wp_ersparnis_euro"),
                    "uebersicht": u.wp_ersparnis_euro,
                    "aussichten": fp.bisherige_ertraege_euro,
                }
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


@pytest.mark.parametrize("strom", [40.0, 80.0])
async def test_standby_monat_eine_zeile_in_jeder_sicht(strom):
    """Juli Strom 40 (bzw. 80) / Wärme 0: Zeile vorhanden mit 0 €, Monat 0 statt „fehlt", Strom wie gemessen; Sensor je
    Wärmepumpe und Übersicht = Σ Zeilen (Juni 25 €); die Aussichten-Erträge hängen nicht vom Standby-Strom ab."""
    s = await _sichten(strom)
    assert s["zeilen"] == [0.0], s
    assert s["monat"] == 0.0, s
    assert s["strom"] == strom, s
    assert not any("WP" in p for p in s["fehlend"]), s
    assert round(s["ha"], 2) == 25.0, s
    assert round(s["uebersicht"], 2) == 25.0, s


async def test_aussichten_unabhaengig_vom_standby_strom():
    """Derselbe Bestand mit 40 und mit 80 kWh Standby-Strom: die bisherigen Erträge der Aussichten sind gleich — vorher
    sanken sie je 40 kWh um 12 € (der Strom wurde gegen die Alternative belastet)."""
    a, b = await _sichten(40.0), await _sichten(80.0)
    assert a["aussichten"] == b["aussichten"], (a["aussichten"], b["aussichten"])
