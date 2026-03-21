/**
 * Gemeinsame Recharts-Konfiguration.
 *
 * Standard-Margins, Achsen-Defaults und Hilfs-Konstanten
 * für konsistente Charts im gesamten Frontend.
 */

/** Standard-Margins für Charts mit Achsenbeschriftungen. */
export const CHART_MARGIN = { top: 10, right: 30, left: 0, bottom: 5 }

/** Kompakte Margins (für Sparklines, eingebettete Charts). */
export const CHART_MARGIN_COMPACT = { top: 0, right: 0, bottom: 0, left: 0 }

/** Margins mit reduzierter linker Achse (negative Y-Labels). */
export const CHART_MARGIN_NARROW_LEFT = { top: 5, right: 5, left: -20, bottom: 0 }
