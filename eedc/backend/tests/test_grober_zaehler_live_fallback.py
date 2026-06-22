"""Unit-Tests: Grober-Zähler-Fallback für die Live-Tagesverlauf-Kurvenform.

Hintergrund (Forum mameier1234, #680): Ein PV-Energiezähler, der seltener als
alle 5 min meldet, lässt HA den ganzen aufgelaufenen Zuwachs in einen 5-Min-Slot
buchen → Nadel-Spike (z. B. 13 kW bei 11 kWp), den das Haushalt-Residuum
spiegelt. `kurven_leistung_mit_live_fallback` erkennt grobe Stunden (Phantom-
Null-Slots) und legt die Stunden-Energie (= Σ Zähler-Delta, LTS-treu) auf die
Live-Form (bzw. Plateau) statt sie zu vernadeln.

Self-contained Standalone-Script:

    eedc/backend/venv/bin/python eedc/backend/tests/test_grober_zaehler_live_fallback.py

Testet:
  1. Feiner Zähler (Update jeden Slot) → Output identisch zu
     counter_deltas_zu_leistung, keine grobe Stunde.
  2. Grober Zähler + Live-Sensor → keine Nadel (max < Spike), Σ-Energie exakt
     erhalten, Stunde als grob markiert.
  3. Grober Zähler OHNE Live → Plateau, Σ exakt erhalten, keine Nadel.
  4. Nacht (Zähler 0, Live 0) → keine grobe Stunde, Output 0.
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.core.berechnungen.live_tagesverlauf_5min import (  # noqa: E402
    kurven_leistung_mit_live_fallback,
    counter_deltas_zu_leistung,
    SLOT_MINUTEN,
    _KWH_PRO_SLOT_ZU_W,
)

_H = datetime(2026, 6, 22, 9, 0, 0)  # Test-Stunde 09:00
_SLOT_H = SLOT_MINUTEN / 60.0  # 5/60 h


def _slot(i: int) -> datetime:
    return _H + timedelta(minutes=i * SLOT_MINUTEN)


def _kurven_energie_kwh(punkte: list[tuple[datetime, float]]) -> float:
    """Σ Slot-Energie der Punkte (jeder Punkt = mittlere Leistung über 5 min)."""
    return sum(w * _SLOT_H / 1000.0 for _, w in punkte)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


# ── Test 1: feiner Zähler — unverändert ──────────────────────────────────

def test_feiner_zaehler_unveraendert():
    # Update in jedem Slot (12 Slots à 0.2 kWh = 2400 W).
    deltas = {_slot(i): 0.2 for i in range(12)}
    # Live vorhanden + glatt — darf NICHT zum Fallback führen, weil keine
    # Phantom-Null-Slots existieren (Zähler meldet ja jeden Slot).
    live = [(_slot(i), 2400.0) for i in range(12)]

    punkte, grob = kurven_leistung_mit_live_fallback(deltas, live)
    referenz = counter_deltas_zu_leistung(deltas)

    _assert(grob == [], f"feiner Zähler darf nicht grob sein: {grob}")
    _assert(punkte == referenz,
            "feiner Zähler muss identisch zu counter_deltas_zu_leistung sein")
    print("✓ Test 1: feiner Zähler unverändert")


# ── Test 2: grober Zähler + Live — Nadel weg, Σ erhalten ─────────────────

def test_grober_zaehler_mit_live():
    # Zähler meldet nur 2× pro Stunde (09:25: 0.5 kWh, 09:55: 0.7 kWh),
    # alle anderen Slots 0 → ohne Fix: Nadeln 6000 W / 8400 W.
    deltas = {_slot(i): 0.0 for i in range(12)}
    deltas[_slot(5)] = 0.5   # 09:25
    deltas[_slot(11)] = 0.7  # 09:55
    summe_kwh = 1.2

    # Live: glatter Vormittagsanstieg 2000 → 3100 W (echte Form, keine Nadel).
    live = [(_slot(i), 2000.0 + i * 100.0) for i in range(12)]

    punkte, grob = kurven_leistung_mit_live_fallback(deltas, live)

    # Stunde als grob erkannt.
    _assert(grob == [_H], f"grobe Stunde nicht erkannt: {grob}")

    # Vergleich: ohne Fix gäbe es eine 8400-W-Nadel.
    referenz = counter_deltas_zu_leistung(deltas)
    nadel = max(w for _, w in referenz)
    _assert(abs(nadel - 0.7 * _KWH_PRO_SLOT_ZU_W) < 1e-6,
            f"Erwartete Nadel 8400 W in Referenz, war {nadel}")

    # Mit Fix: kein Wert über ~ Live-Maximum (3100 W × Faktor ~1).
    max_fix = max(w for _, w in punkte)
    _assert(max_fix < nadel * 0.6,
            f"Fix enthält noch eine Nadel: max={max_fix}, Nadel war {nadel}")

    # Σ-Energie exakt erhalten (= Σ Zähler-Delta = LTS-Stundenwert).
    energie = _kurven_energie_kwh(punkte)
    _assert(abs(energie - summe_kwh) < 1e-9,
            f"Σ-Energie nicht erhalten: {energie} != {summe_kwh}")

    # Form folgt dem Live-Anstieg (monoton steigend wie live).
    werte = [w for _, w in punkte]
    _assert(werte == sorted(werte),
            "Live-Form (monoton steigend) nicht übernommen")
    print("✓ Test 2: grober Zähler + Live — Nadel weg, Σ erhalten")


# ── Test 3: grober Zähler OHNE Live — Plateau ────────────────────────────

def test_grober_zaehler_ohne_live():
    deltas = {_slot(i): 0.0 for i in range(12)}
    deltas[_slot(5)] = 0.5
    deltas[_slot(11)] = 0.7
    summe_kwh = 1.2

    punkte, grob = kurven_leistung_mit_live_fallback(deltas, None)

    _assert(grob == [_H], f"grobe Stunde (ohne Live) nicht erkannt: {grob}")

    werte = [w for _, w in punkte]
    # Plateau: alle Slots gleicher Wert.
    _assert(max(werte) - min(werte) < 1e-6,
            f"kein Plateau: {werte}")
    # Plateau-Höhe = Stundenenergie / 1 h = 1.2 kW (gleichmäßig über 12 Slots).
    erwartet_w = summe_kwh * _KWH_PRO_SLOT_ZU_W / 12
    _assert(abs(werte[0] - erwartet_w) < 1e-6,
            f"Plateau-Höhe falsch: {werte[0]} != {erwartet_w}")
    energie = _kurven_energie_kwh(punkte)
    _assert(abs(energie - summe_kwh) < 1e-9,
            f"Σ-Energie (Plateau) nicht erhalten: {energie} != {summe_kwh}")
    print("✓ Test 3: grober Zähler ohne Live — Plateau, Σ erhalten")


# ── Test 4: Nacht — keine Fehlauslösung ──────────────────────────────────

def test_nacht_keine_fehlausloesung():
    # Zähler 0 jeden Slot, Live ~0 (Rauschen unter Epsilon).
    deltas = {_slot(i): 0.0 for i in range(12)}
    live = [(_slot(i), 10.0) for i in range(12)]  # < LIVE_EPSILON_W (50)

    punkte, grob = kurven_leistung_mit_live_fallback(deltas, live)

    _assert(grob == [], f"Nacht darf nicht grob sein: {grob}")
    _assert(all(w == 0.0 for _, w in punkte),
            "Nacht-Output muss 0 sein")
    print("✓ Test 4: Nacht — keine Fehlauslösung")


def main() -> int:
    tests = [
        test_feiner_zaehler_unveraendert,
        test_grober_zaehler_mit_live,
        test_grober_zaehler_ohne_live,
        test_nacht_keine_fehlausloesung,
    ]
    fehler = 0
    for t in tests:
        try:
            t()
        except Exception:
            fehler += 1
            print(f"✗ {t.__name__}")
            traceback.print_exc()
    if fehler:
        print(f"\n{fehler}/{len(tests)} Tests fehlgeschlagen")
        return 1
    print(f"\nAlle {len(tests)} Tests grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
