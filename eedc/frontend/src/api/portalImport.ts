import { fetchApi } from './fetchApi'
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
  wallbox_ladung_kwh?: number | null
  wallbox_ladung_pv_kwh?: number | null
  wallbox_ladevorgaenge?: number | null
  eauto_km_gefahren?: number | null
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
  /** true = kWp/kWh nicht gepflegt, `default_anteil` ist reine Gleichverteilung. */
  anteil_geschaetzt?: boolean
}

/**
 * Was „Bestehende Monate überschreiben" an Handarbeit ersetzen würde.
 * Gezählt werden BEIDE Ebenen — Zählerzeile und Werte je Gerät.
 */
export interface ManuelleWerteInfo {
  betroffen: boolean
  monate: number
  felder: number
  beispiele: string[]
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
    const response = await fetchApi(`${API_BASE}/portal-import/parsers`)
    if (!response.ok) throw new Error('Fehler beim Laden der Parser')
    return response.json()
  },

  async preview(file: File, parserId?: string): Promise<PreviewResult> {
    const formData = new FormData()
    formData.append('file', file)
    const params = new URLSearchParams()
    if (parserId) params.append('parser_id', parserId)
    const response = await fetchApi(
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
    const response = await fetchApi(`${API_BASE}/portal-import/zuordnung-info/${anlageId}`)
    if (!response.ok) throw new Error('Fehler beim Laden der Zuordnungs-Info')
    return response.json()
  },

  /**
   * Wie viele manuell gepflegte Werte würde „Bestehende Monate überschreiben"
   * ersetzen? Seit 2026-08-12 durchbricht der Haken die Provenance-Hierarchie
   * (vorher meldete der Import hinterher „geschützt" und tat nicht, was
   * angekreuzt war). Damit das eine Anordnung bleibt und keine Überraschung,
   * fragt der Wizard die Zahl VOR dem Import ab.
   *
   * @param perioden Monate als `YYYY-MM`.
   */
  async getManuelleWerte(
    anlageId: number,
    perioden: string[],
  ): Promise<ManuelleWerteInfo> {
    if (perioden.length === 0) {
      return { betroffen: false, monate: 0, felder: 0, beispiele: [] }
    }
    const query = encodeURIComponent(perioden.join(','))
    const response = await fetchApi(
      `${API_BASE}/portal-import/manuelle-werte/${anlageId}?perioden=${query}`,
    )
    if (!response.ok) throw new Error('Fehler beim Prüfen der manuellen Werte')
    return response.json()
  },

  async apply(
    anlageId: number,
    monate: ParsedMonth[],
    ueberschreiben: boolean = false,
    datenquelle: string = 'portal_import',
    zuordnung?: InvestitionsZuordnung,
    /**
     * Gerätegebundene Einfuhr (F-22, #349): ID des Wechselrichters bzw.
     * Balkonkraftwerks, an dem die Quelle hängt. Gesetzt schreibt der Import
     * NUR dessen Erzeuger-Zeilen und lässt die anlagenweiten Hauszähler-Werte
     * unberührt — nötig, sobald zwei Quellen (z. B. zwei Solarman-Stationen)
     * dieselbe Anlage beliefern. `undefined` = bisheriges Verhalten.
     */
    zielInvestitionId?: number | null
  ): Promise<ApplyResult> {
    const params = new URLSearchParams()
    if (ueberschreiben) params.append('ueberschreiben', 'true')
    if (datenquelle !== 'portal_import') params.append('datenquelle', datenquelle)
    const response = await fetchApi(
      `${API_BASE}/portal-import/apply/${anlageId}?${params.toString()}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          monate,
          zuordnung: zuordnung ?? null,
          ziel_investition_id: zielInvestitionId ?? null,
        }),
      }
    )
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Import fehlgeschlagen')
    }
    return response.json()
  },
}
