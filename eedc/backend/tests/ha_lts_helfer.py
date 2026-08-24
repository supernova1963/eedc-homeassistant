"""Eine Quelle für das HA-Statistics-Schema in den `test_ha_lts_*`-Proben.

**Warum es diese Datei gibt.** Die vier Dateien der `ha_lts`-Familie
(`test_ha_lts_hourly_reader.py` · `test_ha_lts_mean_reader.py` ·
`test_ha_lts_minmax_reader.py` · `test_ha_lts_monatswerte_lookup.py`) bauten
sich ihre In-Memory-Datenbank **je selbst**: vier Fassungen desselben
Service-Konstruktors zu 28–33 Zeilen, jede mit einer eigenen handgeschriebenen
`CREATE TABLE`-Folge, dazu vier Varianten von `_seed_sensor`. Rund 120 Zeilen
DDL in vier Kopien.

**Das Schema gehört nicht uns.** Es ist Home Assistants Recorder-Schema
(`statistics_meta` · `statistics` · `statistics_short_term`) — es ändert sich
ohne unser Zutun. Vier Kopien einer fremden Struktur driften nicht *vielleicht*,
sondern sobald HA eine Spalte anfasst; und eine Probe, die gegen ein veraltetes
Schema grün meldet, behauptet mehr als sie weiß. Dieselbe Begründung wie bei
`quellbaum.py` (neun Kopien der Frage „was ist der Produktivbaum", zwei davon
falsch, beide grün) — **eine Definition kann nicht auseinanderlaufen.**

**Warum die Bestandsdateien ihre lokalen Namen behalten.** Jede der vier Dateien
behält `_make_service…` / `_seed_sensor` / ihren Zeilen-Seeder als
**einzeilige Delegation** hierher. Das ist bewusst und folgt dem Hausstil, den
E4 gesetzt hat: **30 Testdateien** tragen heute einen solchen dünnen Alias auf
`factories`. So bleiben alle **55** Aufrufstellen unangetastet — eine
Konsolidierung, die 55 Zeilen umschreibt, kann Fälle verlieren; eine, die nur
die Definition ersetzt, kann es nicht.

⚠ **Kein Export darf mit `test` beginnen.** `python_functions = test*` greift auf
jeden Namen im Modul-Namensraum des **Importeurs** — pytest sammelte am 24.08.
schon einmal eine importierte Quell-Funktion (`quellbaum.testbaum`) als
Testfunktion ein und zählte sie grün.

**Das Schema hier ist die Vereinigung aller vier Fassungen** — beide Tabellen mit
`min`/`max`, dazu `statistics_short_term`. Am Bestand geprüft: keine der vier
Proben behauptet die *Abwesenheit* einer Tabelle oder Spalte, und alle
`INSERT`s nennen ihre Spalten ausdrücklich. Mehr Spalten heißt hier also näher
an der echten HA-Datenbank, nicht lockerer.
"""

from __future__ import annotations

import time as _zeit_modul
from datetime import datetime

from sqlalchemy import create_engine, text

from backend.services.ha_statistics_service import HAStatisticsService

#: Die beiden Werte-Tabellen des Recorders — gleiche Struktur, andere Auflösung.
_WERTE_TABELLEN = ("statistics", "statistics_short_term")


def mach_service() -> HAStatisticsService:
    """`HAStatisticsService` auf einer frischen In-Memory-SQLite mit HA-Schema.

    Der reguläre Konstruktor setzt alle Felder (u. a. den Metadaten-Cache) und
    macht kein I/O — `_init_engine` wird erst beim ersten Zugriff gerufen und
    hier durch `_initialized` übersprungen. `_initialized = True` ist nötig,
    damit `is_available` liefert, ohne `_init_engine` erneut anzustoßen.
    """
    svc = HAStatisticsService()
    svc._engine = create_engine("sqlite:///:memory:")
    svc._is_mysql = False
    svc._initialized = True
    with svc._engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE statistics_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                statistic_id TEXT,
                unit_of_measurement TEXT,
                has_sum INTEGER,
                has_mean INTEGER
            )
        """))
        for tabelle in _WERTE_TABELLEN:
            conn.execute(text(f"""
                CREATE TABLE {tabelle} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metadata_id INTEGER,
                    start_ts REAL,
                    state REAL,
                    sum REAL,
                    mean REAL,
                    min REAL,
                    max REAL
                )
            """))
    return svc


def sensor(
    svc: HAStatisticsService,
    entity_id: str,
    unit: str,
    *,
    has_sum: bool = True,
    has_mean: bool | None = None,
) -> int:
    """Eine Zeile in `statistics_meta`; liefert die `metadata_id`.

    `has_mean` folgt standardmäßig aus `has_sum` — ein Zähler (`has_sum`) trägt
    keinen Mittelwert, ein Messwert umgekehrt. Das deckt alle vier
    Bestandsfassungen deckungsgleich ab: die drei Reader-Proben legten
    ausschließlich das eine oder das andere an, und
    `test_ha_lts_monatswerte_lookup.py` rechnete `has_mean` wörtlich so aus.
    Wer beides oder keines braucht, setzt `has_mean` ausdrücklich.
    """
    if has_mean is None:
        has_mean = not has_sum
    with svc._engine.begin() as conn:
        ergebnis = conn.execute(
            text(
                "INSERT INTO statistics_meta "
                "(statistic_id, unit_of_measurement, has_sum, has_mean) "
                "VALUES (:sid, :unit, :hs, :hm)"
            ),
            {"sid": entity_id, "unit": unit,
             "hs": 1 if has_sum else 0, "hm": 1 if has_mean else 0},
        )
        return ergebnis.lastrowid


def zeile(
    svc: HAStatisticsService,
    metadata_id: int,
    wann: datetime,
    *,
    state: float | None = None,
    sum_wert: float | None = None,
    mean: float | None = None,
    min_wert: float | None = None,
    max_wert: float | None = None,
    tabelle: str = "statistics",
) -> None:
    """Eine Werte-Zeile schreiben.

    `wann` ist `start_ts`. HA-Konvention: der Wert gehört ans **Ende** der
    Periode, ein Stundenwert mit `start_ts = 12:00` beschreibt also 12:00–13:00.
    Die Umrechnung geht bewusst über `time.mktime` und damit über die **lokale**
    Zone — genau so schreibt der Recorder, und genau so lesen die Prüflinge.
    """
    ts = _zeit_modul.mktime(wann.timetuple())
    with svc._engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {tabelle} "
                "(metadata_id, start_ts, state, sum, mean, min, max) "
                "VALUES (:mid, :ts, :state, :sum, :mean, :min, :max)"
            ),
            {"mid": metadata_id, "ts": ts, "state": state, "sum": sum_wert,
             "mean": mean, "min": min_wert, "max": max_wert},
        )
