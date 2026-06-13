/**
 * Zentrale Farbdefinitionen — DIE Farb-SoT des Frontends.
 * (Style-Guide A2 · Regel Nr. 0/0a · VORBEREITUNG-E1-FUNDAMENT §6/§7, entschieden 2026-06-12)
 *
 * Regeln:
 * - KEINE Inline-Hex-Farben in Komponenten/Seiten — jede Farbe kommt von hier.
 *   Wächter: `npm run check:design` (scripts/check-design-konformitaet.mjs).
 * - Neue Farb-Rolle nötig? HIER ergänzen (Regel 0a Stufe 2), nicht lokal hardcoden.
 *   Echte Einzelfall-Ausnahme nur mit Maintainer-Freigabe + Eintrag in der
 *   Ausnahmen-Liste des Wächter-Skripts.
 * - tailwind.config.js importiert dieses Modul (jiti) — Theme kann nicht driften.
 *
 * Entscheide (F1–F4, Gernot 2026-06-12):
 * - F1: Solar-Kanon = #f59e0b (vorher drei Gelbtöne: #f59e0b/#fbbf24/#eab308).
 * - F2: Netzbezug = Dunkelrot #b91c1c (vorher #ef4444); Signal-Rot #ef4444 ist
 *   exklusiv für Kosten/negativ/Fehler. Komponenten-Identität WP bleibt #ef4444
 *   (TYP_COLORS — bewusste, dokumentierte Ko-Existenz).
 * - F3: Status-Achse ok/warnung/kritisch/info (= bisherige Ampel-Schwellen).
 * - F4: Grün-Duo bewusst getrennt: #10b981 = Einspeisung/Erlös (Emerald),
 *   #22c55e = Speicher-Ladung/Status-ok (Green) — erscheinen in denselben Charts.
 */

// ─── Energie-Rollen (A2-Datentyp-Achse) ─────────────────────────────────────

export const COLORS = {
  solar: '#f59e0b',       // F1: kanonisches Amber
  grid: '#b91c1c',        // F2: Dunkelrot — Netzbezug-Serie überall
  consumption: '#8b5cf6', // Violett
  battery: '#3b82f6',     // Blau
  feedin: '#10b981',      // Emerald (F4: bewusst ≠ #22c55e)
}

// ─── Status-Achse (F3) — Zustände, Ampeln, Badges, Alerts ───────────────────

export const STATUS_COLORS = {
  ok: '#22c55e',       // green-500
  warnung: '#eab308',  // yellow-500
  kritisch: '#ef4444', // Signal-Rot
  info: '#3b82f6',     // blue-500
}

/** 4-stufige Ampel-Skala für Gauges (Status-Achse + Zwischenstufe Orange). */
export const AMPEL_SKALA = {
  gut: STATUS_COLORS.ok,
  maessig: STATUS_COLORS.warnung,
  hoch: '#f97316',     // orange-500 — Zwischenstufe vor kritisch
  kritisch: STATUS_COLORS.kritisch,
}

// ─── Geld-Logik — positiv = grün, negativ/Kosten = Signal-Rot ────────────────

export const GELD_COLORS = {
  ertrag: '#10b981',    // Erlöse (z. B. Einspeisevergütung)
  ersparnis: '#22c55e', // vermiedene Kosten
  kosten: '#ef4444',    // Signal-Rot
  netto: '#059669',     // emerald-600 — Netto-Ertrag
}

// ─── Chart-Farben (nach Metrik) ──────────────────────────────────────────────

