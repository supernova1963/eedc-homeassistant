"""C1a-Abnahme: `/monatsdaten/aggregiert` bezieht seine Monatsgrößen aus der Schicht.

`list_monatsdaten_aggregiert` faltete die `InvestitionMonatsdaten` bis
2026-08-03 selbst (Register **N-15**, gedeckelt in
`test_wurzelmuster_konformitaet.py::P10_NOCH_NICHT_MIGRIERT`). Seit C1a laufen
Zeitfilter, Dienstwagen-Filter, P7-PV-Auflösung und die E-Mob-Trias über
`services/monats_fakten.py` (ADR-002/**P10**).

Die Sicht speist *Auswertungen → Tabelle* **und** *Cockpit → Jahr* — sie ist
damit eine der sichtbarsten im Produkt. Diese Datei hält deshalb beides fest:
die Eigenschaften, die **gleich bleiben mussten** (ausdrücklich als Regression
markiert), und die **eine Zahl, die sich ändert**.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.core.investition_parameter import PARAM_E_AUTO
from backend.models.tages_energie_profil import TagesZusammenfassung


async def _anlage(db, *, unterliegt_eeg_51: bool = False) -> Anlage:
    anlage = Anlage(anlagenname="C1a", leistung_kwp=10.0, standort_land="DE",
                    unterliegt_eeg_51=unterliegt_eeg_51)
    db.add(anlage)
    await db.flush()
    return anlage


async def _inv(db, anlage_id: int, typ: str, bez: str, **kw) -> Investition:
    inv = Investition(anlage_id=anlage_id, typ=typ, bezeichnung=bez,
                      anschaffungsdatum=date(2024, 1, 1), **kw)
    db.add(inv)
    await db.flush()
    return inv


# --- Zeilenmenge: nur Monate mit Zählerzeile -------------------------------

async def test_monat_ohne_zaehlerzeile_erscheint_nicht(db):
    """REGRESSION — **der Default**. Die Schicht liefert auch Monate ohne
    `Monatsdaten`-Zeile; ungefragt aufgenommen stünden in *Auswertungen →
    Tabelle* Zeilen, die es dort nie gab und die man nicht bearbeiten kann.

    Seit N-68 sind sie über `inkl_ohne_zaehlerzeile=True` **abrufbar** — dieser
    Test hält fest, dass der Default davon unberührt bleibt. Er ist damit auch
    der Wächter über die `Annotated`-Form des Parameters: als
    `= Query(False, …)` geschrieben wäre der Default beim direkten
    Funktionsaufruf das truthy `Query`-Objekt, und genau hier fiel es auf.
    """
    anlage = await _anlage(db)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    # Juni: NUR eine IMD-Zeile, keine Zählerzeile.
    wp = await _inv(db, anlage.id, "waermepumpe", "WP")
    db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=2026, monat=6,
                                  verbrauch_daten={"stromverbrauch_kwh": 100.0}))
    await db.commit()

    rows = await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db)

    assert [r.monat for r in rows] == [5]


# --- N-68: dieselbe Route, auf Wunsch mit den Monaten ohne Abschluss -------


async def _mai_mit_zeile_juni_ohne(db) -> Anlage:
    """Mai mit Zählerzeile + WP-Zeile, Juni **nur** mit WP-Zeile."""
    anlage = await _anlage(db)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0,
                       globalstrahlung_kwh_m2=140.0, sonnenstunden=210.0))
    wp = await _inv(db, anlage.id, "waermepumpe", "WP")
    for monat, strom in ((5, 80.0), (6, 100.0)):
        db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=2026, monat=monat,
                                      verbrauch_daten={"stromverbrauch_kwh": strom}))
    await db.commit()
    return anlage


async def test_flag_nimmt_den_monat_ohne_zaehlerzeile_auf(db):
    """**N-68.** Cockpit → Jahr zeichnete für 2026 sechs Monatsbalken, während
    die Kopfzahl darüber acht Monate zählte — die fehlenden waren gelaufen, aber
    nicht abgeschlossen. Mit dem Flag sind sie da, samt ihrer IMD-Mengen.
    """
    anlage = await _mai_mit_zeile_juni_ohne(db)

    rows = await list_monatsdaten_aggregiert(
        anlage_id=anlage.id, jahr=2026, inkl_ohne_zaehlerzeile=True, db=db,
    )

    assert [r.monat for r in rows] == [6, 5]      # absteigend wie immer
    juni = rows[0]
    assert juni.id is None                        # es gibt keinen Datensatz
    assert juni.anlage_id == anlage.id            # trotzdem zugeordnet
    assert juni.wp_strom_kwh == 100.0             # die Menge ist der ganze Punkt


async def test_zeile_ohne_zaehlerzeile_behauptet_keine_zaehlerwerte(db):
    """Was es ohne `Monatsdaten`-Datensatz nicht gibt, bleibt `None` — es wird
    nicht still zu 0 (CLAUDE.md „0-Werte prüfen", ADR-002/P4).

    Einspeisung/Netzbezug sind die Ausnahme: sie kommen aus `f.zaehler` und
    stehen dort auf 0,0. Das ist keine neue Behauptung dieser Route, sondern die
    der Schicht — hier festgehalten, damit ein späterer Umbau es nicht übersieht.
    """
    anlage = await _mai_mit_zeile_juni_ohne(db)

    juni = (await list_monatsdaten_aggregiert(
        anlage_id=anlage.id, jahr=2026, inkl_ohne_zaehlerzeile=True, db=db,
    ))[0]

    assert juni.globalstrahlung_kwh_m2 is None
    assert juni.sonnenstunden is None
    assert juni.netzbezug_durchschnittspreis_cent is None
    assert juni.hat_legacy_daten is False
    assert juni.einspeisung_kwh == 0.0
    assert juni.netzbezug_kwh == 0.0


async def test_flag_laesst_die_bestehenden_zeilen_unveraendert(db):
    """**Die Deckungs-Aussage**: das Flag *ergänzt*, es rechnet nichts um.

    Ohne diesen Test wäre „nur zusätzliche Balken" eine Behauptung. Verglichen
    wird die ganze Zeile, nicht eine Auswahl von Feldern — sonst deckt der Test
    genau das Feld nicht ab, das sich später verschiebt.
    """
    anlage = await _mai_mit_zeile_juni_ohne(db)

    ohne = await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db)
    mit = await list_monatsdaten_aggregiert(
        anlage_id=anlage.id, jahr=2026, inkl_ohne_zaehlerzeile=True, db=db,
    )

    assert [r.monat for r in ohne] == [5]
    assert [r.model_dump() for r in ohne] == [r.model_dump() for r in mit if r.monat == 5]


async def test_monat_ganz_ohne_spur_erscheint_auch_mit_flag_nicht(db):
    """Das Flag holt keine leeren Monate ins Bild.

    Die Schicht führt nur Monate, für die es eine Zählerzeile, eine sichtbare
    IMD-Zeile oder eine aufgelöste PV gibt (`lade_monats_fakten`). Ein Balken
    aus lauter Nullen für einen Monat, in dem nichts erfasst wurde, wäre
    schlimmer als der fehlende Balken, den N-68 behebt.
    """
    anlage = await _mai_mit_zeile_juni_ohne(db)

    rows = await list_monatsdaten_aggregiert(
        anlage_id=anlage.id, jahr=2026, inkl_ohne_zaehlerzeile=True, db=db,
    )

    assert [r.monat for r in rows] == [6, 5]   # kein Jan–Apr, kein Jul–Dez


async def test_reihenfolge_bleibt_absteigend(db):
    """REGRESSION: neueste zuerst (Datums-Listen-Konvention)."""
    anlage = await _anlage(db)
    for monat in (3, 5, 4):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=monat,
                           einspeisung_kwh=10.0, netzbezug_kwh=5.0))
    await db.commit()

    rows = await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db)

    assert [r.monat for r in rows] == [5, 4, 3]


# --- None statt 0: „nicht vorhanden" ist keine Messung (P4) ----------------

async def test_ohne_komponenten_zeilen_bleiben_die_felder_none(db):
    """REGRESSION. Zählerzeile ja, Komponenten nein ⇒ überall `None`, nicht 0.

    Der Unterschied ist die ganze Begründung für `MetaFakten.typen_mit_zeile`:
    `aktive_investitionen` würde hier eine aktive Wärmepumpe melden und aus dem
    fehlenden Wert eine gemessene 0 machen.
    """
    anlage = await _anlage(db)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    await _inv(db, anlage.id, "waermepumpe", "WP ohne Zeile")
    await _inv(db, anlage.id, "speicher", "Speicher ohne Zeile")
    await db.commit()

    mai = (await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db))[0]

    assert mai.wp_strom_kwh is None
    assert mai.wp_heizung_kwh is None
    assert mai.speicher_ladung_kwh is None
    assert mai.eauto_ladung_kwh is None
    assert mai.pv_erzeugung_kwh is None
    # Die Zählerwerte selbst sind da — es fehlen nur die Komponenten.
    assert mai.einspeisung_kwh == 300.0


async def test_gemessene_null_bleibt_null(db):
    """REGRESSION: eine WP mit 0 kWh Heizung im Sommer ist eine Aussage."""
    anlage = await _anlage(db)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=7,
                       einspeisung_kwh=500.0, netzbezug_kwh=50.0))
    wp = await _inv(db, anlage.id, "waermepumpe", "WP")
    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2026, monat=7,
        verbrauch_daten={"stromverbrauch_kwh": 40.0, "heizenergie_kwh": 0.0},
    ))
    await db.commit()

    juli = (await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db))[0]

    assert juli.wp_strom_kwh == 40.0
    assert juli.wp_heizung_kwh == 0.0   # nicht None


# --- Filter, die jetzt aus der Schicht kommen ------------------------------

async def test_dienstwagen_zaehlt_nicht_als_beitrag(db):
    """REGRESSION. Ein dienstlicher Wagen gehört nicht in den E-Mob-Pool —
    und darf deshalb auch nicht als „0 kWh geladen" erscheinen, sondern gar
    nicht ([[feedback_dienstwagen_alle_checks]])."""
    anlage = await _anlage(db)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    # Schlüssel aus dem Parameter-SoT, nicht geraten — beim ersten Anlauf stand
    # hier `dienstwagen`, und der Test war grün-falsch (das Flag griff nie).
    auto = await _inv(db, anlage.id, "e-auto", "Firmenwagen",
                      parameter={PARAM_E_AUTO["IST_DIENSTLICH"]: True})
    db.add(InvestitionMonatsdaten(
        investition_id=auto.id, jahr=2026, monat=5,
        verbrauch_daten={"ladung_kwh": 200.0, "ladung_pv_kwh": 150.0,
                         "km_gefahren": 1000.0},
    ))
    await db.commit()

    mai = (await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db))[0]

    assert mai.eauto_ladung_kwh is None
    assert mai.eauto_km is None


async def test_vor_anschaffung_zaehlt_nicht(db):
    """REGRESSION (#236 detLAN): IMD vor dem Anschaffungsdatum bleiben draußen."""
    anlage = await _anlage(db)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=1,
                       einspeisung_kwh=100.0, netzbezug_kwh=400.0))
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
                     anschaffungsdatum=date(2026, 4, 1))
    db.add(wp)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=2026, monat=1,
                                  verbrauch_daten={"stromverbrauch_kwh": 320.0}))
    await db.commit()

    jan = (await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db))[0]

    assert jan.wp_strom_kwh is None


