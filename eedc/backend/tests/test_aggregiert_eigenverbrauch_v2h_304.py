"""`/monatsdaten/aggregiert` zählt V2H im Eigenverbrauch — #304-Bruder.

Die Auswertungen-Finanzen (FinanzenTab → createMonatsZeitreihe) konsumieren die
`eigenverbrauch_kwh` aus `/aggregiert`. Dieser Stats-Pfad rechnete eigenverbrauch
von Hand (`direktverbrauch + speicher_entladung`) und ließ V2H (E-Auto → Haus)
weg, während Cockpit/Aussichten/HA-Export/PDF V2H bereits über den SoT-Helper
`berechne_verbrauchs_kennzahlen` als Eigenverbrauch zählen (#304).

Jetzt routet `/aggregiert` über denselben Helper → V2H zählt, und die Sicht ist
deckungsgleich mit dem Cockpit. Symmetrie statt Drift
([[feedback_aggregator_symmetrie]], [[feedback_legacy_felder]]).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.core.berechnungen import berechne_verbrauchs_kennzahlen
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten


async def _seed_mit_v2h(db) -> int:
    anlage = Anlage(anlagenname="V2H-Stats", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0)
    sp = Investition(anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
                     anschaffungsdatum=date(2024, 1, 1))
    ea = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Auto",
                     anschaffungsdatum=date(2024, 1, 1))
    db.add_all([pv, sp, ea])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=sp.id, jahr=2026, monat=5,
                                  verbrauch_daten={"ladung_kwh": 200.0, "entladung_kwh": 150.0}))
    db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=2026, monat=5,
                                  verbrauch_daten={"v2h_entladung_kwh": 80.0, "km_gefahren": 500.0}))
    await db.commit()
    return anlage.id


async def test_aggregiert_eigenverbrauch_enthaelt_v2h(db):
    """direkt = max(0, 1000−300−200)=500; eigen = 500 + 150 (Speicher) + 80 (V2H) = 730.
    Ohne V2H-Migration wären es nur 650 gewesen (alter #304-Bruder-Bug)."""
    anlage_id = await _seed_mit_v2h(db)
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=2026, db=db)
    mai = next(r for r in rows if r.jahr == 2026 and r.monat == 5)

    erwartet = berechne_verbrauchs_kennzahlen(
        pv_erzeugung_kwh=1000.0, einspeisung_kwh=300.0, netzbezug_kwh=200.0,
        speicher_ladung_kwh=200.0, speicher_entladung_kwh=150.0, v2h_entladung_kwh=80.0,
    )
    assert mai.eigenverbrauch_kwh == pytest.approx(730.0)
    assert mai.eigenverbrauch_kwh == pytest.approx(erwartet.eigenverbrauch_kwh)
    assert mai.eigenverbrauch_kwh != pytest.approx(650.0), (
        "V2H wird im Stats-Pfad noch ignoriert — #304-Bruder zurück."
    )


async def test_aggregiert_deckungsgleich_mit_sot_helper(db):
    """Alle Kern-Kennzahlen des Stats-Pfads = SoT-Helper (Symmetrie-Pflicht)."""
    anlage_id = await _seed_mit_v2h(db)
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=2026, db=db)
    mai = next(r for r in rows if r.jahr == 2026 and r.monat == 5)
    kz = berechne_verbrauchs_kennzahlen(
        pv_erzeugung_kwh=1000.0, einspeisung_kwh=300.0, netzbezug_kwh=200.0,
        speicher_ladung_kwh=200.0, speicher_entladung_kwh=150.0, v2h_entladung_kwh=80.0,
    )
    assert mai.eigenverbrauch_kwh == pytest.approx(kz.eigenverbrauch_kwh)
    assert mai.gesamtverbrauch_kwh == pytest.approx(kz.gesamtverbrauch_kwh)
    assert mai.autarkie_prozent == pytest.approx(kz.autarkie_prozent, abs=0.1)
    assert mai.eigenverbrauchsquote_prozent == pytest.approx(kz.eigenverbrauchsquote_prozent, abs=0.1)
