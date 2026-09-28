"""N-575: Ein V2H-Auto hinter einer Wallbox — die Semantik hängt an der erfassten
Topologie, die Buchung am Messpunkt (Live-Bilanz, `live_komponenten_builder`).

**Der Defekt.** Ein E-Auto mit `v2h_faehig` ist im Live-Builder bidirektional
und wurde im Bidirektional-Zweig abgefangen — **vor** dem `else`-Zweig, in dem
allein die Wallbox-Poolung sitzt. Seine Ladung zählte deshalb neben der Wallbox
ein zweites Mal und als Batterie-Ladung (EV-Quote 30 statt 100 %), und der
Wallbox-Zweig selbst war vorzeichenblind: eine gemessene V2H-Entladung an der
Wallbox erschien als **Phantom-Verbrauch** (im häufigsten Aufbau V-A „nur die
Wallbox misst": Autarkie 67 statt 86 %, Haushalt 0 statt 3,5 kW).

**Die Regel** (Vorlage N-575 Fassung 2, §2):

* **R1 Laden** — mit einer ERFASSTEN Wallbox ist die Heimladung Hausverbrauch,
  nie Batterie-Ladung. Liefert die Wallbox live, bucht sie; sonst bucht das Auto
  als gewöhnlicher Verbraucher (Failover). Ohne Wallbox-Investition: F-69.
* **R2 Entladen** — die Batterie-Rolle verdient nur die gemessene Entladung,
  und sie wird **einmal** gebucht: meldet die Wallbox sie, bucht die Wallbox, und
  das Auto zeigt nur seine Richtung. Dazu schließt das Residual ein nur
  zeigendes Kind aus den Quellen aus (symmetrisch zur Senken-Regel).
* **R3** — vorzeichentreu nur bei einem V2H-Auto im Bestand; jede andere Anlage
  rechnet bitgleich zu vorher, auch mit invertiertem Wallbox-Sensor (V-E).
* **R4** — `wallbox_keys` entsteht richtungsunabhängig.

⚠ **Fünf Bildungsstellen, fünf Gegenproben** (N-274-Bauform, Protokoll im
Baubericht `opus-berichte/N575-BAU.md`): R1-Ladeteil (Rolle) · Wallbox-Vorzeichen ·
`wallbox_entlaedt`-Ausschluss · Residual-Ausschluss · R1-Failover. Die Proben
sind deshalb so geschnitten, dass jede Stelle eine eigene rote Probe hat — die
5b-Aussagen stehen in getrennten Tests, ebenso EV-Quote und Summe bei V-C.

**Grenzfälle, bewusst NICHT gebaut** (Vorlage §3 B3, N3):

* Zwei entladende V2H-Autos bei **einer** negativen Wallbox — beide zeigen nur,
  die Wallbox bucht die Summe; wer entlädt, weiß die Live-Bilanz nicht.
* Ein transienter Richtungswechsel innerhalb eines Polls (Wallbox schon
  negativ, Auto noch ladend) — geerbte Eigenschaft der Wallbox-Poolung: das
  ladende Kind bucht nicht, die Wallbox bucht die Entladung; der nächste Poll
  ist wieder konsistent.

⛔ **Nicht Gegenstand dieser Datei:** der Live-Tagesverlauf derselben Seite
(`live_tagesverlauf_service.py`, Senken-Betrag) zeichnet eine Wallbox-Entladung
weiterhin als Senke — bewusst nicht mitgefixt (Entscheid 28.09.). Die Tages-/
Snapshot-Ebene kennt V2H weiterhin nicht (#110).
"""

from __future__ import annotations

import pytest

from backend.models import Investition
from backend.services.live_komponenten_builder import build_komponenten
from backend.tests import factories


def _wallbox() -> Investition:
    return Investition(typ="wallbox", bezeichnung="Wallbox", parameter={})


def _eauto(*, v2h: bool = True) -> Investition:
    return Investition(
        typ="e-auto",
        bezeichnung="Ioniq 5" if v2h else "Zoe",
        parameter={"v2h_faehig": True} if v2h else {},
    )


def _lauf(*, inv_values: dict, investitionen: dict, live_map: dict,
          pv_w: float, einspeisung_w: float = 0.0,
          netzbezug_w: float = 0.0) -> dict:
    res = build_komponenten(
        factories.mach_anlage(anlagenname="V2H-WB", standort_land="DE"),
        {"pv_gesamt_w": pv_w, "einspeisung_w": einspeisung_w,
         "netzbezug_w": netzbezug_w},
        inv_values, investitionen, live_map,
    )
    return {
        "res": res,
        "gauges": {g["key"]: g["wert"] for g in res["gauges"]},
        "komps": {k["key"]: k for k in res["komponenten"]},
    }


