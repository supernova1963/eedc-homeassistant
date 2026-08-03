"""C1c — `aktueller_monat.py` bezieht seinen DB-Zweig aus den Fakten (P10).

Diese Route ist die einzige der vier P10-Etappen mit einer echten **Abgrenzung**:
sie mischt vier Datenquellen (``saved`` · ``connector`` · ``mqtt_energy`` ·
``ha_stats``) nach Präzedenz, und die Monats-Fakten-Schicht kennt ausdrücklich
nur die erste (``KONZEPT-MONATS-FAKTEN.md`` §4). Migriert wurde deshalb genau
der DB-Zweig; die Präzedenz-Regeln, die ``> 0``-Gates beim Setzen und die
Teilzeitraum-Logik (#361) sind unberührt geblieben — die ersten beiden Tests
halten das fest, damit ein späterer „Aufräum"-Schritt sie nicht wegräumt.

Was sich **ändert**, und warum es hier steht statt in einer Release-Notiz:

* Die PV des Monatsberichts ist **P7-aufgelöst**. Wer nur das Anlagen-Aggregat
  pflegt (kein PV-Sensor je String), sah im Monatsbericht bisher **gar keine
  PV** — der F-5-Befund der Drift-Inventur, an der Sicht, die S1–S6 nicht
  angefasst haben.
* Der **BKW-Eigenverbrauch** fällt ohne Messwert nicht mehr auf die volle
  Erzeugung zurück (der als „D5-Quirk" markierte Site-1-Sonderweg).
* Der **Vorjahresvergleich** verliert drei konservierte Divergenzen: PV ohne
  P7-Auflösung, Eigenverbrauch ohne V2H, E-Mob als ``max()`` je Feld statt der
  kanonischen Trias aus EINER Quelle (#262). Der letzte Punkt ist der
  sichtbarste: **öffentlich geladener Strom zählte im Vorjahr als Heimladung**,
  im laufenden Monat nicht — derselbe Monat trug in zwei Sichten zwei Zahlen.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.investition_parameter import PARAM_E_AUTO, PARAM_SONSTIGES
from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)


async def _anlage(db: AsyncSession, name: str) -> int:
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    return anlage.id


async def _saved(db: AsyncSession, anlage_id: int, jahr: int, monat: int) -> dict:
    """Der `saved`-Zweig der Quellen-Kaskade, so wie die Route ihn baut."""
    from backend.api.routes.aktueller_monat import _collect_saved_data
    from backend.services.monats_fakten import lade_monats_fakten

    fakten = await lade_monats_fakten(
        db, anlage_id, von=(jahr, monat), bis=(jahr, monat)
    )
    return _collect_saved_data(fakten[0] if fakten else None)


async def _vorjahr(db: AsyncSession, anlage_id: int, jahr: int, monat: int):
    from backend.api.routes.aktueller_monat import _load_vorjahr
    invs = list((await db.execute(
        __import__("sqlalchemy").select(Investition)
        .where(Investition.anlage_id == anlage_id)
    )).scalars().all())
    return await _load_vorjahr(anlage_id, [i for i in invs if i.aktiv is not False],
                               jahr, monat, db)


# ── 1. Merge-Semantik bleibt: die `> 0`-Gates sind Präzedenz, keine Rechnung ──

async def test_nullwerte_setzen_kein_feld_und_geben_die_kaskade_frei(db):
    """Ein Feld mit 0 kWh bleibt **ungesetzt** — sonst blockiert es die Kaskade.

    ``saved`` ist die schwächste Quelle (Konfidenz 85). Ein Feld, das sie nicht
    setzt, darf von Connector/MQTT/HA-Statistics kommen. Würde die Migration die
    Gates zu ``is not None`` machen, käme aus einer gepflegten 0 eine Aussage,
    die eine stärkere Quelle nicht mehr korrigieren kann.
    """
    anlage_id = await _anlage(db, "C1cGates")
    wp = Investition(
        anlage_id=anlage_id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(wp)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2025, monat=5,
        verbrauch_daten={"stromverbrauch_kwh": 0.0, "waerme_kwh": 0.0},
    ))
    await db.flush()

    saved = await _saved(db, anlage_id, 2025, 5)
    assert "wp_strom_kwh" not in saved
    assert "wp_waerme_kwh" not in saved


async def test_ohne_zaehlerzeile_kein_zaehlerfeld_trotz_komponentendaten(db):
    """Ohne ``Monatsdaten``-Zeile bleiben Einspeisung/Netzbezug **ungesetzt**.

    Die Schicht liefert für so einen Monat sehr wohl einen Fakt (es gibt ja
    IMD-Zeilen), und ``ZaehlerFakten`` trägt darin 0,0 — die Route darf das
    nicht übernehmen. Sonst füllt die schwächste Quelle eine echte Lücke mit
    einer Null, die keine stärkere Quelle mehr korrigieren kann (P4-Anti-Muster,
    ``KONZEPT-UNVOLLSTAENDIGE-WERTE.md``). Genau hier war beim Umhängen ein
    stiller Fehler möglich, und nur hier: die Spalten selbst sind
    ``nullable=False`` und tragen 0 als Default.
    """
    anlage_id = await _anlage(db, "C1cLuecke")
    modul = Investition(anlage_id=anlage_id, typ="pv-module", bezeichnung="Dach",
                        leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1))
    db.add(modul)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=modul.id, jahr=2025, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 800.0}))
    await db.flush()

    saved = await _saved(db, anlage_id, 2025, 5)
    assert saved["pv_erzeugung_kwh"][0] == 800.0     # der Fakt existiert
    assert "einspeisung_kwh" not in saved
    assert "netzbezug_kwh" not in saved
    # ... und ohne jede Spur bleibt der Zweig ganz leer.
    assert await _saved(db, anlage_id, 2025, 9) == {}


# ── 2. Die PV des Monatsberichts ist P7-aufgelöst ───────────────────────────

async def test_pv_erscheint_bei_reiner_aggregat_pflege(db):
    """Nur das Anlagen-Aggregat gepflegt ⇒ der Monatsbericht zeigt die PV.

    Der F-5-Befund: fünf Sichten summierten roh über die Modul-Zeilen, zwei
    nutzten die P7-Auflösung. Wer keinen Sensor je String hat, sah in dieser
    Sicht 0 kWh und in der Cockpit-Übersicht 1.000 kWh.
    """
    anlage_id = await _anlage(db, "C1cAggregat")
    modul = Investition(
        anlage_id=anlage_id, typ="pv-module", bezeichnung="Süddach",
        leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(modul)
    await db.flush()
    # Anlagen-Aggregat gepflegt, KEINE Modul-Zeile mit eigenem Wert.
    db.add(Monatsdaten(
        anlage_id=anlage_id, jahr=2025, monat=5,
        einspeisung_kwh=600.0, netzbezug_kwh=100.0, pv_erzeugung_kwh=1000.0,
    ))
    await db.flush()

    saved = await _saved(db, anlage_id, 2025, 5)
    assert saved["pv_erzeugung_kwh"][0] == 1000.0


async def test_gemessene_modulwerte_behalten_vorrang(db):
    """Wo gemessen wird, füllt das Aggregat nur die Lücke (P7) — keine Ersetzung."""
    anlage_id = await _anlage(db, "C1cGemessen")
    a = Investition(anlage_id=anlage_id, typ="pv-module", bezeichnung="Süd",
                    leistung_kwp=6.0, anschaffungsdatum=date(2024, 1, 1))
    b = Investition(anlage_id=anlage_id, typ="pv-module", bezeichnung="Nord",
                    leistung_kwp=4.0, anschaffungsdatum=date(2024, 1, 1))
    db.add_all([a, b])
    await db.flush()
    db.add_all([
        InvestitionMonatsdaten(investition_id=a.id, jahr=2025, monat=5,
                               verbrauch_daten={"pv_erzeugung_kwh": 700.0}),
        InvestitionMonatsdaten(investition_id=b.id, jahr=2025, monat=5,
                               verbrauch_daten={"pv_erzeugung_kwh": 400.0}),
    ])
    await db.flush()

    saved = await _saved(db, anlage_id, 2025, 5)
    assert saved["pv_erzeugung_kwh"][0] == 1100.0


# ── 3. BKW: der D5-Quirk fällt ──────────────────────────────────────────────

async def test_bkw_eigenverbrauch_ohne_messwert_bleibt_leer(db):
    """Ohne gemessenen Eigenverbrauch wird **nicht** die volle Erzeugung gemeldet.

    Der alte Fallback (`eigenverbrauch or erzeugung`) behauptete, ein
    Balkonkraftwerk habe seinen gesamten Ertrag selbst verbraucht — divergent zu
    Komponenten-Hub und Cockpit-Übersicht, die den Rohwert zeigen.
    """
    anlage_id = await _anlage(db, "C1cBkw")
    bkw = Investition(
        anlage_id=anlage_id, typ="balkonkraftwerk", bezeichnung="Balkon",
        leistung_kwp=0.8, anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(bkw)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=bkw.id, jahr=2025, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 60.0},   # kein eigenverbrauch_kwh
    ))
    await db.flush()

    saved = await _saved(db, anlage_id, 2025, 5)
    assert saved["bkw_erzeugung_kwh"][0] == 60.0
    assert "bkw_eigenverbrauch_kwh" not in saved
    # Die BKW-Erzeugung zählt weiter in die Anlagen-PV.
    assert saved["pv_erzeugung_kwh"][0] == 60.0


# ── 4. Dienstwagen: unverändert draußen ─────────────────────────────────────

async def test_dienstwagen_zaehlt_in_keinem_der_beiden_pfade(db):
    """Weder im laufenden Monat noch im Vorjahr — [[feedback_dienstwagen_alle_checks]]."""
    anlage_id = await _anlage(db, "C1cDienst")
    dienst = Investition(
        anlage_id=anlage_id, typ="e-auto", bezeichnung="Firmenwagen",
        anschaffungsdatum=date(2023, 1, 1),
        parameter={PARAM_E_AUTO["IST_DIENSTLICH"]: True},
    )
    db.add(dienst)
    await db.flush()
    db.add_all([
        InvestitionMonatsdaten(
            investition_id=dienst.id, jahr=2025, monat=5,
            verbrauch_daten={"ladung_kwh": 300.0, "ladung_pv_kwh": 200.0,
                             "ladung_netz_kwh": 100.0, "km_gefahren": 1500},
        ),
        InvestitionMonatsdaten(
            investition_id=dienst.id, jahr=2024, monat=5,
            verbrauch_daten={"ladung_kwh": 250.0, "ladung_pv_kwh": 150.0,
                             "ladung_netz_kwh": 100.0, "km_gefahren": 1200},
        ),
    ])
    db.add_all([
        Monatsdaten(anlage_id=anlage_id, jahr=2025, monat=5,
                    einspeisung_kwh=500.0, netzbezug_kwh=200.0),
        Monatsdaten(anlage_id=anlage_id, jahr=2024, monat=5,
                    einspeisung_kwh=480.0, netzbezug_kwh=210.0),
    ])
    await db.flush()

    saved = await _saved(db, anlage_id, 2025, 5)
    assert "emob_ladung_kwh" not in saved
    assert "emob_km" not in saved

    vj = await _vorjahr(db, anlage_id, 2025, 5)
    assert "emob_ladung_kwh" not in vj
    assert "emob_km" not in vj


# ── 5. Vorjahr: die drei konservierten Divergenzen fallen ───────────────────

async def test_vorjahr_pv_wird_p7_aufgeloest(db):
    """Vorjahres-PV bei reiner Aggregat-Pflege: 0 kWh → der gepflegte Wert.

    Die Divergenz war im Code als „D6 / IST-Stand erhalten" markiert: der
    Vorjahres-Pfad las je Modul roh, der laufende Monat löste auf.
    """
    anlage_id = await _anlage(db, "C1cVjPv")
    modul = Investition(
        anlage_id=anlage_id, typ="pv-module", bezeichnung="Dach",
        leistung_kwp=10.0, anschaffungsdatum=date(2023, 1, 1),
    )
    db.add(modul)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage_id, jahr=2024, monat=5,
        einspeisung_kwh=600.0, netzbezug_kwh=100.0, pv_erzeugung_kwh=900.0,
    ))
    await db.flush()

    vj = await _vorjahr(db, anlage_id, 2025, 5)
    assert vj["pv_erzeugung_kwh"] == 900.0


async def test_vorjahr_eigenverbrauch_enthaelt_v2h(db):
    """Was das E-Auto ins Haus zurückspeist, zählt jetzt auch im Vorjahr.

    Bisher rechnete der Vorjahres-Pfad ``direktverbrauch + Speicher-Entladung``
    von Hand; V2H fiel weg. Im laufenden Monat zählt es seit v3.x mit — das
    YoY-Delta zeigte deshalb einen methodischen Scheinsprung.
    """
    anlage_id = await _anlage(db, "C1cVjV2h")
    modul = Investition(anlage_id=anlage_id, typ="pv-module", bezeichnung="Dach",
                        leistung_kwp=10.0, anschaffungsdatum=date(2023, 1, 1))
    eauto = Investition(
        anlage_id=anlage_id, typ="e-auto", bezeichnung="Auto",
        anschaffungsdatum=date(2023, 1, 1),
        parameter={PARAM_E_AUTO["V2H_FAEHIG"]: True},
    )
    db.add_all([modul, eauto])
    await db.flush()
    db.add_all([
        InvestitionMonatsdaten(investition_id=modul.id, jahr=2024, monat=5,
                               verbrauch_daten={"pv_erzeugung_kwh": 900.0}),
        InvestitionMonatsdaten(
            investition_id=eauto.id, jahr=2024, monat=5,
            verbrauch_daten={"ladung_kwh": 200.0, "ladung_pv_kwh": 120.0,
                             "ladung_netz_kwh": 80.0, "v2h_entladung_kwh": 40.0},
        ),
    ])
    db.add(Monatsdaten(anlage_id=anlage_id, jahr=2024, monat=5,
                       einspeisung_kwh=600.0, netzbezug_kwh=100.0))
    await db.flush()

    vj = await _vorjahr(db, anlage_id, 2025, 5)
    # Direktverbrauch 900 − 600 = 300, dazu 40 kWh V2H.
    assert vj["direktverbrauch_kwh"] == 300.0
    assert vj["eigenverbrauch_kwh"] == 340.0
    assert vj["gesamtverbrauch_kwh"] == 440.0


async def test_vorjahr_emob_zaehlt_oeffentliches_laden_nicht_als_heimladung(db):
    """Die kanonische Trias statt ``max()`` je Feld (#262).

    Der Demo-Bestand zeigt den Fall: E-Auto meldet 223,8 kWh Gesamt-Ladung, davon
    50 kWh extern; die Wallbox misst am Ladepunkt 174 kWh. Der alte
    ``max()``-Pfad nahm 223,8 — **inklusive der öffentlichen Ladung**, die nie
    durch das Haus floss. Der laufende Monat nahm längst 174.
    """
    anlage_id = await _anlage(db, "C1cVjEmob")
    eauto = Investition(anlage_id=anlage_id, typ="e-auto", bezeichnung="Tesla",
                        anschaffungsdatum=date(2023, 1, 1))
    wallbox = Investition(anlage_id=anlage_id, typ="wallbox", bezeichnung="go-e",
                          anschaffungsdatum=date(2023, 1, 1))
    db.add_all([eauto, wallbox])
    await db.flush()
    db.add_all([
        InvestitionMonatsdaten(
            investition_id=eauto.id, jahr=2024, monat=8,
            verbrauch_daten={"km_gefahren": 1119, "ladung_pv_kwh": 150.0,
                             "ladung_netz_kwh": 24.0, "ladung_extern_kwh": 50.0,
                             "ladung_extern_euro": 27.5, "ladung_kwh": 223.8},
        ),
        InvestitionMonatsdaten(
            investition_id=wallbox.id, jahr=2024, monat=8,
            verbrauch_daten={"ladung_kwh": 174.0, "ladevorgaenge": 6},
        ),
    ])
    db.add(Monatsdaten(anlage_id=anlage_id, jahr=2024, monat=8,
                       einspeisung_kwh=500.0, netzbezug_kwh=200.0))
    await db.flush()

    vj = await _vorjahr(db, anlage_id, 2025, 8)
    assert vj["emob_ladung_kwh"] == 174.0
    # Und dieselbe Zahl, wenn derselbe Monat als LAUFENDER Monat gelesen wird —
    # das ist der eigentliche Befund: eine Größe, zwei Sichten, eine Zahl.
    saved = await _saved(db, anlage_id, 2024, 8)
    assert saved["emob_ladung_kwh"][0] == 174.0


# ── 6. Vorjahr: die Eigenschaften, die überleben mussten ────────────────────

async def test_vorjahr_ohne_zaehlerzeile_bleibt_none(db):
    """Ohne ``Monatsdaten``-Zeile im Vorjahr gibt es keinen Vergleich.

    Die Schicht liefert auch Monate **ohne** Zählerzeile (`hat_zaehlerzeile`
    False), damit eine Sicht die Lücke ausweisen kann. Diese hier tut es nicht —
    sie blendet den Vergleich aus, und das war vorher so.
    """
    anlage_id = await _anlage(db, "C1cVjLeer")
    modul = Investition(anlage_id=anlage_id, typ="pv-module", bezeichnung="Dach",
                        leistung_kwp=10.0, anschaffungsdatum=date(2023, 1, 1))
    db.add(modul)
    await db.flush()
    # IMD-Zeile ja, Zählerzeile nein.
    db.add(InvestitionMonatsdaten(investition_id=modul.id, jahr=2024, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 900.0}))
    await db.flush()

    assert await _vorjahr(db, anlage_id, 2025, 5) is None


async def test_vorjahr_respektiert_das_anschaffungsdatum(db):
    """#236: eine im Vorjahres-Monat noch nicht angeschaffte WP zählt nicht.

    Der Filter lag bis C1c als eigener Loop in dieser Funktion; jetzt gilt er in
    der Schicht. Ohne ihn zeigte der Vergleich Verbrauch aus einer Zeit, in der
    das Gerät noch gar nicht da war (Demo: WP-Zeilen vor Inbetriebnahme).
    """
    anlage_id = await _anlage(db, "C1cVjAnschaffung")
    wp = Investition(
        anlage_id=anlage_id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2024, 7, 1),
    )
    db.add(wp)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2024, monat=5,
        verbrauch_daten={"stromverbrauch_kwh": 320.0, "waerme_kwh": 1400.0},
    ))
    db.add(Monatsdaten(anlage_id=anlage_id, jahr=2024, monat=5,
                       einspeisung_kwh=500.0, netzbezug_kwh=200.0))
    await db.flush()

    vj = await _vorjahr(db, anlage_id, 2025, 5)
    assert "wp_strom_kwh" not in vj
    assert "wp_waerme_kwh" not in vj


async def test_vorjahr_zaehlt_sonstigen_erzeuger_in_die_bilanz(db):
    """Ein BHKW hinter demselben Zähler zählt in Eigenverbrauch/Autarkie.

    v3.45.4-Kanon: an EINEM Netzanschluss messen die Zähler die Summe aller
    dahinter liegenden Erzeuger. ``pv_erzeugung_kwh`` im Vergleich bleibt daneben
    rein — ein BHKW ist kein PV-Modul.
    """
    anlage_id = await _anlage(db, "C1cVjBhkw")
    modul = Investition(anlage_id=anlage_id, typ="pv-module", bezeichnung="Dach",
                        leistung_kwp=10.0, anschaffungsdatum=date(2023, 1, 1))
    bhkw = Investition(
        anlage_id=anlage_id, typ="sonstiges", bezeichnung="BHKW",
        anschaffungsdatum=date(2023, 1, 1),
        parameter={PARAM_SONSTIGES["KATEGORIE"]: "erzeuger"},
    )
    db.add_all([modul, bhkw])
    await db.flush()
    db.add_all([
        InvestitionMonatsdaten(investition_id=modul.id, jahr=2024, monat=5,
                               verbrauch_daten={"pv_erzeugung_kwh": 900.0}),
        InvestitionMonatsdaten(investition_id=bhkw.id, jahr=2024, monat=5,
                               verbrauch_daten={"erzeugung_kwh": 200.0}),
    ])
    db.add(Monatsdaten(anlage_id=anlage_id, jahr=2024, monat=5,
                       einspeisung_kwh=600.0, netzbezug_kwh=100.0))
    await db.flush()

    vj = await _vorjahr(db, anlage_id, 2025, 5)
    assert vj["pv_erzeugung_kwh"] == 900.0          # rein
    assert vj["direktverbrauch_kwh"] == 500.0       # (900 + 200) − 600
