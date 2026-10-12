"""N-707 — eine importierte PV-Erzeugung von 0 ist ein Messwert und steht danach in der Monatszeile.

Beide Importe schrieben PV 0 als NULL (Custom-Import: `pv_mapped > 0`; Portal-Import `data_import.py`:
`pv ≤ 0 ⇒ None`), die Batterie 0 dagegen als 0. Folge: der Daten-Checker meldete «PV-Erzeugung fehlt», das Cockpit
zeigte «—» statt 0. Entscheid Master 12.10. (Regel vorhanden, CLAUDE.md «0-Werte: is not None»): eine explizite 0
wird geschrieben, eine leere Zelle bleibt NULL — in beiden Importen.

Wächter: je Pfad 0 ⇒ 0, leer ⇒ NULL. Schwestern: `test_n709_custom_import_nur_entladung.py`,
`test_import_ziel_investition_349.py`.
"""

from __future__ import annotations

from backend.api.routes.data_import import ApplyMonthInput, ApplyRequest, apply_import
from backend.tests import factories
from backend.tests.custom_import_hilfen import csv_text, imd, importiere, monatszeile

JM = [("Jahr", "jahr"), ("Monat", "monat")]


async def test_custom_import_pv_null_ist_null_und_leer_bleibt_leer(db):
    anlage = await factories.anlage(db)
    dach = await factories.investition(db, anlage.id, "pv-module", bezeichnung="Dach", leistung_kwp=10.0)
    text = csv_text(["Jahr", "Monat", "PV", "Bezug"], [2025, 1, 0, 200], [2025, 2, "", 180])

    antwort = await importiere(db, anlage.id, text, [*JM, ("PV", "pv_erzeugung_kwh"), ("Bezug", "netzbezug_kwh")],
                               [(2025, 1), (2025, 2)])

    assert antwort.erfolg, antwort.fehler
    assert (await monatszeile(db, anlage.id, 2025, 1)).pv_erzeugung_kwh == 0.0
    assert (await monatszeile(db, anlage.id, 2025, 2)).pv_erzeugung_kwh is None
    assert await imd(db, dach.id, 2025, 1) is None, "eine 0 wird nicht auf die Module verteilt"


async def test_portal_import_pv_null_ist_null_und_leer_bleibt_leer(db):
    anlage = await factories.anlage(db)
    await factories.investition(db, anlage.id, "pv-module", bezeichnung="Dach", leistung_kwp=10.0)

    antwort = await apply_import(
        anlage_id=anlage.id,
        data=ApplyRequest(monate=[
            ApplyMonthInput(jahr=2025, monat=1, pv_erzeugung_kwh=0.0, netzbezug_kwh=200.0),
            ApplyMonthInput(jahr=2025, monat=2, netzbezug_kwh=180.0),
        ]),
        ueberschreiben=False, datenquelle="portal_import", db=db,
    )

    assert antwort.erfolg, antwort.fehler
    assert (await monatszeile(db, anlage.id, 2025, 1)).pv_erzeugung_kwh == 0.0
    assert (await monatszeile(db, anlage.id, 2025, 2)).pv_erzeugung_kwh is None
