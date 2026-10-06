"""Kosten einer Stunde bei gemessenem Stundenpreis — die Regel der Kosten-Kanäle (HA-Bauform E4e, Konzept §1 Nr. 5).

**HAs Kostensensor-Muster:** das Energie-Dashboard führt je Quelle einen Kostensensor, der ``Δ kWh × Preis`` je Stunde
aufsummiert; der gewichtete Ø eines Zeitraums ist dann ``Δ Kosten ÷ Δ kWh``. eedc führt dieselben Summen als
abgeleitete kumulative Kanäle (``services/kanal/kosten.py``); diese Funktion ist die EINE Rechnung einer Stunde, aus
der sie fortgeschrieben werden.

**Die Regel ist die des heutigen Preis-Lesers** (``services/strompreis_aggregator.py``, Stundenzeile für Stundenzeile,
KONZEPT-FLEX-TARIFE A-1 bis A-3). Der Leser summiert inline und bleibt für die Monate ohne Kanal-Deckung unverändert
(Lesart 1, Bauplan §3b); die Gleichheitsprobe (``tests/test_kanal_kosten_gleichheit.py``) hält Kanal-Monat und Bestand
auf denselben Stunden aneinander:

* **Bezug:** ``max(0, Netzbezug)`` — ein negativer Wert ist ein Zähler-Glitch und wird geklemmt, nicht verworfen
  (der Clamp trägt, ``test_preis_aggregat_symmetrie.py``).
* **Vermiedener Bezug** (Gewicht der Eigenverbrauchs-Ersparnis, A-2): ``max(0, PV − Einspeisung)`` derselben Stunde,
  PV einschließlich der Erzeuger hinter dem Zähler (wie ``pv_kw`` der Stundenzeile).
* **Ohne Preis** (``preis_cent is None``): die Stunde ist nicht bewertet — weder Kosten noch Gewicht (A-3: die Summe
  über die Stunden, die Preis UND Menge tragen; nie Ø × Gesamtmenge). ⚠ ``is None``, nicht ``> 0`` (P-8: Null- und
  Negativpreise sind Werte).
* **Preis-Summe und Preis-Stunden** (Nachzug B, Entscheid Fable): je Stunde MIT Preis der Preis selbst und eine 1 — der
  arithmetische Ø eines Zeitraums ist dann Δ Preis-Summe ÷ Δ Preis-Stunden und die Zahl der Stunden mit Preis ein Δ, wie
  ``arithmetisch_cent``/``abgedeckte_stunden`` des Lesers (``Σ preis / n`` über die Zeilen mit Preis).

⛔ **Kein Einspeise-Erlös** (Entscheid Master zu E4e, Annahme 2): ein Kanal, den keine Sicht liest und den eine
Tarifänderung nicht neu aufbaut, wäre tote, möglicherweise falsche Daten. Kommt der Erlös als Kanal, dann mit Leser und
Tarif-Neuaufbau in einem Zug.

Einheit der Beträge: **€** (wie HAs Kostensensor, ``…_cost`` in EUR); der Ø in ct/kWh entsteht beim Lesen
(``Δ € × 100 ÷ Δ kWh``).

ADR-001: keine Session, kein Sensor — nur Zahlen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional



@dataclass(frozen=True)
class KostenStunde:
    """Die Zuwächse der Kosten-Kanäle in einer Stunde."""

    #: Σ max(0, Bezug) × Preis / 100 — nur mit Preis.
    kosten_netzbezug_euro: float
    #: die bewertete Bezugsmenge (Gewicht des Bezugs-Ø) — nur mit Preis.
    netzbezug_bewertet_kwh: float
    #: vermiedener Bezug × Preis / 100 — nur mit Preis.
    kosten_ev_vermieden_euro: float
    #: der bewertete vermiedene Bezug (Gewicht des EV-Ø) — nur mit Preis.
    ev_bewertet_kwh: float
    #: der Stundenpreis in ct/kWh — nur mit Preis (Zähler des arithmetischen Ø).
    preis_summe_cent: float
    #: 1 je Stunde mit Preis (Nenner des arithmetischen Ø, Zahl der abgedeckten Stunden).
    preis_stunden: float


def kosten_der_stunde(
    *,
    netzbezug_kwh: Optional[float],
    pv_kwh: Optional[float],
    einspeisung_kwh: Optional[float],
    preis_cent: Optional[float],
) -> KostenStunde:
    """Die Zuwächse einer Stunde. Mengen ``None`` zählen als 0 (keine Menge in dieser Stunde — wie ``or 0.0`` des
    Lesers); ``preis_cent is None`` ⇒ die Stunde ist nicht bewertet."""
    bezug = max(0.0, float(netzbezug_kwh or 0.0))
    ev = max(0.0, float(pv_kwh or 0.0) - float(einspeisung_kwh or 0.0))
    if preis_cent is None:
        return KostenStunde(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    p = float(preis_cent)
    return KostenStunde(
        kosten_netzbezug_euro=p * bezug / 100.0,
        netzbezug_bewertet_kwh=bezug,
        kosten_ev_vermieden_euro=p * ev / 100.0,
        ev_bewertet_kwh=ev,
        preis_summe_cent=p,
        preis_stunden=1.0,
    )


__all__ = ["KostenStunde", "kosten_der_stunde"]
