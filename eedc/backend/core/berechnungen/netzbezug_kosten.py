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


def berechne_netzbezug_kosten(
    netzbezug_kwh: float,
    netzbezug_preis_cent: float,
    grundpreis_euro_monat: float = 0.0,
) -> float:
    """Netzbezugskosten der Periode in Euro.

    Args:
        netzbezug_kwh: aus dem Netz bezogene Energie (kWh).
        netzbezug_preis_cent: Arbeitspreis in ct/kWh.
        grundpreis_euro_monat: monatlicher Grundpreis in Euro (default 0.0).

    Returns:
        `netzbezug_kwh × preis_ct / 100 + grundpreis` — ungerundet; der Aufrufer
        rundet wie bisher selbst.
    """
    return netzbezug_kwh * netzbezug_preis_cent / 100 + grundpreis_euro_monat
