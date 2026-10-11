"""N-673 — eine ungemessene Wärme-Aufteilung (Heizung/Warmwasser) ist „keine Angabe", in jeder Sicht.

**Der Fund** (Kandidat 50 der Konsolidierungsliste): eine Wärmepumpe nur mit Gesamtstrom und Gesamtwärme hat keine
Heiz-/Warmwasser-Zähler. Die Monats-Fakten trugen ``heizung_kwh = 0.0`` (float-Default), und alles, was aus ihnen
liest — Auswertungen → Tabelle, Cockpit-Übersicht, Komponenten-Zeitreihe, Jahr-Verlauf —, zeigte „0 kWh", während
Cockpit → Monat und das PDF „—" zeigten (`> 0`-Regel). Die Achsen-Matrix hielt das als „Soll unklar" mit 208 Haltewerten
(M05/W1 · M07/W5).

**Das Soll** (Fachentscheid Master Wärme/Klima, 11.10.2026): Regel an der Kategorie — ohne Messung der Aufteilung
keine Angabe (``None``); nur eine gemessene 0 ist 0 (K1). Die Substanz von W1 bleibt (der Gesamtwert gilt). Die
Matrix-Zellen von M05/M07 tragen das Soll seitdem (``test_achsen_matrix._wp_soll``); hier die Einzelwerte am Bestand.
"""

from __future__ import annotations

import pytest

from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.investitionen.dashboard_waermepumpe import get_waermepumpe_dashboard
from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.models import Monatsdaten
from backend.services.monats_fakten import lade_monats_fakten
from backend.tests.test_n641_n645_hub_monatsreihe import _anlage, _inv, _zeile


async def _bestand(db, **vd):
    anlage = await _anlage(db, "N-673")
    wp = await _inv(db, anlage, "waermepumpe", "WP", alter_energietraeger="gas", alter_preis_cent_kwh=10.0)
    db.add(_zeile(wp, 6, **vd))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6, einspeisung_kwh=0.0, netzbezug_kwh=100.0))
    await db.commit()
    return anlage


async def _sichten(db, anlage) -> dict:
    (f,) = await lade_monats_fakten(db, anlage.id, von=(2026, 6), bis=(2026, 6))
    tab = [z for z in await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db) if z.monat == 6]
    u = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=2026, db=db)
    kz = await get_komponenten_zeitreihe(anlage_id=anlage.id, jahr=2026, db=db)
    kd = kz if isinstance(kz, dict) else kz.model_dump()
    zr = next(w for w in kd["monatswerte"] if w["monat"] == 6)
    (karte,) = await get_waermepumpe_dashboard(anlage_id=anlage.id, strompreis_cent=None, db=db)
    (reihe,) = karte.monatsreihe
    return {
        "fakten": (f.wp.heizung_kwh, f.wp.warmwasser_kwh),
        "tabelle": (tab[0].wp_heizung_kwh, tab[0].wp_warmwasser_kwh) if tab else ("keine Zeile", None),
        "uebersicht": (u.wp_heizung_kwh, u.wp_warmwasser_kwh),
        "zeitreihe": (zr["wp_heizung_kwh"], zr["wp_warmwasser_kwh"]),
        "hub_reihe": (reihe.heizung_kwh, reihe.warmwasser_kwh),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("strom,waerme", [(0.0, 0.0), (216.0, 648.0)], ids=["W5-beide-0", "W1-gesamt"])
async def test_nur_gesamtwaerme_heisst_keine_angabe(db, strom, waerme):
    """W5 (beide 0) und W1 (Gesamtwerte > 0): Heizung und Warmwasser sind in jeder Sicht None — vorher 0.0 in
    Fakten, Tabelle, Übersicht, Zeitreihe und Hub-Reihe."""
    anlage = await _bestand(db, stromverbrauch_kwh=strom, waerme_kwh=waerme)
    s = await _sichten(db, anlage)
    assert all(v == (None, None) for v in s.values()), s


@pytest.mark.asyncio
async def test_gemessene_null_bleibt_null(db):
    """Gegenprobe: ein Heiz- und ein Warmwasser-Zähler, die 0 melden — die Aufteilung ist gemessen und heißt 0."""
    anlage = await _bestand(db, stromverbrauch_kwh=0.0, heizenergie_kwh=0.0, warmwasser_kwh=0.0)
    s = await _sichten(db, anlage)
    assert all(v == (0.0, 0.0) for v in s.values()), s
