"""N-747 + N-748 — CSV-Import (Backup-Restore): Alt-Spalten nur auf das EINE Gerät eines Typs, jede Zeile ganz oder gar nicht.

**N-747 (P2).** Die Alt-Spalten (Format vor v0.9: `Batterie_Ladung_kWh`, `EAuto_km`, `Wallbox_Ladung_kWh`, `WP_Strom_kWh` …)
tragen den Wert des ganzen TYPS. Der Legacy-Schreiber (`helpers._import_investition_monatsdaten_legacy`) schrieb ihn bis
13.10.2026 auf das erste aktive Gerät des Typs — nach dem Speicher-Verteiler und den Geräte-Spalten, mit Haken ersetzend.
Gemessen am HEAD `babf27c0` (Bericht `opus-berichte/Q-N747-N748.md`, Etappe 1):

| Fall | Haken | am HEAD | Soll |
| --- | --- | --- | --- |
| zwei Speicher 7/3 kWh, `Batterie_*` 50/40 | ja | Akku 50/40 + Klein 15/12, Warnung «verteilt» | 35/28 + 15/12 |
| ein Speicher, `Akku_Ladung_kWh` 30 + `Batterie_Ladung_kWh` 80 | ja | Akku 80, Warnung «Speicher-Werte werden verwendet» | 30 |
| zwei Speicher, `Klein_Entladung` 12 + `Batterie_Ladung` 20 | nein | Akku Ladung 20 | Akku leer |
| zwei E-Autos / Wallboxen / Wärmepumpen, Alt-Spalten | ja und nein | alles aufs erste Gerät, keine Warnung | nichts + Warnung |
| ein Gerät, Geräte-Spalte 900 + Alt-Spalte 800 | ja | 800 | 900 + Warnung |

Mit genau einem Gerät und ohne Geräte-Spalte bleibt die Alt-Spalte lesbar (Kompatibilität alter Dateien).

**N-748 (P3).** `Sueddach_kWh` 300 neben `PV_Erzeugung_kWh` «abc» ergab «Zeile 2: Ungültiger Wert», «0 importiert» — und
einen Gerätewert 300 ohne Monatszeile. Jetzt schreibt jede Zeile in einem SAVEPOINT (ein äußerer klammert die Schleife,
dieselbe Bauform wie der eigene Import seit Päckchen K, `custom_import/apply.py`).

Schwesterdateien: test_n710_csv_suffix_alt_ein_wert.py (Alt-Suffix einer Geräte-Spalte, v09), test_n722_verteiler_speicher_null.py
(Speicher-Verteiler, Seite 0), test_n538_csv_wege_ohne_schutzzaehler.py (CSV-Wege), test_n704_custom_import_sonstiges_slot.py
(SAVEPOINT je Monat im eigenen Import).
"""

from __future__ import annotations

import csv
import inspect
import re
from io import StringIO
from typing import Optional

import pytest

from backend.tests import factories
from backend.tests.custom_import_hilfen import imd, monatszeile

JAHR, MONAT = 2025, 3


class _Upload:
    """Minimales `UploadFile`-Double für `import_csv` — die Route nutzt nur `await .read()`."""

    def __init__(self, text: str) -> None:
        self._data = text.encode("utf-8")

    async def read(self) -> bytes:
        return self._data


def _datei(spalten: list[str], *zeilen: list) -> str:
    out = StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh", *spalten])
    for z in zeilen:
        w.writerow(z)
    return out.getvalue()


async def _csv_import(db, anlage_id: int, text: str, *, haken: bool):
    from backend.api.routes.import_export.csv_operations import import_csv

    return await import_csv(anlage_id=anlage_id, file=_Upload(text), ueberschreiben=haken, auto_wetter=False, db=db)


async def _anlage(db, *geraete: tuple[str, str, Optional[dict]]):
    anlage = await factories.anlage(db)
    invs = []
    for typ, bez, param in geraete:
        invs.append(await factories.investition(db, anlage.id, typ, bezeichnung=bez, parameter=param))
    await db.commit()
    return anlage, invs


ZWEI_SPEICHER = (("speicher", "Akku", {"kapazitaet_kwh": 7.0}), ("speicher", "Klein", {"kapazitaet_kwh": 3.0}))


