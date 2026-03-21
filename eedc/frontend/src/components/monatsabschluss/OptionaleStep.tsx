import { FileText } from 'lucide-react'
import type { FeldStatus } from '../../api'

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
        Sonstiges
      </h2>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Optionale Eingaben für diesen Monat - können auch leer bleiben.
      </p>

      <div className="space-y-4">
        {felder.map(feld => (
          <div key={feld.feld} className="space-y-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {feld.label}
              {feld.einheit && <span className="text-gray-400 ml-1">({feld.einheit})</span>}
            </label>

            {feld.typ === 'text' ? (
              <textarea
                value={(values[feld.feld] as string) || ''}
                onChange={(e) => onChange(feld.feld, e.target.value || null)}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                placeholder={feld.label}
              />
            ) : (
              <input
                type="number"
                step="0.01"
                value={values[feld.feld] ?? ''}
                onChange={(e) => onChange(feld.feld, e.target.value ? parseFloat(e.target.value) : null)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                placeholder={feld.label}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
