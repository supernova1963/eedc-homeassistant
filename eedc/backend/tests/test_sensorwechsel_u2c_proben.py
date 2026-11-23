"""Sensorwechsel U2 Lauf c «Befund» — Proben zu F12 (Befund «Zählerstand springt», ``ha_zaehlerstand_springt``) und F13
(Einstieg «Zähler getauscht (gleiche Quelle)»: für eine Quelle aus Home Assistant nie ein Eintrag).

Lab-Soll (Lab-Liste Nr. 5, ``lab-werkzeug/geraetetausch-rc/ABLAUF.md``): Zähler mit Rate 1,8 kWh je Stunde seit 08.10., Sprung
+2 001 ⇒ Befund «springt nach oben» (Maß ≈ 46); Rate 2,04, Neubeginn bei 300 ⇒ Befund «beginnt nicht bei 0» (Maß ≈ 6);
Rechenweg F12: +2 001 an Zählern mit 160 / 24 / 6,85 kWh am Tag ⇒ Maß 12,5 / 83 / 292. Nach «Summe anpassen» in HA (die Summe ab
der Stunde um den Sprung gesenkt) ist der Befund weg. Still bleiben: Nachholstunde nach einer Lücke, großer Verbrauch nach
langer Ruhe, junger Zähler, Wärmepumpe im Winter, PV nach Schnee, Rückkehr nach «kurz 0», Paare über eine Wechselstelle.
Keine Probe liest die Uhr.

Schwesterdateien: test_sensorwechsel_u2b_proben.py (Lauf b), test_n586_checker_ha_zaehlersprung.py (Muster «kurz 0 und zurück»),
test_daten_checker_handgriff_wirkt.py (Wirkung des Handgriffs, W-11), test_sensorwechsel_s3b_abfrage.py (Einstieg «Zähler getauscht»).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import backend.models.mqtt_gateway_mapping  # noqa: F401 — Tabelle für die Quellen-Wahl im Einstieg (F13)
from backend.core.berechnungen import zaehlerstand_sprung as zs
from backend.core.berechnungen.zaehlerstand_sprung import NEUBEGINN, SPRUNG, finde_standspruenge

T0 = datetime(2026, 10, 8, 0)
TAUSCH = datetime(2026, 11, 19, 10)
#: U3-K (B2): der Arm «Sprung» meldet am jungen Abschnitt (unter einem Jahr) nur über der Grenze «mehr, als eine Anlage in einer
#: Stunde leisten kann» — die Kern-Proben eines kWh-Felds geben sie mit, wie der Erzeuger (ohne kWp: 100 kWh).
G = zs.MENGE_UNMOEGLICH_MIN
#: … oder mit reifem Bezug: ein Abschnitt, der über ein Jahr zurückreicht.
JAHR = TAUSCH - timedelta(days=400)


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


def _reihe(rate=1.8, *, bis=TAUSCH + timedelta(hours=30), start=1000.0, stand_ab=None, raten=None, ab=T0):
    """``(start_ts, state, sum)`` je Stunde wie HA (``total_increasing``): ``state`` der Zähler, ``sum`` = Σ Zuwächse; fällt der
    Stand (Neubeginn), beginnt HA einen neuen Zyklus ab 0. ``stand_ab``: {Stunde: neuer Stand} (Sprung/Neubeginn in dieser
    Stunde, danach Rate weiter); ``raten``: Rate je Stunde (Funktion der Zeit) statt fester Rate."""
    out, stand, summe = [], start, 0.0
    t = ab
    while t < bis:
        r = raten(t) if raten else rate
        neu = (stand_ab or {}).get(t)
        alt = stand
        stand = (neu + r) if neu is not None else stand + r
        summe += stand if stand < alt * 0.9 else stand - alt
        out.append((_ts(t), stand, summe))
        t += timedelta(hours=1)
    return out


def _sprung(z, wo: datetime, plus: float):
    """+``plus`` ab der Zeile ``wo`` in ``state`` und ``sum`` (Gerätetausch, derselbe Sensor, neuer Zähler höher)."""
    return [(ts, st + plus, su + plus) if ts >= _ts(wo) else (ts, st, su) for ts, st, su in z]


def _wert_angepasst(z, wo: datetime, minus: float):
    """«Summe anpassen» in HA: die Summe ab der Zeile ``wo`` um ``minus`` gesenkt; der Stand bleibt."""
    return [(ts, st, su - minus) if ts >= _ts(wo) else (ts, st, su) for ts, st, su in z]


# ─── Kern: Lab-Soll ────────────────────────────────────────────────────────────────────────────────────────────────


def test_lab_plus_2001_springt_nach_oben():
    z = _sprung(_reihe(1.8), TAUSCH, 2001.0)
    (f,) = finde_standspruenge(z, grenze=G)
    assert (f.start_ts, f.art) == (_ts(TAUSCH), SPRUNG)
    assert f.menge == pytest.approx(2002.8)
    assert f.mass == pytest.approx(2002.8 / (1.8 * 24), rel=1e-6)          # ≈ 46


def test_lab_neubeginn_300_beginnt_nicht_bei_0():
    z = _reihe(2.04, start=5000.0, stand_ab={TAUSCH: 300.0})
    (f,) = finde_standspruenge(z)
    assert (f.start_ts, f.art) == (_ts(TAUSCH), NEUBEGINN)
    assert f.menge == pytest.approx(302.04)                                 # HA zählt den ganzen neuen Stand
    assert f.mass == pytest.approx(302.04 / (2.04 * 24), rel=1e-6)          # ≈ 6,2
    # Ein Neubeginn bei 0 (der neue Zähler zählt ab 0) ist kein Befund: HA zählt nur die Stunde.
    assert finde_standspruenge(_reihe(2.04, start=5000.0, stand_ab={TAUSCH: 0.0})) == []


@pytest.mark.parametrize("tag_kwh,soll", [(160.0, 12.5), (24.0, 83.4), (6.85, 292.1)])
def test_rechenweg_f12_lab_masse(tag_kwh, soll):
    z = _sprung(_reihe(tag_kwh / 24), TAUSCH, 2001.0 - tag_kwh / 24)
    (f,) = finde_standspruenge(z, grenze=G)
    assert f.mass == pytest.approx(soll, abs=0.1)


def test_nach_wert_anpassen_kein_befund():
    z = _wert_angepasst(_sprung(_reihe(1.8), TAUSCH, 2001.0), TAUSCH, 2001.0)
    assert finde_standspruenge(z, grenze=G) == []
    z = _wert_angepasst(_reihe(2.04, start=5000.0, stand_ab={TAUSCH: 300.0}), TAUSCH, 300.5)
    assert finde_standspruenge(z) == []


# ─── Kern: Schwellen (Grenzproben — halbiert oder verdoppelt ist rot) ──────────────────────────────────────────────


@pytest.mark.parametrize("arm,schwelle", [(SPRUNG, 10.0), (NEUBEGINN, 3.0)])
def test_schwelle_je_arm(arm, schwelle):
    """Die Schwellen aus M4 als Zahlen (nicht aus dem Modul gelesen — eine geänderte Schwelle ist hier rot)."""
    tag = 1.0 * 24
    for faktor, soll in ((0.97, []), (1.03, [arm])):
        menge = schwelle * faktor * tag
        z = (_sprung(_reihe(1.0), TAUSCH, menge - 1.0) if arm == SPRUNG
             else _reihe(1.0, start=5000.0, stand_ab={TAUSCH: menge - 1.0}))
        assert [f.art for f in finde_standspruenge(z, grenze=G)] == soll, (faktor, menge)


def test_sprung_form_unter_der_sprung_schwelle_ist_kein_neubeginn():
    """Ein Sprung nach oben mit dem Maß 5 (über der Schwelle des Neubeginns, unter der des Sprungs) bleibt still — nur ein
    fallender Stand macht die niedrigere Schwelle gültig."""
    assert finde_standspruenge(_sprung(_reihe(1.0), TAUSCH, 5 * 24.0), grenze=G) == []


def test_ungleiche_zuwaechse_sind_kein_sprung():
    """Δ sum ≠ Δ state (etwa ein Zähler, dessen Summe HA anders führt): kein Sprung, auch bei großer Menge."""
    z = _sprung(_reihe(1.8), TAUSCH, 2001.0)
    z = [(ts, st - (500.0 if ts >= _ts(TAUSCH) else 0.0), su) for ts, st, su in z]
    assert finde_standspruenge(z, grenze=G) == []


# ─── Kern: still bleiben ───────────────────────────────────────────────────────────────────────────────────────────


def test_junger_zaehler_meldet_nur_ueber_der_grenze():
    """U3-K (B2, Bauplan Nr. 158): am jungen Abschnitt meldet der Arm «Sprung» nur über der Grenze (b) — +2 001 ja, ohne Grenze
    (Stand-Zähler in m³) oder mit +50 nein; ohne einen Tag mit Zuwachs im Bezug nie."""
    jung = [z for z in _sprung(_reihe(1.8), TAUSCH, 2001.0) if z[0] >= _ts(TAUSCH - timedelta(days=10))]
    assert [f.art for f in finde_standspruenge(jung, grenze=G)] == [SPRUNG]
    assert finde_standspruenge(jung) == []
    klein = [z for z in _sprung(_reihe(1.8), TAUSCH, 50.0) if z[0] >= _ts(TAUSCH - timedelta(days=10))]
    assert finde_standspruenge(klein, grenze=G) == []
    ohne_bezug = [z for z in _sprung(_reihe(1.8), TAUSCH, 2001.0) if z[0] >= _ts(TAUSCH - timedelta(hours=3))]
    # U3-K3 (K2-B5, Bauplan Nr. 163, neue Erwartung): über der Grenze meldet der Arm «Sprung» auch ohne Tag mit Zuwachs im
    # Bezug (bis U3-K2: still) — Maß 0
    assert [(f.art, f.mass) for f in finde_standspruenge(ohne_bezug, grenze=G)] == [(SPRUNG, 0.0)]


def test_wallbox_11_kwh_nach_30_tagen_ruhe_still():
    """30 Tage lang täglich 1 kWh um 18 Uhr, dann 30 Tage Ruhe, dann 11 kWh in einer Stunde: das Maß teilt sich durch die
    Ruhe (11 / (1 × 30) ≈ 0,4). Gegenprobe: dieselbe Stunde ohne Ruhe (ein Rinnsal hält den Zähler wach) wäre ein Fund."""
    ab = JAHR                                   # U3-K: ein Jahr Bezug, damit die Gegenprobe ohne Grenze meldet (reif)

    def raten(rinnsal):
        def r(t):
            if t < TAUSCH - timedelta(days=30):
                return 1.0 if t.hour == 18 else 0.0
            return 11.0 if t == TAUSCH else rinnsal
        return r
    assert finde_standspruenge(_reihe(raten=raten(0.0), ab=ab)) == []
    assert [f.art for f in finde_standspruenge(_reihe(raten=raten(0.0001), ab=ab))] == [SPRUNG]


def test_nachholstunde_nach_20_stunden_luecke_still():
    z = [r for r in _reihe(1.8) if not (_ts(TAUSCH - timedelta(hours=20)) <= r[0] < _ts(TAUSCH))]
    assert finde_standspruenge(z) == []


def test_waermepumpe_im_winter_und_pv_nach_schnee_still():
    """Ein Jahr Geschichte: im Sommer 0,1 kWh am Tag, im Winter bis 30; nach dem Sommer die erste kalte Stunde mit 4 kWh —
    das Bezugsfenster (ein Jahr) kennt den Winter. PV: drei Wochen Schnee (0,05 je Stunde), dann eine Sonnenstunde 6 kWh."""
    beginn = datetime(2025, 10, 1)

    def wp(t):
        return 1.25 if t < datetime(2026, 4, 1) else (0.004 if t < datetime(2026, 10, 1) else 4.0)
    z = []
    stand, summe, t = 100.0, 0.0, beginn
    while t < datetime(2026, 10, 2):
        r = wp(t)
        stand += r
        summe += r
        z.append((_ts(t), stand, summe))
        t += timedelta(hours=1)
    assert finde_standspruenge(z) == []

    def pv(t):
        if t < datetime(2026, 11, 1):
            return 2.0 if 9 <= t.hour < 16 else 0.0
        if t < datetime(2026, 11, 22, 12):
            return 0.05 if 9 <= t.hour < 16 else 0.0
        return 6.0
    z, stand, t = [], 100.0, datetime(2026, 1, 1)
    while t < datetime(2026, 11, 22, 14):
        stand += pv(t)
        z.append((_ts(t), stand, stand - 100.0))
        t += timedelta(hours=1)
    assert finde_standspruenge(z) == []


def test_stand_zaehler_zaehlt_den_stand():
    """Stand-Zähler (Gas): eedc zählt Δ ``state`` — ein Sprung nach oben ist ein Fund, ein fallender Stand nie (dort zählt eedc
    keinen Zuwachs; den Bruch nennt ``zaehlerstand_reihe_bruch``)."""
    z = _sprung(_reihe(0.12, ab=JAHR), TAUSCH, 2001.0)            # U3-K: Stand-Zähler ohne (b) — reifer Bezug
    (f,) = finde_standspruenge(z, stand=True)
    assert f.art == SPRUNG and f.menge == pytest.approx(2001.12)
    assert finde_standspruenge(_reihe(0.12, start=5000.0, stand_ab={TAUSCH: 300.0}, ab=JAHR), stand=True) == []


def test_ausgenommen_bleibt_still():
    z = _sprung(_reihe(1.8), TAUSCH, 2001.0)
    assert finde_standspruenge(z, ausgenommen={_ts(TAUSCH)}) == []


# ─── Erzeuger: Abschnitte, «kurz 0 und zurück», Texte, Aktion ──────────────────────────────────────────────────────


def _abfrage(key, art, abschnitte, einheit="kWh"):
    """Zeilen wie ``standsprung._SQL``: je Abschnitt (gueltig_ab, statistic_id, Zeilen)."""
    out = []
    for i, (sid, z) in enumerate(abschnitte):
        out += [(7, key, art, einheit, z[0][0] - 3600 * (i + 1), sid, ts, st, su) for ts, st, su in z]
    return out


def test_paar_ueber_eine_wechselstelle_ist_kein_sprung():
    from backend.services.daten_checker.datenquelle.standsprung import finde

    z = _reihe(1.8)
    alt = [r for r in z if r[0] < _ts(TAUSCH)]
    neu = [(ts, st + 3000.0, su + 3000.0) for ts, st, su in z if ts >= _ts(TAUSCH)]
    assert finde(_abfrage("basis:netzbezug", "sum", [("sensor.alt", alt), ("sensor.neu", neu)])) == []
    # Derselbe Sprung in EINEM Abschnitt ist einer.
    assert len(finde(_abfrage("basis:netzbezug", "sum", [("sensor.alt", alt + neu)]))) == 1


def test_kurz_null_und_zurueck_ueberlaesst_er_ha_zaehlersprung():
    from backend.services.daten_checker.datenquelle.standsprung import finde

    z = _reihe(1.8)
    i = next(k for k, r in enumerate(z) if r[0] == _ts(TAUSCH))
    # Stand 0 in drei Stunden, dann zurück: HA zählt die Rückkehr als ganzen Stand (Phantom, `ha_zaehlersprung`).
    phantom, summe, zuvor = [], 0.0, None
    for k, (ts, st, _su) in enumerate(z):
        s = 0.0 if i - 3 <= k < i else st
        if zuvor is not None:
            summe += s if s < zuvor * 0.9 else s - zuvor
        zuvor = s
        phantom.append((ts, s, summe))
    assert finde(_abfrage("basis:netzbezug", "sum", [("sensor.x", phantom)])) == []


async def _anlage_mit(db, abschnitte, *, key="basis:netzbezug", art="sum", einheit="kWh"):
    from backend.models.anlage import Anlage
    from backend.models.kanal import FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik

    a = Anlage(anlagenname="U2c", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    k = Kanal(anlage_id=a.id, key=key, einheit=einheit, art=art)
    db.add(k)
    await db.flush()
    for sid, z in abschnitte:
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=z[0][0], familie=FAMILIE_SPIEGEL, statistic_id=sid, offset=0.0))
        db.add_all([KanalStatistik(kanal_id=k.id, start_ts=ts, state=st, sum=su, familie=FAMILIE_SPIEGEL) for ts, st, su in z])
    await db.commit()
    return a


async def _pruefe(db, a):
    from backend.services.daten_checker.datenquelle.standsprung import ZaehlerstandSpringtChecks

    class _P(ZaehlerstandSpringtChecks):
        def __init__(self, d):
            self.db = d

    return await _P(db)._check_ha_zaehlerstand_springt(a)


async def test_befund_mengen_zaehler_nennt_feld_sensor_stunde_menge_und_aktion(db):
    from backend.tests.werkzeug_befund import befund_op, befund_params

    a = await _anlage_mit(db, [("sensor.netz_bezug", _sprung(_reihe(1.8), TAUSCH, 2001.0))])
    (e,) = await _pruefe(db, a)
    assert (e.code, e.schwere.value if hasattr(e.schwere, "value") else e.schwere) == ("ha_zaehlerstand_springt", "warning")
    assert "Anlage · Netzbezug (sensor.netz_bezug) am 19.11.2026, Stunde ab 10:00: +2.002,8 kWh" in e.details
    assert "der Stand springt nach oben" in e.details and "„Summe anpassen“" in e.details
    assert (befund_op(e), befund_params(e)) == ("spiegel_abgleich_tag", {"datum": "2026-11-19"})
    assert e.werte["funde"][0]["sensor"] == "sensor.netz_bezug" and e.werte["funde"][0]["art"] == SPRUNG


async def test_befund_stand_zaehler_auskunft_mit_den_wegen_nach_e2(db):
    jahr = list({ts: (ts, st, su) for ts, st, su in _sprung(_reihe(0.12, ab=JAHR), TAUSCH, 2001.0)}.values())  # Frühjahr: 02:00 = 03:00
    a = await _anlage_mit(db, [("sensor.gas", jahr)], key="inv:9:zaehlerstand",
                          art="stand", einheit="m³")
    (e,) = await _pruefe(db, a)
    assert (e.schwere.value if hasattr(e.schwere, "value") else e.schwere) == "info"
    assert e.action is None and e.klasse == "auskunft"
    assert "+2.001,1 m³" in e.details and "„Bisherige Werte bleiben“" in e.details
    assert "Stilllegungsdatum" in e.details and "Summe anpassen“ in Home Assistant ändert daran nichts" in e.details  # Nachtrag G: Wortlaut «daran»


async def test_nach_wert_anpassen_und_uebernahme_kein_befund(db):
    z = _wert_angepasst(_sprung(_reihe(1.8), TAUSCH, 2001.0), TAUSCH, 2001.0)
    assert await _pruefe(db, await _anlage_mit(db, [("sensor.netz_bezug", z)])) == []


async def test_ohne_spiegel_kein_befund(db):
    from backend.models.anlage import Anlage

    a = Anlage(anlagenname="leer", leistung_kwp=1.0)
    db.add(a)
    await db.commit()
    assert await _pruefe(db, a) == []


# ─── F13: Einstieg «Zähler getauscht (gleiche Quelle)» ──────────────────────────────────────────────────────────────


async def _gas_aus_ha(db):
    """Verbrauchszähler (Gas) mit Zählerstand aus Home Assistant, Kanal-Art ``stand`` mit Spiegel seit 01.10.2026."""
    from datetime import date

    from backend.models.investition import Investition
    from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
    from backend.tests.test_sensorwechsel_s1_verzeichnen import _anlage

    a = await _anlage(db, {"investitionen": {"9": {"felder": {"zaehlerstand": {"strategie": "sensor",
                                                                                 "sensor_id": "sensor.gas"}}}}},
                      werte=("inv:9:zaehlerstand",))
    db.add(Investition(id=9, anlage_id=a.id, typ="sonstiges", bezeichnung="Gas", anschaffungsdatum=date(2024, 1, 1)))
    k = Kanal(anlage_id=a.id, key="inv:9:zaehlerstand", einheit="m³", art="stand")
    db.add(k)
    await db.flush()
    t0 = datetime(2026, 10, 1)
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=_ts(t0), familie="spiegel", statistic_id="sensor.gas", offset=0.0))
    for h in range(24 * 40):
        db.add(KanalStatistik(kanal_id=k.id, start_ts=_ts(t0 + timedelta(hours=h)), state=100.0 + 0.1 * h, sum=0.1 * h,
                              familie="spiegel"))
    await db.commit()
    return a.id


async def test_f13_stand_zaehler_aus_ha_traegt_nie_ein_und_nennt_die_zwei_wege(db):
    from backend.api.routes.sensorwechsel import ZaehlerGetauschtRequest, pruefe_zaehler_getauscht, zaehler_getauscht
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg
    from backend.tests.test_sensorwechsel_s1_verzeichnen import _zeilen

    aid = await _gas_aus_ha(db)
    req = ZaehlerGetauschtRequest(getauscht_am=datetime(2026, 10, 20, 9, 30))
    p = await pruefe_zaehler_getauscht(aid, "inv_energy_9_zaehlerstand", req, db)
    assert (p["weg"], p["eintragen"], p["saetze"]) == ("home_assistant", False, [zg.SATZ_HA_STAND])
    assert "„Bisherige Werte bleiben“" in zg.SATZ_HA_STAND and "Stilllegungsdatum" in zg.SATZ_HA_STAND
    r = await zaehler_getauscht(aid, "inv_energy_9_zaehlerstand", req, db)
    assert r["eingetragen"] is False and await _zeilen(db, aid) == []


async def test_f13_mengen_zaehler_aus_ha_wie_bisher(db):
    """Mengen-Zähler aus Home Assistant mit Spiegel: Weg in Home Assistant, Satz wie bisher (``SATZ_HA``)."""
    from backend.api.routes.sensorwechsel import ZaehlerGetauschtRequest, pruefe_zaehler_getauscht
    from backend.services.zuordnung_wechsel import zaehler_getauscht as zg
    from backend.tests.test_sensorwechsel_s1_verzeichnen import NETZ, _anlage

    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}})
    await db.commit()
    p = await pruefe_zaehler_getauscht(a.id, NETZ, ZaehlerGetauschtRequest(), db)
    assert (p["weg"], p["eintragen"], p["saetze"]) == ("home_assistant", False, [zg.SATZ_HA])


async def test_f13_weg_nach_der_quelle_zur_zeit_des_tauschs(db):
    """Heute aus Home Assistant (noch ohne Kanal), zur Zeit des Tauschs aber MQTT (Wechsel MQTT → HA danach): der Weg folgt der
    Quelle zur Zeit — MQTT trägt wie bisher ein (vorher galt die heutige Quelle: Weg in Home Assistant)."""
    from backend.api.routes.sensorwechsel import ZaehlerGetauschtRequest, pruefe_zaehler_getauscht
    from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG, HERKUNFT_WECHSEL, ZuordnungWechsel
    from backend.services.zuordnung_wechsel.quelle import standard_quelle
    from backend.services.zuordnung_wechsel.zeitpunkt import vergiss
    from backend.tests.test_sensorwechsel_s1_verzeichnen import NETZ, NETZ_KEY, _anlage

    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}})
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=NETZ_KEY, erklaert_ts=datetime(2026, 10, 5, 8),
                            ab_ts=datetime(2026, 10, 5, 9), vorher=standard_quelle(NETZ_KEY),
                            nachher={"art": "ha", "entity_id": "sensor.a"}, grund=GRUND_FORTSETZUNG,
                            herkunft=HERKUNFT_WECHSEL))
    await db.commit()
    vergiss(db, a.id)
    frueh = await pruefe_zaehler_getauscht(a.id, NETZ, ZaehlerGetauschtRequest(getauscht_am=datetime(2026, 10, 1, 9)), db)
    assert (frueh["weg"], frueh["eintragen"]) == ("fortsetzung", True)
    spaet = await pruefe_zaehler_getauscht(a.id, NETZ, ZaehlerGetauschtRequest(getauscht_am=datetime(2026, 10, 6, 9)), db)
    assert (spaet["weg"], spaet["eintragen"]) == ("home_assistant", False)
