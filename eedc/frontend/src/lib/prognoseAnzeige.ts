/**
 * Prognose-Anzeigewerte — EIN Zugriffsweg auf „welche Zahl zeigt die Solar-
 * Prognose?" (Regel 0a: Regel existiert → anwenden, keine lokale Variante).
 *
 * Hintergrund (Rainer-PN „Nachtrag" 2026-07-25): der 14-Tage-Balken zeigte für
 * denselben Tag 13 kWh, die Stundenwerte-Summe darunter 10,8 kWh. Die 13 war
 * die unkorrigierte OpenMeteo-Rohprognose, die 10,8 der eedc-korrigierte Wert
 * (Prognose-Kanon) — dieselbe Seite, zwei Zahlen. Seither liefert
 * `/api/solar-prognose` je Tag BEIDE Werte; angezeigt wird der korrigierte,
 * der Rohwert bleibt als Fallback und als Basis der „OpenMeteo"-Spalte im
 * Prognosen-Vergleich erhalten.
 *
 * Wer einen Prognose-Tageswert anzeigt, nimmt ihn hier — sonst entsteht die
 * nächste Zahl, die daneben steht.
 */
import type { SolarPrognose, SolarPrognoseTag, PrognoseAnzeigeQuelle } from '../api/wetter'
import { PROGNOSE_QUELLE_LABEL } from './constants'

/** Anzuzeigender Tagesertrag: eedc-korrigiert, sonst OpenMeteo roh. */
export function pvErtragKwh(tag: SolarPrognoseTag): number {
  return tag.eedc_kwh ?? tag.pv_ertrag_kwh
}

/** Vormittags-Anteil passend zu `pvErtragKwh` (`undefined` = kein VM/NM-Split). */
export function pvVormittagKwh(tag: SolarPrognoseTag): number | undefined {
  return tag.eedc_kwh != null && tag.eedc_morgens_kwh != null
    ? tag.eedc_morgens_kwh
    : tag.pv_ertrag_morgens_kwh
}

/** Nachmittags-Anteil passend zu `pvErtragKwh`. */
export function pvNachmittagKwh(tag: SolarPrognoseTag): number | undefined {
  return tag.eedc_kwh != null && tag.eedc_nachmittags_kwh != null
    ? tag.eedc_nachmittags_kwh
    : tag.pv_ertrag_nachmittags_kwh
}

/** Σ über die angezeigten Tageswerte (Backend-Aggregat, ADR-001). */
export function prognoseSummeKwh(p: SolarPrognose): number {
  return p.eedc_summe_kwh ?? p.summe_kwh
}

/** Ø/Tag über die angezeigten Tageswerte. */
export function prognoseDurchschnittKwh(p: SolarPrognose): number {
  return p.eedc_durchschnitt_kwh_tag ?? p.durchschnitt_kwh_tag
}

/** Werte-Quelle der Anzeige — Beschriftung muss zur Zahl passen. */
export function prognoseQuelle(p: SolarPrognose): PrognoseAnzeigeQuelle {
  return p.anzeige_quelle ?? 'openmeteo'
}

/** Kurzer Quellen-Text für Blockkopf/Legende („Quelle: …"). */
export function prognoseQuelleLabel(p: SolarPrognose): string {
  return PROGNOSE_QUELLE_LABEL[prognoseQuelle(p)]
}
