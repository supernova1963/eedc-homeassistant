import { FileText } from 'lucide-react'
import type { FeldStatus } from '../../api'
import Input from '../ui/Input'
import Textarea from '../ui/Textarea'

export default function OptionaleStep({
  felder,
  values,
  onChange,
}: {
  felder: FeldStatus[]
  values: Record<string, number | string | null>
  onChange: (feld: string, wert: number | string | null) => void
}) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
        <FileText className="w-5 h-5 text-gray-500" />
        Allgemein
      </h2>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Typ-übergreifende Eingaben für diesen Monat — können auch leer bleiben.
      </p>

      <div className="space-y-4">
        {felder.map(feld => (
          <div key={feld.feld} className="space-y-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {feld.label}
              {feld.einheit && <span className="text-gray-400 dark:text-gray-500 ml-1">({feld.einheit})</span>}
            </label>

            {/* E3: Textarea-/Input-SoT statt roher Controls. */}
            {feld.typ === 'text' ? (
              <Textarea
                value={(values[feld.feld] as string) || ''}
                onChange={(e) => onChange(feld.feld, e.target.value || null)}
                rows={3}
                aria-label={feld.label}
                placeholder={feld.label}
              />
            ) : (
              <Input
                type="number"
                step="0.01"
                value={values[feld.feld] ?? ''}
                onChange={(e) => onChange(feld.feld, e.target.value ? parseFloat(e.target.value) : null)}
                aria-label={feld.label}
                placeholder={feld.label}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
