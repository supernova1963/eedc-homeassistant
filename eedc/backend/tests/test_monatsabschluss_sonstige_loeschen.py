"""Regression: sonstige Positionen löschen via Wizard.

Hintergrund #286 rcmcronny: nach v3.32.0-Fix (`50706fe7`) meldete der
Tester, dass die WP-Einträge (Eintrag + Gegeneintrag) beim Speichern
verschwinden, beim Neu-Öffnen aber wieder da sind — trotz mehrfachem
Hard-Refresh. Dieser Test reproduziert den End-to-End-Pfad:

1. IMD mit zwei `sonstige_positionen` im `verbrauch_daten`-JSON
2. Wizard-Save mit `sonstige_positionen: []` (Frontend nach Löschen)
3. IMD neu laden — `sonstige_positionen` muss leer sein

Der Test deckt damit auf, ob die Löschung an Frontend↔Backend-Vertrag
(empty list statt None) oder am Provenance-Resolver (manual:form gewinnt)
hängt.
"""

from __future__ import annotations

from datetime import date

from fastapi import BackgroundTasks
from sqlalchemy import select

from backend.api.routes.monatsabschluss.wizard import (
    FeldWert,
    InvestitionWerte,
    MonatsabschlussInput,
    save_monatsabschluss,
)
from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
)


async def test_sonstige_positionen_loeschen_via_leere_liste(db):
    """Wizard schickt nach Löschen `sonstige_positionen: []` — die IMD muss
    danach eine leere Liste haben.

    Frontend-Vertrag nach v3.32.0 (`50706fe7`): bei `hattePositionen=true` +
    `gueltigePositionen=[]` wird `sonstige_positionen: []` (nicht `null`)
    gesendet. Backend (`wizard.py:328`) deutet `is not None` als „berühren",
    schreibt die leere Liste via `write_json_subkey_with_provenance` mit
    `source="manual:form"`. Manual override gewinnt immer (FrodoVDR #251).
    """
    # Seed: Anlage + WP-Investition + IMD mit 2 sonstige_positionen
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=4,
        netzbezug_kwh=100.0, einspeisung_kwh=50.0,
    ))
    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Nibe F2120",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"jaz": 4.2},
    )
    db.add(wp)
    await db.flush()
    imd = InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2025, monat=4,
        verbrauch_daten={
            "heizenergie_kwh": 800.0,
            "stromverbrauch_kwh": 200.0,
            "sonstige_positionen": [
                {"bezeichnung": "WP-Wartung", "betrag": 120.0, "typ": "ausgabe"},
                {"bezeichnung": "Wartungs-Gegenbuchung", "betrag": 120.0, "typ": "ertrag"},
            ],
        },
    )
    db.add(imd)
    await db.flush()
    imd_id = imd.id

    # Wizard-Save mit leerer sonstige_positionen-Liste (User hat beide X-geklickt)
    daten = MonatsabschlussInput(
        einspeisung_kwh=50.0,
        netzbezug_kwh=100.0,
        investitionen=[
            InvestitionWerte(
                investition_id=wp.id,
                felder=[
                    FeldWert(feld="heizenergie_kwh", wert=800.0),
                    FeldWert(feld="stromverbrauch_kwh", wert=200.0),
                ],
                sonstige_positionen=[],
            ),
        ],
    )
    result = await save_monatsabschluss(
        anlage_id=anlage.id, jahr=2025, monat=4,
        daten=daten, background_tasks=BackgroundTasks(), db=db,
    )
    assert result.success

    # Neu laden — sonstige_positionen muss leer sein
    fresh = await db.execute(
        select(InvestitionMonatsdaten).where(InvestitionMonatsdaten.id == imd_id)
    )
    imd_fresh = fresh.scalar_one()
    assert imd_fresh.verbrauch_daten.get("sonstige_positionen") == [], (
        f"sonstige_positionen wurden NICHT gelöscht — Inhalt: "
        f"{imd_fresh.verbrauch_daten.get('sonstige_positionen')!r}"
    )


