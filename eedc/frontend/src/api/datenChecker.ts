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
  link?: string
  // Etappe 6 v3.31.1: optionale Inline-Reparatur-Action.
  // v3.45.9: 'reaggregate_range' für Bulk-Reparatur (Batterie-Vorzeichen-Historie).
  // #349: 'geraetewerte_loeschen' — Messwerte eines Monats ohne Zählerzeile.
  // Die einzige Aktion dieser Liste, die etwas **entfernt**; sie steht hier,
  // weil es für diesen Rest sonst keinen Weg gibt (die Zeile, über die man ihn
  // sonst aufräumt, ist ja gerade die gelöschte).
  // #394: 'kraftstoffpreis_backfill' — Ø-Benzinpreise aus dem EU Oil Bulletin
  // für Monatszeilen ohne Preis. Additiv: schreibt nur, wo NULL steht.
  // N-393: 'feldwert_entfernen' — ein gespeicherter Wert in einem Feld, das
  // das Gerät nach seinen Einstellungen nicht (mehr) führt. Der Monatsabschluss
  // zeigt das Feld nicht, ein erneuter Abschluss lässt den Wert stehen — der
  // einzige Weg an ihn heran ist dieser Knopf. Zweite Aktion, die entfernt.
  // N-426-Nachtrag: 'temperatur_aus_messung' — die Ø-Temperatur der Monate,
  // die zwischen dem V4-Flip und WK-03 ohne Auto-Fill abgeschlossen wurden,
  // aus der eigenen Messreihe nachtragen. Additiv wie der Benzinpreis-Backfill:
  // schreibt nur, wo NULL steht, und nur so weit die Reihe zurückreicht.
  // N-790: 'spiegel_abgleich_tag' — «Aus Home Assistant neu übernehmen» an
  // Drift-, Zählersprung- und Rückgang-Befunden einer Anlage mit HA-Spiegel:
  // erst der Abgleich mit der HA-Statistik, dann der Tag neu aufgebaut.
  action_kind?: 'reaggregate_day' | 'reaggregate_range' | 'geraetewerte_loeschen'
    | 'kraftstoffpreis_backfill' | 'feldwert_entfernen' | 'temperatur_aus_messung'
    | 'spiegel_abgleich_tag'
  action_params?: Record<string, unknown>
  action_label?: string
  // IA-V4 #243: Komponenten-Zuordnung (nur komponenten-bezogene Befunde) —
  // erlaubt dem Komponenten-Hub, Befunde je Gerät zu filtern.
  investition_id?: number
  // E1 «Diagnose-Paket»: die Zahlen der Meldung strukturiert und der Befund-Schlüssel (an den Melder-Erzeugern).
  werte?: Record<string, unknown> | null
  code?: string | null
  // E2 «Befund-Schlüssel, Ziel-Bauer»: Sprung-Ziel und Aktion zusätzlich (Backend `ziele.py`). Der Client liest bis E3/E4
  // weiter `link`/`action_*` — beide sind daraus abgeleitet und unverändert.
  ziel?: CheckZiel | null
  action?: CheckAktion | null
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
  operation: string
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
