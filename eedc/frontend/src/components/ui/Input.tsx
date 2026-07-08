import { forwardRef, InputHTMLAttributes } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
  /**
   * Zusatz-Klassen für das Label — v. a. `md:min-h-[2.5rem]` in mehrspaltigen
   * Feld-Zeilen ohne Subgrid, damit ein umbrechendes Label die Ausrichtung nicht
   * bricht (D17-7). In dichten Rastern besser `denseRow` (per-Zeile automatisch).
   */
  labelClassName?: string
  /**
   * Dichte Raster-Zeile: Label + Feld als 2-Zeilen-**Subgrid** (`row-span-2`),
   * sodass die Label-Höhe sich PRO Raster-Zeile automatisch einstellt — einzeilig,
   * wenn alle Labels der Zeile kurz sind, zweizeilig nur dort, wo ein Titel umbricht
   * (D17-7, kein globales `min-h`). Voraussetzung: Eltern-Grid mit subgrid-fähigen
   * Zeilen (`grid-rows-subgrid`-tauglich). Hint wandert in den `title`-Tooltip.
   */
  denseRow?: boolean
}

// Feld-Basisklassen (ohne Rahmenfarbe — die hängt am Fehlerzustand).
const FELD_KLASSEN =
  "w-full px-3 py-2 rounded-lg border min-h-[42px] bg-white dark:bg-gray-800 " +
  "text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 " +
  "focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent " +
  "disabled:bg-gray-100 dark:disabled:bg-gray-700 disabled:cursor-not-allowed " +
  "[&[type='date']]:text-left [&::-webkit-datetime-edit]:text-left"

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className = '', label, error, hint, labelClassName = '', denseRow = false, id, ...props }, ref) => {
    const inputId = id || props.name
    const feldKlassen = `${FELD_KLASSEN} ${error ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'} ${className}`

    const feld = (
      <input
        ref={ref}
        id={inputId}
        {...props}
        className={feldKlassen}
        title={denseRow ? (hint ?? props.title) : props.title}
      />
    )

    const marker = props.required && <span className="text-red-500 ml-1">*</span>

    if (denseRow) {
      // Label sitzt am unteren Rand seiner (per Subgrid pro Zeile bemessenen) Spur,
      // damit kurze Labels direkt über dem Feld stehen und nicht „schweben".
      return (
        <div className="grid grid-rows-subgrid row-span-2 gap-y-1">
          {label && (
            <label htmlFor={inputId} className={`self-end block text-sm font-medium text-gray-700 dark:text-gray-300 ${labelClassName}`}>
              {label}
              {marker}
            </label>
          )}
          {feld}
        </div>
      )
    }

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={inputId} className={`block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 ${labelClassName}`}>
            {label}
            {marker}
          </label>
        )}
        {feld}
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

Input.displayName = 'Input'

export default Input