_GETRENNT = {"wb": {"leistung_w": "sensor.wb"}, "auto": {"leistung_w": "sensor.auto"}}
_GETEILT = {"wb": {"leistung_w": "sensor.x"}, "auto": {"leistung_w": "sensor.x"}}


def _beide(*, wb_w, auto_w, v2h: bool = True, live_map=_GETRENNT, **basis) -> dict:
    """Wallbox UND Auto liefern einen Wert (getrennte oder geteilte Entity)."""
    return _lauf(
        inv_values={"wb": {"leistung_w": wb_w}, "auto": {"leistung_w": auto_w}},
        investitionen={"wb": _wallbox(), "auto": _eauto(v2h=v2h)},
        live_map=live_map, **basis,
    )


def _nur_wallbox(*, wb_w, **basis) -> dict:
    """Plan 1.4a — der häufigste Aufbau: die Wallbox misst, das Auto meldet nur SoC."""
    return _lauf(
        inv_values={"wb": {"leistung_w": wb_w}, "auto": {}},
        investitionen={"wb": _wallbox(), "auto": _eauto()},
        live_map={"wb": {"leistung_w": "sensor.wb"}, "auto": {}}, **basis,
    )


def _gestalt(lauf: dict) -> dict:
    """Die ganze sichtbare Aussage: Summen, Gauges, Komponenten (Wert + Parent)."""
    res = lauf["res"]
    return {
        "summe_erzeugung_kw": res["summe_erzeugung_kw"],
        "summe_verbrauch_kw": res["summe_verbrauch_kw"],
        "pv_total_w": res["pv_total_w"],
        "gauges": lauf["gauges"],
        "komps": {
            key: (k.get("erzeugung_kw"), k.get("verbrauch_kw"), k.get("parent_key"))
            for key, k in lauf["komps"].items()
        },
    }


# ── R1 Laden: die Wallbox bucht, das Auto zeigt ─────────────────────────────

def test_fall1_ladung_hinter_wallbox_ist_eigenverbrauch():
    """PV 10 · Wallbox 7 · Auto 7 (getrennte Sensoren) · Haus 3, keine Einspeisung.

    Richtig: die 7 kW zählen einmal (Wallbox) und als Verbrauch ⇒ Σ Verbrauch
    7 + Haushalt 3 = **10,0**, EV **100 %**. Vorher: 17,0 und 30 % (das Auto
    buchte ein zweites Mal und als Batterie-Ladung).
    """
    lauf = _beide(wb_w=7000.0, auto_w=7000.0, pv_w=10000.0)
    assert lauf["res"]["summe_verbrauch_kw"] == pytest.approx(10.0)
    assert lauf["gauges"]["eigenverbrauch"] == pytest.approx(100, abs=0.5)
    assert lauf["gauges"]["autarkie"] == pytest.approx(100, abs=0.5)
    auto = lauf["komps"]["eauto_auto"]
    assert (auto["erzeugung_kw"], auto["verbrauch_kw"]) == (None, 7.0)
    assert auto["parent_key"] == "wallbox_wb"
    assert lauf["komps"]["wallbox_wb"]["verbrauch_kw"] == pytest.approx(7.0)
    assert lauf["komps"]["haushalt"]["verbrauch_kw"] == pytest.approx(3.0)


def test_fall2_ladung_mit_einspeisung():
    """Wie Fall 1, PV 12 und 2 kW Einspeisung ⇒ EV (12 − 2) / 12 = **83 %** (vorher 25 %)."""
    lauf = _beide(wb_w=7000.0, auto_w=7000.0, pv_w=12000.0, einspeisung_w=2000.0)
    assert lauf["gauges"]["eigenverbrauch"] == pytest.approx(83, abs=0.5)
    assert lauf["res"]["summe_verbrauch_kw"] == pytest.approx(12.0)


# ── R1 Failover: Wallbox erfasst, aber ohne Live-Wert ───────────────────────

def _vc() -> dict:
    return _lauf(
        inv_values={"auto": {"leistung_w": 7000.0}},
        investitionen={"wb": _wallbox(), "auto": _eauto()},
        live_map={"auto": {"leistung_w": "sensor.auto"}},
        pv_w=10000.0,
    )


def test_vc_semantik_haengt_nicht_am_sensor_uptime():
    """V-C: die Wallbox ist erfasst, liefert aber gerade nichts; das Auto misst 7 kW.

    Die Heimladung bleibt Hausverbrauch ⇒ EV **100 %** (vorher 30 %). Sonst
    flackerte die EV-Gauge im 5-s-Takt, sobald der Wallbox-Sensor ausfällt.
    """
    assert _vc()["gauges"]["eigenverbrauch"] == pytest.approx(100, abs=0.5)


