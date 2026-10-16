"""N-753 (16.10.2026) — die im Monatsformular getippte Ø-Temperatur erreicht die Datenbank.

Bis dahin kannten ``MonatsdatenBase``/``MonatsdatenCreate``/``MonatsdatenUpdate`` das Feld ``durchschnittstemperatur`` nicht; das
Formular (``MonatsdatenForm.tsx``) schickt es seit Juli 2026, Pydantic verwarf es still. Dazu: ein leeres Wetterfeld im Update
(``null``) stempelt keine ``manual:form``-Marke mehr — sonst prallte der tägliche Wetter-Lückenschluss für immer daran ab
(gemessen in Runde 3: 0 von 2 Feldern gefüllt). Ein ``null`` auf ``pv_erzeugung_kwh`` löscht weiter (N-622 Nacharbeit).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from backend.api.routes.monatsdaten import (
    MonatsdatenCreate,
    MonatsdatenUpdate,
    create_monatsdaten,
    update_monatsdaten,
)
from backend.models.monatsdaten import Monatsdaten
from backend.services.wetter import luecken
from backend.tests import factories

_FORMULAR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "forms" / "MonatsdatenForm.tsx"
_WETTER = {"datenquelle": "brightsky", "globalstrahlung_kwh_m2": 150.0, "sonnenstunden": 210.0,
           "durchschnittstemperatur_c": 17.5, "temperatur_herkunft": "archiv"}


async def _anlage(db):
    a = await factories.anlage(db, anlagenname="N-753", standort_land="DE")
    a.latitude, a.longitude = 50.0, 8.0
    await db.commit()
    return a


async def _zeile(db, aid) -> Monatsdaten:
    return (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == aid))).scalar_one()


def _marke(md, feld):
    return ((md.source_provenance or {}).get(feld) or {}).get("source")


async def test_create_speichert_die_temperatur_mit_marke(db):
    a = await _anlage(db)
    await create_monatsdaten(MonatsdatenCreate(anlage_id=a.id, jahr=2026, monat=5, einspeisung_kwh=100.0,
                                               netzbezug_kwh=50.0, durchschnittstemperatur=-2.4), db=db)
    md = await _zeile(db, a.id)
    assert md.durchschnittstemperatur == -2.4 and _marke(md, "durchschnittstemperatur") == "manual:form"


async def test_update_speichert_die_temperatur_mit_marke(db):
    a = await _anlage(db)
    r = await create_monatsdaten(MonatsdatenCreate(anlage_id=a.id, jahr=2026, monat=5, einspeisung_kwh=100.0,
                                                   netzbezug_kwh=50.0), db=db)
    await update_monatsdaten(r.id, MonatsdatenUpdate.model_validate({"durchschnittstemperatur": 14.2}), db=db)
    md = await _zeile(db, a.id)
    assert md.durchschnittstemperatur == 14.2 and _marke(md, "durchschnittstemperatur") == "manual:form"


async def test_leeres_wetterfeld_ist_keine_eingabe_der_lueckenschluss_fuellt(db):
    """``null`` für die drei Wetterfelder: keine Marke, der Lückenschluss füllt alle drei."""
    a = await _anlage(db)
    r = await create_monatsdaten(MonatsdatenCreate(anlage_id=a.id, jahr=2026, monat=5, einspeisung_kwh=100.0,
                                                   netzbezug_kwh=50.0), db=db)
    await update_monatsdaten(r.id, MonatsdatenUpdate.model_validate(
        {"globalstrahlung_kwh_m2": None, "sonnenstunden": None, "durchschnittstemperatur": None}), db=db)
    await db.commit()
    md = await _zeile(db, a.id)
    assert [_marke(md, f) for f in luecken.WETTER_MONATSFELDER] == [None, None, None]
    with patch.object(luecken, "loese_monats_wetter", AsyncMock(return_value=_WETTER)):
        erg = await luecken.schliesse_wetter_luecken(db, a, heute=date(2026, 10, 16))
    assert erg.felder_gefuellt == 3
    assert (md.globalstrahlung_kwh_m2, md.sonnenstunden, md.durchschnittstemperatur) == (150.0, 210.0, 17.5)


async def test_null_auf_pv_gesamt_loescht_weiter(db):
    """Gegenprobe: außerhalb der Wetterfelder bleibt ``null`` ein Löschsignal (N-622 Nacharbeit)."""
    a = await _anlage(db)
    r = await create_monatsdaten(MonatsdatenCreate(anlage_id=a.id, jahr=2026, monat=5, einspeisung_kwh=100.0,
                                                   netzbezug_kwh=50.0, pv_erzeugung_kwh=300.0), db=db)
    await update_monatsdaten(r.id, MonatsdatenUpdate.model_validate({"pv_erzeugung_kwh": None}), db=db)
    md = await _zeile(db, a.id)
    assert md.pv_erzeugung_kwh is None


def test_jedes_feld_des_formulars_kennt_das_schema():
    """Klassenprobe (N-753 a): jeder Schlüssel, den ``MonatsdatenForm.tsx`` an ``onSubmit`` übergibt, ist in
    ``MonatsdatenCreate`` bekannt, und — außer den Schlüsselfeldern — auch in ``MonatsdatenUpdate``. Gelesen aus dem
    Quelltext des Formulars (kein Frontend-Lauf)."""
    text = _FORMULAR.read_text(encoding="utf-8")
    block = text[text.index("await onSubmit({"):]
    block = block[:block.index("\n      })")]
    schluessel = set(re.findall(r"^        ([a-z0-9_]+):", block, flags=re.M))
    assert {"einspeisung_kwh", "globalstrahlung_kwh_m2", "durchschnittstemperatur"} <= schluessel, schluessel
    assert schluessel - set(MonatsdatenCreate.model_fields) == set()
    assert schluessel - set(MonatsdatenUpdate.model_fields) == {"anlage_id", "jahr", "monat"}
