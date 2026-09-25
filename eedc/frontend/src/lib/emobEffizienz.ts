/**
 * E-Auto-Effizienz über einen Zeitraum — Client-Spiegel von
 * `backend/core/berechnungen/emob.py::eauto_effizienz_zeitraum` (N-557, ADR-001).
 *
 * **Warum es diesen Spiegel gibt.** *Cockpit → Jahr* (`v4/JahrAggregat.tsx`)
 * baut das Jahr aus zwölf Monatsantworten und hat keine Backend-Zahl, die es
 * lesen könnte — die Regel braucht eine zweite Heimat, keine zweite Definition
 * (gleiches Muster wie `lib/speicherWirkungsgrad.ts`, gewächtert durch
 * `backend/tests/test_n557_emob_effizienz_symmetrie.py`).
 *
 * **Die Regel in einem Satz** (Konzept Heimladung/Fahrverbrauch, Regel 10):
 * Σ Monatswerte ÷ Σ km — jeder Monat liefert die Menge, aus der das Backend
 * seine kWh/100 km gebildet hat (`emob_verbrauch_basis_kwh`: gemessener
 * Fahrverbrauch bzw. Heim + Extern), und „gemessen" steht nur, wenn **jeder**
 * Monat mit km gemessen ist.
 *
 * Bis zum 25.09.2026 bildete das Jahr hier `Σ Heimladung ÷ Σ km` und nannte das
 * „gemessen", sobald ein einziger Monat gemessen war (N-557, Johnny_1993 #375).
 */

export type EmobVerbrauchQuelle = 'gemessen' | 'ladung' | 'keine'

/** Was ein Monat zur Zeitraum-Quote beiträgt — die Felder der Monatsantwort. */
export interface EmobEffizienzMonat {
  /** Die Menge hinter der Monats-Quote; `null` ⇒ der Monat hat keine Basis. */
  basis_kwh: number | null | undefined
  km: number | null | undefined
  quelle: EmobVerbrauchQuelle
}

export interface EmobEffizienz {
  /** kWh/100 km — `null` heißt „keine Basis", nicht 0. */
  wert: number | null
  quelle: EmobVerbrauchQuelle
}

export function emobEffizienzZeitraum(monate: readonly EmobEffizienzMonat[]): EmobEffizienz {
  const beitraege = monate.filter((m) => m.basis_kwh != null && (m.km ?? 0) > 0)
  const km = beitraege.reduce((s, m) => s + (m.km ?? 0), 0)
  if (km <= 0) return { wert: null, quelle: 'keine' }
  const basis = beitraege.reduce((s, m) => s + (m.basis_kwh ?? 0), 0)
  const alleGemessen = monate
    .filter((m) => (m.km ?? 0) > 0)
    .every((m) => m.quelle === 'gemessen')
  return { wert: (basis / km) * 100, quelle: alleGemessen ? 'gemessen' : 'ladung' }
}
