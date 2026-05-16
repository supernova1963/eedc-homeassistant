"""
Source-Hierarchie für Schreib-Entscheidungen auf Aggregat-Tabellen
(Etappe 3d Päckchen 1).

Niedrigere Zahl = höhere Priorität. Eingesetzt von
`backend.services.provenance.write_with_provenance()` ab Päckchen 3.

Konzept: docs/KONZEPT-DATENPIPELINE.md Sektion 3.1.

Vokabular ist hier abgeschlossen pro Päckchen-Lieferung — neue Schreib-Pfade
müssen ihr Source-Label hier eintragen, sonst weist der Helper sie ab.
Hierarchie-Verletzungen werden im Audit-Log mit decision="rejected_lower_priority"
dokumentiert; gleiche Priorität ist Last-Writer-Wins (akzeptiert, gleiche
Vertrauensklasse). Repair-Source steht als eigene Stufe über allem, damit
explizite User-Reset-Läufe im Audit-Log auf den ersten Blick erkennbar sind.
"""

from enum import IntEnum


class SourcePriority(IntEnum):
    """Schreib-Hierarchie. Niedrigere Zahl gewinnt."""

    REPAIR = 0
    """Repair-Orchestrator mit force_override=True. Steht über allem,
    audit-log-pflichtig mit Operation-ID."""

    MANUAL = 1
    """User-Eingabe (Form, CSV-Wizard). Niemals von Maschine überschreiben."""

    EXTERNAL_AUTHORITATIVE = 2
    """Maschinen-bestätigte Quelle (Cloud-Portal, HA-Statistics-LTS).
    Konflikt zwischen Cloud + HA-Stats: Last-Writer-Wins (selten in Praxis,
    eindeutiger Pfad pro Anlage)."""

    AUTO_AGGREGATION = 3
    """Berechnet, Annahmen-behaftet (Monatsabschluss-Roll-up)."""

    FALLBACK = 4
    """Best-Effort, lückenanfällig (Snapshot-Aggregator, MQTT-Fallback)."""

    LEGACY = 5
    """Bestandsdaten ohne dokumentierte Quelle. Initial-Provenance der
    Pre-3d-Rows: alles, was vor Etappe 3d Päckchen 3 in den Aggregat-Tabellen
    stand. Niedrigste Priorität — der erste bewusste Schreiber gewinnt
    automatisch, statt stillschweigend wegen `existing=None` zu greifen.
    Wird ausschließlich von der Initial-Migration in `_run_data_migrations`
    gesetzt, nie von Schreib-Pfaden zur Laufzeit."""