def test_vc_auto_bucht_im_failover():
    """V-C: ohne Live-Wallbox bucht das Auto als gewöhnlicher Verbraucher.

    Σ Verbrauch = Auto 7 + Haushalt 3 = **10,0** — ein Auto, das nur zeigte,
    ließe 3,0 stehen. Das unterscheidet R1 messbar von Fassung 1.
    """
    lauf = _vc()
    assert lauf["res"]["summe_verbrauch_kw"] == pytest.approx(10.0)
    auto = lauf["komps"]["eauto_auto"]
    assert auto["verbrauch_kw"] == pytest.approx(7.0)
    assert auto.get("parent_key") is None
    assert lauf["komps"]["haushalt"]["verbrauch_kw"] == pytest.approx(3.0)


# ── R2 Entladen: die Wallbox ist die Quelle ─────────────────────────────────

def test_va_leitprobe_nur_wallbox_misst_die_entladung():
    """V-A (Leitprobe, häufigster Aufbau): nur die Wallbox misst, −2 kW · PV 1 · Bezug 0,5.

    Richtig: die Wallbox ist Quelle mit Batterie-Rolle ⇒ Eigenverbrauch 1 + 2 = 3,
    gesamt 3,5 ⇒ Autarkie **86 %**, Haushalt **3,5**, kein Verbrauch an der
    Wallbox. Vorher: 2,0 kW Phantom-Verbrauch, Autarkie 67 %, Haushalt 0.
    """
    lauf = _nur_wallbox(wb_w=-2000.0, pv_w=1000.0, netzbezug_w=500.0)
    wb = lauf["komps"]["wallbox_wb"]
    assert wb["erzeugung_kw"] == pytest.approx(2.0)
    assert wb["verbrauch_kw"] is None
    assert lauf["gauges"]["autarkie"] == pytest.approx(86, abs=0.5)
    assert lauf["komps"]["haushalt"]["verbrauch_kw"] == pytest.approx(3.5)
    assert lauf["res"]["summe_erzeugung_kw"] == pytest.approx(3.5)
    assert lauf["res"]["summe_verbrauch_kw"] == pytest.approx(3.5)


def test_vd_geteilter_sensor_entladung():
    """V-D: Wallbox und Auto teilen die Entity, Entladung −2 kW.

    Der Dedup nimmt dem Auto den Wert (Wallbox-Priorität) — die Wallbox bucht
    als Quelle ⇒ Autarkie **86 %**, Haushalt **3,5**. Vorher: Phantom-Verbrauch.
    """
    lauf = _beide(wb_w=-2000.0, auto_w=-2000.0, live_map=_GETEILT,
                  pv_w=1000.0, netzbezug_w=500.0)
    assert "eauto_auto" not in lauf["komps"]
    assert lauf["komps"]["wallbox_wb"]["erzeugung_kw"] == pytest.approx(2.0)
    assert lauf["gauges"]["autarkie"] == pytest.approx(86, abs=0.5)
    assert lauf["komps"]["haushalt"]["verbrauch_kw"] == pytest.approx(3.5)


def _5b() -> dict:
    return _beide(wb_w=-2000.0, auto_w=-2000.0, pv_w=1000.0, netzbezug_w=500.0)


def test_5b_entladung_steht_genau_einmal_in_der_erzeugung():
    """5b: Auto −2 und Wallbox −2 (getrennte Sensoren) sind EIN Fluss.

    `summe_erzeugung` = PV 1 + Entladung 2 + Bezug 0,5 = **3,5** — die 2 kW
    **genau einmal**. Bucht das Auto mit, stünden dort 5,5.
    """
    assert _5b()["res"]["summe_erzeugung_kw"] == pytest.approx(3.5)


def test_5b_haushalt_ist_das_residual_ohne_doppelte_quelle():
    """5b: Haushalt = Quellen 3,5 − Senken 0 = **3,5** (vorher 1,5; ohne Residual-Regel 5,5)."""
    lauf = _5b()
    assert lauf["komps"]["haushalt"]["verbrauch_kw"] == pytest.approx(3.5)
    assert lauf["res"]["summe_verbrauch_kw"] == pytest.approx(3.5)


def test_5b_autarkie():
    """5b: Eigenverbrauch 1 + 2 = 3, gesamt 3,5 ⇒ **86 %** (doppelt gebucht: 91 %)."""
    assert _5b()["gauges"]["autarkie"] == pytest.approx(86, abs=0.5)


def test_5b_wallbox_bucht_das_auto_zeigt_die_richtung():
    """5b: die Wallbox ist Quelle, das Auto behält sein `erzeugung_kw` als Kind (Plan 1.4a)."""
    lauf = _5b()
    wb = lauf["komps"]["wallbox_wb"]
    assert (wb["erzeugung_kw"], wb["verbrauch_kw"]) == (2.0, None)
    auto = lauf["komps"]["eauto_auto"]
    assert (auto["erzeugung_kw"], auto["verbrauch_kw"]) == (2.0, None)
    assert auto["parent_key"] == "wallbox_wb"


