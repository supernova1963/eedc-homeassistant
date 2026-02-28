/**
 * Export Utilities
 *
 * Funktionen für CSV und Excel Export.
 */

/**
 * Konvertiert Daten zu CSV-String
 */
export function toCSV(data: Record<string, unknown>[], headers?: Record<string, string>): string {
  if (data.length === 0) return ''

  const keys = Object.keys(data[0])
  const headerRow = headers
    ? keys.map(k => headers[k] || k).join(';')
    : keys.join(';')

  const rows = data.map(row =>
    keys.map(k => {
      const val = row[k]
      if (val === null || val === undefined) return ''
      if (typeof val === 'number') return val.toString().replace('.', ',') // Deutsche Notation
      if (typeof val === 'string' && (val.includes(';') || val.includes('"'))) {
        return `"${val.replace(/"/g, '""')}"`
      }
      return String(val)
    }).join(';')
  )

  return [headerRow, ...rows].join('\n')
}

/**
 * Lädt Daten als CSV-Datei herunter
 */
export function downloadCSV(data: Record<string, unknown>[], filename: string, headers?: Record<string, string>): void {
  const csv = toCSV(data, headers)
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' }) // BOM for Excel
  downloadBlob(blob, `${filename}.csv`)
}

/**
 * Lädt Daten als JSON-Datei herunter
 */
export function downloadJSON(data: unknown, filename: string): void {
  const json = JSON.stringify(data, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  downloadBlob(blob, `${filename}.json`)
}

/**
 * Hilfsfunktion zum Download eines Blobs
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * Formatiert ein Datum für Dateinamen
 */
export function formatDateForFilename(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

/**
 * Exportiert Array-Daten direkt als CSV mit gegebenen Headern
 */
export function exportToCSV(headers: string[], rows: (string | number)[][], filename: string): void {
  // Header
  const headerRow = headers.join(';')

  // Datenzeilen mit deutscher Notation
  const dataRows = rows.map(row =>
    row.map(val => {
      if (val === null || val === undefined || val === '') return ''
      if (typeof val === 'number') return val.toString().replace('.', ',')
      if (typeof val === 'string' && (val.includes(';') || val.includes('"'))) {
        return `"${val.replace(/"/g, '""')}"`
      }
      return String(val)
    }).join(';')
  )

  const csv = [headerRow, ...dataRows].join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' }) // BOM for Excel
  downloadBlob(blob, filename)
}
