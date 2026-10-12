"""N-704 — ein `inv:`-Slot auf ein *Sonstiges*-Feld stürzt nicht mehr ab, und der Import schreibt je Monat atomar.

`_shared._is_energy_target` lief flach über `INVESTITION_FELDER.values()`; *Sonstiges* führt seine Felder aber je
Kategorie (dict), die Schleife iterierte Kategorie-Namen ⇒ `AttributeError` für 11 von 12 Sonstiges-Feldern. Die
Vorschau antwortete 500 («Internal Server Error»), über die Fläche war kein Import möglich; per API blieb eine
Gerätezeile ohne Monatszeile stehen (kein Rollback je Zeile).

Wächter (Klassen-Dreifrage «Typ-Weiche kennt Sonstiges nicht»): jede Feld-Option, die die Zuordnungs-Fläche für
eine Sonstiges-Investition anbietet, übersteht `_maybe_convert`; HTTP-Probe 500 ⇒ 200; ein Fehler mitten im Monat
lässt von diesem Monat nichts stehen. Schwestern: `test_custom_import_einheit_non_energy.py`,
`test_n705_custom_import_inv_id_der_anlage.py`.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI

from backend.api.routes.custom_import._shared import _maybe_convert
from backend.core.field_definitions import INVESTITION_FELDER
from backend.tests import factories
from backend.tests.custom_import_hilfen import csv_text, imd, importiere, mapping_json, monatszeile

JM = [("Jahr", "jahr"), ("Monat", "monat")]


def _sonstiges_felder() -> list[str]:
    namen: list[str] = []
    for liste in INVESTITION_FELDER["sonstiges"].values():
        for f in liste:
            if f["feld"] not in namen:
                namen.append(f["feld"])
    return namen


@pytest.mark.parametrize("feld", _sonstiges_felder())
def test_jedes_sonstiges_feld_uebersteht_die_einheiten_weiche(feld):
    _maybe_convert(1000.0, "wh", f"inv:6:{feld}")  # wirft nicht


async def test_vorschau_mit_sonstiges_slot_antwortet_200(db):
    """HTTP: `/preview` mit `inv:<Pool>:verbrauch_sonstig_kwh` — vorher 500 «Internal Server Error»."""
    from backend.api import deps
    from backend.api.routes import custom_import
    from backend.core import database

    anlage = await factories.anlage(db)
    pool = await factories.investition(db, anlage.id, "sonstiges", bezeichnung="Pool",
                                       parameter={"kategorie": "verbraucher"})
    text = csv_text(["Jahr", "Monat", "PoolV"], [2025, 3, 55])

    app = FastAPI()
    app.include_router(custom_import.router, prefix="/api/custom-import")

    async def _db():
        yield db

    app.dependency_overrides[database.get_db] = _db
    app.dependency_overrides[deps.get_db] = _db
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/custom-import/preview",
            params={"mapping_json": mapping_json([*JM, ("PoolV", f"inv:{pool.id}:verbrauch_sonstig_kwh")]),
                    "anlage_id": anlage.id},
            files={"file": ("d.csv", text.encode(), "text/csv")},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["monate"][0]["inv_werte"] == {"PoolV": 55.0}


async def test_sonstiges_slot_wird_importiert(db):
    anlage = await factories.anlage(db)
    pool = await factories.investition(db, anlage.id, "sonstiges", bezeichnung="Pool",
                                       parameter={"kategorie": "verbraucher"})
    text = csv_text(["Jahr", "Monat", "PoolV", "Einsp"], [2025, 3, 77, 9])

    antwort = await importiere(db, anlage.id, text,
                               [*JM, ("PoolV", f"inv:{pool.id}:verbrauch_sonstig_kwh"), ("Einsp", "einspeisung_kwh")],
                               [(2025, 3)])

    assert antwort.erfolg, antwort.fehler
    assert await imd(db, pool.id, 2025, 3) == {"verbrauch_sonstig_kwh": 77.0}


async def test_fehler_mitten_im_monat_laesst_keine_geraetezeile_stehen(db, monkeypatch):
    """Atomar je Monat: scheitert der Monat NACH dem Geräte-Schreibweg, bleibt von ihm nichts stehen —
    der Nachbarmonat wird trotzdem geschrieben."""
    from backend.api.routes.custom_import import apply as apply_mod

    anlage = await factories.anlage(db)
    dach = await factories.investition(db, anlage.id, "pv-module", bezeichnung="Sueddach", leistung_kwp=6.0)
    text = csv_text(["Jahr", "Monat", "Sueddach_kWh", "Einsp"], [2025, 3, 300, 9], [2025, 4, 310, 8])

    echt = apply_mod._schreibe_monatsdaten

    async def _scheitert_im_maerz(db_, anlage_id, existing_md, jahr, monat, *rest, **kw):
        if monat == 3:
            raise RuntimeError("Abbruch nach dem Geräte-Schreibweg")
        return await echt(db_, anlage_id, existing_md, jahr, monat, *rest, **kw)

    monkeypatch.setattr(apply_mod, "_schreibe_monatsdaten", _scheitert_im_maerz)

    antwort = await importiere(db, anlage.id, text, [*JM, ("Einsp", "einspeisung_kwh")], [(2025, 3), (2025, 4)])

    assert antwort.importiert == 1 and len(antwort.fehler) == 1, json.dumps(antwort.model_dump())
    assert await imd(db, dach.id, 2025, 3) is None, "Teilstand: Gerätezeile ohne Monatszeile"
    assert await monatszeile(db, anlage.id, 2025, 3) is None
    assert await imd(db, dach.id, 2025, 4) == {"pv_erzeugung_kwh": 310.0}
