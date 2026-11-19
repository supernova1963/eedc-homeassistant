"""Naht eines Zuordnungswechsels mit Grund «Fortsetzung» — die Abschnitts-Regel der Zählerstand-Reihe (Sensorwechsel mit
Grund, Bauplan B-3, S-3; Sitzung 2).

**Regel.** «Keine Differenz zweier Stände über eine Fortsetzungs-Naht.» Ein verzeichneter Wechsel (``zuordnung_wechsel``) mit
``grund = fortsetzung`` hat ein ``ab_ts``: ein Stand mit ``zeitpunkt ≥ ab_ts`` gehört zur neuen Quelle, einer davor zur alten
(B-1). Die Reihe läuft im selben Schlüssel weiter, auf dem Niveau der neuen Quelle — zwischen dem letzten Stand vor und dem
ersten Stand ab ``ab_ts`` liegt ein Niveau-Sprung, der keine Menge ist. Eine Menge über ein Fenster ist deshalb die **Summe der
Abschnitte**: je Abschnitt die Regel des Lesers (Tageswert, Slot, Zählwerk), über die Naht hinweg nichts.

**Benannte Grenze:** die Menge zwischen dem letzten Stand vor und dem ersten Stand ab ``ab_ts`` zählt nicht (stündliche Stände:
bis 1 h, Tagesstände: bis 1 Tag je Seite). Ein Wechsel **ohne** Grund ist keine Naht — die Leser lesen wie vor diesem Vorhaben.

**Naht mit Rand-Ständen (Sensorwechsel U2 a1, Rechenweg F5).** Ein Wechsel «bleiben» zwischen zwei Sensoren, der
angesetzt ist (``zuordnung_wechsel.ansatz`` ``beide``/``schnitt``), trägt den letzten Stand des alten Sensors
(``stand_alt_ende``) und den Nullpunkt des neuen (``stand_neu_null``). Eine solche Naht **teilt nicht**: sie hebt jeden Stand
ab ``ab_ts`` um ``versatz = stand_alt_ende − stand_neu_null`` (mehrere Nähte: die Summe ihrer Versätze bis zum Stand). Dann
ist ``Stand(bis) − Stand(von)`` über die Naht die Summe der Zuwächse beider Sensoren in ihrer Geltungszeit — die Regel
«Menge = Summe der Zuwächse jeder Quelle in ihrer Geltungszeit»; zwischen zwei Sensoren entsteht nie eine Differenz, und
keine Stunde fällt weg. Eine Naht **ohne** Rand-Stände (MQTT, Altbestand, Lücken-Ränder, eine noch offene Zeile) teilt wie
oben. Eine Naht mit Rand-Ständen ist eine :class:`Naht` (ein Zeitpunkt, der den Versatz trägt) — die Leser behalten ihre
Aufrufe: ``abschnitte`` hebt und teilt; die Slot-Leser, die Paare über ``ueber_naht`` prüfen, heben beim Laden
(``gehoben``) und fragen danach nur die teilenden Nähte (``trennende``).

Rein (ADR-001): Zeitpunkte und Stände rein, Abschnitte bzw. Zahlen raus; das Laden der Nähte steht in
``services/zuordnung_wechsel/zeitpunkt.py::fortsetzungs_naehte``. Leser und Einstufung: Wächter «Reihen-Leser»
(``tests/test_reihen_leser_waechter.py``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Iterable, Optional, Sequence, TypeVar

T = TypeVar("T")


class Naht(datetime):
    """Eine Naht mit Rand-Ständen: der Zeitpunkt ``ab_ts`` (vergleicht, sortiert und hasht wie dieser) und ``versatz``
    (``stand_alt_ende − stand_neu_null``), um den die Stände ab ``ab_ts`` steigen. Rechnen mit ihr (``+``/``−``,
    ``replace``) ergibt einen gewöhnlichen Zeitpunkt ohne Versatz."""

    versatz: float

    def __new__(cls, ab_ts: datetime, versatz: float) -> "Naht":
        n = super().__new__(cls, ab_ts.year, ab_ts.month, ab_ts.day, ab_ts.hour, ab_ts.minute, ab_ts.second,
                            ab_ts.microsecond, ab_ts.tzinfo, fold=ab_ts.fold)
        n.versatz = float(versatz)
        return n

    def zeit(self) -> datetime:
        return datetime(self.year, self.month, self.day, self.hour, self.minute, self.second, self.microsecond,
                        self.tzinfo, fold=self.fold)

    def __add__(self, other):
        return self.zeit() + other

    __radd__ = __add__

    def __sub__(self, other):
        return self.zeit() - (other.zeit() if isinstance(other, Naht) else other)

    def replace(self, *a, **k):  # type: ignore[override]
        return self.zeit().replace(*a, **k)

    def __repr__(self) -> str:  # pragma: no cover — nur Anzeige
        return f"Naht({self.zeit()!r}, versatz={self.versatz})"

    def __reduce__(self):  # pragma: no cover — Kopieren/Pickle
        return (Naht, (self.zeit(), self.versatz))


def rand_versatz(stand_alt_ende: Optional[float], stand_neu_null: Optional[float]) -> Optional[float]:
    """Der Versatz einer Naht mit Rand-Ständen: ``stand_alt_ende − stand_neu_null``; fehlt einer der beiden: ``None``."""
    if stand_alt_ende is None or stand_neu_null is None:
        return None
    return float(stand_alt_ende) - float(stand_neu_null)


def offset_vor_naht(kanalwert_danach: float, roh_danach: float, versatz: float) -> float:
    """Kanal-Nachbau (``kanal/nachfuellen._offsets_rueckwaerts``): der Versatz einer Quelle, die an einer Naht mit
    Rand-Ständen endet — der ihres Nachfolgers (``kanalwert_danach − roh_danach``) minus den Versatz der Naht; dann trägt die
    erste Stunde danach den Zuwachs beider Sensoren wie die gehobene Reihe."""
    return (kanalwert_danach - roh_danach) - versatz


def slot_beider(delta_neu: float, n_neu: int, delta_alt: float, n_alt: int) -> tuple[float, int]:
    """Tagesabschluss aus HA-Slots (``snapshot/lts_aggregator._dazu_anwenden``, U2 a1 F6): der Naht-Slot eines Wechsels
    «bleiben» ohne Überlappung zählt den Zuwachs beider Sensoren — ``(delta_neu + delta_alt, n)``, gerundet wie ein Slot
    (3 Stellen); ``n`` = die längere Spanne der beiden."""
    return round(delta_neu + delta_alt, 3), max(n_neu, n_alt)


def monat_aus_abschnitten(werte: Sequence[tuple[float, float, float, int]]) -> tuple[float, float, float, float, int]:
    """Monat aus Home Assistant je Geltungsabschnitt (``zuordnung_wechsel/monat.py``, U2 a1 F7): je Abschnitt
    ``(start_wert, differenz, verworfen, intervalle)`` der Zeilenregel ⇒ ``(start, ende, differenz, verworfen, intervalle)``
    des Monats. ``differenz``/``verworfen``/``intervalle`` sind die Summen; ``start`` ist der Start des ersten Abschnitts,
    ``ende`` der durchlaufende Stand ``start + differenz − verworfen`` (kein Zählerstand eines Sensors)."""
    differenz = round(sum(d for _s, d, _v, _i in werte), 2)
    verworfen = round(sum(v for _s, _d, v, _i in werte), 3)
    start = werte[0][0]
    return start, round(start + differenz - verworfen, 3), differenz, verworfen, sum(i for *_r, i in werte)


def versatz_der_naht(n) -> Optional[float]:
    """Der Versatz einer Naht mit Rand-Ständen, sonst ``None`` (die Naht teilt)."""
    return n.versatz if isinstance(n, Naht) else None


def trennende(naehte: Iterable[T]) -> list[T]:
    """Die Nähte ohne Rand-Stände — nur sie teilen eine Folge (eine Naht mit Rand-Ständen hebt)."""
    return [n for n in naehte if not isinstance(n, Naht)]


def hebung_am(ts, naehte: Iterable) -> float:
    """Die Summe der Versätze aller Nähte mit Rand-Ständen bis einschließlich ``ts`` (ein Stand bei ``ab_ts`` gehört schon
    zur neuen Quelle)."""
    return sum(n.versatz for n in naehte if isinstance(n, Naht) and n <= ts)


def gehoben(folge: Sequence[tuple[T, float]], naehte: Iterable) -> Sequence[tuple[T, float]]:
    """Die Standfolge mit den Ständen ab jeder Naht mit Rand-Ständen gehoben; ohne eine solche Naht die Folge selbst
    (bitgleich)."""
    mit = [n for n in naehte if isinstance(n, Naht)]
    if not mit:
        return folge
    return [(ts, wert + hebung_am(ts, mit)) for ts, wert in folge]


def gehobene_staende(staende: dict, zeit_von: Callable, naehte: Iterable) -> dict:
    """Wie ``gehoben`` für die Stände eines Slot-Lesers ``{index: stand oder None}`` (``zeit_von(index)`` = Zeitpunkt des
    Stands); ``None`` bleibt ``None``. Ohne Naht mit Rand-Ständen das Dict selbst (bitgleich)."""
    mit = [n for n in naehte if isinstance(n, Naht)]
    if not mit:
        return staende
    return {i: (None if s is None else s + hebung_am(zeit_von(i), mit)) for i, s in staende.items()}


def ueber_naht(von: T, bis: T, naehte: Iterable[T]) -> bool:
    """Liegt zwischen den Ständen bei ``von`` und ``bis`` eine Naht (``von < ab_ts ≤ bis``)? Dann ist ``Stand(bis) −
    Stand(von)`` keine Menge — für eine Naht mit Rand-Ständen erst nach dem Heben (``gehoben``; die Slot-Leser fragen danach
    nur die ``trennende``)."""
    return any(von < n <= bis for n in naehte)


def abschnitte(folge: Sequence[tuple[T, float]], naehte: Iterable[T]) -> list[list[tuple[T, float]]]:
    """Die zeitlich sortierte Standfolge ``[(zeitpunkt, stand), …]``, an jeder Naht geteilt — ein Stand bei oder nach
    ``ab_ts`` beginnt den neuen Abschnitt. Ohne Naht in der Folge: ein Abschnitt (die Folge selbst). Leere Abschnitte
    entstehen nicht. Eine Naht mit Rand-Ständen teilt nicht, sie hebt die Stände ab ihr (``gehoben``)."""
    naehte = list(naehte)
    grenzen = sorted(set(trennende(naehte)))
    teile: list[list[tuple[T, float]]] = []
    for ts, wert in gehoben(folge, naehte):
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


__all__ = ["Naht", "abschnitte", "ende_der_luecke_davor", "endet_in_luecke", "gehoben", "gehobene_staende", "hebung_am",
           "monat_aus_abschnitten", "offset_vor_naht", "rand_versatz", "slot_beider", "stand_differenz", "traegt_messung", "trennende", "ueber_naht", "versatz_der_naht", "zaehlwerk_menge"]
