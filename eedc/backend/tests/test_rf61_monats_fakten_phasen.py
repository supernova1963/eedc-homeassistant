"""RF-61 … RF-63 — benannte Proben für Zweige der Monats-Fakten-Schicht, die weder die direkten Testdateien noch die
Golden Masters am HEAD 7b45d6f23 betreten haben (Zeilenspur `refactoring-werkzeug/rf61/ausgaben/abdeckung-alle-head.txt`).

Gegenstand sind die drei Funktionen, die RF-61 … RF-63 in Phasen geschnitten haben: `laden.py::lade_monats_fakten`,
`bau.py::_baue_fakt`, `roh.py::_RohMonat.falte`. Jede Probe ist am HEAD grün (vor dem Schnitt) und hält die Regel, deren
Phase sie trifft. Zwei stammen aus der Zeilenspur (die Schätzung mit Tages-Quote und ihre Gegenprobe), acht aus der
Gegenprobe des Schnitts: Sprengsätze, die weder die direkten Testdateien noch die Golden Masters noch die Regressionstests
ihres Funds rot machten (`refactoring-werkzeug/rf61/saetze.py`, Kennung im Docstring der Probe).

Schwesterdateien: test_rf56_kanal_leser_phasen.py (Bauform der Proben), test_monats_fakten_schicht.py,
test_n555_fahrverbrauch_bleibt_fahrverbrauch.py, test_pv_anteil_ladung_anschluss.py.
"""

from __future__ import annotations

import pytest

from backend.services.energie_profil.monats_aus_tagen import TagesMonatsSumme
from backend.services.monats_fakten import TAGESWERT_EMOB_ANTEIL, TAGESWERT_WP, lade_monats_fakten
from backend.services.monats_fakten.bau import _baue_fakt
from backend.services.monats_fakten.roh import _RohMonat
from backend.tests import factories

J, M = 2025, 7


@pytest.mark.asyncio
async def test_rf63_schaetzung_mit_tagesquote_markiert_den_abgeleiteten_anteil(db):
    """`_emob_entscheid` (RF-63, N-555 Regel 1): ein privates E-Auto ohne Heimlade-Wert und ohne Wallbox trägt den
    Fahrverbrauch als Schätzung; mit der Tages-Quote (30 %) ist ihr PV-Teil **abgeleitet** — die Marke kommt aus dem
    Entscheid, nicht aus der Anreicherung (die Zeile hat keine Ladung, die sie teilen könnte). Ohne die Marke stünde
    der Monat ohne Hinweis «PV-Anteil abgeleitet» da."""
    a = await factories.anlage(db)
    auto = await factories.investition(db, a.id, "e-auto", bezeichnung="Auto")
    await db.commit()
    roh = _RohMonat()
    roh.falte(auto, {"km_gefahren": 600.0, "verbrauch_kwh": 100.0})
    fakt = await _baue_fakt(
        db, a.id, (J, M), roh,
        monatsdaten=None, pv_modul_summe=None, pv_je_modul={}, investitionen=[auto], neg_preis_kwh=None,
        tarif_cache={}, zeittarif_cache={},
        tages_summe=TagesMonatsSumme(emob_ladung_pv_abgeleitet_kwh=30.0, emob_ladung_netz_abgeleitet_kwh=70.0),
    )
    assert fakt.emob.ladung_anteil_abgeleitet is True
    assert TAGESWERT_EMOB_ANTEIL in fakt.meta.tageswert_gruppen
    assert fakt.emob.je_auto[auto.id].pv_kwh == pytest.approx(30.0)
    assert fakt.emob.je_auto[auto.id].netz_kwh == pytest.approx(70.0)


