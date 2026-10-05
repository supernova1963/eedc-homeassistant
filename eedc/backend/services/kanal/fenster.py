"""Fenster-Helfer der Lese-Schicht — Tages- und Monatsfenster so, wie der BESTAND sie bildet (HA-Bauform E3, Auftrag Punkt 4).

Die Lese-Schicht (``lesen.py``) kennt keine Tages- oder Monatsdefinition: ihre Zeitgrenzen sind absolute Zeit
(Unix-Sekunden), ein Zeitraum ist ``[von, bis)`` in HAs Lesart (``recorder_statistics.py::_statistics_at_time``:
der Stand vor ``t`` ist die letzte Zeile mit ``start_ts < t``). Wer einen Tag oder Monat meint, holt die Grenzen
HIER — an einer Stelle.

**Tagesfenster = das Rückwärts-Fenster des Bestands** ``[Vortag 23:00, 23:00)`` (N-434, #144): Σ Slot 0…23 der
Stundenzeilen. Die Randzeilen kommen aus der EINEN Umrechnung ``slot_konvention.tagesfenster_start_ts`` (E2, H2
abgenommen); sie nennt die ``start_ts`` der beiden Zeilen, die Slot 23 des Vortags bzw. des Tages schließen (Wanduhr
22:00). Der Stand, den eine Zeile trägt, gilt am ENDE ihrer Stunde — die absolute Grenze ist deshalb
``start_ts + 3600`` (Wanduhr 23:00). Damit ist ``zeitraum(k, *tagesfenster(D))`` genau der Δ, den E2 über
``tagesfenster_start_ts`` rechnete, und genau der Tageswert des Bestands (Symmetrie-Wächter, ``kanal_symmetrie.py``).

**Monatsfenster** = Anfang des Tagesfensters des Ersten bis Ende des Tagesfensters des Letzten
(``[letzter Tag des Vormonats 23:00, letzter Tag 23:00)``) — die Summe der Tageswerte des Monats, wie
``energie_profil/monats_aus_tagen.py::lade_monats_summen_aus_tagen`` sie bildet. Aufeinanderfolgende Monatsfenster
stoßen lückenlos aneinander; die Monatsreihe braucht deshalb n+1 Grenzen für n Monate.

**Kalendermonatsfenster** = ``[1. 00:00, 1. des Folgemonats 00:00)`` — die ZWEITE Monatsgrenze, die eedc heute kennt:
der HA-Monatsleser ``ha_statistics_service.get_sensor_monatswert`` rechnet über ``_monatsgrenzen_ts`` genau so
(Probe: gleich für jeden Monat, in drei Zonen). Wer in E4 einen ``get_sensor_monatswert``-Nutzer umhängt, bekommt diese
Grenze als Parameter (Vormerkung Master 06.10.); R-3 („Kalendertag") bleibt S4. Aufeinanderfolgende Kalendermonate stoßen
ebenfalls lückenlos aneinander. Sie sind KEINE Summe von Tagesfenstern (die Stunde 23:00–24:00 des Monatsletzten gehört
zum Kalendermonat, im Tagesfenster aber zum Folgetag).

Zeitzone: wie im ganzen Bestand die Prozesszone (CLAUDE.md, „Die Zeitzone der App wird NICHT festgenagelt").
Die Wanduhr 22:00/23:00 fällt in Berlin, UTC und Auckland an keinem Umstellungstag aus (Umstellung um 02:00/03:00);
gemessen in ``test_kanal_lesen_fenster.py`` in allen drei Zonen.

Schwesterdateien: ``lesen.py``, ``monatsraster.py``, ``quellenwahl.py``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from backend.core.berechnungen.slot_konvention import tagesfenster_start_ts

_STUNDE = 3600


def tagesfenster(datum: date) -> tuple[int, int]:
    """Das Tagesfenster des Bestands als absolute Grenzen ``(von, bis)`` — ``[Vortag 23:00, 23:00)``."""
    von_zeile, bis_zeile = tagesfenster_start_ts(datum)
    return von_zeile + _STUNDE, bis_zeile + _STUNDE


def _letzter_tag(jahr: int, monat: int) -> date:
    return (date(jahr + 1, 1, 1) if monat == 12 else date(jahr, monat + 1, 1)) - timedelta(days=1)


def monatsfenster(jahr: int, monat: int) -> tuple[int, int]:
    """Das Monatsfenster des Bestands: Anfang des Tagesfensters des Ersten bis Ende des Tagesfensters des Letzten."""
    return tagesfenster(date(jahr, monat, 1))[0], tagesfenster(_letzter_tag(jahr, monat))[1]


def kalendermonatsfenster(jahr: int, monat: int) -> tuple[int, int]:
    """Der Kalendermonat als absolute Grenzen ``[1. 00:00, 1. des Folgemonats 00:00)`` (Prozesszone) — wie
    ``ha_statistics_service._monatsgrenzen_ts``."""
    folge = date(jahr + 1, 1, 1) if monat == 12 else date(jahr, monat + 1, 1)
    return (int(round(datetime.combine(date(jahr, monat, 1), time()).timestamp())),
            int(round(datetime.combine(folge, time()).timestamp())))


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
