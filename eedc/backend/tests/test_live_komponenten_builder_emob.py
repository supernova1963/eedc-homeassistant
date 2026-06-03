"""
Akzeptanztests für die Wallbox/E-Auto-Behandlung im Live-Komponenten-Builder.

Hintergrund (#314-Folge, Pool-Asymmetrie-Klasse #290/#298/#318):
1. Geteilter `leistung_w`-Sensor (Wallbox + E-Auto = derselbe Stromfluss aus
   zwei Perspektiven) muss DETERMINISTISCH dedupliziert werden — Wallbox gewinnt
   immer, unabhängig von der Investitions-Reihenfolge. Vorher hing der Dedup an
   der Dict-Reihenfolge.
2. E-Auto OHNE Wallbox (Schuko/Steckerlader) ist ein realer Verbraucher und muss
   in summe_verbrauch + Haushalts-Residual gezählt werden (086cf70f-Prinzip).
3. E-Auto MIT Wallbox (getrennte Sensoren) darf nur einmal zählen — über die
   Wallbox; das E-Auto wird als deren Kind gepoolt.
"""

from __future__ import annotations

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.live_komponenten_builder import build_komponenten


def _anlage() -> Anlage:
    return Anlage(anlagenname="Test", leistung_kwp=5.0, standort_land="DE")


def _inv(typ: str, bez: str) -> Investition:
    return Investition(typ=typ, bezeichnung=bez, parameter={})


# PV-Quelle 3 kW + minimale Einspeisung, damit das Haushalts-Residual gebildet wird
_BASIS = {"pv_gesamt_w": 3000.0, "einspeisung_w": 100.0, "netzbezug_w": None}


def _keys(result) -> set[str]:
    return {k["key"] for k in result["komponenten"]}


def _komp(result, prefix):
    return next((k for k in result["komponenten"] if k["key"].startswith(prefix)), None)


def test_geteilter_sensor_dedup_unabhaengig_von_reihenfolge():
    """Wallbox + E-Auto teilen denselben Sensor → E-Auto wird immer dedupliziert,
    egal in welcher Reihenfolge die Investitionen kommen (Symmetrie)."""
    investitionen = {
        "wb": _inv("wallbox", "Wallbox"),
        "ea": _inv("e-auto", "E-Auto"),
    }
    shared = {"wb": {"leistung_w": "sensor.shared"}, "ea": {"leistung_w": "sensor.shared"}}
    vals = {"wb": {"leistung_w": 1455.0}, "ea": {"leistung_w": 1455.0}}

    # Reihenfolge A: Wallbox zuerst
    res_a = build_komponenten(_anlage(), _BASIS, vals, investitionen, shared)
    # Reihenfolge B: E-Auto zuerst (umgekehrte Dict-Reihenfolge)
    vals_b = {"ea": {"leistung_w": 1455.0}, "wb": {"leistung_w": 1455.0}}
    inv_b = {"ea": investitionen["ea"], "wb": investitionen["wb"]}
    shared_b = {"ea": {"leistung_w": "sensor.shared"}, "wb": {"leistung_w": "sensor.shared"}}
    res_b = build_komponenten(_anlage(), _BASIS, vals_b, inv_b, shared_b)

    # Kein E-Auto-Knoten, Wallbox genau einmal — in beiden Reihenfolgen identisch
    for res in (res_a, res_b):
        assert _komp(res, "eauto_") is None, "E-Auto bei geteiltem Sensor nicht dedupliziert"
        assert _komp(res, "wallbox_") is not None
    assert res_a["summe_verbrauch_kw"] == res_b["summe_verbrauch_kw"]
    # Wallbox zählt einfach (1.455), nicht doppelt
    assert abs(_komp(res_a, "wallbox_")["verbrauch_kw"] - 1.455) < 1e-6


def test_eauto_ohne_wallbox_wird_gezaehlt():
    """E-Auto ohne Wallbox (Schuko) ist realer Verbraucher → in summe_verbrauch
    und als Top-Level-Knoten (ohne parent_key) im Residual."""
    investitionen = {"ea": _inv("e-auto", "E-Auto")}
    live = {"ea": {"leistung_w": "sensor.ea"}}
    vals = {"ea": {"leistung_w": 1455.0}}

    res = build_komponenten(_anlage(), _BASIS, vals, investitionen, live)

    eauto = _komp(res, "eauto_")
    assert eauto is not None
    assert eauto.get("parent_key") is None, "ohne Wallbox darf kein parent_key gesetzt sein"
    # E-Auto-Verbrauch (1.455) ist in summe_verbrauch enthalten
    assert res["summe_verbrauch_kw"] >= 1.455


def test_eauto_mit_wallbox_getrennte_sensoren_nur_einmal():
    """Wallbox + E-Auto mit GETRENNTEN Sensoren → E-Auto wird unter die Wallbox
    gepoolt (parent_key), zählt NICHT zusätzlich in summe_verbrauch."""
    investitionen = {
        "wb": _inv("wallbox", "Wallbox"),
        "ea": _inv("e-auto", "E-Auto"),
    }
    live = {"wb": {"leistung_w": "sensor.wb"}, "ea": {"leistung_w": "sensor.ea"}}
    vals = {"wb": {"leistung_w": 1455.0}, "ea": {"leistung_w": 1455.0}}

    res = build_komponenten(_anlage(), _BASIS, vals, investitionen, live)

    eauto = _komp(res, "eauto_")
    wallbox = _komp(res, "wallbox_")
    assert wallbox is not None
    assert eauto is not None, "E-Auto-Knoten bleibt sichtbar (eigener Sensor)"
    assert eauto.get("parent_key") == wallbox["key"], "E-Auto muss unter Wallbox gepoolt sein"
    # summe_verbrauch enthält die Wallbox-Ladung genau einmal, NICHT zusätzlich
    # die E-Auto-Ladung (sonst Doppelzählung des gleichen Stromflusses).
    haushalt = _komp(res, "haushalt")
    haushalt_kw = haushalt["verbrauch_kw"] if haushalt else 0.0
    # Erwartet: Einspeisung(0.1) + Wallbox(1.455) + Haushalt-Residual, OHNE 2× 1.455
    assert res["summe_verbrauch_kw"] < 0.1 + 1.455 + haushalt_kw + 1.455
