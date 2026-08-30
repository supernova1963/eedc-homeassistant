"""Kern-Kennzahlen Autarkie / Eigenverbrauchsquote / spezifischer Ertrag
(Schläfer-Abbau Block 3).

Single Source of Truth für die drei Quoten-/Ertrags-Primitive, vorher über die
Codebase verstreut inline dupliziert (calculations, verbrauch, aussichten,
investitionen/dashboards, cockpit/social (2026-07-31 zurückgebaut),
cockpit/nachhaltigkeit, pdf-builder).
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
    erzeugung_kwh: Optional[float], leistung_kwp: Optional[float]
) -> Optional[float]:
    """Spezifischer Ertrag in kWh/kWp = Erzeugung / installierte Leistung.

    `None` wenn **einer der beiden Operanden fehlt** — Aufrufer mit `float`-Feld
    nutzen `… or 0`. Ungerundet.

    ⛔ **Der `None`-Zweig des ZÄHLERS ist seit N-355 da, und er ist keine
    Symmetrie-Kosmetik.** Bis dahin deckte die Regel nur den Nenner ab; der
    Docstring sagte „`None` wenn keine Leistung bekannt", und `aktueller_monat.py`
    reichte `pv or 0` herein. Ein Monat **ohne gemessene PV-Zahl** bekam damit
    `0,0 kWh/kWp` — eine Zahl, die wie eine Messung aussieht und die eigene
    Anzeige-Doktrin verletzt (*nie gemessen ⇒ ausblenden, keine erfundene Null*).
    Eine Division braucht **beide** Operanden; wer nur den Nenner prüft, hat die
    halbe Frage gestellt.

    ⚠ **Für die sechs Aufrufer mit `float`-Zähler ändert sich nichts** — sie
    können gar kein `None` hereinreichen (gemessen 30.08.2026: `jahresbericht`
    2×, `calculations`, `aussichten`, `dashboards` lesen Dataclass-Felder bzw.
    Summen). Der Zweig greift genau dort, wo bisher ein `or 0` stand.
    """
    if erzeugung_kwh is None:
        return None
    if not leistung_kwp or leistung_kwp <= 0:
        return None
    return erzeugung_kwh / leistung_kwp
