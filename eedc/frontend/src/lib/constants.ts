/**
 * Zentrale Konstanten für das gesamte Frontend.
 *
 * Monatsnamen, Investitionstyp-Labels und andere wiederverwendbare
 * Definitionen, die in vielen Seiten dupliziert waren.
 */

// ─── Monatsnamen ─────────────────────────────────────────────────────────────

/** Kurze Monatsnamen, 1-basiert (Index 0 = leer). Für Chart-Labels, Tabellen. */
export const MONAT_KURZ = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

/** Volle Monatsnamen, 1-basiert (Index 0 = leer). Für Überschriften, Formulare. */
export const MONAT_NAMEN = ['', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

// ─── Investitionstyp-Labels ──────────────────────────────────────────────────

/** Lesbare Labels für Investitionstypen. */
export const TYP_LABELS: Record<string, string> = {
  'pv-module': 'PV-Module',
  'wechselrichter': 'Wechselrichter',
  'speicher': 'Speicher',
  'e-auto': 'E-Auto',
  'wallbox': 'Wallbox',
  'waermepumpe': 'Wärmepumpe',
  'balkonkraftwerk': 'Balkonkraftwerk',
  'sonstiges': 'Sonstiges',
  'pv-system': 'PV-System',
}

// ─── Sonstige Konstanten ─────────────────────────────────────────────────────

/** CO2-Emissionsfaktor Strommix Deutschland (kg CO2 pro kWh). */
export const CO2_FAKTOR_KG_KWH = 0.38
