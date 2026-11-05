"""Benannte Proben für RF-59/RF-60: Demo-Daten (`create_demo_data`) und CSV-Export (`export_csv`) in Phasen.

Schwesterdateien: test_demo_bestand_sonstiges_verbraucher.py (Demo-Bestand beider Sonstiges-Richtungen),
test_341_live_merkmale.py (Demo-Knoten nehmen die IDs der Anlage, WP = ID 4 wie `create_demo_data`).
Golden Master: `~/.claude/plans/skript-golden-master-demo-daten.py` (Dump aller Tabellen) und
`~/.claude/plans/skript-golden-master-csv-export.py` (drei DB-Kopien + Fixture-Fälle) — diese Proben halten die Zweige,
die bis RF-60 kein Test berührte (`export_csv` hatte keinen direkten Test), auch ohne die Ablagen fest.

Die Proben prüfen Verhalten, nicht die Phasenform; sie sind am HEAD vor dem Schnitt grün gefahren.
"""

import csv
from datetime import date
from io import StringIO

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.models.pvgis_prognose import PVGISMonatsprognose, PVGISPrognose
from backend.models.strompreis import Strompreis

pytestmark = pytest.mark.asyncio


# ── Demo-Daten ─────────────────────────────────────────────────────────────────────────────────────────────────────

async def _zeilenzahlen(db) -> dict[str, int]:
    out = {}
    for modell in (Anlage, Strompreis, Investition, Monatsdaten, InvestitionMonatsdaten, PVGISPrognose, PVGISMonatsprognose):
        out[modell.__tablename__] = (await db.execute(select(func.count()).select_from(modell))).scalar_one()
    return out


async def test_demo_antwort_und_mengen(db):
    from backend.api.routes.import_export.demo_data import create_demo_data

    antwort = await create_demo_data(db=db)
    await db.commit()
    assert antwort.model_dump() == {
        "erfolg": True,
        "anlage_id": 1,
        "anlage_name": "Demo-Anlage",
        "monatsdaten_count": 31,
        "investitionen_count": 11,
        "strompreise_count": 3,
        "message": "Demo-Anlage mit 31 Monatsdaten, 11 Investitionen und 3 Strompreisen erstellt.",
    }
    # Handgriff 5.11.2026: die gemeldete Zahl ist die der angelegten Zeilen (bis dahin fest «10» bei elf Geräten).
    zeilen = await _zeilenzahlen(db)
    assert antwort.investitionen_count == zeilen["investitionen"]
    assert f"{zeilen['investitionen']} Investitionen" in antwort.message
    assert zeilen == {
        "anlagen": 1, "strompreise": 3, "investitionen": 11, "monatsdaten": 31, "investition_monatsdaten": 248,
        "pvgis_prognosen": 1, "pvgis_monatsprognosen": 12,
    }


async def test_demo_geraete_ids_in_reihenfolge(db):
    """Reihenfolge ist Vertrag: IDs 1…11 in Anlage-Reihenfolge, WP = ID 4 (`live_dashboard.py` verlässt sich darauf)."""
    from backend.api.routes.import_export.demo_data import create_demo_data

    await create_demo_data(db=db)
    await db.commit()
    invs = (await db.execute(select(Investition).order_by(Investition.id))).scalars().all()
    assert [(i.id, i.typ, i.bezeichnung) for i in invs] == [
        (1, "wechselrichter", "Fronius Symo GEN24 10.0 Plus"),
        (2, "speicher", "BYD HVS 15.4"),
        (3, "e-auto", "Tesla Model 3 LR"),
        (4, "waermepumpe", "Daikin Altherma 3 H HT"),
        (5, "wallbox", "go-eCharger HOMEfix 11kW"),
        (6, "pv-module", "Süddach"),
        (7, "pv-module", "Ostdach"),
        (8, "pv-module", "Westdach"),
        (9, "balkonkraftwerk", "Balkon Süd"),
        (10, "sonstiges", "Mini-BHKW"),
        (11, "sonstiges", "Heizstab Warmwasser"),
    ]
    # Speicher und PV-Strings hängen am Wechselrichter (Flush vor den Kindern)
    assert {i.id: i.parent_investition_id for i in invs if i.parent_investition_id} == {2: 1, 6: 1, 7: 1, 8: 1}
    sp = (await db.execute(select(Strompreis).order_by(Strompreis.id))).scalars().all()
    assert [(s.id, s.tarifname, s.gueltig_ab) for s in sp] == [
        (1, "Standardtarif 2023", date(2023, 6, 1)),
        (2, "Standardtarif 2024", date(2024, 4, 1)),
        (3, "M-Strom Privat", date(2025, 1, 1)),
    ]