@pytest.mark.asyncio
async def test_rf63_schaetzung_ohne_tagesquote_bleibt_ohne_marke(db):
    """Gegenprobe zu oben: ohne Tages-Quote ist die Schätzung ganz Netz und **nicht** abgeleitet."""
    a = await factories.anlage(db)
    auto = await factories.investition(db, a.id, "e-auto", bezeichnung="Auto")
    await db.commit()
    roh = _RohMonat()
    roh.falte(auto, {"km_gefahren": 600.0, "verbrauch_kwh": 100.0})
    fakt = await _baue_fakt(
        db, a.id, (J, M), roh,
        monatsdaten=None, pv_modul_summe=None, pv_je_modul={}, investitionen=[auto], neg_preis_kwh=None,
        tarif_cache={}, zeittarif_cache={}, tages_summe=None,
    )
    assert fakt.emob.ladung_anteil_abgeleitet is False
    assert TAGESWERT_EMOB_ANTEIL not in fakt.meta.tageswert_gruppen
    assert fakt.emob.je_auto[auto.id].netz_kwh == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_rf61_wp_gruppe_aus_den_kanaelen_traegt_ihre_marke_in_den_monat(db, monkeypatch):
    """`_kanal_gruppen` (RF-61, E4d): deckt die WP-Gruppe einen Monat ohne WP-Zeile aus den Kanälen, faltet
    `_modus_split_ohne_abschluss` die Kanal-Zeile ein, und ihre Marke `TAGESWERT_WP` muss in den Tageswert-Gruppen des
    Monats ankommen — *Auswertungen → Tabelle* nennt sie in `aus_tageswerten`. Gefunden als stiller Sprengsatz L09
    (Zusammenführung der WP-Marken gestrichen: Tests und Golden Masters grün). Der Kanal-Leser ist gestellt (eine
    Kanal-Wahl mit Strom und Wärme für EIN Gerät), alles übrige läuft echt."""
    from backend.services.kanal import wp_leser
    from backend.services.kanal.quellenwahl import QUELLE_KANAL, Quellenwahl

    a = await factories.anlage(db)
    wp = await factories.investition(db, a.id, "waermepumpe", bezeichnung="WP")
    await db.commit()

    async def _wp_monate(_db, _aid, *, von=None, bis=None, jetzt=None):
        return {(J, M): wp_leser.WpZeitraum(
            wahl=Quellenwahl(quelle=QUELLE_KANAL),
            zeilen={wp.id: {"stromverbrauch_kwh": 300.0, "heizenergie_kwh": 1050.0}},
        )}

    monkeypatch.setattr(wp_leser, "wp_monate", _wp_monate)
    fakten = await lade_monats_fakten(db, a.id, von=(J, M), bis=(J, M), inkl_nur_tageswerte=True)
    assert [(f.jahr, f.monat) for f in fakten] == [(J, M)]
    assert TAGESWERT_WP in fakten[0].meta.tageswert_gruppen
    assert fakten[0].wp.strom_kwh == pytest.approx(300.0)


@pytest.mark.asyncio
async def test_rf63_bkw_rest_ist_nie_kleiner_als_die_eigene_messung(db):
    """`_bkw_rest` (RF-63, N-640): `BKW = gemessen + max(0, Tages_Module + Tages_BKW − Modulsumme − gemessen)`. Liegt die
    gespeicherte Modulsumme (600) über dem Anlagenzähler der Tage (500 + 50), bleibt dem Balkonkraftwerk seine eigene
    Messung (20) — ohne `max(0, …)` fiele der Rest negativ und das BKW auf 0. Gefunden als stiller Sprengsatz B03."""
    from backend.services.monats_fakten import TAGESWERT_BKW

    a = await factories.anlage(db)
    bkw = await factories.investition(db, a.id, "balkonkraftwerk", bezeichnung="BKW", leistung_kwp=0.8)
    await db.commit()
    fakt = await _baue_fakt(
        db, a.id, (J, M), _RohMonat(),
        monatsdaten=None, pv_modul_summe=600.0, pv_je_modul={}, investitionen=[bkw], neg_preis_kwh=None,
        tarif_cache={}, zeittarif_cache={},
        tages_summe=TagesMonatsSumme(
            pv_module_kwh=500.0, bkw_kwh=50.0,
            bkw_je_inv={str(bkw.id): 50.0}, bkw_gemessen_je_inv={str(bkw.id): 20.0},
        ),
    )
    assert fakt.bkw.erzeugung_kwh == pytest.approx(20.0)
    assert TAGESWERT_BKW in fakt.meta.tageswert_gruppen
    assert fakt.erzeugung.pv_kwh == pytest.approx(620.0)


