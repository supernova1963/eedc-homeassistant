import { forwardRef, InputHTMLAttributes, ReactNode } from 'react'

/**
 * Checkbox — Einzel-Checkbox mit Label (Style-Guide Teil D, D1).
 * Für Mehrfachauswahl-Gruppen (N-aus-viele) — mehrere Checkboxen in einer Liste.
 * Einzelne Ja/Nein-Schalter nutzen `Switch`; 1-aus-wenig `RadioGroup`/`SegmentControl`.
 */
interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: ReactNode
  hint?: ReactNode
}

const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className = '', label, hint, id, ...props }, ref) => {
    const cbId = id || props.name

    return (
      <label
        htmlFor={cbId}
        className="flex items-start gap-2 cursor-pointer text-sm text-gray-700 dark:text-gray-300"
      >
        <input
          ref={ref}
          id={cbId}
          type="checkbox"
          className={`mt-0.5 h-4 w-4 rounded border-gray-300 dark:border-gray-600 accent-primary-600 ${className}`}
          {...props}
        />
        <span className="min-w-0">
          {label}
          {hint && <span className="block text-xs text-gray-500 dark:text-gray-400">{hint}</span>}
        </span>
      </label>
    )
  }
)

Checkbox.displayName = 'Checkbox'

export default Checkbox
