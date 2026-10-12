"""N-710 — zwei Spalten, ein Feld: der Alt-Suffix zählt nur, wenn der Haupt-Suffix fehlt, das Aggregat einmal.

Die Registry trägt für das Balkonkraftwerk (`pv_erzeugung_kwh`) den Suffix `Erzeugung_kWh` und den Alt-Suffix `kWh`
(bis v4.0.23 schrieb die Vorlage `<Name>_kWh`, F-55). Trägt eine Datei BEIDE Spalten (alte Vorlage und neuer Name
zusammenkopiert), schrieb v09 bis 12.10.2026 den ersten Treffer ins Gerät, summierte aber beide ins Monats-Aggregat.
Gemessen am HEAD `98abc801` (BKW 100 kWh in `Balkon_Erzeugung_kWh`, 120 in `Balkon_kWh`, dazu ein PV-Modul ohne
eigene Spalte):

| Weg | Monatszeile PV | BKW | Monats-Fakten `pv_kwh` (Cockpit → Monat) |
| --- | --- | --- | --- |
| CSV-Import | **220** | 100 | **220** (das Modul bekommt den Rest 120) |
| CSV-Import, Alt-Spalte zuerst | **220** | **120** | **220** |
| Eigenes Format (Custom-Import) | **220** | 100 | **220**, die Vorschau zeigt beide Spalten als Wert |

Soll: der Wert der Haupt-Spalte (100) in Gerät, Aggregat und Vorschau; die Alt-Spalte gilt nur in einer Zeile, deren
Haupt-Spalte leer ist.

Schwesterdateien: test_n702_custom_import_aggregat_registry.py (dieselbe Klasse «Import summiert am Registry-Feld
vorbei», `inv:`-Weg), test_csv_vorlage_rundlauf_f55.py (der Alt-Suffix und die Vorlage),
test_n706_custom_import_vorschau_gleich_import.py (Vorschau = Import).
"""

from __future__ import annotations

import csv
from io import StringIO

import pytest

from backend.services.monats_fakten import lade_monats_fakten
from backend.tests import factories
from backend.tests.custom_import_hilfen import csv_text, imd, importiere, monatszeile, vorschau

JAHR, MONAT = 2025, 6


class _Upload:
    """Minimales `UploadFile`-Double für `import_csv` — die Route nutzt nur `await .read()`."""

    def __init__(self, text: str) -> None:
        self._data = text.encode("utf-8")

    async def read(self) -> bytes:
        return self._data