@pytest.mark.asyncio
async def test_rf62_dienstliche_wallbox_ist_die_dienstliche_ladung(db):
    """`_falte_emob` (RF-62, N-555 Stufe 2 Regel 3): die Zeile einer **dienstlichen Wallbox** wird als solche markiert
    (`dienstliche_wallbox_ids`) — ihre Menge ist die dienstliche Ladung des Monats und gehört zur Netzladung der
    Wallbox-Zeilen (F12). Ohne die Marke liefe sie als Dienstwagen-Zeile, und mit der dienstlichen Wallbox in Betrieb
    zählte sie gar nicht. Gefunden als stiller Sprengsatz R10."""
    a = await factories.anlage(db)
    dwb = await factories.investition(db, a.id, "wallbox", bezeichnung="Firmen-WB", parameter={"ist_dienstlich": True})
    await db.commit()
    roh = _RohMonat()
    roh.falte(dwb, {"ladung_kwh": 100.0, "ladung_pv_kwh": 30.0, "ladung_netz_kwh": 70.0})
    assert roh.dienstliche_wallbox_ids == {dwb.id}
    fakt = await _baue_fakt(
        db, a.id, (J, M), roh,
        monatsdaten=None, pv_modul_summe=None, pv_je_modul={}, investitionen=[dwb], neg_preis_kwh=None,
        tarif_cache={}, zeittarif_cache={}, tages_summe=None,
    )
    assert fakt.emob.dienstlich_ladung_pv_kwh == pytest.approx(30.0)
    assert fakt.emob.dienstlich_ladung_netz_kwh == pytest.approx(70.0)
    assert fakt.emob.wallbox_netzladung_kwh == pytest.approx(70.0)


@pytest.mark.asyncio
async def test_rf61_ohne_flag_oeffnet_der_kanal_keinen_neuen_monat(db, monkeypatch):
    """`_LadeKontext.offen` (RF-61, N-121): wird die Tagesebene nur für den Ladeanteil geladen (eine Wallbox-Zeile ohne
    PV-Anteil, N-141 Weg c), darf eine Kanal-Gruppe keinen Monat ohne Spur aufmachen — sonst tauchte in jeder Sicht ohne
    `inkl_nur_tageswerte` ein Monat auf, der nur eine Kanalspur hat. Mit dem Flag gehört er dazu. Gefunden als stiller
    Sprengsatz L20 (`offen` immer wahr: Tests und Golden Masters grün)."""
    from backend.services.kanal import wp_leser
    from backend.services.kanal.quellenwahl import QUELLE_KANAL, Quellenwahl

    a = await factories.anlage(db)
    wp = await factories.investition(db, a.id, "waermepumpe", bezeichnung="WP")
    wb = await factories.investition(db, a.id, "wallbox", bezeichnung="WB")
    await factories.imd(db, wb.id, J, M, {"ladung_kwh": 100.0})
    await db.commit()

    async def _wp_monate(_db, _aid, *, von=None, bis=None, jetzt=None):
        return {(J, M + 1): wp_leser.WpZeitraum(
            wahl=Quellenwahl(quelle=QUELLE_KANAL),
            zeilen={wp.id: {"stromverbrauch_kwh": 300.0, "heizenergie_kwh": 1050.0}},
        )}

    monkeypatch.setattr(wp_leser, "wp_monate", _wp_monate)
    ohne = await lade_monats_fakten(db, a.id, von=(J, 1), bis=(J, 12))
    assert [(f.jahr, f.monat) for f in ohne] == [(J, M)]
    mit = await lade_monats_fakten(db, a.id, von=(J, 1), bis=(J, 12), inkl_nur_tageswerte=True)
    assert [(f.jahr, f.monat) for f in mit] == [(J, M), (J, M + 1)]


