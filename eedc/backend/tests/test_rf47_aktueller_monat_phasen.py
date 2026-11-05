"""RF-47 … RF-49 — benannte Proben der Zweige, die vor dem Phasenschnitt (Bauform RF-1) weder die direkten Testdateien
noch der Golden Master `cockpit-monat` (Fixtures + drei DB-Kopien) ausführten (Bogen-Spur 5.11.2026, HEAD f1f997bbb).

Geschnitten werden drei Funktionen des Pakets `api/routes/aktueller_monat/`:

* `tkonto.py::_baue_investition_financial` (RF-47) — Kopf `_ZeilenKontext`, je Typ eine Zeilen-Phase;
* `komponenten.py::komponenten_detail` (RF-48) — Speicher-Phase (async) und WP-Phase;
* `aggregation.py::aggregiere_typen` (RF-49) — N-627-Abtretung, N-587-Anlagenzähler, Typ-Aggregation.

Die Proben rufen die Funktionen **in-process** mit gestellten `resolved`/`monats_fakt` (wie `cockpit-monat` an den
Nähten); die drei `await` der Speicher-Phase sind an ihren Modulen gestellt. Charakterisierung des Verhaltens vor dem
Schnitt: am HEAD und nach RF-49 gleich grün. `komponenten_detail` und `aggregiere_typen` hatten vorher keinen direkten
Test. Schwesterdateien: `test_aktueller_monat_financial_builder.py`, `test_n724_bkw_hub_gleich_tkonto.py`,
`test_rf34_emob_heimladung_pool_zweige.py`, `test_427_netzladung_laufender_monat.py`.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.api.routes.aktueller_monat.aggregation import aggregiere_typen
from backend.api.routes.aktueller_monat.komponenten import NETZLADUNG_HERKUNFT_TAGE, komponenten_detail
from backend.api.routes.aktueller_monat.schemas import DatenquelleInfo
from backend.api.routes.aktueller_monat.tkonto import _baue_investition_financial
from backend.models import Investition

_HA = DatenquelleInfo(quelle="ha_statistics", konfidenz=92)
_MQTT = DatenquelleInfo(quelle="mqtt_inbound", konfidenz=90)
_GESPEICHERT = DatenquelleInfo(quelle="gespeichert", konfidenz=85)
_CONNECTOR = DatenquelleInfo(quelle="local_connector", konfidenz=90)


def _inv(inv_id: int, typ: str, **kw) -> Investition:
    return Investition(
        id=inv_id, anlage_id=1, typ=typ, bezeichnung=f"{typ} {inv_id}", anschaffungsdatum=date(2024, 1, 1),
        aktiv=True, **kw,
    )


def _aggregiere(investitionen, resolved, teilzeitraum=()):
    """`aggregiere_typen` für Juli 2026; Rückgabe (direct_fields, resolved als {feld: (wert, quelle)})."""
    out = aggregiere_typen(
        investitionen=investitionen, jahr=2026, monat=7, resolved=resolved, teilzeitraum=set(teilzeitraum),
    )
    assert list(out) == ["direct_fields"]
    return out["direct_fields"], {k: (v[0], v[1].quelle) for k, v in resolved.items()}


# ── RF-49 `aggregiere_typen` ──────────────────────────────────────────────────────────────────────────────────────

def test_n627_abgetretenes_bkw_fuellt_die_kinder_luecken_und_zaehlt_nicht_doppelt():
    """Das BKW (90 kWh) mit zwei Modul-Kindern, eines gemessen (30): das andere bekommt die Lücke 90 − 30 = 60 mit der
    Marke des BKW; die PV-Achse trägt 90 (nicht 90 + 90), eine eigene BKW-Zeile gibt es nicht."""
    invs = [
        _inv(1, "balkonkraftwerk", leistung_kwp=0.8),
        _inv(2, "pv-module", leistung_kwp=0.4, parent_investition_id=1),
        _inv(3, "pv-module", leistung_kwp=0.4, parent_investition_id=1),
    ]
    _, r = _aggregiere(invs, {"inv_1_pv_erzeugung_kwh": (90.0, _HA), "inv_2_pv_erzeugung_kwh": (30.0, _MQTT)})
    assert r["inv_3_pv_erzeugung_kwh"] == (60.0, "ha_statistics")
    assert r["inv_2_pv_erzeugung_kwh"] == (30.0, "mqtt_inbound")
    assert r["pv_erzeugung_kwh"] == (90.0, "ha_statistics")
    assert "bkw_erzeugung_kwh" not in r


def test_n627_bkw_ohne_kinder_traegt_achse_und_eigene_zeile():
    _, r = _aggregiere([_inv(1, "balkonkraftwerk", leistung_kwp=0.8)], {"inv_1_pv_erzeugung_kwh": (90.0, _HA)})
    assert r["bkw_erzeugung_kwh"] == (90.0, "ha_statistics")
    assert r["pv_erzeugung_kwh"] == (90.0, "ha_statistics")


_MODULE = (lambda: [_inv(2, "pv-module", leistung_kwp=5.0), _inv(3, "pv-module", leistung_kwp=5.0)])


@pytest.mark.parametrize("modul_2, anlage, erwartet", [
    # Σ gemessene + max(0, Zähler − Σ gemessene): die Lücke füllt der Zähler, die Marke bleibt die des Zählers
    (400.0, 1000.0, (1000.0, "ha_statistics")),
    # gemessene über dem Zähler: max(0, …) = 0, nie weniger als gemessen
    (1200.0, 1000.0, (1200.0, "ha_statistics")),
])
def test_n587_anlagenzaehler_fuellt_nur_die_luecken(modul_2, anlage, erwartet):
    _, r = _aggregiere(_MODULE(), {"pv_erzeugung_kwh": (anlage, _HA), "inv_2_pv_erzeugung_kwh": (modul_2, _MQTT)})
    assert r["pv_erzeugung_kwh"] == erwartet


def test_n587_alle_quellen_gemessen_gilt_die_summe_mit_der_marke_der_letzten():
    _, r = _aggregiere(_MODULE(), {
        "pv_erzeugung_kwh": (1000.0, _HA), "inv_2_pv_erzeugung_kwh": (400.0, _MQTT), "inv_3_pv_erzeugung_kwh": (500.0, _MQTT),
    })
    assert r["pv_erzeugung_kwh"] == (900.0, "mqtt_inbound")


@pytest.mark.parametrize("anlage, invs", [
    ((1000.0, _GESPEICHERT), _MODULE),                      # «gespeichert» ist schon aufgelöst — unberührt
    ((1000.0, _HA), lambda: [_inv(4, "speicher")]),         # keine aktive PV-Quelle — der Anlagenwert bleibt
    ((None, _HA), _MODULE),                                 # ohne Zahl im Anlagenwert (`_summe` None) — bleibt
])
def test_n587_anlagenwert_bleibt_stehen(anlage, invs):
    """Das gemessene Modul (1200) liegt über dem Anlagenwert (1000): ginge der Wert durch die N-587-Auflösung, stünde
    1200 da — er bleibt aber 1000 (Gegenprobe RF-49: mit 400 ergäbe die Auflösung wieder 1000 und der Satz bliebe still)."""
    resolved = {"pv_erzeugung_kwh": anlage}
    if invs is _MODULE:
        resolved["inv_2_pv_erzeugung_kwh"] = (1200.0, _MQTT)
    _, r = _aggregiere(invs(), resolved)
    assert r["pv_erzeugung_kwh"] == (anlage[0], anlage[1].quelle)


def test_bruchstueck_regel_ersetzt_beim_ersten_beitrag_und_direktwert_sperrt():
    """#361: ein Teilzeitraum-Wert (Connector 5 kWh) wird beim ersten aggregierten Beitrag ERSETZT (100 + 50 = 150, nicht
    155); ein Direktwert außerhalb des Teilzeitraums (gespeichert 7) sperrt die Aggregation."""
    direct, r = _aggregiere([_inv(4, "speicher"), _inv(5, "speicher")], {
        "speicher_ladung_kwh": (5.0, _CONNECTOR), "inv_4_ladung_kwh": (100.0, _HA), "inv_5_ladung_kwh": (50.0, _HA),
        "speicher_entladung_kwh": (7.0, _GESPEICHERT), "inv_4_entladung_kwh": (90.0, _HA),
    }, teilzeitraum={"speicher_ladung_kwh"})
    assert r["speicher_ladung_kwh"] == (150.0, "ha_statistics")
    assert r["speicher_entladung_kwh"] == (7.0, "gespeichert")
    assert "speicher_ladung_kwh" not in direct and "speicher_entladung_kwh" in direct


def test_wp_heizwaerme_aus_der_betriebsart_n398():
    _, r = _aggregiere([_inv(9, "waermepumpe", parameter={})], {"inv_9_betriebsart_nutzenergie_heizen_kwh": (300.0, _HA)})
    assert r["wp_waerme_kwh"] == (300.0, "ha_statistics")


def test_wp_d1_nur_eine_gemessene_null_im_gesamtfeld_traegt_dessen_marke():
    _, r = _aggregiere([_inv(9, "waermepumpe", parameter={})], {"inv_9_waerme_kwh": (0.0, _MQTT)})
    assert r["wp_waerme_kwh"] == (0.0, "mqtt_inbound")


def test_wp_k3_feine_achse_ohne_kennzeichen_ist_kein_summand():
    """Ohne `getrennte_strommessung` ist die feine Achse kein Summand: K3 Stufe «fein», Menge 0 (kein Gesamtzähler);
    die Marke ist die der feinen Achse. (Der Rückfall «kein Trägerfeld der Stufe» darunter ist mit der heutigen K3-Regel
    unerreichbar — jede Stufe findet ihr Feld; gemessen 5.11.2026 über Gesamt/fein/Betriebsart × mit/ohne Kennzeichen.)"""
    _, r = _aggregiere([_inv(9, "waermepumpe", parameter={})], {"inv_9_strom_heizen_kwh": (40.0, _MQTT)})
    assert r["wp_strom_kwh"] == (0.0, "mqtt_inbound")


# ── RF-48 `komponenten_detail` ────────────────────────────────────────────────────────────────────────────────────

_WP_FUNKTION_LEER = SimpleNamespace(
    heizung_kwh=None, warmwasser_kwh=None, heizung_gemessen=False, warmwasser_gemessen=False, hat_split=False,
    strom_heizen_kwh=0.0, strom_warmwasser_kwh=0.0, waerme_ist_gesamt=False, strom_heizen_gemessen=False,
    strom_warmwasser_gemessen=False,
)


@pytest.fixture
def naehte(monkeypatch):
    """Die drei `await` der Speicher-Phase an ihren Modulen gestellt; `stelle(name, fn)` tauscht einzeln."""
    import backend.services.monats_fakten.netzladung_tage as nt
    import backend.services.speicher_wirtschaftlichkeit as sw

    async def aus_tagen(db, anlage, invs, jahr, monat, heute):
        return 3.456

    async def eta(db, **kw):
        return SimpleNamespace(quelle="soc_korrigiert", wirkungsgrad_prozent=88.88)

    async def eff(db, **kw):
        return SimpleNamespace(effektiver_ladepreis_cent=21.234, quelle="dyn-tarif")

    orte = {"aus_tagen": (nt, "speicher_netzladung_aus_tagen"), "eta": (sw, "berechne_ist_wirkungsgrad"),
            "eff": (sw, "berechne_effektiver_ladepreis")}
    for name, fn in (("aus_tagen", aus_tagen), ("eta", eta), ("eff", eff)):
        monkeypatch.setattr(*orte[name], fn)
    return lambda name, fn: monkeypatch.setattr(*orte[name], fn)


async def _detail(**kw) -> dict:
    a = dict(
        _wp_abgrenzung_je_funktion={"heizen": None, "warmwasser": None, "kuehlen": None}, _wp_funktion=_WP_FUNKTION_LEER,
        _wp_kennzahlen_je_geraet=[], anlage_id=1, db=None, fenster=SimpleNamespace(tage=5),
        investitionen=[_inv(4, "speicher", parameter={"kapazitaet_kwh": 10.0})], jahr=2026, monat=7, monats_fakt=None,
        speicher_entladung=20.0, speicher_ladung=25.0, wp_abgrenzung_verletzt=None,
        wp_arbeitszahl=SimpleNamespace(ist_schranke=True), wp_waerme_abgeleitet_kwh=0.0, anlage=None, heute=date(2026, 7, 6),
    )
    a.update(kw)
    out = await komponenten_detail(**a)
    assert len(out) == 34 and out["speicher_ersparnis"] is None
    return out


async def _kaputt(*a, **kw):
    raise RuntimeError("Probe")


async def test_427_netzladung_aus_den_tagen_mit_herkunft_eta_und_ladepreis(naehte):
    """Monat ohne Speicher-Zeile (#427 Punkt 2): Netzladung Σ der Tage (3,46) mit Herkunft «tageswerte»; η aus dem
    SoC-Pfad (88,9 %, F-22); effektiver Ladepreis mit Quelle (21,23 ct)."""
    o = await _detail()
    assert (o["speicher_ladung_netz"], o["speicher_ladung_netz_herkunft"]) == (3.46, NETZLADUNG_HERKUNFT_TAGE)
    assert (o["speicher_wirkungsgrad"], o["speicher_wirkungsgrad_quelle"], o["speicher_soc_drift_flag"]) == (
        88.9, "soc_korrigiert", False)
    assert (o["speicher_eff_ladepreis"], o["speicher_eff_ladepreis_quelle"]) == (21.23, "dyn-tarif")


async def test_427_ohne_tageswert_bleibt_die_netzladung_aus(naehte):
    async def keine(*a):
        return None
    naehte("aus_tagen", keine)
    o = await _detail()
    assert (o["speicher_ladung_netz"], o["speicher_ladung_netz_herkunft"]) == (None, None)
    assert (o["speicher_eff_ladepreis"], o["speicher_eff_ladepreis_quelle"]) == (None, None)


@pytest.mark.parametrize("tage, auslastung, basis", [(5, 40.0, 50.0), (31, 6.5, 310.0)])
async def test_vollzyklen_und_auslastung_im_laufenden_monat(naehte, tage, auslastung, basis):
    """Vollzyklen = Entladung ÷ Kapazität (20 ÷ 10 = 2,0); Auslastung = Entladung ÷ (Kapazität × abgelaufene Tage) —
    am 5. Tag 20 ÷ 50 = 40 %, über den vollen Monat 20 ÷ 310 = 6,5 %."""
    o = await _detail(fenster=SimpleNamespace(tage=tage))
    assert o["speicher_vollzyklen"] == 2.0
    assert (o["speicher_auslastung"], o["speicher_auslastungs_basis"]) == (auslastung, basis)


async def test_f22_eta_fehler_gibt_den_grund_ohne_rohen_quotienten(naehte):
    naehte("eta", _kaputt)
    o = await _detail()
    assert (o["speicher_wirkungsgrad"], o["speicher_wirkungsgrad_quelle"], o["speicher_soc_drift_flag"]) == (
        None, "nicht-ermittelbar", True)


@pytest.mark.parametrize("ladung, entladung, erwartet", [
    (10.0, 12.0, (None, "fenster-zu-kurz", True)),      # roher Quotient über 100 % — ausgeblendet, Grund bleibt
    (10.0, 8.0, (80.0, "roh-unkorrigiert", False)),     # ohne SoC-Randwerte der rohe Quotient als Aussage (P4)
])
async def test_f22_ohne_soc_der_rohe_quotient_nur_wenn_physikalisch_moeglich(naehte, ladung, entladung, erwartet):
    async def ohne_soc(db, **kw):
        return SimpleNamespace(quelle="fenster-zu-kurz", wirkungsgrad_prozent=None)
    naehte("eta", ohne_soc)
    o = await _detail(speicher_ladung=ladung, speicher_entladung=entladung)
    assert (o["speicher_wirkungsgrad"], o["speicher_wirkungsgrad_quelle"], o["speicher_soc_drift_flag"]) == erwartet


async def test_effektiver_ladepreis_fehler_laesst_beide_felder_leer(naehte):
    naehte("eff", _kaputt)
    o = await _detail()
    assert o["speicher_ladung_netz"] == 3.46
    assert (o["speicher_eff_ladepreis"], o["speicher_eff_ladepreis_quelle"]) == (None, None)


async def test_wp_arbeitszahl_je_funktion_ohne_modus_daten_nennt_den_grund(naehte):
    """Ohne Monats-Fakt und ohne getrennte Strommessung: kein Modus-Split, je Funktion keine Zahl, aber der Grund (P4)."""
    o = await _detail(investitionen=[])
    assert o["mf_wp"] is None and o["wp_modus_heizen"] is None and o["wp_modus_gemessen"] is None
    az = o["wp_az_funktion"]
    assert (az.heizen.wert, az.heizen.grund) == (None, "Strom nicht getrennt je Funktion gemessen")
    assert (az.warmwasser.wert, az.warmwasser.grund) == (None, "Strom nicht getrennt je Funktion gemessen")
    assert (o["wp_az_kuehlen"].wert, o["wp_az_kuehlen"].grund) == (None, "kein Kühlbetrieb in diesem Zeitraum")
    assert o["speicher_kapazitaet"] is None and o["speicher_vollzyklen"] is None


async def test_wp_fakten_aus_den_kanaelen_ersetzen_den_monats_fakt(naehte):
    """HA-Bauform E4d: der Monat ohne WP-Zeile reicht `wp_fakten` aus den Kanälen durch."""
    mf_wp = SimpleNamespace(hat_modus_split=False, nutzenergie_kuehlen_kwh=0.0, modus_strom_kuehlen_kwh=0.0)
    o = await _detail(wp_fakten=mf_wp, investitionen=[])
    assert o["mf_wp"] is mf_wp and o["wp_modus_heizen"] is None


# ── RF-47 `_baue_investition_financial` ───────────────────────────────────────────────────────────────────────────

def test_eauto_im_wallbox_fall_ohne_km_anteil_behaelt_das_extern_des_autos():
    """Wallbox-Fall (der Topf trägt Heimladung), das Auto fuhr 0 km: sein km-Anteil am Topf ist leer, die Zeile entsteht
    trotzdem (Heimladung > 0, N-555 Stufe 2) und zieht das Extern des Autos ab (25 €)."""
    from backend.services.eauto_wirtschaftlichkeit import compute_emob_pool_attribution

    inv = _inv(7, "e-auto", parameter={})
    attr = compute_emob_pool_attribution(
        eauto_imd_data=[{"km_gefahren": 0.0}], wallbox_imd_data=[{"ladung_kwh": 250.0, "ladung_pv_kwh": 100.0}],
    )
    kw = dict(netz_p=30.0, einsp_p=8.0, wp_p=30.0, wb_p=30.0, monats_gaspreis=None, monats_benzinpreis=1.8,
              emob_pool_attr=attr)
    mit = _baue_investition_financial(inv, {"km_gefahren": 0.0, "ladung_extern_kwh": 50.0, "ladung_extern_euro": 25.0}, **kw)
    ohne = _baue_investition_financial(inv, {"km_gefahren": 0.0}, **kw)
    assert mit is not None and ohne is not None
    assert ohne.ersparnis_euro - mit.ersparnis_euro == pytest.approx(25.0)


# ── Nachgerüstet nach der Gegenprobe: vier Sätze waren in den direkten Tests, beiden HTTP-/In-Process-GMs und 41
#    Fachdateien still (`47_bkw_abgetreten_doch_gezaehlt`, `47_emob_ev_p_wird_netzpreis`, `47_emob_max0_weg`,
#    `48_wp_kuehlen_abgrenzung_weg`) ─────────────────────────────────────────────────────────────────────────────────

_EMOB_PREISE = dict(netz_p=30.0, einsp_p=8.0, wp_p=30.0, wb_p=25.0, monats_gaspreis=None, monats_benzinpreis=1.8)


def _leerer_topf():
    from backend.services.eauto_wirtschaftlichkeit import compute_emob_pool_attribution

    return compute_emob_pool_attribution(eauto_imd_data=[], wallbox_imd_data=[])


@pytest.mark.parametrize("abgetreten, erwartet", [(False, 18.0), (True, None)])
def test_n724_abgetretenes_bkw_hat_keine_zeile(abgetreten, erwartet):
    """N-724/ADR-002/P11: ohne Monats-Fakt trägt der gemessene Eigenverbrauch einer Zeile ohne Erzeugung (60 kWh × 30 ct
    = 18 €); ist das Gerät an Modul-Kinder abgetreten, steckt er schon bei den Kindern — keine Zeile."""
    d = _baue_investition_financial(
        _inv(1, "balkonkraftwerk", leistung_kwp=0.8), {"eigenverbrauch_kwh": 60.0},
        bkw_abgetreten=abgetreten, emob_pool_attr=_leerer_topf(), **_EMOB_PREISE,
    )
    assert (d.ersparnis_euro if d is not None else None) == erwartet


@pytest.mark.parametrize("ev_p, erwartet", [(None, 108.0), (20.0, 112.0)])
def test_n672_pv_ladung_des_autos_traegt_den_ev_preis(ev_p, erwartet):
    """N-672: 1000 km × 7,5 L × 1,80 € = 135 € − Netz 60 kWh × 25 ct (Wallbox) − PV 40 kWh × EV-Preis (ohne: 30 ct ⇒ 108 €,
    mit 20 ct ⇒ 112 €)."""
    d = _baue_investition_financial(
        _inv(7, "e-auto", parameter={}), {"km_gefahren": 1000.0, "ladung_kwh": 100.0, "ladung_pv_kwh": 40.0},
        ev_p=ev_p, emob_pool_attr=_leerer_topf(), **_EMOB_PREISE,
    )
    assert d.ersparnis_euro == pytest.approx(erwartet)


def test_eauto_negative_netzladung_kostet_nichts():
    """`max(0, netz_kwh)`: eine negativ gepflegte Netzladung (−30) zählt als 0 — 135 € − PV 40 kWh × 30 ct = 123 €
    (ohne die Klemme 130,50 €)."""
    d = _baue_investition_financial(
        _inv(7, "e-auto", parameter={}),
        {"km_gefahren": 1000.0, "ladung_kwh": 100.0, "ladung_pv_kwh": 40.0, "ladung_netz_kwh": -30.0},
        emob_pool_attr=_leerer_topf(), **_EMOB_PREISE,
    )
    assert d.ersparnis_euro == pytest.approx(123.0)


async def test_w5_arbeitszahl_kuehlen_nennt_die_abgrenzung_der_kuehlfunktion(naehte):
    """W-5: Kältemenge 300 ÷ Kühlstrom 100 wäre 3,0 — verletzt die Kühlfunktion die Abgrenzung, steht ihr Grund da."""
    mf_wp = SimpleNamespace(hat_modus_split=False, nutzenergie_kuehlen_kwh=300.0, modus_strom_kuehlen_kwh=100.0)
    o = await _detail(wp_fakten=mf_wp, investitionen=[],
                      _wp_abgrenzung_je_funktion={"heizen": None, "warmwasser": None, "kuehlen": "Probe-Grund"})
    assert (o["wp_az_kuehlen"].wert, o["wp_az_kuehlen"].grund) == (None, "Probe-Grund")
    o = await _detail(wp_fakten=mf_wp, investitionen=[])
    assert o["wp_az_kuehlen"].wert == 3.0
