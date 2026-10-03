/**
 * Monatsfenster — die BESCHRIFTUNG eines Zeitfensters („Jan–Jul", „Jan–Feb, Apr–Jul").
 *
 * Bis 03.10.2026 Teil von `v4/JahrAggregat.tsx`. Die Faltung selbst ist mit dem Paket „Ergebnisgrößen Monat/Jahr
 * in den Layer" ins Backend gezogen (`core/berechnungen/ergebnis.py::falte_zeitraum`, Jahresroute
 * `GET /cockpit/jahr`); hier bleibt nur, was Text setzt und nicht rechnet.
 */
import { MONAT_KURZ } from './constants'
import type { JahrVergleich } from '../api/cockpit'

/** „Jan–Jul" bzw. „Jan–Feb, Apr–Jul" — zusammenhängende Läufe zusammengefasst. */
function monatsBereiche(monate: number[]): string {
  const teile: string[] = []
  let start = monate[0]
  let vorher = monate[0]
  const schliesse = () => teile.push(start === vorher ? MONAT_KURZ[start] : `${MONAT_KURZ[start]}–${MONAT_KURZ[vorher]}`)
  for (const m of monate.slice(1)) {
    if (m === vorher + 1) { vorher = m; continue }
    schliesse()
    start = m
    vorher = m
  }
  schliesse()
  return teile.join(', ')
}

/**
 * Beschriftung des Vergleichsfensters — oder `null`, wenn nichts zu sagen ist.
 *
 * **Steht dort weniger als ein volles Jahr, muss dranstehen, welche Monate es sind.** Geprüft wird die tatsächliche
 * Deckung, NICHT „läuft das Jahr noch" (N-37).
 */
export function monatsFenster(vergleich: Pick<JahrVergleich, 'monate'> | null): string | null {
  return monatsFensterAus(vergleich?.monate)
}

/** Dieselbe Regel für eine nackte Monatsmenge (IST-Spalte, s. {@link monatsFenster}). */
export function monatsFensterAus(monate: readonly number[] | null | undefined): string | null {
  if (!monate || monate.length === 0 || monate.length >= 12) return null
  return monatsBereiche([...monate])
}

/**
 * Fenster der KENNZAHLEN-Kacheln — gesetzt genau dann, wenn die Kopfzahl mehr Monate umfasst als der Vergleich
 * darunter (ADR-002/P4). Die 12-Monats-Ausnahme gilt hier NICHT: im Dezember deckt die Kopfzahl Jan–Dez ab, der
 * Vergleich nur Jan–Nov — dann ist gerade ein volles Fenster erklärungsbedürftig.
 */
export function kennzahlenFensterAus(
  kopfMonate: readonly number[],
  vergleichsMonate: readonly number[],
): string | null {
  if (kopfMonate.length === 0) return null
  if (kopfMonate.length === vergleichsMonate.length
    && kopfMonate.every((m, i) => m === vergleichsMonate[i])) return null
  return monatsBereiche([...kopfMonate])
}
