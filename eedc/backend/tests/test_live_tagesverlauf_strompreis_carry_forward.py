"""
Live-Tagesverlauf Strompreis: Carry-Forward bei Step-Funktionen.

Trigger: #267 rilmor-mhrs (Tibber-Sensor mit 15-Min-Step-Updates).
Vor dem Fix fiel jeder 10-Min-Slot ohne Tibber-Update auf den
EPEX-Börsenpreis-Fallback zurück → Sprünge zwischen ~35 ct
(Endkundenpreis) und ~10 ct (Spotmarkt).

Fix: letzten Sensor-Wert vor Slot-Ende als Carry-Forward nehmen
(Step-Funktion-Semantik).
"""

from __future__ import annotations

from datetime import datetime, timedelta


def _simulate_strompreis_slot(
    pts: list[tuple[datetime, float]],
    h_start: datetime,
    h_end: datetime,
    boersenpreis: float | None,
) -> float | None:
    """Replikat der Slot-Logik aus live_tagesverlauf_service (Strompreis-Block)."""
    h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
    if h_pts:
        return round(sum(h_pts) / len(h_pts), 2)
    vorherige = [p[1] for p in pts if p[0] < h_end]
    if vorherige:
        return round(vorherige[-1], 2)
    if boersenpreis is not None:
        return boersenpreis
    return None


def test_tibber_15min_carry_forward_zwischen_updates():
    """Tibber-Updates alle 15 Min, 10-Min-Slots → 2/3 der Slots ohne
    Update darin. Carry-Forward muss den vorherigen Wert halten."""
    base = datetime(2026, 5, 17, 22, 0)
    # Tibber-Step-Werte (in ct/kWh nach Einheit-Normalisierung)
    pts = [
        (base, 38.3),                    # 22:00 — neuer Block
        (base + timedelta(minutes=15), 37.4),   # 22:15
        (base + timedelta(minutes=30), 36.5),   # 22:30
        (base + timedelta(minutes=45), 36.2),   # 22:45
    ]
    # 10-Min-Slots ab 22:00
    slots = [(base + timedelta(minutes=i), base + timedelta(minutes=i + 10)) for i in range(0, 60, 10)]
    werte = [_simulate_strompreis_slot(pts, s, e, boersenpreis=8.0) for s, e in slots]

    # Erwartete Werte: Tibber-Step-Funktion über 60 Min
    # 22:00-22:10 → Update um 22:00 IN Slot → 38.3
    # 22:10-22:20 → Update um 22:15 IN Slot → 37.4
    # 22:20-22:30 → KEIN Update IN Slot, vorher 37.4 → Carry-Forward 37.4 (vor Fix: 8.0)
    # 22:30-22:40 → Update um 22:30 IN Slot → 36.5
    # 22:40-22:50 → Update um 22:45 IN Slot → 36.2
    # 22:50-23:00 → KEIN Update IN Slot, vorher 36.2 → Carry-Forward 36.2 (vor Fix: 8.0)
    erwartet = [38.3, 37.4, 37.4, 36.5, 36.2, 36.2]
    assert werte == erwartet, f"Erwartet {erwartet}, war {werte}"


def test_kein_sensor_punkt_fuer_tag_falleback_epex():
    """Wenn der Sensor noch gar keinen Punkt geliefert hat (Day-Ahead vor
    Mitternacht), wird EPEX-Börsenpreis als Fallback genutzt."""
    base = datetime(2026, 5, 17, 0, 0)
    pts: list[tuple[datetime, float]] = []  # gar keine Tibber-Punkte
    slot_start = base
    slot_end = base + timedelta(minutes=10)
    wert = _simulate_strompreis_slot(pts, slot_start, slot_end, boersenpreis=10.5)
    assert wert == 10.5, f"EPEX-Fallback erwartet (10.5), war {wert}"


def test_sensor_punkt_vor_slot_aber_kein_epex_kein_neuer_punkt():
    """Sensor hat Punkt vor dem Slot, kein neuer Punkt im Slot, kein EPEX
    → Carry-Forward des Sensor-Werts."""
    base = datetime(2026, 5, 17, 12, 0)
    pts = [(base - timedelta(minutes=20), 25.0)]  # 11:40
    slot_start = base
    slot_end = base + timedelta(minutes=10)
    wert = _simulate_strompreis_slot(pts, slot_start, slot_end, boersenpreis=None)
    assert wert == 25.0, f"Carry-Forward erwartet (25.0), war {wert}"


def test_mehrere_punkte_im_slot_werden_gemittelt():
    """Sehr seltener Fall: mehrere Step-Wechsel in einem 10-Min-Slot —
    bestehende Logik mitteln bleibt unverändert."""
    base = datetime(2026, 5, 17, 8, 0)
    pts = [
        (base, 30.0),
        (base + timedelta(minutes=3), 32.0),
        (base + timedelta(minutes=7), 34.0),
    ]
    slot_start = base
    slot_end = base + timedelta(minutes=10)
    wert = _simulate_strompreis_slot(pts, slot_start, slot_end, boersenpreis=None)
    assert wert == 32.0, f"Mittelwert (30+32+34)/3=32, war {wert}"


def test_regression_punkt_im_slot_nutzt_keinen_carry_forward():
    """Wenn der Slot einen Punkt enthält, wird NICHT auf carry-forward
    zurückgegriffen (Punkt-im-Slot hat Vorrang)."""
    base = datetime(2026, 5, 17, 10, 0)
    pts = [
        (base - timedelta(minutes=15), 100.0),  # alter Wert
        (base + timedelta(minutes=2), 50.0),    # neuer Wert IM Slot
    ]
    slot_start = base
    slot_end = base + timedelta(minutes=10)
    wert = _simulate_strompreis_slot(pts, slot_start, slot_end, boersenpreis=None)
    assert wert == 50.0, f"Punkt-im-Slot hat Vorrang, erwartet 50.0, war {wert}"
