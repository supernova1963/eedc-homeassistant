"""
Regressionstests für die Bug-Klasse `installationsdatum` auf `Investition`-
Objekten → `AttributeError` → HTTP 500.

Der #264-C-UI-Code baut die TEP-Ladepreis-Periode über `sp.installationsdatum`
auf. Dieses Feld gibt es nur am `Anlage`-Model; das `Investition`-Model hat
`anschaffungsdatum`. `80041a7e` fixte das in `get_speicher_dashboard` — die
Geschwister-Vorkommen in `get_roi_dashboard` und `get_finanz_prognose` blieben
und ließen das ROI-Dashboard komplett mit "Ein Fehler ist aufgetreten"
abstürzen (Klausnn-Issue #285, "ROI nicht mehr verfügbar", v3.31.8).

Der Bug rutschte durch, weil kein Akzeptanztest die Endpoints mit einer
echten `Investition` aufrief. Diese Tests schließen die Lücke für alle drei.
"""

from __future__ import annotations

from datetime import date

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.api.routes.investitionen.dashboards import get_speicher_dashboard
from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.api.routes.aussichten import get_finanz_prognose


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


async def test_roi_dashboard_laeuft_durch(db):
    """`get_roi_dashboard` baute die TEP-Periode über `sp.installationsdatum`
    auf — selbe Bug-Klasse, anderer Endpoint. Klausnn-Issue #285 ("ROI nicht
    mehr verfügbar"): das ROI-Dashboard stürzte komplett ab."""
    anlage_id = await _seed_speicher(db)
    result = await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=1.85, jahr=None, db=db,
    )
    assert result is not None


async def test_finanz_prognose_laeuft_durch(db):
    """`get_finanz_prognose` (Aussichten) hatte dasselbe `installationsdatum`-
    Vorkommen — muss ohne AttributeError durchlaufen (#285)."""
    anlage_id = await _seed_speicher(db)
    result = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)
    assert result is not None
