"""Probe: Slot der Stundenzeilen → ``start_ts`` — EINE Umrechnung an EINER Stelle (HA-Bauform E2, Bericht Etappe 1 H2).

``core/berechnungen/slot_konvention.py::slot_start_ts`` ist die Umkehrung von ``lts_boundary_index``
(HA-Zeile → Rückwärts-Slot, #144). Geprüft an Umstellungstagen (März und Oktober) in Berlin, UTC und
Auckland:

* **In-Prozess, in jeder Zone:** jede Stunde, die einen ``start_ts`` hat, kehrt über
  ``lts_boundary_index`` auf ihren Slot zurück; die Zeitstempel steigen streng; das Tagesfenster
  ``[Vortag 23:00, 23:00)`` umfasst so viele reale Stunden, wie der Tag Slots mit Stunde hat
  (+1 für die doppelte Herbststunde).
* **Je Zone im eigenen Prozess** (``TZ=…``): die konkreten Zahlen — Berlin 29.03. Slot 3 ohne Stunde,
  Fenster 23 h; 25.10. Slot 3 = die spätere 02:00, Fenster 25 h. UTC immer 24 h. Auckland stellt am
  05.04./27.09. um und ist am 29.03./25.10. ein gewöhnlicher Tag.

**S4 E-S4-1 (R-3, S4-R-3b): Stunde = Beginn.** Der Kanal-Stundentag beschriftet die Stunde mit ihrem Beginn
(``stunden_leser.stunde_des_beginns``); die Umrechnung Beginn → Bestandszeile steht an EINER Stelle,
``slot_konvention.bestandszeile_fuer_stundenbeginn`` (``(D, h+1)``, für ``h = 23`` ``(D+1, 0)``). Geprüft je Zone im
eigenen Prozess: jede Zeile des Kalendertags fällt über Beginn-Stunde + Umrechnung auf genau die Bestandszeile, die
``lts_boundary_index`` ihr gibt (Umstellungstage: Herbst Stunde 2 zweimal ⇒ Slot 3 zweimal, Frühjahr Stunde 2 leer);
dazu die Paarung einer Beginn-Zeile (``raster = "beginn"``) zeilengleich und ``stundenbeginn_der_zeile``.

Schwesterdateien: test_kanal_symmetrie.py, test_slot_konvention_quellen.py, test_kanal_lesen_fenster.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from backend.core.berechnungen.slot_konvention import lts_boundary_index, slot_start_ts, tagesfenster_start_ts

TAGE = (date(2026, 3, 29), date(2026, 10, 25), date(2026, 4, 5), date(2026, 9, 27))


@pytest.mark.parametrize("tag", TAGE, ids=str)
def test_umkehrung_von_lts_boundary_index_in_dieser_zone(tag):
    ts = {h: slot_start_ts(tag, h) for h in range(24)}
    mit = [h for h in range(24) if ts[h] is not None]
    for h in mit:
        assert lts_boundary_index(datetime.fromtimestamp(ts[h]), tag) == h, h
    assert all(ts[a] < ts[b] for a, b in zip(mit, mit[1:]))
    von, bis = tagesfenster_start_ts(tag)
    assert von == slot_start_ts(tag - timedelta(days=1), 23) and bis == ts[23]
    # Reale Stunden des Fensters = Slots mit Stunde (+ je eine für die doppelte Herbststunde: der Slot
    # dort trägt zwei reale Stunden, n = 2 in get_hourly_slots_for_day).
    doppelt = sum(1 for a, b in zip(mit, mit[1:]) if ts[b] - ts[a] == 7200 and b == a + 1)
    assert (bis - von) // 3600 == len(mit) + doppelt


_SKRIPT = """
import json, sys
from datetime import date
sys.path.insert(0, sys.argv[1])
from backend.core.berechnungen.slot_konvention import slot_start_ts, tagesfenster_start_ts
out = {}
for iso in sys.argv[2:]:
    d = date.fromisoformat(iso)
    ts = [slot_start_ts(d, h) for h in range(24)]
    von, bis = tagesfenster_start_ts(d)
    out[iso] = {"ohne": [h for h in range(24) if ts[h] is None], "fenster_h": (bis - von) // 3600,
                "slot3_minus_slot2": None if ts[3] is None or ts[2] is None else ts[3] - ts[2]}
