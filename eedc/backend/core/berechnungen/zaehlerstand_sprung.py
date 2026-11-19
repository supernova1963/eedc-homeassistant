"""Zählerstand springt — die Erkennung hinter dem Daten-Checker-Befund ``ha_zaehlerstand_springt`` (Sensorwechsel mit Grund,
U2 Lauf c, Rechenweg F12; Messfrage M4).

**Warum es das gibt.** Wird an einem Zähler das Gerät getauscht und Home Assistant führt **dieselbe Entität** weiter, bucht HA
den Tausch als Menge (Leitlinie Gernot 19.11.2026, Bauplan Nr. 132 (b)): springt der Stand nach oben (der neue Zähler zeigt
mehr als der alte), zählt die Stunde den Sprung; beginnt der neue Zähler nicht bei 0, hält HA das für einen neuen Zyklus und
zählt den ganzen neuen Stand. eedc übernimmt HAs Werte wie das Energie-Dashboard und berichtigt nichts (Grundregel
«Quellentreue»); der Befund nennt die Stunde und den Weg in Home Assistant.

**Das Maß** je Zeilenpaar (r0, r1) **innerhalb eines Quell-Abschnitts** (dieselbe Statistik, keine Wechselstelle):

    mass = z / (größter Tageszuwachs im Bezugsfenster × Tage seit dem letzten Zuwachs, mindestens 1)

* ``z`` = der Zuwachs, den eedc für die Stunde zählt (Mengen-Zähler: Δ ``sum``; Stand-Zähler: Δ ``state``).
* Tageszuwachs = Σ der positiven ``z`` je lokalem Kalendertag; Bezugsfenster = die ``BEZUG_TAGE`` Tage vor dem Tag der Stunde
  (derselbe Abschnitt). Hat das Fenster weniger als ``BEZUG_MIN_TAGE`` Tage mit Zuwachs, ist der Zähler **jung**: kein Maß,
  kein Befund (ein neuer Zähler kennt sein eigenes Maß noch nicht).
* Tage seit dem letzten Zuwachs = Abstand zur letzten Zeile davor mit ``z > 0`` in Tagen. Eine Nachholstunde nach einer Lücke
  und ein großer Verbrauch nach langer Ruhe (Wallbox nach Wochen, Wärmepumpe im ersten kalten Monat) teilen sich so durch
  ihre Ruhezeit und bleiben bei höchstens etwa 1.

**Die zwei Arme:**

* **Neubeginn nicht bei 0** (``NEUBEGINN``): der Stand fällt unter ``NEUBEGINN_ANTEIL`` des vorigen (der vorige mindestens
  ``MIN_STAND``) und das Maß überschreitet ``SCHWELLE_NEUBEGINN``. Ein Fall gewöhnlichen Verbrauchs hat diese Form nicht: ein
  Zähler, der täglich oder monatlich bei 0 neu beginnt, zählt in der Stunde des Neubeginns nur den Verbrauch dieser Stunde.
  An einem Stand-Zähler ist ``z`` hier negativ — dieser Arm trifft ihn nie (einen gefallenen Stand nennt dort
  ``zaehlerstand_reihe_bruch``).
* **Sprung nach oben** (``SPRUNG``): Δ ``sum`` = Δ ``state`` (bis ``GLEICH_ABS`` + ``GLEICH_ANTEIL`` · |Δ ``sum``|) und das Maß
  überschreitet ``SCHWELLE_SPRUNG``. Diese Form hat auch jeder gewöhnliche Verbrauch — hier trennt allein das Maß, deshalb die
  höhere Schwelle.

**Schwellen aus M4** (Messung 19.11.2026, ``~/.claude/plans/golden-master/sensorwechsel-saat/u2c/m4_verteilung.py``): über die
Produktiv-Kopie (12 Spiegel-Abschnitte, 137 450 Paare, 31.10.2024–15.11.2026) liegt das größte Maß bei 1,32 (Arm B, ein
Ladevorgang), Arm A bei keinem Paar über 0; im Saat-Satz (26 Abschnitte) bei 0,79. Mit einem Bezugsfenster von 30 Tagen statt
eines Jahres hätte ein Frühlingstag mit Netzbezug 13,3 kWh in einer Stunde nach einem Monat mit höchstens 0,4 kWh am Tag das
Maß 32 erreicht, mit 3 statt 14 Bezugstagen der erste Sonnentag eines jungen Einspeisezählers 44 — beides gewöhnlicher Betrieb.
Die Lab-Sprünge liegen bei +2 001 auf Zählern mit 6,9 bis 160 kWh am Tag zwischen 12,5 und 292 (Rechenweg F12) und beim
Lab-Neubeginn bei 300 (Rate 2,04 kWh je Stunde) bei ≈ 6.

Die Funktionen sind rein (keine Datenbank, keine Uhr; der Kalendertag ist der lokale der Prozesszone = HA, wie
``ha_sprung``). Welche Stunden ausgenommen sind (das Muster «kurz 0 und zurück», ``ha_zaehlersprung``), sagt der Aufrufer.
Der Kern kennt keine Familie: der Erzeuger ``services/daten_checker/datenquelle/standsprung.py`` gibt ihm die Zeilen eines
Spiegel-Abschnitts; eine MQTT-Mitschrift ließe sich ebenso prüfen.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Sequence

#: Arm A: Neubeginn des Zählers nicht bei 0 (der Stand fällt, HA zählt den neuen Stand).
NEUBEGINN = "neubeginn"
#: Arm B: der Stand springt nach oben (Δ sum = Δ state).
SPRUNG = "sprung"

#: Schwelle des Maßes im Arm «Neubeginn» (M4: Produktiv und Saat 0 Paare über 0; Lab-Neubeginn bei 300 ≈ 6).
SCHWELLE_NEUBEGINN = 3.0
#: Schwelle des Maßes im Arm «Sprung» (M4: Produktiv höchstens 1,32, Saat 0,79; Lab +2 001 ab 12,5).
SCHWELLE_SPRUNG = 10.0
#: Bezugsfenster in Tagen vor dem Tag der Stunde — ein Jahr, damit der Winter den Sommer und der Sommer den Winter kennt.
BEZUG_TAGE = 365
#: So viele Tage mit Zuwachs braucht das Bezugsfenster; darunter ist der Zähler jung (kein Befund).
BEZUG_MIN_TAGE = 14
#: Neubeginn: der Stand fällt unter diesen Anteil des vorigen.
NEUBEGINN_ANTEIL = 0.9
#: Unter diesem vorigen Stand ist ein Fallen kein Neubeginn (wie ``ha_sprung.MIN_STAND_KWH``).
MIN_STAND = 1.0
#: Δ sum = Δ state bis auf diese Menge …
GLEICH_ABS = 0.01
#: … plus diesen Anteil von |Δ sum|.
GLEICH_ANTEIL = 0.01
_TAG_S = 86400


@dataclass(frozen=True)
class Standsprung:
    """Eine Stunde mit Sprung: ``start_ts`` = Beginn der Zeile, in der eedc (wie HA) die Menge ``menge`` zählt."""

    start_ts: int
    art: str
    menge: float
    stand_vorher: float
    stand_nachher: float
    mass: float


def _tag(ts: int) -> date:
    return datetime.fromtimestamp(ts).date()


def _zuwachs(z0: tuple, z1: tuple, spalte: int) -> Optional[float]:
    a, b = z0[spalte], z1[spalte]
    return None if a is None or b is None else b - a


def tageszuwachs(zeilen: Sequence[tuple], spalte: int = 2) -> dict[date, float]:
    """Σ der positiven Zuwächse je lokalem Kalendertag (Tag der jeweils späteren Zeile). ``spalte``: 2 = ``sum``, 1 = ``state``."""
    je_tag: dict[date, float] = {}
    for z0, z1 in zip(zeilen, zeilen[1:]):
        d = _zuwachs(z0, z1, spalte)
        if d is not None and d > 0:
            je_tag[_tag(z1[0])] = je_tag.get(_tag(z1[0]), 0.0) + d
    return je_tag


def bezug(je_tag: dict[date, float], tag: date) -> tuple[int, float]:
    """(Tage mit Zuwachs, größter Tageszuwachs) im Bezugsfenster ``[tag − BEZUG_TAGE, tag)``."""
    tage = sorted(je_tag)
    links = bisect_left(tage, date.fromordinal(tag.toordinal() - BEZUG_TAGE))
    rechts = bisect_left(tage, tag)
    fenster = tage[links:rechts]
    return len(fenster), max((je_tag[t] for t in fenster), default=0.0)


def mass(menge: float, groesster_tag: float, tage_ruhe: float) -> float:
    """Das Maß F12: Zuwachs der Stunde ÷ (größter Tageszuwachs × Tage seit dem letzten Zuwachs, mindestens 1)."""
    return menge / (groesster_tag * max(1.0, tage_ruhe))


def _gleich(z0: tuple, z1: tuple) -> bool:
    d_sum, d_state = _zuwachs(z0, z1, 2), _zuwachs(z0, z1, 1)
    return d_sum is not None and d_state is not None and abs(d_sum - d_state) <= GLEICH_ABS + GLEICH_ANTEIL * abs(d_sum)


def _neubeginn(z0: tuple, z1: tuple) -> bool:
    st0, st1 = z0[1], z1[1]
    return st0 is not None and st1 is not None and st0 >= MIN_STAND and st1 < NEUBEGINN_ANTEIL * st0


def _arm(z0: tuple, z1: tuple, m: float) -> Optional[str]:
    if _neubeginn(z0, z1):
        return NEUBEGINN if m > SCHWELLE_NEUBEGINN else None
    return SPRUNG if m > SCHWELLE_SPRUNG and _gleich(z0, z1) else None


def finde_standspruenge(zeilen: Sequence[tuple], *, stand: bool = False,
                        ausgenommen: frozenset[int] | set[int] = frozenset()) -> list[Standsprung]:
    """Reine Funktion: ``zeilen`` = ``(start_ts, state, sum)`` EINES Quell-Abschnitts, aufsteigend. ``stand``: der Zähler ist
    ein Stand (eedc zählt Δ ``state``), sonst eine Menge (Δ ``sum``). ``ausgenommen``: ``start_ts`` der Zeilen, die eine
    andere Prüfung schon nennt. Je Stunde mit Sprung ein ``Standsprung`` in Zeitfolge."""
    spalte = 1 if stand else 2
    je_tag = tageszuwachs(zeilen, spalte)
    bezug_je_tag: dict[date, tuple[int, float]] = {}
    out: list[Standsprung] = []
    letzter_zuwachs: Optional[int] = None
    for z0, z1 in zip(zeilen, zeilen[1:]):
        menge = _zuwachs(z0, z1, spalte)
        if menge is None:
            continue
        ruhe = (z1[0] - letzter_zuwachs) / _TAG_S if letzter_zuwachs is not None else 1.0
        if menge > 0:
            letzter_zuwachs = z1[0]
        tag = _tag(z1[0])
        if tag not in bezug_je_tag:
            bezug_je_tag[tag] = bezug(je_tag, tag)
        n_tage, groesster = bezug_je_tag[tag]
        if menge <= 0 or n_tage < BEZUG_MIN_TAGE or z1[0] in ausgenommen:
            continue
        m = mass(menge, groesster, ruhe)
        art = _arm(z0, z1, m)
        if art is not None:
            out.append(Standsprung(int(z1[0]), art, menge, z0[1], z1[1], m))
    return out


__all__ = ["BEZUG_MIN_TAGE", "BEZUG_TAGE", "NEUBEGINN", "SCHWELLE_NEUBEGINN", "SCHWELLE_SPRUNG", "SPRUNG", "Standsprung",
           "bezug", "finde_standspruenge", "mass", "tageszuwachs"]
