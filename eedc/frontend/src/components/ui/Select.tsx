import { forwardRef, SelectHTMLAttributes } from 'react'
import { STEUER_H } from '../../lib/komponentenStyle'

export interface SelectOption {
  value: string
  label: string
  /** Nicht wählbar (z. B. „nicht verfügbar") — bleibt sichtbar (D1). */
  disabled?: boolean
}

/** Optionsgruppe (`<optgroup>`) für Auswahl >5 mit Kategorien (D1). */
export interface SelectOptgroup {
  label: string
  options: SelectOption[]
}

export type SelectItem = SelectOption | SelectOptgroup

const istGruppe = (item: SelectItem): item is SelectOptgroup =>
  (item as SelectOptgroup).options !== undefined

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  hint?: string
  /** Flache Optionen und/oder Optionsgruppen (gemischt erlaubt). */
  options: SelectItem[]
  placeholder?: string
  /** Kompakte Breite (w-auto statt w-full) — für Header-Bereiche */
  compact?: boolean
  /**
   * 32-px-Steuerleisten-Variante (B15 dritte Höhenklasse `STEUER_H`) für
   * Filter-/Toolbar-Leisten — Rand wie die Toolbar-Familie (SegmentControl:
   * gray-200/700), impliziert `compact`. Formulare/Wizards bleiben bei 42 px.
   */
  steuer?: boolean
}

const renderOption = (o: SelectOption) => (
  <option key={o.value} value={o.value} disabled={o.disabled}>
    {o.label}
  </option>
)

const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className = '', label, error, hint, options, placeholder, compact, steuer, id, ...props }, ref) => {
    const selectId = id || props.name

    return (
      <div className={compact || steuer ? 'shrink-0' : 'w-full'}>
        {label && (
          <label htmlFor={selectId} className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {label}
            {props.required && <span className="text-red-500 ml-1">*</span>}
          </label>
        )}
        <select
          ref={ref}
          id={selectId}
          className={`
            ${steuer
              ? `w-auto px-2 py-0 ${STEUER_H} text-sm rounded-lg border`
              : `${compact ? 'w-auto' : 'w-full'} px-3 py-2 rounded-lg border min-h-[42px] leading-6`}
            bg-white dark:bg-gray-800
            text-gray-900 dark:text-gray-100
            focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent
            disabled:bg-gray-100 dark:disabled:bg-gray-700 disabled:cursor-not-allowed
            ${error ? 'border-red-500' : steuer ? 'border-gray-200 dark:border-gray-700' : 'border-gray-300 dark:border-gray-600'}
            ${className}
          `}
          {...props}
        >
          {placeholder && (
            <option value="">{placeholder}</option>
          )}
          {options.map((item) =>
            istGruppe(item) ? (
              <optgroup key={item.label} label={item.label}>
                {item.options.map(renderOption)}
              </optgroup>
            ) : (
              renderOption(item)
            )
          )}
        </select>
        {hint && !error && (
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</p>
        )}
        {error && (
          <p className="mt-1 text-xs text-red-500">{error}</p>
        )}
      </div>
    )
  }
)

Select.displayName = 'Select'

export default Select
