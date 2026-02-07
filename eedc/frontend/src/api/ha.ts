/**
 * Home Assistant Integration API Client
 *
 * Zugriff auf HA-Sensoren und String-Monatsdaten.
 */

import { api } from './client'

export interface HASensor {
  entity_id: string
  friendly_name: string | null
  unit_of_measurement: string | null
  device_class: string | null
  state: string | null
}

export interface HAStatus {
  connected: boolean
  rest_api?: boolean
  websocket?: boolean
  ha_version?: string
  message: string
}

export interface StringMonatsdaten {
  id: number
  investition_id: number
  investition_bezeichnung: string
  leistung_kwp: number
  ausrichtung: string | null
  jahr: number
  monat: number
  pv_erzeugung_kwh: number
}

export interface StringMonatsdatenCreate {
  investition_id: number
  jahr: number
  monat: number
  pv_erzeugung_kwh: number
}

export interface HAImportResult {
  erfolg: boolean
  monate_importiert: number
  fehler: string | null
  details: string | null
}

export interface HAImportPreviewMonth {
  monat: number
  existiert_in_db: boolean
  datenquelle: string | null
  pv_erzeugung_db: number | null
  pv_erzeugung_ha: number | null
  kann_importieren: boolean
  kann_aktualisieren: boolean
}

export interface HAImportPreview {
  anlage_id: number
  jahr: number
  ha_verbunden: boolean
  sensor_konfiguriert: boolean
  monate: HAImportPreviewMonth[]
}

export interface MonthlyStatistic {
  jahr: number
  monat: number
  summe_kwh: number
  hat_daten: boolean
}

export interface HAMonthlyDataResponse {
  statistic_id: string
  monate: MonthlyStatistic[]
  hinweis: string | null
}

// =============================================================================
// Discovery Types
// =============================================================================

export interface DiscoveredSensor {
  entity_id: string
  friendly_name: string | null
  unit_of_measurement: string | null
  device_class: string | null
  state_class: string | null
  current_state: string | null
  suggested_mapping: string | null  // pv_erzeugung, einspeisung, etc.
  confidence: number
}

export interface DiscoveredDevice {
  id: string
  integration: string              // sma, evcc, smart, wallbox
  device_type: string              // inverter, ev, wallbox, battery
  suggested_investition_typ: string | null  // e-auto, wallbox, speicher
  name: string
  manufacturer: string | null
  model: string | null
  sensors: DiscoveredSensor[]
  suggested_parameters: Record<string, unknown>
  confidence: number
  priority: number
  already_configured: boolean
}

export interface SensorMappingSuggestions {
  pv_erzeugung: DiscoveredSensor[]
  einspeisung: DiscoveredSensor[]
  netzbezug: DiscoveredSensor[]
  batterie_ladung: DiscoveredSensor[]
  batterie_entladung: DiscoveredSensor[]
}

export interface HASensorMapping {
  pv_erzeugung: string | null
  einspeisung: string | null
  netzbezug: string | null
  batterie_ladung: string | null
  batterie_entladung: string | null
}

export interface DiscoveryResult {
  ha_connected: boolean
  devices: DiscoveredDevice[]
  sensor_mappings: SensorMappingSuggestions
  all_energy_sensors: DiscoveredSensor[]  // Alle Energy-Sensoren für manuelle Auswahl
  warnings: string[]
  current_mappings: HASensorMapping
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
   * String/MPPT-Sensoren abrufen
   */
  async getStringSensors(): Promise<HASensor[]> {
    return api.get<HASensor[]>('/ha/string-sensors')
  },

  /**
   * String-Monatsdaten für eine Anlage abrufen
   */
  async getStringMonatsdaten(anlageId: number, jahr?: number): Promise<StringMonatsdaten[]> {
    const params = jahr ? `?jahr=${jahr}` : ''
    return api.get<StringMonatsdaten[]>(`/ha/string-monatsdaten/${anlageId}${params}`)
  },

  /**
   * String-Monatsdaten erstellen/aktualisieren
   */
  async createStringMonatsdaten(data: StringMonatsdatenCreate): Promise<StringMonatsdaten> {
    return api.post<StringMonatsdaten>('/ha/string-monatsdaten', data)
  },

  /**
   * String-Monatsdaten löschen
   */
  async deleteStringMonatsdaten(id: number): Promise<void> {
    return api.delete(`/ha/string-monatsdaten/${id}`)
  },

  /**
   * Vorschau für HA-Import abrufen
   * Zeigt welche Monate aus HA importiert werden können
   */
  async getImportPreview(anlageId: number, jahr: number): Promise<HAImportPreview> {
    return api.get<HAImportPreview>(`/ha/import/preview/${anlageId}?jahr=${jahr}`)
  },

  /**
   * Monatsdaten aus Home Assistant importieren
   * Existierende manuelle Daten werden nicht überschrieben, es sei denn ueberschreiben=true
   */
  async importMonatsdaten(
    anlageId: number,
    jahr: number,
    monat?: number,
    ueberschreiben = false
  ): Promise<HAImportResult> {
    return api.post<HAImportResult>('/ha/import/monatsdaten', {
      anlage_id: anlageId,
      jahr,
      monat: monat || null,
      ueberschreiben
    })
  },

  /**
   * Monatliche Statistiken für einen Sensor abrufen
   */
  async getMonthlyStatistics(
    statisticId: string,
    startJahr: number,
    startMonat = 1,
    endJahr?: number,
    endMonat?: number
  ): Promise<HAMonthlyDataResponse> {
    return api.post<HAMonthlyDataResponse>('/ha/statistics/monthly', {
      statistic_id: statisticId,
      start_jahr: startJahr,
      start_monat: startMonat,
      end_jahr: endJahr,
      end_monat: endMonat
    })
  },

  /**
   * Auto-Discovery: Durchsucht Home Assistant nach Geräten und Sensoren
   *
   * Erkennt automatisch:
   * - SMA, Fronius, Kostal, Huawei, Growatt, SolaX, Sungrow, GoodWe, Enphase Wechselrichter
   * - evcc Loadpoints (Wallbox) und Vehicles (E-Auto)
   * - Smart E-Auto Integration
   * - Wallbox Integration
   *
   * evcc hat Priorität für E-Auto und Wallbox Daten.
   *
   * @param anlageId - Optional: Anlage-ID für Duplikat-Prüfung
   * @param manufacturer - Optional: Wechselrichter-Hersteller für bessere Filterung
   */
  async discover(anlageId?: number, manufacturer?: string): Promise<DiscoveryResult> {
    const params = new URLSearchParams()
    if (anlageId) params.append('anlage_id', anlageId.toString())
    if (manufacturer) params.append('manufacturer', manufacturer)
    const queryString = params.toString()
    return api.get<DiscoveryResult>(`/ha/discover${queryString ? '?' + queryString : ''}`)
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
