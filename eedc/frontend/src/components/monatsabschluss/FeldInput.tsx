import { AlertTriangle, Info } from 'lucide-react'
import type { FeldStatus } from '../../api'
import { getQuelleLabel } from './helpers'

export default function FeldInput({
  feld,
  value,
  onChange,
  compact = false,
}: {
  feld: FeldStatus
  value: number | null | undefined
  onChange: (wert: number | null) => void
  compact?: boolean
}) {
  const hasWarnings = feld.warnungen.length > 0
  const hasVorschlaege = feld.vorschlaege.length > 0

  return (
    <div className={compact ? '' : 'space-y-2'}>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
        {feld.label}
        <span className="text-gray-400 ml-1">({feld.einheit})</span>
      </label>

      <div className="relative">
        <input
          type="number"
          step="0.01"
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value ? parseFloat(e.target.value) : null)}
          className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white ${
            hasWarnings
              ? 'border-amber-300 focus:border-amber-500'
              : 'border-gray-300'
          }`}
          placeholder={hasVorschlaege ? `Vorschlag: ${feld.vorschlaege[0].wert}` : ''}
        />

        {/* Vorschlag-Button */}
        {hasVorschlaege && value === null && (
          <button
            type="button"
            onClick={() => onChange(feld.vorschlaege[0].wert)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-primary-600 hover:text-primary-700 dark:text-primary-400"
          >
            Übernehmen
          </button>
        )}
      </div>

      {/* Vorschläge */}
      {hasVorschlaege && !compact && (
        <div className="flex flex-wrap gap-2 mt-1">
          {feld.vorschlaege.slice(0, 3).map((v, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => onChange(v.wert)}
              className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-600 dark:text-gray-300"
              title={v.beschreibung}
            >
              {v.wert} {feld.einheit}
              <span className="text-gray-400 ml-1">({getQuelleLabel(v.quelle)})</span>
            </button>
          ))}
        </div>
      )}

      {/* Warnungen */}
      {hasWarnings && (
        <div className="mt-1">
          {feld.warnungen.map((w, idx) => (
            <div
              key={idx}
              className={`flex items-center gap-1 text-xs ${
                w.schwere === 'error'
                  ? 'text-red-600 dark:text-red-400'
                  : w.schwere === 'warning'
                  ? 'text-amber-600 dark:text-amber-400'
                  : 'text-blue-600 dark:text-blue-400'
              }`}
            >
              {w.schwere === 'error' ? (
                <AlertTriangle className="w-3 h-3" />
              ) : w.schwere === 'warning' ? (
                <AlertTriangle className="w-3 h-3" />
              ) : (
                <Info className="w-3 h-3" />
              )}
              {w.meldung}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
