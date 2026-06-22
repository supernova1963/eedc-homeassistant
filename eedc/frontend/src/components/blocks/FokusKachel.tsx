/**
 * FokusKachel — Karte mit Fokus/Vollbild-Schalter (⤢), ohne Block-Stack-Beiwerk
 * (kein Einklappen/Sortieren). Für IST-treue Sicht-Layouts wie Cockpit/Live, die
 * NICHT die {@link BlockShell} nutzen, aber dieselbe Fokus-Affordanz haben sollen
 * (Gernot 2026-06-22: durchgängig je Karte). Nutzt dasselbe {@link FokusVollbild}
 * wie die BlockShell → ein Fokus-Verhalten app-weit (Regel 0a).
 *
 * Der Karten-Titel erscheint per Default NUR im Vollbild-Header; im Normalzustand
 * trägt der Inhalt meist seine eigene Überschrift (`zeigeTitel` aktiviert ihn
 * zusätzlich in der Kopfzeile der Karte).
 */
import { useState, type ReactNode } from 'react'
import { Maximize2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { FokusVollbild } from './FokusVollbild'

export function FokusKachel({ titel, icon: Icon, farbe, className = '', kompakt = false, zeigeTitel = false, children }: {
  titel: string
  icon?: LucideIcon
  farbe?: string
  className?: string
  /** Weniger Padding (für schmale Sidebar-Sektionen). */
  kompakt?: boolean
  /** Titel auch in der Karten-Kopfzeile zeigen (sonst nur im Vollbild). */
  zeigeTitel?: boolean
  children: ReactNode
}) {
  const [fokus, setFokus] = useState(false)
  return (
    <>
      {fokus && (
        <FokusVollbild titel={titel} icon={Icon} farbe={farbe} onClose={() => setFokus(false)}>
          {children}
        </FokusVollbild>
      )}
      <div className={`relative bg-white dark:bg-gray-800 rounded-lg shadow ${kompakt ? 'p-3' : 'p-4 sm:p-6'} ${className}`}>
        {/* ⤢ sitzt absolut oben rechts — in der Titelzeile, keine eigene Leerzeile.
            (Energiefluss bringt sein ⤢ über `kopfAktion` selbst mit.) */}
        <button
          type="button"
          onClick={() => setFokus(true)}
          aria-label={`${titel}: Fokus / Vollbild`}
          className="absolute top-2 right-2 z-10 p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700/50"
        >
          <Maximize2 className="h-4 w-4" />
        </button>
        {zeigeTitel && (
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 pr-8 flex items-center gap-2">
            {Icon && <Icon className={`h-4 w-4 ${farbe ?? 'text-gray-400 dark:text-gray-500'}`} />}
            {titel}
          </h3>
        )}
        {/* Inhalt liegt im Fokus im Overlay → hier nicht doppelt rendern. */}
        {!fokus && children}
      </div>
    </>
  )
}