# ── N-747 · Speicher ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("haken", [True, False])
async def test_zwei_speicher_alt_spalten_bleiben_verteilt(db, haken):
    anlage, (akku, klein) = await _anlage(db, *ZWEI_SPEICHER)
    erg = await _csv_import(db, anlage.id, _datei(["Batterie_Ladung_kWh", "Batterie_Entladung_kWh"],
                                                  [JAHR, MONAT, 1, 2, 50, 40]), haken=haken)

    assert erg.erfolg and erg.importiert == 1
    assert await imd(db, akku.id, JAHR, MONAT) == {"ladung_kwh": 35.0, "entladung_kwh": 28.0}, \
        "N-747: der Verteiler-Anteil (7/10) bleibt — kein voller Alt-Spalten-Wert auf dem ersten Speicher"
    assert await imd(db, klein.id, JAHR, MONAT) == {"ladung_kwh": 15.0, "entladung_kwh": 12.0}
    md = await monatszeile(db, anlage.id, JAHR, MONAT)
    assert (md.batterie_ladung_kwh, md.batterie_entladung_kwh) == (50.0, 40.0)
    assert any("proportional nach Kapazität auf 2 Speicher verteilt" in w for w in erg.warnungen), erg.warnungen


async def test_speicher_spalte_neben_alt_spalte_gilt(db):
    anlage, (akku,) = await _anlage(db, ("speicher", "Akku", {"kapazitaet_kwh": 7.0}))
    erg = await _csv_import(db, anlage.id, _datei(["Akku_Ladung_kWh", "Batterie_Ladung_kWh"], [JAHR, MONAT, 1, 2, 30, 80]),
                            haken=True)

    assert erg.erfolg
    assert await imd(db, akku.id, JAHR, MONAT) == {"ladung_kwh": 30.0}, \
        "N-747: die Warnung sagt «Speicher-Werte werden verwendet» — dann trägt das Gerät den Speicher-Wert, nicht 80"
    assert any("Speicher-Werte werden verwendet" in w for w in erg.warnungen), erg.warnungen


async def test_alt_ladung_neben_entladung_eines_anderen_speichers_ohne_haken(db):
    anlage, (akku, klein) = await _anlage(db, *ZWEI_SPEICHER)
    await _csv_import(db, anlage.id, _datei(["Klein_Entladung_kWh", "Batterie_Ladung_kWh"], [JAHR, MONAT, 1, 2, 12, 20]),
                      haken=False)

    assert await imd(db, akku.id, JAHR, MONAT) is None, "N-747: auch ohne Haken keine Alt-Ladung auf den ersten Speicher"
    assert await imd(db, klein.id, JAHR, MONAT) == {"entladung_kwh": 12.0}


async def test_ein_speicher_alt_spalten_bleiben_lesbar(db):
    anlage, (akku,) = await _anlage(db, ("speicher", "Akku", {"kapazitaet_kwh": 7.0}))
    await _csv_import(db, anlage.id, _datei(["Batterie_Ladung_kWh", "Batterie_Entladung_kWh"], [JAHR, MONAT, 1, 2, 50.25, 40]),
                      haken=True)

    assert await imd(db, akku.id, JAHR, MONAT) == {"ladung_kwh": 50.25, "entladung_kwh": 40.0}, \
        "Kompatibilität: ein Speicher, keine Geräte-Spalte — der Wert kommt exakt an (Bestand)"


# ── N-747 · E-Auto, Wallbox, Wärmepumpe ──────────────────────────────────────────────────────────────────────────

#: typ, zwei Bezeichnungen, Alt-Spalten mit Werten, Geräte-Spalte (Suffix) des ersten Geräts, deren Feld, Muster
TYPEN = [
    ("e-auto", ("Smart", "Zweit"), {"EAuto_km": 800, "EAuto_Verbrauch_kWh": 150}, ("Smart_km", "km_gefahren"), "EAuto_*"),
    ("wallbox", ("Garage", "Carport"), {"Wallbox_Ladung_kWh": 140, "Wallbox_Ladevorgaenge": 7},
     ("Garage_Ladung_kWh", "ladung_kwh"), "Wallbox_*"),
    ("waermepumpe", ("Keller", "Pool"), {"WP_Strom_kWh": 300, "WP_Heizung_kWh": 1200},
     ("Keller_Strom_kWh", "stromverbrauch_kwh"), "WP_*"),
]


