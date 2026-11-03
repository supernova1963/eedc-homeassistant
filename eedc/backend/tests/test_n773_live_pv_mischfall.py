"""N-773 (3.11.2026) — Live «PV heute/gestern»: je Sensor seine Messung, auch im Mischfall.

Standalone:

    eedc/backend/venv/bin/python -m pytest backend/tests/test_n773_live_pv_mischfall.py -q

**Der Befund.** ``live_history_service._pv_zaehler_kwh`` zählte, sobald EIN Erzeuger einen kWh-Zähler maß und kein
Anlagenzähler «PV gesamt» zugeordnet war, nur die Zähler-Summe; die Erzeuger, die nur einen W-Sensor haben, fielen aus
der Summe (der Trapez-Fallback ``_kategorie_aus_entities`` lief nur, wenn gar kein Zähler maß). Gesäter Mischfall
(Probe P2 vom 3.11.): Wechselrichter-Zähler 57,04 + Balkonkraftwerk nur W-Sensor 5,70 ⇒ Kachel 57,0 statt 62,7; der
BKW-Wert stand im Tooltip, nicht in der Summe.

**Die Regel seit N-773** (wie die PV-Achse der Stunden, Bauform E4a-2): Erzeuger mit Zähler ⇒ Zähler-Delta, Erzeuger
ohne Zähler mit W-Sensor ⇒ Trapez, Summe = beides. Unverändert: Anlagen mit Anlagenzähler (N-752-Verteilung,
``test_n752_live_pv_wie_tag.py``), reine Zähler- und reine W-Anlagen.

Fünf Proben: (1) Mischfall ⇒ Zähler + Trapez (der Sprengsatz: mit der alten Regel rot) · (2) reine Zähler-Anlage ·
(3) reine W-Anlage · (4) mit Anlagenzähler · (5) Erzeuger mit Zähler UND W-Sensor zählt einmal, mit dem Zähler.

Die Reihen entstehen aus dem Fenster, das ``get_tages_kwh`` anfragt (gestern, ganzer Tag) — die Probe liest keine Uhr;
die Sollwerte rechnet sie aus denselben Reihen.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.services import live_history_service as lhs

WR, BKW = 7, 8
WR_KWP, BKW_KWP = 8.0, 0.8
SPITZE_JE_KWP = 800.0  # W je kWp zur Mittagsspitze
# Der Zähler des Wechselrichters misst bewusst etwas anderes als sein W-Sensor integriert — so trennt Probe (5) die
# Zähler- von der Leistungsmessung (eine Doppel- oder Falschzählung fiele um ≈ 50 kWh auf).
ZAEHLER_FAKTOR = 0.9
ANLAGEN_ZAEHLER_KWH = 70.0


def _leistung(t: datetime, kwp: float) -> float:
    h = t.hour + t.minute / 60
    if not 6 <= h <= 20:
        return 0.0
    return kwp * SPITZE_JE_KWP * math.sin(math.pi * (h - 6) / 14)


def _reihen(start: datetime, end: datetime) -> dict[str, tuple[list, str]]:
    """Alle Sensoren der Proben: W-Reihen (5-Minuten-Punkte), kumulierte Zähler (kWh)."""
    wr_w, bkw_w, wr_kwh, bkw_kwh, anl_kwh = [], [], [], [], []
    stand_wr, stand_bkw = 5000.0, 300.0
    t = start
    while t < end:
        p_wr, p_bkw = _leistung(t, WR_KWP), _leistung(t, BKW_KWP)
        wr_w.append((t, p_wr))
        bkw_w.append((t, p_bkw))
        wr_kwh.append((t, round(stand_wr, 4)))
        bkw_kwh.append((t, round(stand_bkw, 4)))
        stand_wr += ZAEHLER_FAKTOR * p_wr * (5 / 60) / 1000
        stand_bkw += p_bkw * (5 / 60) / 1000
        t += timedelta(minutes=5)
    letzt = end - timedelta(seconds=1)
    wr_kwh.append((letzt, round(stand_wr, 4)))
    bkw_kwh.append((letzt, round(stand_bkw, 4)))
    anl_kwh = [(start, 9000.0), (letzt, 9000.0 + ANLAGEN_ZAEHLER_KWH)]
    return {
        "sensor.wr_w": (wr_w, "W"),
        "sensor.bkw_w": (bkw_w, "W"),
        "sensor.wr_kwh": (wr_kwh, "kWh"),
        "sensor.bkw_kwh": (bkw_kwh, "kWh"),
        "sensor.pv_gesamt_kwh": (anl_kwh, "kWh"),
    }


def _feld(eid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": eid}


def _anlage(*, wr_zaehler: bool, wr_w: bool, bkw_zaehler: bool, bkw_w: bool, anlagenzaehler: bool = False):
    def _inv(zaehler: str | None, leistung: str | None) -> dict:
        d: dict = {}
        if zaehler:
            d["felder"] = {"pv_erzeugung_kwh": _feld(zaehler)}
        if leistung:
            d["live"] = {"leistung_w": leistung}
        return d

    basis: dict = {"pv_gesamt": _feld("sensor.pv_gesamt_kwh")} if anlagenzaehler else {}
    return SimpleNamespace(id=1, sensor_mapping={
        "basis": basis,
        "investitionen": {
            str(WR): _inv("sensor.wr_kwh" if wr_zaehler else None, "sensor.wr_w" if wr_w else None),
            str(BKW): _inv("sensor.bkw_kwh" if bkw_zaehler else None, "sensor.bkw_w" if bkw_w else None),
        },
    })


def _lauf(anlage, *, ohne_traeger: bool = False) -> tuple[dict, dict[str, float]]:
    """``get_tages_kwh`` für gestern (ganzes Fenster) ohne DB; zurück: Ergebnis und die Tagesmengen je Sensor.

    ``ohne_traeger``: ``erzeuger=[]`` — ``live_pv_verteilung`` findet keinen Träger und liefert ``None`` (GM-Fall A6)."""
    mengen: dict[str, float] = {}

    async def hist(ids, start, end):
        alle = _reihen(start, end)
        for eid, (pts, unit) in alle.items():
            mengen[eid] = pts[-1][1] - pts[0][1] if unit == "kWh" else lhs.trapez_kwh(pts)
        return ({i: alle[i][0] for i in ids if i in alle}, {i: alle[i][1] for i in ids if i in alle})

    erzeuger = [
        SimpleNamespace(id=WR, typ="pv-module", parent_investition_id=None, leistung_kwp=WR_KWP, parameter={},
                        aktiv=True),
        SimpleNamespace(id=BKW, typ="balkonkraftwerk", parent_investition_id=None, leistung_kwp=BKW_KWP,
                        parameter={}, aktiv=True),
    ]

    async def _inner():
        with patch.object(lhs, "get_history_normalized", hist):
            return await lhs.get_tages_kwh(
                anlage, db=None, tage_zurueck=1,
                inv_types={str(WR): "pv-module", str(BKW): "balkonkraftwerk"},
                erzeuger=[] if ohne_traeger else erzeuger,
            )

    return asyncio.run(_inner()), mengen


def test_mischfall_zaehler_plus_trapez():
    """(1) Sprengsatz: WR mit Zähler + BKW nur W-Sensor, kein Anlagenzähler ⇒ Zähler-Delta + Trapez."""
    live, m = _lauf(_anlage(wr_zaehler=True, wr_w=True, bkw_zaehler=False, bkw_w=True))
    soll = m["sensor.wr_kwh"] + m["sensor.bkw_w"]
    assert m["sensor.bkw_w"] > 5.0, "die Probe muss einen BKW-Ertrag tragen, sonst prüft sie nichts"
    assert live["pv"] == pytest.approx(soll, abs=0.05), (
        f"N-773: der W-only-Erzeuger gehört in die Summe — Soll {soll:.2f} (Zähler {m['sensor.wr_kwh']:.2f} + "
        f"Trapez {m['sensor.bkw_w']:.2f}), war {live['pv']!r} (alte Regel: nur der Zähler)"
    )
    # Tooltips je Erzeuger wie bisher: Zähler beim WR, Trapez beim BKW.
    assert live[f"pv_{WR}"] == pytest.approx(m["sensor.wr_kwh"], abs=0.05)
    assert live[f"pv_{BKW}"] == pytest.approx(m["sensor.bkw_w"], abs=0.05)


def test_reine_zaehler_anlage_unveraendert():
    """(2) Beide Erzeuger mit Zähler, keine W-Sensoren ⇒ Summe der Zähler-Deltas."""
    live, m = _lauf(_anlage(wr_zaehler=True, wr_w=False, bkw_zaehler=True, bkw_w=False))
    assert live["pv"] == pytest.approx(round(m["sensor.wr_kwh"] + m["sensor.bkw_kwh"], 1), abs=1e-9)


def test_reine_w_anlage_unveraendert():
    """(3) Beide Erzeuger nur mit W-Sensor ⇒ Trapez-Summe (der Fallback `_kategorie_aus_entities`)."""
    live, m = _lauf(_anlage(wr_zaehler=False, wr_w=True, bkw_zaehler=False, bkw_w=True))
    assert live["pv"] == pytest.approx(round(m["sensor.wr_w"] + m["sensor.bkw_w"], 1), abs=1e-9)


def test_mit_anlagenzaehler_unveraendert():
    """(4) Anlagenzähler + WR-Zähler + BKW nur W-Sensor ⇒ der Anlagenzähler gilt (N-752), kein Trapez obendrauf."""
    live, m = _lauf(_anlage(wr_zaehler=True, wr_w=True, bkw_zaehler=False, bkw_w=True, anlagenzaehler=True))
    assert m["sensor.pv_gesamt_kwh"] > m["sensor.wr_kwh"] + m["sensor.bkw_w"], "Anlagenzähler muss unterscheidbar sein"
    assert live["pv"] == pytest.approx(ANLAGEN_ZAEHLER_KWH, abs=0.05), live["pv"]
    # Der Rest des Anlagenzählers geht an den Erzeuger ohne Zähler (Tooltip), nicht sein Trapez.
    assert live[f"pv_{BKW}"] == pytest.approx(ANLAGEN_ZAEHLER_KWH - m["sensor.wr_kwh"], abs=0.05)
    # Anlagenzähler in der History, aber keine Verteilung möglich (keine Träger): wie vor N-773 nur die Zähler —
    # die Leistungsmessung kommt nur ohne Anlagenzähler dazu.
    live_ot, m_ot = _lauf(_anlage(wr_zaehler=True, wr_w=True, bkw_zaehler=False, bkw_w=True, anlagenzaehler=True),
                          ohne_traeger=True)
    assert live_ot["pv"] == pytest.approx(round(m_ot["sensor.wr_kwh"], 1), abs=1e-9), live_ot["pv"]


def test_erzeuger_mit_zaehler_und_w_sensor_zaehlt_einmal():
    """(5) WR mit Zähler UND W-Sensor (Integral ≠ Zähler) + BKW nur W ⇒ WR nur mit dem Zähler, einmal."""
    live, m = _lauf(_anlage(wr_zaehler=True, wr_w=True, bkw_zaehler=False, bkw_w=True))
    assert abs(m["sensor.wr_w"] - m["sensor.wr_kwh"]) > 3.0, "Zähler und Integral müssen unterscheidbar sein"
    assert live["pv"] == pytest.approx(round(m["sensor.wr_kwh"] + m["sensor.bkw_w"], 1), abs=1e-9)
    # Allein mit Zähler und W-Sensor (kein zweiter Erzeuger mit Messung) bleibt es beim Zähler.
    live_allein, m2 = _lauf(_anlage(wr_zaehler=True, wr_w=True, bkw_zaehler=False, bkw_w=False))
    assert live_allein["pv"] == pytest.approx(round(m2["sensor.wr_kwh"], 1), abs=1e-9)
