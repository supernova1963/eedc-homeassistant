"""Proben der Fenster-Helfer (HA-Bauform E3; neu gefasst S4 E-S4-1, R-3) — ``services/kanal/fenster.py``.

Seit E-S4-1 ist das Tagesfenster der Kanal-Schicht der **Kalendertag** ``[D 00:00, D+1 00:00)`` in der Prozesszone und
das Monatsfenster der **Kalendermonat** (``monatsfenster`` ≡ ``kalendermonatsfenster``, ein Körper; Bauplan S4 §4
S4-R-3a). Bestandstage behalten ihr Rückwärts-Fenster ``[Vortag 23:00, 23:00)`` — das nennt weiter
``slot_konvention.tagesfenster_start_ts`` (unverändert, Schreiber und HA-Leser).

* **In-Prozess:** Tag = Kalendertag (und genau eine Stunde später als das Bestands-Fenster), lückenlose Tages- und
  Monatsfolge über einen Jahreswechsel, Σ Tagesfenster eines Monats ≡ Monatsfenster ≡ Kalendermonatsfenster;
  Kalendermonatsfenster == ``ha_statistics_service._monatsgrenzen_ts`` (die Grenze des HA-Monatslesers) für jeden Monat
  von 2025 bis 2028.
* **Je Zone im eigenen Prozess** (``TZ=…``, Berlin · UTC · Auckland): Umstellungstage (März/Oktober, April/September)
  mit 23/25 Stunden-Zeilen, Monats- und Jahreswechsel, Februar im Schaltjahr — gegen ein UNABHÄNGIGES Orakel
  (``zoneinfo``: Wanduhr 00:00 der Zone → UTC), mit den Stundenzahlen ausgeschrieben; **Mitternacht fällt nie aus**
  (die Grenze ist in der Zone wieder genau 00:00 des Tages).

Dass die Kanal-Tage den Bestand um die Randstunde verschoben TREFFEN (Kanal-Tag ≡ Σ Slots 1…23 + Slot 0 des Folgetags),
prüft der Symmetrie-Wächter ``test_kanal_symmetrie.py``; die Stunden-Umrechnung ``test_kanal_slot_umrechnung.py``.

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


def _mitternacht(tag: date) -> int:
    return int(round(datetime.combine(tag, time()).timestamp()))


@pytest.mark.parametrize("tag", TAGE, ids=str)
def test_tagesfenster_ist_der_kalendertag_eine_stunde_nach_dem_bestand(tag):
    assert tagesfenster(tag) == (_mitternacht(tag), _mitternacht(tag + timedelta(days=1)))
    # Das Bestands-Fenster [Vortag 23:00, 23:00) bleibt die Umrechnung der Schreiber — der Kalendertag liegt genau eine
    # Stunde später (Wanduhr 23:00 existiert an jedem Umstellungstag dieser Zone).
    von_zeile, bis_zeile = tagesfenster_start_ts(tag)
    assert tagesfenster(tag) == (von_zeile + 2 * 3600, bis_zeile + 2 * 3600)


def test_tage_und_monate_lueckenlos_ueber_den_jahreswechsel_und_monat_ist_summe_seiner_tage():
    liste = monate((2025, 11), (2027, 2))
    assert liste[0] == (2025, 11) and liste[-1] == (2027, 2) and len(liste) == 16
    g = monatsgrenzen((2025, 11), (2027, 2))
    assert len(g) == len(liste) + 1
    for i, (j, m) in enumerate(liste):
        von, bis = monatsfenster(j, m)
        assert (g[i], g[i + 1]) == (von, bis) == kalendermonatsfenster(j, m)
        tage = [date(j, m, 1) + timedelta(days=d) for d in range(40) if (date(j, m, 1) + timedelta(days=d)).month == m]
        assert von == tagesfenster(tage[0])[0] and bis == tagesfenster(tage[-1])[1]
        assert all(tagesfenster(a)[1] == tagesfenster(b)[0] for a, b in zip(tage, tage[1:]))
        assert sum(tagesfenster(t)[1] - tagesfenster(t)[0] for t in tage) == bis - von   # Σ Tage ≡ Monat
    assert monate((2026, 5), (2026, 4)) == [] and monatsgrenzen((2026, 5), (2026, 4)) == []


def test_kalendermonatsfenster_ist_die_grenze_des_ha_monatslesers():
    from backend.services.ha_statistics_service import _monatsgrenzen_ts

    liste = monate((2025, 1), (2028, 12))
    for j, m in liste:
        assert kalendermonatsfenster(j, m) == tuple(int(round(x)) for x in _monatsgrenzen_ts(j, m)), (j, m)
        assert monatsfenster(j, m) == kalendermonatsfenster(j, m), (j, m)
    assert all(kalendermonatsfenster(*a)[1] == kalendermonatsfenster(*b)[0] for a, b in zip(liste, liste[1:]))


_SKRIPT = """
import json, sys
from datetime import date, datetime, timedelta
sys.path.insert(0, sys.argv[1])
from backend.services.kanal.fenster import kalendermonatsfenster, monatsfenster, tagesfenster
from backend.services.ha_statistics_service import _monatsgrenzen_ts
tage = json.loads(sys.argv[2]); monate = json.loads(sys.argv[3])
def wand(ts):
    d = datetime.fromtimestamp(ts)
    return [d.date().isoformat(), d.hour, d.minute]
