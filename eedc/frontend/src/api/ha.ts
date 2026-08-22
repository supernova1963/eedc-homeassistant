/**
 * Home Assistant Integration API Client
 *
 * Nur noch Status und Export (MQTT + YAML). Das Sensor-Listing und das
 * Legacy-Mapping (`getSensors`/`getMapping`) fielen mit der V3-Bereinigung
 * 2026-08 — clientlos seit dem IA-V4-Flip, die Sensor-Auswahl läuft über die
 * Datenquellen-Fläche.
 */

import { api } from './client'

// =============================================================================
// Basic HA Types
// =============================================================================

export interface HAStatus {
  connected: boolean
  rest_api?: boolean
  ha_version?: string
  message: string
}

// =============================================================================
// HA Export Types
// =============================================================================

export interface SensorExportItem {
  key: string
  name: string
  value: number | string | null
  unit: string
  icon: string
  category: string
  formel: string
  berechnung: string | null
  device_class: string | null
  state_class: string | null
}

export interface AnlageExport {
  anlage_id: number
  anlage_name: string
  sensors: SensorExportItem[]
}

export interface InvestitionExport {
  investition_id: number
  bezeichnung: string
  typ: string
  sensors: SensorExportItem[]
}

export interface FullExportResponse {
  anlagen: AnlageExport[]
  investitionen: InvestitionExport[]
  sensor_count: number
  mqtt_available: boolean
}

export interface HAYamlSnippet {
  yaml: string
  sensor_count: number
  hinweis: string
}

export interface MQTTConfig {
  host: string
  port: number
  username?: string
  password?: string
}

export interface MQTTConfigFromAddon {
  enabled: boolean
  host: string
  port: number
  username: string
  password: string  // Maskiert wenn gesetzt
  auto_publish: boolean
  publish_interval_minutes: number
  /** Ist überhaupt ein Broker hinterlegt? `host` taugt dafür nicht — die
   *  Auflösung liefert immer einen (Default `core-mosquitto`). */
  broker_konfiguriert: boolean
}

export interface MQTTTestResult {
  connected: boolean
  broker?: string
  message?: string
  error?: string
  hint?: string
}

export interface MQTTPublishResult {
  message: string
  anlage_id: number
  total: number
  success: number
  failed: number
  /**
   * Gesetzt, wenn der Aufruf gescheitert ist — dann trägt `message` den Grund
   * der API (z. B. „Keine Monatsdaten vorhanden", HTTP 404).
   *
   * Ohne dieses Feld war ein Fehlschlag von einem Erfolg nicht zu
   * unterscheiden: der Client baute im `catch` ein Ergebnis mit `total: 0`,
   * und die Anzeige machte daraus „0 von 0 Sensoren publiziert" samt grünem
   * Häkchen (T89667 #112, Phir0n). Der Grund stand in `message` und wurde nie
   * gerendert.
   */
  fehlgeschlagen?: boolean
}

// =============================================================================
// API Client
// =============================================================================

export const haApi = {
  /**
   * HA-Verbindungsstatus prüfen
   */
  async getStatus(): Promise<HAStatus> {
    return api.get<HAStatus>('/ha/status')
  },

  // ===========================================================================
  // HA Export API
  // ===========================================================================

  /**
   * Aufgelöste MQTT-Broker-Konfiguration abrufen (B7-5: gemeinsamer Broker aus
   * dem Broker-Block, ENV/Add-on-Optionen nur noch als Fallback).
   */
  async getMqttConfig(): Promise<MQTTConfigFromAddon> {
    return api.get<MQTTConfigFromAddon>('/ha/export/mqtt/config')
  },

  /**
   * Automatischen Export (Auto-Publish) ein-/ausschalten — B7-5b.
   * Wirkt sofort: der Scheduler-Job prüft die Einstellung bei jedem Lauf.
   */
  async setAutoPublish(enabled: boolean): Promise<{ gespeichert: boolean; enabled: boolean }> {
    return api.post<{ gespeichert: boolean; enabled: boolean }>(
      '/ha/export/mqtt/auto-publish',
      { enabled },
    )
  },

  /**
   * Alle exportierbaren Sensoren abrufen
   */
  async getExportSensors(): Promise<FullExportResponse> {
    return api.get<FullExportResponse>('/ha/export/sensors')
  },

  /**
   * Sensoren für eine Anlage abrufen
   */
  async getAnlageSensors(anlageId: number): Promise<AnlageExport> {
    return api.get<AnlageExport>(`/ha/export/sensors/${anlageId}`)
  },

  /**
   * YAML-Snippet für HA configuration.yaml generieren
   */
  async getYamlSnippet(anlageId: number): Promise<HAYamlSnippet> {
    return api.get<HAYamlSnippet>(`/ha/export/yaml/${anlageId}`)
  },

  /**
   * MQTT-Verbindung testen. Ohne `config` nimmt der Server den gemeinsamen
   * Broker (B7-5) — der Regelfall; `config` bleibt für Ad-hoc-Tests.
   */
  async testMqtt(config?: MQTTConfig): Promise<MQTTTestResult> {
    return api.post<MQTTTestResult>('/ha/export/mqtt/test', config || {})
  },

  /**
   * Sensoren via MQTT publizieren
   */
  async publishMqtt(anlageId: number, config?: MQTTConfig): Promise<MQTTPublishResult> {
    return api.post<MQTTPublishResult>(`/ha/export/mqtt/publish/${anlageId}`, config || {})
  },

  /**
   * Sensoren aus MQTT Discovery entfernen
   */
  async removeMqtt(anlageId: number, _config?: MQTTConfig): Promise<void> {
    // Note: Config wird derzeit nicht verwendet, da DELETE keinen Body unterstützt
    return api.delete(`/ha/export/mqtt/remove/${anlageId}`)
  },
}