def test_5a_wallbox_meldet_null_das_auto_bucht_wie_f69():
    """5a: Wallbox 0 W, Auto −2 kW — keine negative Wallbox, also bucht das Auto mit Rolle.

    Autarkie **86 %**, Haushalt **3,5** — wie vor N-575 (der Fall war richtig).
    """
    lauf = _beide(wb_w=0.0, auto_w=-2000.0, pv_w=1000.0, netzbezug_w=500.0)
    assert lauf["gauges"]["autarkie"] == pytest.approx(86, abs=0.5)
    assert lauf["komps"]["haushalt"]["verbrauch_kw"] == pytest.approx(3.5)
    assert lauf["res"]["summe_erzeugung_kw"] == pytest.approx(3.5)


# ── R3 Gegenproben: bitgleich zum Stand vor N-575 ───────────────────────────
#
# Die Sollwerte sind die Ausgabe des Builders auf HEAD `8fabb088` (vor N-575),
# gemessen am 28.09. mit dem Vergleichsskript des Bauberichts — hier als
# Literal festgehalten, damit sie nicht aus dem neuen Code abgeleitet werden.

_LADUNG_BITGLEICH_GAUGES = {
    "netz": 0, "pv_leistung": 100.0, "autarkie": 100.0, "eigenverbrauch": 100.0,
}
_PV10 = (10.0, None, None)
_NETZ0 = (None, None, None)
_HAUS3 = (None, 3.0, None)


def test_vb_laden_nur_wallbox_bitgleich():
    """V-B: nur die Wallbox misst, Ladung 7 kW — war richtig und bleibt es."""
    lauf = _nur_wallbox(wb_w=7000.0, pv_w=10000.0)
    assert _gestalt(lauf) == {
        "summe_erzeugung_kw": 10.0, "summe_verbrauch_kw": 10.0, "pv_total_w": 10000.0,
        "gauges": _LADUNG_BITGLEICH_GAUGES,
        "komps": {"wallbox_wb": (None, 7.0, None), "pv_gesamt": _PV10,
                  "netz": _NETZ0, "haushalt": _HAUS3},
    }


def test_geteilter_sensor_laden_bitgleich():
    """Fall 4: geteilte Entity, Ladung — der Dedup fängt es, wie vorher."""
    lauf = _beide(wb_w=7000.0, auto_w=7000.0, live_map=_GETEILT, pv_w=10000.0)
    assert _gestalt(lauf) == {
        "summe_erzeugung_kw": 10.0, "summe_verbrauch_kw": 10.0, "pv_total_w": 10000.0,
        "gauges": _LADUNG_BITGLEICH_GAUGES,
        "komps": {"wallbox_wb": (None, 7.0, None), "pv_gesamt": _PV10,
                  "netz": _NETZ0, "haushalt": _HAUS3},
    }


def test_ohne_v2h_bitgleich():
    """Fall 3: dasselbe Auto ohne `v2h_faehig` — gewöhnliches Kind der Wallbox, wie vorher."""
    lauf = _beide(wb_w=7000.0, auto_w=7000.0, v2h=False, pv_w=10000.0)
    assert _gestalt(lauf) == {
        "summe_erzeugung_kw": 10.0, "summe_verbrauch_kw": 10.0, "pv_total_w": 10000.0,
        "gauges": _LADUNG_BITGLEICH_GAUGES,
        "komps": {"wallbox_wb": (None, 7.0, None),
                  "eauto_auto": (None, 7.0, "wallbox_wb"),
                  "pv_gesamt": _PV10, "netz": _NETZ0, "haushalt": _HAUS3},
    }


def test_ve_invertierter_wallbox_sensor_ohne_v2h_bitgleich():
    """V-E: kein V2H-Auto im Bestand, Wallbox-Sensor liefert −7000 (invertiert angeschlossen).

    Der Betrag bleibt der Schutz: 7 kW Verbrauch, EV 100 % — genau wie vorher.
    Vorzeichentreu wird der Wallbox-Zweig nur im V2H-Haushalt (R3).
    """
    lauf = _lauf(
        inv_values={"wb": {"leistung_w": -7000.0}},
        investitionen={"wb": _wallbox(), "zoe": _eauto(v2h=False)},
        live_map={"wb": {"leistung_w": "sensor.wb"}},
        pv_w=10000.0,
    )
    assert _gestalt(lauf) == {
        "summe_erzeugung_kw": 10.0, "summe_verbrauch_kw": 10.0, "pv_total_w": 10000.0,
        "gauges": _LADUNG_BITGLEICH_GAUGES,
        "komps": {"wallbox_wb": (None, 7.0, None), "pv_gesamt": _PV10,
                  "netz": _NETZ0, "haushalt": _HAUS3},
    }
