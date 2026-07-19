/**
 * verlaufVergleich — geteilte SoT (Presets + Filter-Logik) für den „Vergleich"-Modus
 * der Verlauf-Blöcke (Cockpit/Monat = TagesverlaufChart, Cockpit/Jahr = JahrVerlaufChart).
 *
 * R17-1/R17-2b (Rainer): statt gestapelter Bilanz-Balken **ungestackte, gruppierte**
 * Balken ausgewählter Kennzahlen je Zeitschritt. **Datengrenzen (Jahr-only):**
 * Netzladung + E-Auto haben keine billige Tagesauflösung → in der Monat-Sicht
 * ausgeblendet (`nurJahr`). Farben ausschließlich aus `CHART_COLORS` (Rule 0a).
 *
 * Reine Logik/Konstanten (kein JSX) — der Renderer lebt in `VergleichBalken.tsx`.
 */
import { CHART_COLORS } from '../lib'
import type { ChartTabelleSpalte } from '../components/ui'

export interface VergleichSerie {
  /** dataKey im ChartPunkt (beide Charts liefern denselben Key). */
  key: string
  name: string
  color: string
  /** km statt kWh → zweite (rechte) Achse. */
  achse?: 'kwh' | 'km'
  /** Serie nur in der Jahr-Sicht (keine billige Tagesauflösung). */
  nurJahr?: boolean
}

export interface VergleichPreset {
  key: string
  label: string
  serien: VergleichSerie[]
  /** Ganzes Preset nur in der Jahr-Sicht. */
  nurJahr?: boolean
}

export const VERLAUF_PRESETS: VergleichPreset[] = [
  {
    key: 'verbrauch',
    label: 'Verbrauch',
    serien: [
      { key: 'netzbezug', name: 'Netzbezug', color: CHART_COLORS.netzbezug },
      { key: 'eigenverbrauch', name: 'Eigenverbrauch', color: CHART_COLORS.eigenverbrauch },
    ],
  },
  {
    key: 'erzeugung',
    label: 'Erzeugung',
    serien: [
      { key: 'pvAnlage', name: 'PV-Anlage', color: CHART_COLORS.erzeugung },
      { key: 'bkw', name: 'Balkonkraftwerk', color: CHART_COLORS.bkw },
    ],
  },
  {
    key: 'ertrag',
    label: 'Ertrag',
    serien: [
      { key: 'einspeisung', name: 'Einspeisung', color: CHART_COLORS.einspeisung },
      { key: 'neg51', name: '§51-Abzug', color: CHART_COLORS.einspeisungNeg51 },
    ],
  },
  {
    key: 'batterie',
    label: 'Batterie',
    serien: [
      { key: 'speicherLadung', name: 'Ladung', color: CHART_COLORS.speicherLadung },
      { key: 'speicherEntladung', name: 'Entladung', color: CHART_COLORS.speicherEntladung },
      { key: 'netzladung', name: 'Netzladung', color: CHART_COLORS.speicherArbitrage, nurJahr: true },
    ],
  },
  {
    key: 'emob',
    label: 'E-Auto',
    nurJahr: true,
    serien: [
      { key: 'eautoLadung', name: 'Ladung', color: CHART_COLORS.emobLadung },
      { key: 'eautoKm', name: 'Fahrleistung', color: CHART_COLORS.emobKm, achse: 'km' },
    ],
  },
]

// ─── Tabellen-Ablesung (Paket CT) ────────────────────────────────────────────

/**
 * Spalten der Chart-Daten-Tabelle beider Verlauf-Blöcke (Monat=Tage, Jahr=Monate):
 * Union der Chart-Serien über alle Modi (Bilanz gestapelt + Vergleich-Presets +
 * Autarkie-Linie), Labels identisch zu den Chart-Serien (Regel D). `nurJahr`-Serien
 * fehlen in der Monat-Sicht — dieselbe Datengrenze wie im Chart.
 */