@pytest.mark.parametrize("haken", [True, False])
@pytest.mark.parametrize("typ,namen,alt,geraete_spalte,muster", TYPEN, ids=[t[0] for t in TYPEN])
async def test_zwei_geraete_eines_typs_bekommen_keine_alt_spalte(db, typ, namen, alt, geraete_spalte, muster, haken):
    anlage, (erstes, zweites) = await _anlage(db, (typ, namen[0], None), (typ, namen[1], None))
    erg = await _csv_import(db, anlage.id, _datei(list(alt), [JAHR, MONAT, 1, 2, *alt.values()]), haken=haken)

    assert erg.erfolg and erg.importiert == 1
    assert await imd(db, erstes.id, JAHR, MONAT) is None, \
        f"N-747: der Typ-Wert ({', '.join(alt)}) gehört keinem der zwei Geräte — nichts aufs erste"
    assert await imd(db, zweites.id, JAHR, MONAT) is None
    assert any(w.startswith(f"Alt-Spalten {muster} nicht zugeordnet: 2 ") for w in erg.warnungen), erg.warnungen


@pytest.mark.parametrize("typ,namen,alt,geraete_spalte,muster", TYPEN, ids=[t[0] for t in TYPEN])
async def test_geraete_spalte_schlaegt_alt_spalte(db, typ, namen, alt, geraete_spalte, muster):
    anlage, (geraet,) = await _anlage(db, (typ, namen[0], None))
    spalte, feld = geraete_spalte
    erste_alt = next(iter(alt))
    erg = await _csv_import(db, anlage.id, _datei([spalte, erste_alt], [JAHR, MONAT, 1, 2, 999, alt[erste_alt]]), haken=True)

    assert erg.erfolg
    assert (await imd(db, geraet.id, JAHR, MONAT))[feld] == 999.0, \
        f"N-747: die Geräte-Spalte {spalte} gilt, die Alt-Spalte {erste_alt} überschreibt sie nicht"
    assert f"Alt-Spalten {muster} nicht zugeordnet: Geräte-Spalte vorhanden — es gelten die Werte der Geräte-Spalte." \
        in erg.warnungen


@pytest.mark.parametrize("typ,namen,alt,geraete_spalte,muster", TYPEN, ids=[t[0] for t in TYPEN])
async def test_ein_geraet_ohne_geraete_spalte_liest_alt_spalte(db, typ, namen, alt, geraete_spalte, muster):
    anlage, (geraet,) = await _anlage(db, (typ, namen[0], None))
    erg = await _csv_import(db, anlage.id, _datei(list(alt), [JAHR, MONAT, 1, 2, *alt.values()]), haken=True)

    assert erg.erfolg and erg.warnungen == []
    assert await imd(db, geraet.id, JAHR, MONAT), "Kompatibilität: ein Gerät, keine Geräte-Spalte — die Alt-Spalte kommt an"


async def test_geraet_heisst_wie_die_alt_spalte(db):
    """Eine Wallbox namens «Wallbox»: `Wallbox_Ladung_kWh` ist zugleich ihre Geräte-Spalte (v09 trifft sie). Das ist kein
    Konflikt — kein «nicht zugeordnet», der Wert kommt an."""
    anlage, (wb,) = await _anlage(db, ("wallbox", "Wallbox", None))
    erg = await _csv_import(db, anlage.id, _datei(["Wallbox_Ladung_kWh"], [JAHR, MONAT, 1, 2, 140]), haken=True)

    assert erg.erfolg and erg.warnungen == []
    assert await imd(db, wb.id, JAHR, MONAT) == {"ladung_kwh": 140.0}


def test_alt_spalten_liste_gleich_den_lesungen_des_schreibers():
    """`LEGACY_GERAETE_SPALTEN` nennt genau die Spalten, die der Legacy-Schreiber liest — sonst zählte eine neue Alt-Spalte
    als Geräte-Spalte (`csv_operations._typen_mit_geraete_spalte`)."""
    from backend.api.routes.import_export import helpers

    gelesen = set(re.findall(r'row\.get\("(\w+)"', inspect.getsource(helpers._import_investition_monatsdaten_legacy)))
    assert gelesen == {s for spalten in helpers.LEGACY_GERAETE_SPALTEN.values() for s in spalten}


