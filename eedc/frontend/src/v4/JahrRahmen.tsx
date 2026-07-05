/**
 * JahrRahmen — Sicht-Rahmen der Cockpit/Jahr-Sicht. {@link JahrHeader} ist das
 * Pendant zu {@link MonatHeader}: Titel (Jahr) + Status-Badge (läuft/abgeschlossen)
 * + Aktualisieren + Quellen-Provenance (aus `feld_quellen` der aggregierten Monate).
 */
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { ReloadButton } from './ReloadButton'

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
            ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300'
            : 'bg-gray-50 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
        }`}>
          {laufend ? 'läuft' : 'abgeschlossen'}
        </span>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {laufend && onReload && <ReloadButton onClick={onReload} loading={!!reloading} />}
        {quellen.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs text-gray-400 dark:text-gray-500">Quellen:</span>
            {quellen.map((q) => (
              <span key={q} className="text-[10px] leading-tight px-1.5 py-0.5 rounded-full font-medium bg-gray-50 text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                {q}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