@pytest.mark.asyncio
async def test_rf62_sonstiger_erzeuger_mit_null_ist_eine_erzeuger_zeile(db):
    """`_falte_sonstiges` (RF-62, P4): ein sonstiger Erzeuger (Kategorie «erzeuger»), der im Monat 0 kWh erzeugt hat, ist
    ein echter 0-Wert, kein «nicht vorhanden» — die Marke `hat_erzeuger_zeile` trägt ihn (*Auswertungen → Tabelle* zeigt
    dann 0 statt «—», `monatsdaten_aggregiert.py`). Gegenstück: ein Verbraucher mit 0 kWh. Gefunden als stiller
    Sprengsatz R13."""
    a = await factories.anlage(db)
    bhkw = await factories.investition(db, a.id, "sonstiges", bezeichnung="BHKW", parameter={"kategorie": "erzeuger"})
    heizstab = await factories.investition(db, a.id, "sonstiges", bezeichnung="Heizstab",
                                           parameter={"kategorie": "verbraucher"})
    await db.commit()
    roh = _RohMonat()
    roh.falte(bhkw, {"erzeugung_kwh": 0.0})
    roh.falte(heizstab, {"verbrauch_sonstig_kwh": 0.0})
    fakt = await _baue_fakt(
        db, a.id, (J, M), roh,
        monatsdaten=None, pv_modul_summe=None, pv_je_modul={}, investitionen=[bhkw, heizstab], neg_preis_kwh=None,
        tarif_cache={}, zeittarif_cache={}, tages_summe=None,
    )
    assert fakt.sonstiges.hat_erzeuger_zeile is True
    assert fakt.sonstiges.hat_verbraucher_zeile is True
    assert fakt.sonstiges.erzeugung_kwh == 0.0


@pytest.mark.asyncio
async def test_rf63_rest_der_wallbox_geht_nur_an_autos_in_betrieb(db):
    """`_emob_entscheid` (RF-63, N-555 Regel 2 Schritt 3): Empfänger des Wallbox-Rests sind die privaten Autos **in
    Betrieb** dieses Monats — auch ohne Monatszeile, aber nie eines, das erst später angeschafft wird. Gefunden als
    stiller Sprengsatz B20 (Zeitfilter der Empfänger gestrichen: Tests und Golden Masters grün)."""
    from datetime import date

    a = await factories.anlage(db)
    wb = await factories.investition(db, a.id, "wallbox", bezeichnung="WB")
    alt = await factories.investition(db, a.id, "e-auto", bezeichnung="Auto alt")
    neu = await factories.investition(db, a.id, "e-auto", bezeichnung="Auto neu", anschaffungsdatum=date(J + 1, 1, 1))
    await db.commit()
    roh = _RohMonat()
    roh.falte(wb, {"ladung_kwh": 100.0, "ladung_pv_kwh": 40.0, "ladung_netz_kwh": 60.0})
    fakt = await _baue_fakt(
        db, a.id, (J, M), roh,
        monatsdaten=None, pv_modul_summe=None, pv_je_modul={}, investitionen=[wb, alt, neu], neg_preis_kwh=None,
        tarif_cache={}, zeittarif_cache={}, tages_summe=None,
    )
    assert set(fakt.emob.je_auto) == {alt.id}
    assert fakt.emob.je_auto[alt.id].pv_kwh == pytest.approx(40.0)
    assert fakt.emob.je_auto[alt.id].netz_kwh == pytest.approx(60.0)


