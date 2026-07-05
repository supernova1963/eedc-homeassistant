"""
Regressions- + Symmetrie-Tests für den Speicher-Netzladung-Key (R15-3).

Bug: `get_speicher_dashboard` las die IMD-Netzladung nur über den Legacy-Key
`speicher_ladung_netz_kwh`. Kanon ist seit der v3.26-Key-Migration
(`_migrate_verbrauch_daten_keys_v326`) `ladung_netz_kwh` — produktive Rows
tragen also NUR den Kanon-Key → `arbitrage_kwh` war immer 0, der
Arbitrage-Block im Komponenten-Hub (V4) und die Arbitrage-KPIs im
v3-SpeicherDashboard blieben unsichtbar, obwohl `arbitrage_faehig=true` und
Netzladung vorhanden war (Demo-DB-Befund 2026-07-05).

Symmetrie-Pflicht (Lehre Aggregations-Drift): der Dashboard-Pfad und der
SoT-Aggregator `aggregiere_speicher_ist` müssen für dieselben IMD-Rows
dieselbe Netzladung liefern — egal ob Kanon- oder Legacy-Key.
"""

from __future__ import annotations

from datetime import date

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.api.routes.investitionen.dashboards import get_speicher_dashboard
from backend.core.berechnungen.speicher_wirtschaftlichkeit import aggregiere_speicher_ist


async def _seed_speicher(db, verbrauch_daten_liste: list[dict]) -> int:
    """Anlage + arbitragefähiger Speicher mit gegebenen IMD-Monaten."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=4,
        netzbezug_kwh=100.0, einspeisung_kwh=200.0,
    ))
    inv = Investition(
        anlage_id=anlage.id, typ="speicher",
        bezeichnung="BYD HVS 15.4",
        anschaffungsdatum=date(2023, 7, 1),
        parameter={
            "kapazitaet_kwh": 15.4,
            "wirkungsgrad_prozent": 95,
            "arbitrage_faehig": True,
            "laedt_aus_netz": True,
        },
    )
    db.add(inv)
    await db.flush()
    for i, daten in enumerate(verbrauch_daten_liste):
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=2026, monat=4 + i,
            verbrauch_daten=daten,
        ))
    await db.flush()
    return anlage.id


async def test_arbitrage_kwh_liest_kanon_key(db):
    """Regression: Kanon-Key `ladung_netz_kwh` muss in arbitrage_kwh landen."""
    anlage_id = await _seed_speicher(db, [
        {"ladung_kwh": 210.4, "entladung_kwh": 154.6,
         "ladung_netz_kwh": 31.6, "speicher_ladepreis_cent": 22},
        {"ladung_kwh": 300.0, "entladung_kwh": 270.0,
         "ladung_netz_kwh": 63.7, "speicher_ladepreis_cent": 22},
    ])
    result = await get_speicher_dashboard(
        anlage_id=anlage_id, strompreis_cent=None,
        einspeiseverguetung_cent=None, db=db,
    )
    assert len(result) == 1
    z = result[0].zusammenfassung
    assert z["arbitrage_faehig"] is True
    assert z["arbitrage_kwh"] == 95.3  # 31,6 + 63,7 — war vor dem Fix 0
    assert z["arbitrage_avg_preis_cent"] == 22.0


async def test_arbitrage_kwh_liest_legacy_key_weiter(db):
    """Legacy-Rows (vor dem nächsten Migrations-Lauf) bleiben lesbar."""
    anlage_id = await _seed_speicher(db, [
        {"ladung_kwh": 200.0, "entladung_kwh": 180.0,
         "speicher_ladung_netz_kwh": 40.0, "speicher_ladepreis_cent": 18},
    ])
    result = await get_speicher_dashboard(
        anlage_id=anlage_id, strompreis_cent=None,
        einspeiseverguetung_cent=None, db=db,
    )
    z = result[0].zusammenfassung
    assert z["arbitrage_kwh"] == 40.0
    assert z["arbitrage_avg_preis_cent"] == 18.0


async def test_symmetrie_dashboard_vs_aggregiere_speicher_ist(db):
    """Dashboard-Summe == SoT-Aggregator für dieselben IMD-Rows (beide Keys)."""
    daten = [
        {"ladung_kwh": 210.4, "entladung_kwh": 154.6, "ladung_netz_kwh": 31.6},
        {"ladung_kwh": 300.0, "entladung_kwh": 270.0, "speicher_ladung_netz_kwh": 63.7},
        {"ladung_kwh": 250.0, "entladung_kwh": 220.0, "ladung_netz_kwh": 51.3},
    ]
    anlage_id = await _seed_speicher(db, daten)
    result = await get_speicher_dashboard(
        anlage_id=anlage_id, strompreis_cent=None,
        einspeiseverguetung_cent=None, db=db,
    )
    dashboard_kwh = result[0].zusammenfassung["arbitrage_kwh"]

    ist = aggregiere_speicher_ist(daten)
    # aggregiere_speicher_ist normiert auf ein Jahr — zurückrechnen.
    sot_kwh = ist.ladung_netz_kwh_jahr / ist.jahres_faktor
    assert dashboard_kwh == round(sot_kwh, 1)