async def test_demo_monatswerte_stichproben(db):
    """Stichproben der Monats-Absätze: Arbitrage ab 2025, BKW ab 3/2024, BHKW ab 10/2024, Heizstab ab 2025, PV-Anteile."""
    from backend.api.routes.import_export.demo_data import create_demo_data

    await create_demo_data(db=db)
    await db.commit()
    imd = {(r.investition_id, r.jahr, r.monat): r.verbrauch_daten
           for r in (await db.execute(select(InvestitionMonatsdaten))).scalars().all()}
    assert imd[(2, 2025, 1)] == {"ladung_kwh": 157.3, "entladung_kwh": 115.83, "ladung_netz_kwh": 31.5,
                                 "speicher_ladepreis_cent": 20}
    assert "ladung_netz_kwh" not in imd[(2, 2024, 12)]
    assert imd[(2, 2025, 3)]["sonstige_positionen"] == [{"bezeichnung": "Firmware-Update", "betrag": 95.0, "typ": "ausgabe"}]
    assert (9, 2024, 2) not in imd and imd[(9, 2024, 3)]["pv_erzeugung_kwh"] == 39.2
    assert (10, 2024, 9) not in imd and imd[(10, 2024, 10)] == {"erzeugung_kwh": 150}
    assert (11, 2024, 12) not in imd and imd[(11, 2025, 1)] == {"verbrauch_sonstig_kwh": 45}
    assert imd[(6, 2024, 6)] == {"pv_erzeugung_kwh": 857.6} and imd[(8, 2024, 12)] == {"pv_erzeugung_kwh": 27.4}
    assert imd[(5, 2024, 1)] == {"ladung_kwh": 212, "ladevorgaenge": 8}
    assert imd[(3, 2024, 11)]["sonstige_positionen"][1] == {"bezeichnung": "THG-Quote", "betrag": 85.0, "typ": "ertrag"}
    assert imd[(4, 2024, 10)]["sonstige_positionen"] == [{"bezeichnung": "Jahreswartung", "betrag": 180.0, "typ": "ausgabe"}]
    md = (await db.execute(select(Monatsdaten).where(Monatsdaten.jahr == 2023, Monatsdaten.monat == 6))).scalar_one()
    assert (md.einspeisung_kwh, md.netzbezug_kwh, md.datenquelle) == (517.08, 1.84, "demo")
    assert set(md.source_provenance) == {"einspeisung_kwh", "netzbezug_kwh", "globalstrahlung_kwh_m2", "sonnenstunden"}
    prog = (await db.execute(select(PVGISPrognose))).scalar_one()
    assert (prog.jahresertrag_kwh, prog.spezifischer_ertrag_kwh_kwp, prog.ist_aktiv) == (20000, 1000.0, True)


