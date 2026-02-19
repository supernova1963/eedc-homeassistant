/**
 * HA Statistics API Client
 *
 * Ermöglicht den Zugriff auf Home Assistant Langzeitstatistiken
 * für historischen Datenimport.
 */

import { api } from './client'

// =============================================================================
// Types
// =============================================================================

export interface HAStatisticsStatus {
  verfuegbar: boolean
  pfad?: string
  fehler?: string
}

export interface FeldWert {
  feld: string
  label: string
  wert: number | null
  einheit: string
  sensor_id?: string
}

// Backend Response Format für MappedMonatswert
interface BackendMappedFeld {
  feld: string
  feld_label: string
  sensor_id: string
  start_wert: number
  end_wert: number
  differenz: number
  einheit: string
}

// Backend Response Format für InvestitionMitFelder
interface BackendInvestitionMitFelder {
  investition_id: number
  bezeichnung: string
  typ: string
  felder: BackendMappedFeld[]
}

// Backend Response Format für AnlagenMonatswertResponse
interface BackendMonatswerte {
  anlage_id: number
  anlage_name: string
  jahr: number
  monat: number
  monat_name: string
  basis: BackendMappedFeld[]
  investitionen: BackendInvestitionMitFelder[]  // Liste von Investitionen mit Feldern
}

export interface InvestitionWerte {
  investition_id: number
  bezeichnung: string
  typ: string
  felder: FeldWert[]
}

export interface Monatswerte {
  jahr: number
  monat: number
  monat_name: string
  basis: FeldWert[]
  investitionen: InvestitionWerte[]
}

/**
 * Konvertiert Backend-Format zu Frontend-Format
 */
function convertBackendToMonatswerte(backend: BackendMonatswerte): Monatswerte {
  return {
    jahr: backend.jahr,
    monat: backend.monat,
    monat_name: backend.monat_name,
    basis: backend.basis.map(b => ({
      feld: b.feld,
      label: b.feld_label,
      wert: b.differenz,
      einheit: b.einheit,
      sensor_id: b.sensor_id
    })),
    investitionen: backend.investitionen.map(inv => ({
      investition_id: inv.investition_id,
      bezeichnung: inv.bezeichnung,
      typ: inv.typ,
      felder: inv.felder.map(f => ({
        feld: f.feld,
        label: f.feld_label,
        wert: f.differenz,
        einheit: f.einheit,
        sensor_id: f.sensor_id
      }))
    }))
  }
}

export interface VerfuegbarerMonat {
  jahr: number
  monat: number
  monat_name: string
  hat_daten?: boolean  // Optional, nicht immer vom Backend geliefert
}

export interface VerfuegbareMonateResponse {
  anlage_id: number
  anlage_name: string
  erstes_datum: string
  letztes_datum: string
  anzahl_monate: number
  monate: VerfuegbarerMonat[]
}

export interface AlleMonatswerte {
  anlage_id: number
  anlage_name: string
  monate: Monatswerte[]
  sensor_count: number
  zeitraum?: {
    von: string
    bis: string
  }
}

export interface MonatsanfangWerte {
  anlage_id: number
  anlage_name: string
  jahr: number
  monat: number
  startwerte: Record<string, number>
}

export type ImportAktion = 'importieren' | 'ueberspringen' | 'ueberschreiben' | 'konflikt'

export interface InvestitionImportStatus {
  investition_id: number
  bezeichnung: string
  typ: string
  ha_werte: Record<string, number | null>
  vorhandene_werte: Record<string, number | null>
  hat_abweichung: boolean
}

export interface MonatImportStatus {
  jahr: number
  monat: number
  monat_name: string
  aktion: ImportAktion
  grund: string
  ha_werte: Record<string, number | null>
  vorhandene_werte?: Record<string, number | null>
  investitionen?: InvestitionImportStatus[]
}

export interface ImportVorschau {
  anlage_id: number
  anlage_name: string
  anzahl_monate: number
  anzahl_importieren: number
  anzahl_konflikte: number
  anzahl_ueberspringen: number
  monate: MonatImportStatus[]
}

export interface MonatFeldAuswahl {
  jahr: number
  monat: number
  // Basis-Felder: Liste der Feld-Namen die importiert werden sollen
  // null/undefined = alle, [] = keine
  basis_felder?: string[] | null
  // Investitions-Felder: Dict von inv_id -> Liste der Feld-Namen
  // null/undefined = alle, {} = keine
  investition_felder?: Record<string, string[]> | null
}

export interface ImportRequest {
  monate: MonatFeldAuswahl[]
  ueberschreiben: boolean
}

export interface ImportResult {
  erfolg: boolean
  importiert: number
  uebersprungen: number
  ueberschrieben: number
  fehler: string[]
}

// =============================================================================
// API Client
// =============================================================================

export const haStatisticsApi = {
  /**
   * Prüft ob HA-Datenbank verfügbar ist
   */
  async getStatus(): Promise<HAStatisticsStatus> {
    return api.get<HAStatisticsStatus>('/ha-statistics/status')
  },

  /**
   * Monatswerte für einen einzelnen Monat abrufen
   */
  async getMonatswerte(
    anlageId: number,
    jahr: number,
    monat: number
  ): Promise<Monatswerte> {
    const backend = await api.get<BackendMonatswerte>(`/ha-statistics/monatswerte/${anlageId}/${jahr}/${monat}`)
    return convertBackendToMonatswerte(backend)
  },

  /**
   * Alle verfügbaren Monate mit Daten abrufen
   */
  async getVerfuegbareMonate(anlageId: number): Promise<VerfuegbarerMonat[]> {
    const response = await api.get<VerfuegbareMonateResponse>(`/ha-statistics/verfuegbare-monate/${anlageId}`)
    // Backend gibt Wrapper-Objekt zurück, wir extrahieren nur die monate-Liste
    return response.monate.map(m => ({
      ...m,
      hat_daten: true  // Alle zurückgegebenen Monate haben Daten
    }))
  },

  /**
   * Alle Monatswerte (Bulk-Abfrage)
   */
  async getAlleMonatswerte(anlageId: number): Promise<AlleMonatswerte> {
    return api.get<AlleMonatswerte>(`/ha-statistics/alle-monatswerte/${anlageId}`)
  },

  /**
   * Zählerstände am Monatsanfang (für MQTT Startwerte)
   */
  async getMonatsanfangWerte(
    anlageId: number,
    jahr: number,
    monat: number
  ): Promise<MonatsanfangWerte> {
    return api.get<MonatsanfangWerte>(`/ha-statistics/monatsanfang/${anlageId}/${jahr}/${monat}`)
  },

  /**
   * Import-Vorschau mit Konflikt-Erkennung
   */
  async getImportVorschau(anlageId: number): Promise<ImportVorschau> {
    return api.get<ImportVorschau>(`/ha-statistics/import-vorschau/${anlageId}`)
  },

  /**
   * Import durchführen mit Überschreib-Schutz
   */
  async importieren(anlageId: number, request: ImportRequest): Promise<ImportResult> {
    return api.post<ImportResult>(`/ha-statistics/import/${anlageId}`, request)
  },
}