async def _anlage(db):
    anlage = await factories.anlage(db)
    bkw = await factories.investition(db, anlage.id, "balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8)
    modul = await factories.investition(db, anlage.id, "pv-module", bezeichnung="Dach", leistung_kwp=5.0)
    await db.commit()
    return anlage, bkw, modul


def _datei(spalten: dict[str, object]) -> str:
    out = StringIO()
    w = csv.writer(out, delimiter=";")
    kopf = ["Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh", *spalten]
    w.writerow(kopf)
    w.writerow([JAHR, MONAT, 50, 200, *spalten.values()])
    return out.getvalue()


async def _csv_import(db, anlage_id: int, text: str):
    from backend.api.routes.import_export.csv_operations import import_csv

    ergebnis = await import_csv(
        anlage_id=anlage_id, file=_Upload(text), ueberschreiben=True, auto_wetter=False, db=db,
    )
    assert ergebnis.erfolg, ergebnis.fehler
    return ergebnis


async def _fakten_pv(db, anlage_id: int) -> float:
    fakten = await lade_monats_fakten(db, anlage_id, von=(JAHR, MONAT), bis=(JAHR, MONAT))
    return fakten[0].erzeugung.pv_kwh


@pytest.mark.asyncio
@pytest.mark.parametrize("reihenfolge", ["haupt_zuerst", "alt_zuerst"])
async def test_csv_import_zaehlt_die_haupt_spalte_einmal(db, reihenfolge):
    anlage, bkw, modul = await _anlage(db)
    spalten = {"Balkon_Erzeugung_kWh": 100, "Balkon_kWh": 120}
    if reihenfolge == "alt_zuerst":
        spalten = {"Balkon_kWh": 120, "Balkon_Erzeugung_kWh": 100}
    await _csv_import(db, anlage.id, _datei(spalten))

    assert await imd(db, bkw.id, JAHR, MONAT) == {"pv_erzeugung_kwh": 100.0}
    md = await monatszeile(db, anlage.id, JAHR, MONAT)
    assert md.pv_erzeugung_kwh == 100.0, f"Aggregat {md.pv_erzeugung_kwh} — die Alt-Spalte zählt nicht mit"
    assert await _fakten_pv(db, anlage.id) == 100.0


@pytest.mark.asyncio
async def test_csv_import_nimmt_die_alt_spalte_wenn_die_haupt_spalte_fehlt(db):
    """Gegenprobe: eine alte Datei mit nur `<Name>_kWh` wird weiter gelesen (Rückwärtskompatibilität, F-55)."""
    anlage, bkw, _ = await _anlage(db)
    await _csv_import(db, anlage.id, _datei({"Balkon_kWh": 120}))

    assert await imd(db, bkw.id, JAHR, MONAT) == {"pv_erzeugung_kwh": 120.0}
    assert (await monatszeile(db, anlage.id, JAHR, MONAT)).pv_erzeugung_kwh == 120.0


@pytest.mark.asyncio
async def test_csv_import_nimmt_die_alt_spalte_in_einer_zeile_mit_leerer_haupt_spalte(db):
    """Die Regel gilt je Zeile: eine leere Haupt-Zelle „fehlt"."""
    anlage, bkw, _ = await _anlage(db)
    await _csv_import(db, anlage.id, _datei({"Balkon_Erzeugung_kWh": "", "Balkon_kWh": 120}))

    assert await imd(db, bkw.id, JAHR, MONAT) == {"pv_erzeugung_kwh": 120.0}
    assert (await monatszeile(db, anlage.id, JAHR, MONAT)).pv_erzeugung_kwh == 120.0


ZUORDNUNG = [("Jahr", "jahr"), ("Monat", "monat"), ("Einsp", "einspeisung_kwh")]


@pytest.mark.asyncio
async def test_custom_import_und_vorschau_zeigen_den_geschriebenen_wert(db):
    anlage, bkw, _ = await _anlage(db)
    text = csv_text(["Jahr", "Monat", "Einsp", "Balkon_Erzeugung_kWh", "Balkon_kWh"], [JAHR, MONAT, 50, 100, 120])

    v = await vorschau(db, anlage.id, text, ZUORDNUNG)
    assert v.monate[0].inv_werte == {"Balkon_Erzeugung_kWh": 100.0}, v.monate[0].inv_werte

    antwort = await importiere(db, anlage.id, text, ZUORDNUNG, [(JAHR, MONAT)])
    assert antwort.erfolg, antwort.fehler
    assert await imd(db, bkw.id, JAHR, MONAT) == {"pv_erzeugung_kwh": 100.0}
    assert (await monatszeile(db, anlage.id, JAHR, MONAT)).pv_erzeugung_kwh == 100.0
    assert await _fakten_pv(db, anlage.id) == 100.0


@pytest.mark.asyncio
async def test_custom_import_vorschau_nimmt_die_alt_spalte_wenn_die_haupt_spalte_leer_ist(db):
    anlage, bkw, _ = await _anlage(db)
    text = csv_text(["Jahr", "Monat", "Einsp", "Balkon_Erzeugung_kWh", "Balkon_kWh"], [JAHR, MONAT, 50, "", 120])

    v = await vorschau(db, anlage.id, text, ZUORDNUNG)
    assert v.monate[0].inv_werte == {"Balkon_kWh": 120.0}, v.monate[0].inv_werte

    antwort = await importiere(db, anlage.id, text, ZUORDNUNG, [(JAHR, MONAT)])
    assert antwort.erfolg, antwort.fehler
    assert await imd(db, bkw.id, JAHR, MONAT) == {"pv_erzeugung_kwh": 120.0}
    assert (await monatszeile(db, anlage.id, JAHR, MONAT)).pv_erzeugung_kwh == 120.0


@pytest.mark.asyncio
async def test_custom_import_mehrere_zeilen_im_monat_vorschau_gleich_import(db):
    """Mehrere Zeilen je Monat (Tageswerte): v09 bekommt die Monatssumme als eine Zeile — trägt sie die Haupt-Spalte,
    zählt die Alt-Spalte nicht. Geprüft wird nur, dass die Vorschau den Wert zeigt, den der Import schreibt."""
    anlage, bkw, _ = await _anlage(db)
    text = csv_text(
        ["Jahr", "Monat", "Einsp", "Balkon_Erzeugung_kWh", "Balkon_kWh"],
        [JAHR, MONAT, 20, 60, 70],
        [JAHR, MONAT, 30, "", 50],
    )

    v = await vorschau(db, anlage.id, text, ZUORDNUNG)
    gezeigt = v.monate[0].inv_werte
    assert set(gezeigt) == {"Balkon_Erzeugung_kWh"}, gezeigt

    antwort = await importiere(db, anlage.id, text, ZUORDNUNG, [(JAHR, MONAT)])
    assert antwort.erfolg, antwort.fehler
    assert await imd(db, bkw.id, JAHR, MONAT) == {"pv_erzeugung_kwh": gezeigt["Balkon_Erzeugung_kWh"]}
    assert (await monatszeile(db, anlage.id, JAHR, MONAT)).pv_erzeugung_kwh == gezeigt["Balkon_Erzeugung_kWh"]
