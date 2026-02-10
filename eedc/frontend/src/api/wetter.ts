/**
 * Wetter API Client
 *
 * Ruft Globalstrahlung und Sonnenstunden für Monatsdaten ab.
 * Nutzt Open-Meteo für historische und PVGIS TMY für aktuelle/zukünftige Daten.
 */

import { api } from './client'

// =============================================================================
// Types
// =============================================================================

export interface StandortInfo {
  latitude: number
  longitude: number
}

export interface WetterDaten {
  jahr: number
  monat: number
  globalstrahlung_kwh_m2: number
  sonnenstunden: number
  datenquelle: 'open-meteo' | 'pvgis-tmy' | 'defaults'
  standort: StandortInfo
  abdeckung_prozent?: number
  hinweis?: string
}

// =============================================================================
// API Functions
// =============================================================================

export const wetterApi = {
  /**
   * Holt Wetterdaten für eine Anlage und einen Monat.
   *
   * Verwendet die Koordinaten der Anlage.
   *
   * @param anlageId - ID der Anlage
   * @param jahr - Jahr
   * @param monat - Monat (1-12)
   * @returns WetterDaten mit Globalstrahlung und Sonnenstunden
   */
  async getMonatsdaten(anlageId: number, jahr: number, monat: number): Promise<WetterDaten> {
    return api.get<WetterDaten>(`/wetter/monat/${anlageId}/${jahr}/${monat}`)
  },

  /**
   * Holt Wetterdaten für beliebige Koordinaten.
   *
   * Nützlich für Standort-Prüfung ohne Anlage.
   *
   * @param latitude - Breitengrad
   * @param longitude - Längengrad
   * @param jahr - Jahr
   * @param monat - Monat (1-12)
   * @returns WetterDaten mit Globalstrahlung und Sonnenstunden
   */
  async getMonatsdatenByCoords(
    latitude: number,
    longitude: number,
    jahr: number,
    monat: number
  ): Promise<WetterDaten> {
    return api.get<WetterDaten>(`/wetter/monat/koordinaten/${latitude}/${longitude}/${jahr}/${monat}`)
  },
}
