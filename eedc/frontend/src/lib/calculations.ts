/**
 * Pure Berechnungsfunktionen für Energie-Kennzahlen.
 *
 * Keine React-Abhängigkeiten. Können in Backend-Logik,
 * Tests und Frontend gleichermaßen verwendet werden.
 */

import { CO2_FAKTOR_KG_KWH } from './constants'

/** Autarkiequote: Anteil Eigenverbrauch am Gesamtverbrauch (0–100 %). */
export function calcAutarkie(eigenverbrauch: number, gesamtverbrauch: number): number {
  return gesamtverbrauch > 0 ? (eigenverbrauch / gesamtverbrauch) * 100 : 0
}

/** Eigenverbrauchsquote: Anteil Eigenverbrauch an PV-Erzeugung (0–100 %). */
export function calcEigenverbrauchsquote(eigenverbrauch: number, erzeugung: number): number {
  return erzeugung > 0 ? (eigenverbrauch / erzeugung) * 100 : 0
}

/** Spezifischer Ertrag: kWh pro kWp installierter Leistung. */
export function calcSpezifischerErtrag(erzeugung: number, kwp: number | null | undefined): number {
  return kwp ? erzeugung / kwp : 0
}

/** Speicher-Effizienz: Verhältnis Entladung zu Ladung (0–100 %). */
export function calcSpeicherEffizienz(entladung: number, ladung: number): number | null {
  return ladung > 0 ? (entladung / ladung) * 100 : null
}

/** Wärmepumpen-COP: Coefficient of Performance. */
export function calcCOP(waerme: number, strom: number): number | null {
  return strom > 0 ? waerme / strom : null
}

/** CO2-Einsparung in kg durch PV-Eigenverbrauch. */
export function calcCO2Einsparung(erzeugung: number): number {
  return erzeugung * CO2_FAKTOR_KG_KWH
}

/** Ergebnis der §51-bereinigten Erlös-Berechnung (Spiegel von `EinspeiseErloes`). */
export interface EinspeiseErloes {
  /** Tatsächlicher Erlös in € (nach §51-Abzug). */
  erloes_euro: number
  /** Erlös, der durch §51 entfallen ist (= entgangener Erlös). */
  nicht_verguetet_euro: number
  /** Eingespeiste kWh, die nicht vergütet wurden (= §51-Volumen). */
  nicht_verguetete_kwh: number
}

/**
 * Einspeise-Erlös unter §51 EEG — Spiegel des Backend-SoT
 * `core/berechnungen/einspeise_erloes.py::einspeise_erloes_euro`.
 *
 * Seit Solarpaket I entfällt für betroffene Anlagen die Vergütung in Stunden mit
 * negativem Börsenpreis. Das Volumen steht als `einspeisung_neg_preis_kwh` in den
 * aggregierten Monatsdaten (`null` = Anlage unterliegt nicht §51 bzw. keine
 * Strompreis-Mitschrift → kein Abzug, wie vor dem Feature).
 *
 * `max(0, min(...))` fängt Drift zwischen Monatsdaten und Tages-Aggregat ab —
 * ein negativer Erlös darf daraus nie entstehen. Beide Implementierungen müssen
 * identisch bleiben; die Testfälle spiegeln `backend/tests/test_einspeise_erloes.py`.
 */
export function calcEinspeiseErloes(
  einspeisung_kwh: number,
  neg_preis_kwh: number | null | undefined,
  verguetung_ct_kwh: number,
): EinspeiseErloes {
  if (einspeisung_kwh <= 0) {
    return { erloes_euro: 0, nicht_verguetet_euro: 0, nicht_verguetete_kwh: 0 }
  }
  const abzugKwh = Math.max(0, Math.min(neg_preis_kwh ?? 0, einspeisung_kwh))
  return {
    erloes_euro: ((einspeisung_kwh - abzugKwh) * verguetung_ct_kwh) / 100,
    nicht_verguetet_euro: (abzugKwh * verguetung_ct_kwh) / 100,
    nicht_verguetete_kwh: abzugKwh,
  }
}
