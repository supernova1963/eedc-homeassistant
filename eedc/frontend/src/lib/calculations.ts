/**
 * Pure Berechnungsfunktionen für Energie-Kennzahlen.
 *
 * Keine React-Abhängigkeiten. Können in Backend-Logik,
 * Tests und Frontend gleichermaßen verwendet werden.
 */


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

// `calcCO2Einsparung(erzeugung)` ist am 2026-07-31 mit N-21 entfallen: die
// Funktion trug im Namen den Eigenverbrauch und rechnete auf der Erzeugung —
// die vor `berechne_co2_bilanz` gültige Definition (ADR-001/DI-2). Aufrufer
// hatte sie zuletzt keine. CO₂-Mengen konstruiert ausschließlich das Backend;
// der Client liest sie aus `/cockpit/nachhaltigkeit`. Gewächtert von
// `npm run check:co2-roh`.

// ENTFERNT 2026-08-04 (Fund N-22): `calcEinspeiseErloes` war der Frontend-Spiegel
// von `core/berechnungen/einspeise_erloes.py`. Sein einziger Aufrufer war die
// Finanz-Rechnung in `pages/auswertung/types.ts` — eine zweite Finanz-Engine
// neben `services/finanz_zeilen.py`, die es seit N-22 nicht mehr gibt. Ein
// Spiegel ohne Aufrufer ist kein Vorrat, sondern der Anfang der nächsten Drift:
// er altert still mit, bis ihn jemand wieder einsetzt. Der §51-Abzug kommt
// fertig aus der Antwort (`einspeise_erloes_euro` / `einspeise_nicht_verguetet_euro`).
