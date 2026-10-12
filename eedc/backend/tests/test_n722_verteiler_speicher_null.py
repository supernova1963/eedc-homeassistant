"""N-722 — Custom- und CSV-Import: eine gelieferte Speicher-0 kommt am Speicher an (0 ist ein Wert), leer bleibt leer.

Der gemeinsame Verteiler `import_export/helpers.py::_distribute_legacy_battery_to_storages` schreibt je Seite nur
`> 0`; die Aufrufer reichen `wert or 0` durch, eine 0 und eine leere Zelle sind dort nicht mehr zu unterscheiden. Der
Portal-Import gleicht das seit N-718 mit `data_import._speicher_nullen` aus, der Custom-Import (`custom_import/apply.py`)
und der CSV-Import mit Alt-Spalten (`import_export/csv_operations.py`) nicht. Gemessen am HEAD `7fb9b026`
(ein Speicher, 03/2025, Ladung 50, Entladung 0):

* Custom-Import ⇒ Speicher `{'ladung_kwh': 50.0}`, Daten-Checker WARNING «03/2025: Akku: Entladung nicht erfasst
  (Ladung 50,0 kWh vorhanden)», Speicher-Hub «—»; der Portal-Import schreibt für denselben Monat `entladung_kwh: 0.0`.
* CSV-Import (Alt-Spalten `Batterie_Ladung_kWh`/`Batterie_Entladung_kWh`) ⇒ dasselbe.

Soll (Regel N-707/N-711/N-718): eine gelieferte 0 steht exakt am Speicher (ohne `abgeleitet`-Marke — eine 0 ist kein
Kapazitätsanteil), eine fehlende Spalte bleibt leer. Wächter: derselbe Monat über Custom- und Portal-Import ⇒
dieselben Werte am Speicher.

Schwesterdateien: test_n718_portal_speicher_null.py, test_n709_custom_import_nur_entladung.py.
"""

from __future__ import annotations

import csv
from io import StringIO

import pytest

from backend.api.routes.data_import import ApplyMonthInput, ApplyRequest, apply_import
from backend.tests import factories
from backend.tests.custom_import_hilfen import csv_text, imd, importiere

JM = [("Jahr", "jahr"), ("Monat", "monat")]
JAHR, MONAT = 2025, 3


async def _speicher_anlage(db, name: str, *, zwei: bool = False):
    anlage = await factories.anlage(db, anlagenname=name)
    a = await factories.investition(db, anlage.id, "speicher", bezeichnung="Akku", parameter={"kapazitaet_kwh": 7.0})
    speicher = [a]
    if zwei:
        speicher.append(await factories.investition(
            db, anlage.id, "speicher", bezeichnung="Klein", parameter={"kapazitaet_kwh": 3.0}))
    await db.commit()
    return anlage, speicher


