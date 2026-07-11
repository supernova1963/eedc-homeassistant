import { AlertTriangle, Info } from 'lucide-react'
import type { FeldStatus } from '../../api'
import Button from '../ui/Button'
import Input from '../ui/Input'
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
        <span className="text-gray-400 dark:text-gray-500 ml-1">({feld.einheit})</span>
      </label>

      {/* Eingabefeld + Übernehmen daneben — der Übernehmen-Button saß früher
          absolute-overlay im Input und überdeckte die Number-Spinner-Pfeile
          (#213 detLAN). Jetzt nebeneinander, Spinner bleiben bedienbar. */}
      {/* E3: Input-/Button-SoT — die Vorschlagswerte-Mechanik (Placeholder,
          Übernehmen, Vorschlags-Chips) bleibt 1:1 erhalten. */}
      <div className="flex items-stretch gap-2">
        <div className="flex-1 min-w-0">
          <Input
            type="number"
            step="0.01"
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value ? parseFloat(e.target.value) : null)}
            warnung={hasWarnings}
            aria-label={feld.label}
            placeholder={hasVorschlaege ? `Vorschlag: ${feld.vorschlaege[0].wert}` : ''}
          />
        </div>

        {/* Vorschlag-Übernehmen-Button — nur sichtbar wenn Wert leer ist */}
        {hasVorschlaege && value === null && (
          <Button
            type="button" variant="secondary" size="sm" className="flex-shrink-0"
            onClick={() => onChange(feld.vorschlaege[0].wert)}
          >
            Übernehmen
          </Button>
        )}
      </div>

      {/* Vorschläge */}
      {hasVorschlaege && !compact && (
        <div className="flex flex-wrap gap-2 mt-1">
          {feld.vorschlaege.slice(0, 3).map((v, idx) => (
            <Button
              key={idx}
              type="button" variant="secondary" size="sm"
              onClick={() => onChange(v.wert)}
              title={v.beschreibung}
              className="text-xs"
            >
              {v.wert} {feld.einheit}
              <span className="text-gray-400 dark:text-gray-500 ml-1">({getQuelleLabel(v.quelle)})</span>
            </Button>
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
