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
import type { LiveWetterResponse, VerbrauchsStunde } from '../api/liveDashboard'
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

/**
 * PV-Prognose (kW) einer Stunde der Live-Wetter-Antwort aus der GEWÄHLTEN
 * Quelle — die Kurve «Wetter heute» (N-761, #434).
 *
 * Bis N-761 zeichnete das Widget immer `pv_ertrag_kw` (eedc), auch wenn
 * Kopfzahl und Quellenvermerk Solar Forecast ML oder Solcast nannten: Σ Kurve
 * 36,1 kWh neben 47,75 kWh Kopfzahl. Entscheid #401: ein Block, eine Quelle —
 * die Kurve wählt, sie rechnet nichts.
 *
 * `pv_ml_prognose_kw` ist die Heute-Reihe der effektiven Quelle (SFML oder
 * Solcast, Backend `live_wetter_antwort.py::_quelle_ins_profil`). Sie gilt nur,
 * wenn die Antwort ein Stundenprofil der Quelle meldet
 * (`prognose_quelle_hat_profil`, je Antwort, nicht je Stunde) — ohne Profil
 * ist die Reihe aus der eedc-Kurvenform geschmiert (SFML-GTI-Rückfall), und
 * genau diese Vermischung meidet der Block auch beim Rest. Bei eedc als Quelle
 * (gewählt oder zurückgefallen) gilt die eedc-Reihe; fehlt der Stundenwert,
 * gilt der eedc-Wert dieser Stunde.
 */
export function pvPrognoseKwDerQuelle(
  wetter: Pick<LiveWetterResponse, 'prognose_quelle' | 'prognose_quelle_hat_profil'>,
  stunde: VerbrauchsStunde,
): number {
  const fremdeQuelle = wetter.prognose_quelle != null && wetter.prognose_quelle !== 'eedc'
  if (fremdeQuelle && wetter.prognose_quelle_hat_profil && stunde.pv_ml_prognose_kw != null) {
    return stunde.pv_ml_prognose_kw
  }
  return stunde.pv_ertrag_kw
}
