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
export type { ErfassungZustand } from '../components/ui/ErfassungZustandBadge'

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

// ─── Toleranz (PN 90128) ────────────────────────────────────────────────────
//
// Ein Vorschlag wird nur so genau genommen, wie er geliefert wird: das Backend
// rundet den HA-Statistics-/Connector-Vorschlag auf EINE Nachkommastelle
// (`round(wert, 1)`), der gespeicherte Wert trägt dagegen zwei. Gegen eine feste
// Schwelle verglichen weicht der Vorschlag damit systematisch ab (2,3 ↔ 2,33 =
// 0,03) — genau die Meldung „fast überall wird die 2. Nachkommastelle
// angemeckert". Deshalb bestimmt die Genauigkeit des VORSCHLAGS die Toleranz.

/** Gröbste berücksichtigte Genauigkeit. Vorschläge werden im Backend auf ≥1
 *  Nachkommastelle gerundet — ein glatter Wert wie 2,0 heißt also NICHT
 *  „ganzzahlig genau", sonst würde eine Toleranz von 0,5 entstehen. */
export const MIN_NACHKOMMASTELLEN = 1
/** Feinste berücksichtigte Genauigkeit (Entscheid Gernot: höchstens drei). */
export const MAX_NACHKOMMASTELLEN = 3

/** Nachkommastellen, auf die für den Vergleich gerundet wird — geklammert auf
 *  [{@link MIN_NACHKOMMASTELLEN}, {@link MAX_NACHKOMMASTELLEN}]. */
export function vergleichsStellen(wert: number): number {
  if (!Number.isFinite(wert)) return MIN_NACHKOMMASTELLEN
  const s = String(wert)
  // Exponentialschreibweise (1e-7) → feinste Stufe, nie die gröbste.
  if (s.includes('e') || s.includes('E')) return MAX_NACHKOMMASTELLEN
  const punkt = s.indexOf('.')
  const stellen = punkt < 0 ? 0 : s.length - punkt - 1
  return Math.min(Math.max(stellen, MIN_NACHKOMMASTELLEN), MAX_NACHKOMMASTELLEN)
}

/** Halbe Einheit der letzten berücksichtigten Stelle = „auf `stellen` gerundet gleich". */
const toleranz = (stellen: number): number => 0.5 * Math.pow(10, -stellen)

/** Standard-Genauigkeit für Vergleiche ohne Vorschlags-Bezug (Form ↔ gespeichert):
 *  zwei Nachkommastellen, entspricht der bisherigen festen Schwelle 0,005. */
const STANDARD_STELLEN = 2

/** Zwei gerundete Messwerte gelten als gleich (Werte sind auf ≤2 Nachkommastellen gerundet). */
export const gleich = (a: number, b: number): boolean =>
  Math.abs(a - b) < toleranz(STANDARD_STELLEN)

/**
 * Vergleich gegen einen Vorschlags-/Sensorwert **mit dessen Genauigkeit**: beide
 * Seiten zählen als gleich, wenn sie auf die Nachkommastellen von
 * `vorschlagWert` gerundet übereinstimmen (1 ≤ Stellen ≤ 3).
 *
 * Beispiele: Sensor 2,3 ↔ gespeichert 2,33 → gleich (reine Rundung).
 * Sensor 453,7 ↔ gespeichert 454,74 → NICHT gleich (echte Abweichung, 1,04 kWh).
 */
