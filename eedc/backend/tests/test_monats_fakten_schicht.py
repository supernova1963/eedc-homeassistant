"""Monats-Fakten — Einheitstests je Feldgruppe (ADR-002/P10, Schritt S1).

Die Drift-Inventur vom 2026-07-31 fand keinen Rechenfehler im Berechnungs-Layer,
sondern **sechsmal dieselbe Aufbereitungs-Struktur**: jede Sicht faltet die
Rohdaten selbst, und dabei fällt jedes Mal etwas anderes weg. `services/
monats_fakten.py` ist die eine Faltung davor.

Diese Datei prüft die Schicht **für sich** — keine Sicht ist in S1 umgehängt.
Geprüft wird je Feldgruppe genau das, was in den sechs Befunden verloren ging:

- **F-5** — nur das Anlagen-Aggregat gepflegt: die PV darf nicht auf 0 fallen.
- **F-1** — V2H und der Erzeuger hinter dem Zähler gehören in die Bilanz.
- **F-4** — BKW ohne gemessenen Eigenverbrauch (P9-Aufteilung).
- **F-7** — der Dienstwagen wird gefiltert, aber nicht verworfen.
- dazu die Zeitfilter (`aktiv` · Anschaffung · Stilllegung), die ab jetzt **genau
  hier** greifen, und der Monatstarif (P8).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.strompreis import Strompreis
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.einspeise_erloes_service import (
    get_neg_preis_einspeisung_je_monat,
    get_neg_preis_einspeisung_monat,
)
from backend.services.monats_fakten import (
    finanz_zeile_eingabe,
    kennzahlen_aus_fakten,
    lade_monats_fakten,
)

ANSCHAFFUNG = date(2024, 1, 1)


async def _anlage(db, **kwargs) -> Anlage:
    anlage = Anlage(anlagenname="Fakten", leistung_kwp=10.0, **kwargs)
    db.add(anlage)
    await db.flush()
    return anlage


async def _inv(db, anlage, typ, bezeichnung="X", **kwargs) -> Investition:
    inv = Investition(
        anlage_id=anlage.id, typ=typ, bezeichnung=bezeichnung,
        anschaffungsdatum=kwargs.pop("anschaffungsdatum", ANSCHAFFUNG),
        **kwargs,
    )
    db.add(inv)
    await db.flush()
    return inv


def _imd(inv, jahr, monat, daten) -> InvestitionMonatsdaten:
    return InvestitionMonatsdaten(
        investition_id=inv.id, jahr=jahr, monat=monat, verbrauch_daten=daten
    )


async def _tarif(db, anlage, *, ab=date(2024, 1, 1), bis=None, netz=30.0,
                 verguetung=8.0, grundpreis=12.0, verwendung="allgemein"):
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung=verwendung,
        gueltig_ab=ab, gueltig_bis=bis,
        netzbezug_arbeitspreis_cent_kwh=netz,
        einspeiseverguetung_cent_kwh=verguetung,
        grundpreis_euro_monat=grundpreis,
    ))


def _fakt(fakten, jahr, monat):
    """Der Monat aus der Fakten-Liste — mit lesbarer Meldung, wenn er fehlt.

    `next()` ohne Default würde in einem `async def`-Test als „coroutine raised
    StopIteration" ankommen und die eigentliche Ursache verdecken.
    """
    treffer = [f for f in fakten if f.schluessel == (jahr, monat)]
    assert treffer, (
        f"kein MonatsFakt für {jahr}-{monat:02d} — vorhanden: "
        f"{[f.schluessel for f in fakten]}"
    )
    return treffer[0]


# ═══════════════════════════════════════════════════════════════════════
# Gruppe `zaehler` + `meta`
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_zaehlerwerte_und_fehlende_zaehlerzeile(db):
    """Zählerwerte kommen aus `Monatsdaten`; ein Monat ohne Zeile sagt es.

    Ein Monat, für den nur eine IMD-Zeile existiert, verschwindet **nicht** —
    sonst übersieht eine Sicht die Lücke, statt sie auszuweisen (P4).
    """
    anlage = await _anlage(db)
    pv = await _inv(db, anlage, "pv-module", leistung_kwp=10.0)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    db.add(_imd(pv, 2025, 2, {"pv_erzeugung_kwh": 900.0}))
    await db.commit()

    fakten = await lade_monats_fakten(db, anlage.id)

    jan = _fakt(fakten, 2025, 1)
    assert jan.zaehler.einspeisung_kwh == pytest.approx(400.0)
    assert jan.zaehler.netzbezug_kwh == pytest.approx(100.0)
    assert jan.meta.hat_zaehlerzeile is True

    feb = _fakt(fakten, 2025, 2)
    assert feb.meta.hat_zaehlerzeile is False
    assert feb.zaehler.einspeisung_kwh == 0.0
    assert feb.erzeugung.pv_kwh == pytest.approx(900.0)


# ═══════════════════════════════════════════════════════════════════════
# Gruppe `erzeugung` — F-5 und der Erzeuger hinter dem Zähler
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_f5_nur_anlagen_aggregat_gepflegt_pv_faellt_nicht_auf_null(db):
    """**F-5**, der schwerste Befund: PV nur als Anlagen-Aggregat.

    Fünf Sichten summierten roh `verbrauch_daten["pv_erzeugung_kwh"]` und sahen
    für diese Anlage 0 kWh — 85 % Abweichung im Netto-Ertrag. Die Schicht löst
    über P7 auf.
    """
    anlage = await _anlage(db)
    await _inv(db, anlage, "pv-module", leistung_kwp=10.0)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0,
                       pv_erzeugung_kwh=1000.0))
    await db.commit()

    fakt = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 6)

    assert fakt.erzeugung.pv_module_kwh == pytest.approx(1000.0)
    assert fakt.erzeugung.pv_kwh == pytest.approx(1000.0)
    assert fakt.erzeugung.pv_vollstaendig is True
    assert fakt.kennzahlen.eigenverbrauch_kwh == pytest.approx(600.0)


@pytest.mark.asyncio
async def test_teilluecke_ohne_aggregat_ist_luecke_keine_teilsumme(db):
    """N42: ein Modul misst, das andere nicht, kein Aggregat → `None`.

    Eine Teilsumme als Anlagenerzeugung wäre irreführend; die Schicht reicht die
    Unvollständigkeit als Flag durch, statt sie zu 0 zu machen.
    """
    anlage = await _anlage(db)
    sued = await _inv(db, anlage, "pv-module", "Süd", leistung_kwp=6.0)
    await _inv(db, anlage, "pv-module", "Ost", leistung_kwp=4.0)
    db.add(_imd(sued, 2025, 5, {"pv_erzeugung_kwh": 700.0}))
    await db.commit()

    fakt = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 5)

    assert fakt.erzeugung.pv_module_kwh is None
    assert fakt.erzeugung.pv_vollstaendig is False
    assert fakt.meta.pv_vollstaendig is False
    # Die Pro-Modul-Sicht behält ihren Messwert (P2-A).
    assert fakt.erzeugung.pv_je_modul[sued.id].pv_erzeugung_kwh == pytest.approx(700.0)


@pytest.mark.asyncio
async def test_f1_erzeuger_hinter_dem_zaehler_zaehlt_in_die_bilanz_nicht_in_die_pv(db):
    """**F-1**: ein BHKW speist hinter denselben Zähler.

    Seine Erzeugung gehört in Eigenverbrauch/Autarkie (sonst drückt der
    Einspeise-Zähler den Direktverbrauch still zu niedrig), aber **nicht** in die
    PV-Achse — ein BHKW ist kein PV-Modul (Achsen-Trennung v3.45.4).
    """
    anlage = await _anlage(db)
    pv = await _inv(db, anlage, "pv-module", leistung_kwp=10.0)
    bhkw = await _inv(db, anlage, "sonstiges", "BHKW", parameter={"kategorie": "erzeuger"})
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=3,
                       einspeisung_kwh=200.0, netzbezug_kwh=100.0))
    db.add(_imd(pv, 2025, 3, {"pv_erzeugung_kwh": 800.0}))
    db.add(_imd(bhkw, 2025, 3, {"erzeugung_kwh": 300.0}))
    await db.commit()

    fakt = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 3)

    assert fakt.erzeugung.pv_kwh == pytest.approx(800.0), "PV-Achse bleibt rein"
    assert fakt.erzeugung.sonstige_erzeuger_kwh == pytest.approx(300.0)
    assert fakt.erzeugung.hinter_zaehler_kwh == pytest.approx(1100.0)
    # Ohne den BHKW-Anteil wären es 600 kWh Direktverbrauch statt 900.
    assert fakt.kennzahlen.direktverbrauch_kwh == pytest.approx(900.0)


# ═══════════════════════════════════════════════════════════════════════
# Gruppe `bkw` — P9 / F-4
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("daten", "erwartet_erzeugung", "erwartet_rest"),
    [
        ({"pv_erzeugung_kwh": 300.0}, 300.0, 0.0),
        ({"pv_erzeugung_kwh": 300.0, "eigenverbrauch_kwh": 250.0}, 300.0, 0.0),
        ({"eigenverbrauch_kwh": 250.0}, 0.0, 250.0),
    ],
    ids=["nur-erzeugung", "erzeugung-und-ev", "nur-ev-datenluecke"],
)
async def test_bkw_traegt_je_monat_genau_einen_wert(db, daten, erwartet_erzeugung,
                                                    erwartet_rest):
    """**P9**: Erzeugung ODER Rest-Eigenverbrauch — nie beides (F-4).

    Steht die Erzeugung, steckt der Eigenverbrauch schon in der Ableitung aus
    `pv_kwh`; ein zweiter Term wäre Doppelzählung. Fehlt sie (Datenlücke), trägt
    der gemessene Eigenverbrauch allein.
    """
    anlage = await _anlage(db)
    bkw = await _inv(db, anlage, "balkonkraftwerk", "BKW", leistung_kwp=0.8)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=7,
                       einspeisung_kwh=0.0, netzbezug_kwh=200.0))
    db.add(_imd(bkw, 2025, 7, daten))
    await db.commit()

    fakt = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 7)

    assert fakt.bkw.erzeugung_kwh == pytest.approx(erwartet_erzeugung)
    assert fakt.bkw.rest_eigenverbrauch_kwh == pytest.approx(erwartet_rest)
    assert fakt.bkw.eigenverbrauch_gemessen_kwh == pytest.approx(
        daten.get("eigenverbrauch_kwh", 0.0)
    ), "der ROHE Wert bleibt für die Anzeige erhalten"
    # Das BKW speist hinter denselben Zähler → seine Erzeugung ist Teil der PV.
    assert fakt.erzeugung.pv_kwh == pytest.approx(erwartet_erzeugung)


# ═══════════════════════════════════════════════════════════════════════
# Gruppe `speicher`
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_speicher_summiert_und_gewichtet_den_ladepreis_nach_menge(db):
    """Zwei Speicher, zwei Netzlade-Preise → mengengewichteter Ø, nicht 20 ct."""
    anlage = await _anlage(db)
    a = await _inv(db, anlage, "speicher", "A", leistung_kwp=10.0)
    b = await _inv(db, anlage, "speicher", "B", leistung_kwp=5.0)
    db.add(_imd(a, 2025, 4, {"ladung_kwh": 300.0, "entladung_kwh": 270.0,
                             "ladung_netz_kwh": 100.0, "speicher_ladepreis_cent": 10.0}))
    db.add(_imd(b, 2025, 4, {"ladung_kwh": 100.0, "entladung_kwh": 90.0,
                             "ladung_netz_kwh": 300.0, "speicher_ladepreis_cent": 30.0}))
    await db.commit()

    speicher = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 4).speicher

    assert speicher.ladung_kwh == pytest.approx(400.0)
    assert speicher.entladung_kwh == pytest.approx(360.0)
    assert speicher.netzladung_kwh == pytest.approx(400.0)
    assert speicher.netzladung_preis_cent == pytest.approx(25.0), (
        "mengengewichtet (100×10 + 300×30) / 400 — nicht der Mittelwert der Preise"
    )


@pytest.mark.asyncio
async def test_speicher_ohne_gepflegten_ladepreis_hat_keinen_durchschnitt(db):
    """Ohne gepflegten Preis ist der Ø `None` — eine 0 wäre eine Aussage."""
    anlage = await _anlage(db)
    sp = await _inv(db, anlage, "speicher", "S", leistung_kwp=10.0)
    db.add(_imd(sp, 2025, 4, {"ladung_kwh": 300.0, "ladung_netz_kwh": 100.0}))
    await db.commit()

    speicher = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 4).speicher

    assert speicher.netzladung_kwh == pytest.approx(100.0)
    assert speicher.netzladung_preis_cent is None


# ═══════════════════════════════════════════════════════════════════════
# Gruppe `emob` — Pool, V2H, Dienstwagen (F-7)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_emob_pool_kommt_geschlossen_aus_einer_quelle(db):
    """Wallbox vorhanden und mit Heimladung → sie ist die Quelle (#262).

    Feldweises `max()` über getrennte Töpfe konnte PV aus der einen und Netz aus
    der anderen Quelle nehmen — PV-Anteil > 100 %.
    """
    anlage = await _anlage(db)
    auto = await _inv(db, anlage, "e-auto", "Auto")
    wb = await _inv(db, anlage, "wallbox", "WB")
    db.add(_imd(auto, 2025, 5, {"km_gefahren": 1000.0, "verbrauch_kwh": 180.0,
                                "ladung_pv_kwh": 50.0, "ladung_netz_kwh": 30.0,
                                "v2h_entladung_kwh": 25.0}))
    db.add(_imd(wb, 2025, 5, {"ladung_pv_kwh": 120.0, "ladung_netz_kwh": 80.0}))
    await db.commit()

    emob = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 5).emob

    assert emob.quelle == "wallbox"
    assert emob.ladung_kwh == pytest.approx(200.0)
    assert emob.ladung_pv_kwh + emob.ladung_netz_kwh == pytest.approx(emob.ladung_kwh)
    assert emob.km == pytest.approx(1000.0), "km kommen immer vom Fahrzeug"
    assert emob.v2h_entladung_kwh == pytest.approx(25.0)
    assert emob.km_je_fahrzeug == {auto.id: pytest.approx(1000.0)}


@pytest.mark.asyncio
async def test_f7_dienstwagen_faellt_aus_dem_pool_bleibt_aber_ausgewiesen(db):
    """**F-7**: ein dienstlich geladenes Fahrzeug ist keine private Ersparnis.

    Die Komponenten-Dashboards filterten es bisher gar nicht. Die Schicht filtert
    es genau hier — und wirft es nicht weg, weil der Anteil als **Ausgabe** in
    die Sonstige-Summen gehört.
    """
    anlage = await _anlage(db)
    privat = await _inv(db, anlage, "e-auto", "Privat")
    dienst = await _inv(db, anlage, "e-auto", "Dienst", parameter={"ist_dienstlich": True})
    db.add(_imd(privat, 2025, 5, {"km_gefahren": 1000.0, "ladung_pv_kwh": 100.0,
                                  "ladung_netz_kwh": 50.0}))
    db.add(_imd(dienst, 2025, 5, {"km_gefahren": 2000.0, "ladung_pv_kwh": 300.0,
                                  "ladung_netz_kwh": 200.0, "v2h_entladung_kwh": 40.0}))
    await db.commit()

    emob = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 5).emob

    assert emob.ladung_kwh == pytest.approx(150.0), "nur das private Fahrzeug"
    assert emob.km == pytest.approx(1000.0)
    assert emob.v2h_entladung_kwh == 0.0, "V2H des Dienstwagens ist keine eigene Bilanz"
    assert emob.dienstlich_ladung_pv_kwh == pytest.approx(300.0)
    assert emob.dienstlich_ladung_netz_kwh == pytest.approx(200.0)


@pytest.mark.asyncio
async def test_emob_rohdaten_erlauben_die_globale_poolung_ueber_denselben_sot(db):
    """Die durchgereichten Rohdicts sind bereits gefiltert.

    Wer über einen Zeitraum EINMAL poolen will (so rechnet die Cockpit-Übersicht
    heute), bekommt die Eingabe dafür aus der Schicht — statt die ORM-Zeilen ein
    zweites Mal selbst zu laden und dabei den Dienstwagen-Filter zu vergessen.
    """
    anlage = await _anlage(db)
    privat = await _inv(db, anlage, "e-auto", "Privat")
    dienst = await _inv(db, anlage, "e-auto", "Dienst", parameter={"ist_dienstlich": True})
    wb = await _inv(db, anlage, "wallbox", "WB")
    db.add(_imd(privat, 2025, 5, {"ladung_pv_kwh": 100.0, "ladung_netz_kwh": 50.0}))
    db.add(_imd(dienst, 2025, 5, {"ladung_pv_kwh": 300.0}))
    db.add(_imd(wb, 2025, 5, {"ladung_pv_kwh": 120.0, "ladung_netz_kwh": 80.0}))
    await db.commit()

    emob = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 5).emob

    assert len(emob.eauto_ladedaten) == 1, "der Dienstwagen ist nicht dabei"
    assert len(emob.wallbox_ladedaten) == 1


# ═══════════════════════════════════════════════════════════════════════
# Gruppe `wp`
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_wp_wird_kanonisch_gelesen_inklusive_split_flag(db):
    """Wärme = `waerme_kwh`, sonst Heizung + Warmwasser (D1); Split je Anlage."""
    anlage = await _anlage(db)
    wp = await _inv(db, anlage, "waermepumpe", "WP",
                    parameter={"getrennte_strommessung": True})
    db.add(_imd(wp, 2025, 1, {"heizung_kwh": 900.0, "warmwasser_kwh": 100.0,
                              "strom_heizen_kwh": 250.0, "strom_warmwasser_kwh": 50.0}))
    await db.commit()

    fakt_wp = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 1).wp

    assert fakt_wp.heizung_kwh == pytest.approx(900.0)
    assert fakt_wp.warmwasser_kwh == pytest.approx(100.0)
    assert fakt_wp.waerme_kwh == pytest.approx(1000.0), "Heizung + Warmwasser"
    assert fakt_wp.strom_kwh == pytest.approx(300.0), "Split-Summe statt strom_kwh"
    assert fakt_wp.hat_split is True


# ═══════════════════════════════════════════════════════════════════════
# Gruppe `sonstiges`
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sonstige_positionen_kommen_aus_allen_typen_und_der_basis_ebene(db):
    """#310 + G19-1: die Finanz-Positionen hängen nicht am Typ.

    Eine Reparatur am Wechselrichter ist so real wie eine am Speicher; die
    Basis-Positionen der `Monatsdaten`-Zeile wirken genau wie IMD-Positionen.
    """
    anlage = await _anlage(db)
    wr = await _inv(db, anlage, "wechselrichter", "WR")
    verbraucher = await _inv(db, anlage, "sonstiges", "Pool",
                             parameter={"kategorie": "verbraucher"})
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=8,
        einspeisung_kwh=0.0, netzbezug_kwh=100.0,
        sonstige_positionen=[{"bezeichnung": "THG-Quote", "betrag": 200.0,
                              "typ": "ertrag"}],
    ))
    db.add(_imd(wr, 2025, 8, {"sonstige_positionen": [
        {"bezeichnung": "Reparatur", "betrag": 150.0, "typ": "ausgabe"}]}))
    db.add(_imd(verbraucher, 2025, 8, {"verbrauch_sonstig_kwh": 80.0}))
    await db.commit()

    sonstiges = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 8).sonstiges

    assert sonstiges.ertraege_euro == pytest.approx(200.0)
    assert sonstiges.ausgaben_euro == pytest.approx(150.0)
    assert sonstiges.netto_euro == pytest.approx(50.0)
    assert sonstiges.verbrauch_kwh == pytest.approx(80.0)
    assert sonstiges.erzeugung_kwh == 0.0, "kategorie=verbraucher liefert keine Erzeugung"


# ═══════════════════════════════════════════════════════════════════════
# Gruppe `tarif` — P8
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_p8_jeder_monat_traegt_den_tarif_seines_stichtags(db):
    """Eine Preiserhöhung schreibt die Historie **nicht** um.

    Der Stichtag ist der Monatserste: ein Tarif ab dem 15. gilt erst im
    Folgemonat.
    """
    anlage = await _anlage(db)
    await _tarif(db, anlage, ab=date(2024, 1, 1), bis=date(2025, 6, 14), netz=25.0,
                 verguetung=8.0)
    await _tarif(db, anlage, ab=date(2025, 6, 15), netz=35.0, verguetung=7.0)
    for monat in (5, 6, 7):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=monat,
                           einspeisung_kwh=100.0, netzbezug_kwh=100.0))
    await db.commit()

    fakten = await lade_monats_fakten(db, anlage.id)

    assert _fakt(fakten, 2025, 5).tarif.netzbezug_preis_cent == pytest.approx(25.0)
    assert _fakt(fakten, 2025, 6).tarif.netzbezug_preis_cent == pytest.approx(25.0), (
        "der Tarif ab dem 15. gilt im Juni noch nicht"
    )
    juli = _fakt(fakten, 2025, 7).tarif
    assert juli.netzbezug_preis_cent == pytest.approx(35.0)
    assert juli.einspeiseverguetung_cent == pytest.approx(7.0)
    assert juli.grundpreis_euro_monat == pytest.approx(12.0)


@pytest.mark.asyncio
async def test_p8_abgerechneter_flex_durchschnitt_schlaegt_den_stammpreis(db):
    """Der Flex-Ø des Monats hat Vorrang — und geht sonst **still** verloren."""
    anlage = await _anlage(db)
    await _tarif(db, anlage, netz=30.0)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=2,
                       einspeisung_kwh=0.0, netzbezug_kwh=100.0,
                       netzbezug_durchschnittspreis_cent=21.5))
    await db.commit()

    tarif = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 2).tarif

    assert tarif.netzbezug_preis_cent == pytest.approx(21.5)
    assert tarif.netzbezug_stammpreis_cent == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_spezialtarife_fallen_auf_den_allgemeinen_zurueck(db):
    """WP-Spezialtarif greift, Wallbox fällt auf allgemein zurück (§14a)."""
    anlage = await _anlage(db)
    await _tarif(db, anlage, netz=30.0)
    await _tarif(db, anlage, netz=18.0, verwendung="waermepumpe")
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       einspeisung_kwh=0.0, netzbezug_kwh=100.0))
    await db.commit()

    tarif = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 1).tarif

    assert tarif.wp_preis_cent == pytest.approx(18.0)
    assert tarif.wallbox_preis_cent == pytest.approx(30.0)


# ═══════════════════════════════════════════════════════════════════════
# Gruppe `eeg` — §51
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_eeg_negativpreis_je_monat_und_ohne_flag(db):
    """`None` heißt nicht 0: ohne §51-Flag gibt es keinen Abzug."""
    ohne_flag = await _anlage(db)
    mit_flag = await _anlage(db, unterliegt_eeg_51=True)
    for anlage in (ohne_flag, mit_flag):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=4,
                           einspeisung_kwh=500.0, netzbezug_kwh=0.0))
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=5,
                           einspeisung_kwh=500.0, netzbezug_kwh=0.0))
        db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=date(2025, 4, 10),
                                    einspeisung_neg_preis_kwh=12.0))
        db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=date(2025, 4, 11),
                                    einspeisung_neg_preis_kwh=8.0))
    await db.commit()

    mit = await lade_monats_fakten(db, mit_flag.id)
    assert _fakt(mit, 2025, 4).eeg.neg_preis_kwh == pytest.approx(20.0)
    assert _fakt(mit, 2025, 5).eeg.neg_preis_kwh is None, (
        "Monat ohne Mitschrift ist eine Lücke, keine 0"
    )

    ohne = await lade_monats_fakten(db, ohne_flag.id)
    assert _fakt(ohne, 2025, 4).eeg.neg_preis_kwh is None


@pytest.mark.asyncio
async def test_neg_preis_bulk_und_einzelabfrage_sagen_dasselbe(db):
    """Der Bulk-Weg ist ein Query, keine zweite Wahrheit.

    Zwei Wege zu derselben Größe sind genau die Konstellation, aus der die
    Inventur-Befunde entstanden sind — deshalb hier festgenagelt.
    """
    anlage = await _anlage(db, unterliegt_eeg_51=True)
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=date(2025, 4, 10),
                                einspeisung_neg_preis_kwh=12.0))
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=date(2025, 4, 11),
                                einspeisung_neg_preis_kwh=8.0))
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=date(2025, 6, 1),
                                einspeisung_neg_preis_kwh=0.0))
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=date(2025, 7, 1),
                                einspeisung_neg_preis_kwh=None))
    await db.commit()

    bulk = await get_neg_preis_einspeisung_je_monat(db, anlage.id)

    for jahr, monat in ((2025, 4), (2025, 6), (2025, 7)):
        einzeln = await get_neg_preis_einspeisung_monat(db, anlage.id, jahr, monat)
        assert bulk.get((jahr, monat)) == einzeln, f"Drift in {jahr}-{monat:02d}"


# ═══════════════════════════════════════════════════════════════════════
# Gruppe `kennzahlen`
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_kennzahlen_zaehlen_v2h_wie_eine_zweite_batterie(db):
    """**F-1**: ohne V2H fallen Eigenverbrauch und Autarkie zu niedrig aus (#304)."""
    anlage = await _anlage(db)
    pv = await _inv(db, anlage, "pv-module", leistung_kwp=10.0)
    speicher = await _inv(db, anlage, "speicher", "S", leistung_kwp=10.0)
    auto = await _inv(db, anlage, "e-auto", "Auto")
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=200.0))
    db.add(_imd(pv, 2025, 6, {"pv_erzeugung_kwh": 1000.0}))
    db.add(_imd(speicher, 2025, 6, {"ladung_kwh": 200.0, "entladung_kwh": 180.0}))
    db.add(_imd(auto, 2025, 6, {"v2h_entladung_kwh": 50.0}))
    await db.commit()

    kz = _fakt(await lade_monats_fakten(db, anlage.id), 2025, 6).kennzahlen

    assert kz.direktverbrauch_kwh == pytest.approx(400.0)
    assert kz.eigenverbrauch_kwh == pytest.approx(630.0), "400 + 180 Speicher + 50 V2H"
    assert kz.gesamtverbrauch_kwh == pytest.approx(830.0)


