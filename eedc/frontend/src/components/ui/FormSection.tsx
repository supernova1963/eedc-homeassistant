import { ElementType, ReactNode, useState } from 'react'
import { ChevronDown } from 'lucide-react'

/**
 * FormSection — thematische Formular-Sektion (Style-Guide Teil D, S1/S2).
 *
 * Einheitliches Sektions-Shading (heilt D17-10 „Shading uneinheitlich") statt
 * loser `<h3>`-Überschriften. `variant="erweitert"` klappt optionale/Experten-
 * Felder ein (S2) über die bestehende Chevron-Klapp-Mechanik — kein neuer
 * „Experten"-Schalter ([[feedback_bestehende_mechanik_nutzen_nicht_erfinden]]).
 * Kern-/Pflichtfelder bleiben in `variant="standard"` immer sichtbar.
 */
interface FormSectionProps {
  title: string
  description?: ReactNode
  /** Optionales Sektions-Icon (z. B. Typ-Kodierung PV/Speicher/E-Auto). */
  icon?: ElementType
  /** Tailwind-Textfarbe fürs Icon (z. B. „text-yellow-500"). */
  iconColor?: string
  /** 'erweitert' = aufklappbar, standardmäßig eingeklappt (optionale Felder). */
  variant?: 'standard' | 'erweitert'
  /** Startzustand aufklappbarer Sektionen (Default: erweitert=zu, standard=offen). */
  defaultOpen?: boolean
  children: ReactNode
  className?: string
}

const SHADING =
  'rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-800/40'

export default function FormSection({
  title, description, icon: Icon, iconColor = '', variant = 'standard', defaultOpen, children, className = '',
}: FormSectionProps) {
  const collapsible = variant === 'erweitert'
  const [open, setOpen] = useState<boolean>(defaultOpen ?? !collapsible)

  if (collapsible) {
    return (
      <section className={`${SHADING} ${className}`}>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-semibold text-gray-900 dark:text-white hover:text-primary-600 dark:hover:text-primary-400"
        >
          <ChevronDown
            className={`h-4 w-4 text-gray-400 dark:text-gray-500 transition-transform ${open ? 'rotate-0' : '-rotate-90'}`}
          />
          {Icon && <Icon className={`h-4 w-4 ${iconColor}`} />}
          {title}
        </button>
        {open && (
          <div className="px-4 pb-4">
            {description && <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">{description}</p>}
            {children}
          </div>
        )}
      </section>
    )
  }

  return (
    <section className={`${SHADING} p-4 ${className}`}>
      <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
        {Icon && <Icon className={`h-4 w-4 ${iconColor}`} />}
        {title}
      </h3>
      {description && <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{description}</p>}
      <div className="mt-3">{children}</div>
    </section>
  )
}
