"""Temperatur-Größen der Wärmepumpe — eine Formel, ein Ort (P-433-3, ADR-001).

**Spreizung** = Vorlauf − Rücklauf in K. Heute gerufen vom Live-Builder für den Augenblickswert am
Wärmepumpen-Knoten (`services/live_komponenten_builder._wp_geraete_werte`, P-433-3 S1); das Tagesmittel der
Tagessicht (S3) ruft dieselbe Differenz. Der Client rechnet sie nicht nach, er zeigt `spreizung_k` an.
"""

from __future__ import annotations

from typing import Optional


def spreizung_k(vorlauf_c: Optional[float], ruecklauf_c: Optional[float]) -> Optional[float]:
    """Vorlauf − Rücklauf in K; `None`, wenn einer der beiden fehlt (keine erfundene 0, P4).

    Ungerundet — die Rundung gehört dem Aufrufer (Live: eine Nachkommastelle wie die Temperaturen).
    """
    if vorlauf_c is None or ruecklauf_c is None:
        return None
    return vorlauf_c - ruecklauf_c
