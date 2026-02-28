/**
 * Wetter API Client
 *
 * Ruft Globalstrahlung und Sonnenstunden für Monatsdaten ab.
 *
 * Unterstützte Datenquellen:
 * - Open-Meteo: Weltweit, 16-Tage Prognose
 * - Bright Sky (DWD): Höchste Qualität für Deutschland
 * - Open-Meteo Solar: GTI-Berechnung für PV-Module
 * - PVGIS TMY: Langjährige Durchschnittswerte als Fallback
 */

import { api } from './client'

// =============================================================================
// Types
// =============================================================================

export type WetterProvider = 'auto' | 'open-meteo' | 'brightsky' | 'open-meteo-solar'

export interface StandortInfo {
  latitude: number
  longitude: number
  land?: string
  in_deutschland?: boolean
}

export interface ProviderInfo {
  name: string
  tage_mit_daten?: number
  tage_gesamt?: number
  temperatur_c?: number
  hinweis?: string
}

export interface WetterDaten {
  jahr: number
  monat: number
  globalstrahlung_kwh_m2: number
  sonnenstunden: number
  datenquelle: 'open-meteo' | 'brightsky' | 'pvgis-tmy' | 'defaults'
  standort: StandortInfo
  abdeckung_prozent?: number
  hinweis?: string
  provider_info?: ProviderInfo
  provider_versucht?: string[]
}

export interface WetterProviderOption {
  id: WetterProvider
  name: string
  beschreibung: string
  empfohlen: boolean
  verfuegbar: boolean
  hinweis?: string
}

export interface WetterProviderList {
  standort: StandortInfo
  provider: WetterProviderOption[]
  aktueller_provider: WetterProvider
}

export interface ProviderVergleichDaten {
  verfuegbar: boolean
  globalstrahlung_kwh_m2?: number
  sonnenstunden?: number
  abdeckung_prozent?: number
  temperatur_c?: number
  hinweis?: string
  fehler?: string
}

export interface WetterVergleich {
  jahr: number
  monat: number
  standort: StandortInfo
  provider: Record<string, ProviderVergleichDaten>
  vergleich?: {
    durchschnitt_kwh_m2: number
    abweichung_max_prozent: number
  }
}

// Solar-Prognose Types
export interface SolarPrognoseTag {
  datum: string
  pv_ertrag_kwh: number
  gti_kwh_m2: number
  ghi_kwh_m2: number
  sonnenstunden: number
  temperatur_max_c?: number
  temperatur_min_c?: number
  bewoelkung_prozent?: number
  niederschlag_mm?: number
  schnee_cm?: number
}

export interface StringPrognose {
  name: string
  kwp: number
  neigung: number
  ausrichtung: number
  summe_kwh: number
  durchschnitt_kwh_tag: number
  tageswerte: Array<{
    datum: string
    pv_ertrag_kwh: number
    gti_kwh_m2: number
  }>
}

export interface SolarPrognose {
  anlage_id: number
  anlagenname: string
  kwp_gesamt: number
  neigung: number
  ausrichtung: number
  system_losses_prozent: number
  prognose_zeitraum: {
    von: string | null
    bis: string | null
  }
  summe_kwh: number
  durchschnitt_kwh_tag: number
  tage: SolarPrognoseTag[]  // Alias für tageswerte
  tageswerte: SolarPrognoseTag[]
  string_prognosen?: StringPrognose[] | null
  datenquelle: string
  abgerufen_am: string
  hinweise: string[]
  // Convenience accessor für Anlage-Info
  anlage: {
    id: number
    name: string
    leistung_kwp: number
    neigung: number
    azimut: number
  }
}

// =============================================================================
// API Functions
// =============================================================================

export const wetterApi = {
  /**
   * Holt Wetterdaten für eine Anlage und einen Monat.
   *
   * @param anlageId - ID der Anlage
   * @param jahr - Jahr
   * @param monat - Monat (1-12)
   * @param provider - Datenquelle (optional)
   * @returns WetterDaten mit Globalstrahlung und Sonnenstunden
   */
  async getMonatsdaten(
    anlageId: number,
    jahr: number,
    monat: number,
    provider: WetterProvider = 'auto'
  ): Promise<WetterDaten> {
    return api.get<WetterDaten>(`/wetter/monat/${anlageId}/${jahr}/${monat}?provider=${provider}`)
  },

  /**
   * Holt Wetterdaten für beliebige Koordinaten.
   *
   * @param latitude - Breitengrad
   * @param longitude - Längengrad
   * @param jahr - Jahr
   * @param monat - Monat (1-12)
   * @param provider - Datenquelle (optional)
   * @returns WetterDaten mit Globalstrahlung und Sonnenstunden
   */
  async getMonatsdatenByCoords(
    latitude: number,
    longitude: number,
    jahr: number,
    monat: number,
    provider: WetterProvider = 'auto'
  ): Promise<WetterDaten> {
    return api.get<WetterDaten>(
      `/wetter/monat/koordinaten/${latitude}/${longitude}/${jahr}/${monat}?provider=${provider}`
    )
  },

  /**
   * Gibt verfügbare Wetter-Provider für eine Anlage zurück.
   *
   * @param anlageId - ID der Anlage
   * @returns Liste der verfügbaren Provider
   */
  async getProvider(anlageId: number): Promise<WetterProviderList> {
    return api.get<WetterProviderList>(`/wetter/provider/${anlageId}`)
  },

  /**
   * Vergleicht Wetterdaten verschiedener Provider.
   *
   * @param anlageId - ID der Anlage
   * @param jahr - Jahr
   * @param monat - Monat (1-12)
   * @returns Vergleichsdaten aller Provider
   */
  async getVergleich(anlageId: number, jahr: number, monat: number): Promise<WetterVergleich> {
    return api.get<WetterVergleich>(`/wetter/vergleich/${anlageId}/${jahr}/${monat}`)
  },

  /**
   * Holt Solar-Prognose basierend auf GTI.
   *
   * @param anlageId - ID der Anlage
   * @param tage - Anzahl Tage (1-16)
   * @param proString - Separate Prognose pro String
   * @returns Solar-Prognose mit Tageswerten
   */
  async getSolarPrognose(
    anlageId: number,
    tage: number = 7,
    proString: boolean = false
  ): Promise<SolarPrognose> {
    const result = await api.get<SolarPrognose>(
      `/solar-prognose/${anlageId}?tage=${tage}&pro_string=${proString}`
    )
    // Alias und Convenience-Objekte hinzufügen
    return {
      ...result,
      tage: result.tageswerte,  // Alias für einfachere Verwendung
      anlage: {
        id: result.anlage_id,
        name: result.anlagenname,
        leistung_kwp: result.kwp_gesamt,
        neigung: result.neigung,
        azimut: result.ausrichtung,
      }
    }
  },
}
