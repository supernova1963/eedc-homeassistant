/**
 * React Hook für Investitionen-Verwaltung mit Shared Module-Level Cache.
 *
 * Funktioniert wie useAnlagen: Alle Hook-Instanzen für dieselbe anlageId
 * teilen einen Cache. SubTabs + Seiten machen nur 1 API-Call statt N.
 */

import { useState, useEffect, useCallback } from 'react'
import { investitionenApi, type InvestitionCreate, type InvestitionUpdate, type InvestitionTypInfo } from '../api'
import type { Investition } from '../types'

// ── Shared Module-Level Cache ───────────────────────────────────────────────

/** Cache pro anlageId (ohne typ-Filter). Key "all:{anlageId}" */
const cachedInvestitionen: Map<number, Investition[]> = new Map()
const cachePromises: Map<number, Promise<Investition[]>> = new Map()

const CACHE_EVENT = 'eedc-investitionen-changed'

function notifyChange(anlageId: number, data: Investition[]) {
  cachedInvestitionen.set(anlageId, data)
  cachePromises.delete(anlageId)
  window.dispatchEvent(new CustomEvent(CACHE_EVENT, { detail: { anlageId, data } }))
}

async function fetchInvestitionen(anlageId: number, typ?: string): Promise<Investition[]> {
  // typ-Filter → kein Cache (selten, spezifisch)
  if (typ) return investitionenApi.list(anlageId, typ)

  const existing = cachePromises.get(anlageId)
  if (existing) return existing

  const promise = investitionenApi.list(anlageId).then(data => {
    cachedInvestitionen.set(anlageId, data)
    cachePromises.delete(anlageId)
    return data
  }).catch(err => {
    cachePromises.delete(anlageId)
    throw err
  })
  cachePromises.set(anlageId, promise)
  return promise
}

// ── Hook ────────────────────────────────────────────────────────────────────

interface UseInvestitionenReturn {
  investitionen: Investition[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  createInvestition: (data: InvestitionCreate) => Promise<Investition>
  updateInvestition: (id: number, data: InvestitionUpdate) => Promise<Investition>
  deleteInvestition: (id: number) => Promise<void>
}

export function useInvestitionen(anlageId?: number, typ?: string): UseInvestitionenReturn {
  const cacheKey = anlageId && !typ ? anlageId : undefined
  const [investitionen, setInvestitionen] = useState<Investition[]>(
    () => (cacheKey ? cachedInvestitionen.get(cacheKey) : undefined) ?? []
  )
  const [loading, setLoading] = useState(
    () => cacheKey ? !cachedInvestitionen.has(cacheKey) : true
  )
  const [error, setError] = useState<string | null>(null)

  // Auf Cache-Änderungen von anderen Instanzen reagieren
  useEffect(() => {
    if (!cacheKey) return
    const handler = (e: Event) => {
      const { anlageId: changedId, data } = (e as CustomEvent).detail
      if (changedId === cacheKey) {
        setInvestitionen(data)
        setLoading(false)
      }
    }
    window.addEventListener(CACHE_EVENT, handler)
    return () => window.removeEventListener(CACHE_EVENT, handler)
  }, [cacheKey])

  // Initial laden
  useEffect(() => {
    if (!anlageId) return

    // Cache-Hit?
    if (cacheKey && cachedInvestitionen.has(cacheKey)) {
      setInvestitionen(cachedInvestitionen.get(cacheKey)!)
      setLoading(false)
      return
    }

    fetchInvestitionen(anlageId, typ)
      .then(data => {
        setInvestitionen(data)
        setLoading(false)
        setError(null)
      })
      .catch(e => {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden der Investitionen')
        setLoading(false)
      })
  }, [anlageId, typ, cacheKey])

  const refresh = useCallback(async () => {
    if (!anlageId) return
    try {
      setLoading(true)
      setError(null)
      if (cacheKey) cachedInvestitionen.delete(cacheKey)
      const data = await fetchInvestitionen(anlageId, typ)
      if (cacheKey) {
        notifyChange(cacheKey, data)
      } else {
        setInvestitionen(data)
        setLoading(false)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden der Investitionen')
      setLoading(false)
    }
  }, [anlageId, typ, cacheKey])

  const createInvestition = useCallback(async (data: InvestitionCreate): Promise<Investition> => {
    const newInv = await investitionenApi.create(data)
    if (cacheKey) {
      notifyChange(cacheKey, [...(cachedInvestitionen.get(cacheKey) ?? []), newInv])
    } else {
      setInvestitionen(prev => [...prev, newInv])
    }
    return newInv
  }, [cacheKey])

  const updateInvestition = useCallback(async (id: number, data: InvestitionUpdate): Promise<Investition> => {
    const updated = await investitionenApi.update(id, data)
    if (cacheKey) {
      notifyChange(cacheKey, (cachedInvestitionen.get(cacheKey) ?? []).map(i => i.id === id ? updated : i))
    } else {
      setInvestitionen(prev => prev.map(i => i.id === id ? updated : i))
    }
    return updated
  }, [cacheKey])

  const deleteInvestition = useCallback(async (id: number): Promise<void> => {
    await investitionenApi.delete(id)
    if (cacheKey) {
      notifyChange(cacheKey, (cachedInvestitionen.get(cacheKey) ?? []).filter(i => i.id !== id))
    } else {
      setInvestitionen(prev => prev.filter(i => i.id !== id))
    }
  }, [cacheKey])

  return {
    investitionen,
    loading,
    error,
    refresh,
    createInvestition,
    updateInvestition,
    deleteInvestition,
  }
}

/**
 * Hook für Investitionstypen-Schema
 */
export function useInvestitionTypen() {
  const [typen, setTypen] = useState<InvestitionTypInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        const data = await investitionenApi.getTypen()
        setTypen(data)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden der Typen')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  return { typen, loading, error }
}

/**
 * Investitionen nach Typ gruppieren
 */
export function useInvestitionenByTyp(investitionen: Investition[]) {
  const grouped = investitionen.reduce((acc, inv) => {
    if (!acc[inv.typ]) acc[inv.typ] = []
    acc[inv.typ].push(inv)
    return acc
  }, {} as Record<string, Investition[]>)

  return grouped
}