@pytest.mark.asyncio
async def test_perioden_kennzahlen_summieren_die_mengen_vor_der_formel(db):
    """`max(0, …)` klemmt — monatsweise geklemmt und summiert ist etwas anderes.

    Die vier Finanz-Sichten rechnen über die Perioden-Summen. `kennzahlen_aus_
    fakten` tut dasselbe, damit ein Umhängen auf die Schicht keine Zahl still
    verschiebt.
    """
    anlage = await _anlage(db)
    pv = await _inv(db, anlage, "pv-module", leistung_kwp=10.0)
    # Januar: Einspeisung > Erzeugung (Zähler-Zeitversatz) → monatsweise geklemmt.
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       einspeisung_kwh=200.0, netzbezug_kwh=0.0))
    db.add(_imd(pv, 2025, 1, {"pv_erzeugung_kwh": 100.0}))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=2,
                       einspeisung_kwh=100.0, netzbezug_kwh=0.0))
    db.add(_imd(pv, 2025, 2, {"pv_erzeugung_kwh": 500.0}))
    await db.commit()

    fakten = await lade_monats_fakten(db, anlage.id)

    monatsweise = sum(f.kennzahlen.direktverbrauch_kwh for f in fakten)
    periode = kennzahlen_aus_fakten(fakten)

    assert monatsweise == pytest.approx(400.0), "Januar auf 0 geklemmt"
    assert periode.direktverbrauch_kwh == pytest.approx(300.0), (
        "600 erzeugt − 300 eingespeist — die Perioden-Rechnung der Finanz-Sichten"
    )


