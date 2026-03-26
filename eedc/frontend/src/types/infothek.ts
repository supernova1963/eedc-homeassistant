/**
 * Infothek TypeScript Type Definitions
 */

export interface InfothekEintrag {
  id: number
  anlage_id: number
  bezeichnung: string
  kategorie: string
  notizen?: string | null
  parameter?: Record<string, unknown> | null
  investition_id?: number | null
  ansprechpartner_id?: number | null
  sortierung: number
  aktiv: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface InfothekEintragCreate {
  anlage_id: number
  bezeichnung: string
  kategorie: string
  notizen?: string | null
  parameter?: Record<string, unknown> | null
  investition_id?: number | null
  ansprechpartner_id?: number | null
  sortierung?: number
  aktiv?: boolean
}

export interface InfothekEintragUpdate {
  bezeichnung?: string
  kategorie?: string
  notizen?: string | null
  parameter?: Record<string, unknown> | null
  investition_id?: number | null
  ansprechpartner_id?: number | null
  sortierung?: number
  aktiv?: boolean
}

export interface KategorieFeld {
  type: 'string' | 'number' | 'date' | 'select'
  label: string
  options?: string[]
}

export interface KategorieSchema {
  label: string
  icon: string
  felder: Record<string, KategorieFeld>
}

export interface UebergreifendeSektion {
  label: string
  felder: Record<string, KategorieFeld>
}

export interface KategorienResponse {
  kategorien: Record<string, KategorieSchema>
  uebergreifende_felder: Record<string, UebergreifendeSektion>
}

export interface InfothekDatei {
  id: number
  eintrag_id: number
  dateiname: string
  dateityp: 'image' | 'pdf'
  mime_type: string
  beschreibung?: string | null
  created_at?: string | null
}
