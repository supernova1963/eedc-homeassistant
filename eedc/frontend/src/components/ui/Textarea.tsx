import { forwardRef, TextareaHTMLAttributes } from 'react'

/**
 * Textarea — Langtext-Control-SoT (Style-Guide Teil D, D1: „Langtext → Textarea").
 * Gleiche Feld-Anatomie wie {@link Input}: Label (+ Pflicht-`*`) · Hint · Fehler (rot).
 * Für Notizen/Beschreibungen; feste `rows` über das `rows`-Attribut.
 */
interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
  hint?: string
}

const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className = '', label, error, hint, id, ...props }, ref) => {
    const taId = id || props.name

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={taId} className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {label}
            {props.required && <span className="text-red-500 ml-1">*</span>}
          </label>
        )}
        <textarea
          ref={ref}
          id={taId}
          className={`
            w-full px-3 py-2 rounded-lg border
            bg-white dark:bg-gray-800
            text-gray-900 dark:text-gray-100
            placeholder-gray-400 dark:placeholder-gray-500
            focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent
            disabled:bg-gray-100 dark:disabled:bg-gray-700 disabled:cursor-not-allowed
            ${error ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'}
            ${className}
          `}
          {...props}
        />
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

Textarea.displayName = 'Textarea'

export default Textarea