# ═══════════════════════════════════════════════════════════════════════
# Zeitfilter — der eine Ort (aktiv · Anschaffung · Stilllegung)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_zeitfilter_greifen_genau_hier(db):
    """Vor Anschaffung, nach Stilllegung, deaktiviert → nichts davon zählt.

    #153/#155/#236/#308: dieselbe Regel lag bisher in jeder Sicht neu — und in
    den Komponenten-Dashboards gar nicht.
    """
    anlage = await _anlage(db)
    frueh = await _inv(db, anlage, "speicher", "Neuzugang", leistung_kwp=10.0,
                       anschaffungsdatum=date(2025, 6, 1))
    alt = await _inv(db, anlage, "speicher", "Stillgelegt", leistung_kwp=10.0,
                     stilllegungsdatum=date(2025, 3, 31))
    aus = await _inv(db, anlage, "speicher", "Deaktiviert", leistung_kwp=10.0,
                     aktiv=False)
    for inv in (frueh, alt, aus):
        db.add(_imd(inv, 2025, 5, {"ladung_kwh": 100.0}))
        db.add(_imd(inv, 2025, 8, {"ladung_kwh": 100.0}))
    for monat in (5, 8):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=monat,
                           einspeisung_kwh=0.0, netzbezug_kwh=100.0))
    await db.commit()

    fakten = await lade_monats_fakten(db, anlage.id)

    mai = _fakt(fakten, 2025, 5)
    assert mai.speicher.ladung_kwh == 0.0, (
        "vor Anschaffung / nach Stilllegung / deaktiviert — keine Zeile zählt"
    )
    assert mai.meta.aktive_investitionen == ()

    august = _fakt(fakten, 2025, 8)
    assert august.speicher.ladung_kwh == pytest.approx(100.0), "nur der Neuzugang"
    assert august.meta.aktive_investitionen == (frueh.id,)