export const CHART_COLORS = {
  // Energie
  erzeugung: COLORS.solar,
  eigenverbrauch: COLORS.consumption,
  einspeisung: COLORS.feedin,
  netzbezug: COLORS.grid,
  autarkie: '#3b82f6',           // Blue (Metrik-Farbe, unabhängig von battery)
  evQuote: '#a855f7',            // Purple-500
  direktverbrauch: '#f97316',    // Orange
  spezErtrag: '#eab308',         // Yellow
  // Speicher
  speicherLadung: '#22c55e',     // Green (F4)
  speicherEntladung: '#3b82f6',  // Blue
  speicherEffizienz: '#06b6d4',  // Cyan
  // Wärmepumpe (Komponenten-Identität Rot bleibt — dokumentiert, s. Kopf)
  wpWaerme: '#ef4444',
  wpStrom: '#8b5cf6',
  wpCop: '#f97316',
  // E-Mobilität
  emobKm: '#8b5cf6',
  emobLadung: '#3b82f6',
  emobPvAnteil: '#10b981',
  // CO2
  co2Pv: '#10b981',
  co2Wp: '#ef4444',
  co2Emob: '#8b5cf6',
  // Finanzen (Geld-Logik; wpErsparnis war Fehlfarbe Rot → grün, A2-Bereinigung)
  einspeiseErloes: GELD_COLORS.ertrag,
  evErsparnis: '#8b5cf6',
  wpErsparnis: GELD_COLORS.ersparnis,
  emobErsparnis: '#3b82f6',
  nettoErtrag: GELD_COLORS.netto,
  // Wetter / Umgebung
  temperatur: '#6366f1',         // Indigo
  strahlung: '#f59e0b',          // = solar (GHI/GTI)
  bewoelkung: '#94a3b8',         // slate-400
  niederschlag: '#0ea5e9',       // sky-500
  strompreis: '#a855f7',         // Purple-500
  solarNoon: '#f97316',          // Sonnenhöchststand-Marker (≠ SA/SU = solar)
  // Detail-Rollen (Sweep-Nachträge 2026-06-12, Regel 0a Stufe 2)
  speicherArbitrage: '#8b5cf6',  // Netz-Ladung fürs Arbitrage-Laden (Detail-Stack)
  speicherZyklen: '#8b5cf6',     // Vollzyklen-Verlauf
  wpWarmwasser: '#3b82f6',       // Warmwasser-Anteil (Heizung = wpWaerme)
  emobV2h: '#06b6d4',            // Vehicle-to-Home-Rückspeisung
}

/** E-Auto-/Wallbox-Ladequellen — ein Trio, überall gleich (PV günstig → Extern teuer). */
export const LADEQUELLEN_FARBEN = {
  pv: '#22c55e',
  netz: COLORS.grid,   // Netz-Ladung IST Netzbezug → Dunkelrot
  extern: '#f97316',
}

/** „Du/deine Daten"-Hervorhebung in Community-Vergleichen — überall dieselbe. */
export const EIGENE_SERIE_FARBEN = {
  du: '#3b82f6',
  duRand: '#1d4ed8',   // Rahmen/Outline der eigenen Markierung (z. B. Choropleth)
  region: '#60a5fa',   // Zwischenebene Du ↔ Community
}

/** Karten-Darstellung (Choropleth). */
export const KARTE_FARBEN = { grenze: '#ffffff' }

/** Neutrale/inaktive Datenserie (z. B. übrige Histogramm-Bins). */
export const SERIE_NEUTRAL = '#d1d5db'

/** Schwellen-/Warn-Marker in Charts (ReferenceLine + Beschriftung). */
export const MARKER_WARNUNG = { linie: STATUS_COLORS.warnung, text: '#b45309' }

/** Wochentags-Identitätsfarben (Energieprofil-Gruppierung Mo–So + Sammelgruppen). */
export const WOCHENTAG_FARBEN: Record<string, string> = {
  'Mo–Fr': '#3b82f6',
  'Sa–So': '#f97316',
  'Mo': '#6366f1',
  'Di': '#8b5cf6',
  'Mi': '#ec4899',
  'Do': '#14b8a6',
  'Fr': '#84cc16',
  'Sa': '#f59e0b',
  'So': '#ef4444',
}

// ─── SOLL/IST-Vergleichsfarben (zentral für alle SOLL-IST-Diagramme) ────────
//
// Müssen in ALLEN SOLL-IST-Diagrammen gleich sein, damit Nutzer konsistente
// Farben über Tabs/Seiten hinweg sehen (Cockpit, Auswertungen, Aussichten).

export const SOLL_IST_COLORS = {
  soll: '#3b82f6',   // Blau (Prognose)
  ist: '#f59e0b',    // Amber (tatsächlicher Wert)
  abweichung: '#10b981',  // Grün (Differenz-Linie)
}

