"""N-708 — ein negativer `inv:`-Wert ist ein Zeilenfehler, wie in v09 (eine Regel, ein Ort).

Die automatisch erkannte Geräte-Spalte prüft das Vorzeichen seit jeher (v09, «Wert darf nicht negativ sein»), der
`inv:`-Slot für dieselbe Größe nicht: −77 + 200 ergab im Cockpit PV 123, der Daten-Checker schwieg. Jetzt prüfen
beide über `import_export.helpers.pruefe_nicht_negativ`; Zählfelder (`typ: int`) prüft v09 nicht, der Slot ebenso.
Die Vorschau bietet den Monat nicht an und nennt den Grund.

Schwestern: `test_n705_custom_import_inv_id_der_anlage.py`, `test_n706_custom_import_vorschau_gleich_import.py`.
"""

from __future__ import annotations

from backend.tests import factories
from backend.tests.custom_import_hilfen import csv_text, imd, importiere, monatszeile, vorschau

JM = [("Jahr", "jahr"), ("Monat", "monat")]


async def test_negativer_inv_wert_ist_ein_zeilenfehler_wie_in_v09(db):
    anlage = await factories.anlage(db)
    sued = await factories.investition(db, anlage.id, "pv-module", bezeichnung="Sueddach", leistung_kwp=6.0)
    nord = await factories.investition(db, anlage.id, "pv-module", bezeichnung="Norddach", leistung_kwp=4.0)
    text = csv_text(["Jahr", "Monat", "S", "N"], [2025, 3, -77, 200], [2025, 4, 50, 60])
    zuordnung = [*JM, ("S", f"inv:{sued.id}:pv_erzeugung_kwh"), ("N", f"inv:{nord.id}:pv_erzeugung_kwh")]

    antwort = await importiere(db, anlage.id, text, zuordnung, [(2025, 3), (2025, 4)])

    assert antwort.fehler == ["2025/03: Spalte 'S': Wert darf nicht negativ sein (-77.0)"]
    assert antwort.importiert == 1
    assert await imd(db, sued.id, 2025, 3) is None and await imd(db, nord.id, 2025, 3) is None
    assert await monatszeile(db, anlage.id, 2025, 3) is None
    assert (await monatszeile(db, anlage.id, 2025, 4)).pv_erzeugung_kwh == 110.0

    v = await vorschau(db, anlage.id, text, zuordnung)
    assert [(m.jahr, m.monat) for m in v.monate] == [(2025, 4)]
    assert any("Wert darf nicht negativ sein" in w for w in v.warnungen), v.warnungen


async def test_geraete_spalte_negativ_bleibt_derselbe_zeilenfehler(db):
    """Gegenprobe: der v09-Text ist unverändert — dieselbe Regel, jetzt an einem Ort."""
    anlage = await factories.anlage(db)
    await factories.investition(db, anlage.id, "pv-module", bezeichnung="Sueddach", leistung_kwp=6.0)
    text = csv_text(["Jahr", "Monat", "Sueddach_kWh"], [2025, 3, -5])

    antwort = await importiere(db, anlage.id, text, list(JM), [(2025, 3)])

    assert antwort.fehler == ["2025/03: Spalte 'Sueddach_kWh': Wert darf nicht negativ sein (-5.0)"]
