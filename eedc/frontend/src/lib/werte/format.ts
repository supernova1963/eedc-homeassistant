/**
 * Zahl-Formatierung für die Werte-Tabelle — delegiert an die zentrale Zahl-SoT
 * `fmtZahl` (R1: de-DE mit Tausenderpunkt). Eigener Name bleibt für die Werte-
 * Modul-Aufrufer; EINE Format-Wahrheit (kein zweiter toLocaleString-Wrapper).
 */
import { fmtZahl } from '../einheiten'

export function fmtWert(v: number | null, decimals: number): string {
  return fmtZahl(v, decimals)
}
