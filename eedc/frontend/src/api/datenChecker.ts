/**
 * Daten-Checker API Client
 *
 * Endpoint für Datenqualitäts-Prüfung.
 */

import { api } from './client'

export interface CheckErgebnis {
  kategorie: string
  schwere: 'error' | 'warning' | 'info' | 'ok'
  meldung: string
  details?: string
  // IA-V4 #243: Komponenten-Zuordnung (nur komponenten-bezogene Befunde) —
  // erlaubt dem Komponenten-Hub, Befunde je Gerät zu filtern.
  investition_id?: number
  // E1 «Diagnose-Paket»: die Zahlen der Meldung strukturiert und der Befund-Schlüssel (an den Melder-Erzeugern).
  werte?: Record<string, unknown> | null
  code?: string | null
  // E2/E3: der eine Handgriff — Sprung-Ziel (Pfad über `lib/zielPfad.ts`) oder Aktion (Plan/Ausführen). Seit E5 ohne
  // die Altfelder `link`/`action_*` (Wächter W-3).
  ziel?: CheckZiel | null
  action?: CheckAktion | null
  /** E5.7 L1: der Knopf-Text aller drei Klassen aus dem Katalog (Aktion · Sprung · «Was gilt»); OK ⇒ null. */
  knopf?: string | null
  /** E5 V2: Gruppenzeile — Befunde mit gleichem `schluessel` stehen als eine Zeile mit Gliedern. */
  gruppe?: CheckGruppe | null
}

/** Gruppenzeile eines Befunds (Backend `services/daten_checker/gruppen.py`). */
export interface CheckGruppe {
  schluessel: string
  titel: string
  glied: string
  weitere: number
  details?: string | null
}

/** E5 V4: eine Prüfung, die in dieser Installation nicht laufen kann (kein Home Assistant, MQTT-Import aus). */
export interface NichtAusfuehrbar {
  pruefung: string
  grund: string
}

/** Sprung-Ziel eines Befunds (Bereich der Einstellungen, Block, Deep-Link-Parameter, Anker). */
export interface CheckZiel {
  bereich: string
  block?: string | null
  params: Record<string, unknown>
  anker?: string | null
}

/** Inline-Handgriff eines Befunds (Operation, Parameter, Knopf-Beschriftung). */
export interface CheckAktion {
  operation: 'reaggregate_day' | 'reaggregate_range' | 'kraftstoffpreis_backfill' | 'wetter_backfill'
    | 'feldwert_entfernen' | 'temperatur_aus_messung' | 'spiegel_abgleich_tag' | string
  params: Record<string, unknown>
  label: string
}

export interface MonatsdatenAbdeckung {
  vorhanden: number
  erwartet: number
  prozent: number
}

export interface DatenCheckResponse {
  anlage_id: number
  anlage_name: string
  ergebnisse: CheckErgebnis[]
  zusammenfassung: {
    error: number
    warning: number
    info: number
    ok: number
  }
  monatsdaten_abdeckung?: MonatsdatenAbdeckung
  nicht_ausfuehrbar?: NichtAusfuehrbar[]
}

/** E1: Fassung des Diagnose-Pakets — `datei` ungekürzt, `kopie` höchstens 20 KB (Kürzung steht im Kopf). */
export type DiagnosePaketFassung = 'datei' | 'kopie'

export interface DiagnosePaket {
  text: string
  dateiname: string
}

/** Adresse des Diagnose-Pakets (relativ wie `api/client.ts`, damit Ingress greift). */
export function diagnosePaketUrl(anlageId: number, fassung: DiagnosePaketFassung, monate?: string[]): string {
  const q = new URLSearchParams({ fassung })
  if (monate && monate.length > 0) q.set('monate', monate.join(','))
  return `./api/system/diagnose-paket/${anlageId}?${q.toString()}`
}

export const datenCheckerApi = {
  async check(anlageId: number): Promise<DatenCheckResponse> {
    return api.get<DatenCheckResponse>(`/system/daten-check/${anlageId}`)
  },

  /** Das Diagnose-Paket als Text (Markdown) samt Dateiname aus dem Anhang-Kopf. */
  async diagnosePaket(anlageId: number, fassung: DiagnosePaketFassung, monate?: string[]): Promise<DiagnosePaket> {
    const res = await fetch(diagnosePaketUrl(anlageId, fassung, monate))
    if (!res.ok) {
      const detail = await res.json().catch(() => null)
      throw new Error(detail?.detail || `HTTP ${res.status}`)
    }
    const kopf = res.headers.get('content-disposition') ?? ''
    const name = /filename="([^"]+)"/.exec(kopf)?.[1] ?? `eedc_diagnose_${anlageId}.md`
    return { text: await res.text(), dateiname: name }
  },
}
