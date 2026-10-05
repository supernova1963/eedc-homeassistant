"""Proben der Fenster-Helfer (HA-Bauform E3, Auftrag Punkt 4) — ``services/kanal/fenster.py``.

Tagesfenster und Monatsfenster als absolute Grenzen exakt so, wie der Bestand sie bildet: Tag = ``[Vortag 23:00,
23:00)`` über die EINE Umrechnung ``slot_konvention.tagesfenster_start_ts`` (+1 h: der Stand einer Zeile gilt am Ende
ihrer Stunde); Monat = Anfang des Tagesfensters des Ersten bis Ende des Tagesfensters des Letzten.

* **In-Prozess:** Bezug zur Umrechnung, lückenlose Monatsfolge über einen Jahreswechsel, Monat = Σ seiner Tage;
  Kalendermonatsfenster == ``ha_statistics_service._monatsgrenzen_ts`` (die Grenze des HA-Monatslesers) für jeden Monat
  von 2025 bis 2028.
* **Je Zone im eigenen Prozess** (``TZ=…``, Berlin · UTC · Auckland): Umstellungstage (März/Oktober, April/September),
  Monats- und Jahreswechsel, Februar im Schaltjahr — gegen ein UNABHÄNGIGES Orakel (``zoneinfo``: Wanduhr 23:00 der
  Zone → UTC) und mit den Stundenzahlen ausgeschrieben.

Dass die Fenster den Bestand TREFFEN (Δ über das Tagesfenster == Tageswert von ``aggregate_day``), prüft der
Symmetrie-Wächter ``test_kanal_symmetrie.py`` über die Lese-Schicht auf allen 33 Matrix-Formen; den Monat
(Δ über das Monatsfenster == ``lade_monats_summen_aus_tagen``) ``test_kanal_quellenwahl.py``.

Schwesterdateien: test_kanal_lesen.py, test_kanal_slot_umrechnung.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backend.core.berechnungen.slot_konvention import tagesfenster_start_ts
from backend.services.kanal.fenster import kalendermonatsfenster, monate, monatsfenster, monatsgrenzen, tagesfenster

TAGE = (date(2026, 3, 29), date(2026, 10, 25), date(2026, 4, 5), date(2026, 9, 27), date(2026, 1, 1),
        date(2026, 12, 31), date(2028, 2, 29))
MONATE = ((2026, 3), (2026, 10), (2026, 4), (2026, 9), (2026, 12), (2027, 1), (2028, 2))


@pytest.mark.parametrize("tag", TAGE, ids=str)
def test_tagesfenster_ist_die_eine_umrechnung_plus_eine_stunde(tag):
    von_zeile, bis_zeile = tagesfenster_start_ts(tag)
    assert tagesfenster(tag) == (von_zeile + 3600, bis_zeile + 3600)


def test_monatsfolge_lueckenlos_ueber_den_jahreswechsel_und_monat_ist_summe_seiner_tage():
    liste = monate((2025, 11), (2027, 2))
    assert liste[0] == (2025, 11) and liste[-1] == (2027, 2) and len(liste) == 16
    g = monatsgrenzen((2025, 11), (2027, 2))
    assert len(g) == len(liste) + 1
    for i, (j, m) in enumerate(liste):
        von, bis = monatsfenster(j, m)
        assert (g[i], g[i + 1]) == (von, bis)
        tage = [date(j, m, 1) + timedelta(days=d) for d in range(40) if (date(j, m, 1) + timedelta(days=d)).month == m]
        assert von == tagesfenster(tage[0])[0] and bis == tagesfenster(tage[-1])[1]
        assert all(tagesfenster(a)[1] == tagesfenster(b)[0] for a, b in zip(tage, tage[1:]))
    assert monate((2026, 5), (2026, 4)) == [] and monatsgrenzen((2026, 5), (2026, 4)) == []


def test_kalendermonatsfenster_ist_die_grenze_des_ha_monatslesers():
    from backend.services.ha_statistics_service import _monatsgrenzen_ts

    liste = monate((2025, 1), (2028, 12))
    for j, m in liste:
        assert kalendermonatsfenster(j, m) == tuple(int(round(x)) for x in _monatsgrenzen_ts(j, m)), (j, m)
    assert all(kalendermonatsfenster(*a)[1] == kalendermonatsfenster(*b)[0] for a, b in zip(liste, liste[1:]))


_SKRIPT = """
import json, sys
from datetime import date
sys.path.insert(0, sys.argv[1])
from backend.services.kanal.fenster import kalendermonatsfenster, monatsfenster, tagesfenster
from backend.services.ha_statistics_service import _monatsgrenzen_ts
tage = json.loads(sys.argv[2]); monate = json.loads(sys.argv[3])
print(json.dumps({"tage": {t: list(tagesfenster(date.fromisoformat(t))) for t in tage},
                  "monate": {f"{j}-{m:02d}": list(monatsfenster(j, m)) for j, m in monate},
                  "kalender": {f"{j}-{m:02d}": list(kalendermonatsfenster(j, m)) for j, m in monate},
                  "ha_leser": {f"{j}-{m:02d}": [int(round(x)) for x in _monatsgrenzen_ts(j, m)] for j, m in monate}}))
