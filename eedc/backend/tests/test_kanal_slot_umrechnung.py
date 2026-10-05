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

Schwesterdateien: test_kanal_symmetrie.py, test_slot_konvention_quellen.py.
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
