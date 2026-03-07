/**
 * Custom-Import API Client
 * Importiert beliebige CSV/JSON-Dateien mit benutzerdefiniertem Feld-Mapping.
 */

const API_BASE = './api'

export interface ColumnInfo {
  name: string
  sample_values: string[]
}

export interface EedcField {
  id: string
  label: string
  required: boolean
  group: string
}

export interface AnalyzeResult {
  dateiname: string
  format: string
  spalten: ColumnInfo[]
  zeilen_gesamt: number
  eedc_felder: EedcField[]
  auto_mapping: Record<string, string>
}

export interface FieldMapping {
  spalte: string
  eedc_feld: string
}

export interface MappingConfig {
  mappings: FieldMapping[]
  einheit: string
  dezimalzeichen: string
  datum_spalte?: string | null
  datum_format?: string | null
}

export interface PreviewMonth {
  jahr: number
  monat: number
  pv_erzeugung_kwh: number | null
  einspeisung_kwh: number | null
  netzbezug_kwh: number | null
  batterie_ladung_kwh: number | null
  batterie_entladung_kwh: number | null
  eigenverbrauch_kwh: number | null
  wallbox_ladung_kwh: number | null
  wallbox_ladung_pv_kwh: number | null
  wallbox_ladevorgaenge: number | null
  eauto_km_gefahren: number | null
}

export interface PreviewResult {
  monate: PreviewMonth[]
  anzahl_monate: number
  warnungen: string[]
}

export interface TemplateInfo {
  name: string
  mapping: MappingConfig
}

export const customImportApi = {
  /**
   * Datei hochladen und Spalten analysieren
   */
  async analyze(file: File): Promise<AnalyzeResult> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch(`${API_BASE}/custom-import/analyze`, {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Analyse fehlgeschlagen')
    }

    return response.json()
  },

  /**
   * Mapping auf Datei anwenden und Vorschau erhalten
   */
  async preview(file: File, mapping: MappingConfig): Promise<PreviewResult> {
    const formData = new FormData()
    formData.append('file', file)

    const params = new URLSearchParams()
    params.append('mapping_json', JSON.stringify(mapping))

    const response = await fetch(
      `${API_BASE}/custom-import/preview?${params.toString()}`,
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
   * Gespeicherte Templates abrufen
   */
  async getTemplates(): Promise<TemplateInfo[]> {
    const response = await fetch(`${API_BASE}/custom-import/templates`)
    if (!response.ok) throw new Error('Fehler beim Laden der Templates')
    const data = await response.json()
    return data.templates
  },

  /**
   * Template speichern
   */
  async saveTemplate(name: string, mapping: MappingConfig): Promise<void> {
    const response = await fetch(
      `${API_BASE}/custom-import/templates/${encodeURIComponent(name)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mapping),
      }
    )
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Speichern fehlgeschlagen')
    }
  },

  /**
   * Template löschen
   */
  async deleteTemplate(name: string): Promise<void> {
    const response = await fetch(
      `${API_BASE}/custom-import/templates/${encodeURIComponent(name)}`,
      { method: 'DELETE' }
    )
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Löschen fehlgeschlagen')
    }
  },
}
