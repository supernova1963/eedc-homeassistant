"""Netzbezugskosten = Arbeitspreis × kWh + Grundpreis (Schläfer-Abbau Block 2).

Single Source of Truth für die Formel `netzbezug_kwh × preis_ct/100 +
grundpreis_euro`, vorher in fünf Sites inline dupliziert (cockpit/komponenten,
cockpit/uebersicht, aktueller_monat ×2, core/calculations). Reine Arithmetik,
DB-/Service-frei (ADR-001).

Drift-Risiko, das hier getilgt wird: der monatliche **Grundpreis** wird
leicht vergessen oder versehentlich auf eine Ersparnis statt auf die Kosten
addiert. Die reine `kWh × preis/100`-Multiplikation (ohne Grundpreis, z. B.
Eigenverbrauchs-Ersparnis) ist eindeutig und bleibt bewusst inline.
"""

from __future__ import annotations

from typing import Sequence


def berechne_netzbezug_kosten(
    netzbezug_kwh: float,
    netzbezug_preis_cent: float,
    grundpreis_euro_monat: float = 0.0,
    anteile: Sequence[tuple[float, float]] = (),
) -> float:
    """Netzbezugskosten der Periode in Euro.

    Args:
        netzbezug_kwh: aus dem Netz bezogene Energie (kWh).
        netzbezug_preis_cent: Arbeitspreis in ct/kWh.
        grundpreis_euro_monat: monatlicher Grundpreis in Euro (default 0.0).
        anteile: N-770/N-771 (30.10.2026) — ``(kWh, ct/kWh)`` je Teil des Netzbezugs, den der Versorger zu einem
            EIGENEN Komponenten-Tarif abrechnet (Netzbezug zum WP- bzw. Wallbox-Tarif, bereits geklemmt:
            ``klemme_netzanteil``). Der Rest des Netzbezugs trägt ``netzbezug_preis_cent``.

    Returns:
        Ohne Anteile `netzbezug_kwh × preis_ct / 100 + grundpreis` (bitgleich wie bis dahin); mit Anteilen
        `(netzbezug − Σ N) × preis / 100 + Σ N × ct_N / 100 + grundpreis` — ungerundet; der Aufrufer rundet selbst.
    """
    if not anteile:
        return netzbezug_kwh * netzbezug_preis_cent / 100 + grundpreis_euro_monat
    rest_kwh = netzbezug_kwh - sum(kwh for kwh, _cent in anteile)
    return (
        rest_kwh * netzbezug_preis_cent / 100
        + sum(kwh * cent / 100 for kwh, cent in anteile)
        + grundpreis_euro_monat
    )


def klemme_netzanteil(gemessen_kwh: float, menge_kwh: float, rest_netzbezug_kwh: float) -> float:
    """N-770/N-771 (Bauplan F7): ein gemessener Netzbezug zum Komponenten-Tarif auf ``[0, min(Menge, Netzbezug-Rest)]``.

    Mehr, als das Gerät verbraucht bzw. geladen hat (``menge_kwh``), oder mehr, als der Netzbezug der Anlage noch trägt
    (``rest_netzbezug_kwh`` — bei WP und Wallbox zusammen der Rest nach der WP), kann der Versorger nicht zum
    Komponenten-Tarif abgerechnet haben; die Herleitung sagt, wenn geklemmt wurde."""
    return max(0.0, min(gemessen_kwh, menge_kwh, rest_netzbezug_kwh))
