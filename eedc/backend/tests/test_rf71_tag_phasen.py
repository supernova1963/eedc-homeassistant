"""RF-71 … RF-72 — benannte Proben für die Phasen von ``get_tag_detail`` und ``get_tagesdetail_kwh``.

Der Schnitt (Serie „Funktion vor Datei", Bauform RF-1) ist ein reiner Umzug; diese Proben pinnen die Regeln, die
weder der Golden Master ``energie-profil`` noch die direkten Testdateien bis dahin einzeln festhielten, und sind
**am HEAD vor dem Schnitt grün** gelaufen. Sie gehen nur über die öffentlichen Funktionen (Route bzw. Leser), nie
über einen Phasennamen.

* RF-71 ``get_tag_detail``: Tages-SOLL = ``round(Prognose × Lernfaktor, 1)`` · Netzbezugspreis des Tages = Slot-Ø,
  sonst der Monatstarif (SOLL P-2) · Nenner einer Funktion aus der Faltung, sonst der Tageswert
  (``_nenner_der_funktion``) · R2/Bauart nur über Geräte mit Strom des Tages · E1b: Strom ohne Wärme ist eine
  Schranke, Wärme ohne Strom sperrt · 404 · Strom eines unbekannten Geräts ohne Kennzahl · Kühl-Deckung des Tages
  ersetzt die Faltung · Kühlzahl je Gerät aus dem Kühlstrom des Beitrags · gemessene Null ohne Betriebsart-Grund ·
  Störung nur von Geräten mit Strom · Monats-Lage «Geräte ohne Wärme» je Funktion.
* RF-72 ``get_tagesdetail_kwh``: Fenster je Typ (N-435/N-444, Kanal-Tag = Kalendertag) · Gerätefeld ODER Σ
  Innengeräte, nie addiert · E-Auto mit Wallbox-Parent oder deckender Wallbox übersprungen, eine stillgelegte Wallbox
  deckt nichts (N-555) · der aussagekräftigste Grund gewinnt (W-18).

Mehrere Proben kamen aus der Gegenprobe (ein Sprengsatz blieb zuerst still): Kühl-Deckung, Kühlzahl je Gerät,
gemessene Null, Störung, Monats-Lage, stillgelegte Wallbox.

Schwesterdateien: ``test_n444_tagesdetail_ein_fenster.py``, ``test_n435_tages_jaz_ein_fenster.py`` (Fenster),
``test_bs6_kaelte_je_tag.py`` (Kälte je Innengerät), ``test_wk16j_tag_deckung.py`` (Deckung je Funktion),
``test_n441_geraete_identitaet.py`` (Gegenrichtung), ``test_rf56_kanal_leser_phasen.py`` (Muster).
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_BAUARTEN_GEMISCHT,
    GRUND_GERAETE_VERSCHIEDEN,
)
from backend.core.tageswert_grund import GRUND_KEINE_ZAEHLERSTAENDE, GRUND_NICHT_ZUGEORDNET
from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung  # noqa: F401
from backend.services.snapshot.aggregator import get_tagesdetail_kwh
from backend.tests import factories

TAG = date(2026, 9, 10)
_T0 = datetime.combine(TAG, datetime.min.time())
_LW = {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz"}
_LL = {"wp_art": "luft_luft", "effizienz_modus": "gesamt_jaz"}
_LW_F5 = {**_LW, "getrennte_strommessung": True}


async def _anlage_mit_wps(db, geraete, *, pv_prognose=None):
    """Anlage mit Wärmepumpen und EINEM Tag: ``geraete`` = ``[(parameter, felder)]``; ``stromverbrauch_kwh`` geht
    als Zählerstrom in ``komponenten_kwh``, jedes andere Feld als Randstandspaar [00:00, 24:00)."""
    anlage = await factories.anlage(db, anlagenname="RF-71")
    mapping, invs = {}, []
    for n, (parameter, felder) in enumerate(geraete):
        inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung=f"WP {n}",
                          anschaffungsdatum=date(2024, 1, 1), parameter=parameter)
        db.add(inv)
        await db.flush()
        invs.append(inv)
        mapping[str(inv.id)] = {"felder": {
            f: {"strategie": "sensor", "sensor_id": f"sensor.{inv.id}_{f}"} for f in felder if f != "stromverbrauch_kwh"}}
        for f, zuwachs in felder.items():
            if f == "stromverbrauch_kwh":
                continue
            for versatz, wert in ((0, 100.0), (24, 100.0 + zuwachs)):
                db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=f"inv:{inv.id}:{f}",
                                      zeitpunkt=_T0 + timedelta(hours=versatz), wert_kwh=wert, quelle="ha_statistics"))
    anlage.sensor_mapping = {"investitionen": mapping}
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=TAG, pv_prognose_kwh=pv_prognose,
        komponenten_kwh={f"waermepumpe_{i.id}": f["stromverbrauch_kwh"]
                         for i, (_, f) in zip(invs, geraete) if f.get("stromverbrauch_kwh")}))
    await db.commit()
    return anlage, invs


async def _tag(db, anlage_id):
    from backend.api.routes.energie_profil.views import get_tag_detail
    return await get_tag_detail(anlage_id=anlage_id, datum=TAG, db=db)


# ── RF-71 ────────────────────────────────────────────────────────────────────


async def test_rf71_tages_soll_ist_prognose_mal_lernfaktor(db, monkeypatch):
    """Tages-SOLL = ``round(pv_prognose × Lernfaktor(openmeteo), 1)``; ohne Lernfaktor die Prognose selbst."""
    from backend.api.routes import live_wetter

    anlage, _ = await _anlage_mit_wps(db, [], pv_prognose=10.0)
    gefragt = []

    async def _lern(anlage_id, _db, quelle=None):
        gefragt.append(quelle)
        return 1.234

    monkeypatch.setattr(live_wetter, "_get_lernfaktor", _lern)
    assert (await _tag(db, anlage.id)).soll_pv_kwh == 12.3
    assert gefragt == ["openmeteo"]

    async def _kein(anlage_id, _db, quelle=None):
        return None

    monkeypatch.setattr(live_wetter, "_get_lernfaktor", _kein)
    assert (await _tag(db, anlage.id)).soll_pv_kwh == 10.0


async def test_rf71_tagespreis_slot_mittel_vor_monatstarif(db, monkeypatch):
    """SOLL P-2: der Netzbezugspreis des Tages ist der Slot-Ø, wo es ihn gibt — sonst der Arbeitspreis des Monats;
    die Herkunft kommt aus dem Slot-Tag (ohne Slot-Tag ``None``)."""
    from backend.services import finanz_zeilen, strompreis_aggregator

    anlage, _ = await _anlage_mit_wps(db, [])

    async def _tarif(*a, **k):
        return SimpleNamespace(netzbezug_preis_cent=28.0, einspeiseverguetung_cent=8.1)

    monkeypatch.setattr(finanz_zeilen, "baue_finanz_zeile", _tarif)
    for slot, preis, herkunft in (
        ({TAG: SimpleNamespace(mittel_cent=33.3, herkunft="slots")}, 33.3, "slots"),
        ({TAG: SimpleNamespace(mittel_cent=None, herkunft="slots")}, 28.0, "slots"),
        ({}, 28.0, None),
    ):
        async def _slots(*a, _s=slot, **k):
            return _s

        monkeypatch.setattr(strompreis_aggregator, "lade_slot_kosten_je_tag", _slots)
        t = await _tag(db, anlage.id)
        assert (t.netzbezug_preis_cent, t.netzbezug_preis_herkunft, t.einspeise_preis_cent) == (preis, herkunft, 8.1)


async def test_rf71_nenner_aus_faltung_sonst_tageswert(db, monkeypatch):
    """Nenner einer Funktion = die Faltung, wo sie etwas trägt (> 0), sonst der Tageswert samt seiner ``None``-heit."""
    from backend.services import waerme_klima_block

    anlage, _ = await _anlage_mit_wps(db, [(_LW_F5, {
        "stromverbrauch_kwh": 4.0, "heizenergie_kwh": 10.0, "warmwasser_kwh": 4.5,
        "strom_heizen_kwh": 2.5, "strom_warmwasser_kwh": 1.5})])
    echt = waerme_klima_block.funktions_eingaenge_der_anlage
    t = await _tag(db, anlage.id)
    assert (t.wp_strom_heizen_kwh, t.wp_strom_warmwasser_kwh) == (2.5, 1.5)   # Faltung = Tageswert

    def _faltung(kennzahlen):
        return dataclasses.replace(echt(kennzahlen), strom_heizen_kwh=0.0, strom_warmwasser_kwh=5.0)

    monkeypatch.setattr(waerme_klima_block, "funktions_eingaenge_der_anlage", _faltung)
    t = await _tag(db, anlage.id)
    assert (t.wp_strom_heizen_kwh, t.wp_strom_warmwasser_kwh) == (2.5, 5.0)


async def test_rf71_bauarten_gemischt_nur_mit_strom_des_tages(db):
    """R2/Bauart (SOLL §5): Luft-Wasser **und** Luft-Luft mit Strom am Tag sperren je Funktion mit
    ``GRUND_BAUARTEN_GEMISCHT``; eine Luft-Luft ohne Strom des Tages zählt nicht."""
    gemischt, _ = await _anlage_mit_wps(db, [
        (_LW_F5, {"stromverbrauch_kwh": 4.0, "heizenergie_kwh": 12.0, "strom_heizen_kwh": 3.0}),
        (_LL, {"stromverbrauch_kwh": 2.0}),
    ])
    t = await _tag(db, gemischt.id)
    assert t.wp_jaz_heizen_grund == GRUND_BAUARTEN_GEMISCHT   # Warmwasser: der Layer nennt zuerst die Strommessung

    allein, _ = await _anlage_mit_wps(db, [
        (_LW_F5, {"stromverbrauch_kwh": 4.0, "heizenergie_kwh": 12.0, "strom_heizen_kwh": 3.0}),
        (_LL, {"heizenergie_kwh": 0.0}),
    ])
    t = await _tag(db, allein.id)
    assert t.wp_jaz_heizen_grund is None and t.wp_jaz_heizen == 4.0


async def test_rf71_e1b_schranke_und_gegenrichtung(db):
    """E1b: ein Gerät mit Strom und ohne Wärme macht die Tageszahl zur unteren Schranke; ein Gerät mit Wärme und
    ohne Strom des Tages sperrt (``GRUND_GERAETE_VERSCHIEDEN``, am TAG gezählt)."""
    schranke, _ = await _anlage_mit_wps(db, [
        (_LW, {"stromverbrauch_kwh": 4.0, "heizenergie_kwh": 12.0}),
        (_LW, {"stromverbrauch_kwh": 2.0}),
    ])
    t = await _tag(db, schranke.id)
    assert t.wp_jaz_ist_schranke is True
    assert t.wp_jaz == 2.0 and t.wp_jaz_grund is None

    gesperrt, _ = await _anlage_mit_wps(db, [
        (_LW, {"stromverbrauch_kwh": 4.0, "heizenergie_kwh": 12.0}),
        (_LW, {"heizenergie_kwh": 5.0}),
    ])
    t = await _tag(db, gesperrt.id)
    assert t.wp_jaz is None
    assert t.wp_jaz_grund == GRUND_GERAETE_VERSCHIEDEN


# ── RF-72 ────────────────────────────────────────────────────────────────────


async def _anlage_mit_zaehlern(db, geraete):
    """``geraete`` = ``[(typ, kwargs, {feld: [Stände an Vortag 23:00, 00:00, 23:00, Folgetag 00:00] oder None})]`` —
    ``None`` heißt «zugeordnet, aber ohne Stände»; ein Feld, das fehlt, ist nicht zugeordnet."""
    anlage = await factories.anlage(db, anlagenname="RF-72")
    zeiten = [_T0 - timedelta(hours=1), _T0, _T0 + timedelta(hours=23), _T0 + timedelta(hours=24)]
    mapping, invs = {}, []
    for typ, kw, felder in geraete:
        inv = Investition(anlage_id=anlage.id, typ=typ, bezeichnung=typ, anschaffungsdatum=date(2024, 1, 1), **kw)
        db.add(inv)
        await db.flush()
        invs.append(inv)
        mapping[str(inv.id)] = {"felder": {
            f: {"strategie": "sensor", "sensor_id": f"sensor.{inv.id}_{f}"} for f in felder}}
        for f, staende in felder.items():
            for ts, wert in zip(zeiten, staende or ()):
                db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=f"inv:{inv.id}:{f}", zeitpunkt=ts,
                                      wert_kwh=wert, quelle="ha_statistics"))
    anlage.sensor_mapping = {"investitionen": mapping}
    await db.commit()
    invs_by_id = {str(i.id): i for i in (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all()}
    return anlage, invs, invs_by_id


async def test_rf72_fenster_je_typ(db):
    """N-435/N-444: der Speicher liest immer rückwärts [Vortag 23:00, 23:00), die Wärmepumpe bedingt
    (``tageszeile_rueckwaerts``); an einem Kanal-Tag lesen beide den Kalendertag [00:00, 24:00)."""
    anlage, _, invs = await _anlage_mit_zaehlern(db, [
        ("speicher", {}, {"ladung_netz_kwh": [100.0, 106.0, 106.0, 107.0]}),
        ("waermepumpe", {"parameter": _LW}, {"strom_heizen_kwh": [200.0, 201.0, 211.0, 214.0]}),
    ])
    w = (await get_tagesdetail_kwh(db, anlage, invs, TAG)).werte
    assert (w["speicher_ladung_netz_kwh"], w["wp_strom_heizen_kwh"]) == (6.0, 13.0)
    w = (await get_tagesdetail_kwh(db, anlage, invs, TAG, tageszeile_rueckwaerts=True)).werte
    assert (w["speicher_ladung_netz_kwh"], w["wp_strom_heizen_kwh"]) == (6.0, 11.0)
    w = (await get_tagesdetail_kwh(db, anlage, invs, TAG, tageszeile_rueckwaerts=True, kanal_tag=True)).werte
    assert (w["speicher_ladung_netz_kwh"], w["wp_strom_heizen_kwh"]) == (1.0, 13.0)


async def test_rf72_geraetefeld_oder_innengeraete_nie_addiert(db):
    """Bauschnitt 6: Gerätefeld ODER Σ der Innengerät-Kopien — mit Gerätefeld zählt nur es, ohne die Σ der Kopien."""
    k = "betriebsart_nutzenergie_kuehlen_kwh"
    anlage, (mit, ohne), invs = await _anlage_mit_zaehlern(db, [
        ("waermepumpe", {"parameter": _LL}, {
            k: [0.0, 0.0, 5.0, 5.0], f"{k}-1": [0.0, 0.0, 2.0, 2.0], f"{k}-2": [0.0, 0.0, 4.0, 4.0]}),
        ("waermepumpe", {"parameter": _LL}, {f"{k}-1": [0.0, 0.0, 1.0, 1.0], f"{k}-2": [0.0, 0.0, 3.0, 3.0]}),
    ])
    d = await get_tagesdetail_kwh(db, anlage, invs, TAG)
    assert d.werte_je_inv["wp_kaelte_kwh"] == {str(mit.id): 5.0, str(ohne.id): 4.0}
    assert d.werte["wp_kaelte_kwh"] == 9.0
    assert d.felder_je_inv["wp_kaelte_kwh"][str(mit.id)] == {k: 5.0, f"{k}-1": 2.0, f"{k}-2": 4.0}


async def test_rf72_eauto_mit_wallbox_parent_uebersprungen(db):
    """N-555: ein E-Auto mit Wallbox-Parent trägt nichts bei (die Wallbox misst die Ladung); ohne Parent zählt es."""
    anlage, (wallbox, eauto), invs = await _anlage_mit_zaehlern(db, [
        ("wallbox", {}, {}),
        ("e-auto", {}, {"ladung_pv_kwh": [0.0, 0.0, 4.0, 4.0]}),
    ])
    assert (await get_tagesdetail_kwh(db, anlage, invs, TAG)).werte["emob_ladung_pv_kwh"] == 4.0
    eauto.parent_investition_id = wallbox.id
    await db.commit()
    d = await get_tagesdetail_kwh(db, anlage, invs, TAG)
    assert "emob_ladung_pv_kwh" not in d.werte
    assert d.grund_je_feld["emob_ladung_pv_kwh"] == GRUND_NICHT_ZUGEORDNET   # nur die Wallbox wurde gefragt


async def test_rf72_aussagekraeftigster_grund_gewinnt(db):
    """W-18: liefert kein Gerät eines Keys, gewinnt «zugeordnet, aber ohne Stände» gegen «nicht zugeordnet» —
    unabhängig davon, welches Gerät zuerst gefragt wird; ein Key mit Wert trägt keinen Grund."""
    anlage, _, invs = await _anlage_mit_zaehlern(db, [
        ("wallbox", {}, {}),
        ("e-auto", {}, {"ladung_pv_kwh": None, "ladung_netz_kwh": [0.0, 0.0, 2.0, 2.0]}),
    ])
    d = await get_tagesdetail_kwh(db, anlage, invs, TAG)
    assert d.grund_je_feld["emob_ladung_pv_kwh"] == GRUND_KEINE_ZAEHLERSTAENDE
    assert "emob_ladung_netz_kwh" not in d.grund_je_feld and d.werte["emob_ladung_netz_kwh"] == 2.0

    anlage, _, invs = await _anlage_mit_zaehlern(db, [
        ("e-auto", {}, {"ladung_pv_kwh": None}),
        ("wallbox", {}, {}),
    ])
    d = await get_tagesdetail_kwh(db, anlage, invs, TAG)
    assert d.grund_je_feld["emob_ladung_pv_kwh"] == GRUND_KEINE_ZAEHLERSTAENDE


async def test_rf71_unbekannte_anlage_404(db):
    """``_tag_laden``: eine unbekannte Anlage ist 404, bevor irgendetwas gelesen wird."""
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        await _tag(db, 4711)
    assert e.value.status_code == 404


async def test_rf72_eauto_bei_deckender_wallbox_uebersprungen(db):
    """N-555 (Regel 6): trägt eine Wallbox in Betrieb einen Ladezähler, zählen die Heim-Zähler des Autos nicht
    zusätzlich — auch ohne Parent."""
    anlage, _, invs = await _anlage_mit_zaehlern(db, [
        ("wallbox", {}, {"ladung_kwh": [0.0, 0.0, 9.0, 9.0], "ladung_pv_kwh": [0.0, 0.0, 6.0, 6.0]}),
        ("e-auto", {}, {"ladung_pv_kwh": [0.0, 0.0, 4.0, 4.0]}),
    ])
    d = await get_tagesdetail_kwh(db, anlage, invs, TAG)
    assert d.werte["emob_ladung_pv_kwh"] == 6.0
    assert list(d.werte_je_inv["emob_ladung_pv_kwh"]) == [str(invs_id) for invs_id in invs if invs[invs_id].typ == "wallbox"]


async def test_rf71_strom_eines_unbekannten_geraets_ohne_kennzahl(db):
    """D-Sicht 3: trägt die Tageszeile Strom eines Geräts, das es nicht (mehr) gibt, entsteht für es keine
    Geräte-Kennzahl — die Zeilen je Gerät nennen nur bekannte Geräte; die Tagessumme behält den Strom."""
    anlage, (wp,) = await _anlage_mit_wps(db, [(_LW, {"stromverbrauch_kwh": 4.0, "heizenergie_kwh": 12.0})])
    tz = (await db.execute(select(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == anlage.id))).scalar_one()
    tz.komponenten_kwh = {**tz.komponenten_kwh, "waermepumpe_9999": 2.0}
    await db.commit()
    t = await _tag(db, anlage.id)
    assert [g.investition_id for g in t.wp_geraete] == [wp.id]
    assert t.wp_jaz_nenner_kwh == 6.0


async def test_rf71_kuehl_deckung_vom_tag_ersetzt_die_faltung(db):
    """``_funktions_deckung``: «kuehlen» beantwortet die Faltung nicht (``None``) — der Tag setzt seine eigene
    Kühl-Deckung ein. Erst damit trifft eine Block-Lage wie die gemischten Bauarten auch die Kühl-Zeile: Kälte eines
    Geräts ohne Kühlstrom im Stapel (Deckung verletzt) an einem Tag mit Luft-Wasser und Luft-Luft ⇒ der Bauart-Grund
    (``abgrenzung_je_funktion``), nicht der allgemeinere Deckungs-Satz."""
    anlage, _ = await _anlage_mit_wps(db, [
        (_LW, {"stromverbrauch_kwh": 4.0, "heizenergie_kwh": 12.0}),
        (_LL, {"stromverbrauch_kwh": 2.0, "betriebsart_strom_kuehlen_kwh": 1.5}),
        (_LL, {"stromverbrauch_kwh": 2.0, "betriebsart_nutzenergie_kuehlen_kwh": 3.0}),
    ])
    t = await _tag(db, anlage.id)
    assert t.wp_jaz_kuehlen is None
    assert t.wp_jaz_kuehlen_grund == GRUND_BAUARTEN_GEMISCHT


async def test_rf71_kuehlzahl_je_geraet_aus_dem_kuehlstrom_des_beitrags(db):
    """``_geraete_mengen`` (D-Sicht 3): die Kühl-Arbeitszahl je Gerät teilt die Kälte des Geräts durch SEINEN
    Kühlstrom aus dem Tages-Stapel (``modus_strom_kuehlen_kwh`` des Beitrags) — 4,5 ÷ 1,5 = 3,0."""
    anlage, (klima,) = await _anlage_mit_wps(db, [
        (_LL, {"stromverbrauch_kwh": 2.0, "betriebsart_strom_kuehlen_kwh": 1.5,
               "betriebsart_nutzenergie_kuehlen_kwh": 4.5}),
    ])
    t = await _tag(db, anlage.id)
    (zeile,) = [g for g in t.wp_geraete if g.investition_id == klima.id]
    assert zeile.jaz_kuehlen == 3.0
    assert t.wp_jaz_kuehlen == 3.0


async def test_rf72_stillgelegte_wallbox_nimmt_dem_auto_nichts(db):
    """N-555 (Regel 6): nur eine Wallbox **in Betrieb** an diesem Tag deckt die Ladung ab — eine am Vortag
    stillgelegte Wallbox mit Ladezähler lässt das E-Auto seine Heim-Ladung tragen."""
    anlage, (wallbox, eauto), invs = await _anlage_mit_zaehlern(db, [
        ("wallbox", {"stilllegungsdatum": TAG - timedelta(days=1)}, {"ladung_kwh": [0.0, 0.0, 0.0, 0.0]}),
        ("e-auto", {}, {"ladung_pv_kwh": [0.0, 0.0, 4.0, 4.0]}),
    ])
    d = await get_tagesdetail_kwh(db, anlage, invs, TAG)
    assert d.werte_je_inv["emob_ladung_pv_kwh"] == {str(eauto.id): 4.0}


async def test_rf71_gemessene_null_ohne_grund_des_betriebsart_zaehlers(db):
    """``_waerme_tag`` (W-18, Alternativ-Gruppe der Heizwärme): der Betriebsart-Key zählt nur mit, wenn die Achse
    selbst einen Grund trägt — eine gemessene 0 auf Achse und Warmwasser bekommt keinen «kein Zähler»-Grund, nur
    weil der Betriebsart-Zähler nicht zugeordnet ist (Muster ``test_n348_…::test_gemessene_null_…``)."""
    anlage, _ = await _anlage_mit_wps(db, [
        (_LW, {"stromverbrauch_kwh": 4.0, "heizenergie_kwh": 0.0, "warmwasser_kwh": 0.0}),
    ])
    t = await _tag(db, anlage.id)
    assert t.wp_waerme_kwh is None
    assert t.wp_waerme_grund is None


async def test_rf71_stoerung_nur_von_geraeten_mit_strom_des_tages(db):
    """R2 (Anwender-Angabe ``abgrenzung``): ein Heizstab auf dem WP-Zähler (``fremdstrom``) sperrt die Tageszahl und
    beide Funktionen — aber nur, wenn das gemeldete Gerät an diesem Tag Strom beigetragen hat."""
    from backend.core.berechnungen.waermepumpe_kennzahl import GRUND_FREMDSTROM

    stoer = {**_LW_F5, "abgrenzung": "fremdstrom"}
    gestoert, _ = await _anlage_mit_wps(db, [(stoer, {
        "stromverbrauch_kwh": 4.0, "heizenergie_kwh": 12.0, "strom_heizen_kwh": 3.0})])
    t = await _tag(db, gestoert.id)
    assert (t.wp_jaz, t.wp_jaz_grund) == (None, GRUND_FREMDSTROM)
    assert t.wp_jaz_heizen_grund == GRUND_FREMDSTROM

    still, _ = await _anlage_mit_wps(db, [
        (_LW_F5, {"stromverbrauch_kwh": 4.0, "heizenergie_kwh": 12.0, "strom_heizen_kwh": 3.0}),
        (stoer, {"heizenergie_kwh": 0.0}),
    ])
    t = await _tag(db, still.id)
    assert t.wp_jaz == 3.0 and t.wp_jaz_grund is None


async def test_rf71_monats_lage_geraete_ohne_waerme_je_funktion(db, monkeypatch):
    """``_abgrenzung_tag`` (R2/§4.2 Fall 1 aus den Monats-Fakten des Monats): meldet der Monat Strom von Geräten ohne
    Wärme, nennt eine Funktion mit verletzter Tages-Deckung diesen Block-Grund statt des allgemeinen Deckungs-Satzes
    (``abgrenzung_je_funktion``: der konkretere Block-Grund gewinnt). Die Monats-Fakten sind gestellt."""
    from backend.api.routes.energie_profil import tag as tag_modul
    from backend.core.berechnungen.waermepumpe_kennzahl import (
        GRUND_FUNKTION_NICHT_DECKUNGSGLEICH, GRUND_GERAETE_OHNE_WAERME,
    )

    anlage, _ = await _anlage_mit_wps(db, [
        (_LW_F5, {"stromverbrauch_kwh": 4.0, "heizenergie_kwh": 12.0, "strom_heizen_kwh": 3.0}),
        (_LW_F5, {"stromverbrauch_kwh": 2.0, "strom_heizen_kwh": 2.0}),
    ])
    assert (await _tag(db, anlage.id)).wp_jaz_heizen_grund == GRUND_FUNKTION_NICHT_DECKUNGSGLEICH

    async def _monat(*a, **k):
        return [SimpleNamespace(wp=SimpleNamespace(waerme_deckt_nicht_alle_geraete=True, geraete_verschieden=False))]

    monkeypatch.setattr(tag_modul, "lade_monats_fakten", _monat)
    assert (await _tag(db, anlage.id)).wp_jaz_heizen_grund == GRUND_GERAETE_OHNE_WAERME