async def test_demo_zweiter_aufruf_ohne_zuwachs(db):
    """Existenz-Prüfung: der zweite Aufruf wirft 400 und legt nichts an."""
    from backend.api.routes.import_export.demo_data import create_demo_data

    await create_demo_data(db=db)
    await db.commit()
    vorher = await _zeilenzahlen(db)
    with pytest.raises(HTTPException) as fehler:
        await create_demo_data(db=db)
    await db.rollback()
    assert (fehler.value.status_code, fehler.value.detail) == (400, "Demo-Anlage existiert bereits. Bitte zuerst löschen.")
    assert await _zeilenzahlen(db) == vorher


# ── CSV-Export ─────────────────────────────────────────────────────────────────────────────────────────────────────

async def _export(db, anlage_id, jahr=None, include_investitionen=True):
    from backend.api.routes.import_export.csv_operations import export_csv

    resp = await export_csv(anlage_id, jahr=jahr, include_investitionen=include_investitionen, db=db)
    teile = [c if isinstance(c, str) else c.decode("utf-8") async for c in resp.body_iterator]
    return resp, "".join(teile)


def _tabelle(text):
    assert text.startswith("﻿")
    zeilen = list(csv.reader(StringIO(text[1:]), delimiter=";"))
    return zeilen[0], zeilen[1:]


async def _saat(db, *, name="Müller & Söhne; \"Süd\"", vertragsart="dynamisch", variabel=True):
    db.add(Anlage(id=1, anlagenname=name, leistung_kwp=10.0))
    await db.flush()
    db.add(Strompreis(anlage_id=1, netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
                      gueltig_ab=date(2020, 1, 1), vertragsart=vertragsart, einspeisung_variabel=variabel))
    for iid, typ, bez, param, aktiv in [
        (10, "wechselrichter", "WR", None, True),
        (11, "speicher", "Keller", {"arbitrage_faehig": True}, True),
        (12, "balkonkraftwerk", "Balkon", None, True),
        (13, "speicher", "Altspeicher", None, False),
    ]:
        db.add(Investition(id=iid, anlage_id=1, typ=typ, bezeichnung=bez, parameter=param, aktiv=aktiv))
    await db.flush()
    db.add(Monatsdaten(anlage_id=1, jahr=2024, monat=1, einspeisung_kwh=100.5, netzbezug_kwh=200,
                       netzbezug_durchschnittspreis_cent=0.0, einspeise_durchschnittspreis_cent=0, notizen="a;b"))
    db.add(Monatsdaten(anlage_id=1, jahr=2025, monat=2, einspeisung_kwh=1, netzbezug_kwh=2,
                       netzbezug_durchschnittspreis_cent=None, einspeise_durchschnittspreis_cent=None))
    for iid, j, m, vd in [
        (11, 2024, 1, {"ladung_kwh": 10, "speicher_ladung_netz_kwh": 2.5,
                       "sonstige_positionen": [{"bezeichnung": "Firmware", "betrag": 95.0, "typ": "ausgabe"},
                                               {"bezeichnung": "Bonus", "betrag": 20, "typ": "ertrag"}]}),
        (12, 2024, 1, {"erzeugung_kwh": 33.3}),
        (13, 2024, 1, {"ladung_kwh": 5.5}),
        (11, 2025, 2, {"ladung_netz_kwh": None, "speicher_ladung_netz_kwh": 4.4}),
    ]:
        db.add(InvestitionMonatsdaten(investition_id=iid, jahr=j, monat=m, verbrauch_daten=vd))
    await db.commit()


async def test_export_bom_semikolon_crlf_und_dezimalkomma(db):
    await _saat(db)
    resp, text = await _export(db, 1)
    assert resp.media_type == "text/csv; charset=utf-8"
    assert text.startswith("﻿Jahr;Monat;Einspeisung_kWh;Netzbezug_kWh;")
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    kopf, zeilen = _tabelle(text)
    assert zeilen[0][:4] == ["2024", "1", "100,5", "200,0"]
    assert zeilen[0][-1] == "a;b"


