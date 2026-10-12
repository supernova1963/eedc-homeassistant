"""N-702 — der `inv:`-Weg des Custom-Imports summiert das Monats-Aggregat nur über `aggregiert_in` der Registry.

Bis 12.10.2026 summierte `apply.py` jeden `inv:`-Wert nach seinem **Feldnamen** ins Aggregat der Monatszeile,
zusätzlich zu dem, was v09 für dieselbe Spalte schon gezählt hatte:

* eine automatisch erkannte Geräte-Spalte, im Dropdown zusätzlich auf ihren eigenen `inv:`-Slot gelegt (#222 hat
  das eingestellt), ergab PV **600 statt 300** — und weil das Aggregat die Lücke jedes Moduls ohne eigenen Wert
  füllt (P7), zeigte das Cockpit für den Monat 600;
* `ladung_kwh` einer **Wallbox** oder eines **E-Autos** landete im Batterie-Aggregat (Z1) — die Monatsliste
  meldete danach «Legacy-Daten», ohne dass es einen Speicher gab.

Wächter (Klassen-Dreifrage): je Pfad eine Probe — Doppelzuordnung ⇒ einmal, Wallbox/E-Auto ⇒ kein Batterie-Wert,
Speicher-Slot ⇒ weiter im Batterie-Aggregat (die Registry-Regel greift, sie schaltet nichts ab).
Schwestern: `test_n706_custom_import_vorschau_gleich_import.py` (derselbe Kern), `test_custom_import_preview_inv_werte.py`.
"""

from __future__ import annotations

from backend.services.pv_monatswerte import lade_pv_je_monat, pv_summe_je_monat
from backend.tests import factories
from backend.tests.custom_import_hilfen import csv_text, imd, importiere, monatszeile


async def _anlage_zwei_daecher(db):
    anlage = await factories.anlage(db)
    sued = await factories.investition(db, anlage.id, "pv-module", bezeichnung="Sueddach", leistung_kwp=6.0)
    nord = await factories.investition(db, anlage.id, "pv-module", bezeichnung="Norddach", leistung_kwp=4.0)
    return anlage, sued, nord


async def test_doppelt_zugeordnete_geraete_spalte_zaehlt_einmal(db):
    """B1-a: `Sueddach_kWh` wird automatisch erkannt UND steht im Dropdown auf `inv:<Süd>:pv_erzeugung_kwh`."""
    anlage, sued, nord = await _anlage_zwei_daecher(db)
    text = csv_text(["Jahr", "Monat", "Sueddach_kWh", "Einsp"], [2025, 3, 300, 100])

    antwort = await importiere(
        db, anlage.id, text,
        [("Jahr", "jahr"), ("Monat", "monat"), ("Sueddach_kWh", f"inv:{sued.id}:pv_erzeugung_kwh"),
         ("Einsp", "einspeisung_kwh")],
        [(2025, 3)],
    )

    assert antwort.erfolg, antwort.fehler
    assert await imd(db, sued.id, 2025, 3) == {"pv_erzeugung_kwh": 300.0}
    md = await monatszeile(db, anlage.id, 2025, 3)
    assert md.pv_erzeugung_kwh == 300.0, "die Spalte zählt im Aggregat einmal, nicht zweimal"

    # Was der Anwender sieht (P7-Auflösung, Cockpit → Monat): Norddach hat keinen Wert, das Aggregat füllt die Lücke.
    monate = await lade_pv_je_monat(db, anlage.id, [sued, nord], 2025)
    assert pv_summe_je_monat(monate)[(2025, 3)] == 300.0


async def test_wallbox_und_eauto_ladung_landen_nicht_im_batterie_aggregat(db):
    """Z1: `ladung_kwh` der Wallbox und des E-Autos hat in der Registry kein `aggregiert_in`."""
    anlage = await factories.anlage(db)
    wb = await factories.investition(db, anlage.id, "wallbox", bezeichnung="Wallbox Garage")
    ea = await factories.investition(db, anlage.id, "e-auto", bezeichnung="Smart")
    text = csv_text(["Jahr", "Monat", "WB", "EA", "Einsp"], [2025, 3, 120, 80, 5])

    antwort = await importiere(
        db, anlage.id, text,
        [("Jahr", "jahr"), ("Monat", "monat"), ("WB", f"inv:{wb.id}:ladung_kwh"),
         ("EA", f"inv:{ea.id}:ladung_kwh"), ("Einsp", "einspeisung_kwh")],
        [(2025, 3)],
    )

    assert antwort.erfolg, antwort.fehler
    assert await imd(db, wb.id, 2025, 3) == {"ladung_kwh": 120.0}
    assert await imd(db, ea.id, 2025, 3) == {"ladung_kwh": 80.0}
    md = await monatszeile(db, anlage.id, 2025, 3)
    assert md.batterie_ladung_kwh is None, f"Wallbox-/E-Auto-Ladung im Batterie-Aggregat: {md.batterie_ladung_kwh}"
    assert md.batterie_entladung_kwh is None


async def test_speicher_slot_zaehlt_weiter_ins_batterie_aggregat(db):
    """Gegenprobe: die Registry-Regel schaltet nichts ab — ein Speicher-Slot trägt sein `aggregiert_in`."""
    anlage = await factories.anlage(db)
    sp = await factories.investition(db, anlage.id, "speicher", bezeichnung="Akku", parameter={"kapazitaet_kwh": 10.0})
    text = csv_text(["Jahr", "Monat", "L", "E", "Einsp"], [2025, 3, 40, 35, 5])

    antwort = await importiere(
        db, anlage.id, text,
        [("Jahr", "jahr"), ("Monat", "monat"), ("L", f"inv:{sp.id}:ladung_kwh"),
         ("E", f"inv:{sp.id}:entladung_kwh"), ("Einsp", "einspeisung_kwh")],
        [(2025, 3)],
    )

    assert antwort.erfolg, antwort.fehler
    md = await monatszeile(db, anlage.id, 2025, 3)
    assert (md.batterie_ladung_kwh, md.batterie_entladung_kwh) == (40.0, 35.0)
