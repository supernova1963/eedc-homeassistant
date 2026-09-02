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

/* Speicher-Effizienz stand hier bis zum 17.08.2026 als `calcSpeicherEffizienz`
 * — ein roher, ungekappter Quotient, also eine zweite Definition neben dem
 * Layer-SoT `core/berechnungen/speicher_wirkungsgrad.py`. Sie ist ersetzt
 * durch `lib/speicherWirkungsgrad.ts::speicherWirkungsgrad`, der dieselbe
 * Rechnung mit Obergrenze UND der Herkunft der Aussage liefert (N-252).
 * Der Wächter `check:speicher-eta-roh` hält die Stelle frei. */

// ENTFERNT 2026-09-02 (ADR-002/P12): `calcCOP` war der Frontend-Spiegel von
// `core/berechnungen/waermepumpe_kennzahl.py::arbeitszahl` — nur ohne dessen
// R2-Sperren. Ihr einziger Aufrufer war die Werte-Tabelle
// (`pages/auswertung/types.ts`), die damit als einzige Sicht eine Arbeitszahl
// zeigte, die Cockpit und Komponenten-Hub daneben schon verweigerten.
// Die Zahl kommt jetzt fertig aus `/monatsdaten/aggregiert`, gebildet mit
// demselben SoT wie Cockpit, Hub, PDF und HA-Export. Gewaechtert von
// `npm run check:cop-roh`.
//
// Dritte Streichung dieser Familie nach `calcCO2Einsparung` (N-21) und
// `calcEinspeiseErloes` (N-22) — und aus demselben Grund: Ein Client-Spiegel
// einer Layer-Formel altert still mit, bis ihn jemand wieder einsetzt.

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