@pytest.mark.asyncio
async def test_erzeuger_fenster_meldet_monate_vor_der_inbetriebnahme(db):
    """Die Anschaffungs-Grenze als Flag statt als Regel in jeder Sicht."""
    anlage = await _anlage(db)
    await _inv(db, anlage, "pv-module", leistung_kwp=10.0,
               anschaffungsdatum=date(2025, 4, 1))
    for monat in (3, 4):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=monat,
                           einspeisung_kwh=0.0, netzbezug_kwh=300.0))
    await db.commit()

    fakten = await lade_monats_fakten(db, anlage.id)

    assert _fakt(fakten, 2025, 3).meta.erzeuger_aktiv is False
    assert _fakt(fakten, 2025, 4).meta.erzeuger_aktiv is True


@pytest.mark.asyncio
async def test_fenster_von_bis_schneidet_monatsgenau(db):
    """`von`/`bis` sind inklusive und schneiden über Jahresgrenzen monatsgenau."""
    anlage = await _anlage(db)
    for jahr, monat in ((2024, 11), (2024, 12), (2025, 1), (2025, 2)):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=jahr, monat=monat,
                           einspeisung_kwh=0.0, netzbezug_kwh=100.0))
    await db.commit()

    fakten = await lade_monats_fakten(db, anlage.id, von=(2024, 12), bis=(2025, 1))

    assert [f.schluessel for f in fakten] == [(2024, 12), (2025, 1)]


