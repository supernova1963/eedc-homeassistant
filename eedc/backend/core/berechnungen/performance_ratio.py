"""Performance Ratio eines Tages — die eine Formel (ADR-001).

PR = IST-Ertrag ÷ (GTI × kWp ÷ 1000). Der Nenner ist die Einstrahlung auf der
**geneigten Modulfläche** (Wh/m²), nicht die waagerechte (#139: mit GHI liefen
PR-Werte im Winter auf 1,5–2,8); die kWp sind die der an diesem Tag aktiven
Erzeuger (F-58), nicht der zeitlose Anlagen-Skalar.

Bis 05.09.2026 stand die Rechnung nur im Aggregator. Der Wetter-Nachzug für
den Altbestand (N-388) braucht sie ein zweites Mal — mit denselben Zutaten,
ohne den Tag neu zu aggregieren. Zwei Fassungen derselben Formel wären genau
die Klasse, aus der die Drift-Inventur vom 31.07. entstand.
"""

from __future__ import annotations

from typing import Optional


def berechne_performance_ratio(
    pv_ertrag_kwh: Optional[float],
    gti_summe_wh_m2: Optional[float],
    kwp: Optional[float],
) -> Optional[float]:
    """IST ÷ theoretisch — ``None``, wo eine Zutat fehlt.

    ``None`` statt 0 ist Absicht (ADR-002/P4): ohne Einstrahlung, ohne kWp
    oder ohne eine einzige gemessene PV-Stunde gibt es keine Aussage über die
    Anlage — eine 0,0 sähe aus wie eine katastrophale Messung und ließe den
    Daten-Checker „auffällig niedrig" melden (Forum kaba-kakao 2026-08-07).
    """
    if pv_ertrag_kwh is None or kwp is None or gti_summe_wh_m2 is None:
        return None
    if kwp <= 0 or gti_summe_wh_m2 <= 0:
        return None
    theoretisch_kwh = gti_summe_wh_m2 * kwp / 1000  # Wh/m² × kWp / 1000
    if theoretisch_kwh <= 0:
        return None
    return round(pv_ertrag_kwh / theoretisch_kwh, 3)