# --- BKW-Akku: Altbestand bewusst bitgleich (N-28) -------------------------

async def test_bkw_akku_zaehlt_weiter_in_die_speicher_summe(db):
    """REGRESSION für **N-28**, ausdrücklich als solche markiert.

    `SpeicherFakten` hält die BKW-eigenen Akku-Felder getrennt, diese Sicht
    zählt sie seit jeher in dieselbe anlagenweite Summe. Der Umbau darf das
    nicht still ändern — sonst sinkt die Speicher-Summe genau bei den
    Anwendern, die noch auf dem alten Weg pflegen. Aufgelöst wird es über den
    Erfassungs-Kanon (eigene `speicher`-Investition mit BKW-Parent), nicht hier.
    """
    anlage = await _anlage(db)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    bkw = await _inv(db, anlage.id, "balkonkraftwerk", "BKW", leistung_kwp=0.8)
    db.add(InvestitionMonatsdaten(
        investition_id=bkw.id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 60.0,
                         "speicher_ladung_kwh": 20.0,
                         "speicher_entladung_kwh": 15.0},
    ))
    await db.commit()

    mai = (await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db))[0]

    assert mai.speicher_ladung_kwh == 20.0
    assert mai.speicher_entladung_kwh == 15.0
    assert mai.bkw_kwh == 60.0
    assert mai.pv_erzeugung_kwh == 60.0
    assert mai.pv_module_kwh == 0.0      # kein PV-Modul, nur BKW


