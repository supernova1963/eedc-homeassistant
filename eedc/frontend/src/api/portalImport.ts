/**
 * Portal-Import API Client
 * Importiert Energiedaten aus Hersteller-Portal-Exporten (CSV).
 */

const API_BASE = './api'

export interface ParserInfo {
  id: string
  name: string
  hersteller: string
  beschreibung: string
  erwartetes_format: string
  anleitung: string
  beispiel_header: string
  getestet: boolean
}

export interface ParsedMonth {
  jahr: number
  monat: number
  pv_erzeugung_kwh: number | null
  einspeisung_kwh: number | null
  netzbezug_kwh: number | null
  batterie_ladung_kwh: number | null
  batterie_entladung_kwh: number | null
  eigenverbrauch_kwh: number | null
}

export interface PreviewResult {
  parser: ParserInfo
  monate: ParsedMonth[]
  anzahl_monate: number
}

export interface ApplyResult {
  erfolg: boolean
  importiert: number
  uebersprungen: number
  fehler: string[]
  warnungen: string[]
}

export const portalImportApi = {
  /**
   * Verfügbare Parser abrufen
   */
  async getParsers(): Promise<ParserInfo[]> {
    const response = await fetch(`${API_BASE}/portal-import/parsers`)
    if (!response.ok) throw new Error('Fehler beim Laden der Parser')
    return response.json()
  },

  /**
   * CSV-Datei hochladen und Vorschau erhalten (ohne Speichern)
   */
  async preview(file: File, parserId?: string): Promise<PreviewResult> {
    const formData = new FormData()
    formData.append('file', file)

    const params = new URLSearchParams()
    if (parserId) params.append('parser_id', parserId)

    const response = await fetch(
      `${API_BASE}/portal-import/preview?${params.toString()}`,
      {
        method: 'POST',
        body: formData,
      }
    )

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Vorschau fehlgeschlagen')
    }

    return response.json()
  },

  /**
   * Bestätigte Monatswerte importieren
   */
  async apply(
    anlageId: number,
    monate: ParsedMonth[],
    ueberschreiben: boolean = false
  ): Promise<ApplyResult> {
    const params = new URLSearchParams()
    if (ueberschreiben) params.append('ueberschreiben', 'true')

    const response = await fetch(
      `${API_BASE}/portal-import/apply/${anlageId}?${params.toString()}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ monate }),
      }
    )

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Import fehlgeschlagen')
    }

    return response.json()
  },
}