@pytest.mark.asyncio
async def test_rf62_stillstehendes_zweitgeraet_mischt_keine_bauart(db):
    """`_falte_wp` (RF-62, R2/Bauart SOLL §5): die Bauart-Zähler zählen nur Geräte, die im Monat **Strom** beitragen — eine
    Split-Klimaanlage, die stillsteht (Zeile mit 0 kWh), macht den Block einer Luft-Wasser-WP nicht «gemischt», und die
    Arbeitszahl bleibt ohne den Grund «Wärmepumpe und Klimaanlage in einer Zahl». Läuft sie, ist der Block gemischt.
    Gefunden als stiller Sprengsatz R17."""
    a = await factories.anlage(db)
    wp = await factories.investition(db, a.id, "waermepumpe", bezeichnung="WP", parameter={"wp_art": "luft_wasser"})
    klima = await factories.investition(db, a.id, "waermepumpe", bezeichnung="Klima", parameter={"wp_art": "luft_luft"})
    await db.commit()

    async def _fakt(klima_strom: float):
        roh = _RohMonat()
        roh.falte(wp, {"stromverbrauch_kwh": 300.0, "heizenergie_kwh": 1050.0})
        roh.falte(klima, {"stromverbrauch_kwh": klima_strom})
        return await _baue_fakt(
            db, a.id, (J, M), roh,
            monatsdaten=None, pv_modul_summe=None, pv_je_modul={}, investitionen=[wp, klima], neg_preis_kwh=None,
            tarif_cache={}, zeittarif_cache={}, tages_summe=None,
        )

    still = await _fakt(0.0)
    assert (still.wp.geraete_luft_luft, still.wp.geraete_luft_wasser) == (0, 1)
    assert still.wp.bauarten_gemischt is False
    laeuft = await _fakt(50.0)
    assert (laeuft.wp.geraete_luft_luft, laeuft.wp.geraete_luft_wasser) == (1, 1)
    assert laeuft.wp.bauarten_gemischt is True


@pytest.mark.asyncio
async def test_rf61_nachgetragener_split_kuerzt_nach_der_stufe_der_zeile(db, monkeypatch):
    """`_roh_je_monat` (RF-61, N-462): der Nachtrag des Modus-Splits (F-52) fragt die **Stufe** der Monatszeile, nicht das
    Kennzeichen `getrennte_strommessung`. Trägt die Zeile nur den Gesamtzähler (Stufe «gesamt»), steckt der Kühlstrom im
    Nenner und wird ganz abgezogen — auch wenn das Gerät auf «getrennt» steht (am Kennzeichen festgemacht: 0, die
    Arbeitszahl zu niedrig). Der Split ist gestellt (die Weiche `lade_modus_split_mit_kanaelen`), alles übrige echt.
    Gefunden als stiller Sprengsatz L21 (Buchführung der Stufe gestrichen: Tests und Golden Masters grün)."""
    from backend.services.energie_profil.modus_split_monat import AngewandterSplit
    from backend.services.monats_fakten import laden

    a = await factories.anlage(db)
    wp = await factories.investition(db, a.id, "waermepumpe", bezeichnung="WP",
                                     parameter={"getrennte_strommessung": True})
    await factories.imd(db, wp.id, J, M, {"stromverbrauch_kwh": 300.0, "heizenergie_kwh": 900.0})
    await db.commit()

    async def _split(_db, _aid, **_kw):
        return {(J, M): {str(wp.id): AngewandterSplit(
            heizen_kwh=200.0, kuehlen_kwh=40.0, warmwasser_kwh=60.0, abdeckung_h=700.0, bezug_kwh=300.0,
        )}}

    monkeypatch.setattr(laden, "lade_modus_split_mit_kanaelen", _split)
    (fakt,) = await lade_monats_fakten(db, a.id, von=(J, M), bis=(J, M))
    assert fakt.wp.modus_strom_funktionsfremd_abzug_kwh == pytest.approx(40.0)
