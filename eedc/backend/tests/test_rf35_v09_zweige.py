"""RF-35 — die Zweige von `import_export/helpers.py::_import_investition_monatsdaten_v09`, die weder die Golden Master
`csv-import`/`custom-import` noch ein Test vor dem Umbau ausführten (Zeilenspur und Sprengsätze 23.10.2026, HEAD dba12861):

* **Strategie 1 mit dem nackten Gerätenamen**: eine Spalte, die genau `<Bezeichnung>` heißt (ohne Suffix), gehört dem ersten
  Feld des Geräts mit `csv_suffix` — Strategie 2 (Suffix) fände sie nicht (`_v09_spalte_zuordnen`);
* **eine Zelle ohne Zahl** in einer Geräte-Spalte wird übersprungen — kein Gerätewert, kein Aggregat (`_v09_spalten_sammeln`);
* **Sonderkosten eines Geräts ohne weitere Werte** legen seine Zeile an (`_v09_sonderkosten`);
* **`on_upsert`** wird je geschriebenem Gerät gerufen (die beiden Aufrufer übergeben ihn nicht; Orchestrator).

Charakterisierung des Verhaltens vor dem Schnitt (am HEAD und nach RF-35 gleich grün). Schwesterdateien:
`test_n710_csv_suffix_alt_ein_wert.py`, `test_csv_vorlage_rundlauf_f55.py`, `test_nebenfunde_j_handgriffe.py`.
"""

from __future__ import annotations

import pytest

from backend.api.routes.import_export.helpers import _import_investition_monatsdaten_v09
from backend.api.routes.custom_import._shared import _parse_number
from backend.api.routes.import_export.csv_operations import _parse_float
from backend.tests import factories
from backend.tests.custom_import_hilfen import imd

JAHR, MONAT = 2025, 6


async def _geraete(db):
    anlage = await factories.anlage(db)
    bkw = await factories.investition(db, anlage.id, "balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8)
    modul = await factories.investition(db, anlage.id, "pv-module", bezeichnung="Dach", leistung_kwp=5.0)
    await db.flush()
    return bkw, modul


async def _v09(db, row, investitionen, parse_float=_parse_float, **kw):
    return await _import_investition_monatsdaten_v09(
        db, row, parse_float, investitionen, JAHR, MONAT, True, source="manual:csv_import", writer="csv_wizard", **kw,
    )


@pytest.mark.asyncio
async def test_rf35_spalte_mit_nacktem_geraetenamen_gehoert_dem_ersten_feld(db):
    bkw, modul = await _geraete(db)
    summen = await _v09(db, {"Jahr": "2025", "Monat": "6", "Balkon": "42"}, [bkw, modul])
    assert await imd(db, bkw.id, JAHR, MONAT) == {"pv_erzeugung_kwh": 42.0}
    assert summen["pv_erzeugung_sum"] == 42.0


@pytest.mark.asyncio
async def test_rf35_zelle_ohne_zahl_wird_uebersprungen(db):
    bkw, modul = await _geraete(db)
    # Der Custom-Import liest Zahlen mit `_parse_number` (eine Zelle ohne Zahl ⇒ None); der CSV-Import wirft dort.
    summen = await _v09(db, {"Jahr": "2025", "Monat": "6", "Balkon_Erzeugung_kWh": "abc", "Dach_kWh": "10"}, [bkw, modul],
                        parse_float=lambda v: _parse_number(v, ","))
    assert await imd(db, bkw.id, JAHR, MONAT) is None
    assert await imd(db, modul.id, JAHR, MONAT) == {"pv_erzeugung_kwh": 10.0}
    assert summen["pv_erzeugung_sum"] == 10.0


@pytest.mark.asyncio
async def test_rf35_sonderkosten_ohne_weitere_werte_und_on_upsert(db):
    bkw, modul = await _geraete(db)
    gerufen = []
    summen = await _v09(
        db, {"Jahr": "2025", "Monat": "6", "Dach_Sonderkosten_Euro": "12,5", "Dach_Sonderkosten_Notiz": " Reinigung ",
             "Balkon_Erzeugung_kWh": "7"},
        [bkw, modul], on_upsert=gerufen.append,
    )
    assert await imd(db, modul.id, JAHR, MONAT) == {
        "sonstige_positionen": [{"bezeichnung": "Reinigung", "betrag": 12.5, "typ": "ausgabe"}],
    }
    assert await imd(db, bkw.id, JAHR, MONAT) == {"pv_erzeugung_kwh": 7.0}
    assert summen["pv_erzeugung_sum"] == 7.0
    assert len(gerufen) == 2
