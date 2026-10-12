"""N-739 (b) — ein nicht erfasstes Netzfeld erscheint im Monatsabschluss nicht als geliefert.

**Der Defekt.** Für eine Zeile, die ein Import ohne Netzfelder anlegte (0/0 ohne Herkunft, seit N-734 «nicht erfasst»),
zeigte die Monatsabschluss-Ansicht ``aktueller_wert 0.0 · quelle 'portal_import'`` und das Formular belegte beide
Pflichtfelder mit 0 vor. Wer dem Checker-Handgriff folgte und ungeprüft speicherte, stempelte die 0 als eingetragen
(``manual:form``): Cockpit → Monat zeigte wieder 0 / 0 / 100 %, der Checker schwieg, und der HA-Statistik-Import kam
danach auch mit Haken nicht mehr durch (Stufe 2 < Stufe 1).

**Jetzt:** die Ansicht liefert für ein nicht erfasstes Netzfeld ``aktueller_wert``/``quelle`` leer
(``monatsabschluss/views.py::baue_basis_feld``), ``MonatsdatenResponse`` trägt ``einspeisung_erfasst``/
``netzbezug_erfasst`` (das Formular belegt dann leer vor — Vitest ``monatsdaten-netzfeld-nicht-erfasst-n739.test.tsx``).
Speichert der Anwender den **Vorschlag**, steht der gemessene Wert als ``manual:form`` da.

Schwestern: ``test_n734_netzfeld_ohne_herkunft.py`` (die Regel), ``test_daten_checker_beheben_links_wirken.py`` (N-739 a).
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from backend.api import deps
from backend.api.routes.monatsabschluss.views import get_monatsabschluss
from backend.core import database
from backend.models import Monatsdaten
from backend.tests.test_n734_netzfeld_ohne_herkunft import HA, J, M, _anlage, _import, _monat

NETZ = ("einspeisung_kwh", "netzbezug_kwh")


async def _md(db, aid: int) -> Monatsdaten:
    return (await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == aid).execution_options(populate_existing=True)
    )).scalar_one()


async def test_ansicht_zeigt_das_nicht_erfasste_feld_nicht_als_geliefert(db):
    a = await _anlage(db)
    await _import(db, a.id, wallbox_ladung_kwh=150.0)

    res = await get_monatsabschluss(a.id, J, M, db=db)
    basis = {f.feld: f for f in res.basis_felder}

    for feld in NETZ:
        assert (basis[feld].aktueller_wert, basis[feld].quelle) == (None, None), f"{feld}: vorher 0.0 · 'portal_import'"


async def test_ansicht_gegenprobe_erfasste_null_bleibt_geliefert(db):
    a = await _anlage(db)
    await _import(db, a.id, einspeisung_kwh=0.0, netzbezug_kwh=250.0)

    res = await get_monatsabschluss(a.id, J, M, db=db)
    basis = {f.feld: f for f in res.basis_felder}

    assert (basis["einspeisung_kwh"].aktueller_wert, basis["einspeisung_kwh"].quelle) == (0.0, "portal_import")
    assert basis["netzbezug_kwh"].aktueller_wert == 250.0


async def test_liste_traegt_die_erfasst_marke(db):
    from backend.api.routes import monatsdaten as md_route

    a = await _anlage(db)
    await _import(db, a.id, wallbox_ladung_kwh=150.0)
    b = await _anlage(db)
    await _import(db, b.id, einspeisung_kwh=0.0, netzbezug_kwh=250.0)

    app = FastAPI()
    app.include_router(md_route.router, prefix="/api/monatsdaten")

    async def _db():
        yield db

    app.dependency_overrides[database.get_db] = _db
    app.dependency_overrides[deps.get_db] = _db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        zeilen = {aid: (await client.get("/api/monatsdaten/", params={"anlage_id": aid})).json() for aid in (a.id, b.id)}

    assert [(z["einspeisung_erfasst"], z["netzbezug_erfasst"]) for z in zeilen[a.id]] == [(False, False)]
    assert [(z["einspeisung_erfasst"], z["netzbezug_erfasst"]) for z in zeilen[b.id]] == [(True, True)]


async def test_den_vorschlag_speichern_stempelt_den_messwert(db, monkeypatch):
    """Probe 12 umgekehrt: das leere Feld bekommt den Vorschlag 250/700; gespeichert steht er als `manual:form` da."""
    from backend.api.routes.monatsdaten import MonatsdatenUpdate, update_monatsdaten

    a = await _anlage(db)
    await _import(db, a.id, wallbox_ladung_kwh=150.0)
    md = await _md(db, a.id)

    await update_monatsdaten(md.id, MonatsdatenUpdate(einspeisung_kwh=700.0, netzbezug_kwh=250.0), None, db)
    await db.commit()
    md = await _md(db, a.id)

    assert {k: md.source_provenance[k]["source"] for k in NETZ} == {k: "manual:form" for k in NETZ}
    res = await _monat(db, monkeypatch, a.id, HA)
    assert (res.netzbezug_kwh, res.einspeisung_kwh) == (250.0, 700.0)
