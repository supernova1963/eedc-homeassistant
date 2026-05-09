"""
Snapshot-Source-Marker (E3 aus KONZEPT-ENERGIEPROFIL-3C.md).

Schmale VARCHAR(20)-Klassifikation der Schreib-Pfade in `sensor_snapshots`,
damit die Diagnose-Frage „Welche Snapshots kommen aus welchem Pfad?"
beantwortbar wird (Auslöser MartyBr-Sensor-Migration 7.5.2026).

`sensor_snapshots` hält pro Zeile genau ein Datenfeld, daher reicht ein
einzelner Spalten-Marker. Etappe 3d generalisiert das Pattern auf
JSON-Spalten mit Per-Feld-Provenance der vier Aggregat-Tabellen
(`monatsdaten`, `investition_monatsdaten`, `tages_zusammenfassung`,
`tages_energie_profil`).
"""

from __future__ import annotations

from typing import Final


class SnapshotSource:
    """Konstanten für die `quelle`-Spalte auf `sensor_snapshots`."""

    #: HA Long-Term Statistics (Add-on-Modus, hourly :05-Job + Resnap)
    HA_STATISTICS: Final[str] = "ha_statistics"
    #: mqtt_energy_snapshots-Tabelle (Standalone-Modus, MQTT-Topic-Inbound)
    MQTT_INBOUND: Final[str] = "mqtt_inbound"
    #: Live-Annäherungswert vor voller Stunde (Standalone-Modus,
    #: `live_snapshot_if_missing`)
    MQTT_LIVE: Final[str] = "mqtt_live"
    #: MQTT-Fallback im Self-Healing-Read, wenn HA-Statistics None lieferte
    #: (Add-on-Modus mit MQTT als Backup)
    LIVE_FALLBACK: Final[str] = "live_fallback"
    #: Legacy / vor Etappe 3c P1 / unklassifiziert
    UNKNOWN: Final[str] = "unknown"


ALL_SOURCES: frozenset[str] = frozenset({
    SnapshotSource.HA_STATISTICS,
    SnapshotSource.MQTT_INBOUND,
    SnapshotSource.MQTT_LIVE,
    SnapshotSource.LIVE_FALLBACK,
    SnapshotSource.UNKNOWN,
})


def assert_valid_source(quelle: str) -> None:
    """Validiert ein Source-Label gegen `ALL_SOURCES`. Hebt ValueError bei Unbekannten."""
    if quelle not in ALL_SOURCES:
        raise ValueError(
            f"Unbekannte Snapshot-Quelle {quelle!r}. "
            f"Erwartet eine aus: {sorted(ALL_SOURCES)}"
        )
