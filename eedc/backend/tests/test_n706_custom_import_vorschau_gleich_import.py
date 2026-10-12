"""N-706 — die Vorschau des Custom-Imports zeigt, was der Import schreibt (Prinzip N-666).

Vorschau (`preview.py::_apply_mapping`) und Import (`apply.py`) lasen dieselbe Zeile bis 12.10.2026 mit zwei
Handschriften (RF-10 §4.6). Gemessen: Geräte-Spalten in Wh zeigte die Vorschau als Tausendstel (300), der Import
schrieb sie roh (Cockpit 500 000 kWh), km ebenso (0,9 statt 900); Tageszeilen wurden im Import zum ersten bzw.
letzten Tag des Monats («31 importiert»); «Jahr 0» bot die Vorschau an, der Import übersprang es still.

Seitdem lesen beide über einen Kern (`_shared.plane_zuordnung` + `lies_monate`). Regeln (Entscheid Master 12.10.):
die Einheit im Namen einer Geräte-Spalte gilt (keine Umrechnung); mehrere Zeilen eines Monats werden summiert wie im
Portal-Import — nur Mengenwerte, ein Stand in mehreren Zeilen ist ein Zeilenfehler; Jahr 0 ist ungültig.

Wächter: «Vorschau-Zahl = geschriebene Zahl» je Fall. Schwestern: `test_custom_import_preview_inv_werte.py`,
`test_custom_import_einheit_non_energy.py`, `test_n702_custom_import_aggregat_registry.py`.
"""

from __future__ import annotations

from backend.tests import factories
from backend.tests.custom_import_hilfen import csv_text, imd, importiere, monatszeile, vorschau

JM = [("Jahr", "jahr"), ("Monat", "monat")]


async def _anlage(db):
    anlage = await factories.anlage(db)
    sued = await factories.investition(db, anlage.id, "pv-module", bezeichnung="Sueddach", leistung_kwp=6.0)
    nord = await factories.investition(db, anlage.id, "pv-module", bezeichnung="Norddach", leistung_kwp=4.0)
    auto = await factories.investition(db, anlage.id, "e-auto", bezeichnung="Smart #1")
    return anlage, sued, nord, auto


async def test_geraete_spalten_in_wh_vorschau_gleich_import(db):
    """B4: `_kWh`/`_km` im Spaltennamen gilt — weder Vorschau noch Import rechnen diese Spalten um."""
    anlage, sued, nord, auto = await _anlage(db)
    text = csv_text(["Jahr", "Monat", "Einsp", "Sueddach_kWh", "Norddach_kWh", "Smart_1_km"],
                    [2025, 3, 100000, 300, 200, 900])
    zuordnung = [*JM, ("Einsp", "einspeisung_kwh")]

    v = await vorschau(db, anlage.id, text, zuordnung, einheit="wh")
    antwort = await importiere(db, anlage.id, text, zuordnung, [(2025, 3)], einheit="wh")
    assert antwort.erfolg, antwort.fehler

    gezeigt = v.monate[0].inv_werte
    geschrieben = {
        "Sueddach_kWh": (await imd(db, sued.id, 2025, 3))["pv_erzeugung_kwh"],
        "Norddach_kWh": (await imd(db, nord.id, 2025, 3))["pv_erzeugung_kwh"],
        "Smart_1_km": (await imd(db, auto.id, 2025, 3))["km_gefahren"],
    }
    assert gezeigt == geschrieben == {"Sueddach_kWh": 300.0, "Norddach_kWh": 200.0, "Smart_1_km": 900.0}
    # Die Spalte OHNE Einheit im Namen rechnet die globale Einheit um — in beiden gleich.
    md = await monatszeile(db, anlage.id, 2025, 3)
    assert v.monate[0].einspeisung_kwh == md.einspeisung_kwh == 100.0


