"""Fenster-Helfer der Lese-Schicht — Kalendertag und Kalendermonat der Kanal-Schicht (HA-Bauform E3, seit S4 E-S4-1:
R-3, Bauplan S4 §4 S4-R-3a).

Die Lese-Schicht (``lesen.py``) kennt keine Tages- oder Monatsdefinition: ihre Zeitgrenzen sind absolute Zeit
(Unix-Sekunden), ein Zeitraum ist ``[von, bis)`` in HAs Lesart (``recorder_statistics.py::_statistics_at_time``:
der Stand vor ``t`` ist die letzte Zeile mit ``start_ts < t``). Wer einen Tag oder Monat meint, holt die Grenzen
HIER — an einer Stelle.

**Tagesfenster = der Kalendertag** ``[D 00:00, D+1 00:00)`` in der Prozesszone (R-3, wie HAs Energie-Dashboard). Eine
Zeile ``start_ts = H`` trägt den Stand am ENDE ihrer Stunde; der Stand vor ``D 00:00`` ist also die Zeile ``D−1 23:00``,
der Tag besteht aus den Zeilen ``D 00:00 … D 23:00`` (23 bzw. 25 an den Umstellungstagen) — die Grenze liegt genau auf
einer Zeilengrenze. Bis E-S4-1 war das Tagesfenster das Rückwärts-Fenster des Bestands ``[Vortag 23:00, 23:00)``
(N-434); der Unterschied je Kanal und Tag ist die Randstunde ``change(D 23:00) − change(D−1 23:00)`` (S4-R-3d).
**Bestandstage** (Stundenzeilen ``TagesEnergieProfil``, Tageszeilen) bleiben, wie sie geschrieben sind — ihr Fenster nennt
``slot_konvention.tagesfenster_start_ts`` (Schreiber und HA-Leser, unverändert; S4-R-3c).

**Monatsfenster = Kalendermonat** ``[1. 00:00, 1. des Folgemonats 00:00)`` — ``monatsfenster`` und
``kalendermonatsfenster`` sind seit E-S4-1 EIN Körper (beide Namen bleiben, damit kein Aufrufer sich ändert; S5
verschmilzt sie). Er ist die Grenze des HA-Monatslesers ``ha_statistics_service.get_sensor_monatswert``
(``_monatsgrenzen_ts``; Probe: gleich für jeden Monat, in drei Zonen) und **per Konstruktion** die Σ seiner
Kalendertage: aufeinanderfolgende Tage und Monate stoßen lückenlos aneinander, die Monatsreihe braucht n+1 Grenzen für n
Monate (``monatsgrenzen``).

Zeitzone: wie im ganzen Bestand die Prozesszone (CLAUDE.md, „Die Zeitzone der App wird NICHT festgenagelt").
Mitternacht fällt in Berlin, UTC und Auckland an keinem Umstellungstag aus (Umstellung um 02:00/03:00); gemessen in
``test_kanal_lesen_fenster.py`` in allen drei Zonen (Umstellungstage 23/25 Stunden).

Schwesterdateien: ``lesen.py``, ``monatsraster.py``, ``quellenwahl.py``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta


def _mitternacht(datum: date) -> int:
    """Wanduhr ``datum`` 00:00 in der Prozesszone als Unix-Sekunden."""
    return int(round(datetime.combine(datum, time()).timestamp()))


def tagesfenster(datum: date) -> tuple[int, int]:
    """Der Kalendertag als absolute Grenzen ``(von, bis)`` — ``[D 00:00, D+1 00:00)`` (Prozesszone, S4-R-3a)."""
    return _mitternacht(datum), _mitternacht(datum + timedelta(days=1))


def kalendertag_der_stunde(start_ts: int) -> date:
    """Der Kalendertag, zu dem die Stunde ``start_ts`` gehört (Datum ihres Beginns, Prozesszone) — die Zeile liegt in
    ``tagesfenster(tag)``. Gegenstück zu ``abgeleitet.tag_der_stunde`` (Bestands-Fenster ``[Vortag 23:00, 23:00)``)."""
    return datetime.fromtimestamp(start_ts).date()


def _folgemonat(jahr: int, monat: int) -> date:
    return date(jahr + 1, 1, 1) if monat == 12 else date(jahr, monat + 1, 1)


def kalendermonatsfenster(jahr: int, monat: int) -> tuple[int, int]:
    """Der Kalendermonat als absolute Grenzen ``[1. 00:00, 1. des Folgemonats 00:00)`` (Prozesszone) — wie
    ``ha_statistics_service._monatsgrenzen_ts`` und = Anfang des Tagesfensters des Ersten bis Ende des Tagesfensters des
    Letzten."""
    return _mitternacht(date(jahr, monat, 1)), _mitternacht(_folgemonat(jahr, monat))


def monatsfenster(jahr: int, monat: int) -> tuple[int, int]:
    """Das Monatsfenster der Kanal-Schicht — seit E-S4-1 der Kalendermonat (``kalendermonatsfenster``, ein Körper; S5
    verschmilzt die Namen)."""
    return kalendermonatsfenster(jahr, monat)


def monate(von_monat: tuple[int, int], bis_monat: tuple[int, int]) -> list[tuple[int, int]]:
    """Die Monate ``von_monat`` … ``bis_monat`` (beide inklusive) als ``(jahr, monat)``, aufsteigend."""
    (j, m), out = von_monat, []
    while (j, m) <= bis_monat:
        out.append((j, m))
        j, m = (j + 1, 1) if m == 12 else (j, m + 1)
    return out


def monatsgrenzen(von_monat: tuple[int, int], bis_monat: tuple[int, int]) -> list[int]:
    """Die n+1 Grenzen der Monatsfenster ``von_monat`` … ``bis_monat`` (inklusive) — lückenlos aneinander."""
    liste = monate(von_monat, bis_monat)
    if not liste:
        return []
    return [monatsfenster(j, m)[0] for j, m in liste] + [monatsfenster(*liste[-1])[1]]
