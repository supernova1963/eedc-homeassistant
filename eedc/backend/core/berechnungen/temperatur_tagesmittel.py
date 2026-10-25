"""Ø Vorlauf und Ø Spreizung einer Wärmepumpe über den Tag — eine Formel, ein Ort (P-433-3 S3, #432; Bauplan B6, G5).

**Gemittelt wird über die Stunden mit Betrieb**, nicht über alle 24: eine Wärmepumpe, die nachts steht, kühlt im
Vorlauf aus, und ein Mittel über die Stillstandsstunden beschriebe das Rohr, nicht den Betrieb. Welche Stunde Betrieb
hat, entscheidet der Betriebsmodus, wo es ihn gibt; sonst der Strom.

* **Mit Modus-Signal** (mindestens eine Stunde des Tages trägt einen Modus): Betrieb ⇔ in der Stunde ein Modus
  außer ``aus``/``unbestimmt`` (Kanon ``core/betriebsmodus.py``) mit Strom > 0 oder ohne Strom-Angabe. ``None`` heißt
  «nicht hingesehen» (``ModusStunde``) und ist kein Betrieb.
* **Ohne Modus-Signal:** Betrieb ⇔ Strom der Stunde über dem Tagesminimum (das Minimum ist der Ruhe-/Standby-Strom).
  Läuft das Gerät alle Stunden gleich, gibt es keine erkennbare Betriebsstunde — dann keine Zahl (kein Raten).
* Ohne Modus und ohne Strom: keine Zahl.

**Nicht je Funktion** (E-P3-12): ein Vorlauf «beim Heizen» wäre eine abgeleitete Größe neben gemessenen Zählern; die
Stunden sind gemischt (Heizen und Warmwasser in derselben Stunde).

Die Spreizung je Stunde rechnet ``temperatur.spreizung_k`` (dieselbe Differenz wie live); ihr Mittel läuft über die
Betriebsstunden, die beide Temperaturen tragen. Ungerundet — die Rundung gehört dem Aufrufer.

Aufrufer: ``api/routes/energie_profil/waerme.py::get_waerme_temperaturen_stunden`` (Kopf des Temperatur-Diagramms in
*Cockpit → Tag*).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from backend.core.berechnungen.modus_split import ModusStunde
from backend.core.berechnungen.temperatur import spreizung_k
from backend.core.betriebsmodus import AUS, UNBESTIMMT

#: Woran die Betriebsstunden erkannt wurden.
BETRIEB_AUS_MODUS = "modus"
BETRIEB_AUS_STROM = "strom"

_STUNDEN = 24


@dataclass(frozen=True)
class TemperaturTagesmittel:
    """Ø Vorlauf und Ø Spreizung über die Betriebsstunden eines Tages — ``None`` ohne erkennbare Betriebsstunde."""

    vorlauf_c: Optional[float]
    spreizung_k: Optional[float]
    #: Betriebsstunden mit Vorlauf-Wert — die Zahl, über die ``vorlauf_c`` gemittelt ist.
    betriebsstunden: int
    #: Betriebsstunden mit Vorlauf UND Rücklauf — die Zahl, über die ``spreizung_k`` gemittelt ist.
    spreizung_stunden: int
    #: ``"modus"`` · ``"strom"`` · ``None`` (keine Grundlage für Betriebsstunden).
    betrieb_aus: Optional[str]


def _betrieb_aus_modus(modus_stunden: Sequence[ModusStunde]) -> Optional[list[bool]]:
    """Betrieb je Stunde aus den Modus-Stunden — ``None``, wenn keine Stunde ein Modus-Signal trägt."""
    if not any(m.modus is not None for m in modus_stunden):
        return None
    betrieb = [False] * _STUNDEN
    for m in modus_stunden:
        h = m.stunde
        if h is None or not 0 <= h < _STUNDEN:
            continue
        if m.modus not in (None, AUS, UNBESTIMMT) and (m.kwh is None or abs(m.kwh) > 0):
            betrieb[h] = True
    return betrieb


def _betrieb_aus_strom(strom_kwh: Sequence[Optional[float]]) -> Optional[list[bool]]:
    """Betrieb je Stunde: Strom über dem Tagesminimum — ``None`` ohne Strom-Stunde."""
    werte = [v for v in strom_kwh if v is not None]
    if not werte:
        return None
    minimum = min(werte)
    return [v is not None and v > minimum + 1e-9 for v in list(strom_kwh)[:_STUNDEN]]


def temperatur_tagesmittel(
    vorlauf_c: Sequence[Optional[float]],
    ruecklauf_c: Sequence[Optional[float]],
    *,
    modus_stunden: Sequence[ModusStunde] = (),
    strom_kwh: Sequence[Optional[float]] = (),
) -> TemperaturTagesmittel:
    """Ø Vorlauf und Ø Spreizung über die Betriebsstunden (Modul-Kopf). Eingänge je Stunde (24, Raster des Tages);
    ``modus_stunden`` mit ``stunde`` im selben Raster, ``strom_kwh`` 24 Werte (``None`` = keine Zeile)."""
    betrieb = _betrieb_aus_modus(modus_stunden)
    quelle = BETRIEB_AUS_MODUS
    if betrieb is None:
        betrieb, quelle = _betrieb_aus_strom(strom_kwh), BETRIEB_AUS_STROM
    if betrieb is None:
        return TemperaturTagesmittel(None, None, 0, 0, None)
    v = list(vorlauf_c) + [None] * (_STUNDEN - len(vorlauf_c))
    r = list(ruecklauf_c) + [None] * (_STUNDEN - len(ruecklauf_c))
    vorlauf = [v[h] for h in range(len(betrieb)) if betrieb[h] and v[h] is not None]
    spreizung = [s for h in range(len(betrieb)) if betrieb[h] and (s := spreizung_k(v[h], r[h])) is not None]
    return TemperaturTagesmittel(
        vorlauf_c=sum(vorlauf) / len(vorlauf) if vorlauf else None,
        spreizung_k=sum(spreizung) / len(spreizung) if spreizung else None,
        betriebsstunden=len(vorlauf),
        spreizung_stunden=len(spreizung),
        betrieb_aus=quelle,
    )


__all__ = ["BETRIEB_AUS_MODUS", "BETRIEB_AUS_STROM", "TemperaturTagesmittel", "temperatur_tagesmittel"]