# ── N-748 · je Zeile ganz oder gar nicht ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("haken", [True, False])
async def test_fehlerhafte_zeile_hinterlaesst_keinen_geraetewert(db, haken):
    anlage, (modul,) = await _anlage(db, ("pv-module", "Sueddach", None))
    erg = await _csv_import(db, anlage.id, _datei(["Sueddach_kWh", "PV_Erzeugung_kWh"], [JAHR, MONAT, 50, 200, 300, "abc"]),
                            haken=haken)

    assert (erg.erfolg, erg.importiert) == (False, 0)
    assert erg.fehler and erg.fehler[0].startswith("Zeile 2: Ungültiger Wert")
    assert await imd(db, modul.id, JAHR, MONAT) is None, "N-748: kein Gerätewert ohne Monatszeile"
    assert await monatszeile(db, anlage.id, JAHR, MONAT) is None


async def test_nach_der_fehlerzeile_kommt_die_naechste_an(db):
    anlage, (modul,) = await _anlage(db, ("pv-module", "Sueddach", None))
    erg = await _csv_import(db, anlage.id, _datei(["Sueddach_kWh", "PV_Erzeugung_kWh"],
                                                  [JAHR, 3, 50, 200, 300, "abc"], [JAHR, 4, 50, 200, 310, 310]), haken=False)

    assert erg.importiert == 1 and len(erg.fehler) == 1
    assert await imd(db, modul.id, JAHR, 3) is None
    assert await imd(db, modul.id, JAHR, 4) == {"pv_erzeugung_kwh": 310.0}
    assert (await monatszeile(db, anlage.id, JAHR, 4)).pv_erzeugung_kwh == 310.0


async def test_fehler_im_legacy_block_laesst_den_bestand_stehen(db):
    """Die Monatszeile wird VOR den Alt-Spalten geschrieben; scheitert danach `Wallbox_Ladevorgaenge` «inf», blieb bis
    13.10.2026 die überschriebene Monatszeile stehen. Jetzt gilt der Bestand."""
    anlage, (wb,) = await _anlage(db, ("wallbox", "Garage", None))
    db.add(factories.mach_monatsdaten(anlage.id, JAHR, MONAT, einspeisung_kwh=11.0, netzbezug_kwh=22.0))
    await db.commit()

    erg = await _csv_import(db, anlage.id, _datei(["Wallbox_Ladevorgaenge"], [JAHR, MONAT, 1, 2, "inf"]), haken=True)

    assert erg.importiert == 0 and erg.fehler[0].startswith("Zeile 2: Fehler")
    md = await monatszeile(db, anlage.id, JAHR, MONAT)
    assert (md.einspeisung_kwh, md.netzbezug_kwh) == (11.0, 22.0), "N-748: die Zeile schreibt ganz oder gar nicht"
    assert await imd(db, wb.id, JAHR, MONAT) is None


class _Abbruch(BaseException):
    """Ein Abbruch, den `_importiere_zeile` nicht fängt (wie `asyncio.CancelledError` beim Verbindungsabbruch)."""


async def test_abbruch_der_anfrage_rollt_alle_zeilen_zurueck(db, monkeypatch):
    """Der äußere SAVEPOINT: SQLite beginnt die Transaktion mit dem ersten SAVEPOINT selbst, das RELEASE der ersten
    Zeilen-Klammer committete sie ohne die äußere Klammer — ein Abbruch in Zeile 2 ließe Zeile 1 stehen. Mit ihr rollt
    der Abbruch (Rollback in `get_db`) alle Zeilen zurück, wie vor N-748."""
    from backend.api.routes.import_export import csv_operations

    anlage, (modul,) = await _anlage(db, ("pv-module", "Sueddach", None))
    anlage_id, modul_id = anlage.id, modul.id
    original = csv_operations._wetter_nachholen
    aufrufe = []

    async def _wetter_bricht_in_zeile_2_ab(*args, **kwargs):
        aufrufe.append(args[-1])
        if len(aufrufe) == 2:
            raise _Abbruch()
        return await original(*args, **kwargs)

    monkeypatch.setattr(csv_operations, "_wetter_nachholen", _wetter_bricht_in_zeile_2_ab)
    with pytest.raises(_Abbruch):
        await _csv_import(db, anlage_id, _datei(["Sueddach_kWh"], [JAHR, 3, 1, 2, 300], [JAHR, 4, 1, 2, 310]), haken=False)
    await db.rollback()

    assert await monatszeile(db, anlage_id, JAHR, 3) is None, "N-748: Zeile 1 ist nach dem Abbruch nicht dauerhaft"
    assert await imd(db, modul_id, JAHR, 3) is None
