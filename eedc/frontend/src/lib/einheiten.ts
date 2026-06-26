/**
 * Einheiten-/Zahl-SoT (IA-V4 A.5, Regel R2) — EINE Stelle für Einheiten-Umschaltung
 * + feste Nachkommastellen je Größe. Löst die dezentrale, inkonsistente IST-Praxis
 * (EnergyFlowDiagram ≥1000→MWh/1 NK · AktuellerMonat >10000/1 NK · WP/Speicher 2 NK ·
 * ROI €→k€ · CO₂ frei t/kg/g) durch eine konsistente Regel ab.
 *
 * Abnahme Gernot 2026-06-25 (SPEC-AUSWERTUNGEN.md §0a, R2-Tabelle):
 *  - Umschalt-Schwelle = **≥ 1.000** der jeweiligen Einheit (Einzelwert; bei Achsen
 *    bestimmt der Achsen-Max die Einheit für die GANZE Achse → value=Achse=Tooltip=CSV gleich).
 *  - NK: kWh 0 · MWh/GWh 2 · kg 0 · t 2 · € (Summen) 0 · ct/kWh 2 · % 1 · kWh/kWp 0 · JAZ/COP/PR 2.
 *  - Zahlen de-DE mit Tausenderpunkt (R1); Nicht-Mengen (Jahr/ID/Version) laufen NIE hier durch.
 *
 * Gibt `{ wert, einheit, text }` zurück: `wert`/`einheit` getrennt für KPICard-Slots,
 * `text` = „wert einheit" für Tooltips/Tabellen/CSV.
 */

const FALLBACK = '—'

/** de-DE-Zahl mit Tausenderpunkt + fester NK (gleiche Semantik wie `fmtCalc`,
 *  aber layer-sauber in lib). Mengen-SoT — Nicht-Mengen (Jahr/ID) NICHT hierdurch. */
export function fmtZahl(n: number | null | undefined, nk = 0, fallback = FALLBACK): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return fallback
  return n.toLocaleString('de-DE', { minimumFractionDigits: nk, maximumFractionDigits: nk })
}

export interface FmtWert {
  /** formatierte Zahl (ohne Einheit), z. B. „2,00". */
  wert: string
  /** Einheit, z. B. „MWh". */
  einheit: string
  /** „wert einheit", z. B. „2,00 MWh". */
  text: string
}

interface Stufe {
  faktor: number
  einheit: string
  nk: number
}
type Leiter = Stufe[] // aufsteigend nach faktor

const ENERGIE: Leiter = [
  { faktor: 1, einheit: 'kWh', nk: 0 },
  { faktor: 1_000, einheit: 'MWh', nk: 2 },
  { faktor: 1_000_000, einheit: 'GWh', nk: 2 },
]
const CO2: Leiter = [
  { faktor: 1, einheit: 'kg', nk: 0 },
  { faktor: 1_000, einheit: 't', nk: 2 },
]
const LEISTUNG: Leiter = [
  { faktor: 1, einheit: 'W', nk: 0 },
  { faktor: 1_000, einheit: 'kW', nk: 2 },
  { faktor: 1_000_000, einheit: 'MW', nk: 2 },
]

/** Höchste Stufe, deren Schwelle (faktor) der |Referenzwert| erreicht (≥ 1.000-Regel). */
function waehleStufe(leiter: Leiter, referenz: number): Stufe {
  const abs = Math.abs(referenz)
  let gewaehlt = leiter[0]
  for (const s of leiter) if (abs >= s.faktor) gewaehlt = s
  return gewaehlt
}

function formatMitStufe(stufe: Stufe, wert: number | null | undefined): FmtWert {
  if (wert === null || wert === undefined || !Number.isFinite(wert)) {
    return { wert: FALLBACK, einheit: stufe.einheit, text: FALLBACK }
  }
  const wertStr = fmtZahl(wert / stufe.faktor, stufe.nk)
  return { wert: wertStr, einheit: stufe.einheit, text: `${wertStr} ${stufe.einheit}` }
}

/** Einzelwert in skalierter Einheit. `referenz` erzwingt eine gemeinsame Einheit
 *  (z. B. Achsen-Max), damit mehrere Werte konsistent dieselbe Einheit tragen. */
function skaliere(leiter: Leiter, wert: number | null | undefined, referenz?: number): FmtWert {
  const ref = referenz ?? (wert ?? 0)
  return formatMitStufe(waehleStufe(leiter, ref), wert)
}

/** Achsen-Formatter: EINE Einheit (vom Achsen-Max bestimmt) für alle Ticks. */
function achse(leiter: Leiter, maxBasis: number): { einheit: string; tick: (v: number) => string } {
  const stufe = waehleStufe(leiter, maxBasis)
  return { einheit: stufe.einheit, tick: (v: number) => fmtZahl(v / stufe.faktor, stufe.nk) }
}

// ── Skalierende Größen (Schwelle ≥ 1.000) ────────────────────────────────────
export const formatEnergie = (kwh: number | null | undefined, referenzKwh?: number): FmtWert =>
  skaliere(ENERGIE, kwh, referenzKwh)
export const formatCo2 = (kg: number | null | undefined, referenzKg?: number): FmtWert =>
  skaliere(CO2, kg, referenzKg)
export const formatLeistung = (w: number | null | undefined, referenzW?: number): FmtWert =>
  skaliere(LEISTUNG, w, referenzW)

export const energieAchse = (maxKwh: number) => achse(ENERGIE, maxKwh)
export const co2Achse = (maxKg: number) => achse(CO2, maxKg)
export const leistungAchse = (maxW: number) => achse(LEISTUNG, maxW)

// ── Fixe Einheiten (keine Skalierung) ─────────────────────────────────────────
const fix = (wert: number | null | undefined, einheit: string, nk: number): FmtWert => {
  const wertStr = fmtZahl(wert, nk)
  return { wert: wertStr, einheit, text: wertStr === FALLBACK ? FALLBACK : `${wertStr} ${einheit}` }
}

/** Geld-Summe: € ohne Cent (0 NK). Für Tarife → {@link formatTarif}. */
export const formatGeld = (eur: number | null | undefined): FmtWert => fix(eur, '€', 0)
/** Tarif/Cent-Wert: ct/kWh mit 2 NK. */
export const formatTarif = (ct: number | null | undefined): FmtWert => fix(ct, 'ct/kWh', 2)
/** Anteil/Quote: % mit 1 NK (Leerzeichen vor % via `text`). */
export const formatProzent = (p: number | null | undefined): FmtWert => fix(p, '%', 1)
/** Spezifischer Ertrag: kWh/kWp, 0 NK. */
export const formatSpezErtrag = (v: number | null | undefined): FmtWert => fix(v, 'kWh/kWp', 0)
/** Effizienz-Kennzahl (JAZ/COP/PR), dimensionslos, 2 NK. */
export const formatEffizienz = (v: number | null | undefined, einheit = ''): FmtWert => fix(v, einheit, 2)
