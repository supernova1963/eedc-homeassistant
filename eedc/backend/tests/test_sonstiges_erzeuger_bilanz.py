"""Sonstiger Erzeuger (z. B. BHKW) zählt in die Netzpunkt-Bilanz — Konzept 2026-06-22.

Ein sonstiger Erzeuger speist hinter denselben Hauszähler wie die PV. Seine
Erzeugung MUSS in die Eigenverbrauchs-/Autarkie-Ableitung einfließen, sonst
verfälscht der gemessene Einspeise-Zähler die PV-Bilanz still: `direktverbrauch
= max(0, Erzeugung − Einspeisung − …)` wird zu niedrig, Autarkie/EV-Quote
unterschätzt. PV-EIGENE Kennzahlen (Anzeige-Erzeugung, spez. Ertrag) bleiben
rein (Achsen-Trennung).

Die drei Bilanz-Read-Sites (cockpit/uebersicht, monatsdaten/aggregiert,
aktueller_monat inkl. Vorjahr) müssen denselben Wert liefern (Symmetrie-Pflicht,
[[feedback_aggregator_symmetrie]]).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.core.berechnungen import (
    berechne_verbrauchs_kennzahlen,
    erzeugung_hinter_zaehler_kwh,
)
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.services.live_komponenten_builder import build_komponenten


async def _seed(db, *, mit_sonstiges: bool) -> int:
    """PV 1000 kWh + (optional) BHKW 400 kWh; Zähler einsp=300, netz=200, Mai 2026."""
    anlage = Anlage(anlagenname="BHKW-Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0)
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    if mit_sonstiges:
        bhkw = Investition(anlage_id=anlage.id, typ="sonstiges", bezeichnung="Mini-BHKW",
                           anschaffungsdatum=date(2024, 1, 1),
                           parameter={"kategorie": "erzeuger"})
        db.add(bhkw)
        await db.flush()
        db.add(InvestitionMonatsdaten(investition_id=bhkw.id, jahr=2026, monat=5,
                                      verbrauch_daten={"erzeugung_kwh": 400.0}))
    await db.commit()
    return anlage.id


# Erwartung MIT BHKW: Erzeugung_gesamt = 1000 + 400 = 1400.
#   direkt = max(0, 1400 − 300) = 1100; eigen = 1100; gesamt = 1100 + 200 = 1300.
#   autarkie = 1100/1300 = 84.6 %; ev_quote = 1100/1400 = 78.6 %.
_KZ_MIT = berechne_verbrauchs_kennzahlen(
    pv_erzeugung_kwh=1400.0, einspeisung_kwh=300.0, netzbezug_kwh=200.0,
)


def test_helper_summiert_alle_erzeuger():
    assert erzeugung_hinter_zaehler_kwh(1000.0, 0.0, 400.0) == pytest.approx(1400.0)
    assert erzeugung_hinter_zaehler_kwh(None, 400.0) == pytest.approx(400.0)
    assert erzeugung_hinter_zaehler_kwh() == 0.0


async def test_sonstiges_erzeuger_hebt_eigenverbrauch_und_autarkie(db):
    """Die 400 BHKW-kWh erhöhen Eigenverbrauch/Gesamtverbrauch/Autarkie."""
    anlage_id = await _seed(db, mit_sonstiges=True)
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=2026, db=db)
    mai = next(r for r in rows if r.monat == 5)
    assert mai.eigenverbrauch_kwh == pytest.approx(1100.0)
    assert mai.gesamtverbrauch_kwh == pytest.approx(1300.0)
    assert mai.autarkie_prozent == pytest.approx(_KZ_MIT.autarkie_prozent, abs=0.1)
    # Ohne den Fix wären es die reinen PV-Werte 700 / 900 gewesen.
    assert mai.eigenverbrauch_kwh != pytest.approx(700.0)


async def test_ohne_sonstiges_reine_pv_bilanz_unveraendert(db):
    """Regression: ohne BHKW exakt die alte PV-Bilanz (700 / 900)."""
    anlage_id = await _seed(db, mit_sonstiges=False)
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=2026, db=db)
    mai = next(r for r in rows if r.monat == 5)
    assert mai.eigenverbrauch_kwh == pytest.approx(700.0)
    assert mai.gesamtverbrauch_kwh == pytest.approx(900.0)


async def test_pv_kennzahlen_bleiben_rein(db):
    """Achsen-Trennung: die Anzeige-PV-Erzeugung zählt das BHKW NICHT mit,
    während die Autarkie die Gesamterzeugung nutzt."""
    anlage_id = await _seed(db, mit_sonstiges=True)
    ueb = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=2026, db=db)
    assert ueb.pv_erzeugung_kwh == pytest.approx(1000.0)  # rein PV, NICHT 1400
    assert ueb.autarkie_prozent == pytest.approx(_KZ_MIT.autarkie_prozent, abs=0.1)


async def test_drei_read_sites_symmetrisch(db):
    """cockpit/uebersicht == monatsdaten/aggregiert == aktueller_monat (gleicher Monat)."""
    anlage_id = await _seed(db, mit_sonstiges=True)
    ueb = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=2026, db=db)
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=2026, db=db)
    mai = next(r for r in rows if r.monat == 5)
    am = await get_aktueller_monat(anlage_id=anlage_id, jahr=2026, monat=5, db=db)

    for feld in ("eigenverbrauch_kwh", "gesamtverbrauch_kwh"):
        u, m, a = getattr(ueb, feld), getattr(mai, feld), getattr(am, feld)
        assert u == pytest.approx(m, abs=0.5), f"{feld}: uebersicht={u} != aggregiert={m}"
        assert u == pytest.approx(a, abs=0.5), f"{feld}: uebersicht={u} != aktueller_monat={a}"
    assert ueb.autarkie_prozent == pytest.approx(mai.autarkie_prozent, abs=0.2)
    assert ueb.autarkie_prozent == pytest.approx(am.autarkie_prozent, abs=0.2)


# ─── Live-Bilanz ─────────────────────────────────────────────────────────────


def _live_anlage() -> Anlage:
    return Anlage(anlagenname="Live", leistung_kwp=10.0, standort_land="DE")


def test_live_sonstiger_erzeuger_eigene_komponente_und_in_autarkie():
    """Live: ein BHKW (sonstiges/erzeuger) mit Live-Leistung erscheint als eigene
    Erzeugungs-Komponente und hebt Eigenverbrauch/Autarkie — PV-Leistung rein."""
    anlage = _live_anlage()
    bhkw = Investition(typ="sonstiges", bezeichnung="Mini-BHKW",
                       parameter={"kategorie": "erzeuger"})
    investitionen = {"bhkw": bhkw}
    inv_values = {"bhkw": {"leistung_w": 1000.0}}
    live_map = {"bhkw": {"leistung_w": "sensor.bhkw"}}
    # PV 3 kW über Basis, Einspeisung 0.5 kW, Netzbezug 1 kW.
    basis = {"pv_gesamt_w": 3000.0, "einspeisung_w": 500.0, "netzbezug_w": 1000.0}

    res = build_komponenten(anlage, basis, inv_values, investitionen, live_map)

    sonst = next((k for k in res["komponenten"] if k["key"] == "sonstige_bhkw"), None)
    assert sonst is not None, "Sonstiger Erzeuger fehlt als Live-Komponente"
    assert sonst["erzeugung_kw"] == pytest.approx(1.0)
    assert sonst["verbrauch_kw"] is None  # NICHT als Verbraucher gezählt

    # PV-Leistung bleibt rein (3000 W, nicht 4000): kein BHKW in pv_total_w.
    assert res["pv_total_w"] == pytest.approx(3000.0)

    # Autarkie nutzt Gesamterzeugung 4 kW: direkt=max(0,4−0.5)=3.5, eigen=3.5,
    # gesamt=3.5+1=4.5 → 77.8 %. Ohne BHKW wären es 2.5/3.5 = 71.4 %.
    autarkie = next((g for g in res["gauges"] if g["key"] == "autarkie"), None)
    assert autarkie is not None
    assert autarkie["wert"] == pytest.approx(78, abs=1)


def test_live_sonstiger_verbraucher_bleibt_verbraucher():
    """Gegenprobe: ein sonstiger *Verbraucher* zählt weiter als Verbrauch."""
    anlage = _live_anlage()
    last = Investition(typ="sonstiges", bezeichnung="Pool-Pumpe",
                       parameter={"kategorie": "verbraucher"})
    res = build_komponenten(
        anlage, {"pv_gesamt_w": 3000.0, "einspeisung_w": 0.0, "netzbezug_w": 0.0},
        {"last": {"leistung_w": 800.0}}, {"last": last},
        {"last": {"leistung_w": "sensor.pool"}},
    )
    komp = next((k for k in res["komponenten"] if k["key"].endswith("_last")), None)
    assert komp is not None
    assert komp["verbrauch_kw"] == pytest.approx(0.8)
    assert komp["erzeugung_kw"] is None
    assert res["pv_total_w"] == pytest.approx(3000.0)
