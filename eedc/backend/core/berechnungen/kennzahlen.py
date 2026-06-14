"""Kern-Kennzahlen Autarkie / Eigenverbrauchsquote / spezifischer Ertrag
(Schläfer-Abbau Block 3).

Single Source of Truth für die drei Quoten-/Ertrags-Primitive, vorher über die
Codebase verstreut inline dupliziert (calculations, verbrauch, aussichten,
investitionen/dashboards, cockpit/social, cockpit/nachhaltigkeit, pdf-builder).
Reine Arithmetik, DB-/Service-frei (ADR-001).

Maintainer-Entscheid (2026-06-14): die **Eigenverbrauchsquote wird überall auf
100 % gecappt** (`min(…, 100)`) — vorher cappten manche Sites nicht (u. a. der
Aussichten-Forecast), was rechnerisch >100 % zeigen konnte. Das ist ein
Bugfix, release-note-pflichtig.

Bewusst NICHT migriert: `energie_profil/views.py` (Tages-Autarkie mess-seitig,
offener IA-V4-Phase-1A-Produktentscheid) und die `live_*`-Sites (kW statt kWh).
"""

from __future__ import annotations

from typing import Optional


def autarkie_prozent(eigenverbrauch_kwh: float, gesamtverbrauch_kwh: float) -> float:
    """Autarkiegrad in % = Eigenverbrauch / Gesamtverbrauch × 100.

    Strukturell ≤ 100 % (Eigenverbrauch ist Teilmenge des Gesamtverbrauchs),
    daher ungecappt. 0.0 wenn kein Gesamtverbrauch. Ungerundet — der Aufrufer
    rundet wie bisher selbst.
    """
    if gesamtverbrauch_kwh <= 0:
        return 0.0
    return eigenverbrauch_kwh / gesamtverbrauch_kwh * 100


def eigenverbrauchsquote_prozent(eigenverbrauch_kwh: float, pv_erzeugung_kwh: float) -> float:
    """Eigenverbrauchsquote in % = Eigenverbrauch / PV-Erzeugung × 100, **auf
    100 % gecappt**.

    Cap (Maintainer-Entscheid 2026-06-14): Drift zwischen Eigenverbrauchs- und
    Erzeugungs-Quelle kann rechnerisch >100 % ergeben — das ist nie eine echte
    Quote. 0.0 wenn keine Erzeugung. Ungerundet.
    """
    if pv_erzeugung_kwh <= 0:
        return 0.0
    return min(eigenverbrauch_kwh / pv_erzeugung_kwh * 100, 100.0)


def spezifischer_ertrag_kwh_kwp(
    erzeugung_kwh: float, leistung_kwp: Optional[float]
) -> Optional[float]:
    """Spezifischer Ertrag in kWh/kWp = Erzeugung / installierte Leistung.

    `None` wenn keine Leistung bekannt (Division undefiniert) — Aufrufer mit
    `float`-Feld nutzen `… or 0`. Ungerundet.
    """
    if not leistung_kwp or leistung_kwp <= 0:
        return None
    return erzeugung_kwh / leistung_kwp
