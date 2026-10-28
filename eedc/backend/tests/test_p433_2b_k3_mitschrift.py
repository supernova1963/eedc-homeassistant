"""P-433-2b K3 «Zustands-Mitschrift typoffen, Karte „Betrieb heute“ E-Mobilität» — Backend-Proben (Bauplan K3 §1–§5).

Was hier gesichert wird, und warum jede Gruppe existiert:

1. **Eine Regel** (K3-1): mitgeschrieben wird jedes Registry-Zustandsfeld mit ``kanon`` und ``mitschrift: True`` —
   abgeleitete Menge ``MITSCHRIFT_LIVE_FELDER`` (Wächter mit Registry-Kopie, keine getippte Liste); Lademodus, Textfeld
   und evcc-Rollen bleiben ``nur_live`` (Sprengsatz S2).
2. **Katalog** (K3-2): ``zustand:inv:<id>:<feld>:<wert>`` (mean, Anteil) und ``wechsel:inv:<id>:ladezustand:laedt``
   (sum); der Betriebsmodus behält ``modus:`` (S1).
3. **Kanon** (K3-4): ``ladezustand_aus_werten`` — gemessener zuerst, sonst Option A; der Live-Leser nutzt dieselbe Regel.
4. **Layer** (K3-6): ``stunden_je_zustand`` = die WP-Formel parametrisiert (bitgleich); ``kein_fahrzeug`` ist kein
   Betrieb (S4).
5. **Inbound** (K3-4): ein Fenster je (Gerät, Feld) (S6), Option A schreibt das Ladezustand-Fenster, gemessener geht vor
   (S3), Wechsel nur von einem bekannten Wert (S7, E-K3-1), Modus-Pfad unberührt.
6. **Snapshot** (K3-3): Zeilen ``inv:<id>:<feld>:<wert>`` und ``…:wechsel_laedt`` (nur > 0), nur bei Verbindung.
7. **Stundenlauf MQTT**: Anteile und fortlaufender Wechsel-Stand, laufende Stunde nie (S5), HA-Entität schließt aus.
8. **HA-Pfad** (K3-5, D6): direkt; Option A verschränkt (Abnahme 20 min lädt / 40 min wartet ⇒ 1/3 · 2/3); gemessener
   geht vor (S3 HA); Wechsel ohne Vorgänger zählt nicht (S7 HA); Schreiber Slot-Form, nur abgeschlossene Stunden.
9. **Tag-Detail** (K3-7): ``emob_betrieb`` mit Stunden in Lese-Reihenfolge, Klartext, «Ladevorgänge»; ohne Mitschrift
   leer; Monats-Fakten unberührt.
10. **Investition löschen** räumt ``zustand:``/``wechsel:`` mit (N-668-Klasse).

Die Uhr steht fest (``jetzt=`` bzw. ``zeitpunkt``) — keine Probe liest die echte Uhr.

Schwesterdateien: test_kanal_mitschrift_betriebsart.py (HA-Mitschrift WP), test_standalone_s1_betriebsmodus_mqtt.py
(MQTT-Mitschrift WP), test_p433_2c_auf_einen_blick.py (Karte «Betrieb heute» WP), test_p433_2b_k1_emob.py,
test_p433_2b_k2b_option_a_gateway_preset.py (Option A live), test_kanal_feld_deckung.py (Katalog).
"""

from __future__ import annotations

import calendar
import copy
import time as _zeit
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import select

from backend.core import zustands_kanon as zk
from backend.core.berechnungen.betriebsstunden import (
    BETRIEBSARTEN_MIT_STUNDEN,
    stunden_je_betriebsart,
    stunden_je_zustand,
)
from backend.core.field_definitions import LIVE_FELDER_INV, MITSCHRIFT_LIVE_FELDER, ist_mitschrift_feld
from backend.models.kanal import ART_MEAN, ART_SUM, FAMILIE_MITSCHRIFT, Kanal, KanalQuelle, KanalStatistik
from backend.models.mqtt_live_snapshot import MqttLiveSnapshot
from backend.services import betriebsmodus_live as bml
from backend.services import mqtt_inbound_service as mis
from backend.services.energie_profil import _helpers
from backend.services.kanal import katalog as kat
from backend.services.mqtt_inbound_service import MqttInboundCache
from backend.tests import factories, ha_lts_helfer

_STUNDE = 3600
#: Eine volle UTC-Stunde (eine ganze Stunde in jeder Zone) — MQTT-Proben.
T0 = calendar.timegm((2026, 6, 10, 8, 0, 0))
#: HA-Proben in lokaler Zeit.
TAG = date(2026, 6, 10)
M0 = datetime(2026, 6, 10, 0)

MITSCHRIFT = {("wallbox", "ladezustand"), ("e-auto", "ladezustand_fahrzeug"), ("e-auto", "zu_hause")}


def _ts(dt: datetime) -> int:
    return int(_zeit.mktime(dt.timetuple()))


@pytest.fixture(autouse=True)
def _ohne_takt_und_singleton(monkeypatch):
    bml.cache_leeren()
    monkeypatch.setattr(mis, "_mqtt_inbound_service", None)
    yield
    bml.cache_leeren()


