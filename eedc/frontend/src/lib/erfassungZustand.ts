/**
 * Ableitungslogik der Erfassungs-Zustände (Monatsabschluss-V4, §4).
 *
 * Reine Funktionen — bilden einen Feld-`FeldStatus` (Backend) + den aktuellen
 * Eingabewert auf einen der vier Zustände `gemessen/geschaetzt/fehlt/weicht_ab`
 * ab (SoT-Vokabular in `lib/colors.ts` / `ErfassungZustandBadge`).
 *
 * Quellen-Klassierung (exakte Strings aus VorschlagQuelle + Monatsdaten.datenquelle):
 * - GEMESSEN: Sensor/Import/Connector-Quellen. `manuell`/`manual` zählen bewusst
 *   ebenfalls als „gemessen" (Gernot 2026-07-12) — ein selbst eingetragener Wert
 *   ist die vertrauenswürdigste Quelle und wird nie automatisch überschrieben (P3b).
 * - GESCHÄTZT: Historie/Berechnung (vormonat/vorjahr/durchschnitt/berechnung/parameter).
 *   Erscheint NUR als Prefill — gespeicherte Werte sind nie „geschätzt".
 */

import type { FeldStatus, Vorschlag } from '../api/monatsabschluss'
import type { ErfassungZustand } from '../components/ui/ErfassungZustandBadge'

/** Quellen, die einen GEMESSENEN Wert markieren (Sensor/Import/Connector). */
export const GEMESSENE_QUELLEN: ReadonlySet<string> = new Set([
  'ha_sensor', 'ha_statistics', 'snapshot', 'cron_snapshot', 'local_connector',
  'mqtt_inbound', 'portal_import', 'cloud_import', 'ha_import', 'csv',
])

/** „Von Hand" — zählt visuell als gemessen (Gernot 2026-07-12). */
export const MANUELLE_QUELLEN: ReadonlySet<string> = new Set(['manuell', 'manual'])

/** Quellen, die einen GESCHÄTZTEN (nicht gemessenen) Wert markieren. */
export const GESCHAETZTE_QUELLEN: ReadonlySet<string> = new Set([
  'vormonat', 'vorjahr', 'berechnung', 'berechnet', 'durchschnitt', 'parameter',
])

export function istGemesseneQuelle(quelle: string | null | undefined): boolean {
  if (!quelle) return false
  return GEMESSENE_QUELLEN.has(quelle) || MANUELLE_QUELLEN.has(quelle)
}

/** Bester Vorschlag = höchste Konfidenz (gemessene Quellen liegen konstruktiv vorn). */
export function besterVorschlag(vorschlaege: Vorschlag[] | undefined): Vorschlag | null {
  if (!vorschlaege || vorschlaege.length === 0) return null
  return vorschlaege.reduce((best, v) => (v.konfidenz > best.konfidenz ? v : best), vorschlaege[0])
}

const EPS = 0.005
/** Zwei gerundete Messwerte gelten als gleich (Werte sind auf ≤2 Nachkommastellen gerundet). */
export const gleich = (a: number, b: number): boolean => Math.abs(a - b) < EPS

export interface ZustandErgebnis {
  zustand: ErfassungZustand
  /** Roh-Quelle des aktuellen Werts/Prefills (für Badge-Label via getQuelleLabel). */
  quelle?: string | null
  /** Nur bei 'weicht_ab': gemessener Sensor-Vorschlag ≠ gespeicherter Wert. */
  weichtAb?: { sensorWert: number; gespeichert: number }
}

/**
 * Leitet den Erfassungs-Zustand eines Feldes ab (§4.1).
 *
 * @param formWert aktueller Eingabewert als String ('' = leer)
 * @param feld     Backend-FeldStatus (gespeicherter Wert, Quelle, Vorschläge) —
 *                 `undefined` für Client-Only-Felder (dann nur leer/manuell möglich)
 */
export function ermittleZustand(formWert: string, feld: FeldStatus | undefined): ZustandErgebnis {
  const best = besterVorschlag(feld?.vorschlaege)
  const gespeichert = feld?.aktueller_wert ?? null
  const hatForm = formWert.trim() !== ''
  const formNum = hatForm ? parseFloat(formWert) : NaN

  // „Weicht ab": es gibt einen gespeicherten Wert UND einen gemessenen Vorschlag,
  // der abweicht, und der Eingabewert entspricht noch dem gespeicherten (der
  // Nutzer hat also noch nicht bewusst entschieden). Nur beim Bearbeiten (R2).
  if (
    gespeichert != null && best && istGemesseneQuelle(best.quelle) &&
    !gleich(best.wert, gespeichert) &&
    hatForm && !Number.isNaN(formNum) && gleich(formNum, gespeichert)
  ) {
    return { zustand: 'weicht_ab', quelle: best.quelle, weichtAb: { sensorWert: best.wert, gespeichert } }
  }

  if (!hatForm || Number.isNaN(formNum)) {
    return { zustand: 'fehlt' }
  }

  // Entspricht dem gespeicherten Wert → dessen Quelle. Gespeicherte Werte sind
  // nie „geschätzt" (Schätzung existiert nur als Prefill) → immer 'gemessen'.
  if (gespeichert != null && gleich(formNum, gespeichert)) {
    return { zustand: 'gemessen', quelle: feld?.quelle ?? 'manuell' }
  }

  // Entspricht dem besten Vorschlag → Prefill; dessen Quelle bestimmt den Zustand.
  if (best && gleich(formNum, best.wert)) {
    return istGemesseneQuelle(best.quelle)
      ? { zustand: 'gemessen', quelle: best.quelle }
      : { zustand: 'geschaetzt', quelle: best.quelle }
  }

  // Sonst: vom Nutzer eingetippt (≠ gespeichert, ≠ Vorschlag) → manuell → gemessen.
  return { zustand: 'gemessen', quelle: 'manuell' }
}

/** Prefill-Wert für ein leeres Feld (R1/R2 „Lücken füllen"): bester Vorschlag. */
export function prefillWert(feld: FeldStatus | undefined): number | null {
  const best = besterVorschlag(feld?.vorschlaege)
  return best ? best.wert : null
}
