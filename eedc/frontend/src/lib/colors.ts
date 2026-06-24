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
 * - F4: #10b981 = Einspeisung/Erlös (Emerald). Speicher-Ladung war früher
 *   #22c55e (Green), las sich aber im selben Stapel zu nah am Einspeisung-
 *   Emerald (IA-V4 #243, Gernot) → jetzt Orange #f97316 (klar abgesetzt, nicht-
 *   grün). #22c55e bleibt für Status-ok / Ersparnis (eigene Achsen/Charts).
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
  speicherLadung: '#f97316',     // Orange (F4-Revision #243): klar abgesetzt von Einspeisung-Emerald; war #22c55e
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

/** Tailwind-bg-Klassen-Zwillinge zu STRING_COLORS (Tailwind-500) — für VerteilungsBalken/
 *  Anteils-Darstellungen pro String/Modul (dort sind bg-Klassen statt Inline-Hex nötig). */
export const STRING_BG = ['bg-amber-500', 'bg-blue-500', 'bg-emerald-500', 'bg-violet-500', 'bg-cyan-500', 'bg-pink-500']

/**
 * **Kanonische Datenrollen-Farben (SoT, Gernot 2026-06-24)** — die EINE Quelle
 * für „eine Datenrolle = eine Farbe" (Regel 0a). Jede Rolle trägt den Recharts-
 * **Hex** (Linien/Balken/Pies) UND die **Tailwind-bg-Klasse** (VerteilungsBalken),
 * damit dieselbe Rolle in JEDER Darstellung gleich aussieht. Abgeleitet aus
 * {@link COLORS}; Hex ↔ bg sind aufeinander abgestimmte Tailwind-500-Töne.
 *
 * Vorher lagen die Rollenfarben dreifach auseinander (Inline-`bg-purple/green`
 * in den Bilanzen, `ROLLEN_BG` grün/blau im Hub-Balken, `CHART_COLORS` violett/
 * emerald im Hub-Chart) → behoben, alles zieht jetzt von hier.
 */
export const DATENROLLE = {
  pv:                { hex: COLORS.solar,       bg: 'bg-amber-500' },   // PV-Erzeugung
  eigenverbrauch:    { hex: COLORS.consumption, bg: 'bg-violet-500' },  // = Direktverbrauch (genutzte PV)
  einspeisung:       { hex: COLORS.feedin,      bg: 'bg-emerald-500' }, // ins Netz abgegeben
  netzbezug:         { hex: COLORS.grid,        bg: 'bg-red-700' },     // aus dem Netz bezogen
  speicherLadung:    { hex: '#f97316',          bg: 'bg-orange-500' },  // in den Speicher
  speicherEntladung: { hex: COLORS.battery,     bg: 'bg-blue-500' },    // aus dem Speicher
  extern:            { hex: '#9ca3af',          bg: 'bg-gray-400' },    // externe Ladung
} as const

/** PV-Modul-Palette = Schattierungen der Solar-Farbe (alle Module sind PV) —
 *  bewusst KEINE kategorischen Fremdfarben, damit Module nicht mit den
 *  Verwendungs-Rollen (emerald/orange/violett) im selben Stapel-Chart kollidieren
 *  (Rainer/Gernot 2026-06-24: Westdach=Einspeisung, Süddach≈Speicherladung).
 *
 *  **Regel-Scope (Gernot 2026-06-24):** Amber-Schattierungen NUR dort, wo Module
 *  UND Rollen im selben Chart liegen (Komponenten-Hub PV-Verlauf). Eigenständige
 *  String-/Modul-Charts ohne Rollen (z. B. `PVStringVergleich` SOLL/IST pro
 *  String) behalten die distinkten {@link STRING_COLORS} — dort trennen bunte
 *  Töne mehrere Strings besser und es gibt keine Kollision. */
export const PV_MODUL_FARBEN = ['#b45309', '#f59e0b', '#fcd34d', '#fbbf24', '#78350f', '#fde68a']
export const PV_MODUL_BG = ['bg-amber-700', 'bg-amber-500', 'bg-amber-300', 'bg-amber-400', 'bg-amber-900', 'bg-amber-200']

/** Datenrollen → Tailwind-bg-Klasse für Aufteilungs-Segmente (VerteilungsBalken).
 *  Leitet aus {@link DATENROLLE} ab (keine Parallel-Definition mehr); WP-Roh-
 *  rollen (heizung/warmwasser) sind komponenten-eigene Identitäten. */