async def _entladung_meldungen(db, anlage_id: int) -> list[str]:
    from backend.services.daten_checker import DatenChecker

    return [f"{e.meldung}" for e in (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse
            if "nicht erfasst" in e.meldung and ("Entladung" in e.meldung or "Ladung" in e.meldung)]


async def _custom(db, anlage_id: int, kopf: list[str], werte: list, zuordnung: list[tuple[str, str]]):
    antwort = await importiere(db, anlage_id, csv_text(["Jahr", "Monat", *kopf], [JAHR, MONAT, *werte]),
                               [*JM, *zuordnung], [(JAHR, MONAT)])
    assert antwort.erfolg, antwort.fehler
    return antwort


class _Upload:
    """Minimales `UploadFile`-Double für `import_csv` — die Route nutzt nur `await .read()`."""

    def __init__(self, text: str) -> None:
        self._data = text.encode("utf-8")

    async def read(self) -> bytes:
        return self._data


async def _csv(db, anlage_id: int, spalten: dict[str, object]):
    from backend.api.routes.import_export.csv_operations import import_csv

    out = StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh", *spalten])
    w.writerow([JAHR, MONAT, 50, 200, *spalten.values()])
    ergebnis = await import_csv(anlage_id=anlage_id, file=_Upload(out.getvalue()), ueberschreiben=True,
                                auto_wetter=False, db=db)
    assert ergebnis.erfolg, ergebnis.fehler
    return ergebnis


@pytest.mark.asyncio
async def test_custom_import_entladung_null_neben_ladung_kommt_an(db):
    custom, (c_akku,) = await _speicher_anlage(db, "Custom")
    portal, (p_akku,) = await _speicher_anlage(db, "Portal")

    await _custom(db, custom.id, ["PV", "Lad", "Ent"], [500, 50, 0],
                  [("PV", "pv_erzeugung_kwh"), ("Lad", "batterie_ladung_kwh"), ("Ent", "batterie_entladung_kwh")])
    await apply_import(
        anlage_id=portal.id,
        data=ApplyRequest(monate=[ApplyMonthInput(jahr=JAHR, monat=MONAT, pv_erzeugung_kwh=500.0,
                                                  batterie_ladung_kwh=50.0, batterie_entladung_kwh=0.0)]),
        ueberschreiben=False, datenquelle="portal_import", db=db,
    )

    assert await imd(db, c_akku.id, JAHR, MONAT) == {"ladung_kwh": 50.0, "entladung_kwh": 0.0}
    assert await imd(db, c_akku.id, JAHR, MONAT) == await imd(db, p_akku.id, JAHR, MONAT), "Custom = Portal"
    assert await _entladung_meldungen(db, custom.id) == []


@pytest.mark.asyncio
async def test_custom_import_null_null_kommt_an_wie_im_portal_import(db):
    """0/0 — der Speicher war im Monat aus: wie N-718 am Portal trägt jeder Speicher die 0."""
    custom, speicher = await _speicher_anlage(db, "Custom", zwei=True)

    await _custom(db, custom.id, ["PV", "Lad", "Ent"], [500, 0, 0],
                  [("PV", "pv_erzeugung_kwh"), ("Lad", "batterie_ladung_kwh"), ("Ent", "batterie_entladung_kwh")])

    for inv in speicher:
        assert await imd(db, inv.id, JAHR, MONAT) == {"ladung_kwh": 0.0, "entladung_kwh": 0.0}


@pytest.mark.asyncio
async def test_custom_import_null_mit_zwei_speichern_ohne_kapazitaets_marke(db):
    """Die 0 ist exakt, kein Kapazitätsanteil: beide Speicher 0, die Ladung nach Kapazität (35/15)."""
    from sqlalchemy import select

    from backend.models.investition import InvestitionMonatsdaten

    custom, (gross, klein) = await _speicher_anlage(db, "Custom", zwei=True)
    await _custom(db, custom.id, ["Lad", "Ent"], [50, 0],
                  [("Lad", "batterie_ladung_kwh"), ("Ent", "batterie_entladung_kwh")])

    assert await imd(db, gross.id, JAHR, MONAT) == {"ladung_kwh": 35.0, "entladung_kwh": 0.0}
    assert await imd(db, klein.id, JAHR, MONAT) == {"ladung_kwh": 15.0, "entladung_kwh": 0.0}
    row = (await db.execute(select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id == gross.id))).scalar_one()
    prov = (row.source_provenance or {}) if hasattr(row, "source_provenance") else {}
    eintrag = prov.get("verbrauch_daten.entladung_kwh") or {}
    assert not eintrag.get("abgeleitet"), eintrag


@pytest.mark.asyncio
async def test_custom_import_leere_entladung_bleibt_leer(db):
    custom, (akku,) = await _speicher_anlage(db, "Custom")
    await _custom(db, custom.id, ["PV", "Lad"], [500, 50],
                  [("PV", "pv_erzeugung_kwh"), ("Lad", "batterie_ladung_kwh")])

    assert await imd(db, akku.id, JAHR, MONAT) == {"ladung_kwh": 50.0}


@pytest.mark.asyncio
async def test_csv_import_alt_spalten_entladung_null_kommt_an(db):
    anlage, (akku,) = await _speicher_anlage(db, "CSV")
    await _csv(db, anlage.id, {"Batterie_Ladung_kWh": 50, "Batterie_Entladung_kWh": 0})

    assert await imd(db, akku.id, JAHR, MONAT) == {"ladung_kwh": 50.0, "entladung_kwh": 0.0}
    assert await _entladung_meldungen(db, anlage.id) == []


@pytest.mark.asyncio
async def test_csv_import_alt_spalte_leer_bleibt_leer(db):
    anlage, (akku,) = await _speicher_anlage(db, "CSV")
    await _csv(db, anlage.id, {"Batterie_Ladung_kWh": 50, "Batterie_Entladung_kWh": ""})

    assert await imd(db, akku.id, JAHR, MONAT) == {"ladung_kwh": 50.0}