export function verlaufTabellenSpalten(istJahr: boolean): ChartTabelleSpalte[] {
  return [
    { key: 'eigenverbrauch', label: 'Eigenverbrauch', einheit: 'kWh' },
    { key: 'einspeisung', label: 'Einspeisung', einheit: 'kWh' },
    { key: 'netzbezug', label: 'Netzbezug', einheit: 'kWh' },
    { key: 'direktverbrauch', label: 'Direktverbrauch', einheit: 'kWh' },
    { key: 'speicherEntladung', label: 'Speicher-Entladung', einheit: 'kWh' },
    { key: 'pvAnlage', label: 'PV-Anlage', einheit: 'kWh' },
    { key: 'bkw', label: 'Balkonkraftwerk', einheit: 'kWh' },
    { key: 'neg51', label: '§51-Abzug', einheit: 'kWh' },
    { key: 'speicherLadung', label: 'Speicher-Ladung', einheit: 'kWh' },
    ...(istJahr
      ? [
          { key: 'netzladung', label: 'Speicher-Netzladung', einheit: 'kWh' },
          { key: 'eautoLadung', label: 'E-Auto-Ladung', einheit: 'kWh' },
          { key: 'eautoKm', label: 'Fahrleistung', einheit: 'km', nachkomma: 0 },
        ]
      : []),
    { key: 'autarkie', label: 'Autarkie', einheit: '%' },
  ]
}

/** Presets für die Sicht: in der Monat-Sicht fallen `nurJahr`-Presets weg. */
export function verfuegbarePresets(istJahr: boolean): VergleichPreset[] {
  return VERLAUF_PRESETS.filter((p) => istJahr || !p.nurJahr)
}

/** Sichtbare Serien eines Presets: in der Monat-Sicht ohne `nurJahr`-Serien. */
export function sichtbareSerien(preset: VergleichPreset, istJahr: boolean): VergleichSerie[] {
  return preset.serien.filter((s) => istJahr || !s.nurJahr)
}

// ─── Drill-in (B3) ────────────────────────────────────────────────────────────
// Balken-Klick im Vergleich-Modus → Ziel-Sicht des geklickten Zeitschritts:
// Monat-Sicht (Tages-Balken) → Cockpit/Tag · Jahr-Sicht (Monats-Balken) → Cockpit/Monat.
// Reine Pfad-/Query-Helfer (testbar ohne Router). Die Ziel-Sichten lesen den Param
// beim Laden und ziehen ihn ihrem lokalen Default vor — additiv, kein Nav-Neubau
// (etablierte `useSearchParams`-Mechanik wie CockpitAussichtV4 `?h=`).

/** Drill-in-Pfad zum Einzeltag (Monat-Sicht → Cockpit/Tag). */
export function tagDrillInPfad(datum: string): string {
  return `/v4/cockpit/tag?datum=${datum}` /* de-de-allow: ISO-Datum als URL-Query-Param (Routing), keine Nutzer-Anzeige. */
}

/** Drill-in-Pfad zum Einzelmonat (Jahr-Sicht → Cockpit/Monat). */
export function monatDrillInPfad(jahr: number, monat: number): string {
  return `/v4/cockpit/monat?jahr=${jahr}&monat=${monat}`
}

const DATUM_RE = /^\d{4}-\d{2}-\d{2}$/

/** Gültiges `?datum=YYYY-MM-DD` aus der Query, sonst null (Default gewinnt). */
export function datumAusQuery(params: URLSearchParams): string | null {
  const d = params.get('datum')
  return d != null && DATUM_RE.test(d) ? d : null
}

/** Gültiges `?jahr=&monat=` (1–12, plausibles Jahr) aus der Query, sonst null. */
export function monatRefAusQuery(params: URLSearchParams): { jahr: number; monat: number } | null {
  const jahr = Number(params.get('jahr'))
  const monat = Number(params.get('monat'))
  return Number.isInteger(jahr) && jahr >= 2000 && Number.isInteger(monat) && monat >= 1 && monat <= 12
    ? { jahr, monat }
    : null
}