export const gleichWieVorschlag = (wert: number, vorschlagWert: number): boolean =>
  Math.abs(wert - vorschlagWert) < toleranz(vergleichsStellen(vorschlagWert))

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
export function ermittleZustand(
  formWert: string,
  feld: FeldStatus | undefined,
  bestaetigt = false,
): ZustandErgebnis {
  const best = besterVorschlag(feld?.vorschlaege)
  const gespeichert = feld?.aktueller_wert ?? null
  const hatForm = formWert.trim() !== ''
  const formNum = hatForm ? parseFloat(formWert) : NaN

  // „Weicht ab": es gibt einen gespeicherten Wert UND einen gemessenen Vorschlag,
  // der — gemessen an SEINER Genauigkeit (gleichWieVorschlag, PN 90128) —
  // abweicht, und der Eingabewert entspricht noch dem gespeicherten (der
  // Nutzer hat also noch nicht bewusst entschieden). Nur beim Bearbeiten (R2).
  // Hat der Nutzer „gespeicherten behalten" bestätigt (bestaetigt), entfällt der
  // Hinweis → der gespeicherte Wert gilt als bewusst geprüft.
  if (
    !bestaetigt &&
    gespeichert != null && best && istGemesseneQuelle(best.quelle) &&
    !gleichWieVorschlag(gespeichert, best.wert) &&
    hatForm && !Number.isNaN(formNum) && gleich(formNum, gespeichert)
  ) {
    return { zustand: 'weicht_ab', quelle: best.quelle, weichtAb: { sensorWert: best.wert, gespeichert } }
  }

  // Leeres Feld → „offen" nur wenn erwartet (Zähler ODER gemappter Sensor); sonst
  // „optional" (leer, aber nicht nötig — zählt nicht, nagt nicht; Gernot 2026-07-12).
  if (!hatForm || Number.isNaN(formNum)) {
    const erwartet = feld?.gruppe === 'zaehler' || !!feld?.sensor_id
    return { zustand: erwartet ? 'fehlt' : 'optional' }
  }

  // Entspricht dem gespeicherten Wert → dessen Quelle. Sensor/Import = gemessen,
  // manuell = geprüft (von Hand ist eine bewusste Bestätigung, Gernot 2026-07-12).
  if (gespeichert != null && gleich(formNum, gespeichert)) {
    const q = feld?.quelle ?? null
    if (q && MANUELLE_QUELLEN.has(q)) return { zustand: 'geprueft', quelle: q }
    return { zustand: 'gemessen', quelle: q ?? 'gemessen' }
  }

  // Entspricht dem besten Vorschlag → Prefill. Gemessene Quelle = gemessen; eine
  // Schätzung ist „prüfen", nach Bestätigen (✓ passt) „geprüft".
  if (best && gleichWieVorschlag(formNum, best.wert)) {
    if (istGemesseneQuelle(best.quelle)) return { zustand: 'gemessen', quelle: best.quelle }
    return { zustand: bestaetigt ? 'geprueft' : 'geschaetzt', quelle: best.quelle }
  }

  // Sonst: vom Nutzer eingetippt (≠ gespeichert, ≠ Vorschlag) → geprüft.
  return { zustand: 'geprueft', quelle: 'manuell' }
}

/** Prefill-Wert für ein leeres Feld (R1/R2 „Lücken füllen"): bester Vorschlag. */
export function prefillWert(feld: FeldStatus | undefined): number | null {
  const best = besterVorschlag(feld?.vorschlaege)
  return best ? best.wert : null
}

// ─── Rollup + Kopf-Ampel-Zählung (§6.2 / §6.7) ──────────────────────────────

/** Schweregrad für den Rollup: fehlt > weicht_ab > geschätzt > (gemessen=geprüft).
 *  `optional` ist neutral (−1) und wird vom Rollup ignoriert. */
const RANG: Record<ErfassungZustand, number> = {
  fehlt: 3, weicht_ab: 2, geschaetzt: 1, gemessen: 0, geprueft: 0, optional: -1,
}

/**
 * Rollup einer Gruppe (§6.7): der **schlechteste** relevante Zustand. `optional`
 * bleibt außen vor (leere Optionalfelder machen eine Sektion nicht unfertig). Nur
 * Optional/leer → 'gemessen' (nichts zu tun → grün, klappt zu).
 */
export function rollupZustand(zustaende: ErfassungZustand[]): ErfassungZustand {
  const relevant = zustaende.filter((z) => z !== 'optional')
  if (relevant.length === 0) return 'gemessen'
  return relevant.reduce((a, b) => (RANG[b] > RANG[a] ? b : a), relevant[0])
}

/** Kopf-Ampel-Zählung (§6.2): fertig (gemessen+geprüft) · prüfen (geschätzt+weicht_ab)
 *  · offen (fehlt). `optional` zählt nicht. */
export interface AmpelZaehlung { fertig: number; pruefen: number; offen: number }

export function zaehleAmpel(zustaende: ErfassungZustand[]): AmpelZaehlung {
  const z: AmpelZaehlung = { fertig: 0, pruefen: 0, offen: 0 }
  for (const s of zustaende) {
    if (s === 'gemessen' || s === 'geprueft') z.fertig++
    else if (s === 'geschaetzt' || s === 'weicht_ab') z.pruefen++
    else if (s === 'fehlt') z.offen++
    // optional → ignoriert
  }
  return z
}

/** Rollup-Badge (§6.7): Farb-Zustand (schlechtester) + Kurz-Label mit Anzahl. */
export function rollupBadge(zustaende: ErfassungZustand[]): { zustand: ErfassungZustand; label: string } {
  const roll = rollupZustand(zustaende)
  const z = zaehleAmpel(zustaende)
  const label = (roll === 'gemessen' || roll === 'geprueft') ? 'vollständig'
    : z.offen > 0 ? `${z.offen} offen`
    : `${z.pruefen} prüfen`
  return { zustand: roll, label }
}