"""


def _orakel_00(zone: str, tag: date) -> int:
    """Wanduhr ``tag`` 00:00 in ``zone`` als Unix-Sekunden (unabhängig von Prozesszone und Produktcode)."""
    return int(datetime.combine(tag, time(0)).replace(tzinfo=ZoneInfo(zone)).timestamp())


def _orakel_23(zone: str, tag: date) -> int:
    """Wanduhr ``tag`` 23:00 in ``zone`` als Unix-Sekunden — unabhängig von der Prozesszone und von ``slot_konvention``."""
    return int(datetime.combine(tag, time(23)).replace(tzinfo=ZoneInfo(zone)).timestamp())


def _letzter(j: int, m: int) -> date:
    return (date(j + 1, 1, 1) if m == 12 else date(j, m + 1, 1)) - timedelta(days=1)


#: Stunden je Tagesfenster und je Monatsfenster, ausgeschrieben (Umstellung Berlin 29.03./25.10., Auckland 05.04./27.09.).
_STUNDEN = {
    "Europe/Berlin": {"tage": {"2026-03-29": 23, "2026-10-25": 25, "2026-04-05": 24, "2026-09-27": 24,
                               "2026-01-01": 24, "2026-12-31": 24, "2028-02-29": 24},
                      "monate": {"2026-03": 743, "2026-10": 745, "2026-04": 720, "2026-09": 720,
                                 "2026-12": 744, "2027-01": 744, "2028-02": 696}},
    "UTC": {"tage": {t.isoformat(): 24 for t in TAGE},
            "monate": {"2026-03": 744, "2026-10": 744, "2026-04": 720, "2026-09": 720,
                       "2026-12": 744, "2027-01": 744, "2028-02": 696}},
    "Pacific/Auckland": {"tage": {"2026-03-29": 24, "2026-10-25": 24, "2026-04-05": 25, "2026-09-27": 23,
                                  "2026-01-01": 24, "2026-12-31": 24, "2028-02-29": 24},
                         "monate": {"2026-03": 744, "2026-10": 744, "2026-04": 721, "2026-09": 719,
                                    "2026-12": 744, "2027-01": 744, "2028-02": 696}},
}


#: Stunden je Kalendermonat (Berlin: März −1, Oktober +1; Auckland: April +1, September −1).
_KALENDER_STUNDEN = {
    "Europe/Berlin": {"2026-03": 743, "2026-10": 745, "2026-04": 720, "2026-09": 720, "2026-12": 744, "2027-01": 744,
                      "2028-02": 696},
    "UTC": {"2026-03": 744, "2026-10": 744, "2026-04": 720, "2026-09": 720, "2026-12": 744, "2027-01": 744,
            "2028-02": 696},
    "Pacific/Auckland": {"2026-03": 744, "2026-10": 744, "2026-04": 721, "2026-09": 719, "2026-12": 744,
                         "2027-01": 744, "2028-02": 696},
}


@pytest.mark.parametrize("zone", sorted(_STUNDEN))
def test_fenster_je_zone_gegen_unabhaengiges_orakel(zone):
    wurzel = str(Path(__file__).resolve().parents[2])
    tage = [t.isoformat() for t in TAGE]
    r = subprocess.run([sys.executable, "-B", "-c", _SKRIPT, wurzel, json.dumps(tage), json.dumps(MONATE)],
                       env={**os.environ, "TZ": zone}, capture_output=True, text=True, timeout=60, check=True)
    ist = json.loads(r.stdout)
    for t in TAGE:
        von, bis = ist["tage"][t.isoformat()]
        assert (von, bis) == (_orakel_23(zone, t - timedelta(days=1)), _orakel_23(zone, t)), (zone, t)
        assert (bis - von) // 3600 == _STUNDEN[zone]["tage"][t.isoformat()], (zone, t)
    for j, m in MONATE:
        von, bis = ist["monate"][f"{j}-{m:02d}"]
        assert (von, bis) == (_orakel_23(zone, date(j, m, 1) - timedelta(days=1)), _orakel_23(zone, _letzter(j, m)))
        assert (bis - von) // 3600 == _STUNDEN[zone]["monate"][f"{j}-{m:02d}"], (zone, j, m)
    # Jahreswechsel: Dezember endet, wo Januar beginnt
    assert ist["monate"]["2026-12"][1] == ist["monate"]["2027-01"][0]
    # Kalendermonat: gegen das Orakel 00:00, gleich dem HA-Monatsleser, Stunden ausgeschrieben
    for j, m in MONATE:
        schl = f"{j}-{m:02d}"
        folge = date(j + 1, 1, 1) if m == 12 else date(j, m + 1, 1)
        assert ist["kalender"][schl] == [_orakel_00(zone, date(j, m, 1)), _orakel_00(zone, folge)], (zone, schl)
        assert ist["kalender"][schl] == ist["ha_leser"][schl], (zone, schl)
        von, bis = ist["kalender"][schl]
        assert (bis - von) // 3600 == _KALENDER_STUNDEN[zone][schl], (zone, schl)
    assert ist["kalender"]["2026-12"][1] == ist["kalender"]["2027-01"][0]
