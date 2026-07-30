"""Datenquellen-Priorisierung — reine Merge-Präzedenz für aktueller_monat.

`get_aktueller_monat` sammelt Monatswerte aus vier Quellen (gespeichert,
Connector, MQTT-Inbound, HA-Statistics) und führt sie nach fester Präzedenz
zusammen. Das Sammeln ist I/O (DB/HA) und bleibt in der Route; die
Zusammenführungs-Regel ist reine Logik und lebt hier (ADR-001) — eine Stelle,
testbar, ohne Drift zwischen den vier `update`/`setdefault`-Zweigen.

Präzedenz (höchste überschreibt niedrigere):
  1. gespeicherte Monatsdaten (Basis)
  2. Connector (Geräte-Snapshot-Delta)
  3. MQTT-Inbound (Energy-Topics, nur laufender Monat — vom Aufrufer gegated)
  4. HA-Statistics (Recorder-DB)

Laufender Monat: jede frischere Quelle DARF gespeicherte Werte überschreiben
(Live-Vorschau) → `update`. Abgeschlossener Monat: gespeicherte/manuell
gepflegte Werte sind authoritativ — Connector und HA-Statistics füllen nur
fehlende Felder (`setdefault`), überschreiben NICHT rückwirkend (#325 Connector,
#118 HA-Statistics). MQTT wird für vergangene Monate vom Aufrufer gar nicht
erst gesammelt (leeres Dict).

**Connector im laufenden Monat — Abdeckung entscheidet.** Der Connector-Wert
ist die Differenz zweier Zähler-Snapshots und misst damit nur den Zeitraum
zwischen ihnen. Beginnt der erste Snapshot mitten im Monat (frisch
eingerichteter Connector), ist das Delta kein Monatswert, sondern ein
Teilzeitraum — es darf einen gespeicherten Monatswert dann NICHT überschreiben,
sondern nur füllen, was sonst fehlt. Der Wert für den nicht abgedeckten Teil
kommt aus dem Monatsdaten-Import (CSV/Statistik), der einzigen Quelle, die die
Zeit vor dem ersten Snapshot kennt. Bewusst NICHT: Import und Delta addieren
(die Abdeckung des Imports ist unbekannt — aneinandergestückelt wäre es Raten).

Werte sind `(float, DatenquelleInfo)`-Tupel; diese Funktion bewegt sie nur und
ist daher bewusst typ-agnostisch über das zweite Tupel-Element (kein Import aus
api/routes → keine Layer-Inversion). Die Abdeckung kommt deshalb als eigenes
Argument herein, nicht aus dem Wert-Tupel.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypeVar

_V = TypeVar("_V")


def connector_deckt_monatsanfang(
    abdeckung_von: datetime | None,
    monat_start: datetime | None,
) -> bool:
    """Deckt das Connector-Delta den Monat ab seinem ersten Tag ab?

    Nur dann ist es ein vollwertiger Monatswert. Unbekannte Abdeckung zählt
    als „deckt nicht" — ohne Beleg über den gemessenen Zeitraum wird kein
    gespeicherter Wert überschrieben.
    """
    if abdeckung_von is None or monat_start is None:
        return False
    return abdeckung_von <= monat_start


def merge_datenquellen(
    *,
    saved: dict[str, _V],
    connector: dict[str, _V],
    mqtt_energy: dict[str, _V],
    ha_stats: dict[str, _V],
    ist_aktueller_monat: bool,
    connector_abdeckung_von: datetime | None = None,
    monat_start: datetime | None = None,
) -> dict[str, _V]:
    """Führt die vier Datenquellen nach fester Präzedenz zusammen.

    Reine Funktion, kein I/O. Regeln siehe Modul-Docstring. ``mqtt_energy``
    wird unverändert per ``update`` angewendet — der Aufrufer übergibt für
    abgeschlossene Monate ein leeres Dict (MQTT wird dann nicht gesammelt).

    ``connector_abdeckung_von``/``monat_start`` beschreiben den Zeitraum, den
    das Connector-Delta wirklich misst. Fehlen sie, gilt die Abdeckung als
    unbekannt und der Connector überschreibt auch im laufenden Monat nicht.
    """
    resolved: dict[str, _V] = {}
    resolved.update(saved)

    if ist_aktueller_monat and connector_deckt_monatsanfang(
        connector_abdeckung_von, monat_start
    ):
        # Laufender Monat mit Abdeckung ab dem Monatsersten: Connector
        # (Konfidenz 90 %) ist frischer als die gespeicherten Werte und darf
        # sie überschreiben (Vorschau).
        resolved.update(connector)
    else:
        # Abgeschlossener Monat (#325, detlefh68) — oder laufender Monat, dessen
        # Connector-Delta erst mitten im Monat beginnt: gespeicherte Monatsdaten
        # sind authoritativ, der Connector füllt nur fehlende Felder.
        for k, v in connector.items():
            resolved.setdefault(k, v)

    resolved.update(mqtt_energy)

    if ist_aktueller_monat:
        # Laufender Monat: HA-Stats sind die frischeste Quelle (Live-Sensoren).
        resolved.update(ha_stats)
    else:
        # Vergangener Monat: HA-Stats nur als Fallback für fehlende Felder —
        # kein rückwirkender Override (#118).
        for k, v in ha_stats.items():
            resolved.setdefault(k, v)

    return resolved
