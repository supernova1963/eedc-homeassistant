"""Relevante Kosten einer Anlage — die EINE Definition von „Mehrkosten".

Was hat eine Anschaffung **gegenüber ihrer Alternative** gekostet? Diese Frage
stellen im Baum drei Größen, und bis 2026-08-04 gab jede eine eigene Antwort:

- die **USt-Bemessungsgrundlage** (Selbstkosten je kWh, § 3 Abs. 1b UStG),
- der **Amortisations-Fortschritt** („wie viel von der Investition ist drin?"),
- die **Amortisationsdauer** in *Auswertungen → ROI*.

N-129/N-130 haben die erste am 04.08. auf `Σ max(0, gesamt − alternativ)`
festgelegt (Entscheid Gernot). Die beiden anderen liefen weiter auf eigenen
Summen — namentlich die **Hybrid-Summe** `PV-System voll + WP-/eAuto-Mehrkosten
+ Sonstiges voll`, die in `aussichten.py` und `cockpit/uebersicht.py` doppelt
stand und ihre Mehrkosten aus `parameter["alternativ_kosten_euro"]` las: einem
Schlüssel, der **baumweit keinen Schreiber hat** (Fund N-134). Sie fiel damit
immer auf die Festannahmen 8.000 € / 35.000 € zurück und ignorierte genau das
Feld, das der Daten-Checker mit WARNING einfordert
(`anschaffungskosten_alternativ`, „*werden für ROI-Berechnung benötigt*").

Seit N-137 ist es **eine** Definition für alle drei. Der Name hier ist
neutral, `ust_eigenverbrauch.bemessungsgrundlage_aus_investitionen` delegiert
hierher — zwei Namen für denselben Wert, weil das Steuerrecht ihn anders nennt
als die Wirtschaftlichkeitsrechnung.

**Warum die Klemmung je Position** (`max(0, …)` statt `Σ gesamt − Σ alternativ`):
eine Anschaffung, deren Alternative *teurer* gewesen wäre, hat keine negativen
Mehrkosten — sie senkt die Grundlage nicht, sie trägt 0 bei. Sonst könnte ein
einzelnes günstiges Gerät die relevanten Kosten der ganzen Anlage drücken und
der Amortisations-Fortschritt spränge über 100 %.
"""

from __future__ import annotations

from typing import Iterable


def relevante_kosten_aus_investitionen(investitionen: Iterable) -> float:
    """Mehrkosten der Anlage: ``Σ max(0, gesamt − alternativ)``.

    ``investitionen`` wird nur per ``getattr`` gelesen — kein ORM-Import,
    ADR-001 bleibt gewahrt. Fehlende Alternativkosten zählen als 0, die
    Position geht dann mit ihren Vollkosten ein (der Normalfall bei PV,
    Speicher und Wechselrichter, wo es keine Alternative gibt).
    """
    summe = 0.0
    for inv in investitionen:
        gesamt = getattr(inv, "anschaffungskosten_gesamt", None) or 0.0
        alternativ = getattr(inv, "anschaffungskosten_alternativ", None) or 0.0
        summe += max(0.0, gesamt - alternativ)
    return summe
