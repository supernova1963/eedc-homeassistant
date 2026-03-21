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
