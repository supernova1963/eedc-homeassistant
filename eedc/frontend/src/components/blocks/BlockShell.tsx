/**
 * BlockShell — rendert eine Liste universeller {@link Block}s mit Einklappen,
 * Fokus/Vollbild und (optional) ↑↓-Reihenfolge; merkt Klapp-/Reihenfolge-
 * Zustand pro Sicht in localStorage.
 *
 * Promoviert aus `components/preview/IASkeleton.tsx` (dort `BloeckeView`).
 * Hier die echte, getestete Variante für den IA-v4-Routenbaum.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  ArrowUp, ArrowDown, ChevronDown, Maximize2, RotateCcw,
} from 'lucide-react'
import type { Block } from './types'
import { FokusVollbild } from './FokusVollbild'

// ─── Persistenz Klappzustand + Reihenfolge (detLAN #243 A4) ───────────────────
const LS_PREFIX = 'eedc-bloecke:'
interface BlockState { order?: string[]; zu?: string[] }

export function ladeBlockState(key: string): BlockState {
  try {
    const raw = localStorage.getItem(LS_PREFIX + key)
    return raw ? (JSON.parse(raw) as BlockState) : {}
  } catch {
    return {}
  }
}
export function speichereBlockState(key: string, state: { order: string[]; zu: string[] }) {
  try {
    localStorage.setItem(LS_PREFIX + key, JSON.stringify(state))
  } catch {
    /* localStorage nicht verfügbar (Privatmodus o. Ä.) — Persistenz still überspringen */
  }
}

export function BlockShell({
  bloecke,
  sortierbar = false,
  persistKey,
}: {
  bloecke: Block[]
  sortierbar?: boolean
  persistKey: string
}) {
  const ids = useMemo(() => bloecke.map((b) => b.id), [bloecke])
  const [order, setOrder] = useState<string[]>(() => {
    const gespeichert = ladeBlockState(persistKey).order
    if (!gespeichert) return ids
    // Nur bekannte IDs übernehmen, neue/fehlende hinten anhängen (Schema-robust).
    const gueltig = gespeichert.filter((id) => ids.includes(id))
    return [...gueltig, ...ids.filter((id) => !gueltig.includes(id))]
  })
  const [zu, setZu] = useState<Set<string>>(() => {
    const gespeichert = ladeBlockState(persistKey).zu
    return gespeichert
      ? new Set(gespeichert.filter((id) => ids.includes(id)))
      : new Set(bloecke.filter((b) => b.defaultOpen === false).map((b) => b.id))
  })
  const [fokus, setFokus] = useState<string | null>(null)
  const byId = useMemo(() => Object.fromEntries(bloecke.map((b) => [b.id, b] as const)), [bloecke])

  // Default-Klappzustand (defaultOpen === false → eingeklappt) für den Reset.
  const defaultZu = useMemo(
    () => bloecke.filter((b) => b.defaultOpen === false).map((b) => b.id),
    [bloecke],
  )
  const istDefault = useMemo(() => {
    const sameOrder = order.length === ids.length && order.every((id, i) => id === ids[i])
    const sameZu = zu.size === defaultZu.length && defaultZu.every((id) => zu.has(id))
    return sameOrder && sameZu
  }, [order, ids, zu, defaultZu])
  const zuruecksetzen = () => {
    setOrder(ids)
    setZu(new Set(defaultZu))
    setFokus(null)
  }

  // Klappzustand (+ Reihenfolge) pro Sicht merken.
  useEffect(() => {
    speichereBlockState(persistKey, { order, zu: [...zu] })
  }, [persistKey, order, zu])

  const verschieben = (i: number, r: -1 | 1) => {
    const ziel = i + r
    if (ziel < 0 || ziel >= order.length) return
    const next = [...order]
    ;[next[i], next[ziel]] = [next[ziel], next[i]]
    setOrder(next)
  }
  const toggle = (id: string) => {
    const next = new Set(zu)
    next.has(id) ? next.delete(id) : next.add(id)
    setZu(next)
  }

  // ── Fokus/Vollbild: nur dieser Block, bildschirmfüllend (geteiltes Overlay) ──
  if (fokus && byId[fokus]) {
    const b = byId[fokus]
    return (
      <FokusVollbild titel={b.title} icon={b.icon} farbe={b.farbe} onClose={() => setFokus(null)}>
        {b.render(true)}
      </FokusVollbild>
    )
  }

  const ordered = order.map((id) => byId[id]).filter(Boolean) as Block[]
  return (
    <div className="p-3 sm:p-6 space-y-3 max-w-[1920px] mx-auto">
      <p className="text-xs text-gray-400 dark:text-gray-500 flex flex-wrap items-center gap-x-1">
        <span>
          Jeder Block: <ChevronDown className="inline h-3 w-3" /> einklappen ·{' '}
          <Maximize2 className="inline h-3 w-3" /> Fokus/Vollbild
          {sortierbar && (
            <>
              {' '}· <ArrowUp className="inline h-3 w-3" />
              <ArrowDown className="inline h-3 w-3" /> verschieben
            </>
          )}{' '}
          · Zustand bleibt gemerkt
        </span>
        {!istDefault && (
          <button
            type="button"
            onClick={zuruecksetzen}
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
          >
            <RotateCcw className="h-3 w-3" /> zurücksetzen
          </button>
        )}
      </p>
      {ordered.map((b, i) => {
        const istZu = zu.has(b.id)
        return (
          <section
            key={b.id}
            className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden"
          >
            <div className="flex items-center gap-2 px-3 min-h-[44px]">
              <button
                type="button"
                onClick={() => toggle(b.id)}
                className="flex-1 flex items-center gap-2 text-left py-2 min-w-0"
              >
                {b.icon && <b.icon className={`h-4 w-4 flex-shrink-0 ${b.farbe ?? 'text-gray-400 dark:text-gray-500'}`} />}
                <span className="text-sm font-semibold text-gray-900 dark:text-white whitespace-nowrap">{b.title}</span>
                {b.summary && <span className="text-xs text-gray-400 dark:text-gray-500 truncate">{b.summary}</span>}
              </button>
              {b.badge && <div className="flex-shrink-0">{b.badge}</div>}
              <div className="flex items-center gap-0.5 flex-shrink-0">
                {sortierbar && (
                  <>
                    <button
                      type="button"
                      onClick={() => verschieben(i, -1)}
                      disabled={i === 0}
                      aria-label="nach oben"
                      className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-30 disabled:cursor-default"
                    >
                      <ArrowUp className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => verschieben(i, 1)}
                      disabled={i === ordered.length - 1}
                      aria-label="nach unten"
                      className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-30 disabled:cursor-default"
                    >
                      <ArrowDown className="h-4 w-4" />
                    </button>
                  </>
                )}
                <button
                  type="button"
                  onClick={() => setFokus(b.id)}
                  aria-label="Fokus / Vollbild"
                  className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                >
                  <Maximize2 className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => toggle(b.id)}
                  aria-label={istZu ? 'aufklappen' : 'einklappen'}
                  className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                >
                  <ChevronDown className={`h-4 w-4 transition-transform ${istZu ? '-rotate-90' : ''}`} />
                </button>
              </div>
            </div>
            {!istZu && <div className="px-3 pb-3">{b.render(false)}</div>}
          </section>
        )
      })}
    </div>
  )
}
