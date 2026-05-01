/**
 * SortableSection - Akkordeon-Sektion mit Auf-/Zuklappen + ↑↓-Sortierung
 *
 * Vorbild war die `Section`-Komponente in MonatsabschlussView (#175 detLAN).
 * Per `sectionId` adressierbar, Open/Close-Status pro Storage-Key persistent
 * (localStorage), Up/Down-Handler werden vom Container `<OrderedSections>`
 * injiziert.
 *
 * Bewusst page-agnostisch: keine Anlage-Reads, keine Page-spezifischen Hooks.
 */

import React, { useState } from 'react'
import { ArrowUp, ArrowDown, ChevronDown } from 'lucide-react'
import Card from './Card'

export interface SortableSectionProps {
  icon: React.ElementType
  title: string
  summary?: React.ReactNode
  children: React.ReactNode
  defaultOpen?: boolean
  color?: string
  /**
   * Storage-Schlüssel-Präfix für den Open/Close-Status. Empfehlung pro Cockpit
   * eindeutig, z.B. "cockpit-wp" → ergibt `cockpit-wp_section_<title>`.
   */
  storageKeyPrefix: string
  /** Stabile ID für Reorder-Logik. Pflicht wenn die Section sortierbar sein soll. */
  sectionId?: string
  /** Wird von `<OrderedSections>` injiziert — manuell setzen geht auch. */
  onMoveUp?: () => void
  /** Wird von `<OrderedSections>` injiziert — manuell setzen geht auch. */
  onMoveDown?: () => void
}

export default function SortableSection({
  icon: Icon, title, summary, children, defaultOpen = false,
  color = 'text-blue-500', storageKeyPrefix,
  onMoveUp, onMoveDown,
}: SortableSectionProps) {
  const storageKey = `${storageKeyPrefix}_section_${title}`
  const [open, setOpen] = useState(() => {
    try {
      const stored = localStorage.getItem(storageKey)
      return stored !== null ? stored === 'true' : defaultOpen
    } catch {
      return defaultOpen
    }
  })

  const toggle = () => {
    setOpen(o => {
      const next = !o
      try { localStorage.setItem(storageKey, String(next)) } catch { /* localStorage nicht verfügbar */ }
      return next
    })
  }
  const stop = (e: React.MouseEvent) => { e.stopPropagation(); e.preventDefault() }

  return (
    <Card className="!p-0 overflow-hidden">
      <button
        type="button"
        onClick={toggle}
        className="w-full flex items-center gap-3 px-4 py-3.5 text-left rounded-xl hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
      >
        <Icon className={`h-5 w-5 shrink-0 ${color}`} />
        <span className="font-semibold text-gray-900 dark:text-white text-sm">{title}</span>
        {summary !== undefined && (
          <span className="ml-2 text-sm text-gray-500 dark:text-gray-400 flex-1 min-w-0 truncate">{summary}</span>
        )}
        {(onMoveUp || onMoveDown) && (
          <span className="flex items-center gap-0.5 shrink-0 mr-1 border-r border-gray-200 dark:border-gray-700 pr-2" onClick={stop}>
            <button
              type="button"
              onClick={(e) => { stop(e); onMoveUp?.() }}
              disabled={!onMoveUp}
              className="p-1 rounded text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-20 disabled:cursor-not-allowed transition-colors"
              title="Sektion nach oben verschieben"
              aria-label="Sektion nach oben verschieben"
            >
              <ArrowUp className="h-3.5 w-3.5" strokeWidth={2.5} />
            </button>
            <button
              type="button"
              onClick={(e) => { stop(e); onMoveDown?.() }}
              disabled={!onMoveDown}
              className="p-1 rounded text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-20 disabled:cursor-not-allowed transition-colors"
              title="Sektion nach unten verschieben"
              aria-label="Sektion nach unten verschieben"
            >
              <ArrowDown className="h-3.5 w-3.5" strokeWidth={2.5} />
            </button>
          </span>
        )}
        <ChevronDown className={`h-4 w-4 text-gray-400 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="px-4 pb-5 pt-2 border-t border-gray-100 dark:border-gray-700">
          {children}
        </div>
      )}
    </Card>
  )
}

/**
 * Rendert SortableSection-Kinder in der durch `order` definierten Reihenfolge
 * und injiziert Up/Down-Handler. Kinder ohne sectionId oder mit unbekannter ID
 * werden am Ende angehängt.
 */
export function OrderedSections({
  order, onMove, children, className,
}: {
  order: string[]
  onMove: (id: string, dir: 'up' | 'down') => void
  children: React.ReactNode
  className?: string
}) {
  const all = React.Children.toArray(children).filter(React.isValidElement) as React.ReactElement<{ sectionId?: string }>[]
  const byId = new Map<string, React.ReactElement<{ sectionId?: string }>>()
  for (const child of all) {
    const id = child.props.sectionId
    if (id) byId.set(id, child)
  }
  const ordered: { id: string; el: React.ReactElement<{ sectionId?: string }> }[] = []
  for (const id of order) {
    const el = byId.get(id)
    if (el) ordered.push({ id, el })
  }
  for (const child of all) {
    const id = child.props.sectionId
    if (!id || !order.includes(id)) {
      ordered.push({ id: id || `_${ordered.length}`, el: child })
    }
  }
  return (
    <div className={className}>
      {ordered.map(({ id, el }, i) => React.cloneElement(el, {
        key: id,
        onMoveUp: i > 0 ? () => onMove(id, 'up') : undefined,
        onMoveDown: i < ordered.length - 1 ? () => onMove(id, 'down') : undefined,
      } as Partial<SortableSectionProps>))}
    </div>
  )
}