async def test_export_dateiname_mit_umlaut_und_sonderzeichen(db):
    """#220: Umlaute → ae/oe/ue, Sonderzeichen → _, ohne Jahr «alle»; ein zu "" bereinigter Name wird «anlage»."""
    await _saat(db)
    resp, _ = await _export(db, 1)
    assert resp.headers["content-disposition"] == 'attachment; filename="eedc_export_Mueller_Soehne_Sued_alle.csv"'
    resp, _ = await _export(db, 1, jahr=2024)
    assert resp.headers["content-disposition"].endswith('_Mueller_Soehne_Sued_2024.csv"')
    anlage = (await db.execute(select(Anlage))).scalar_one()
    anlage.anlagenname = "!!!"
    await db.commit()
    resp, _ = await _export(db, 1)
    assert resp.headers["content-disposition"] == 'attachment; filename="eedc_export_anlage_alle.csv"'


async def test_export_tarif_und_verguetungs_spalte(db):
    """Dynamischer Tarif ⇒ «Durchschnittspreis_Cent», #392 variable Vergütung ⇒ «Einspeiseverguetung_Cent»; 0 bleibt 0."""
    await _saat(db)
    kopf, zeilen = _tabelle((await _export(db, 1))[1])
    assert kopf[4:6] == ["Durchschnittspreis_Cent", "Einspeiseverguetung_Cent"]
    assert zeilen[0][4:6] == ["0,0", "0,0"]
    assert zeilen[1][4:6] == ["", ""]


async def test_export_ohne_dynamik_keine_preisspalten(db):
    await _saat(db, vertragsart="fix", variabel=False)
    kopf, _ = _tabelle((await _export(db, 1))[1])
    assert "Durchschnittspreis_Cent" not in kopf and "Einspeiseverguetung_Cent" not in kopf


async def test_export_fallback_keys(db):
    """Legacy-Schlüssel füllen eine leere kanonische Zelle; ein kanonisches None füllt sie nicht."""
    await _saat(db)
    kopf, zeilen = _tabelle((await _export(db, 1))[1])
    zeile = dict(zip(kopf, zeilen[0]))
    assert zeile["Keller_Netzladung_kWh"] == "2,5"
    assert zeile["Balkon_Erzeugung_kWh"] == "33,3"
    assert dict(zip(kopf, zeilen[1]))["Keller_Netzladung_kWh"] == ""


async def test_export_sonderkosten(db):
    await _saat(db)
    kopf, zeilen = _tabelle((await _export(db, 1))[1])
    zeile = dict(zip(kopf, zeilen[0]))
    assert zeile["Keller_Sonderkosten_Euro"] == "75,0"
    assert zeile["Keller_Sonderkosten_Notiz"] == "Firmware: 95.0€ (ausgabe); Bonus: 20€ (ertrag)"
    assert zeile["Balkon_Sonderkosten_Euro"] == "" and zeile["Balkon_Sonderkosten_Notiz"] == ""


async def test_export_inaktive_investition_bleibt_drin(db):
    """#123: kein aktiv-Filter — eine stillgelegte Komponente behält ihre Spalten und Werte; der Wechselrichter hat keine."""
    await _saat(db)
    kopf, zeilen = _tabelle((await _export(db, 1))[1])
    assert dict(zip(kopf, zeilen[0]))["Altspeicher_Ladung_kWh"] == "5,5"
    assert not any(k.startswith("WR_") for k in kopf)


async def test_export_jahr_und_ohne_investitionen(db):
    await _saat(db)
    kopf, zeilen = _tabelle((await _export(db, 1, jahr=2025, include_investitionen=False))[1])
    assert kopf == ["Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh", "Durchschnittspreis_Cent",
                    "Einspeiseverguetung_Cent", "Notizen"]
    assert zeilen == [["2025", "2", "1,0", "2,0", "", "", ""]]


async def test_export_unbekannte_anlage(db):
    with pytest.raises(HTTPException) as fehler:
        await _export(db, 4711)
    assert fehler.value.status_code == 404
