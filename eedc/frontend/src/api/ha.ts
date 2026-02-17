/**
 * Home Assistant Integration API Client
 *
 * Bereinigt in v1.1: Nur noch Status, Sensor-Listing und Export.
 * Komplexe Features (Discovery, Statistics-Import, StringMonatsdaten) wurden entfernt.
 */

import { api } from './client'

// =============================================================================
// Basic HA Types
// =============================================================================

export interface HASensor {
  entity_id: string
  friendly_name: string | null
  unit_of_measurement: string | null
  device_class: string | null
  state_class: string | null
  state: string | null
}

export interface HAStatus {
  connected: boolean
  rest_api?: boolean
  ha_version?: string
  message: string
}

export interface HASensorMapping {
  pv_erzeugung: string | null
  einspeisung: string | null
  netzbezug: string | null
  batterie_ladung: string | null
  batterie_entladung: string | null
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
}

export interface SensorDefinition {
  key: string
  name: string
  unit: string
  icon: string
  category: string
  formel: string
  device_class: string | null
  state_class: string | null
  enabled_by_default: boolean
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

  /**
   * Alle Energy-relevanten Sensoren abrufen
   */
  async getSensors(): Promise<HASensor[]> {
    return api.get<HASensor[]>('/ha/sensors')
  },

  /**
   * Sensor-Mapping Konfiguration abrufen (Legacy)
   */
  async getMapping(): Promise<HASensorMapping> {
    return api.get<HASensorMapping>('/ha/mapping')
  },

  // ===========================================================================
  // HA Export API
  // ===========================================================================

  /**
   * MQTT-Konfiguration aus Add-on Optionen abrufen
   */
  async getMqttConfig(): Promise<MQTTConfigFromAddon> {
    return api.get<MQTTConfigFromAddon>('/ha/export/mqtt/config')
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
   * Alle Sensor-Definitionen abrufen
   */
  async getSensorDefinitions(): Promise<{ count: number; sensors: SensorDefinition[] }> {
    return api.get<{ count: number; sensors: SensorDefinition[] }>('/ha/export/definitions')
  },

  /**
   * MQTT-Verbindung testen
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
