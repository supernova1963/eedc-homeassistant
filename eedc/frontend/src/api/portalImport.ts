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

export interface ZuordnungInvestition {
  id: number
  bezeichnung: string
  kwp?: number
  kwh?: number
  default_anteil: number
}

export interface ZuordnungInfo {
  benoetigt_zuordnung: boolean
  pv_module: ZuordnungInvestition[]
  speicher: ZuordnungInvestition[]
  wallboxen: ZuordnungInvestition[]
  eautos: ZuordnungInvestition[]
}

export interface InvestitionsZuordnung {
  pv: Record<number, number>       // {inv_id: anteil_prozent}
  batterie: Record<number, number> // {inv_id: anteil_prozent}
  wallbox_id?: number
  eauto_id?: number
}

export const portalImportApi = {
  async getParsers(): Promise<ParserInfo[]> {
    const response = await fetch(`${API_BASE}/portal-import/parsers`)
    if (!response.ok) throw new Error('Fehler beim Laden der Parser')
    return response.json()
  },

  async preview(file: File, parserId?: string): Promise<PreviewResult> {
    const formData = new FormData()
    formData.append('file', file)
    const params = new URLSearchParams()
    if (parserId) params.append('parser_id', parserId)
    const response = await fetch(
      `${API_BASE}/portal-import/preview?${params.toString()}`,
      { method: 'POST', body: formData }
    )
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Vorschau fehlgeschlagen')
    }
    return response.json()
  },

  async getZuordnungInfo(anlageId: number): Promise<ZuordnungInfo> {
    const response = await fetch(`${API_BASE}/portal-import/zuordnung-info/${anlageId}`)
    if (!response.ok) throw new Error('Fehler beim Laden der Zuordnungs-Info')
    return response.json()
  },

  async apply(
    anlageId: number,
    monate: ParsedMonth[],
    ueberschreiben: boolean = false,
    datenquelle: string = 'portal_import',
    zuordnung?: InvestitionsZuordnung
  ): Promise<ApplyResult> {
    const params = new URLSearchParams()
    if (ueberschreiben) params.append('ueberschreiben', 'true')
    if (datenquelle !== 'portal_import') params.append('datenquelle', datenquelle)
    const response = await fetch(
      `${API_BASE}/portal-import/apply/${anlageId}?${params.toString()}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ monate, zuordnung: zuordnung ?? null }),
      }
    )
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Import fehlgeschlagen')
    }
    return response.json()
  },
}
