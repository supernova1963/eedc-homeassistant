"""V2H (Vehicle-to-Home) wird einheitlich als Eigenverbrauch gezählt.

#304-Definitionsentscheidung: V2H (E-Auto entlädt ins Haus) wird wie eine
zweite Batterie behandelt — voll als Eigenverbrauch, analog zur stationären
Speicher-Entladung. Umgesetzt als Parameter des SoT-Helpers
berechne_verbrauchs_kennzahlen, den ALLE vier Read-Sites nutzen
(Cockpit, HA-Export, Aussichten, Jahresbericht) → keine Drift mehr.

Hier: Helper-Vertrag + Cockpit-Integration (die zwei zuvor V2H-blinden Pfade).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen import berechne_verbrauchs_kennzahlen
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten


def test_helper_v2h_wie_speicher_entladung():
    """V2H erhöht Eigenverbrauch (Zähler) UND Gesamtverbrauch (Nenner)."""
    mit = berechne_verbrauchs_kennzahlen(
        pv_erzeugung_kwh=1000, einspeisung_kwh=400, netzbezug_kwh=300,
        speicher_ladung_kwh=200, speicher_entladung_kwh=180, v2h_entladung_kwh=50,
    )
    # direkt = max(0,1000-400-200)=400; eigen = 400+180+50 = 630; gesamt = 930
    assert mit.eigenverbrauch_kwh == pytest.approx(630)
    assert mit.gesamtverbrauch_kwh == pytest.approx(930)
    assert mit.autarkie_prozent == pytest.approx(630 / 930 * 100)

    ohne = berechne_verbrauchs_kennzahlen(
        pv_erzeugung_kwh=1000, einspeisung_kwh=400, netzbezug_kwh=300,
        speicher_ladung_kwh=200, speicher_entladung_kwh=180,
    )
    assert ohne.eigenverbrauch_kwh == pytest.approx(580)  # ohne V2H
    assert mit.eigenverbrauch_kwh - ohne.eigenverbrauch_kwh == pytest.approx(50)


def test_helper_default_v2h_null_unveraendert():
    """Ohne v2h-Argument identisch zur Formel vor der Erweiterung."""
    k = berechne_verbrauchs_kennzahlen(
        pv_erzeugung_kwh=1000, einspeisung_kwh=400, netzbezug_kwh=300,
        speicher_entladung_kwh=180,
    )
    assert k.eigenverbrauch_kwh == pytest.approx(780)


async def test_cockpit_eigenverbrauch_inklusive_v2h(db):
    """Cockpit (zuvor V2H-blinde Inline-Formel) zählt V2H jetzt mit."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    anlage = Anlage(anlagenname="V2H", leistung_kwp=10.0, latitude=52.0, longitude=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=300.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2020, 1, 1))
    ea = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Auto",
                     anschaffungsdatum=date(2020, 1, 1))
    db.add_all([pv, ea])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=2025, monat=6,
                                  verbrauch_daten={"v2h_entladung_kwh": 80.0, "km_gefahren": 500.0}))
    await db.commit()

    resp = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=2025, db=db)
    # direkt = 1000-400 = 600; eigen = 600 + V2H 80 = 680 (kein stationärer Speicher)
    assert resp.eigenverbrauch_kwh == pytest.approx(680, abs=1), (
        f"Cockpit-Eigenverbrauch {resp.eigenverbrauch_kwh} ignoriert V2H "
        f"(wäre 600 ohne) — V2H-Vereinheitlichung greift nicht."
    )
