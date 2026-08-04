/**
 * JahrRahmen — Sicht-Rahmen der Cockpit/Jahr-Sicht. {@link JahrHeader} ist das
 * Pendant zu {@link MonatHeader}: Titel (Jahr) + Status-Badge (läuft/abgeschlossen)
 * + Aktualisieren + Quellen-Provenance (aus `feld_quellen` der aggregierten Monate).
 */
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { ReloadButton } from './ReloadButton'
import { provenanzQuellen, ProvenanzQuellenZeile } from './ProvenanzQuellen'
import { LAUFEND_ZUSTAND } from '../lib'

export function JahrHeader({ jahr, laufend, d, onReload, reloading }: {
  jahr: number
  laufend: boolean
  d: AktuellerMonatResponse | null
  onReload?: () => void
  reloading?: boolean
}) {
  // #360/E3 bewusst OHNE Monatskontext: `JahrAggregat` faltet zwölf Monate zu
  // EINER Badge-Liste. Ein Connector-Zeitraum je Quelle wäre hier entweder falsch
  // (welcher Monat?) oder eine Liste von zwölf — die Teilabdeckung gehört in die
  // Monats-Sicht, wo sie zu genau einem Wert gehört.
  const quellen = d ? provenanzQuellen(d.feld_quellen) : []
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2.5">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">{jahr}</h1>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          laufend
            ? LAUFEND_ZUSTAND.badge
            : 'bg-gray-50 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
        }`}>
          {laufend ? 'läuft' : 'abgeschlossen'}
        </span>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {laufend && onReload && <ReloadButton onClick={onReload} loading={!!reloading} />}
        <ProvenanzQuellenZeile quellen={quellen} />
      </div>
    </div>
  )
}