export const ROLLEN_BG = {
  pv: DATENROLLE.pv.bg,
  ev: DATENROLLE.eigenverbrauch.bg,
  einspeisung: DATENROLLE.einspeisung.bg,
  netz: DATENROLLE.netzbezug.bg,
  extern: DATENROLLE.extern.bg,
  heizung: 'bg-orange-500',    // WP-Heizwärme (Komponenten-Identität)
  warmwasser: 'bg-red-400',    // WP-Warmwasser
  ladung: DATENROLLE.speicherLadung.bg,
  entladung: DATENROLLE.speicherEntladung.bg,
} as const

/** Solar-Intensitäts-Rampe (Sparklines: schwach → stark). */
export const SOLAR_INTENSITAET = ['#fde68a', '#fbbf24', '#f59e0b']

/** Zusatz-/Extra-Serien (dynamische Kategorien jenseits der festen Rollen). */
export const EXTRA_SERIEN_FARBEN = ['#8b5cf6', '#06b6d4', '#84cc16', '#f43f5e', '#fb923c', '#a78bfa']

// ─── Tooltip-Grundfarben (Vorgriff auf den Tooltip-Kanon, Paket P3) ─────────

export const TOOLTIP_FARBEN = {
  bg: '#111827',      // gray-900 — Tooltip-Kanon (P3, = FormelTooltip/ChartTooltip-Fläche)
  text: '#ffffff',
}

/**
 * Hover-/Cursor-Overlay für Charts (S3/S4, Triage 2026-06-24) — die EINE
 * app-weite Hover-Mechanik. Recharts zeichnet `cursor.fill` NUR bei Bar-/
 * Composed-Charts als Highlight-Rechteck (Linien/Flächen behalten ihren
 * Default-Cursor). Mittleres Grau mit NIEDRIGER Alpha → dezent in hell UND
 * dunkel (Dark nicht mehr grell, S3), das **Raster scheint durch** und der
 * **Balken bleibt deckend** (S4: nicht der Balken wird transparent, sondern der
 * Hintergrund). Hebt sich klar von soliden „Verlust"-Grau-Balken ab (S5).
 * Als `cursor={CHART_HOVER_CURSOR}` an `<Tooltip>` setzen.
 */
export const CHART_HOVER_CURSOR = { fill: 'rgba(107, 114, 128, 0.14)' } // gray-500 @ 14 %

/**
 * Strich-Muster für **Prognose-/SOLL-Serien** in Charts (Gernot 2026-06-24) —
 * die EINE app-weite Konvention: „Prognose/SOLL = gestrichelt, IST/gemessen =
 * durchgezogen". Auf `strokeDasharray` von Linien, Flächen-Rändern UND Balken-
 * Rändern setzen (z. B. PVGIS-Prognose, OpenMeteo/Solcast/eedc-Prognose, SOLL).
 * Ersetzt die früheren ad-hoc-Muster `"4 2"`/`"5 3"`.
 */
export const PROGNOSE_DASH = '5 3'

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

/**
 * Tailwind-Text-Klassen-Zwilling zu {@link TYP_COLORS} — für Icon-Farben in
 * Komponenten/Seiten (dort sind Inline-Hex verboten, `check:design`). Jeder
 * Eintrag ist die `-500`-Klasse desselben Farbtons wie der Hex daneben; beide
 * Maps zusammen pflegen (eine Farb-Rolle, zwei Ausgabeformen — wie `COLORS` ↔
 * `COLOR_CLASSES`). Konsumiert von `komponentenStyle.KOMPONENTEN_IDENTITAET`.
 */
export const TYP_TEXT_CLASS: Record<string, string> = {
  'pv-module': 'text-amber-500',     // #f59e0b
  'wechselrichter': 'text-yellow-500', // #eab308
  'speicher': 'text-blue-500',       // #3b82f6
  'e-auto': 'text-violet-500',       // #8b5cf6
  'wallbox': 'text-cyan-500',        // #06b6d4
  'waermepumpe': 'text-red-500',     // #ef4444
  'balkonkraftwerk': 'text-emerald-500', // #10b981
  'sonstiges': 'text-gray-500',      // #6b7280
  'pv-system': 'text-orange-500',    // #f97316
}