print(json.dumps({"tage": {t: list(tagesfenster(date.fromisoformat(t))) for t in tage},
                  "wand": {t: [wand(x) for x in tagesfenster(date.fromisoformat(t))] for t in tage},
                  "zeilen": {t: [datetime.fromtimestamp(ts).hour for ts in range(*tagesfenster(date.fromisoformat(t)), 3600)]
                             for t in tage},
                  "monate": {f"{j}-{m:02d}": list(monatsfenster(j, m)) for j, m in monate},
                  "kalender": {f"{j}-{m:02d}": list(kalendermonatsfenster(j, m)) for j, m in monate},
                  "summe_tage": {f"{j}-{m:02d}": sum(tagesfenster(d)[1] - tagesfenster(d)[0]
                                 for d in (date(j, m, 1) + timedelta(days=k) for k in range(31))
                                 if d.month == m) for j, m in monate},
                  "ha_leser": {f"{j}-{m:02d}": [int(round(x)) for x in _monatsgrenzen_ts(j, m)] for j, m in monate}}))
"""


def _orakel_00(zone: str, tag: date) -> int:
    """Wanduhr ``tag`` 00:00 in ``zone`` als Unix-Sekunden (unabhängig von Prozesszone und Produktcode)."""
    return int(datetime.combine(tag, time(0)).replace(tzinfo=ZoneInfo(zone)).timestamp())


#: Stunden je Kalendertag, ausgeschrieben (Umstellung Berlin 29.03./25.10., Auckland 05.04./27.09.) — zugleich die Zahl
#: der Stundenzeilen eines Kanal-Tags.
_TAG_STUNDEN = {
    "Europe/Berlin": {"2026-03-29": 23, "2026-10-25": 25, "2026-04-05": 24, "2026-09-27": 24,
                      "2026-01-01": 24, "2026-12-31": 24, "2028-02-29": 24},
    "UTC": {t.isoformat(): 24 for t in TAGE},
    "Pacific/Auckland": {"2026-03-29": 24, "2026-10-25": 24, "2026-04-05": 25, "2026-09-27": 23,
                         "2026-01-01": 24, "2026-12-31": 24, "2028-02-29": 24},
}

#: Die doppelte bzw. fehlende Wanduhr-Stunde der Umstellungstage (Stunde des Beginns der Zeilen).
_UMSTELLUNG = {
    "Europe/Berlin": {"2026-10-25": ("doppelt", 2), "2026-03-29": ("fehlt", 2)},
    "UTC": {},
    "Pacific/Auckland": {"2026-04-05": ("doppelt", 2), "2026-09-27": ("fehlt", 2)},
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


@pytest.mark.parametrize("zone", sorted(_TAG_STUNDEN))
def test_fenster_je_zone_gegen_unabhaengiges_orakel(zone):
    wurzel = str(Path(__file__).resolve().parents[2])
    tage = [t.isoformat() for t in TAGE]
    r = subprocess.run([sys.executable, "-B", "-c", _SKRIPT, wurzel, json.dumps(tage), json.dumps(MONATE)],
                       env={**os.environ, "TZ": zone}, capture_output=True, text=True, timeout=60, check=True)
    ist = json.loads(r.stdout)
    for t in TAGE:
        schl = t.isoformat()
        von, bis = ist["tage"][schl]
        assert (von, bis) == (_orakel_00(zone, t), _orakel_00(zone, t + timedelta(days=1))), (zone, t)
        # Mitternacht fällt nie aus: beide Grenzen sind in der Zone wieder genau 00:00 des Tages bzw. Folgetags.
        assert ist["wand"][schl] == [[schl, 0, 0], [(t + timedelta(days=1)).isoformat(), 0, 0]], (zone, t)
        zeilen = ist["zeilen"][schl]
        assert len(zeilen) == (bis - von) // 3600 == _TAG_STUNDEN[zone][schl], (zone, t)
        art = _UMSTELLUNG[zone].get(schl)
        if art is None:
            assert zeilen == list(range(24)), (zone, t)
        elif art[0] == "doppelt":
            assert zeilen.count(art[1]) == 2 and sorted(set(zeilen)) == list(range(24)), (zone, t)
        else:
            assert art[1] not in zeilen and sorted(zeilen + [art[1]]) == list(range(24)), (zone, t)
    for j, m in MONATE:
        schl = f"{j}-{m:02d}"
        folge = date(j + 1, 1, 1) if m == 12 else date(j, m + 1, 1)
        assert ist["kalender"][schl] == [_orakel_00(zone, date(j, m, 1)), _orakel_00(zone, folge)], (zone, schl)
        assert ist["monate"][schl] == ist["kalender"][schl] == ist["ha_leser"][schl], (zone, schl)
        von, bis = ist["kalender"][schl]
        assert (bis - von) // 3600 == _KALENDER_STUNDEN[zone][schl], (zone, schl)
        assert ist["summe_tage"][schl] == bis - von, (zone, schl)   # Σ Tagesfenster ≡ Monatsfenster
    assert ist["kalender"]["2026-12"][1] == ist["kalender"]["2027-01"][0]
    assert ist["monate"]["2026-12"][1] == ist["monate"]["2027-01"][0]
