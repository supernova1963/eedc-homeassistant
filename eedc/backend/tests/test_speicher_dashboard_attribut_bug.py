"""
Regressionstest: `get_speicher_dashboard` stürzte mit HTTP 500 ab —
`AttributeError: 'Investition' object has no attribute 'installationsdatum'`.

Der #264-C-UI-Commit baute die TEP-Ladepreis-Periode über
`s.installationsdatum` auf. Dieses Feld gibt es nur am `Anlage`-Model;
das `Investition`-Model hat `anschaffungsdatum`. Jeder Aufruf der
Cockpit-Rubrik "Speicher" mit mindestens einem Speicher warf den Fehler
(rapahl-PN + lokal bestätigt 2026-05-22, v3.31.7).

Der Bug war ungetestet, weil bisher kein Akzeptanztest den Endpoint mit
einer echten `Investition` aufrief — die C-Helfer hatten nur Unit-Tests.
"""

from __future__ import annotations

from datetime import date

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.api.routes.investitionen.dashboards import get_speicher_dashboard


async def _seed_speicher(db, *, anschaffungsdatum: date | None = date(2023, 7, 1)) -> int:
    """Anlage + ein Speicher (analog Huawei 10 kWh aus der rapahl-Meldung)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=4,
        netzbezug_kwh=100.0, einspeisung_kwh=200.0,
    ))
    inv = Investition(
        anlage_id=anlage.id, typ="speicher",
        bezeichnung="Huawei 10 kWh",
        anschaffungsdatum=anschaffungsdatum,
        parameter={
            "kapazitaet_kwh": 10,
            "nutzbare_kapazitaet_kwh": 9.5,
            "wirkungsgrad_prozent": 95,
            "arbitrage_faehig": True,
            "laedt_aus_netz": True,
        },
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={"ladung_kwh": 300.0, "entladung_kwh": 270.0},
    ))
    await db.flush()
    return anlage.id


async def test_speicher_dashboard_laeuft_durch(db):
    """Endpoint muss ohne AttributeError durchlaufen (Regression #264-C-UI)."""
    anlage_id = await _seed_speicher(db)
    result = await get_speicher_dashboard(
        anlage_id=anlage_id, strompreis_cent=None,
        einspeiseverguetung_cent=None, db=db,
    )
    assert len(result) == 1
    assert result[0].zusammenfassung["gesamt_ladung_kwh"] == 300.0
    assert result[0].zusammenfassung["gesamt_entladung_kwh"] == 270.0


async def test_speicher_dashboard_ohne_anschaffungsdatum(db):
    """Speicher ohne Anschaffungsdatum: kein TEP-Ladepreis, aber kein Crash."""
    anlage_id = await _seed_speicher(db, anschaffungsdatum=None)
    result = await get_speicher_dashboard(
        anlage_id=anlage_id, strompreis_cent=None,
        einspeiseverguetung_cent=None, db=db,
    )
    assert len(result) == 1
