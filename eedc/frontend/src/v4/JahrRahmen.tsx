/**
 * JahrRahmen — Sicht-Rahmen der Cockpit/Jahr-Sicht. {@link JahrHeader} ist das
 * Pendant zu {@link MonatHeader}: Titel (Jahr) + Status-Badge (läuft/abgeschlossen)
 * + Aktualisieren + Quellen-Provenance (aus `feld_quellen` der aggregierten Monate).
 */
import { RefreshCw } from 'lucide-react'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

// Roh-Enum → Label (Roh-Werte gehören nie in die UI, [[feedback_typ_labels_pattern]]).
const QUELLE_LABEL: Record<string, string> = {
  ha_sensor: 'HA', mqtt: 'MQTT', connector: 'Connector',
  scheduler: 'gespeichert', monatsabschluss: 'Abschluss', manuell: 'manuell',
}

function provenanceQuellen(feldQuellen: AktuellerMonatResponse['feld_quellen']): string[] {
  if (!feldQuellen) return []
  const set = new Set<string>()
  for (const info of Object.values(feldQuellen)) {
    if (info?.quelle) set.add(QUELLE_LABEL[info.quelle] ?? info.quelle)
  }
  return [...set]
}

export function JahrHeader({ jahr, laufend, d, onReload, reloading }: {
  jahr: number
  laufend: boolean
  d: AktuellerMonatResponse | null
  onReload?: () => void
  reloading?: boolean
}) {
  const quellen = d ? provenanceQuellen(d.feld_quellen) : []
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2.5">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">{jahr}</h1>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          laufend
            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
            : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
        }`}>
          {laufend ? 'läuft' : 'abgeschlossen'}
        </span>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {laufend && onReload && (
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
        {quellen.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs text-gray-400 dark:text-gray-500">Quellen:</span>
            {quellen.map((q) => (
              <span key={q} className="text-[10px] leading-tight px-1.5 py-0.5 rounded font-medium bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                {q}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
