"""N-735 — eine über das Formular neu angelegte Monatszeile trägt ihre Herkunft.

**Der Defekt** (seit ``e527bfe8``, 09.05.2026): ``create_monatsdaten`` setzte die Provenance der frischen Zeile mit
``seed_provenance`` und rief danach ``db.refresh(md)`` **ohne** ``flush`` — der Refresh lud die Zeile neu und verwarf die
eben gesetzten Einträge. Jede Formular-Neuanlage stand ohne ``manual:form`` in der DB (gemessen: Provenance ``[]`` am
Objekt und nach dem Commit). Folgen: der Schutz «im Formular gepflegt schlägt Import und HA-Statistik» galt für neu
angelegte Zeilen nicht, und eine eingetragene 0 war von einem DB-Default nicht zu unterscheiden (N-734).

Wächter: nach ``create_monatsdaten`` tragen die gelieferten Felder ``manual:form``, die berechneten
``auto:monatsabschluss`` — in der DB, nicht nur am Objekt. Schwester: ``test_n734_netzfeld_ohne_herkunft.py``.
"""

from __future__ import annotations

from sqlalchemy import select

from backend.api.routes.monatsdaten import MonatsdatenCreate, create_monatsdaten
from backend.models import Monatsdaten
from backend.tests import factories


async def test_formular_neuanlage_traegt_manual_form_und_auto(db):
    a = await factories.anlage(db)
    await db.commit()

    await create_monatsdaten(MonatsdatenCreate.model_validate({
        "anlage_id": a.id, "jahr": 2025, "monat": 6,
        "einspeisung_kwh": 180.0, "netzbezug_kwh": 0.0, "pv_erzeugung_kwh": 500.0, "geprueft_gegen": {},
    }), None, db)
    await db.commit()

    md = (await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == a.id).execution_options(populate_existing=True)
    )).scalar_one()
    quellen = {feld: eintrag["source"] for feld, eintrag in md.source_provenance.items()}

    for feld in ("einspeisung_kwh", "netzbezug_kwh", "pv_erzeugung_kwh"):
        assert quellen.get(feld) == "manual:form", (feld, quellen)
    for feld in ("direktverbrauch_kwh", "eigenverbrauch_kwh", "gesamtverbrauch_kwh"):
        assert quellen.get(feld) == "auto:monatsabschluss", (feld, quellen)
    assert "batterie_ladung_kwh" not in quellen, "ein nicht geliefertes Feld bekommt keinen Eintrag"


async def test_eingetragene_null_ist_danach_erfasst(db):
    """Die Folge für N-734: eine im Formular eingetragene 0 ist ein erfasster Wert."""
    from backend.services.monats_fakten import netzfeld_ist_erfasst

    a = await factories.anlage(db)
    await db.commit()
    md = await create_monatsdaten(MonatsdatenCreate.model_validate({
        "anlage_id": a.id, "jahr": 2025, "monat": 6,
        "einspeisung_kwh": 0.0, "netzbezug_kwh": 0.0, "geprueft_gegen": {},
    }), None, db)

    assert netzfeld_ist_erfasst(md, "einspeisung_kwh") and netzfeld_ist_erfasst(md, "netzbezug_kwh")
