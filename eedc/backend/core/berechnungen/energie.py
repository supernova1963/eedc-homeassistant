"""Energie-Aggregate aus den zentralen Tabellen.

Single Source of Truth für:
- Whitelist-Prefixe für PV-Erzeugungs-Komponenten in komponenten_kwh
- Tages-Summen aus dem komponenten_kwh-JSON

Konsumenten importieren ausschließlich aus diesem Modul, NICHT inline
re-implementieren. Konformitäts-Test prüft, dass die Prefix-Tuple bzw.
Inline-`startswith("pv_")`-Patterns außerhalb dieses Layers nicht auftauchen.
"""

from __future__ import annotations

from typing import Optional


# ─── Whitelist-Konstante (SoT) ──────────────────────────────────────────────

# Komponenten-Keys in TagesZusammenfassung.komponenten_kwh, die zur PV-
# Tageserzeugung beitragen. Ein neues PV-Präfix (z. B. `wr_`) muss hier
# ergänzt werden — sonst zählen Daten-Checker, Drift-Check, Genauigkeits-
# Tracking und Reparatur-Werkbank ihn nicht mit.
#
# Vor Hinzufügen eines neuen Präfixes prüfen:
# - Wird der Boundary-Pfad (lts_aggregator.py:237+ oder snapshot/aggregator.py)
#   diesen Präfix tatsächlich schreiben?
# - Ist das Naming-Schema zwischen Live-Tagesverlauf-Service
#   (live_sensor_config.TV_SERIE_CONFIG → live_tagesverlauf_service:148) und
#   Boundary-Aggregator identisch? Bei Mismatch entsteht Doppelzählung
#   (BKW-Bug 2026-05-19, Rainer-PN).
PV_KOMPONENTEN_PREFIXE: tuple[str, ...] = ("pv_", "bkw_")


# ─── Σ-Helper ───────────────────────────────────────────────────────────────


def summe_pv_bkw_kwh(komponenten_kwh: Optional[dict]) -> float:
    """Tages-PV-Σ aus dem JSON-Feld `TagesZusammenfassung.komponenten_kwh`.

    Whitelist auf `PV_KOMPONENTEN_PREFIXE`, nur positive Werte
    (Verbraucher-Sub-Keys mit negativem Vorzeichen werden ignoriert).
    """
    if not komponenten_kwh:
        return 0.0
    return sum(
        float(v)
        for k, v in komponenten_kwh.items()
        if isinstance(v, (int, float))
        and v > 0
        and any(k.startswith(p) for p in PV_KOMPONENTEN_PREFIXE)
    )
