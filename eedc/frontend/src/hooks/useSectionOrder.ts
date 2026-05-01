/**
 * useSectionOrder - localStorage-basierte Reihenfolge-Verwaltung für
 * sortierbare Cockpit-Sektionen (#175).
 *
 * Validiert geladene Reihenfolge gegen die Default-Liste, fehlende IDs
 * werden hinten angehängt — robust gegen Releases, die neue Sektionen
 * einführen oder umbenennen.
 *
 * Verwendung:
 *   const { order, moveSection, resetOrder } = useSectionOrder('cockpit-wp', [
 *     'kpis', 'jaz', 'charts', 'monatsvergleich', 'co2', 'details',
 *   ])
 */

import { useCallback, useState } from 'react'

type Direction = 'up' | 'down'

function loadOrder(storageKey: string, defaults: readonly string[]): string[] {
  try {
    const stored = localStorage.getItem(storageKey)
    if (stored) {
      const parsed = JSON.parse(stored)
      if (Array.isArray(parsed)) {
        const valid = parsed.filter((id: unknown): id is string =>
          typeof id === 'string' && defaults.includes(id))
        for (const def of defaults) {
          if (!valid.includes(def)) valid.push(def)
        }
        return valid
      }
    }
  } catch { /* invalides JSON / localStorage nicht verfügbar */ }
  return [...defaults]
}

function saveOrder(storageKey: string, order: string[]): void {
  try { localStorage.setItem(storageKey, JSON.stringify(order)) } catch { /* localStorage nicht verfügbar */ }
}

export function useSectionOrder(storageKey: string, defaults: readonly string[]) {
  const [order, setOrder] = useState<string[]>(() => loadOrder(storageKey, defaults))

  const moveSection = useCallback((id: string, dir: Direction) => {
    setOrder(prev => {
      const idx = prev.indexOf(id)
      if (idx < 0) return prev
      const target = dir === 'up' ? idx - 1 : idx + 1
      if (target < 0 || target >= prev.length) return prev
      const next = [...prev]
      ;[next[idx], next[target]] = [next[target], next[idx]]
      saveOrder(storageKey, next)
      return next
    })
  }, [storageKey])

  const resetOrder = useCallback(() => {
    const fresh = [...defaults]
    saveOrder(storageKey, fresh)
    setOrder(fresh)
  }, [storageKey, defaults])

  return { order, moveSection, resetOrder }
}
