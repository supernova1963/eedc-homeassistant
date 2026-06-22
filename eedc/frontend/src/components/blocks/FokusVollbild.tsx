/**
 * FokusVollbild — das EINE Fokus/Vollbild-Overlay (IA-V4, Regel 0a).
 *
 * Geteilte SoT für „bildschirmfüllend" (KONZEPT-IA-V4 Z.76): genutzt von der
 * {@link BlockShell} (⤢ je Block) UND der {@link FokusKachel} (⤢ je Karte ohne
 * Block-Stack). Ein Verhalten + ein Look app-weit — keine zweite Kopie.
 */
import type { ReactNode } from 'react'
import { Minimize2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export function FokusVollbild({ titel, icon: Icon, farbe, onClose, children }: {
  titel: string
  icon?: LucideIcon
  farbe?: string
  onClose: () => void
  children: ReactNode
}) {
  return (
    <div className="fixed inset-0 z-50 bg-white dark:bg-gray-900 flex flex-col p-3 sm:p-6 gap-3 overflow-auto">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
          {Icon && <Icon className={`h-5 w-5 ${farbe ?? ''}`} />}
          {titel}
          <span className="text-xs font-normal text-gray-400 dark:text-gray-500">Fokus / Vollbild</span>
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="min-h-[44px] flex items-center gap-2 px-3 rounded-lg text-sm font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
        >
          <Minimize2 className="h-4 w-4" /> Zurück
        </button>
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  )
}
