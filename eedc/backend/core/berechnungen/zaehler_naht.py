"""Naht eines Zuordnungswechsels mit Grund «Fortsetzung» — die Abschnitts-Regel der Zählerstand-Reihe (Sensorwechsel mit
Grund, Bauplan B-3, S-3; Sitzung 2).

**Regel.** «Keine Differenz zweier Stände über eine Fortsetzungs-Naht.» Ein verzeichneter Wechsel (``zuordnung_wechsel``) mit
``grund = fortsetzung`` hat ein ``ab_ts``: ein Stand mit ``zeitpunkt ≥ ab_ts`` gehört zur neuen Quelle, einer davor zur alten
(B-1). Die Reihe läuft im selben Schlüssel weiter, auf dem Niveau der neuen Quelle — zwischen dem letzten Stand vor und dem
ersten Stand ab ``ab_ts`` liegt ein Niveau-Sprung, der keine Menge ist. Eine Menge über ein Fenster ist deshalb die **Summe der
Abschnitte**: je Abschnitt die Regel des Lesers (Tageswert, Slot, Zählwerk), über die Naht hinweg nichts.

**Benannte Grenze:** die Menge zwischen dem letzten Stand vor und dem ersten Stand ab ``ab_ts`` zählt nicht (stündliche Stände:
bis 1 h, Tagesstände: bis 1 Tag je Seite). Ein Wechsel **ohne** Grund ist keine Naht — die Leser lesen wie vor diesem Vorhaben.

Rein (ADR-001): Zeitpunkte und Stände rein, Abschnitte bzw. Zahlen raus; das Laden der Nähte steht in
``services/zuordnung_wechsel/zeitpunkt.py::fortsetzungs_naehte``. Leser und Einstufung: Wächter «Reihen-Leser»
(``tests/test_reihen_leser_waechter.py``).
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, TypeVar

T = TypeVar("T")


def ueber_naht(von: T, bis: T, naehte: Iterable[T]) -> bool:
    """Liegt zwischen den Ständen bei ``von`` und ``bis`` eine Naht (``von < ab_ts ≤ bis``)? Dann ist ``Stand(bis) −
    Stand(von)`` keine Menge."""
    return any(von < n <= bis for n in naehte)


def abschnitte(folge: Sequence[tuple[T, float]], naehte: Iterable[T]) -> list[list[tuple[T, float]]]:
    """Die zeitlich sortierte Standfolge ``[(zeitpunkt, stand), …]``, an jeder Naht geteilt — ein Stand bei oder nach
    ``ab_ts`` beginnt den neuen Abschnitt. Ohne Naht in der Folge: ein Abschnitt (die Folge selbst). Leere Abschnitte
    entstehen nicht."""
    grenzen = sorted(set(naehte))
    teile: list[list[tuple[T, float]]] = []
    for ts, wert in folge:
        if not teile or ueber_naht(teile[-1][-1][0], ts, grenzen):
            teile.append([])
        teile[-1].append((ts, wert))
    return teile


def zaehlwerk_menge(folge: Sequence[tuple[T, float]], naehte: Iterable[T]) -> float:
    """Menge eines Zählwerks (Starts, Betriebsstunden) über die Folge: je Abschnitt ``letzter − erster`` Stand, ein Rückgang
    zählt 0 (Regel der Zählwerke, ``snapshot/aggregator.get_daily_counter_deltas_by_inv``), über eine Naht nichts."""
    return sum(max(0.0, teil[-1][1] - teil[0][1]) for teil in abschnitte(folge, naehte))


def stand_differenz(folge: Sequence[tuple[T, float]], naehte: Iterable[T]) -> float:
    """Differenz eines Zählerstands (Gas, Wasser, Öl — ``services/zaehlerstaende.py``) über die Folge: je Abschnitt
    ``letzter − erster`` Stand, über eine Naht nichts. Ein Rückgang bleibt hier negativ — die Bewertung («Reihe
    gebrochen») trifft der Leser."""
    return sum(teil[-1][1] - teil[0][1] for teil in abschnitte(folge, naehte))


# ── Rand eines Fensters an einem gesperrten Stück (Sensorwechsel 4b-1-K/-K2, Bauplan «Zu §14» Nr. 102, Nr. 112) ──────────
#
# Ein **gesperrtes Stück** ``[S, R)`` (eine Lücke mit Höhenwechsel — verworfene, nicht gefüllte Stände, davor und danach nicht
# dieselbe Zählerhöhe —, oder eine Korrektur, deren Füllen aussteht; ``zuordnung_wechsel.zeitpunkt.gesperrte_stuecke``) hat
# Nähte an beiden Rändern. Eine Lücke ohne Höhenwechsel ist keins (U1): über sie rechnen die Leser wie über jede Zählerlücke. Für ein Fenster gilt dann **eine**
# Regel, die die Tagesansicht (``snapshot/aggregator._tagesdetail_boundary_diff_mit_grund``) und der Bereichs-Leser
# (``snapshot/bereichs_leser._randstaende``) teilen — das Laden der Stände liegt beim Leser, die Regel hier:
#
# * **linker Rand:** fehlt der Stand am Fensterbeginn und läge der letzte Stand davor vor einem gesperrten Stück, rückt der
#   Rand nicht über das Stück — er beginnt frühestens an dessen Ende (``ende_der_luecke_davor``);
# * **rechter Rand:** fehlt der Stand am Fensterende, weil es in einem gesperrten Stück liegt, rückt der Rand auf den letzten
#   Stand im Fenster (``endet_in_luecke``) — der Tag, an dem die Lücke beginnt, zeigt seinen Teil;
# * **kein Wert statt 0,0:** trägt die Folge keinen Abschnitt aus zwei Ständen (``traegt_messung``), ist außerhalb der
#   gesperrten Stücke nichts gemessen — der Tag hat keinen Wert.


def ende_der_luecke_davor(anker: Optional[T], fensterbeginn: T, luecken: Iterable[tuple[T, T]]) -> Optional[T]:
    """Liegt zwischen dem letzten Stand vor dem Fenster (``anker``) und dem Fensterbeginn ein gesperrtes Stück ``[S, R)``
    (``S ≤ fensterbeginn``, ``R > anker``)? Dann sein spätestes Ende ``R`` — dort beginnt der linke Rand frühestens —, sonst
    ``None``."""
    if anker is None:
        return None
    enden = [r for s, r in luecken if s <= fensterbeginn and r > anker]
    return max(enden) if enden else None


def endet_in_luecke(fensterende: T, luecken: Iterable[tuple[T, T]]) -> bool:
    """Liegt das Fensterende in einem gesperrten Stück (``S ≤ ende < R``)? Dann fehlt sein Stand, weil er verworfen ist —
    der rechte Rand rückt auf den letzten Stand im Fenster."""
    return any(s <= fensterende < r for s, r in luecken)


def traegt_messung(folge: Sequence[tuple[T, float]], naehte: Iterable[T]) -> bool:
    """Trägt die Folge (mit ihren Rändern) einen Abschnitt aus mindestens zwei Ständen ohne Naht dazwischen? Sonst ist im
    Fenster außerhalb der gesperrten Stücke nichts messbar — kein Wert statt einer gemessenen 0,0."""
    return any(len(teil) > 1 for teil in abschnitte(folge, naehte))


__all__ = ["abschnitte", "ende_der_luecke_davor", "endet_in_luecke", "stand_differenz", "traegt_messung", "ueber_naht",
           "zaehlwerk_menge"]