async def test_sonstige_positionen_null_laesst_unveraendert(db):
    """Gegen-Test: wenn `sonstige_positionen=None` gesendet wird (Frontend-
    Vertrag „nicht anfassen"), bleibt die bestehende Liste in der DB
    erhalten — Backend darf nicht aus None einen Löschvorgang machen."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=4,
        netzbezug_kwh=100.0, einspeisung_kwh=50.0,
    ))
    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Nibe",
        anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(wp)
    await db.flush()
    imd = InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2025, monat=4,
        verbrauch_daten={
            "heizenergie_kwh": 800.0,
            "sonstige_positionen": [
                {"bezeichnung": "Wartung", "betrag": 120.0, "typ": "ausgabe"},
            ],
        },
    )
    db.add(imd)
    await db.flush()
    imd_id = imd.id

    daten = MonatsabschlussInput(
        einspeisung_kwh=50.0,
        netzbezug_kwh=100.0,
        investitionen=[
            InvestitionWerte(
                investition_id=wp.id,
                felder=[FeldWert(feld="heizenergie_kwh", wert=800.0)],
                sonstige_positionen=None,  # explizit None
            ),
        ],
    )
    result = await save_monatsabschluss(
        anlage_id=anlage.id, jahr=2025, monat=4,
        daten=daten, background_tasks=BackgroundTasks(), db=db,
    )
    assert result.success

    fresh = await db.execute(
        select(InvestitionMonatsdaten).where(InvestitionMonatsdaten.id == imd_id)
    )
    imd_fresh = fresh.scalar_one()
    bestand = imd_fresh.verbrauch_daten.get("sonstige_positionen")
    assert bestand and len(bestand) == 1, (
        f"None-Pfad soll Bestand erhalten, hat aber: {bestand!r}"
    )


async def test_monatsdaten_form_loeschen_via_leere_liste(db):
    """Zweite Speicher-Route (MonatsdatenForm → PUT /monatsdaten/{id}) muss
    den Löschsignal-Pfad ebenfalls bedienen.

    #286 rcmcronny: Tester meldete „Einträge bleiben drin trotz v3.32.0-Fix
    und mehrfachem Hard-Refresh". Ursache: der Wizard-Fix (`50706fe7`) deckt
    nur `MonatsabschlussWizard.tsx` ab — `MonatsdatenForm.tsx` (separat
    erreichbar über Monatsdaten-Tabelle → Edit) hatte exakt denselben Bug:
    bei leerer Positionen-Liste wurde `sonstige_positionen` nicht ins
    Payload aufgenommen, der Backend-`_save_investitionen_monatsdaten`-
    Helper ließ den Sub-Key unangetastet, alte Liste blieb in der DB.
    """
    from backend.api.routes.monatsdaten import update_monatsdaten
    from backend.api.routes.monatsdaten import MonatsdatenUpdate

    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    md = Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=4,
        netzbezug_kwh=100.0, einspeisung_kwh=50.0,
    )
    db.add(md)
    await db.flush()
    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Nibe",
        anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(wp)
    await db.flush()
    imd = InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2025, monat=4,
        verbrauch_daten={
            "heizenergie_kwh": 800.0,
            "sonstige_positionen": [
                {"bezeichnung": "Eintrag", "betrag": 120.0, "typ": "ausgabe"},
                {"bezeichnung": "Gegeneintrag", "betrag": 120.0, "typ": "ertrag"},
            ],
        },
    )
    db.add(imd)
    await db.flush()
    imd_id = imd.id

    # User hat in MonatsdatenForm alle Positionen X-geklickt und speichert
    # — Payload-Vertrag nach Fix: sonstige_positionen: [] (Löschsignal)
    update = MonatsdatenUpdate(
        investitionen_daten={
            str(wp.id): {
                "heizenergie_kwh": 800.0,
                "sonstige_positionen": [],
            }
        },
    )
    await update_monatsdaten(monatsdaten_id=md.id, data=update, db=db)

    fresh = await db.execute(
        select(InvestitionMonatsdaten).where(InvestitionMonatsdaten.id == imd_id)
    )
    imd_fresh = fresh.scalar_one()
    assert imd_fresh.verbrauch_daten.get("sonstige_positionen") == [], (
        f"sonstige_positionen wurden NICHT gelöscht — Inhalt: "
        f"{imd_fresh.verbrauch_daten.get('sonstige_positionen')!r}"
    )
