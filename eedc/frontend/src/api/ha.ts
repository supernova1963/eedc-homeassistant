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
}
