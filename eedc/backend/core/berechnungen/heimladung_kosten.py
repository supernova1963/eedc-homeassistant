"""Stromkosten der Heimladung eines E-Autos — eine kWh ist einmal Geld (N-672).

Single Source of Truth für den Strom-Posten der **E-Auto-Ersparnis gegenüber dem
Verbrenner**. Die Ersparnis ist überall

    Kosten des Vergleichs-Verbrenners − Stromkosten der Ladung − ggf. Tankrechnung (PHEV)

und die Stromkosten der Heimladung sind

    Netzladung × Netzladungspreis  +  PV-Ladung × Preis der Eigenverbrauchs-Ersparnis

**Warum die PV-Ladung nicht kostenlos ist.** Dieselbe Kilowattstunde steht schon auf
der PV-Seite: Die Eigenverbrauchs-Ersparnis bewertet den **ganzen** Eigenverbrauch
der Anlage — der Strom, den die Wallbox aus der Anlage zieht, steckt darin. Bis
N-672 (11.10.2026) setzte die E-Auto-Zeile ihn zusätzlich „kostenlos" an, er war
also zweimal Geld. Gemessen an einer Beispielanlage (PV 1000, Einspeisung 400,
E-Auto 400 kWh davon 200 aus PV, 30 ct, Verbrenner 7,5 l/100 km × 1,65 €/l):
*Auswertungen → ROI* und *Cockpit → Jahr* nannten 399,50 € statt 339,50 € — die
Differenz ist genau 200 kWh × 30 ct. Die Gegenrechnung gegen die Referenz „ohne
PV, mit Verbrenner" (Erlös + Eigenverbrauch × Preis + Benzin − **ganze** Ladung ×
Preis) ergibt 339,50 €.

**Welcher Preis die PV-Ladung trägt** (Entscheid Master 11.10.2026): genau der
Preis, zu dem die Eigenverbrauchs-Ersparnis **derselben Sicht** diese kWh
gutschreibt — belastet = gutgeschrieben, sonst bleibt die Differenz doppelt. Das
ist im Monat der Preis der Eigenverbrauchs-Ersparnis (gepflegt · gemessen ·
Zeitfenster · Stamm, seit N-669 der Preis der vermiedenen Stunden), in der Prognose
der Strompreis, mit dem die Prognose den Eigenverbrauch bewertet. Die **Netzladung**
behält ihren Preis (den Wallbox-Tarif, wo es einen gibt) — sie ist ein Bezug, kein
Eigenverbrauch.

Wer den PV-Anteil anzeigt („davon aus PV x kWh"), zeigt eine **Information** —
keinen eigenen Geldposten.

Dieselbe Regel gilt für die Wärmepumpe seit N-459 (ADR-002/P9: „der PV-Anteil eines
Verbrauchers senkt dessen Stromkosten nicht — er ist als Eigenverbrauch gebucht").
Die dienstlichen Ladekosten (`dienstliche_ladekosten.py`) rechnen seit jeher so.
"""

from __future__ import annotations


def heimladung_stromkosten_euro(
    *,
    netz_kwh: float,
    netz_preis_cent: float,
    pv_kwh: float,
    pv_preis_cent: float,
) -> float:
    """Stromkosten der Heimladung in € — Netz zum Netzladungspreis, PV zum Eigenverbrauchspreis.

    Beide Mengen werden nach unten bei 0 geklemmt (eine negative Ladung ist ein
    Erfassungsfehler, kein Ertrag) — dieselbe Klemme, die bisher auf der Netzladung saß.

    Args:
        netz_kwh: Heim-Netzladung in kWh.
        netz_preis_cent: Preis der Netzladung in ct/kWh (Wallbox-Tarif, sonst allgemein).
        pv_kwh: Heim-PV-Ladung in kWh (inkl. Ladung aus dem Speicher — PV = Direkt + Speicher).
        pv_preis_cent: Preis, mit dem die Eigenverbrauchs-Ersparnis derselben Sicht
            diese kWh gutschreibt, in ct/kWh.
    """
    return (
        max(0.0, netz_kwh) * netz_preis_cent / 100
        + max(0.0, pv_kwh) * pv_preis_cent / 100
    )