# --- Die eine Zahl, die sich ändert ----------------------------------------

async def test_emob_ladung_wird_abgeleitet_statt_roh_addiert(db):
    """**ÄNDERUNG durch C1a** — bewusst, und nach oben.

    Die alte Schleife addierte `ladung_pv_kwh + ladung_netz_kwh` **roh** aus dem
    Dict. Wer nur Gesamt-Ladung und PV-Anteil pflegt (kein `ladung_netz_kwh`),
    bekam damit nur den PV-Anteil ausgewiesen — die Netzladung fiel still weg.
    Die Schicht liest über `summiere_emob_quelle` → `get_emob_pv_netz_kwh`, das
    den Netzanteil aus `Total − PV` ableitet (#262-Familie).

    Hier: 200 kWh geladen, davon 150 PV. Alt: 150. Neu: 200.
    """
    anlage = await _anlage(db)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    auto = await _inv(db, anlage.id, "e-auto", "E-Auto")
    db.add(InvestitionMonatsdaten(
        investition_id=auto.id, jahr=2026, monat=5,
        verbrauch_daten={"ladung_kwh": 200.0, "ladung_pv_kwh": 150.0,
                         "km_gefahren": 900.0},
    ))
    await db.commit()

    mai = (await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db))[0]

    assert mai.eauto_ladung_kwh == 200.0
    assert mai.eauto_km == 900.0