SOURCE_LABELS: dict[str, SourcePriority] = {
    # Repair (force_override über Repair-Orchestrator, P4-Lieferung)
    "repair": SourcePriority.REPAIR,

    # Manual (User-Eingabe oder User-bestätigte Aktion)
    "manual:form": SourcePriority.MANUAL,
    "manual:csv_import": SourcePriority.MANUAL,
    # P2-Erweiterung: Anlagen-Backup-Restore + Backup-CSV-Re-Import.
    # Beide sind explizite User-Klicks („Backup einspielen") — User-Wille,
    # also MANUAL-Klasse. Bei gleichzeitigem manual:form-Eintrag im selben
    # Feld gewinnt Last-Writer-Wins.
    "manual:json_backup": SourcePriority.MANUAL,
    "manual:csv_backup":  SourcePriority.MANUAL,

    # External Authoritative — 11 Cloud-Provider aus services/cloud_import/
    # Apply-Pfad: routes/data_import.py → routes/import_export/helpers.py
    # _upsert_investition_monatsdaten. P2 stellt diesen Helper auf
    # write_with_provenance() um.
    "external:cloud_import:anker_solix":         SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:deye_solarman":       SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:ecoflow_powerocean":  SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:ecoflow_powerstream": SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:fronius_solarweb":    SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:growatt":             SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:hoymiles_smiles":     SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:huawei_fusionsolar":  SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:solaredge":           SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:sungrow_isolarcloud": SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:viessmann_gridbox":   SourcePriority.EXTERNAL_AUTHORITATIVE,

    # External Authoritative — HA-Statistics-LTS-Backfill
    # (services/ha_statistics_service.py + routes/ha_statistics.py)
    "external:ha_statistics": SourcePriority.EXTERNAL_AUTHORITATIVE,

    # Etappe 4 (v3.31.0): HA-Statistics-LTS als Source-of-Truth für
    # TagesEnergieProfil + TagesZusammenfassung. Aufgesplittet nach
    # Auflösung, damit das Audit-Log unterscheiden kann, ob Stunden-
    # oder Tagessumme geschrieben wurde — wichtig für Konsistenz-
    # Diagnose (Σ Hourly == Daily-Summe?). Generisches `external:ha_statistics`
    # bleibt für punktuelle Snapshot-Self-Healing-Reads (sensor_snapshots).
    # Hierarchie identisch (EXTERNAL_AUTHORITATIVE), kein Wettbewerb mit
    # bestehendem Label.
    "external:ha_statistics:hourly": SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:ha_statistics:daily":  SourcePriority.EXTERNAL_AUTHORITATIVE,

    # External Authoritative — Wetter- und Prognose-Quellen (P3 Stub).
    # Diese drei Labels sind ein Vorgriff auf die Quellenwahl-Roadmap (Schritt
    # 4 SFML-Connector wäre sonst neuer Schreiber ohne Provenance — Risiko #3
    # im Konzept). Heute schreibt nur `routes/live_wetter.py:_persist_pv_prognose`
    # alle drei Felder an einer Stelle; mit dem Quellenwahl-Picker werden
    # SFML-Connector und Solcast-Service eigene Schreiber, die unter dem
    # gleichen Label-Vokabular weiterlaufen.
    "external:openmeteo":    SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:tom_ha_sfml":  SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:solcast":      SourcePriority.EXTERNAL_AUTHORITATIVE,

    # External Authoritative — Kraftstoff-Preis-Quellen (P3-Aufräum 2026-05-09).
    # Generisches Label statt provider-spezifisch (Memory-Linie
    # `feedback_pfadabhaengigkeits_reflex.md`): heute liefert nur EU Oil
    # Bulletin (`services/kraftstoff_preis_service.py`), spätere Provider
    # (Tankerkönig u. ä.) liefen unter dem gleichen Label, Writer-Feld zur
    # Unterscheidung.
    "external:fuel_price":   SourcePriority.EXTERNAL_AUTHORITATIVE,

    # P2-Erweiterung: Hersteller-Portal-Datei-Upload (Apply-Pfad in
    # routes/data_import.py) und Cloud-Sync-Apply ohne Provider-Spezifizierung.
    # Provider-spezifische external:cloud_import:<provider>-Labels werden
    # erst aktiv, wenn das Frontend den provider_id-Query-Param mitschickt
    # (heute setzt es nur datenquelle="portal_import"|"cloud_import").
    "external:portal_import": SourcePriority.EXTERNAL_AUTHORITATIVE,

    # Auto-Aggregation — Monatsabschluss-Roll-up aus Tageswerten
    # (routes/monatsabschluss.py — wird in P3 in Service-Schicht ausgelagert)
    "auto:monatsabschluss":  SourcePriority.AUTO_AGGREGATION,
    # P2-Erweiterung: Demo-Daten-Loader für Standalone-Erstinstallation.
    # AUTO_AGGREGATION-Klasse, damit nachträgliche manuelle Bearbeitung
    # die Demo-Werte sauber schlägt.
    "auto:demo_data": SourcePriority.AUTO_AGGREGATION,

    # Fallback — Sensor-Snapshot-Aggregator + MQTT-Inbound-Pfad
    "fallback:sensor_snapshot": SourcePriority.FALLBACK,
    "fallback:mqtt_inbound":    SourcePriority.FALLBACK,

    # Legacy — Bestandsdaten (P3 Initial-Migration). Gesetzt einmalig pro
    # Installation in `_run_data_migrations`, nie von Live-Schreib-Pfaden.
    "legacy:unknown": SourcePriority.LEGACY,
}


def get_priority(source: str) -> SourcePriority:
    """Liefert die Priorität für ein Source-Label.

    Wirft `KeyError`, wenn das Label nicht im Vokabular steht — Schreib-Pfade,
    die ein neues Label brauchen, müssen es hier eintragen, sonst gibt's keine
    stille Akzeptanz.
    """
    return SOURCE_LABELS[source]
