"""Versetzte Abschnitte in einer Zählerstand-Reihe — die Erkennung hinter dem Daten-Checker-Befund ``zaehler_versatz``.

**Warum es das gibt (Verdacht N-803, Erhebung 16.11.2026).** eedc schreibt je Stunde den Zählerstand jedes zugeordneten
Zählers in seine Standreihe (``sensor_snapshots``, ``services/snapshot/writer.py``) — mit der Entität, die **heute**
zugeordnet ist. Ändert sich die Zuordnung, läuft derselbe Schlüssel mit dem Stand eines anderen Sensors weiter; schreibt
ein Lauf dann einen Abschnitt mit dem anderen Sensor (oder bleibt ein solcher Abschnitt stehen), steht in der Reihe ein
**versetzter Abschnitt**: der Stand springt um +X, läuft auf der anderen Höhe weiter und fällt später um ≈ −X zurück. An
den beiden Rändern ist der Tageswert, den eedc aus zwei Ständen bildet, falsch — am Sprung um X zu hoch, am Rückgang
fehlt er («Zähler zurückgesprungen»).

**Die Regel** (gemessen an der Produktiv-Sicherung 15.11.2026 und den vier Kopien des Daten-Checker-Werkzeugs E0):

* **Sprung:** ein Schritt Δ > max(``SPRUNG_FAKTOR`` × Median der positiven Δ der Reihe, ``SPRUNG_MIN_KWH``).
* **Rückgang (Stufe):** ein Schritt Δ < −``RUECKGANG_MIN_KWH``, dessen neuer Stand nicht nach einem Neubeginn aussieht
  (mindestens ``RESET_ANTEIL`` des alten und mindestens ``RESET_MIN_STAND``) — ein Zurücksetzen auf nahe null ist kein
  Versatz, sondern ein Zählerlauf (``zaehler_ruecksprung``, N-341).
* **Paar:** je Rückgang der **nächstliegende vorangehende**, noch ungepaarte Sprung ähnlicher Größe
  (|X_auf − X_ab| ≤ ``AEHNLICH_ANTEIL`` × X_auf). Ein einzelner Stufen-Rückgang ohne Gegen-Sprung (Speicher-Netzladung
  der Produktiv-Anlage, April/Mai 2026) und ein Sprung ohne Rückgang (ein großer Ladevorgang, eine Datenlücke, ein
  dokumentierter Sensorwechsel) sind kein Befund.
* **Zerteilter Lauf:** liegen der Rückgang eines Paars und der Sprung des nächsten höchstens ``NAHT_STUNDEN`` auseinander
  und sind sie ähnlich groß, ist das **ein** Lauf mit einem Loch (an der Produktiv-Anlage am 15.07.2026: ein lesender
  Abruf hat fünf richtige Stunden mitten in den Lauf gesetzt).

Die Funktionen sind rein (keine Datenbank, keine Uhr). Den Abgleich mit dem HA-Spiegel (``stand_passt_zum_spiegel``)
und die Wahl der Rand-Tage trifft der Erzeuger ``services/daten_checker/datenquelle/versatz.py``.

Schwesterdateien: ``services/daten_checker/datenquelle/versatz.py`` (Erzeuger), ``services/daten_checker/datenquelle/
ruecksprung.py`` (Zurücksetzen in MQTT-Reihen), ``services/daten_checker/datenquelle/ha_sprung.py`` (Sprung im Spiegel).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

#: Ein Sprung ist größer als dieses Vielfache des Medians der positiven Schritte der Reihe …
SPRUNG_FAKTOR = 20.0
#: … und größer als diese Menge (kWh) — eine fast stehende Reihe macht sonst jeden Ladevorgang zum Sprung.
SPRUNG_MIN_KWH = 10.0
#: Ein Rückgang ist ein Schritt unter −diesem Wert (Rundungsrauschen der Stände ist keiner).
RUECKGANG_MIN_KWH = 0.001
#: Ein Rückgang auf weniger als diesen Anteil des alten Stands ist ein Neubeginn, kein Versatz.
RESET_ANTEIL = 0.05
#: Ein Rückgang auf weniger als diesen Stand (kWh) ist ein Neubeginn, kein Versatz.
RESET_MIN_STAND = 1.0
#: Sprung und Rückgang gehören zusammen, wenn sie sich um höchstens diesen Anteil des Sprungs unterscheiden.
AEHNLICH_ANTEIL = 0.2
#: Rückgang und Folge-Sprung, die höchstens so weit auseinanderliegen, verbinden zwei Paare zu einem Lauf.
NAHT_STUNDEN = 24
#: Ein Stand stimmt mit dem HA-Spiegel überein, wenn er um höchstens diese Menge (kWh) abweicht.
SPIEGEL_TOLERANZ_KWH = 0.01


@dataclass(frozen=True)
class Schritt:
    """Ein Schritt der Reihe: von der Zeile ``von`` (Stand ``stand_vorher``) zur Zeile ``bis`` (Stand ``stand_nachher``)."""

    von: datetime
    bis: datetime
    stand_vorher: float
    stand_nachher: float

    @property
    def delta_kwh(self) -> float:
        return self.stand_nachher - self.stand_vorher

    @property
    def tag(self) -> date:
        """Der Kalendertag, dessen Tageswert den Schritt trägt — eine Zeile genau um Mitternacht schließt den Vortag."""
        return (self.bis - timedelta(microseconds=1)).date()


@dataclass(frozen=True)
class VersatzLauf:
    """Ein versetzter Abschnitt: seine Sprünge und Rückgänge in zeitlicher Folge (ein Paar, beim zerteilten Lauf mehr)."""

    spruenge: tuple[Schritt, ...]
    rueckgaenge: tuple[Schritt, ...]

    @property
    def beginn(self) -> Schritt:
        return self.spruenge[0]

    @property
    def ende(self) -> Schritt:
        return self.rueckgaenge[-1]

    @property
    def versatz_kwh(self) -> float:
        """Die Höhe des Versatzes am Beginn (der erste Sprung)."""
        return self.beginn.delta_kwh

    @property
    def rand_tage(self) -> tuple[date, date]:
        """Tag des ersten Sprungs und Tag des letzten Rückgangs."""
        return self.beginn.tag, self.ende.tag

    @property
    def tage_zu_hoch(self) -> list[date]:
        return sorted({s.tag for s in self.spruenge})

    @property
    def tage_ohne_wert(self) -> list[date]:
        return sorted({r.tag for r in self.rueckgaenge})


def _schritte(staende: Sequence[tuple[datetime, float]]) -> list[Schritt]:
    return [Schritt(staende[i - 1][0], staende[i][0], staende[i - 1][1], staende[i][1]) for i in range(1, len(staende))]


def sprung_schwelle(schritte: Sequence[Schritt]) -> float:
    """Die Sprung-Schwelle einer Reihe: ``max(SPRUNG_FAKTOR × Median der positiven Schritte, SPRUNG_MIN_KWH)``."""
    positiv = [s.delta_kwh for s in schritte if s.delta_kwh > 0]
    median = statistics.median(positiv) if positiv else 0.0
    return max(SPRUNG_FAKTOR * median, SPRUNG_MIN_KWH)


def ist_stufen_rueckgang(s: Schritt) -> bool:
    """Ein Rückgang, der nicht nach einem Neubeginn aussieht (der neue Stand bleibt über ``RESET_ANTEIL`` des alten und
    über ``RESET_MIN_STAND``)."""
    return (s.delta_kwh < -RUECKGANG_MIN_KWH and s.stand_nachher >= RESET_ANTEIL * s.stand_vorher
            and s.stand_nachher >= RESET_MIN_STAND)


def aehnlich(sprung_kwh: float, rueckgang_kwh: float) -> bool:
    """Gehören ein Sprung um ``sprung_kwh`` und ein Rückgang um ``rueckgang_kwh`` (beide als Betrag) zusammen?"""
    return abs(sprung_kwh - rueckgang_kwh) <= AEHNLICH_ANTEIL * sprung_kwh


def _paare(schritte: Sequence[Schritt], schwelle: float) -> list[tuple[Schritt, Schritt]]:
    """Je Stufen-Rückgang der nächstliegende vorangehende, noch ungepaarte Sprung ähnlicher Größe — nach Sprung sortiert."""
    offen: list[Schritt] = []
    paare: list[tuple[Schritt, Schritt]] = []
    for s in schritte:
        if s.delta_kwh > schwelle:
            offen.append(s)
            continue
        if not ist_stufen_rueckgang(s):
            continue
        treffer = next((j for j in range(len(offen) - 1, -1, -1) if aehnlich(offen[j].delta_kwh, -s.delta_kwh)), None)
        if treffer is not None:
            paare.append((offen.pop(treffer), s))
    return sorted(paare, key=lambda p: p[0].bis)


def _gehoeren_zusammen(lauf: VersatzLauf, sprung: Schritt) -> bool:
    """Schließt ``sprung`` (der Beginn des nächsten Paars) höchstens ``NAHT_STUNDEN`` nach dem Ende von ``lauf`` ähnlich
    groß an — dann ist es dasselbe versetzte Stück mit einem Loch."""
    abstand = sprung.bis - lauf.ende.bis
    return timedelta(0) <= abstand <= timedelta(hours=NAHT_STUNDEN) and aehnlich(sprung.delta_kwh, -lauf.ende.delta_kwh)


def finde_versatz_laeufe(staende: Sequence[tuple[datetime, float]]) -> list[VersatzLauf]:
    """Reine Funktion: ``staende`` = ``(zeitpunkt, stand)`` einer Reihe, aufsteigend. Je versetztem Abschnitt ein
    ``VersatzLauf`` (Regel im Modulkopf), in zeitlicher Folge."""
    schritte = _schritte(staende)
    laeufe: list[VersatzLauf] = []
    for sprung, rueckgang in _paare(schritte, sprung_schwelle(schritte)):
        if laeufe and _gehoeren_zusammen(laeufe[-1], sprung):
            letzter = laeufe.pop()
            laeufe.append(VersatzLauf(letzter.spruenge + (sprung,), letzter.rueckgaenge + (rueckgang,)))
        else:
            laeufe.append(VersatzLauf((sprung,), (rueckgang,)))
    return laeufe


def stand_passt_zum_spiegel(stand: float, summe: Optional[float], offset: float) -> bool:
    """Stimmt ein Stand der Reihe mit dem HA-Spiegel überein (``summe + offset`` der zum Zeitpunkt gültigen Quelle,
    Toleranz ``SPIEGEL_TOLERANZ_KWH``)? Ohne Spiegelzeile nein."""
    return summe is not None and abs(stand - (summe + offset)) <= SPIEGEL_TOLERANZ_KWH


__all__ = [
    "AEHNLICH_ANTEIL", "NAHT_STUNDEN", "RESET_ANTEIL", "RESET_MIN_STAND", "RUECKGANG_MIN_KWH", "SPIEGEL_TOLERANZ_KWH",
    "SPRUNG_FAKTOR", "SPRUNG_MIN_KWH", "Schritt", "VersatzLauf", "aehnlich", "finde_versatz_laeufe",
    "ist_stufen_rueckgang", "sprung_schwelle", "stand_passt_zum_spiegel",
]
