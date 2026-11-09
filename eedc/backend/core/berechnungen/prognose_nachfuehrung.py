"""Nachführung «Rest heute» aus dem gemessenen Vormittag — Faktor und SOLL bis zur IST-Grenze (Päckchen CC, 9.11.2026).

**Regel (Konzept `konzept-prognose-nachfuehrung-rest-heute-2026-11-09.md` §3, Variante K):**

    r = IST_bisher ÷ SOLL_bisher       (wie gut trifft der Tag bisher)
    w = SOLL_bisher ÷ SOLL_Tag          (welcher Anteil des Tages-SOLL ist schon vorbei)
    f = clip(1 + (r − 1) · √w, 0,4, 1,6)

Der Rest des Tages wird mit ``f`` skaliert; am Morgen (kleines ``w``) wirkt die Abweichung gedämpft, am Nachmittag fast voll.

**Herkunft:** gemessen Winterborn 1.9.–8.11.2026 (69 Tage), Backtest gegen die HA-Langzeitstatistik der Sensoren «PV-Prognose
heute»/«Rest heute» und das IST je Stunde (Werkzeug ``refactoring-werkzeug/nachfuehrung-backtest-2026-11-09/backtest.py``):
MAE des Tagesendwerts im Okt/Nov um 10–14 Uhr 28,6/24,7/19,7/14,6/10,6 % ⇒ 24,4/19,6/17,5/12,6/9,4 %, Nebeltage halbiert,
September ≤ 1,5 Punkte schlechter um 10 Uhr. Die volle Nachführung (``f = r``) verschlechterte den September deutlich.

**Annahmen** (benannt, nicht gemessen optimiert): die Klemme 0,4…1,6 (ein Vormittag sagt nicht mehr als «Faktor 2,5 daneben»),
die Schwellen ``SOLL_bisher ≥ 1 kWh`` und ``w ≥ 10 %`` (Morgen-Rauschen: zwei Zehntel kWh entscheiden sonst über den Tag).

**SOLL bis zur IST-Grenze** (:func:`soll_bisher_kwh`): Σ der Prognose-Slots bis **einschließlich** dem höchsten Slot, der einen
IST-Wert beigesteuert hat (N-544, ``prognose_kanon.KanonPrognose.ist_bisher_bis_slot``) — dieselbe Grenze wie das IST, nicht die
Uhr. Die Funktion ist die eine Stelle dieser Summe; die Abweichungs-Ampel des HA-Exports (``anlage_steuerung._abweichungs_ampel``)
liest sie ebenso.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

#: Annahme: so weit darf der Vormittag den Rest höchstens verschieben (Faktor 0,4 … 1,6).
NACHFUEHR_KLEMME: tuple[float, float] = (0.4, 1.6)
#: Annahme: unter 1 kWh SOLL bisher ist das Verhältnis IST/SOLL Rauschen — kein Faktor.
NACHFUEHR_MIN_SOLL_KWH: float = 1.0
#: Annahme: unter 10 % des Tages-SOLL (früher Morgen) bleibt der Rest das Modell.
NACHFUEHR_MIN_ANTEIL: float = 0.10
#: Annahme: ab ±5 % Verschiebung nennt die Live-Sicht die Nachführung in einem Satz — darunter ist es Rauschen
#: (dieselbe Schwelle wie der Abweichungs-Hinweis daneben).
NACHFUEHR_HINWEIS_AB: float = 0.05


def nachfuehr_faktor(
    ist_bisher_kwh: Optional[float],
    soll_bisher_kwh: Optional[float],
    soll_tag_kwh: Optional[float],
    *,
    klemme: tuple[float, float] = NACHFUEHR_KLEMME,
    min_soll_kwh: float = NACHFUEHR_MIN_SOLL_KWH,
    min_anteil: float = NACHFUEHR_MIN_ANTEIL,
) -> float:
    """Der Nachführ-Faktor ``f = clip(1 + (r − 1)·√w, klemme)`` — ``1.0``, wo der Vormittag nichts sagt.

    ``1.0`` ohne IST-Messung (``ist_bisher_kwh is None``), ohne SOLL, bei ``soll_bisher_kwh < min_soll_kwh``,
    ``soll_tag_kwh <= 0`` oder ``w < min_anteil``. Eine gemessene 0 kWh ist ein Wert (ADR-002/P4) und ergibt die untere Klemme.
    """
    if ist_bisher_kwh is None or soll_bisher_kwh is None or soll_tag_kwh is None:
        return 1.0
    if soll_tag_kwh <= 0 or soll_bisher_kwh < min_soll_kwh:
        return 1.0
    w = soll_bisher_kwh / soll_tag_kwh
    if w < min_anteil:
        return 1.0
    r = ist_bisher_kwh / soll_bisher_kwh
    f = 1.0 + (r - 1.0) * math.sqrt(min(w, 1.0))
    unten, oben = klemme
    return max(unten, min(oben, f))


def soll_bisher_kwh(slots: Optional[Sequence[Optional[float]]], bis_slot: Optional[int]) -> Optional[float]:
    """Σ ``slots[:bis_slot + 1]`` — das SOLL bis zur IST-Grenze (N-544-Regel, inklusive). ``None`` ohne Grenze oder Slots.

    ``None``-Slots zählen als 0 (wie die Ampel bisher). Ein negativer ``bis_slot`` (Uhr-Rückfall vor 01:00) ergibt 0.
    """
    if bis_slot is None or not slots:
        return None
    return sum(float(v or 0.0) for v in slots[: max(0, int(bis_slot) + 1)])


def rest_nachgefuehrt_kwh(rest_modell_kwh: Optional[float], faktor: float) -> Optional[float]:
    """Der nachgeführte Rest ``round(rest × f, 1)`` — ``None`` bleibt ``None`` (kein Profil, kein Rest)."""
    if rest_modell_kwh is None:
        return None
    return round(rest_modell_kwh * faktor, 1)


def nachfuehr_prozent(faktor: Optional[float], *, ab: float = NACHFUEHR_HINWEIS_AB) -> Optional[int]:
    """Die Verschiebung des Rests in ganzen Prozent ``round((f − 1) · 100)`` — ``None`` ohne Faktor oder unter ``ab``.

    Für den Satz der Live-Sicht («Rest nach dem bisherigen Tag um 18 % gesenkt»); der Client zeigt, er rechnet nicht.
    """
    if faktor is None or abs(faktor - 1.0) < ab:
        return None
    return round((faktor - 1.0) * 100)


def slots_nachgefuehrt(
    slots: Optional[Sequence[Optional[float]]], faktor: Optional[float], ab_slot: Optional[int],
) -> Optional[list[Optional[float]]]:
    """Die Prognose-Slots ab ``ab_slot`` × ``faktor``, davor unverändert — die Eingangsreihe der Speicher-Simulation
    («Speicher voll um», Entscheid Master H-N2: sie folgt dem nachgeführten Rest wie «Rest heute»).

    ``None``-Slots bleiben ``None``; ohne Faktor, ohne Startslot oder bei ``faktor == 1.0`` dieselbe Reihe (bitgleich).
    """
    if slots is None:
        return None
    if faktor is None or ab_slot is None or faktor == 1.0:
        return list(slots)
    return [v if (v is None or h < ab_slot) else v * faktor for h, v in enumerate(slots)]

