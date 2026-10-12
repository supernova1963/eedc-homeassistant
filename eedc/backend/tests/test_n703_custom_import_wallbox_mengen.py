"""N-703 — der Custom-Import schreibt `wallbox_ladung_kwh`/`wallbox_ladung_pv_kwh` wie der Portal-Import.

Dropdown und Auto-Mapping bieten beide Felder seit v2.8.0 an (`_shared.EEDC_FIELDS`, `analyze._auto_detect_mapping`:
`Wallbox_kWh → wallbox_ladung_kwh`), der Schreibweg hatte nie einen Zweig dafür: der Import meldete Erfolg und
schrieb nichts (N-302: «der Import darf nie still etwas wegwerfen»). Jetzt gilt das Vorbild
`data_import._schreibe_wallbox`: die Wallbox ist die Quelle (Konzept Wallbox/E-Auto), `ladung_netz_kwh` = Gesamt − PV.
Ohne Wallbox ist der Monat ein Zeilenfehler.

Klassen-Wächter «Feld angeboten, aber nicht geschrieben»: jedes Zielfeld aus `EEDC_FIELDS` (außer Jahr/Monat) kommt
nach dem Import in der Datenbank an. Schwestern: `test_n702_custom_import_aggregat_registry.py`,
`test_import_ziel_investition_349.py` (Portal-Import).
"""

from __future__ import annotations

from backend.api.routes.custom_import._shared import EEDC_FIELDS
from backend.tests import factories
from backend.tests.custom_import_hilfen import csv_text, imd, importiere, monatszeile, vorschau

JM = [("Jahr", "jahr"), ("Monat", "monat")]


async def test_wallbox_mengen_landen_auf_der_wallbox(db):
    anlage = await factories.anlage(db)
    wb = await factories.investition(db, anlage.id, "wallbox", bezeichnung="Wallbox Garage")
    text = csv_text(["Jahr", "Monat", "WBL", "WBPV", "LV"], [2025, 3, 120, 80, 7])

    antwort = await importiere(
        db, anlage.id, text,
        [*JM, ("WBL", "wallbox_ladung_kwh"), ("WBPV", "wallbox_ladung_pv_kwh"), ("LV", "wallbox_ladevorgaenge")],
        [(2025, 3)],
    )

    assert antwort.erfolg, antwort.fehler
    assert await imd(db, wb.id, 2025, 3) == {
        "ladung_kwh": 120.0, "ladung_pv_kwh": 80.0, "ladung_netz_kwh": 40.0, "ladevorgaenge": 7,
    }
    # Die Vorschau zeigt dieselbe Menge, die geschrieben wurde.
    v = await vorschau(db, anlage.id, text, [*JM, ("WBL", "wallbox_ladung_kwh"), ("WBPV", "wallbox_ladung_pv_kwh")])
    assert (v.monate[0].wallbox_ladung_kwh, v.monate[0].wallbox_ladung_pv_kwh) == (120.0, 80.0)


async def test_wallbox_menge_ohne_wallbox_ist_ein_zeilenfehler(db):
    anlage = await factories.anlage(db)
    text = csv_text(["Jahr", "Monat", "WBL", "Einsp"], [2025, 3, 120, 5])

    antwort = await importiere(db, anlage.id, text, [*JM, ("WBL", "wallbox_ladung_kwh"), ("Einsp", "einspeisung_kwh")],
                               [(2025, 3)])

    assert not antwort.erfolg
    assert antwort.importiert == 0
    assert "keine Wallbox" in antwort.fehler[0]
    assert await monatszeile(db, anlage.id, 2025, 3) is None, "der Monat wird ganz oder gar nicht geschrieben"


async def test_jedes_angebotene_zielfeld_kommt_an(db):
    """Klasse: alle `EEDC_FIELDS` außer Jahr/Monat — jeder Wert steht danach in der Monatszeile oder am Gerät."""
    anlage = await factories.anlage(db)
    await factories.investition(db, anlage.id, "pv-module", bezeichnung="Dach", leistung_kwp=10.0)
    await factories.investition(db, anlage.id, "speicher", bezeichnung="Akku", parameter={"kapazitaet_kwh": 10.0})
    wb = await factories.investition(db, anlage.id, "wallbox", bezeichnung="WB")
    ea = await factories.investition(db, anlage.id, "e-auto", bezeichnung="Auto")

    werte = {
        "pv_erzeugung_kwh": 500.0, "einspeisung_kwh": 200.0, "netzbezug_kwh": 150.0, "eigenverbrauch_kwh": 300.0,
        "batterie_ladung_kwh": 40.0, "batterie_entladung_kwh": 35.0, "wallbox_ladung_kwh": 120.0,
        "wallbox_ladung_pv_kwh": 80.0, "wallbox_ladevorgaenge": 7, "eauto_km_gefahren": 900.0,
    }
    felder = [f["id"] for f in EEDC_FIELDS if f["id"] not in ("jahr", "monat")]
    assert sorted(felder) == sorted(werte), "ein neues Zielfeld braucht hier einen Wert — und einen Schreibweg"
    spalten = [f"S{i}" for i in range(len(felder))]
    text = csv_text(["Jahr", "Monat", *spalten], [2025, 3, *(werte[f] for f in felder)])

    antwort = await importiere(db, anlage.id, text, [*JM, *zip(spalten, felder)], [(2025, 3)])
    assert antwort.erfolg, antwort.fehler

    md = await monatszeile(db, anlage.id, 2025, 3)
    wb_d = await imd(db, wb.id, 2025, 3) or {}
    ea_d = await imd(db, ea.id, 2025, 3) or {}
    angekommen = {
        "pv_erzeugung_kwh": md.pv_erzeugung_kwh,
        "einspeisung_kwh": md.einspeisung_kwh,
        "netzbezug_kwh": md.netzbezug_kwh,
        "eigenverbrauch_kwh": md.eigenverbrauch_kwh,
        "batterie_ladung_kwh": md.batterie_ladung_kwh,
        "batterie_entladung_kwh": md.batterie_entladung_kwh,
        "wallbox_ladung_kwh": wb_d.get("ladung_kwh"),
        "wallbox_ladung_pv_kwh": wb_d.get("ladung_pv_kwh"),
        "wallbox_ladevorgaenge": wb_d.get("ladevorgaenge"),
        "eauto_km_gefahren": ea_d.get("km_gefahren"),
    }
    fehlt = {f: werte[f] for f in felder if angekommen[f] != werte[f]}
    assert not fehlt, f"angeboten, aber nicht geschrieben: {fehlt}"
