"""Drift-Guard: Backend-Tagesverlauf-Farben == Frontend-Farb-Kanon (Regel A/B).

Die Live-/Tagesverlauf-Serienfarben kommen aus dem Backend (``TV_SERIE_CONFIG``
+ inline in ``live_tagesverlauf_service``) und wurden historisch von der
Frontend-SoT ``eedc/frontend/src/lib/colors.ts`` weggedriftet (PV gelb statt
Amber, Netzbezug Signal-Rot statt Dunkelrot, Einspeisung Cyan, Haushalt =
Einspeisung-Emerald, E-Auto = Wallbox). Regel-A/-B-Slice 2026-06-24 hat sie
kanonisiert; dieser Test friert den Kanon ein, damit eine künftige Backend-
Änderung NICHT still wieder driftet ([[feedback_aggregations_drift]]).

Quelle der Wahrheit = ``colors.ts``: COLORS (F1/F2/F4) + KOMPONENTEN_FARBEN
(Regel A). Werte hier bewusst dupliziert (Python kann TS nicht importieren) —
genau DAS macht der Test sichtbar: stimmen beide Seiten überein?
"""
from __future__ import annotations

from pathlib import Path

from backend.services.live_sensor_config import TV_SERIE_CONFIG

# ── Kanon aus eedc/frontend/src/lib/colors.ts (bei Änderung dort HIER mitziehen) ──
# COLORS: solar=#f59e0b (F1) · grid=#b91c1c (F2) · battery=#3b82f6 · feedin=#10b981 (F4)
# KOMPONENTEN_FARBEN: e-auto=#14b8a6 · wallbox=#06b6d4 · waermepumpe=#ef4444 · sonstiges=#6b7280
KANON_TYP_FARBE = {
    "pv-module": "#f59e0b",
    "balkonkraftwerk": "#f59e0b",   # im Tagesverlauf Kategorie "pv" → PV-Amber
    "speicher": "#3b82f6",
    "wallbox": "#06b6d4",
    "e-auto": "#14b8a6",
    "waermepumpe": "#ef4444",
    "sonstiges": "#6b7280",
}

# Inline-Serienfarben im Service (virtuelle Serien + WP-Warmwasser-Split)
KANON_PV_GESAMT = "#f59e0b"
KANON_NETZBEZUG = "#b91c1c"
KANON_EINSPEISUNG = "#10b981"
KANON_HAUSHALT = "#64748b"
KANON_WP_WARMWASSER = "#3b82f6"   # blau (= CHART_COLORS.wpWarmwasser; Gernot 2026-06-25 nach detLAN „Wasser=blau")

_BACKEND = Path(__file__).resolve().parents[1]
_SERVICE = (_BACKEND / "services" / "live_tagesverlauf_service.py").read_text(encoding="utf-8")
# Dritte Farbquelle: Demo-Generatoren (Dev-Box/?demo=true) — müssen denselben Kanon tragen.
_DEMO = (_BACKEND / "api" / "routes" / "live_dashboard.py").read_text(encoding="utf-8")


def test_tv_serie_config_farben_kanonisch():
    """TV_SERIE_CONFIG pro Investitionstyp == Farb-Kanon (importierbar, exakt)."""
    for typ, erwartet in KANON_TYP_FARBE.items():
        assert TV_SERIE_CONFIG[typ]["farbe"] == erwartet, (
            f"{typ}: {TV_SERIE_CONFIG[typ]['farbe']} != Kanon {erwartet} "
            f"(colors.ts driftet — beide Seiten angleichen)"
        )


def test_eauto_und_wallbox_distinkt():
    """Kern-Bug Regel A: E-Auto und Wallbox dürfen NICHT dieselbe Farbe haben."""
    assert TV_SERIE_CONFIG["e-auto"]["farbe"] != TV_SERIE_CONFIG["wallbox"]["farbe"]


def test_service_virtuelle_serien_farben_kanonisch():
    """Inline-Serienfarben im Service (PV-Gesamt/Netz/Einspeisung/Haushalt/WW) == Kanon."""
    for hex_wert, rolle in [
        (KANON_PV_GESAMT, "PV-Gesamt"),
        (KANON_NETZBEZUG, "Netzbezug"),
        (KANON_EINSPEISUNG, "Einspeisung"),
        (KANON_HAUSHALT, "Haushalt"),
        (KANON_WP_WARMWASSER, "WP-Warmwasser"),
    ]:
        assert hex_wert in _SERVICE, f"{rolle}-Kanon {hex_wert} fehlt im Service (Drift?)"


def test_service_keine_legacy_drift_hexes():
    """Die alten weggedrifteten Hex dürfen NICHT mehr im Service stehen."""
    for legacy, rolle in [
        ("#eab308", "PV gelb (alt, F1)"),
        ("#a855f7", "E-Auto/Wallbox identisch (alt)"),
    ]:
        assert legacy not in _SERVICE, f"Legacy-Farbe {legacy} ({rolle}) noch im Service"


def test_demo_generator_farben_kanonisch():
    """Demo-Tagesverlauf (Dev-Box/?demo=true) trägt den Kanon, NICHT die alte Identitäts-Drift."""
    for legacy, rolle in [
        ("#eab308", "PV gelb (alt)"),
        ("#a855f7", "Wallbox/E-Auto lila (alt)"),
        ("#f97316", "WP orange (alt)"),
    ]:
        assert legacy not in _DEMO, f"Legacy-Farbe {legacy} ({rolle}) noch im Demo-Generator"
    for hex_wert, rolle in [
        (KANON_PV_GESAMT, "PV"),
        (KANON_NETZBEZUG, "Netz"),
        (KANON_HAUSHALT, "Haushalt"),
        ("#06b6d4", "Wallbox cyan"),
        ("#ef4444", "WP rot"),
    ]:
        assert hex_wert in _DEMO, f"{rolle}-Kanon {hex_wert} fehlt im Demo-Generator (Drift?)"