print(json.dumps(out))
"""

_SOLL = {
    "Europe/Berlin": {
        "2026-03-29": {"ohne": [3], "fenster_h": 23, "slot3_minus_slot2": None},
        "2026-10-25": {"ohne": [], "fenster_h": 25, "slot3_minus_slot2": 7200},   # die spätere 02:00
        "2026-04-05": {"ohne": [], "fenster_h": 24, "slot3_minus_slot2": 3600},
        "2026-09-27": {"ohne": [], "fenster_h": 24, "slot3_minus_slot2": 3600},
    },
    "UTC": {iso: {"ohne": [], "fenster_h": 24, "slot3_minus_slot2": 3600}
            for iso in ("2026-03-29", "2026-10-25", "2026-04-05", "2026-09-27")},
    "Pacific/Auckland": {
        "2026-03-29": {"ohne": [], "fenster_h": 24, "slot3_minus_slot2": 3600},
        "2026-10-25": {"ohne": [], "fenster_h": 24, "slot3_minus_slot2": 3600},
        "2026-04-05": {"ohne": [], "fenster_h": 25, "slot3_minus_slot2": 7200},  # 02:00 doppelt (NZDT → NZST)
        "2026-09-27": {"ohne": [3], "fenster_h": 23, "slot3_minus_slot2": None},
    },
}


@pytest.mark.parametrize("zone", sorted(_SOLL))
def test_umstellungstage_je_zone(zone):
    wurzel = str(Path(__file__).resolve().parents[2])
    env = {**os.environ, "TZ": zone}
    r = subprocess.run([sys.executable, "-B", "-c", _SKRIPT, wurzel, *_SOLL[zone]],
                       env=env, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(r.stdout) == _SOLL[zone]


# ── S4 E-S4-1: Stunde = Beginn, Umrechnung Beginn → Bestandszeile ───────────────────────────────────────────────────

from types import SimpleNamespace  # noqa: E402

from backend.core.berechnungen.slot_konvention import (  # noqa: E402
    FORWARD_FELDER, RASTER_BEGINN, bestandszeile_fuer_stundenbeginn, forward_werte_je_backward_zeile,
    stundenbeginn_der_zeile, zeile_traegt_backward_kw,
)


def test_bestandszeile_fuer_stundenbeginn_23_geht_in_den_folgetag():
    d = date(2026, 7, 2)
    assert [bestandszeile_fuer_stundenbeginn(d, h) for h in range(23)] == [(d, h + 1) for h in range(23)]
    assert bestandszeile_fuer_stundenbeginn(d, 23) == (date(2026, 7, 3), 0)
    assert bestandszeile_fuer_stundenbeginn(date(2026, 12, 31), 23) == (date(2027, 1, 1), 0)
    assert bestandszeile_fuer_stundenbeginn(date(2028, 2, 28), 23) == (date(2028, 2, 29), 0)
    assert FORWARD_FELDER == {"soc_prozent", "soc_je_speicher", "strompreis_cent", "boersenpreis_cent"}


def test_beginn_zeile_paart_zeilengleich_und_traegt_keine_backward_kw():
    d = date(2026, 7, 2)
    alt = date(2026, 9, 1)   # created_at nach SLOT_PAARUNG_VORZEILE_AB: Bestandszeilen paaren mit der Vorzeile
    bestand = [SimpleNamespace(datum=d, stunde=h, created_at=alt, strompreis_cent=10.0 + h) for h in range(3)]
    beginn = [SimpleNamespace(datum=d, stunde=h, created_at=alt, strompreis_cent=10.0 + h, raster=RASTER_BEGINN)
              for h in range(3)]
    assert forward_werte_je_backward_zeile(bestand, "strompreis_cent") == [None, 10.0, 11.0]
    assert forward_werte_je_backward_zeile(beginn, "strompreis_cent") == [10.0, 11.0, 12.0]
    assert [zeile_traegt_backward_kw(z) for z in bestand] == [True, True, True]
    assert [zeile_traegt_backward_kw(z) for z in beginn] == [False, False, False]
    assert [stundenbeginn_der_zeile(z) for z in bestand] == [23, 0, 1]
    assert [stundenbeginn_der_zeile(z) for z in beginn] == [0, 1, 2]


_SKRIPT_BEGINN = """
import json, sys
from datetime import date, datetime, timedelta
sys.path.insert(0, sys.argv[1])
from backend.core.berechnungen.slot_konvention import bestandszeile_fuer_stundenbeginn, lts_boundary_index
from backend.services.kanal.fenster import tagesfenster
from backend.services.kanal.stunden_leser import stunde_des_beginns
out = {}
for iso in sys.argv[2:]:
    d = date.fromisoformat(iso)
    von, bis = tagesfenster(d)
    stunden, abweichend = [], []
    for ts in range(von, bis, 3600):
        h = stunde_des_beginns(ts, d)
        k = lts_boundary_index(datetime.fromtimestamp(ts), d)
        bestand = (d + timedelta(days=k // 24), k % 24)
        if bestandszeile_fuer_stundenbeginn(d, h) != bestand:
            abweichend.append([ts, h, k])
        stunden.append(h)
    out[iso] = {"stunden": stunden, "abweichend": abweichend,
                "vor_dem_tag": stunde_des_beginns(von - 3600, d), "folgetag": stunde_des_beginns(bis, d)}
print(json.dumps(out))
"""

_SOLL_BEGINN = {
    "Europe/Berlin": {"2026-03-29": [h for h in range(24) if h != 2], "2026-10-25": [0, 1, 2, 2, *range(3, 24)],
                      "2026-04-05": list(range(24)), "2026-09-27": list(range(24))},
    "UTC": {iso: list(range(24)) for iso in ("2026-03-29", "2026-10-25", "2026-04-05", "2026-09-27")},
    "Pacific/Auckland": {"2026-03-29": list(range(24)), "2026-10-25": list(range(24)),
                         "2026-04-05": [0, 1, 2, 2, *range(3, 24)], "2026-09-27": [h for h in range(24) if h != 2]},
}


@pytest.mark.parametrize("zone", sorted(_SOLL_BEGINN))
def test_stunde_des_beginns_und_bestandszeile_je_zone(zone):
    wurzel = str(Path(__file__).resolve().parents[2])
    r = subprocess.run([sys.executable, "-B", "-c", _SKRIPT_BEGINN, wurzel, *_SOLL_BEGINN[zone]],
                       env={**os.environ, "TZ": zone}, capture_output=True, text=True, timeout=60, check=True)
    ist = json.loads(r.stdout)
    for iso, stunden in _SOLL_BEGINN[zone].items():
        assert ist[iso]["stunden"] == stunden, (zone, iso)
        assert ist[iso]["abweichend"] == [], (zone, iso)
        assert ist[iso]["vor_dem_tag"] == -1 and ist[iso]["folgetag"] == -1, (zone, iso)
