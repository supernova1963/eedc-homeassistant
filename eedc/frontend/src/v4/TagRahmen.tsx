/**
 * TagRahmen — Sicht-Rahmen der Cockpit/Tag-Sicht. {@link TagHeader} ist das
 * Pendant zu {@link MonatHeader}: Titel (langes Datum) + Status-Badge
 * (heute/abgeschlossen) + Aktualisieren + Quellen-Provenance (`TagWerte.datenquelle`).
 */
import type { TagWerte } from '../api/energie_profil'
import { ReloadButton } from './ReloadButton'
// R3b S7: Provenance-Labels + Wochentage aus der SoT (vorher 3 gedriftete lokale Kopien).
import { DATENQUELLE_LABELS, WT_LANG } from '../lib/constants'
import { LAUFEND_ZUSTAND } from '../lib'

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
  const quelle = tag?.datenquelle ? (DATENQUELLE_LABELS[tag.datenquelle] ?? tag.datenquelle) : null
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2.5">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">{langesDatum(datum)}</h1>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          laufend
            ? LAUFEND_ZUSTAND.badge
            : 'bg-gray-50 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
        }`}>
          {laufend ? 'heute' : 'abgeschlossen'}
        </span>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {onReload && <ReloadButton onClick={onReload} loading={!!reloading} />}
        {quelle && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs text-gray-400 dark:text-gray-500">Quellen:</span>
            <span className="text-[10px] leading-tight px-1.5 py-0.5 rounded-full font-medium bg-gray-50 text-gray-700 dark:bg-gray-700 dark:text-gray-300">
              {quelle}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
