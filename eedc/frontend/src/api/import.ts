/**
 * Import/Export API Client
 */

import type { ImportResult } from '../types'

const API_BASE = '/api'

export interface CSVTemplateInfo {
  spalten: string[]
  beschreibung: Record<string, string>
}

export const importApi = {
  /**
   * CSV Template Info abrufen
   */
  async getTemplateInfo(anlageId: number): Promise<CSVTemplateInfo> {
    const response = await fetch(`${API_BASE}/import/template/${anlageId}`)
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

    const response = await fetch(
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
}
