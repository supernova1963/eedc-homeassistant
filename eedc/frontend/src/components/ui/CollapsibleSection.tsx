import { ReactNode, useState, useEffect } from 'react'
import { ChevronDown } from 'lucide-react'

interface Props {
  /** Eindeutiger Schlüssel für die LocalStorage-Persistenz des Offen/Zu-Status. */
  storageKey: string
  title: string
  /** Optionale Aktion-Buttons rechts neben dem Titel (außerhalb des Toggle-Bereichs). */
  action?: ReactNode
  defaultOpen?: boolean
  children: ReactNode
  className?: string
}

/**
 * Aufklappbare Card-Sektion. Status persistiert pro `storageKey` in localStorage,
 * sodass der User seine Anordnung beim nächsten Besuch wiederfindet.
 */
export default function CollapsibleSection({
  storageKey,
  title,
  action,
  defaultOpen = true,
  children,
  className = '',
}: Props) {
  const fullKey = `eedc-collapse-${storageKey}`
  const [open, setOpen] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem(fullKey)
      if (stored === 'open') return true
      if (stored === 'closed') return false
    } catch { /* ignore */ }
    return defaultOpen
  })

  useEffect(() => {
    try { localStorage.setItem(fullKey, open ? 'open' : 'closed') } catch { /* ignore */ }
  }, [fullKey, open])

  return (
    <div className={`bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 ${className}`}>
      <div className="flex items-center justify-between gap-2 px-6 py-3">
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          aria-expanded={open}
          className="flex items-center gap-2 flex-1 text-left text-sm font-semibold text-gray-900 dark:text-white hover:text-primary-600 dark:hover:text-primary-400"
        >
          <ChevronDown
            className={`h-4 w-4 text-gray-400 transition-transform ${open ? 'rotate-0' : '-rotate-90'}`}
          />
          {title}
        </button>
        {action && <div className="flex items-center">{action}</div>}
      </div>
      {open && <div className="px-6 pb-6">{children}</div>}
    </div>
  )
}
