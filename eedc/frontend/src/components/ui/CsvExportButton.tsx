/**
 * CsvExportButton — die EINE CSV-/Export-Schaltfläche (D13-10-Vertrag, Gernot
 * Variante A, final; D14-18-Folge).
 *
 * Toolbar-Kontext (Default): **immer Icon + Wort** — `≥1024` „CSV-Export",
 * `<1024` „CSV". Das Label fällt NIE ganz weg: natives `title` ist auf Touch
 * unsichtbar, ein Tap-Tooltip kollidiert auf Aktions-Buttons mit der Aktion →
 * Mobile-Klarheit gibt es nur über sichtbaren Text (Triage Runde 13/14).
 *
 * Header-Kontext (`variante="header"`, D13-15): Export im Block-Kopf =
 * Icon-Button im Stil des rechten Control-Clusters (`↑↓⤢⌄`), nie freistehend
 * in eigener Zeile. ⚠️ Nach D14-18 (detLAN: Icon-only liest sich als „CSV
 * fehlt") nur noch für Blöcke mit prominenter Primär-Aktion gedacht — im
 * Zweifel gilt der Toolbar-Kontext (Icon + Wort). Aktuell ohne Nutzer.
 */
import { Download } from 'lucide-react'
import Button from './Button'

export function CsvExportButton({
  onClick,
  label = 'CSV-Export',
  title,
  variante = 'toolbar',
  className = '',
}: {
  onClick: () => void
  /** Langform ab `lg` (Default „CSV-Export"); unter `lg` steht immer „CSV". */
  label?: string
  /** Desktop-/a11y-Tooltip; Default = Langform. */
  title?: string
  variante?: 'toolbar' | 'header'
  className?: string
}) {
  const titel = title ?? label
  if (variante === 'header') {
    return (
      <button
        type="button"
        onClick={onClick}
        title={titel}
        aria-label={titel}
        className={`p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 ${className}`.trim()}
      >
        <Download className="h-4 w-4" />
      </button>
    )
  }
  return (
    <Button variant="secondary" size="sm" onClick={onClick} title={titel} className={className}>
      <Download className="h-4 w-4 mr-1.5" />
      <span className="lg:hidden">CSV</span>
      <span className="hidden lg:inline">{label}</span>
    </Button>
  )
}

export default CsvExportButton