async def _anlage_emob(db, *, wb_live: dict | None = None, auto_live: dict | None = None):
    a = await factories.anlage(db, anlagenname="Test", sensor_mapping={})
    wb = await factories.investition(db, a.id, "wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1))
    auto = await factories.investition(db, a.id, "e-auto", bezeichnung="Auto", anschaffungsdatum=date(2024, 1, 1))
    inv = {}
    if wb_live is not None:
        inv[str(wb.id)] = {"live": wb_live}
    if auto_live is not None:
        inv[str(auto.id)] = {"live": auto_live}
    a.sensor_mapping = {"investitionen": inv}
    await db.commit()
    return a, wb, auto


async def _kanalzeilen(db, anlage_id: int, praefix: str) -> dict[str, dict[int, tuple]]:
    out: dict[str, dict[int, tuple]] = {}
    for k in (await db.execute(select(Kanal).where(Kanal.anlage_id == anlage_id,
                                                   Kanal.key.like(f"{praefix}%")))).scalars().all():
        rows = (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id))).scalars().all()
        out[k.key] = {r.start_ts: (r.mean if k.art == ART_MEAN else r.sum) for r in rows}
    return out


# ═══ 1 · Eine Regel ═══════════════════════════════════════════════════════════

def test_mitschrift_felder_kommen_aus_der_registry():
    assert MITSCHRIFT_LIVE_FELDER == MITSCHRIFT
    for typ, feld in MITSCHRIFT:
        f = next(x for x in LIVE_FELDER_INV[typ] if x["key"] == feld)
        assert f["zustand"] and f["kanon"] == feld and f["mitschrift"] is True and "nur_live" not in f
        assert "mitgeschrieben" in f["hinweis"]
        assert ist_mitschrift_feld(feld, typ) and ist_mitschrift_feld(feld)
    for feld in ("lademodus", "fahrzeug_am_ladepunkt", *zk.OPTION_A_FELDER):
        assert not ist_mitschrift_feld(feld, "wallbox"), feld
    assert not ist_mitschrift_feld("betriebsmodus", "waermepumpe"), "der Modus hat seinen eigenen Pfad"


def test_waechter_registry_kopie_mitschrift_ohne_kanon_hat_keine_regel():
    """Gegenprobe der Ableitung: ein Probefeld mit ``mitschrift`` und Kanon bekommt einen ``zustand:``-Kanal; dasselbe
    ohne Kanon (ein Text) bekommt KEINE Regel — der Deckungs-Wächter meldet es beim Namen."""
    live = copy.deepcopy(LIVE_FELDER_INV)
    live["wallbox"].append({"key": "probe_zustand", "einheit": "", "zustand": True, "kanon": "ladezustand",
                            "mitschrift": True})
    live["wallbox"].append({"key": "probe_text", "einheit": "", "zustand": True, "text": True, "mitschrift": True})
    zuw, ohne = kat.kanal_katalog(live_felder_inv=live)
    probe = next(z for z in zuw if z.feld == "probe_zustand")
    assert (probe.art, probe.familien, probe.schluessel) == (
        ART_MEAN, (FAMILIE_MITSCHRIFT,), "zustand:inv:{id}:probe_zustand:{wert}")
    assert (kat.L_LIVE_INV, "wallbox", "probe_text") in ohne
    from backend.core.field_definitions.karten import mitschrift_live_felder

    assert mitschrift_live_felder(live) == MITSCHRIFT | {("wallbox", "probe_zustand")}


# ═══ 2 · Katalog (S1, S2) ═════════════════════════════════════════════════════

def test_katalog_zustand_und_wechsel_nur_fuer_mitschrift_felder():
    zustand = {(z.typ, z.feld): z for z in kat.zuweisungen() if z.schluessel.startswith("zustand:")}
    assert set(zustand) == MITSCHRIFT
    for (typ, feld), z in zustand.items():
        assert (z.liste, z.art, z.familien, z.e1_schreiber) == (kat.L_LIVE_INV, ART_MEAN, (FAMILIE_MITSCHRIFT,), True)
        assert z.schluessel == f"zustand:inv:{{id}}:{feld}:{{wert}}"
    wechsel = [z for z in kat.zuweisungen() if z.schluessel.startswith("wechsel:")]
    assert [(z.liste, z.typ, z.feld, z.art, z.schluessel) for z in wechsel] == [
        (kat.L_WECHSEL, "wallbox", "ladezustand", ART_SUM, "wechsel:inv:{id}:ladezustand:laedt")]
    nur_live = {(z.typ, z.feld) for z in kat.zuweisungen() if z.ausnahme == kat.AUSNAHME_NUR_LIVE}
    assert {("wallbox", "lademodus"), ("wallbox", "fahrzeug_am_ladepunkt")} | {
        ("wallbox", f) for f in zk.OPTION_A_FELDER} <= nur_live
    assert not nur_live & MITSCHRIFT
    assert kat.zaehler_art("inv:4:ladezustand", "wallbox") is None, "kein Zähler im Snapshot-Sinn"


def test_modus_schluessel_und_neue_schluessel():
    assert kat.modus_kanal_key(7, "heizen") == "modus:inv:7:heizen"
    wp = [z for z in kat.zuweisungen() if z.feld == "betriebsmodus"]
    assert [z.schluessel for z in wp] == ["modus:inv:{id}:{betriebsart}"]
    assert kat.zustand_kanal_key(4, "ladezustand", "laedt") == "zustand:inv:4:ladezustand:laedt"
    assert kat.wechsel_kanal_key(4, "ladezustand", "laedt") == "wechsel:inv:4:ladezustand:laedt"


