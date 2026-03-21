/**
 * Formatierungs-Utilities für Zahlen, Einheiten und Währungen.
 *
 * Ersetzt die ~65 verstreuten toFixed/toLocaleString-Aufrufe
 * durch konsistente, wiederverwendbare Funktionen.
 */

const DE = 'de-DE'

/** Formatiert kWh-Werte: "1.234,5 kWh" oder "12,3 kWh" */
export function formatKWh(value: number | null | undefined, decimals = 1): string {
  if (value == null) return '—'
  return `${value.toLocaleString(DE, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })} kWh`
}

/** Formatiert Watt-Werte: "1.234 W" oder "3,45 kW" */
export function formatWatt(value: number | null | undefined, decimals = 0): string {
  if (value == null) return '—'
  return `${value.toLocaleString(DE, { maximumFractionDigits: decimals })} W`
}

/** Formatiert kW-Werte: "3,45 kW" */
export function formatKW(value: number | null | undefined, decimals = 2): string {
  if (value == null) return '—'
  return `${value.toLocaleString(DE, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })} kW`
}

/** Formatiert Euro-Beträge: "12,34 €" oder "1.234,56 €" */
export function formatEuro(value: number | null | undefined, decimals = 2): string {
  if (value == null) return '—'
  return `${value.toLocaleString(DE, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })} €`
}

/** Formatiert Cent-Beträge: "29,5 ct/kWh" */
export function formatCentKWh(value: number | null | undefined, decimals = 1): string {
  if (value == null) return '—'
  return `${value.toLocaleString(DE, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })} ct/kWh`
}

/** Formatiert Prozentwerte: "94,2 %" */
export function formatPercent(value: number | null | undefined, decimals = 1): string {
  if (value == null) return '—'
  return `${value.toLocaleString(DE, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })} %`
}

/** Formatiert CO2-Werte: "1.234 kg" */
export function formatCO2(value: number | null | undefined, decimals = 0): string {
  if (value == null) return '—'
  return `${value.toLocaleString(DE, { maximumFractionDigits: decimals })} kg`
}

/** Formatiert eine Zahl mit deutscher Lokalisierung (ohne Einheit). */
export function formatNumber(value: number | null | undefined, decimals = 1): string {
  if (value == null) return '—'
  return value.toLocaleString(DE, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}
