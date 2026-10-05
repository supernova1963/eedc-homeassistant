"""Die Summe eines Zählers nach Home Assistants Regel — eigene Summe ohne HA (HA-Bauform E1, Bauplan §4).

**Wozu.** Wo eedc ohne Home Assistant läuft (MQTT, Standalone), bildet es die Stundensumme eines
kumulativen Zählers selbst — mit derselben Regel, nach der HA seine Langzeitstatistik schreibt.
Quelle: HA 2026.9.2, ``homeassistant/components/sensor/recorder.py``, ``reset_detected``
(Z. 475-500) und die Summenschleife in ``compile_statistics`` (Z. 736-822), Abschrift unter
``plans/ha-bauform-werkzeug/ha-quelltext-2026.9.2/sensor_recorder.py``.

Die Regel, wie HA sie für ``state_class: total_increasing`` anwendet:

* Zu Beginn einer Periode gilt ``old_state = new_state = state`` der letzten Periode und
  ``_sum = sum`` der letzten Periode. Gibt es keine letzte Periode, ist der erste gültige Stand
  der **Nullpunkt** (``old_state = new_state = Stand``, die Summe beginnt bei 0).
* Ein Stand **unter 90 %** des vorigen ist ein **Reset**: Der Zuwachs bis zum alten Stand zählt
  noch (``_sum += new_state − old_state``), danach läuft der neue Zyklus **ab 0**
  (``old_state = 0``). Folge: 480 → 0 → 480 ergibt **+480** — der Sprung zurück auf den alten
  Stand zählt als neue Energie. Das ist HAs Verhalten und hier Absicht (Gegenprüfung W3; N-586).
* Ein Stand zwischen 90 und 100 % des vorigen ist **kein** Reset (HA warnt nur): die Summe sinkt
  um den Dip und steigt mit der Rückkehr wieder.
* Ein **negativer** Stand wird verworfen (HA: ``warn_negative`` + ``HomeAssistantError`` →
  ``continue``) — außer als allererster Nullpunkt, den HA ohne Prüfung annimmt
  (``old_state is None or reset_detected(...)`` prüft das Vorzeichen erst ab dem zweiten Stand).
* Am Ende der Periode: ``_sum += new_state − old_state``; gespeichert werden ``sum`` und
  ``state = new_state``.

DB-frei (ADR-001). Der Plausibilitäts-Deckel (R3) ist **nicht** Teil dieser Regel — HA kennt ihn
nicht; der Schreiber legt ihn als Filter darüber (Bauplan §4, ``services/kanal/schreiber.py``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional

#: HA: ``fstate < 0.9 * previous_fstate`` ist ein Reset.
RESET_SCHWELLE: float = 0.9


@dataclass(frozen=True)
class PeriodenSumme:
    """Ergebnis einer Periode: was HA als ``sum`` und ``state`` schreiben würde."""

    sum: float
    state: float


def ha_summe_der_periode(
    vorher: Optional[PeriodenSumme], staende: Iterable[Optional[float]],
) -> Optional[PeriodenSumme]:
    """Eine Periode (Stunde) nach HAs Regel fortschreiben.

    Args:
        vorher: ``sum``/``state`` der letzten geschriebenen Periode desselben Zählers, oder
            ``None`` (erste Periode: der erste gültige Stand ist der Nullpunkt).
        staende: die Rohstände der Periode in zeitlicher Reihenfolge. ``None`` und nicht
            endliche Werte zählen nicht (HA nimmt nur gültige Fließkomma-Stände).

    Returns:
        ``PeriodenSumme`` oder ``None``, wenn die Periode keinen gültigen Stand trägt — **auch bei
        vorhandener Vorperiode**. HA schreibt in diesem Fall eine Zeile mit fortgeschriebener Summe
        (es liest den Zustand zum Periodenbeginn mit — Abfrage ab ``start − resolution``,
        ``sensor_recorder.py:549-556``); eedc hat ohne Rohstand keinen Beleg, dass der Zähler
        lief, und füllt deshalb keine Lücke — die Energie steht in der nächsten Stunde mit Stand.
        Eine Periode, deren Stände alle verworfen sind (nur negative), liefert dagegen die Vorperiode
        unverändert fort (HA: gültige Fließkommastände, aber kein Update).
    """
    if vorher is None:
        _sum = 0.0
        old_state: Optional[float] = None
        new_state: Optional[float] = None
    else:
        _sum = float(vorher.sum)
        old_state = new_state = float(vorher.state)

    gesehen = False
    for roh in staende:
        if roh is None:
            continue
        fstate = float(roh)
        if not math.isfinite(fstate):
            continue
        gesehen = True
        if old_state is None:
            reset = True
        else:
            if fstate < 0:
                continue  # HA: warn_negative → HomeAssistantError → `continue`
            reset = new_state is not None and fstate < RESET_SCHWELLE * new_state
        if reset:
            if old_state is not None and new_state is not None:
                _sum += new_state - old_state
            new_state = fstate
            old_state = 0.0 if old_state is not None else new_state
        else:
            new_state = fstate

    if not gesehen or new_state is None or old_state is None:
        return None
    _sum += new_state - old_state
    return PeriodenSumme(sum=_sum, state=new_state)
