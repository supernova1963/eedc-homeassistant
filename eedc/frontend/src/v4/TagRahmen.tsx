/**
 * TagRahmen — Sicht-Rahmen der Cockpit/Tag-Sicht. {@link TagHeader} ist das
 * Pendant zu {@link MonatHeader}: Titel (langes Datum) + Status-Badge
 * (heute/abgeschlossen) + Aktualisieren + Quellen-Provenance (`TagWerte.datenquelle`).
 */
import { RefreshCw } from 'lucide-react'
import type { TagWerte } from '../api/energie_profil'

// Roh-Enum → Label (Roh-Werte gehören nie in die UI, [[feedback_typ_labels_pattern]]).
const QUELLE_LABEL: Record<string, string> = {
  ha_sensor: 'HA', mqtt: 'MQTT', connector: 'Connector',
  scheduler: 'gespeichert', monatsabschluss: 'Abschluss', manuell: 'manuell',
  wetter_prognose: 'Prognose',
}

const WT_LANG = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag']
function langesDatum(iso: string): string {
  const d = new Date(iso + 'T12:00:00')
  return `${WT_LANG[d.getDay()]}, ${d.toLocaleDateString('de-DE', { day: '2-digit', month: 'long', year: 'numeric' })}`
}

export function TagHeader({ datum, laufend, tag, onReload, reloading }: {
  datum: string
  laufend: boolean
  tag: TagWerte | null
  onReload?: () => void
  reloading?: boolean
}) {
  const quelle = tag?.datenquelle ? (QUELLE_LABEL[tag.datenquelle] ?? tag.datenquelle) : null
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2.5">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">{langesDatum(datum)}</h1>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          laufend
            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
            : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
        }`}>
          {laufend ? 'heute' : 'abgeschlossen'}
        </span>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {onReload && (
          <button
            type="button"
            onClick={onReload}
            disabled={reloading}
            className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${reloading ? 'animate-spin' : ''}`} />
            Aktualisieren
          </button>
        )}
        {quelle && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs text-gray-400 dark:text-gray-500">Quellen:</span>
            <span className="text-[10px] leading-tight px-1.5 py-0.5 rounded font-medium bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
              {quelle}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
