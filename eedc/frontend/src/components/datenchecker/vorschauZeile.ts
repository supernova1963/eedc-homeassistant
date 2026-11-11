/**
 * Daten-Checker — die eine Vorschau-Zeile und der Ergebnis-Satz einer Aktion (Etappe E3, Konzept §5).
 *
 * Reines Modul (ohne React), damit Texte und Entscheidungen ohne Mount prüfbar bleiben. **Der Client rechnet nichts**
 * (`check:rechenstellen`): die Zeile setzt die Zähler des Plans (`estimated_changes`) mit ihren Beschriftungen
 * (`REPARATUR_AENDERUNG_LABELS`) zusammen, hängt die Monate der Vorschau an und — wo es gilt — die Vorbedingung
 * (Spiegel-Abgleich, Gegenprüfung Ü8) bzw. «endgültig» (Lösch-Operationen). Wächter W-4
 * (`backend/tests/test_daten_checker_texte.py`): keine Mechanik-Wörter, keine Menüweg-Pfeile in diesen Satzteilen.
 * Die Werkbank-Warnungen (`plan.warnings`) zeigt der Kasten unverändert darunter.
 */
import type { RepairPlan, RepairResult } from '../../api/repair'
import { REPARATUR_AENDERUNG_LABELS } from '../../lib/constants'
import { fmtZahl } from '../../lib'
import { baueFeldwertMeldung, baueSpiegelAbgleichMeldung, type ReparaturMeldung, type SpiegelAbgleichTagErgebnis } from '../../pages/datenCheckerMeldungen'

/** Vorbedingung von «Aus Home Assistant neu übernehmen» (Ü8): der Knopf übernimmt, was Home Assistant hat. */
export const VORBEDINGUNG_HA = 'wirksam, wenn du in Home Assistant korrigiert hast'
export const ENDGUELTIG = 'endgültig'

export interface VorschauAussage {
  /** Die eine Zeile in Anwender-Sprache (bei «nichts zu tun» der Satz des Plans). */
  satz: string
  nichtsZuTun: boolean
  endgueltig: boolean
  vorbedingung: boolean
  /** «gültig bis HH:MM» (Plan-TTL). */
  gueltigBis: string
}

function uhrzeit(iso: string): string {
  return new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
}

export function vorschauAussage(plan: RepairPlan): VorschauAussage {
  const vorschau = plan.operation_preview ?? {}
  const gueltigBis = uhrzeit(plan.expires_at)
  const nichts = vorschau.nichts_zu_tun
  if (typeof nichts === 'string' && nichts) {
    return { satz: nichts, nichtsZuTun: true, endgueltig: false, vorbedingung: false, gueltigBis }
  }
  const teile = Object.entries(plan.estimated_changes)
    .map(([k, v]) => `${REPARATUR_AENDERUNG_LABELS[k] ?? k}: ${fmtZahl(v, 0)}`)
  const monate = Array.isArray(vorschau.monate) ? (vorschau.monate as unknown[]).map(String) : []
  let satz = teile.join(' · ') || 'Keine Änderung angekündigt'
  if (monate.length > 0) satz += ` (${monate.join(', ')})`
  const vorbedingung = plan.operation === 'spiegel_abgleich_tag'
  const endgueltig = vorschau.endgueltig === true
  if (vorbedingung) satz += ` — ${VORBEDINGUNG_HA}`
  if (endgueltig) satz += ` — ${ENDGUELTIG}`
  return { satz, nichtsZuTun: false, endgueltig, vorbedingung, gueltigBis }
}

/** Ergebnis-Satz nach «Anwenden» (Muster `summarizeResult` der Werkbank, je Operation in Anwender-Sprache). */
export function ergebnisMeldung(result: RepairResult, knopf: string): ReparaturMeldung {
  const s = result.operation_summary ?? {}
  switch (result.operation) {
    case 'spiegel_abgleich_tag':
      return baueSpiegelAbgleichMeldung(s as unknown as SpiegelAbgleichTagErgebnis)
    case 'feldwert_entfernen':
      return baueFeldwertMeldung(String(s.feld ?? ''), s as unknown as Parameters<typeof baueFeldwertMeldung>[1])
    case 'temperatur_aus_messung': {
      const gefuellt = Number(s.gefuellt ?? 0)
      const offen = Number(s.offen ?? 0)
      if (gefuellt <= 0) {
        return { art: 'hinweis', text: 'Es war nichts nachzutragen — für die offenen Monate reicht die Messreihe nicht zurück.' }
      }
      return {
        art: 'ok',
        text: `${gefuellt} Monat(e) haben jetzt eine Ø Temperatur aus deinen eigenen Messwerten.`
          + (offen > 0 ? ` Für ${offen} weitere reicht die Messreihe nicht zurück — dort hilft „Auto-Fill“ unter „Wetterdaten (optional)“ im Monat selbst.` : ''),
      }
    }
    case 'kraftstoffpreis_backfill': {
      const n = Number(s.monats_aktualisiert ?? 0)
      if (n > 0) return { art: 'ok', text: `${n} Monat(e) haben jetzt einen Ø-Benzinpreis (Quelle: EU Weekly Oil Bulletin, ${String(s.land ?? '')}).` }
      return { art: 'hinweis', text: s.monats_fehler ? `Es konnten keine Preise geladen werden: ${String(s.monats_fehler)}` : 'Es war nichts nachzutragen.' }
    }
    default: {
      const quelle = typeof s.quelle_text === 'string' && s.quelle_text ? ` ${s.quelle_text}` : ''
      return { art: 'ok', text: `${knopf}: ausgeführt.${quelle}` }
    }
  }
}
