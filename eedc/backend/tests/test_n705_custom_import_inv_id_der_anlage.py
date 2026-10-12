"""N-705 — eine `inv:`-Zuordnung muss zur Ziel-Anlage gehören, sonst wird sie ignoriert und gemeldet.

Vorlagen sind global (`templates.py`, ohne Anlagen-Bezug), das Löschen einer Investition räumt sie nicht auf, und
SQLite vergibt freie IDs neu. Bis 12.10.2026 prüfte der Import die ID nicht: eine ID einer anderen Anlage schrieb in
die **fremde** Anlage (dieselbe PV stand danach in zwei Anlagen), eine gelöschte ID ergab einen FK-Fehler und 500.
Jetzt: Zuordnung ignorieren (wie die Auswahl der Fläche «– Ignorieren –» zeigt) und es sagen — Vorschau wie Import.

Wächter (Klasse «Investitions-ID ohne Anlagenbindung», wie N-668): fremde Anlage ⇒ kein Schreiben dort, unbekannte
ID ⇒ kein Absturz, kein Datensatz. Schwestern: `test_n704_custom_import_sonstiges_slot.py`,
`test_n706_custom_import_vorschau_gleich_import.py`.
"""

from __future__ import annotations

from sqlalchemy import select

from backend.models.investition import InvestitionMonatsdaten
from backend.tests import factories
from backend.tests.custom_import_hilfen import csv_text, imd, importiere, monatszeile, vorschau

JM = [("Jahr", "jahr"), ("Monat", "monat")]


async def test_id_einer_fremden_anlage_schreibt_dort_nicht(db):
    eigene = await factories.anlage(db, anlagenname="Eigene")
    fremde = await factories.anlage(db, anlagenname="Fremde")
    await factories.investition(db, eigene.id, "pv-module", bezeichnung="Dach", leistung_kwp=10.0)
    fremd_dach = await factories.investition(db, fremde.id, "pv-module", bezeichnung="Fremddach", leistung_kwp=5.0)
    text = csv_text(["Jahr", "Monat", "S", "Einsp"], [2025, 3, 77, 5])
    zuordnung = [*JM, ("S", f"inv:{fremd_dach.id}:pv_erzeugung_kwh"), ("Einsp", "einspeisung_kwh")]

    antwort = await importiere(db, eigene.id, text, zuordnung, [(2025, 3)])

    assert antwort.erfolg, antwort.fehler
    assert await imd(db, fremd_dach.id, 2025, 3) is None, "Daten in einer fremden Anlage"
    md = await monatszeile(db, eigene.id, 2025, 3)
    assert md.pv_erzeugung_kwh is None and md.einspeisung_kwh == 5.0
    assert any("nicht gibt" in w for w in antwort.warnungen), antwort.warnungen

    # Die Vorschau zeigt den Wert nicht an und sagt dasselbe.
    v = await vorschau(db, eigene.id, text, zuordnung)
    assert "S" not in v.monate[0].inv_werte
    assert any("nicht gibt" in w for w in v.warnungen), v.warnungen


async def test_unbekannte_id_stuerzt_nicht_ab_und_schreibt_nichts(db):
    anlage = await factories.anlage(db)
    text = csv_text(["Jahr", "Monat", "S", "Einsp"], [2025, 3, 77, 1], [2025, 4, 78, 2])

    antwort = await importiere(db, anlage.id, text,
                               [*JM, ("S", "inv:4242:pv_erzeugung_kwh"), ("Einsp", "einspeisung_kwh")],
                               [(2025, 3), (2025, 4)])

    assert antwort.erfolg and antwort.importiert == 2, antwort.fehler
    verwaist = (await db.execute(
        select(InvestitionMonatsdaten).where(InvestitionMonatsdaten.investition_id == 4242)
    )).scalars().all()
    assert verwaist == []
    assert any("ID 4242" in w for w in antwort.warnungen), antwort.warnungen


async def test_feld_das_die_investition_nicht_fuehrt_wird_ignoriert(db):
    """Eine Vorlage, deren ID inzwischen einem Gerät anderen Typs gehört (ID neu vergeben)."""
    anlage = await factories.anlage(db)
    wb = await factories.investition(db, anlage.id, "wallbox", bezeichnung="WB")
    text = csv_text(["Jahr", "Monat", "S"], [2025, 3, 300])

    antwort = await importiere(db, anlage.id, text, [*JM, ("S", f"inv:{wb.id}:pv_erzeugung_kwh")], [(2025, 3)])

    assert await imd(db, wb.id, 2025, 3) is None
    assert any("kein Feld" in w for w in antwort.warnungen), antwort.warnungen
