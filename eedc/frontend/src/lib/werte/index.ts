/**
 * Werte/Tabelle-SoT (W1) — Barrel.
 */
export type { WerteMetrik, WerteGruppe, WerteAggregation } from './registry'
export {
  WERTE_METRIKEN, WERTE_GRUPPEN, GRUPPE_LABELS, METRIK_BY_KEY, getMonatWert,
} from './registry'
export { fmtWert } from './format'
export { aggregiere } from './aggregate'
export { bewerteDelta } from './bewertung'
export type { DeltaUrteil } from './bewertung'
export { exportWerteCsv } from './csv'
export type { WerteCsvOptions } from './csv'