async def test_tageszeilen_werden_je_monat_summiert(db):
    """V6: 31 Tageszeilen eines Monats ⇒ ein Monat mit der Summe (Vorbild Portal-Import), nicht der erste/letzte Tag."""
    anlage, sued, _nord, _auto = await _anlage(db)
    zeilen = [[f"2025-03-{t:02d}", t, 1] for t in range(1, 32)]
    text = csv_text(["Datum", "PV", "Einsp"], *zeilen)
    zuordnung = [("PV", "pv_erzeugung_kwh"), ("Einsp", "einspeisung_kwh")]

    v = await vorschau(db, anlage.id, text, zuordnung, datum_spalte="Datum")
    assert [(m.jahr, m.monat) for m in v.monate] == [(2025, 3)], "ein Monat, nicht 31 gleiche Zeilen"
    assert (v.monate[0].pv_erzeugung_kwh, v.monate[0].einspeisung_kwh) == (496.0, 31.0)

    for haken in (False, True):
        antwort = await importiere(db, anlage.id, text, zuordnung, [(2025, 3)], ueberschreiben=haken,
                                   datum_spalte="Datum")
        assert antwort.erfolg, antwort.fehler
        md = await monatszeile(db, anlage.id, 2025, 3)
        assert (md.pv_erzeugung_kwh, md.einspeisung_kwh) == (496.0, 31.0), f"Haken={haken}"
    assert (antwort.importiert, antwort.uebersprungen) == (1, 0)


async def test_tageszeilen_mit_geraete_spalten_summieren_auch_am_geraet(db):
    anlage, sued, _nord, _auto = await _anlage(db)
    text = csv_text(["Datum", "Sueddach_kWh"], ["2025-03-01", "10,5"], ["2025-03-02", "11,25"])

    v = await vorschau(db, anlage.id, text, [], datum_spalte="Datum", dezimal="komma")
    antwort = await importiere(db, anlage.id, text, [], [(2025, 3)], datum_spalte="Datum", dezimal="komma")

    assert antwort.erfolg, antwort.fehler
    assert v.monate[0].inv_werte["Sueddach_kWh"] == (await imd(db, sued.id, 2025, 3))["pv_erzeugung_kwh"] == 21.75
    assert (await monatszeile(db, anlage.id, 2025, 3)).pv_erzeugung_kwh == 21.75


async def test_ein_stand_in_mehreren_zeilen_eines_monats_ist_ein_zeilenfehler(db):
    """Nur Mengen lassen sich summieren: ein Tachostand je Tag ergäbe als Summe Unsinn — der Monat wird nicht
    geschrieben, die Vorschau sagt es und bietet ihn nicht an."""
    anlage, _sued, _nord, auto = await _anlage(db)
    text = csv_text(["Datum", "Tacho", "Einsp"], ["2025-03-01", 1000, 1], ["2025-03-02", 1010, 1],
                    ["2025-04-01", 1020, 1])
    zuordnung = [("Tacho", f"inv:{auto.id}:km_stand"), ("Einsp", "einspeisung_kwh")]

    v = await vorschau(db, anlage.id, text, zuordnung, datum_spalte="Datum")
    assert [(m.jahr, m.monat) for m in v.monate] == [(2025, 4)], "ein Stand in EINER Zeile des Monats bleibt erlaubt"
    assert any("kein Mengenwert" in w for w in v.warnungen), v.warnungen

    antwort = await importiere(db, anlage.id, text, zuordnung, [(2025, 3)], datum_spalte="Datum")
    assert not antwort.erfolg and "kein Mengenwert" in antwort.fehler[0]
    assert await monatszeile(db, anlage.id, 2025, 3) is None


async def test_jahr_null_bietet_die_vorschau_nicht_an(db):
    """V5: der Import nahm Jahr 0 nie (`not jahr`) — die Vorschau bietet ihn nicht mehr an und zählt die Zeile."""
    anlage, *_ = await _anlage(db)
    text = csv_text(["Jahr", "Monat", "Einsp"], [0, 8, 5], [2025, 8, 6])

    v = await vorschau(db, anlage.id, text, [*JM, ("Einsp", "einspeisung_kwh")])

    assert [(m.jahr, m.monat) for m in v.monate] == [(2025, 8)]
    assert any("1 Zeilen übersprungen" in w for w in v.warnungen), v.warnungen
