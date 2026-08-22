/**
 * Import/Export API Client
 * Verwendet relative Pfade für HA Ingress Kompatibilität.
 */

import type { ImportResult, JSONImportResult } from '../types'
import { fetchApi } from './fetchApi'

// Relative Basis-URL für HA Ingress Support
const API_BASE = './api'

export interface CSVTemplateInfo {
  spalten: string[]
  beschreibung: Record<string, string>
}

export interface DemoDataResult {
  erfolg: boolean
  anlage_id: number
  anlage_name: string
  monatsdaten_count: number
  investitionen_count: number
  strompreise_count: number
  message: string
}

export const importApi = {
  /**
   * CSV Template Info abrufen
   */
  async getTemplateInfo(anlageId: number): Promise<CSVTemplateInfo> {
    const response = await fetchApi(`${API_BASE}/import/template/${anlageId}`)
    if (!response.ok) throw new Error('Fehler beim Laden des Templates')
    return response.json()
  },

  /**
   * CSV Template herunterladen
   */
  getTemplateDownloadUrl(anlageId: number): string {
    return `${API_BASE}/import/template/${anlageId}/download`
  },

  /**
   * CSV-Datei importieren
   */
  async importCSV(anlageId: number, file: File, ueberschreiben: boolean = false): Promise<ImportResult> {
    const formData = new FormData()
    formData.append('file', file)

    const params = new URLSearchParams()
    if (ueberschreiben) params.append('ueberschreiben', 'true')

    const response = await fetchApi(
      `${API_BASE}/import/csv/${anlageId}?${params.toString()}`,
      {
        method: 'POST',
        body: formData,
      }
    )

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Import fehlgeschlagen')
    }

    return response.json()
  },

  /**
   * Daten als CSV exportieren
   */
  getExportUrl(anlageId: number, jahr?: number): string {
    const params = new URLSearchParams()
    if (jahr) params.append('jahr', jahr.toString())
    const query = params.toString()
    return `${API_BASE}/import/export/${anlageId}${query ? '?' + query : ''}`
  },

  /**
   * Demo-Daten erstellen
   * Erstellt eine komplette Demo-Anlage mit Investitionen, Strompreisen und Monatsdaten
   */
  async createDemoData(): Promise<DemoDataResult> {
    const response = await fetchApi(`${API_BASE}/import/demo`, {
      method: 'POST',
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Demo-Daten konnten nicht erstellt werden')
    }

    return response.json()
  },

  /**
   * Demo-Daten löschen
   */
  async deleteDemoData(): Promise<{ message: string }> {
    const response = await fetchApi(`${API_BASE}/import/demo`, {
      method: 'DELETE',
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Demo-Daten konnten nicht gelöscht werden')
    }

    return response.json()
  },

  /**
   * Vollständigen JSON-Export einer Anlage herunterladen
   */
  getFullExportUrl(anlageId: number): string {
    return `${API_BASE}/import/export/${anlageId}/full`
  },

  /**
   * JSON-Datei importieren (erstellt neue Anlage)
   */
  async importJSON(file: File, ueberschreiben: boolean = false): Promise<JSONImportResult> {
    const formData = new FormData()
    formData.append('file', file)

    const params = new URLSearchParams()
    if (ueberschreiben) params.append('ueberschreiben', 'true')

    const response = await fetchApi(
      `${API_BASE}/import/json?${params.toString()}`,
      {
        method: 'POST',
        body: formData,
      }
    )

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'JSON-Import fehlgeschlagen')
    }

    return response.json()
  },

  /**
   * PDF-Bericht URL generieren
   * Vollstaendiger Bericht mit Stammdaten, KPIs, Diagrammen, Monatswerten
   *
   * @param anlageId - ID der Anlage
   * @param jahr - Jahr fuer Jahresbericht, oder undefined/null fuer Gesamtzeitraum
   */
  getPdfExportUrl(anlageId: number, jahr?: number | null): string {
    if (jahr) {
      return `${API_BASE}/import/pdf/${anlageId}?jahr=${jahr}`
    }
    // Ohne Jahr-Parameter: Gesamtzeitraum
    return `${API_BASE}/import/pdf/${anlageId}`
  },

  /**
   * ZIP-URL fuer mehrere Berichte (#121-Rest).
   *
   * @param berichte - Bericht-Keys (jahresbericht, infothek, anlagendokumentation, finanzbericht)
   * @param jahr - Jahr fuer den Jahresbericht, oder undefined/null fuer Gesamtzeitraum
   */
  getPdfZipExportUrl(anlageId: number, berichte: string[], jahr?: number | null): string {
    const params = new URLSearchParams()
    berichte.forEach(b => params.append('berichte', b))
    if (jahr) params.append('jahr', String(jahr))
    return `${API_BASE}/import/pdf-zip/${anlageId}?${params.toString()}`
  },
}