/** Prognose-Quellen — eine Quelle = überall dieselbe Farbe (Vergleichs-Tab, Charts). */
export const PROGNOSE_QUELLEN_COLORS = {
  ist: '#22c55e',
  openmeteo: '#eab308',
  eedc: '#f97316',
  solcast: '#3b82f6',
}

// ─── Mehrserien-Paletten ─────────────────────────────────────────────────────

/** Jahres-/Serienvergleich (Balken pro Jahr) — Reihenfolge fix, max. 5 Serien. */
export const SERIEN_PALETTE = ['#f59e0b', '#22c55e', '#3b82f6', '#ef4444', '#8b5cf6']

/** PV-String-Vergleich (bis 6 Strings) — identisch in allen String-Ansichten. */
export const STRING_COLORS = ['#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#06b6d4', '#ec4899']

/** Solar-Intensitäts-Rampe (Sparklines: schwach → stark). */
export const SOLAR_INTENSITAET = ['#fde68a', '#fbbf24', '#f59e0b']

/** Zusatz-/Extra-Serien (dynamische Kategorien jenseits der festen Rollen). */
export const EXTRA_SERIEN_FARBEN = ['#8b5cf6', '#06b6d4', '#84cc16', '#f43f5e', '#fb923c', '#a78bfa']

// ─── Tooltip-Grundfarben (Vorgriff auf den Tooltip-Kanon, Paket P3) ─────────

export const TOOLTIP_FARBEN = {
  bg: '#111827',      // gray-900 — Tooltip-Kanon (P3, = FormelTooltip/ChartTooltip-Fläche)
  text: '#ffffff',
}

// ─── Chart-Infrastruktur: Achsen/Grid/Referenzlinien (hell + dunkel) ────────

/** Für Inline-Styles in Charts (Recharts stroke etc.) — Tailwind-Klassen gehen vor. */
export const CHART_ACHSEN = {
  light: { achse: '#6b7280', grid: '#e5e7eb', referenz: '#9ca3af' }, // gray-500/200/400
  dark:  { achse: '#9ca3af', grid: '#374151', referenz: '#6b7280' }, // gray-400/700/500
}

// ─── Tagesverlauf-Kategorien ─────────────────────────────────────────────────

/** Farben für Energiefluss- und Bilanz-Visualisierungen (nach Tagesverlauf-Kategorie) */
export const KATEGORIE_FARBEN: Record<string, string> = {
  pv: COLORS.solar,        // F1: war #eab308 — kanonisiert
  netz: COLORS.grid,       // F2: Dunkelrot
  batterie: COLORS.battery,
  eauto: '#a855f7',
  wallbox: '#a855f7',
  waermepumpe: '#f97316',
  sonstige: '#6b7280',
  haushalt: '#10b981',
}

/**
 * Kategorien die KEINE Energieflüsse darstellen (z.B. Preise, virtuelle Serien).
 * Werden im Verbrauchs-Stacking (WetterWidget etc.) ignoriert.
 * → Neue nicht-Energie-Kategorien hier ergänzen, nicht in einzelnen Komponenten.
 */
export const NICHT_ENERGIE_KATEGORIEN = new Set(['preis', 'virtual'])

/** Kategorien die dedizierte DB-Felder/Spalten haben (kein Extra-Tracking nötig) */
export const DEDIZIERTE_KATEGORIEN = new Set([
  'pv', 'batterie', 'netz', 'haushalt', 'waermepumpe', 'wallbox', 'eauto', 'virtual',
])

// ─── Typ-Farben (Komponenten-Identität der Investitionstypen) ────────────────

export const TYP_COLORS: Record<string, string> = {
  'pv-module': '#f59e0b',
  'wechselrichter': '#eab308',
  'speicher': '#3b82f6',
  'e-auto': '#8b5cf6',
  'wallbox': '#06b6d4',
  'waermepumpe': '#ef4444', // Identitäts-Rot, bewusste Ko-Existenz mit Signal-Rot
  'balkonkraftwerk': '#10b981',
  'sonstiges': '#6b7280',
  'pv-system': '#f97316',
}
