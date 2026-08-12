"""Hauszähler-Größen beim Stationsimport — Ollis Fall in allen Varianten (#349).

**Der Befund** (Gernot, 2026-08-12): Der gerätegebundene Import ließ Einspeisung
und Netzbezug weg, begründet mit ADR-002/P7 („eine von zwei Stationen ist eine
Teilsumme"). Fachlich falsch — ein Wechselrichter *misst* diese Größen nicht, er
bekommt sie vom **Smartmeter am Hausanschluss**. Zwei Wechselrichter an einem
Anschluss melden **denselben** Wert: redundant, nicht partiell. Verboten ist das
**Summieren**, nicht das Übernehmen.

**Die Wirkung beim Melder:** Import lief durch, die Modulwerte kamen an, eine
Monatszeile entstand nie — und kein erneuter Import konnte das heilen. Sichtbar
als „Monat fehlt" im Daten-Checker bei gleichzeitig richtigen Zahlen im Cockpit.

Die Datei deckt beide Ebenen ab: die **Entscheidungsregel** als reine Funktion
(schnell, alle Randfälle) und den **Import-Endpunkt** an echten ORM-Objekten
(zwei Stationen, Reihenfolge, Speicher, Überschreiben-Haken).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.api.routes.data_import import (
    ApplyMonthInput,
    ApplyRequest,
    apply_import,
)
from backend.models import Anlage, Investition
from backend.models.investition import InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.import_hauszaehler import (
    HauszaehlerQuelle,
    entscheide_hauszaehler,
    waehle_hauszaehler_quelle,
)


# ═══════════════════════════════════════════════════════════════════════════
# Ebene 1 — die Entscheidungsregel als reine Funktion
# ═══════════════════════════════════════════════════════════════════════════


def test_erste_station_begruendet_den_monat():
    """Ohne vorhandene Zeile schreibt die Station, was ihr Zähler sagt."""
    e = entscheide_hauszaehler(
        neu_einspeisung_kwh=700.0, neu_netzbezug_kwh=400.0, hat_bestandszeile=False,
    )
    assert e.schreiben
    assert (e.einspeisung_kwh, e.netzbezug_kwh) == (700.0, 400.0)
    assert e.warnung is None
    assert e.grund == "neu"


def test_zweite_station_meldet_denselben_zaehler_und_addiert_nicht():
    """Der Kern des Befundes: derselbe Wert, nicht die Summe.

    700 + 700 wären 1400 — der Hausanschluss hat aber nur einmal 700
    eingespeist. Die zweite Station bestätigt den Wert, sie erhöht ihn nicht.
    """
    e = entscheide_hauszaehler(
        neu_einspeisung_kwh=700.0, neu_netzbezug_kwh=400.0,
        bestand_einspeisung_kwh=700.0, bestand_netzbezug_kwh=400.0,
        hat_bestandszeile=True,
    )
    assert (e.einspeisung_kwh, e.netzbezug_kwh) == (700.0, 400.0)
    assert e.warnung is None
    assert e.grund == "deckungsgleich"


def test_station_ohne_smartmeter_gewinnt_nie():
    """Ein WR ohne Meter meldet 0/None — das ist ein „weiß nicht", kein Messwert.

    Der gefährliche Fall: die leere Station läuft als zweite und würde den
    echten Wert der ersten auf 0 setzen.
    """
    e = entscheide_hauszaehler(
        neu_einspeisung_kwh=0.0, neu_netzbezug_kwh=0.0,
        bestand_einspeisung_kwh=700.0, bestand_netzbezug_kwh=400.0,
        hat_bestandszeile=True,
    )
    assert not e.schreiben
    assert e.grund == "keine_messung_bestand_bleibt"


def test_station_ohne_smartmeter_gewinnt_auch_mit_haken_nicht():
    """Der Überschreiben-Haken entscheidet den Konflikt, nicht die Leere."""
    e = entscheide_hauszaehler(
        neu_einspeisung_kwh=None, neu_netzbezug_kwh=None,
        bestand_einspeisung_kwh=700.0, bestand_netzbezug_kwh=400.0,
        hat_bestandszeile=True, ueberschreiben=True,
    )
    assert not e.schreiben


def test_station_ohne_smartmeter_und_ohne_monat_sagt_was_zu_tun_ist():
    """Hier fehlt dem Anwender der Monatsabschluss — schweigen wäre die
    P-6-Falle: eine Lücke ohne Hinweis, wie man sie schließt."""
    e = entscheide_hauszaehler(
        neu_einspeisung_kwh=None, neu_netzbezug_kwh=None, hat_bestandszeile=False,
        quelle_bezeichnung="'Sofar 1100'",
    )
    assert not e.schreiben
    assert e.warnung is not None
    assert "Monatsabschluss" in e.warnung
    assert "Sofar 1100" in e.warnung


def test_rundungsunterschied_ist_kein_konflikt():
    """Jede Station rundet den Zählerstand selbst — 700,0 gegen 700,4 ist
    dasselbe Smartmeter, keine Meldung wert."""
    e = entscheide_hauszaehler(
        neu_einspeisung_kwh=700.4, neu_netzbezug_kwh=400.0,
        bestand_einspeisung_kwh=700.0, bestand_netzbezug_kwh=400.0,
        hat_bestandszeile=True,
    )
    assert e.warnung is None
    assert e.grund == "deckungsgleich"


def test_echte_abweichung_ohne_haken_behaelt_den_bestand():
    """eedc rät nicht, welcher Zähler recht hat — es sagt es."""
    e = entscheide_hauszaehler(
        neu_einspeisung_kwh=250.0, neu_netzbezug_kwh=400.0,
        bestand_einspeisung_kwh=700.0, bestand_netzbezug_kwh=400.0,
        hat_bestandszeile=True, ueberschreiben=False,
    )
    assert not e.schreiben
    assert e.grund == "konflikt_bestand_behalten"
    assert "700,0" in e.warnung and "250,0" in e.warnung
    # Der unstrittige Netzbezug taucht im Konflikttext nicht auf.
    assert "Netzbezug" not in e.warnung


def test_echte_abweichung_mit_haken_uebernimmt_und_meldet_trotzdem():
    """Der Anwender hat es angeordnet — gemeldet wird es dennoch, sonst hinge
    das Ergebnis still an der Import-Reihenfolge."""
    e = entscheide_hauszaehler(
        neu_einspeisung_kwh=250.0, neu_netzbezug_kwh=400.0,
        bestand_einspeisung_kwh=700.0, bestand_netzbezug_kwh=400.0,
        hat_bestandszeile=True, ueberschreiben=True,
    )
    assert e.einspeisung_kwh == 250.0
    assert e.grund == "konflikt_ueberschrieben"
    assert e.warnung is not None


def test_nur_eine_der_beiden_groessen_gemeldet():
    """Teil-Lieferungen schreiben, was da ist, statt alles zu verwerfen."""
    e = entscheide_hauszaehler(
        neu_einspeisung_kwh=700.0, neu_netzbezug_kwh=None, hat_bestandszeile=False,
    )
    assert e.einspeisung_kwh == 700.0
    assert e.netzbezug_kwh is None


# ═══════════════════════════════════════════════════════════════════════════
# Ebene 1b — Quellenwahl im Monatsabschluss-Cloudabruf
# ═══════════════════════════════════════════════════════════════════════════
#
# Dort wird vorgeschlagen statt geschrieben, und mehrere gespeicherte Quellen
# liegen nebeneinander. Bis 12.08. durfte nur eine Quelle OHNE Geräte-Zuordnung
# beitragen — bei ausschließlich zugeordneten Stationen gab es nie einen
# Vorschlag für Einspeisung und Netzbezug.


def _q(herkunft, einspeisung, netzbezug, *, ohne_ziel=False) -> HauszaehlerQuelle:
    return HauszaehlerQuelle(
        herkunft=herkunft, ohne_ziel=ohne_ziel,
        einspeisung_kwh=einspeisung, netzbezug_kwh=netzbezug,
    )


def test_wahl_ohne_kandidaten_bleibt_leer():
    wahl = waehle_hauszaehler_quelle([])
    assert (wahl.einspeisung_kwh, wahl.netzbezug_kwh) == (None, None)
    assert wahl.hinweis is None


def test_wahl_nimmt_die_station_wenn_es_keine_hausquelle_gibt():
    """Ollis Aufbau: beide Quellen sind Stationen."""
    wahl = waehle_hauszaehler_quelle([
        _q("Sofar 2200", 700.0, 400.0),
        _q("Sofar 1100", 700.0, 400.0),
    ])
    assert (wahl.einspeisung_kwh, wahl.netzbezug_kwh) == (700.0, 400.0)
    assert wahl.herkunft == "Sofar 2200"
    assert wahl.hinweis is None


def test_wahl_bevorzugt_die_quelle_ohne_geraete_zuordnung():
    """Eine Quelle ohne Ziel ist erklärtermaßen für die Anlage eingerichtet —
    sie schlägt die Station, auch wenn sie später kommt."""
    wahl = waehle_hauszaehler_quelle([
        _q("Sofar 2200", 690.0, 402.0),
        _q("Hauszähler", 700.0, 400.0, ohne_ziel=True),
    ])
    assert wahl.herkunft == "Hauszähler"
    assert (wahl.einspeisung_kwh, wahl.netzbezug_kwh) == (700.0, 400.0)


def test_wahl_ueberspringt_die_station_ohne_smartmeter():
    wahl = waehle_hauszaehler_quelle([
        _q("Sofar 1100", 0.0, 0.0),
        _q("Sofar 2200", 700.0, 400.0),
    ])
    assert wahl.herkunft == "Sofar 2200"
    assert wahl.hinweis is None


def test_wahl_meldet_abweichende_quellen():
    """Zwei Zähler, zwei Wahrheiten — das entscheidet eedc nicht still."""
    wahl = waehle_hauszaehler_quelle([
        _q("Sofar 2200", 700.0, 400.0),
        _q("Sofar 1100", 300.0, 400.0),
    ])
    assert wahl.einspeisung_kwh == 700.0
    assert wahl.hinweis is not None
    assert "Sofar 1100" in wahl.hinweis and "Sofar 2200" in wahl.hinweis


def test_wahl_summiert_niemals():
    """Der Kern: 700 + 300 wären 1000 — der Anschluss hat einmal eingespeist."""
    wahl = waehle_hauszaehler_quelle([
        _q("A", 700.0, 400.0),
        _q("B", 300.0, 200.0),
    ])
    assert wahl.einspeisung_kwh in (700.0, 300.0)
    assert wahl.netzbezug_kwh in (400.0, 200.0)


# ═══════════════════════════════════════════════════════════════════════════
# Ebene 2 — der Import-Endpunkt an echten Objekten
# ═══════════════════════════════════════════════════════════════════════════


async def _zwei_wechselrichter(db, *, mit_speicher: bool = False) -> dict:
    """Ollis Aufbau: ein Haus, zwei WR, je ein PV-String (optional je Speicher)."""
    anlage = Anlage(anlagenname="Zwei Sofar", leistung_kwp=8.0)
    db.add(anlage)
    await db.flush()

    ids: dict = {"anlage": anlage.id}
    for name, kwp in (("Sofar 2200", 5.0), ("Sofar 1100", 3.0)):
        wr = Investition(
            anlage_id=anlage.id, typ="wechselrichter", bezeichnung=name,
            anschaffungsdatum=date(2023, 1, 1),
        )
        db.add(wr)
        await db.flush()
        modul = Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=f"String {name}",
            anschaffungsdatum=date(2023, 1, 1), leistung_kwp=kwp,
            parent_investition_id=wr.id,
        )
        db.add(modul)
        await db.flush()
        ids[name] = {"wr": wr.id, "modul": modul.id}
        if mit_speicher:
            sp = Investition(
                anlage_id=anlage.id, typ="speicher", bezeichnung=f"Akku {name}",
                anschaffungsdatum=date(2023, 1, 1), parent_investition_id=wr.id,
                parameter={"kapazitaet_kwh": 5.0},
            )
            db.add(sp)
            await db.flush()
            ids[name]["speicher"] = sp.id

    await db.commit()
    return ids


def _monat(**werte) -> ApplyMonthInput:
    return ApplyMonthInput(jahr=2025, monat=6, **werte)


async def _monatszeile(db, anlage_id) -> Monatsdaten | None:
    return (await db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == 2025, Monatsdaten.monat == 6,
        )
    )).scalar_one_or_none()


async def _imd(db, investition_id) -> dict:
    row = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == investition_id,
            InvestitionMonatsdaten.jahr == 2025,
            InvestitionMonatsdaten.monat == 6,
        )
    )).scalar_one_or_none()
    return (row.verbrauch_daten or {}) if row else {}


async def _importiere(db, ids, station, *, ueberschreiben=False, **werte):
    return await apply_import(
        anlage_id=ids["anlage"],
        data=ApplyRequest(
            monate=[_monat(**werte)], ziel_investition_id=ids[station]["wr"],
        ),
        ueberschreiben=ueberschreiben, datenquelle="cloud_import", db=db,
    )


async def test_ollis_fall_zwei_stationen_ergeben_einen_monat(db):
    """**Der Fall des Melders, Ende zu Ende.**

    Beide Sofar hängen am selben Hausanschluss und sehen dasselbe Smartmeter.
    Nach beiden Einfuhren muss gelten: jede Station hat ihre eigene Erzeugung an
    ihrem String, und der Monat trägt die Zählerwerte **einmal**.
    """
    ids = await _zwei_wechselrichter(db)

    await _importiere(db, ids, "Sofar 2200",
                      pv_erzeugung_kwh=625.0, einspeisung_kwh=700.0, netzbezug_kwh=400.0)
    await _importiere(db, ids, "Sofar 1100",
                      pv_erzeugung_kwh=375.0, einspeisung_kwh=700.0, netzbezug_kwh=400.0)

    md = await _monatszeile(db, ids["anlage"])
    assert md is not None, "Ollis Symptom: der Monat entsteht nicht."
    assert md.einspeisung_kwh == 700.0, "Die zweite Station hat addiert statt bestätigt."
    assert md.netzbezug_kwh == 400.0

    assert (await _imd(db, ids["Sofar 2200"]["modul"]))["pv_erzeugung_kwh"] == 625.0
    assert (await _imd(db, ids["Sofar 1100"]["modul"]))["pv_erzeugung_kwh"] == 375.0


async def test_reihenfolge_der_stationen_aendert_nichts(db):
    """Dasselbe Ergebnis, wenn der kleine Wechselrichter zuerst läuft."""
    ids = await _zwei_wechselrichter(db)

    await _importiere(db, ids, "Sofar 1100",
                      pv_erzeugung_kwh=375.0, einspeisung_kwh=700.0, netzbezug_kwh=400.0)
    await _importiere(db, ids, "Sofar 2200",
                      pv_erzeugung_kwh=625.0, einspeisung_kwh=700.0, netzbezug_kwh=400.0)

    md = await _monatszeile(db, ids["anlage"])
    assert (md.einspeisung_kwh, md.netzbezug_kwh) == (700.0, 400.0)


async def test_zweite_station_ohne_smartmeter_zerstoert_den_monat_nicht(db):
    """Der gefährliche Fall: nur ein WR hat ein Smartmeter.

    Die zweite Station meldet 0/0. Würde sie gewinnen, stünde der Monat auf
    „Einspeisung 0, Netzbezug 0" — und der Plausibilitäts-Check schlüge an,
    obwohl die Daten vorher richtig waren.
    """
    ids = await _zwei_wechselrichter(db)

    await _importiere(db, ids, "Sofar 2200",
                      pv_erzeugung_kwh=625.0, einspeisung_kwh=700.0, netzbezug_kwh=400.0)
    await _importiere(db, ids, "Sofar 1100",
                      pv_erzeugung_kwh=375.0, einspeisung_kwh=0.0, netzbezug_kwh=0.0,
                      ueberschreiben=True)

    md = await _monatszeile(db, ids["anlage"])
    assert (md.einspeisung_kwh, md.netzbezug_kwh) == (700.0, 400.0)
    # Die Erzeugung der meterlosen Station kommt trotzdem an.
    assert (await _imd(db, ids["Sofar 1100"]["modul"]))["pv_erzeugung_kwh"] == 375.0


async def test_abweichende_zaehlerwerte_werden_gemeldet(db):
    """Zwei Stationen, zwei verschiedene Zählerstände — das muss der Anwender
    erfahren, statt dass die Import-Reihenfolge still entscheidet."""
    ids = await _zwei_wechselrichter(db)

    await _importiere(db, ids, "Sofar 2200",
                      pv_erzeugung_kwh=625.0, einspeisung_kwh=700.0, netzbezug_kwh=400.0)
    antwort = await _importiere(db, ids, "Sofar 1100",
                                pv_erzeugung_kwh=375.0, einspeisung_kwh=250.0,
                                netzbezug_kwh=400.0)

    md = await _monatszeile(db, ids["anlage"])
    assert md.einspeisung_kwh == 700.0, "Ohne Haken darf der Bestand nicht fallen."
    assert any("Smartmeter" in w for w in antwort.warnungen), antwort.warnungen


async def test_speicher_je_station_und_zaehlerzeile_zusammen(db):
    """Alles auf einmal: zwei WR, je ein String, je ein Speicher.

    Die Speicherwerte sind **stationsbezogen** (der Akku hängt an seinem WR) und
    dürfen sich nicht vermischen — die Zählerwerte sind anlagenweit.
    """
    ids = await _zwei_wechselrichter(db, mit_speicher=True)

    await _importiere(db, ids, "Sofar 2200",
                      pv_erzeugung_kwh=625.0, einspeisung_kwh=700.0, netzbezug_kwh=400.0,
                      batterie_ladung_kwh=200.0, batterie_entladung_kwh=180.0)
    await _importiere(db, ids, "Sofar 1100",
                      pv_erzeugung_kwh=375.0, einspeisung_kwh=700.0, netzbezug_kwh=400.0,
                      batterie_ladung_kwh=90.0, batterie_entladung_kwh=80.0)

    md = await _monatszeile(db, ids["anlage"])
    assert (md.einspeisung_kwh, md.netzbezug_kwh) == (700.0, 400.0)

    gross = await _imd(db, ids["Sofar 2200"]["speicher"])
    klein = await _imd(db, ids["Sofar 1100"]["speicher"])
    assert (gross["ladung_kwh"], gross["entladung_kwh"]) == (200.0, 180.0)
    assert (klein["ladung_kwh"], klein["entladung_kwh"]) == (90.0, 80.0)


async def test_monat_ohne_zaehlerzeile_entsteht_nicht_mehr(db):
    """Die Regression zu F-30: genau dieser Zustand war Ollis Symptom.

    Ein Monat mit Gerätewerten, aber ohne Zählerzeile, fiel aus der
    Monatsdaten-Liste und wurde vom Daten-Checker als Defekt gemeldet — mit
    einem Knopf, der die gültigen Messwerte gelöscht hätte.
    """
    ids = await _zwei_wechselrichter(db)

    await _importiere(db, ids, "Sofar 2200",
                      pv_erzeugung_kwh=625.0, einspeisung_kwh=700.0, netzbezug_kwh=400.0)

    imd_vorhanden = bool(await _imd(db, ids["Sofar 2200"]["modul"]))
    md = await _monatszeile(db, ids["anlage"])
    assert imd_vorhanden and md is not None, (
        "Gerätewerte ohne Monatszeile — genau der Zustand, der F-30 auslöste."
    )


async def test_erneuter_import_derselben_station_bleibt_stabil(db):
    """Idempotenz: derselbe Import zweimal ändert nichts und meldet nichts."""
    ids = await _zwei_wechselrichter(db)

    for _ in range(2):
        antwort = await _importiere(
            db, ids, "Sofar 2200", ueberschreiben=True,
            pv_erzeugung_kwh=625.0, einspeisung_kwh=700.0, netzbezug_kwh=400.0,
        )

    md = await _monatszeile(db, ids["anlage"])
    assert (md.einspeisung_kwh, md.netzbezug_kwh) == (700.0, 400.0)
    assert not any("Smartmeter" in w for w in antwort.warnungen), antwort.warnungen


async def test_ohne_ziel_bleibt_der_alte_weg_unveraendert(db):
    """Gegenprobe: der anlagenweite Weg ist nicht Gegenstand dieser Änderung."""
    ids = await _zwei_wechselrichter(db)

    await apply_import(
        anlage_id=ids["anlage"],
        data=ApplyRequest(monate=[_monat(
            pv_erzeugung_kwh=1000.0, einspeisung_kwh=700.0, netzbezug_kwh=400.0,
        )]),
        ueberschreiben=False, datenquelle="portal_import", db=db,
    )

    md = await _monatszeile(db, ids["anlage"])
    assert (md.einspeisung_kwh, md.netzbezug_kwh) == (700.0, 400.0)
    # Ohne Ziel trägt die Anlagen-Zeile das PV-Aggregat weiterhin selbst.
    assert md.pv_erzeugung_kwh == 1000.0
