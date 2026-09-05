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
  action_kind?: 'reaggregate_day' | 'reaggregate_range' | 'geraetewerte_loeschen'
    | 'kraftstoffpreis_backfill' | 'feldwert_entfernen'
  action_params?: Record<string, unknown>
  action_label?: string
  // IA-V4 #243: Komponenten-Zuordnung (nur komponenten-bezogene Befunde) —
  // erlaubt dem Komponenten-Hub, Befunde je Gerät zu filtern.
  investition_id?: number
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

export const datenCheckerApi = {
  async check(anlageId: number): Promise<DatenCheckResponse> {
    return api.get<DatenCheckResponse>(`/system/daten-check/${anlageId}`)
  },
}
