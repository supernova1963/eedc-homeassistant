"""Kern-Kennzahlen Autarkie / Eigenverbrauchsquote / spezifischer Ertrag
(Schläfer-Abbau Block 3).

Single Source of Truth für die drei Quoten-/Ertrags-Primitive, vorher über die
Codebase verstreut inline dupliziert (calculations, verbrauch, aussichten,
investitionen/dashboard_* (bis 18.09.2026 dashboards.py), cockpit/social (2026-07-31 zurückgebaut),
cockpit/nachhaltigkeit, pdf-builder).
Reine Arithmetik, DB-/Service-frei (ADR-001).

Maintainer-Entscheid (2026-06-14): die **Eigenverbrauchsquote wird überall auf
100 % gecappt** (`min(…, 100)`) — vorher cappten manche Sites nicht (u. a. der
Aussichten-Forecast), was rechnerisch >100 % zeigen konnte. Das ist ein
Bugfix, release-note-pflichtig.

Die `live_*`-Sites (kW statt kWh) rufen seit Päckchen Z1a (9.11.2026) dieselben Helfer —
die Quoten sind dimensionslos, kW-Eingänge sind erlaubt. ⚠ Hier stand bis
18.09.2026 auch `energie_profil/views.py` („Tages-Autarkie mess-seitig, offener
IA-V4-Phase-1A-Produktentscheid“) — Monatsauswertung und Tagesprognose rufen
längst die beiden Helfer hier; beim Umzug der Datei in Module (Vorlage 4)
gemessen: 0 Inline-Treffer, die Wächter-Ausnahme ist gestrichen.
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


def eigenverbrauchsquote_prozent(
    eigenverbrauch_kwh: float, pv_erzeugung_kwh: float, *, kappen: bool = True
) -> float:
    """Eigenverbrauchsquote in % = Eigenverbrauch / PV-Erzeugung × 100, **auf
    100 % gecappt**.

    Cap (Maintainer-Entscheid 2026-06-14): Drift zwischen Eigenverbrauchs- und
    Erzeugungs-Quelle kann rechnerisch >100 % ergeben — das ist nie eine echte
    Quote. 0.0 wenn keine Erzeugung. Ungerundet.

    ``kappen=False`` (Päckchen Z1a): der Live-Gauge (``live_komponenten_builder._autarkie_gauges``)
    kappt selbst mit ``round(min(quote, 100), 0)`` — mit vorgekappter Quote käme dort bei Kappung
    ``100.0`` statt ``100`` heraus (Typ der JSON-Zahl, GM bitgleich). Die Zahl ist dieselbe.
    """
    if pv_erzeugung_kwh <= 0:
        return 0.0
    quote = eigenverbrauch_kwh / pv_erzeugung_kwh * 100
    return min(quote, 100.0) if kappen else quote


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


def netto_kwh(
    erzeugung_kwh: Optional[float], verbrauch_kwh: Optional[float]
) -> Optional[float]:
    """«Netto» eines Zeitraums = Erzeugung − Verbrauch: Überschuss (+) oder Defizit (−), vor dem Speicher
    (Päckchen Z-Client, 9.11.2026).

    Die Σ-Zeile «Netto» der Tagesprognose (*Auswertungen → Energieprofil*, Prognose) auf den beiden Tagessummen der
    Antwort; bis dahin rechnete der Client sie. ``None``, sobald ein Operand fehlt (ohne Verbrauchsprognose, A28).
    Ungerundet — die Summen sind es schon.
    """
    if erzeugung_kwh is None or verbrauch_kwh is None:
        return None
    return erzeugung_kwh - verbrauch_kwh