# ═══ 3 · Kanon ════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("werte,erwartet", [
    ({"ladezustand": "wartet", "evcc_verbunden": "an", "evcc_laedt": "an"}, "wartet"),     # S3: gemessener vor
    ({"evcc_verbunden": "aus", "evcc_laedt": "an"}, "kein_fahrzeug"),
    ({"evcc_verbunden": "an", "evcc_laedt": "an", "evcc_freigegeben": "aus"}, "laedt"),
    ({"evcc_verbunden": "an", "evcc_laedt": "aus", "evcc_freigegeben": "aus"}, "wartet"),
    ({"evcc_verbunden": "an", "evcc_laedt": None, "evcc_freigegeben": None}, "verbunden"),
    ({"evcc_laedt": "an"}, None),
    ({}, None),
    ({"ladezustand": None, "evcc_verbunden": None}, None),
])
def test_ladezustand_aus_werten(werte, erwartet):
    assert zk.ladezustand_aus_werten(werte) == erwartet


def test_live_leser_rechnet_mit_derselben_regel():
    ergebnis = {(5, "evcc_verbunden"): "an", (5, "evcc_laedt"): "aus", (5, "evcc_freigegeben"): "aus",
                (6, "evcc_verbunden"): "an", (6, "ladezustand"): "fertig"}
    out = bml._kombiniere_option_a(dict(ergebnis))
    assert out[(5, "ladezustand")] == "wartet"
    assert out[(6, "ladezustand")] == "fertig", "ein gemessener Ladezustand geht immer vor"


# ═══ 4 · Layer (S4) ═══════════════════════════════════════════════════════════

@pytest.mark.parametrize("anteile", [
    {},
    {0: {"heizen": 1.0}, 1: {"heizen": 0.4, "warmwasser": 0.6}, 2: {"aus": 1.0}},
    {0: {"unbestimmt": 1.0, "kuehlen": 0.25, "aus": 0.5, "lueften": 0.25, "heizen": 0.0}},
    {0: {"aus": 1.0}, 1: {"unbestimmt": 1.0}},
    {0: {"heizen": 0.33333}, 1: {"heizen": 0.33333}, 2: {"heizen": 0.33334}},
])
def test_stunden_je_zustand_ist_die_wp_formel_bitgleich(anteile):
    def alt(a):     # die Formel vor K3, wörtlich
        summe: dict[str, float] = {}
        for je in a.values():
            for m, x in je.items():
                if m in BETRIEBSARTEN_MIT_STUNDEN and x is not None:
                    summe[m] = summe.get(m, 0.0) + float(x)
        return None if not summe else {m: round(summe[m], 1) for m in BETRIEBSARTEN_MIT_STUNDEN if m in summe}
    assert stunden_je_betriebsart(anteile) == alt(anteile)
    assert stunden_je_zustand(anteile, BETRIEBSARTEN_MIT_STUNDEN) == alt(anteile)


def test_kein_fahrzeug_ist_kein_betrieb():
    werte = zk.WERTE_MIT_STUNDEN["ladezustand"]
    assert werte == ("laedt", "verbunden", "wartet", "fertig")
    for kein in ("kein_fahrzeug", "gesperrt", "fehler"):
        assert kein not in werte
    assert "nicht_verbunden" not in zk.WERTE_MIT_STUNDEN["ladezustand_fahrzeug"]
    assert stunden_je_zustand({0: {"kein_fahrzeug": 1.0}}, werte) is None
    assert stunden_je_zustand({0: {"kein_fahrzeug": 0.5, "laedt": 0.5}, 1: {"laedt": 0.0, "kein_fahrzeug": 1.0}},
                              werte) == {"laedt": 0.5}
    assert stunden_je_zustand({0: {"laedt": 0.0, "verbunden": 0.0, "kein_fahrzeug": 1.0}}, werte) == {
        "laedt": 0.0, "verbunden": 0.0}, "gemessene 0 bleibt eine Auskunft"
    assert list(stunden_je_zustand({0: {"wartet": 0.5, "laedt": 0.5}}, werte)) == ["laedt", "wartet"]


# ═══ 5 · Inbound (S3 MQTT, S6, S7) ════════════════════════════════════════════

def _topic(anlage_id: int, inv_id: int, key: str) -> str:
    return f"eedc/{anlage_id}_Test/live/inv/{inv_id}_WB/{key}"


def test_ein_fenster_je_feld_nicht_je_geraet():
    """S6: Ladezustand und Standort an derselben Investition teilen KEIN Fenster."""
    c = MqttInboundCache()
    c.verbinden()
    c.on_message(_topic(1, 4, "ladezustand"), "laedt", jetzt=T0)
    c.on_message(_topic(1, 4, "zu_hause"), "home", jetzt=T0 + 60)
    out = c.zustand_anteile_abschliessen(T0 + 300)
    assert out == {1: {"4": {"ladezustand": ({"laedt": 1.0}, {}), "zu_hause": ({"zu_hause": 1.0}, {})}}}
    # (Ein Fenster beginnt mit seiner ersten Nachricht — dieselbe Regel wie beim Modus.)


def test_option_a_nachricht_schreibt_das_ladezustand_fenster_und_gemessener_geht_vor():
    c = MqttInboundCache()
    c.verbinden()
    c.on_message(_topic(1, 4, "evcc_verbunden"), "true", jetzt=T0)
    c.on_message(_topic(1, 4, "evcc_laedt"), "true", jetzt=T0 + 60)      # 0–60 verbunden, ab 60 lädt
    a, w = c.zustand_anteile_abschliessen(T0 + 300)[1]["4"]["ladezustand"]
    assert a == pytest.approx({"verbunden": 0.2, "laedt": 0.8}) and w == {"laedt": 1}
    # S3 (MQTT): ein gemessener Ladezustand überstimmt Option A.
    c.on_message(_topic(1, 4, "ladezustand"), "3", jetzt=T0 + 300)        # go-e-Code 3 = wartet (codes=True)
    c.on_message(_topic(1, 4, "evcc_laedt"), "true", jetzt=T0 + 360)
    a, _w = c.zustand_anteile_abschliessen(T0 + 600)[1]["4"]["ladezustand"]
    assert a == {"wartet": 1.0}


