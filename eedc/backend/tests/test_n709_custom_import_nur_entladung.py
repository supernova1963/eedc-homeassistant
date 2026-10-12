"""N-709 — der Custom-Import verteilt reine Entladung auf die Speicher wie der Portal-Import.

Der Custom-Import verteilte die generische Batterie nur bei Ladung > 0 (`apply.py`), der Portal-Import bei Ladung
ODER Entladung > 0 (`data_import._verteile_batterie`) — beide über denselben Verteiler
`_distribute_legacy_battery_to_storages`. Folge: Speicher-Entladung «—», Eigenverbrauch ohne Entladung.

Wächter: derselbe Monat über beide Importe ⇒ dieselben Werte an den Speichern.
Schwestern: `test_n707_import_pv_null_ist_messwert.py`, `test_import_zuordnung_kwp.py`.
"""

from __future__ import annotations

from backend.api.routes.data_import import ApplyMonthInput, ApplyRequest, apply_import
from backend.tests import factories
from backend.tests.custom_import_hilfen import csv_text, imd, importiere

JM = [("Jahr", "jahr"), ("Monat", "monat")]


async def _zwei_speicher(db, name: str):
    anlage = await factories.anlage(db, anlagenname=name)
    a = await factories.investition(db, anlage.id, "speicher", bezeichnung="Gross", parameter={"kapazitaet_kwh": 7.0})
    b = await factories.investition(db, anlage.id, "speicher", bezeichnung="Klein", parameter={"kapazitaet_kwh": 3.0})
    return anlage, a, b


async def test_nur_entladung_wird_verteilt_wie_im_portal_import(db):
    custom, c_a, c_b = await _zwei_speicher(db, "Custom")
    portal, p_a, p_b = await _zwei_speicher(db, "Portal")

    antwort = await importiere(
        db, custom.id, csv_text(["Jahr", "Monat", "PV", "Ent"], [2025, 3, 500, 50]),
        [*JM, ("PV", "pv_erzeugung_kwh"), ("Ent", "batterie_entladung_kwh")], [(2025, 3)],
    )
    assert antwort.erfolg, antwort.fehler
    await apply_import(
        anlage_id=portal.id,
        data=ApplyRequest(monate=[ApplyMonthInput(jahr=2025, monat=3, pv_erzeugung_kwh=500.0,
                                                  batterie_entladung_kwh=50.0)]),
        ueberschreiben=False, datenquelle="portal_import", db=db,
    )

    custom_werte = (await imd(db, c_a.id, 2025, 3), await imd(db, c_b.id, 2025, 3))
    portal_werte = (await imd(db, p_a.id, 2025, 3), await imd(db, p_b.id, 2025, 3))
    assert custom_werte == portal_werte == ({"entladung_kwh": 35.0}, {"entladung_kwh": 15.0})