# ═══════════════════════════════════════════════════════════════════════
# Übersetzung in die Finanz-Zeilen-Eingabe
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_finanz_zeile_eingabe_traegt_bkw_und_monatsdaten(db):
    """P9 + P8 in der Übersetzung: Rest-Term statt Rohwert, `monatsdaten` dabei.

    Der Finanz-Zeilen-Builder bekommt damit seine Eingabe aus EINER Quelle statt
    aus zwölf site-eigenen Dicts.
    """
    anlage = await _anlage(db)
    pv = await _inv(db, anlage, "pv-module", leistung_kwp=10.0)
    bkw = await _inv(db, anlage, "balkonkraftwerk", "BKW", leistung_kwp=0.8)
    auto = await _inv(db, anlage, "e-auto", "Auto")
    monatsdaten = Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=9,
                              einspeisung_kwh=300.0, netzbezug_kwh=150.0,
                              netzbezug_durchschnittspreis_cent=22.0)
    db.add(monatsdaten)
    db.add(_imd(pv, 2025, 9, {"pv_erzeugung_kwh": 800.0}))
    db.add(_imd(bkw, 2025, 9, {"eigenverbrauch_kwh": 60.0}))
    db.add(_imd(auto, 2025, 9, {"v2h_entladung_kwh": 20.0}))
    await db.commit()

    eingabe = finanz_zeile_eingabe(_fakt(await lade_monats_fakten(db, anlage.id), 2025, 9))

    assert (eingabe.jahr, eingabe.monat) == (2025, 9)
    assert eingabe.einspeisung_kwh == pytest.approx(300.0)
    assert eingabe.netzbezug_kwh == pytest.approx(150.0)
    assert eingabe.pv_erzeugung_kwh == pytest.approx(800.0), "Module + BKW (hier 0)"
    assert eingabe.bkw_eigenverbrauch_kwh == pytest.approx(60.0), (
        "Datenlücke → der gemessene Eigenverbrauch trägt"
    )
    assert eingabe.v2h_entladung_kwh == pytest.approx(20.0)
    assert eingabe.monatsdaten is monatsdaten, "sonst geht der Flex-Ø still verloren"
