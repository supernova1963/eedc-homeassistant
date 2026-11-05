"""RF-67 … RF-70 — benannte Proben der Zweige, die vor dem Phasenschnitt (Bauform RF-1) weder die direkten Testdateien
noch die Golden Master (`cockpit-monat` mit Fixtures und drei DB-Kopien, `analyse-sichten` A1 `pv-strings`) ausführten,
dazu die Regeln, deren Sprengsätze sonst still blieben (Bogen-Spur 5.11.2026, BASIS 7b45d6f23).

Geschnitten werden vier Funktionen:

* `aktueller_monat/waerme.py::waerme_klima_monat` (RF-67) — Kennzahlen je Gerät mit Kanal-Zeilen vor der Tagesebene,
  die R2-/SOLL-§3.2b-Abgrenzung mit S5-Rückfall, die Systemarbeitszahl mit Schranke, die WP-Ersparnis als Σ Gerätezeilen;
* `aktueller_monat/komponenten.py::geraete_sicht` (RF-68) — E-Mob-Split aus dem Pool (C1d/N-555), Sonstiges, R15-1;
* `aktueller_monat/quellen_leser.py::_geraete_aus_kanaelen` (RF-69) — Quelle je Gruppe mit und ohne HA (N-750);
* `cockpit/pv_strings.py::get_pv_strings` (RF-70) — SOLL nur in Monaten mit IST, F-34, Prognose je Modul, Ranking.

Die Proben rufen die Funktionen **in-process**: die Wärme-Route mit gestellten Kennzahlen je Gerät und gestelltem
Monatstarif (an `waerme.py`), die Gerätesicht mit gestellten Monats-Fakt-Teilen, der Kanal-Leser mit gestelltem
`geraete_kalendermonate` (an seinem Modul, wie `cockpit-monat`), die PV-Strings über die `db`-Fixture. Charakterisierung
des Verhaltens vor dem Schnitt: am HEAD und nach RF-70 gleich grün. Schwesterdateien: `test_rf47_aktueller_monat_phasen.py`,
`test_n750_kanal_gruppen_ohne_ha.py`, `test_pv_strings_kwp_verteilung.py`, `test_n661_soll_nenner_prognose_kwp.py`.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest

import backend.api.routes.aktueller_monat.waerme as waerme_mod
from backend.api.routes.aktueller_monat.komponenten import geraete_sicht
from backend.api.routes.aktueller_monat.quellen_leser import _geraete_aus_kanaelen
from backend.api.routes.aktueller_monat.schemas import DatenquelleInfo
from backend.api.routes.cockpit.pv_strings import get_pv_strings
from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_BAUARTEN_GEMISCHT,
    GRUND_GERAETE_OHNE_WAERME,
    GRUND_ZEITRAUM,
)
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.monats_fakten.fakten_wp import WpFakten
from backend.services.waermepumpe_kennzahlen_je_geraet import kennzahlen_aus_mengen, mengen_aus_tageswerten

_HA = DatenquelleInfo(quelle="ha_statistics", konfidenz=92)
_OHNE_HA = DatenquelleInfo(quelle="tagesebene", konfidenz=70)

_WP_PARAM = {"effizienz_modus": "gesamt_jaz", "jaz": 3.5, "alter_energietraeger": "gas",
             "alter_preis_cent_kwh": 12.0, "waermebedarf_kwh": 12000.0}


def _inv(inv_id: int, typ: str = "waermepumpe", **kw) -> Investition:
    kw.setdefault("parameter", dict(_WP_PARAM) if typ == "waermepumpe" else {})
    return Investition(id=inv_id, anlage_id=1, typ=typ, bezeichnung=f"{typ} {inv_id}",
                       anschaffungsdatum=date(2024, 1, 1), aktiv=True, **kw)


# ── RF-67 `waerme_klima_monat` ────────────────────────────────────────────────────────────────────────────────────

def _kennzahl(inv, strom=0.0, waerme=0.0, heizung=0.0):
    return kennzahlen_aus_mengen(mengen_aus_tageswerten(
        inv, strom_kwh=strom, waerme_kwh=waerme, heizung_kwh=heizung, warmwasser_kwh=0.0, strom_heizen_kwh=0.0,
        strom_warmwasser_kwh=0.0, kaelte_kwh=0.0, modus_strom_kuehlen_kwh=0.0, funktionsfremd_abzug_kwh=0.0,
        waerme_ist_gesamt=bool(waerme), strom_gemessen=strom > 0, waerme_gemessen=waerme > 0,
    ))


def _tagesmengen(strom, waerme):
    return SimpleNamespace(strom_kwh=strom, waerme_kwh=waerme, heizung_kwh=0.0, warmwasser_kwh=0.0, strom_heizen_kwh=0.0,
                           strom_warmwasser_kwh=0.0, kaelte_kwh=0.0, modus_strom_kuehlen_kwh=0.0,
                           funktionsfremd_abzug_kwh=0.0, gemessen=("strom_kwh", "waerme_kwh"))


def _fakt(**lagen):
    """Monats-Fakt mit einer WP-Gruppe ohne Menge (S5: die Geräte-Mengen tragen) und den gestellten R2-Lagen."""
    wp = dict(strom_kwh=0.0, waerme_kwh=0.0, waerme_abgeleitet_kwh=0.0, abgrenzung_stoerung=None,
              bauarten_gemischt=False, waerme_deckt_nicht_alle_geraete=False, geraete_verschieden=False,
              modus_strom_funktionsfremd_abzug_kwh=0.0, je_geraet={})
    wp.update(lagen)
    return SimpleNamespace(wp=SimpleNamespace(**wp, deckung_je_funktion=lambda f: None))


@pytest.fixture
def waerme(monkeypatch):
    """`waerme_klima_monat` für Juli 2026 mit gestellten Kennzahlen je Gerät und WP-Preis 30 ct."""
    async def _lauf(invs, kennzahlen, **kw):
        async def _lade(*a, **k):
            return kennzahlen

        async def _tarif(*a, **k):
            return SimpleNamespace(wp_preis_cent=30.0)
        monkeypatch.setattr(waerme_mod, "lade_kennzahlen_je_geraet", _lade)
        monkeypatch.setattr(waerme_mod, "monatstarif_der_route", _tarif)
        args = dict(resolved=None, _tages_wp_mengen=None, kanal_wp_zeilen=None, _zt_cache=None, allgemein_tarif=None,
                    anlage_id=1, db=None, get_val=lambda k: None, investitionen=invs, jahr=2026, monat=7,
                    monats_fakt=None, monats_gaspreis=12.0, netzbezug_preis_effektiv_cent=30.0, tarife={},
                    teilzeitraum=set(), wp_strom=100.0, wp_waerme=350.0)
        args.update(kw)
        out = await waerme_mod.waerme_klima_monat(**args)
        assert sorted(out) == sorted((
            "_wp_abgrenzung_je_funktion", "_wp_funktion", "_wp_kennzahlen_je_geraet", "wp_abgrenzung_verletzt",
            "wp_arbeitszahl", "wp_ersparnis", "wp_ersparnis_berechnung_text", "wp_ersparnis_vorbehalt",
            "wp_waerme_abgeleitet_kwh", "wp_waerme_herkunft"))
        return out
    return _lauf


@pytest.mark.asyncio
@pytest.mark.parametrize("teilzeitraum, wert, grund", [
    (set(), 3.5, None),
    ({"wp_waerme_kwh"}, None, GRUND_ZEITRAUM),          # genau eine Seite versetzt ⇒ gesperrt (SOLL §4.2 Fall 3)
    ({"wp_strom_kwh"}, None, GRUND_ZEITRAUM),
    ({"wp_waerme_kwh", "wp_strom_kwh"}, 3.5, None),     # beide Seiten derselbe Ausschnitt ⇒ eine Wirklichkeit
])
async def test_r2_zeitraum_versatz_sperrt_die_zahl_und_jede_funktion(waerme, teilzeitraum, wert, grund):
    a = _inv(1)
    out = await waerme([a], [_kennzahl(a, 100.0, 350.0)], monats_fakt=SimpleNamespace(wp=WpFakten(
        strom_kwh=100.0, waerme_kwh=350.0)), teilzeitraum=teilzeitraum)
    assert out["wp_arbeitszahl"].wert == wert
    assert out["wp_arbeitszahl"].grund == grund
    assert out["wp_abgrenzung_verletzt"] == grund
    assert out["_wp_abgrenzung_je_funktion"] == {"heizen": grund, "warmwasser": grund, "kuehlen": grund}


@pytest.mark.asyncio
async def test_e4d_kanal_zeile_vor_der_tagesebene(waerme):
    """Ein Gerät ohne Menge, Kanal-Zeile (100/400) UND Tagesmengen (50/100): die Kanal-Zeile gewinnt."""
    a = _inv(1)
    out = await waerme([a], [_kennzahl(a)], kanal_wp_zeilen={1: {"stromverbrauch_kwh": 100.0, "heizenergie_kwh": 400.0}},
                       _tages_wp_mengen={"1": _tagesmengen(50.0, 100.0)})
    m = out["_wp_kennzahlen_je_geraet"][0].mengen
    assert (m.strom_kwh, m.waerme_kwh) == (100.0, 400.0)


@pytest.mark.asyncio
async def test_n472_tagesebene_fuellt_nur_ohne_kanal_zeile(waerme):
    a = _inv(1)
    out = await waerme([a], [_kennzahl(a)], _tages_wp_mengen={"1": _tagesmengen(50.0, 100.0)})
    m = out["_wp_kennzahlen_je_geraet"][0].mengen
    assert (m.strom_kwh, m.waerme_kwh) == (50.0, 100.0)


@pytest.mark.asyncio
async def test_ersetzt_wird_nur_was_leer_ist(waerme):
    """Trägt das Gerät schon eine Menge (10/20), ändern weder Kanal-Zeile noch Tagesebene etwas; ein Gerät ohne Kanal-
    Zeile (2) bleibt im Kanal-Schritt stehen und bekommt die Tagesmenge."""
    a, b = _inv(1), _inv(2)
    out = await waerme([a, b], [_kennzahl(a, 10.0, 20.0), _kennzahl(b)],
                       kanal_wp_zeilen={1: {"stromverbrauch_kwh": 100.0}},
                       _tages_wp_mengen={"1": _tagesmengen(50.0, 100.0), "2": _tagesmengen(7.0, 21.0)})
    assert [(k.mengen.strom_kwh, k.mengen.waerme_kwh) for k in out["_wp_kennzahlen_je_geraet"]] == [
        (10.0, 20.0), (7.0, 21.0)]


@pytest.mark.asyncio
async def test_s5_rueckfall_der_funktions_eingaenge(waerme):
    """WK-16i/N-503: trägt die Monatszeile eine Menge, gilt sie; sonst (kein Fakt, Fakt ohne Menge) die Geräte-Mengen."""
    a = _inv(1)
    k = [_kennzahl(a, 80.0, 240.0)]
    mit = SimpleNamespace(wp=WpFakten(strom_kwh=100.0, waerme_kwh=350.0))
    assert (await waerme([a], k, monats_fakt=mit))["_wp_funktion"] is mit.wp
    for fakt in (None, SimpleNamespace(wp=WpFakten())):
        f = (await waerme([a], k, monats_fakt=fakt))["_wp_funktion"]
        assert type(f).__name__ == "FunktionsEingaengeDerAnlage"


@pytest.mark.asyncio
@pytest.mark.parametrize("lage, verletzt, heizen, wert", [
    # SOLL §3.2b: Bauarten/Geräte ohne Wärme treffen nur die vermischte Funktion; E1b: die Zahl bleibt (Schranke)
    ({"bauarten_gemischt": True}, GRUND_BAUARTEN_GEMISCHT, GRUND_BAUARTEN_GEMISCHT, 3.5),
    ({"waerme_deckt_nicht_alle_geraete": True}, GRUND_GERAETE_OHNE_WAERME, GRUND_GERAETE_OHNE_WAERME, 3.5),
    # Anwender-Angabe trifft alles und sperrt (E1b: kein Glied der Schranke)
    ({"abgrenzung_stoerung": "fremdstrom"}, "Ein weiterer Verbraucher auf dem WP-Zähler (z. B. Heizstab)",
     "Ein weiterer Verbraucher auf dem WP-Zähler (z. B. Heizstab)", None),
    # N-441 sperrt die Anlagenzahl; je Funktion antwortet die Deckung der Geräte-Mengen (S5)
    ({"geraete_verschieden": True}, "Wärme und Strom stammen von verschiedenen Geräten",
     "Nutzenergie und Strom dieser Funktion stammen von verschiedenen Geräten", None),
])
async def test_soll_32b_abgrenzung_je_funktion_und_e1b_sperre(waerme, lage, verletzt, heizen, wert):
    a = _inv(1)
    out = await waerme([a], [_kennzahl(a, 80.0, 240.0, heizung=240.0)], monats_fakt=_fakt(**lage))
    assert out["wp_abgrenzung_verletzt"] == verletzt
    assert out["_wp_abgrenzung_je_funktion"]["heizen"] == heizen
    assert out["wp_arbeitszahl"].wert == wert
    trifft_alles = "abgrenzung_stoerung" in lage
    assert (out["_wp_abgrenzung_je_funktion"]["warmwasser"] is not None) == trifft_alles


@pytest.mark.asyncio
async def test_e1b_schranke_bei_geraet_ohne_waerme(waerme):
    """Zwei Wärmepumpen, die zweite meldet Strom ohne Wärme: die anlagenweite Zahl 350 / 150 ist eine untere Schranke
    mit dem Gerät im Hinweis (E1b), keine Sperre."""
    a, b = _inv(1), _inv(2)
    out = await waerme([a, b], [_kennzahl(a, 100.0, 350.0), _kennzahl(b, 50.0, 0.0)], wp_strom=150.0, wp_waerme=350.0)
    az = out["wp_arbeitszahl"]
    assert az.ist_schranke is True
    assert az.wert == pytest.approx(350.0 / 150.0)
    assert az.schranke_hinweis == "waermepumpe 2: Strom ohne Wärmemessung enthalten"


@pytest.mark.asyncio
async def test_n609_wp_ersparnis_ist_die_summe_der_cent_gerundeten_geraetezeilen(waerme):
    """Je Gerät 900 kWh Wärme, 366,6533 kWh Strom: 900 / 0,9 × 12 ct − 366,6533 × 30 ct = 10,004 € je Zeile ⇒ Σ der
    gerundeten Zeilen 20,00 € (die ungerundete Σ wäre 20,01 €); die Herleitung nennt jedes Gerät mit Namen."""
    a, b = _inv(1), _inv(2)
    w, s = waerme_mod._WP_WAERME_D1_SUFFIX, waerme_mod._WP_STROM_K3_SUFFIX
    resolved = {f"inv_{i}_{w}": (900.0, None) for i in (1, 2)} | {f"inv_{i}_{s}": (366.6533, None) for i in (1, 2)}
    out = await waerme([a, b], [_kennzahl(a), _kennzahl(b)], resolved=resolved)
    assert out["wp_ersparnis"] == 20.0
    zeilen = out["wp_ersparnis_berechnung_text"].split("\n")
    assert [z.split(":")[0] for z in zeilen] == ["waermepumpe 1", "waermepumpe 2"]
    einzeln = await waerme([a], [_kennzahl(a)], resolved={k: v for k, v in resolved.items() if k.startswith("inv_1_")})
    assert einzeln["wp_ersparnis"] == 10.0
    assert not einzeln["wp_ersparnis_berechnung_text"].startswith("waermepumpe 1:")


@pytest.mark.asyncio
async def test_n609_ohne_mengen_keine_ersparnis(waerme):
    out = await waerme([_inv(1)], [_kennzahl(_inv(1))])
    assert out["wp_ersparnis"] is None and out["wp_ersparnis_berechnung_text"] is None


# ── RF-68 `geraete_sicht` ─────────────────────────────────────────────────────────────────────────────────────────

_GRUND = SimpleNamespace(grund=None)


def _sicht(**kw):
    args = dict(_wp_kennzahlen_je_geraet=[], get_val=lambda k: None, emob_entscheid=None, investitionen=[],
                mf_bkw=None, mf_emob=None, mf_sonstiges=None, netzbezug_preis_effektiv_cent=30.0,
                speicher_eff_ladepreis=None, speicher_imd_ladepreis=None, speicher_ladung_netz=None,
                wp_arbeitszahl=_GRUND, wp_az_funktion=SimpleNamespace(heizen=_GRUND, warmwasser=_GRUND),
                wp_az_kuehlen=_GRUND)
    args.update(kw)
    out = geraete_sicht(**args)
    assert len(out) == 15
    return out


def _emob(netz=0.0, extern=0.0, v2h=0.0):
    return SimpleNamespace(ladung_netz_kwh=netz, extern_kwh=extern, v2h_entladung_kwh=v2h)


def test_c1d_emob_split_aus_dem_monats_fakt():
    out = _sicht(get_val=lambda k: 40.0 if k == "emob_pv_ladung_kwh" else None, mf_emob=_emob(12.345, 7.0, 3.0))
    assert (out["emob_pv"], out["emob_ladung_netz"], out["emob_ladung_extern"], out["emob_v2h"]) == (40.0, 12.35, 7.0, 3.0)
    leer = _sicht(mf_emob=_emob())
    assert (leer["emob_ladung_netz"], leer["emob_ladung_extern"], leer["emob_v2h"]) == (None, None, None)


def test_n555_entscheid_der_route_schliesst_die_trias():
    """Hat die Route den Monat selbst entschieden, kommen PV/Netz/Extern geschlossen aus ihrem Pool (#262) — auch gegen
    einen Netz-Anteil im Fakt; V2H bleibt der des Fakts."""
    pool = SimpleNamespace(pv_kwh=20.004, netz_kwh=0.0, extern_kwh=5.555)
    out = _sicht(get_val=lambda k: 40.0, mf_emob=_emob(12.0, 7.0, 3.0), emob_entscheid=SimpleNamespace(pool=pool))
    assert (out["emob_pv"], out["emob_ladung_netz"], out["emob_ladung_extern"], out["emob_v2h"]) == (20.0, None, 5.55, 3.0)
    ohne_extern = _sicht(mf_emob=_emob(12.0, 7.0), emob_entscheid=SimpleNamespace(pool=SimpleNamespace(
        pv_kwh=0.0, netz_kwh=9.0, extern_kwh=0.0)))
    assert (ohne_extern["emob_pv"], ohne_extern["emob_ladung_netz"], ohne_extern["emob_ladung_extern"]) == (None, 9.0, 7.0)


def test_bkw_eigenverbrauch_nur_ueber_null():
    assert _sicht(mf_bkw=SimpleNamespace(eigenverbrauch_gemessen_kwh=1.234))["bkw_eigenverbrauch"] == 1.23
    assert _sicht(mf_bkw=SimpleNamespace(eigenverbrauch_gemessen_kwh=0.0))["bkw_eigenverbrauch"] is None


def _sg(**w):
    d = dict(erzeugung_kwh=0.0, eigenverbrauch_kwh=0.0, einspeisung_kwh=0.0, verbrauch_kwh=0.0, bezug_pv_kwh=0.0,
             bezug_netz_kwh=0.0, abgabe_kwh=0.0, einspeise_erloes_euro=0.0)
    d.update(w)
    return SimpleNamespace(**d)


def test_sonstiges_summen_und_geraete_je_richtung():
    """Summen nur über 0; je Gerät die Richtung (N-250), ein Gerät ohne Menge seiner Richtung bleibt aus der Liste."""
    invs = [_inv(1, "sonstiges", parameter={"kategorie": "erzeuger"}), _inv(2, "sonstiges", parameter={"kategorie": "verbraucher"}),
            _inv(3, "sonstiges", parameter={"kategorie": "abgabe"}), _inv(4, "sonstiges", parameter={"kategorie": "erzeuger"}),
            _inv(5, "sonstiges", parameter={"kategorie": "verbraucher"}), _inv(6, "sonstiges", parameter={"kategorie": "abgabe"}),
            _inv(7, "sonstiges"), _inv(8, "e-auto"), _inv(9, "sonstiges")]
    je = {1: _sg(erzeugung_kwh=10.0, eigenverbrauch_kwh=6.0, einspeisung_kwh=4.0), 2: _sg(verbrauch_kwh=5.0, bezug_pv_kwh=2.0),
          3: _sg(abgabe_kwh=3.0, einspeise_erloes_euro=0.6), 4: _sg(), 5: _sg(), 6: _sg(), 7: _sg(bezug_netz_kwh=1.0)}
    mf = SimpleNamespace(erzeugung_kwh=10.0, eigenverbrauch_kwh=6.0, einspeisung_kwh=4.0, verbrauch_kwh=6.0,
                         bezug_pv_kwh=2.0, bezug_netz_kwh=1.0, je_geraet=je)
    out = _sicht(investitionen=invs, mf_sonstiges=mf)
    assert [out[k] for k in ("sonstiges_erzeugung", "sonstiges_eigenverbrauch", "sonstiges_einspeisung",
                             "sonstiges_verbrauch", "sonstiges_bezug_pv", "sonstiges_bezug_netz")] == [10.0, 6.0, 4.0, 6.0, 2.0, 1.0]
    assert [(g.bezeichnung, g.kategorie) for g in out["sonstiges_geraete"]] == [
        ("sonstiges 1", "erzeuger"), ("sonstiges 2", "verbraucher"), ("sonstiges 3", "abgabe"), ("sonstiges 7", "verbraucher")]
    assert out["sonstiges_geraete"][1].bezug_netz_kwh is None and out["sonstiges_geraete"][2].erloes_euro == 0.6
    leer = _sicht(investitionen=invs, mf_sonstiges=None)
    assert leer["sonstiges_geraete"] == [] and leer["sonstiges_erzeugung"] is None


@pytest.mark.parametrize("eff, imd, netz, preis, quelle", [
    (20.0, 25.0, 30.0, 20.0, "tep"),        # R15-1: TEP-effektiv vor IMD-Ø vor Bezugspreis
    (None, 25.0, 30.0, 25.0, "imd"),
    (None, None, 30.0, 30.0, "bezugspreis"),
])
def test_r15_1_preis_kette_der_netzladung(eff, imd, netz, preis, quelle):
    out = _sicht(speicher_ladung_netz=10.0, speicher_eff_ladepreis=eff, speicher_imd_ladepreis=imd,
                 netzbezug_preis_effektiv_cent=netz)
    assert (out["netzladung_kosten"].preis_cent, out["netzladung_kosten"].quelle) == (preis, quelle)
    assert out["netzladung_kosten"].kosten_euro == pytest.approx(10.0 * preis / 100)
    assert _sicht(speicher_ladung_netz=None)["netzladung_kosten"] is None


# ── RF-69 `_geraete_aus_kanaelen` ─────────────────────────────────────────────────────────────────────────────────

def _gruppe(kanal=False, zeilen=None, quote=None):
    return SimpleNamespace(kanal=kanal, zeilen=zeilen or {}, quote=quote)


@pytest.fixture
def kanal(monkeypatch):
    """`_geraete_aus_kanaelen` für Juli 2026 mit gestelltem `geraete_kalendermonate` (an seinem Modul)."""
    import backend.services.kanal.geraete_leser as gl

    async def _lauf(invs, g, ha_stats, *, ohne_ha=None, fakt=None, bilanz_ersetzt=False, sonstige_erzeuger=None):
        async def _gk(db, anlage_id, monate):
            return {(2026, 7): g} if g is not None else {}
        monkeypatch.setattr(gl, "geraete_kalendermonate", _gk)
        return await _geraete_aus_kanaelen(None, SimpleNamespace(id=1), invs, 2026, 7, ha_stats, monats_fakt=fakt,
                                           bilanz_ersetzt=bilanz_ersetzt, sonstige_erzeuger=sonstige_erzeuger,
                                           ohne_ha=ohne_ha)
    return _lauf


@pytest.mark.asyncio
@pytest.mark.parametrize("ha_stats, ohne_ha, quelle", [
    ({"netzbezug_kwh": (100.0, _HA)}, None, "ha_statistics"),
    ({"netzbezug_kwh": (100.0, _HA)}, _OHNE_HA, "ha_statistics"),   # HA-Weg geht vor (N-750: ohne_ha nur ohne HA)
    ({}, _OHNE_HA, "tagesebene"),
])
async def test_n750_quelle_je_gruppe_mit_und_ohne_ha(kanal, ha_stats, ohne_ha, quelle):
    g = SimpleNamespace(emob=_gruppe(True, {5: {"ladung_kwh": 30.0}}, 0.4), sonstiges=_gruppe())
    out, emob, sonstiges, zeilen = await kanal([_inv(5, "e-auto")], g, ha_stats, ohne_ha=ohne_ha)
    assert out["inv_5_ladung_kwh"] == (30.0, DatenquelleInfo(quelle=quelle, konfidenz=out["inv_5_ladung_kwh"][1].konfidenz))
    assert out["inv_5_ladung_kwh"][1].quelle == quelle
    assert emob == (True, 0.4) and sonstiges is None and zeilen == {5: {"ladung_kwh": 30.0}}


@pytest.mark.asyncio
async def test_n750_ohne_ha_und_ohne_herkunft_bleiben_die_gruppen_aus(kanal):
    g = SimpleNamespace(emob=_gruppe(True, {5: {"ladung_kwh": 30.0}}, 0.4), sonstiges=_gruppe())
    assert await kanal([_inv(5, "e-auto")], g, {}) == ({}, (False, None), None, {})


@pytest.mark.asyncio
async def test_emob_kanal_negativ_faellt_raus_gemessene_null_bleibt(kanal):
    """N-585: eine gemessene 0 der E-Mob ist ein Wert; ein negatives Kanal-Δ verdrängt einen HA-Wert desselben Felds."""
    g = SimpleNamespace(emob=_gruppe(True, {5: {"ladung_kwh": 0.0, "ladung_pv_kwh": -2.0}}, None), sonstiges=_gruppe())
    out, *_ = await kanal([_inv(5, "e-auto")], g, {"inv_5_ladung_pv_kwh": (9.0, _HA), "netzbezug_kwh": (1.0, _HA)})
    assert out["inv_5_ladung_kwh"][0] == 0.0
    assert "inv_5_ladung_pv_kwh" not in out


# ── RF-70 `get_pv_strings` ────────────────────────────────────────────────────────────────────────────────────────

async def _anlage(db, *, strings, ist, prognose=True, module_monatswerte=None):
    """`strings` = [(name, kwp, ab, still)], `ist` = {name: {monat: kWh}} (2026, gemessen je Modul)."""
    a = Anlage(anlagenname="Probe RF-70", leistung_kwp=sum(s[1] for s in strings) or 1.0)
    db.add(a)
    await db.flush()
    ids = {}
    for name, kwp, ab, still in strings:
        inv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung=name, leistung_kwp=kwp,
                          anschaffungsdatum=ab, stilllegungsdatum=still)
        db.add(inv)
        await db.flush()
        ids[name] = inv.id
    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=m, einspeisung_kwh=100.0, netzbezug_kwh=100.0))
    for name, je in ist.items():
        for m, kwh in je.items():
            db.add(InvestitionMonatsdaten(investition_id=ids[name], jahr=2026, monat=m,
                                          verbrauch_daten={"pv_erzeugung_kwh": kwh}))
    if prognose:
        db.add(PVGISPrognose(
            anlage_id=a.id, abgerufen_am=datetime(2026, 1, 1), latitude=48.0, longitude=11.0, neigung_grad=30.0,
            ausrichtung_grad=0.0, jahresertrag_kwh=12000.0, spezifischer_ertrag_kwh_kwp=1200.0, gesamt_leistung_kwp=10.0,
            monatswerte=[{"monat": m, "e_m": 1000.0} for m in range(1, 13)],
            module_monatswerte={str(ids[n]): w for n, w in (module_monatswerte or {}).items()},
        ))
    await db.commit()
    return a.id


_AB = date(2024, 1, 1)


def _str(resp, name):
    return next(s for s in resp.strings if s.bezeichnung == name)


@pytest.mark.asyncio
async def test_soll_nur_in_monaten_mit_ist(db):
    """SOLL je Monat = Prognose × kWp-Anteil — nur in Monaten mit IST; die übrigen tragen 0 und gehen nicht ins Jahr."""
    aid = await _anlage(db, strings=[("Süd", 6.0, _AB, None), ("Ost", 4.0, _AB, None)],
                        ist={"Süd": {5: 700.0, 6: 650.0}, "Ost": {5: 380.0}})
    r = await get_pv_strings(anlage_id=aid, jahr=2026, db=db)
    sued, ost = _str(r, "Süd"), _str(r, "Ost")
    assert [w.prognose_kwh for w in sued.monatswerte] == [0, 0, 0, 0, 600.0, 600.0, 0, 0, 0, 0, 0, 0]
    assert [w.prognose_kwh for w in ost.monatswerte][4:6] == [400.0, 0.0]
    assert (sued.prognose_jahr_kwh, ost.prognose_jahr_kwh, r.prognose_gesamt_kwh) == (1200.0, 400.0, 1600.0)
    assert sued.monatswerte[0].performance_ratio is None and sued.monatswerte[4].performance_ratio == pytest.approx(1.167)


@pytest.mark.asyncio
async def test_f34_soll_im_anschaffungsmonat_gekuerzt(db):
    """Ost seit 16.05.2026: im Mai trägt sein SOLL 16 von 31 Tagen (400 × 16/31 = 206,5)."""
    aid = await _anlage(db, strings=[("Süd", 6.0, _AB, None), ("Ost", 4.0, date(2026, 5, 16), None)],
                        ist={"Süd": {5: 700.0}, "Ost": {5: 200.0, 6: 400.0}})
    r = await get_pv_strings(anlage_id=aid, jahr=2026, db=db)
    assert [w.prognose_kwh for w in _str(r, "Ost").monatswerte][4:6] == [206.5, 400.0]
    assert _str(r, "Süd").monatswerte[4].prognose_kwh == 600.0


@pytest.mark.asyncio
async def test_prognose_je_modul_geht_vor_dem_kwp_anteil(db):
    aid = await _anlage(db, strings=[("Süd", 6.0, _AB, None), ("Ost", 4.0, _AB, None)],
                        ist={"Süd": {5: 700.0}, "Ost": {5: 380.0}},
                        module_monatswerte={"Süd": [{"monat": 5, "e_m": 777.0}]})
    r = await get_pv_strings(anlage_id=aid, jahr=2026, db=db)
    assert (_str(r, "Süd").monatswerte[4].prognose_kwh, _str(r, "Ost").monatswerte[4].prognose_kwh) == (777.0, 400.0)


@pytest.mark.asyncio
async def test_ranking_ab_zwei_gemessenen_strings(db):
    aid = await _anlage(db, strings=[("Süd", 6.0, _AB, None), ("Ost", 4.0, _AB, None), ("West", 4.0, _AB, None)],
                        ist={"Süd": {5: 700.0}, "Ost": {5: 380.0}, "West": {5: 420.0}})
    r = await get_pv_strings(anlage_id=aid, jahr=2026, db=db)
    assert (r.bester_string, r.schlechtester_string, r.vergleich_hinweis) == ("Süd", "Ost", None)
    eins = await _anlage(db, strings=[("Solo", 6.0, _AB, None)], ist={"Solo": {5: 700.0}})
    r1 = await get_pv_strings(anlage_id=eins, jahr=2026, db=db)
    assert (r1.bester_string, r1.schlechtester_string, r1.vergleich_hinweis) == (None, None, None)


@pytest.mark.asyncio
async def test_ranking_ohne_prognose_bleibt_leer(db):
    """Gemessen, aber ohne Prognose: keine Performance-Ratio, also keine Platzierung und kein Hinweis."""
    aid = await _anlage(db, strings=[("Süd", 6.0, _AB, None), ("Ost", 4.0, _AB, None)],
                        ist={"Süd": {5: 700.0}, "Ost": {5: 380.0}}, prognose=False)
    r = await get_pv_strings(anlage_id=aid, jahr=2026, db=db)
    assert (r.hat_prognose, r.bester_string, r.schlechtester_string, r.vergleich_hinweis) == (False, None, None, None)
    assert r.prognose_gesamt_kwh == 0 and r.abweichung_gesamt_prozent is None


@pytest.mark.asyncio
async def test_stillgelegter_string_bleibt_zeile_traegt_kein_soll_nach_der_stilllegung(db):
    """#123: kein aktiv-Filter — Ost (still seit 31.05.2026) bleibt eine Zeile mit seinen Monaten bis Mai; danach kein IST,
    also kein SOLL. N-661: der SOLL-Nenner ist die Prognose-kWp (10), nicht die Σ der Träger (14)."""
    aid = await _anlage(db, strings=[("Süd", 6.0, _AB, None), ("Ost", 4.0, _AB, date(2026, 5, 31)), ("West", 4.0, _AB, None)],
                        ist={"Süd": {5: 700.0, 6: 650.0}, "Ost": {5: 380.0}, "West": {6: 300.0}})
    r = await get_pv_strings(anlage_id=aid, jahr=2026, db=db)
    assert [s.bezeichnung for s in r.strings] == ["Süd", "Ost", "West"]
    assert [w.prognose_kwh for w in _str(r, "Ost").monatswerte][4:6] == [400.0, 0.0]
    assert _str(r, "Süd").monatswerte[5].prognose_kwh == 600.0


@pytest.mark.asyncio
async def test_ohne_erzeuger_leere_antwort(db):
    a = Anlage(anlagenname="Leer", leistung_kwp=3.0)
    db.add(a)
    await db.commit()
    r = await get_pv_strings(anlage_id=a.id, jahr=2026, db=db)
    assert (r.strings, r.hat_prognose, r.anlagen_leistung_kwp, r.prognose_gesamt_kwh) == ([], False, 3.0, 0)
    assert (r.bester_string, r.ist_quelle, r.vergleich_hinweis) == (None, "fehlt", None)
    # Auch mit aktiver Prognose: ohne Erzeuger keine Prognose-Seite (frühe Antwort, `hat_prognose` False, keine Warnung)
    db.add(PVGISPrognose(
        anlage_id=a.id, abgerufen_am=datetime(2026, 1, 1), latitude=48.0, longitude=11.0, neigung_grad=30.0,
        ausrichtung_grad=0.0, jahresertrag_kwh=12000.0, spezifischer_ertrag_kwh_kwp=1200.0, gesamt_leistung_kwp=10.0,
        monatswerte=[{"monat": m, "e_m": 1000.0} for m in range(1, 13)],
    ))
    await db.commit()
    mit = await get_pv_strings(anlage_id=a.id, jahr=2026, db=db)
    assert (mit.strings, mit.hat_prognose, mit.prognose_warnung) == ([], False, None)


# ── RF-67 Nachrüstung nach der Gegenprobe: Grundgesamtheit und Kühlanteil der Gerätezeilen ────────────────────────

def _resolved_je_geraet(*ids):
    w, s = waerme_mod._WP_WAERME_D1_SUFFIX, waerme_mod._WP_STROM_K3_SUFFIX
    return {f"inv_{i}_{w}": (900.0, None) for i in ids} | {f"inv_{i}_{s}": (366.6533, None) for i in ids}


@pytest.mark.asyncio
async def test_n609_nur_im_monat_aktive_waermepumpen_tragen_eine_zeile(waerme):
    """Eine seit 2025 stillgelegte zweite Wärmepumpe mit Mengen in der Kaskade trägt im Juli 2026 keine Zeile."""
    a, b = _inv(1), _inv(2, stilllegungsdatum=date(2025, 12, 31))
    out = await waerme([a, b], [_kennzahl(a), _kennzahl(b)], resolved=_resolved_je_geraet(1, 2))
    assert out["wp_ersparnis"] == 10.0
    assert "\n" not in out["wp_ersparnis_berechnung_text"]


@pytest.mark.asyncio
async def test_e_b_kuehlanteil_je_geraet_aus_kanal_tagesebene_oder_anlage(waerme):
    """E-B (#263 K-2): Kühlen ersetzt keine Heizung — 900 / 0,9 × 12 ct − (366,6533 − Kühlstrom) × 30 ct. Der Kühlstrom
    kommt aus der Kanal-Zeile des Geräts (E4d, 70 kWh ⇒ 31,00 €), sonst aus seinen Tagesmengen (50 ⇒ 25,00 €), sonst bei
    genau EINER Wärmepumpe aus der Anlage (`wp_modus_kuehlen_kwh`, 100 ⇒ 40,00 €)."""
    a = _inv(1)
    kanal = await waerme([a], [_kennzahl(a)], resolved=_resolved_je_geraet(1), kanal_wp_zeilen={1: {"stromverbrauch_kwh": 1.0}},
                         monats_fakt=_fakt(je_geraet={1: SimpleNamespace(strom_kuehlen_kwh=70.0)}))
    assert kanal["wp_ersparnis"] == 31.0
    tage = _tagesmengen(0.0, 0.0)
    tage.modus_strom_kuehlen_kwh = 50.0
    assert (await waerme([a], [_kennzahl(a)], resolved=_resolved_je_geraet(1),
                         _tages_wp_mengen={"1": tage}))["wp_ersparnis"] == 25.0
    anlage = await waerme([a], [_kennzahl(a)], resolved=_resolved_je_geraet(1),
                          get_val=lambda k: 100.0 if k == "wp_modus_kuehlen_kwh" else None)
    assert anlage["wp_ersparnis"] == 40.0
    b = _inv(2)
    zwei = await waerme([a, b], [_kennzahl(a), _kennzahl(b)], resolved=_resolved_je_geraet(1, 2),
                        get_val=lambda k: 100.0 if k == "wp_modus_kuehlen_kwh" else None)
    assert zwei["wp_ersparnis"] == 20.0      # zwei Wärmepumpen: der anlagenweite Kühlanteil gehört keiner


# ── RF-69 Nachrüstung nach der Gegenprobe: die Zeilen-Tore der Gruppen und die Erzeuger aus der Bilanz-Gruppe ─────
# (`cockpit-monat` S69/S70 sind am HEAD wie nach dem Schnitt still. Ursache offen: die GM-Bögen zeigen, dass die K-Fälle die
# Tore betreten — der geänderte Wert erreicht die Antwort dort nicht (Nachmessung 5.11.2026). Diese Proben decken die Regeln.)

def _kanal_fakt(typen=(), emob_ladedaten=None):
    return SimpleNamespace(meta=SimpleNamespace(typen_mit_zeile=list(typen)),
                           emob=SimpleNamespace(ladedaten_je_inv=emob_ladedaten or {}, dienstlich_ladedaten_je_inv={}))


@pytest.mark.asyncio
async def test_e4c_gruppen_nur_ohne_zeile_des_monats(kanal):
    """P8: gespeichert schlägt gerechnet — trägt der Monat eine E-Mob- bzw. Sonstiges-Zeile, bleibt die Gruppe aus."""
    invs = [_inv(5, "e-auto"), _inv(7, "sonstiges", parameter={"kategorie": "verbraucher"})]
    g = SimpleNamespace(emob=_gruppe(True, {5: {"ladung_kwh": 30.0}}, 0.4),
                        sonstiges=_gruppe(True, {7: {"verbrauch_sonstig_kwh": 5.0}}))
    ha = {"netzbezug_kwh": (100.0, _HA)}
    out, emob, sonstiges, zeilen = await kanal(invs, g, ha, fakt=_kanal_fakt())
    assert emob == (True, 0.4) and "inv_5_ladung_kwh" in out and sonstiges is not None
    out, emob, sonstiges, zeilen = await kanal(invs, g, ha, fakt=_kanal_fakt(
        typen=("sonstiges",), emob_ladedaten={5: {"ladung_kwh": 1.0}}))
    assert (emob, sonstiges, zeilen) == ((False, None), None, {})
    assert out == ha


@pytest.mark.asyncio
async def test_e4c_sonstige_erzeuger_aus_der_bilanz_gruppe_oder_der_fuenften_quelle(kanal):
    """Erzeuger nur aus den Bilanz-Feldern, die für ihre Kategorie Erzeugung sind (`_categorize_counter`), wenn die
    Bilanz-Gruppe aus den Kanälen kam; sonst aus `sonstige_erzeuger` (Weg 2). Die Summe über 0 steht danach in `out`."""
    invs = [_inv(7, "sonstiges", parameter={"kategorie": "erzeuger"}), _inv(8, "sonstiges", parameter={"kategorie": "verbraucher"})]
    g = SimpleNamespace(emob=_gruppe(), sonstiges=_gruppe())
    ha = {"inv_7_erzeugung_kwh": (12.0, _HA), "inv_8_verbrauch_kwh": (4.0, _HA)}
    out, _, sonstiges, _ = await kanal(invs, g, ha, bilanz_ersetzt=True)
    assert sonstiges.erzeugung_kwh == 12.0 and out["sonstiges_erzeugung_kwh"] == (12.0, _HA)
    out, _, sonstiges, _ = await kanal(invs, g, {}, ohne_ha=_OHNE_HA, sonstige_erzeuger={"7": 9.0})
    assert sonstiges.erzeugung_kwh == 9.0 and out["sonstiges_erzeugung_kwh"] == (9.0, _OHNE_HA)
    _, _, ohne, _ = await kanal(invs, g, ha, bilanz_ersetzt=False)
    assert ohne is None


# ── RF-70 Nachrüstung nach der Gegenprobe: der SOLL-Nenner je Monat (N-613) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_n613_soll_nenner_je_monat_ohne_prognose_kwp(db):
    """Prognose ohne gespeicherte kWp: der Nenner ist je Monat die Menge, die in diesem Monat trägt. Bis Juni trägt das
    Balkonkraftwerk (0,8 kWp) selbst — Nenner Süd 6 + 0,8; ab Juli trägt sein Modul-Kind (0,4 kWp) — Nenner 6 + 0,4."""
    a = Anlage(anlagenname="Probe RF-70 N-613", leistung_kwp=6.8)
    db.add(a)
    await db.flush()
    sued = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Süd", leistung_kwp=6.0, anschaffungsdatum=_AB)
    bkw = Investition(anlage_id=a.id, typ="balkonkraftwerk", bezeichnung="BKW", leistung_kwp=0.8, anschaffungsdatum=_AB)
    db.add_all([sued, bkw])
    await db.flush()
    kind = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Kind", leistung_kwp=0.4,
                       anschaffungsdatum=date(2026, 7, 1), parent_investition_id=bkw.id)
    db.add(kind)
    await db.flush()
    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=m, einspeisung_kwh=100.0, netzbezug_kwh=100.0))
    for inv, m, kwh in ((sued, 5, 700.0), (sued, 8, 700.0), (bkw, 5, 60.0), (kind, 8, 40.0)):
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=2026, monat=m, verbrauch_daten={"pv_erzeugung_kwh": kwh}))
    db.add(PVGISPrognose(
        anlage_id=a.id, abgerufen_am=datetime(2026, 1, 1), latitude=48.0, longitude=11.0, neigung_grad=30.0,
        ausrichtung_grad=0.0, jahresertrag_kwh=12000.0, spezifischer_ertrag_kwh_kwp=1200.0, gesamt_leistung_kwp=None,
        monatswerte=[{"monat": m, "e_m": 1000.0} for m in range(1, 13)],
    ))
    await db.commit()
    r = await get_pv_strings(anlage_id=a.id, jahr=2026, db=db)
    s = _str(r, "Süd")
    assert (s.monatswerte[4].prognose_kwh, s.monatswerte[7].prognose_kwh) == (
        round(1000.0 * 6.0 / 6.8, 1), round(1000.0 * 6.0 / 6.4, 1))
