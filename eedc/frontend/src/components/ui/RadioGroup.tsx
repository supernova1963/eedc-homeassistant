import { ReactNode } from 'react'

/**
 * RadioGroup — Auswahl 1-aus-wenig als vertikale Liste mit Beschreibung
 * (Style-Guide Teil D, D1: „Auswahl 2–5 → RadioGroup = Liste mit Beschreibung").
 *
 * Für Fälle, in denen jede Option einen erklärenden Text trägt (z. B. Tarif-
 * Verwendung Standard/WP/Wallbox). Kompakte, gleichrangige Umschalter ohne
 * Beschreibung nutzen weiterhin {@link SegmentControl}.
 *
 * Feld-Anatomie wie {@link Input}: Label (+ Pflicht-`*`) · Hint · Fehler (rot).
 */
interface RadioOption<K extends string> {
  value: K
  label: string
  description?: ReactNode
}

export default function RadioGroup<K extends string>({
  label, options, value, onChange, name, required, error, hint,
}: {
  label?: string
  options: readonly RadioOption<K>[]
  value: string
  onChange: (value: K) => void
  name: string
  required?: boolean
  error?: string
  hint?: string
}) {
  return (
    <fieldset className="w-full">
      {label && (
        <legend className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          {label}
          {required && <span className="text-red-500 ml-1">*</span>}
        </legend>
      )}
      <div className="space-y-2">
        {options.map((o) => {
          const selected = value === o.value
          return (
            <label
              key={o.value}
              className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${
                selected
                  ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                  : 'border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700/50'
              }`}
            >
              <input
                type="radio"
                name={name}
                value={o.value}
                checked={selected}
                onChange={() => onChange(o.value)}
                className="mt-0.5 h-4 w-4 accent-primary-600"
              />
              <span className="min-w-0">
                <span className="block text-sm font-medium text-gray-900 dark:text-gray-100">{o.label}</span>
                {o.description && (
                  <span className="block text-xs text-gray-500 dark:text-gray-400 mt-0.5">{o.description}</span>
                )}
              </span>
            </label>
          )
        })}
      </div>
      {hint && !error && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</p>}
      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
    </fieldset>
  )
}