def test_wechsel_nur_von_einem_bekannten_wert():
    """S7 / E-K3-1: der erste Wert nach dem Verbinden (None → lädt) zählt nicht, auch nicht nach «unknown»."""
    c = MqttInboundCache()
    c.verbinden()
    c.on_message(_topic(1, 4, "ladezustand"), "laedt", jetzt=T0)
    _a, w = c.zustand_anteile_abschliessen(T0 + 300)[1]["4"]["ladezustand"]
    assert w == {}
    c.on_message(_topic(1, 4, "ladezustand"), "kein_fahrzeug", jetzt=T0 + 310)
    c.on_message(_topic(1, 4, "ladezustand"), "laedt", jetzt=T0 + 320)
    c.on_message(_topic(1, 4, "ladezustand"), "laedt", jetzt=T0 + 330)    # gleicher Wert: kein Wechsel
    c.on_message(_topic(1, 4, "ladezustand"), "unknown", jetzt=T0 + 340)
    c.on_message(_topic(1, 4, "ladezustand"), "laedt", jetzt=T0 + 350)    # nach «unknown»: zählt nicht
    _a, w = c.zustand_anteile_abschliessen(T0 + 600)[1]["4"]["ladezustand"]
    assert w == {"kein_fahrzeug": 1, "laedt": 1}


def test_modus_pfad_bleibt_unberuehrt():
    c = MqttInboundCache()
    c.verbinden()
    c.on_message(_topic(1, 39, "betriebsmodus"), "1", jetzt=T0)
    c.on_message(_topic(1, 39, "betriebsmodus"), "2", jetzt=T0 + 150)
    assert c.modus_anteile_abschliessen(T0 + 300) == {1: {"39": {"heizen": 0.5, "warmwasser": 0.5}}}
    assert c.zustand_anteile_abschliessen(T0 + 300) == {}
    assert not c._zustand_fenster


def test_verbinden_und_trennen_leeren_die_zustands_fenster():
    c = MqttInboundCache()
    c.verbinden()
    c.on_message(_topic(1, 4, "ladezustand"), "laedt", jetzt=T0)
    c.trennen()
    assert c.zustand_anteile_abschliessen(T0 + 300) == {}
    c.verbinden()
    c.on_message(_topic(1, 4, "ladezustand"), "laedt", jetzt=T0 + 400)
    c.verbinden()
    assert not c._zustand_fenster


# ═══ 6 · Snapshot ═════════════════════════════════════════════════════════════

def test_snapshot_zeilen_anteil_und_wechsel():
    from backend.services.mqtt_live_history_service import zustand_zeilen

    c = MqttInboundCache()
    c.verbinden()
    c.on_message(_topic(1, 4, "ladezustand"), "kein_fahrzeug", jetzt=T0)
    c.on_message(_topic(1, 4, "ladezustand"), "laedt", jetzt=T0 + 150)
    c.on_message(_topic(1, 5, "ladezustand_fahrzeug"), "charging", jetzt=T0)
    c.on_message(_topic(1, 5, "ladezustand_fahrzeug"), "plugged_in", jetzt=T0 + 150)
    rows = zustand_zeilen(c, {1}, datetime.fromtimestamp(T0 + 300), T0 + 300)
    assert sorted((r.component_key, r.value_w) for r in rows) == [
        ("inv:4:ladezustand:kein_fahrzeug", 0.5), ("inv:4:ladezustand:laedt", 0.5),
        ("inv:4:ladezustand:wechsel_laedt", 1.0),
        ("inv:5:ladezustand_fahrzeug:laedt", 0.5), ("inv:5:ladezustand_fahrzeug:verbunden", 0.5)]
    assert all(r.ts_unix == T0 + 300 for r in rows)
    # Ohne Wechsel keine Wechsel-Zeile; ohne Verbindung gar nichts; fremde Anlage nichts.
    assert {r.component_key for r in zustand_zeilen(c, {1}, datetime.fromtimestamp(T0 + 600), T0 + 600)} == {
        "inv:4:ladezustand:laedt", "inv:5:ladezustand_fahrzeug:verbunden"}
    assert zustand_zeilen(c, {2}, datetime.fromtimestamp(T0 + 900), T0 + 900) == []
    c.trennen()
    assert zustand_zeilen(c, {1}, datetime.fromtimestamp(T0 + 1200), T0 + 1200) == []


async def test_snapshot_lauf_schreibt_die_zustands_zeilen(db, monkeypatch):
    from backend.services import mqtt_live_history_service as mlh

    a, wb, _auto = await _anlage_emob(db)
    cache = MqttInboundCache()
    cache.verbinden()
    t = _zeit.time()
    cache.on_message(f"eedc/{a.id}_Test/live/inv/{wb.id}_WB/ladezustand", "laedt", jetzt=t - 120)

    @asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr(mlh, "get_mqtt_inbound_service", lambda: SimpleNamespace(cache=cache))
    monkeypatch.setattr(mlh, "get_session", _session)
    assert await mlh.snapshot_live_cache() == 1
    rows = (await db.execute(select(MqttLiveSnapshot))).scalars().all()
    assert [(r.component_key, r.value_w) for r in rows] == [(f"inv:{wb.id}:ladezustand:laedt", 1.0)]


