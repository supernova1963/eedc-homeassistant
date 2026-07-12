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
 *
 * `statusSlot` + `ebene` (Monatsabschluss-V4 §6.7): dieselbe Sektion dient als
 * rekursiver **Ampel-Block** — `statusSlot` trägt das Rollup-Badge rechts im Kopf,
 * `ebene='typ'` = primäre Rahmung (Shading, fett), `ebene='geraet'` = untergeordnet
 * (flach, kein Box-in-Box, Teil-D S4). KEINE zweite Block-Art
 * ([[feedback_kpicard_drei_versionen]]).
 */
interface FormSectionProps {
  title: ReactNode
  description?: ReactNode
  /** Optionales Sektions-Icon (z. B. Typ-Kodierung PV/Speicher/E-Auto). */
  icon?: ElementType
  /** Tailwind-Textfarbe fürs Icon (z. B. „text-yellow-500"). */
  iconColor?: string
  /** 'erweitert' = aufklappbar, standardmäßig eingeklappt (optionale Felder). */
  variant?: 'standard' | 'erweitert'
  /** Startzustand aufklappbarer Sektionen (Default: erweitert=zu, standard=offen). */
  defaultOpen?: boolean
  /** Rechts im Kopf ausgerichteter Inhalt (z. B. Rollup-Ampel-Badge, §6.7). */
  statusSlot?: ReactNode
  /** Gewichtungs-Ebene rekursiver Ampel-Blöcke (§6.7): 'geraet' = flach/untergeordnet. */
  ebene?: 'typ' | 'geraet'
  children: ReactNode
  className?: string
}

const SHADING =
  'rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-800/40'

export default function FormSection({
  title, description, icon: Icon, iconColor = '', variant = 'standard', defaultOpen,
  statusSlot, ebene = 'typ', children, className = '',
}: FormSectionProps) {
  const collapsible = variant === 'erweitert'
  const [open, setOpen] = useState<boolean>(defaultOpen ?? !collapsible)
  const flach = ebene === 'geraet'

  if (collapsible) {
    // Flach (Geräte-Ebene): kein Shading-Box, leichteres Gewicht, kein Box-in-Box.
    const rahmen = flach ? '' : `${SHADING} `
    const kopf = flach
      ? 'px-2 py-2 text-sm font-medium text-gray-700 dark:text-gray-300'
      : 'px-4 py-3 text-sm font-semibold text-gray-900 dark:text-white'
    const inhalt = flach ? 'px-2 pb-3' : 'px-4 pb-4'
    return (
      <section className={`${rahmen}${className}`}>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className={`flex w-full items-center justify-between gap-2 text-left hover:text-primary-600 dark:hover:text-primary-400 ${kopf}`}
        >
          <span className="flex items-center gap-2 min-w-0">
            <ChevronDown
              className={`h-4 w-4 flex-shrink-0 text-gray-400 dark:text-gray-500 transition-transform ${open ? 'rotate-0' : '-rotate-90'}`}
            />
            {Icon && <Icon className={`h-4 w-4 flex-shrink-0 ${iconColor}`} />}
            <span className="truncate">{title}</span>
          </span>
          {statusSlot && <span className="flex-shrink-0">{statusSlot}</span>}
        </button>
        {open && (
          <div className={inhalt}>
            {description && <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">{description}</p>}
            {children}
          </div>
        )}
      </section>
    )
  }

  return (
    <section className={`${flach ? '' : SHADING + ' p-4'} ${className}`}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white min-w-0">
          {Icon && <Icon className={`h-4 w-4 flex-shrink-0 ${iconColor}`} />}
          <span className="truncate">{title}</span>
        </h3>
        {statusSlot && <span className="flex-shrink-0">{statusSlot}</span>}
      </div>
      {description && <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{description}</p>}
      <div className="mt-3">{children}</div>
    </section>
  )
}