# --- §51: `None` heißt nicht 0 ---------------------------------------------

async def test_eeg51_ohne_tagesdaten_liefert_none(db):
    """**ÄNDERUNG durch C1a.** Die alte Route setzte für §51-Anlagen in jedem
    Monat ohne Tages-Aggregat `0.0` (`.get(key, 0.0)`); die Schicht liefert
    `None` — „keine Mitschrift" ist keine gemessene Null. Der Client trägt es
    bereits (`number | null`, `fmtCalc(…, '—')`)."""
    anlage = await _anlage(db, unterliegt_eeg_51=True)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    await db.commit()

    mai = (await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db))[0]

    assert mai.einspeisung_neg_preis_kwh is None


async def test_eeg51_mit_tagesdaten_summiert_weiter(db):
    """REGRESSION: mit Mitschrift kommt die Summe unverändert."""
    anlage = await _anlage(db, unterliegt_eeg_51=True)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    for tag, wert in ((3, 4.0), (17, 6.0)):
        db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=date(2026, 5, tag),
                                    einspeisung_neg_preis_kwh=wert))
    await db.commit()

    mai = (await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db))[0]

    assert mai.einspeisung_neg_preis_kwh == pytest.approx(10.0)


async def test_ohne_eeg51_flag_bleibt_none(db):
    """REGRESSION: dasselbe Gate wie überall — ohne Schalter kein Ausweis."""
    anlage = await _anlage(db, unterliegt_eeg_51=False)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=date(2026, 5, 3),
                                einspeisung_neg_preis_kwh=4.0))
    await db.commit()

    mai = (await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db))[0]

    assert mai.einspeisung_neg_preis_kwh is None