# ═══ 7 · Stundenlauf MQTT (S5) ════════════════════════════════════════════════

def _snap(anlage_id: int, inv_id: int, ts: int, feld: str, wert: str, anteil: float = 1.0) -> MqttLiveSnapshot:
    return MqttLiveSnapshot(anlage_id=anlage_id, timestamp=datetime.fromtimestamp(ts),
                            component_key=f"inv:{inv_id}:{feld}:{wert}", value_w=anteil, ts_unix=ts)


async def test_mqtt_mitschrift_anteile_wechsel_und_laufende_stunde_nie(db):
    from backend.services.kanal.schreiber import schreibe_zustands_mitschrift_mqtt

    a, wb, auto = await _anlage_emob(db)
    for m in range(5, 65, 5):                      # Stunde T0: 4 Fenster verbunden, 8 Fenster lädt
        db.add(_snap(a.id, wb.id, T0 + m * 60 - 1, "ladezustand", "verbunden" if m <= 20 else "laedt"))
        db.add(_snap(a.id, auto.id, T0 + m * 60 - 1, "zu_hause", "zu_hause"))
    db.add(_snap(a.id, wb.id, T0 + 24 * 60 - 1, "ladezustand", "wechsel_laedt"))      # ein Übergang
    db.add(_snap(a.id, wb.id, T0 + _STUNDE + 300, "ladezustand", "laedt"))            # laufende Stunde
    db.add(_snap(a.id, wb.id, T0 + _STUNDE + 300, "ladezustand", "wechsel_laedt"))
    await db.commit()
    await schreibe_zustands_mitschrift_mqtt(db, a, datetime.fromtimestamp(T0 + _STUNDE + 600))
    await db.commit()
    z = await _kanalzeilen(db, a.id, f"zustand:inv:{wb.id}:")
    assert set(z) == {f"zustand:inv:{wb.id}:ladezustand:{w}" for w in zk.KANON["ladezustand"]}
    assert z[f"zustand:inv:{wb.id}:ladezustand:laedt"] == {T0: pytest.approx(2 / 3)}
    assert z[f"zustand:inv:{wb.id}:ladezustand:verbunden"] == {T0: pytest.approx(1 / 3)}
    assert z[f"zustand:inv:{wb.id}:ladezustand:kein_fahrzeug"] == {T0: 0.0}
    assert (await _kanalzeilen(db, a.id, f"zustand:inv:{auto.id}:zu_hause:"))[
        f"zustand:inv:{auto.id}:zu_hause:zu_hause"] == {T0: 1.0}
    w = await _kanalzeilen(db, a.id, "wechsel:")
    assert w == {f"wechsel:inv:{wb.id}:ladezustand:laedt": {T0: 1.0}}, "nur die abgeschlossene Stunde (S5)"
    k = (await db.execute(select(Kanal).where(Kanal.key == f"wechsel:inv:{wb.id}:ladezustand:laedt"))).scalar_one()
    q = (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars().all()
    assert (k.art, k.einheit) == (ART_SUM, "") and [(x.familie, x.statistic_id) for x in q] == [
        (FAMILIE_MITSCHRIFT, f"mqtt:inv/{wb.id}/ladezustand")]
    # Nächste Stunde: fortlaufender Stand (1 + 1), die erste bleibt; Wiederholung schreibt nichts.
    await schreibe_zustands_mitschrift_mqtt(db, a, datetime.fromtimestamp(T0 + 2 * _STUNDE + 600))
    await db.commit()
    assert (await _kanalzeilen(db, a.id, "wechsel:"))[f"wechsel:inv:{wb.id}:ladezustand:laedt"] == {
        T0: 1.0, T0 + _STUNDE: 2.0}
    assert await schreibe_zustands_mitschrift_mqtt(db, a, datetime.fromtimestamp(T0 + 2 * _STUNDE + 900)) == 0


@pytest.mark.parametrize("wb_live", [{"ladezustand": "sensor.wb"}, {"evcc_verbunden": "binary_sensor.wb_c"}])
async def test_mqtt_schreibt_nicht_bei_ha_entitaet(db, wb_live):
    from backend.services.kanal.schreiber import schreibe_zustands_mitschrift_mqtt

    a, wb, _auto = await _anlage_emob(db, wb_live=wb_live)
    for m in range(5, 65, 5):
        db.add(_snap(a.id, wb.id, T0 + m * 60 - 1, "ladezustand", "laedt"))
    await db.commit()
    assert await schreibe_zustands_mitschrift_mqtt(db, a, datetime.fromtimestamp(T0 + _STUNDE + 600)) == 0


async def test_stillgelegtes_geraet_schreibt_nicht(db):
    from backend.services.kanal.schreiber import schreibe_zustands_mitschrift_mqtt

    a, wb, _auto = await _anlage_emob(db)
    wb.stilllegungsdatum = date(2025, 1, 1)
    for m in range(5, 65, 5):
        db.add(_snap(a.id, wb.id, T0 + m * 60 - 1, "ladezustand", "laedt"))
    await db.commit()
    assert await schreibe_zustands_mitschrift_mqtt(db, a, datetime.fromtimestamp(T0 + _STUNDE + 600)) == 0


# ═══ 8 · HA-Pfad (K3-5, D6; S3/S5/S7 HA) ══════════════════════════════════════

async def _ha(db, a, verlauf: dict, *, feld="ladezustand", typ="wallbox"):
    with patch("backend.services.ha_state_service.get_ha_state_service",
               lambda: ha_lts_helfer.ZustandsVerlauf(verlauf)):
        return await _helpers._get_zustand_history(
            a, a.sensor_mapping, TAG, db, typ=typ, feld=feld,
            normalisiere=lambda roh, _akt=None: zk.normalisiere(feld, roh),
            option_a=zk.OPTION_A_FELDER if feld == "ladezustand" else None)


async def test_ha_direkt_anteile_entitaet_und_wechsel(db):
    a, wb, _auto = await _anlage_emob(db, wb_live={"ladezustand": "sensor.wb"})
    m = await _ha(db, a, {"sensor.wb": [(datetime(2026, 6, 9, 22), "not_connected"),
                                        (M0 + timedelta(hours=7, minutes=15), "active_mode"),
                                        (M0 + timedelta(hours=7, minutes=45), "sleep_mode")]})
    # Slot 8 = [07:00, 08:00): 15 min kein Fahrzeug, 30 min lädt, 15 min verbunden
    assert m.anteile[8][wb.id] == pytest.approx({"kein_fahrzeug": 0.25, "laedt": 0.5, "verbunden": 0.25})
    assert m.anteile[3][wb.id] == {"kein_fahrzeug": 1.0}
    assert m.entitaeten == {wb.id: "sensor.wb"}
    assert m.wechsel[8] == {wb.id: 1} and m.wechsel[3] == {wb.id: 0}


async def test_ha_option_a_verschraenkt_drei_verlaeufe(db):
    """Abnahme (Bauplan §5): verbunden seit dem Vortag, lädt 10:00–10:20, dann nicht freigegeben ⇒ Slot 11
    ``[10:00, 11:00)`` = 20 min lädt, 40 min wartet ⇒ 1/3 · 2/3; ein Ladevorgang (verbunden → lädt um 10:00)."""
    live = {"evcc_verbunden": "binary_sensor.c", "evcc_laedt": "binary_sensor.l", "evcc_freigegeben": "binary_sensor.f"}
    a, wb, _auto = await _anlage_emob(db, wb_live=live)
    m = await _ha(db, a, {
        "binary_sensor.c": [(datetime(2026, 6, 9, 20), "on")],
        "binary_sensor.l": [(datetime(2026, 6, 9, 20), "off"), (M0 + timedelta(hours=10), "on"),
                            (M0 + timedelta(hours=10, minutes=20), "off")],
        "binary_sensor.f": [(datetime(2026, 6, 9, 20), "on"), (M0 + timedelta(hours=10, minutes=20), "off")],
    })
    # (Der Wechsel genau zur vollen Stunde hinterlässt «verbunden» mit 0 s — Bestandsregel der Verweildauer-Schleife.)
    assert m.anteile[11][wb.id] == pytest.approx({"verbunden": 0.0, "laedt": 1 / 3, "wartet": 2 / 3})
    assert m.anteile[10][wb.id] == {"verbunden": 1.0}
    assert m.wechsel[11] == {wb.id: 1}
    assert m.entitaeten == {wb.id: "binary_sensor.c|binary_sensor.l|binary_sensor.f"}, "E-K3-2"


async def test_ha_option_a_nur_verbunden_kennt_kein_laden(db):
    a, wb, _auto = await _anlage_emob(db, wb_live={"evcc_verbunden": "binary_sensor.c"})
    m = await _ha(db, a, {"binary_sensor.c": [(datetime(2026, 6, 9, 20), "off"),
                                               (M0 + timedelta(hours=5, minutes=30), "on")]})
    assert m.anteile[6][wb.id] == pytest.approx({"kein_fahrzeug": 0.5, "verbunden": 0.5})
    assert m.entitaeten == {wb.id: "binary_sensor.c"}


async def test_ha_gemessener_ladezustand_geht_vor(db):
    """S3 (HA): Ladezustand-Entität UND evcc-Felder — die Mitschrift kommt allein aus dem gemessenen."""
    live = {"ladezustand": "sensor.wb", "evcc_verbunden": "binary_sensor.c", "evcc_laedt": "binary_sensor.l"}
    a, wb, _auto = await _anlage_emob(db, wb_live=live)
    m = await _ha(db, a, {"sensor.wb": [(datetime(2026, 6, 9, 20), "station_locked")],
                          "binary_sensor.c": [(datetime(2026, 6, 9, 20), "on")],
                          "binary_sensor.l": [(datetime(2026, 6, 9, 20), "on")]})
    assert m.anteile[5][wb.id] == {"gesperrt": 1.0}
    assert m.entitaeten == {wb.id: "sensor.wb"}


async def test_ha_wechsel_ohne_vorgaenger_zaehlt_nicht(db):
    """S7 (HA): der erste Punkt überhaupt (kein Vortag) ist kein Ladevorgang."""
    a, wb, _auto = await _anlage_emob(db, wb_live={"ladezustand": "sensor.wb"})
    m = await _ha(db, a, {"sensor.wb": [(M0 + timedelta(hours=4, minutes=10), "active_mode"),
                                        (M0 + timedelta(hours=4, minutes=30), "sleep_mode"),
                                        (M0 + timedelta(hours=4, minutes=40), "active_mode")]})
    assert m.wechsel[5] == {wb.id: 1}, "nur verbunden → lädt um 04:40"
    assert 4 not in m.anteile, "vor dem ersten Punkt: nicht hingesehen"


async def test_ha_e_auto_felder(db):
    a, _wb, auto = await _anlage_emob(db, auto_live={"ladezustand_fahrzeug": "sensor.auto", "zu_hause": "device_tracker.a"})
    m = await _ha(db, a, {"sensor.auto": [(datetime(2026, 6, 9, 20), "charging"),
                                          (M0 + timedelta(hours=2, minutes=30), "fully_charged")]},
                  feld="ladezustand_fahrzeug", typ="e-auto")
    assert m.anteile[3][auto.id] == pytest.approx({"laedt": 0.5, "fertig": 0.5}) and m.wechsel == {}
    m = await _ha(db, a, {"device_tracker.a": [(datetime(2026, 6, 9, 20), "not_home"),
                                               (M0 + timedelta(hours=6, minutes=45), "home")]},
                  feld="zu_hause", typ="e-auto")
    assert m.anteile[7][auto.id] == pytest.approx({"unterwegs": 0.75, "zu_hause": 0.25})


async def test_ha_schreiber_slot_form_nur_abgeschlossene_stunden(db):
    from backend.services.kanal.schreiber import schreibe_zustands_mitschrift

    a, wb, _auto = await _anlage_emob(db, wb_live={"ladezustand": "sensor.wb"})
    m = await _ha(db, a, {"sensor.wb": [(datetime(2026, 6, 9, 22), "not_connected"),
                                        (M0 + timedelta(hours=7, minutes=15), "active_mode"),
                                        (M0 + timedelta(hours=7, minutes=45), "sleep_mode")]})
    n = await schreibe_zustands_mitschrift(db, a, TAG, {("wallbox", "ladezustand"): m},
                                           jetzt=M0 + timedelta(hours=8, minutes=10))
    await db.commit()
    z = await _kanalzeilen(db, a.id, f"zustand:inv:{wb.id}:")
    slot8 = _ts(M0 + timedelta(hours=7))
    assert z[f"zustand:inv:{wb.id}:ladezustand:laedt"][slot8] == pytest.approx(0.5)
    for werte in z.values():
        assert max(werte) == slot8 and min(werte) == _ts(M0 - timedelta(hours=1))   # Slot 9 läuft noch (S5)
    w = (await _kanalzeilen(db, a.id, "wechsel:"))[f"wechsel:inv:{wb.id}:ladezustand:laedt"]
    assert w[slot8] == 1.0 and w[_ts(M0 + timedelta(hours=6))] == 0.0 and len(w) == 9
    assert n == 9 * len(zk.KANON["ladezustand"]) + 9


async def test_mitschrift_history_aller_felder_und_sicherer_einstieg(db, monkeypatch):
    from backend.services.kanal import schreiber

    a, wb, auto = await _anlage_emob(db, wb_live={"ladezustand": "sensor.wb"},
                                     auto_live={"zu_hause": "device_tracker.a"})
    verlauf = {"sensor.wb": [(datetime(2026, 6, 9, 22), "active_mode")],
               "device_tracker.a": [(datetime(2026, 6, 9, 22), "home")]}
    with patch("backend.services.ha_state_service.get_ha_state_service",
               lambda: ha_lts_helfer.ZustandsVerlauf(verlauf)):
        je_feld = await _helpers._get_zustands_mitschrift_history(a, a.sensor_mapping, TAG, db)
    assert set(je_feld) == {("wallbox", "ladezustand"), ("e-auto", "zu_hause")}
    assert je_feld[("e-auto", "zu_hause")].anteile[5] == {auto.id: {"zu_hause": 1.0}}

    async def _kaputt(*_a, **_k):
        raise RuntimeError("Probe")
    monkeypatch.setattr(schreiber, "schreibe_zustands_mitschrift", _kaputt)
    assert await schreiber.schreibe_zustands_mitschrift_sicher(db, a, TAG, je_feld) is None
    assert await schreiber.schreibe_zustands_mitschrift_sicher(db, a, TAG, {}) == 0


async def test_aggregate_day_ruft_die_zustands_mitschrift(db, monkeypatch):
    """Die Tagesaggregation schreibt die Mitschrift nach der Betriebsart-Mitschrift (eigener Einstieg)."""
    from backend.services.energie_profil import aggregator
    from backend.services.energie_profil.source import Source
    from backend.services.kanal import schreiber

    a, _wb, _auto = await _anlage_emob(db, wb_live={"ladezustand": "sensor.wb"})
    gerufen = {}

    async def _hist(anlage, mapping, datum, db_):
        gerufen["hist"] = datum
        return {("wallbox", "ladezustand"): "X"}

    async def _sicher(db_, anlage, datum, je_feld):
        gerufen["sicher"] = (datum, je_feld)
        return 0
    monkeypatch.setattr(_helpers, "_get_zustands_mitschrift_history", _hist)
    monkeypatch.setattr(schreiber, "schreibe_zustands_mitschrift_sicher", _sicher)
    tv = {"serien": [{"key": "netz_a", "kategorie": "netz", "label": "Netz"}],
          "punkte": [{"zeit": f"{h:02d}:00", "werte": {"netz_a": 100.0}} for h in range(24)]}
    await aggregator.aggregate_day(a, TAG, db, source=Source.MANUAL_REPAIR, prefetched_tagesverlauf=tv)
    assert gerufen == {"hist": TAG, "sicher": (TAG, {("wallbox", "ladezustand"): "X"})}


# ═══ 9 · Tag-Detail (K3-7) ════════════════════════════════════════════════════

async def _tag(db, anlage_id, datum=TAG):
    from backend.api.routes.energie_profil.views import get_tag_detail

    return await get_tag_detail(anlage_id, datum, db)


async def test_tag_detail_emob_betrieb(db):
    from backend.services.kanal.schreiber import schreibe_zustands_mitschrift

    a, wb, auto = await _anlage_emob(db, wb_live={"ladezustand": "sensor.wb"},
                                     auto_live={"ladezustand_fahrzeug": "sensor.auto", "zu_hause": "device_tracker.a"})
    wb_verlauf = {"sensor.wb": [(datetime(2026, 6, 9, 22), "not_connected"),
                                (M0 + timedelta(hours=7), "sleep_mode"),
                                (M0 + timedelta(hours=8), "active_mode"),
                                (M0 + timedelta(hours=11, minutes=30), "sleep_mode"),
                                (M0 + timedelta(hours=12), "not_connected")]}
    auto_verlauf = {"sensor.auto": [(datetime(2026, 6, 9, 22), "not_connected"),
                                    (M0 + timedelta(hours=8), "charging"), (M0 + timedelta(hours=10), "complete")],
                    "device_tracker.a": [(datetime(2026, 6, 9, 22), "home"), (M0 + timedelta(hours=14), "not_home")]}
    je_feld = {("wallbox", "ladezustand"): await _ha(db, a, wb_verlauf)}
    je_feld[("e-auto", "ladezustand_fahrzeug")] = await _ha(db, a, auto_verlauf, feld="ladezustand_fahrzeug",
                                                            typ="e-auto")
    je_feld[("e-auto", "zu_hause")] = await _ha(db, a, auto_verlauf, feld="zu_hause", typ="e-auto")
    await schreibe_zustands_mitschrift(db, a, TAG, je_feld, jetzt=datetime(2026, 6, 12))
    await db.commit()
    t = await _tag(db, a.id)
    zeilen = {(z.investition_id, z.feld): z for z in t.emob_betrieb}
    assert set(zeilen) == {(wb.id, "ladezustand"), (auto.id, "ladezustand_fahrzeug"), (auto.id, "zu_hause")}
    w = zeilen[(wb.id, "ladezustand")]
    # Bestandstag (Ende-Raster): Slot 0 = Vortag 23:00 … Slot 23 = 22:00–23:00 ⇒ lädt 08:00–11:30, verbunden
    # 07:00–08:00 und 11:30–12:00, Rest kein Fahrzeug (zählt nicht).
    assert w.stunden == {"laedt": 3.5, "verbunden": 1.5, "wartet": 0.0, "fertig": 0.0}
    assert list(w.stunden) == ["laedt", "verbunden", "wartet", "fertig"]
    assert w.labels == {"laedt": "Lädt", "verbunden": "Verbunden", "wartet": "Wartet", "fertig": "Fertig"}
    assert (w.typ, w.wechsel) == ("wallbox", 1)
    f = zeilen[(auto.id, "ladezustand_fahrzeug")]
    assert f.stunden == {"laedt": 2.0, "laedt_dc": 0.0, "verbunden": 0.0} and f.wechsel is None
    s = zeilen[(auto.id, "zu_hause")]
    assert s.stunden == {"zu_hause": 15.0, "unterwegs": 9.0} and s.labels == {"zu_hause": "Zu Hause",
                                                                               "unterwegs": "Unterwegs"}


async def test_tag_detail_ohne_mitschrift_leer(db):
    a, _wb, _auto = await _anlage_emob(db)
    t = await _tag(db, a.id)
    assert t.emob_betrieb == []
    assert t.model_dump()["emob_betrieb"] == []


async def test_tag_detail_gemessene_null_bleibt(db):
    """Ein Tag nur «kein Fahrzeug»: die Zeile steht mit 0 h (die Karte sagt «Heute kein Betrieb»), Wechsel 0."""
    from backend.services.kanal.schreiber import schreibe_zustands_mitschrift

    a, wb, _auto = await _anlage_emob(db, wb_live={"ladezustand": "sensor.wb"})
    m = await _ha(db, a, {"sensor.wb": [(datetime(2026, 6, 9, 22), "not_connected")]})
    await schreibe_zustands_mitschrift(db, a, TAG, {("wallbox", "ladezustand"): m}, jetzt=datetime(2026, 6, 12))
    await db.commit()
    (z,) = (await _tag(db, a.id)).emob_betrieb
    assert (z.investition_id, z.stunden, z.wechsel) == (wb.id, {"laedt": 0.0, "verbunden": 0.0, "wartet": 0.0,
                                                                 "fertig": 0.0}, 0)


# ═══ 10 · Investition löschen (N-668-Klasse) ═══════════════════════════════════

async def test_investition_loeschen_raeumt_zustand_und_wechsel(db):
    from backend.api.routes.investitionen.crud import _entferne_messreihen
    from backend.services.kanal.schreiber import schreibe_zustands_mitschrift_mqtt

    a, wb, _auto = await _anlage_emob(db)
    for m in range(5, 65, 5):
        db.add(_snap(a.id, wb.id, T0 + m * 60 - 1, "ladezustand", "laedt"))
    await db.commit()
    await schreibe_zustands_mitschrift_mqtt(db, a, datetime.fromtimestamp(T0 + _STUNDE + 600))
    await db.commit()
    assert await _kanalzeilen(db, a.id, "wechsel:") and await _kanalzeilen(db, a.id, "zustand:")
    _snaps, kanaele = await _entferne_messreihen(db, a.id, wb.id)
    await db.commit()
    assert kanaele == len(zk.KANON["ladezustand"]) + 1
    assert (await db.execute(select(Kanal).where(Kanal.anlage_id == a.id))).first() is None
