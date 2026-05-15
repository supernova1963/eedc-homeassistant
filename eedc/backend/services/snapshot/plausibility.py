"""
Plausibilitäts-Caps für Counter-basierte Energie-Werte.

Counter-Spikes (Off-by-one nach HA-Restarts, vgl. #200) liefern Stunden-kWh
weit jenseits der physikalischen Leistung der Anlage. Beispiel-Bug aus dem
Forum (dietmar1968, 14.05.2026): pv_kw=109 kW um 11:00 bei 11.2 kWp-Anlage —
6× über Anlagengrenze.

Vor v3.30.2 hat der Daten-Checker solche Spikes nur *detektiert*, aber der
Aggregator schrieb sie ungekappt in `TagesEnergieProfil.pv_kw`. Reaggregation
war idempotent gegen Roh-Snapshots und konnte den Spike nicht heilen.

Dieser SoT-Helper teilt eine einzige Schwellen-Definition zwischen Aggregator
(präventiver Cap) und Daten-Checker (Detektor). Damit gilt: was der Aggregator
nicht kappt, sieht der Checker nicht — und umgekehrt.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Schwelle pro Stunde = leistung_kwp × Faktor.
# 1.5 toleriert kurze Mess-Peaks (Wechselrichter-Überlast, Kalibrierungs-
# Toleranz), blockt klare Counter-Off-by-ones (≥ 2× Anlagenleistung).
SPIKE_FAKTOR_STUNDE = 1.5


def schwelle_pv_einspeisung_stunde_kwh(kwp: Optional[float]) -> Optional[float]:
    """
    Maximaler plausibler Stunden-kWh-Wert für PV oder Einspeisung.

    Returns None falls kwp nicht bekannt/0 — dann findet kein Cap statt
    (z. B. Anlagen ohne PV-Leistungs-Eintrag im Setup).
    """
    if kwp is None or kwp <= 0:
        return None
    return float(kwp) * SPIKE_FAKTOR_STUNDE


def cap_pv_einspeisung_stunde(
    wert_kwh: Optional[float],
    schwelle_kwh: Optional[float],
    *,
    anlage_id: int,
    datum,
    stunde: int,
    kategorie: str,
) -> Optional[float]:
    """
    Cappt einen Stunden-kWh-Wert für PV oder Einspeisung gegen Plausibilität.

    Returns:
        None falls der Wert die Schwelle überschreitet (Lücken-Semantik —
        Stundenzeile bleibt leer, weitere Read-Sites filtern None bereits).
        Sonst unveränderter Wert.

    Logs eine WARNING beim Cap, damit Operator-Logs den Bereinigungs-
    Aufruf nachvollziehen können.
    """
    if wert_kwh is None or schwelle_kwh is None:
        return wert_kwh
    if abs(wert_kwh) <= schwelle_kwh:
        return wert_kwh
    logger.warning(
        "Counter-Spike geklemmt: anlage=%s %s h=%02d %s=%.1f kWh > Schwelle %.1f kWh → None",
        anlage_id, datum, stunde, kategorie, wert_kwh, schwelle_kwh,
    )
    return None
