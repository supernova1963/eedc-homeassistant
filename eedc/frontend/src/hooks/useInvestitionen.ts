/**
 * React Hook für Investitionen-Verwaltung
 */

import { useState, useEffect, useCallback } from 'react'
import { investitionenApi, type InvestitionCreate, type InvestitionUpdate, type InvestitionTypInfo } from '../api'
import type { Investition } from '../types'

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
  const [investitionen, setInvestitionen] = useState<Investition[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await investitionenApi.list(anlageId, typ)
      setInvestitionen(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden der Investitionen')
    } finally {
      setLoading(false)
    }
  }, [anlageId, typ])

  useEffect(() => {
    refresh()
  }, [refresh])

  const createInvestition = useCallback(async (data: InvestitionCreate): Promise<Investition> => {
    const newInv = await investitionenApi.create(data)
    setInvestitionen(prev => [...prev, newInv])
    return newInv
  }, [])

  const updateInvestition = useCallback(async (id: number, data: InvestitionUpdate): Promise<Investition> => {
    const updated = await investitionenApi.update(id, data)
    setInvestitionen(prev => prev.map(i => i.id === id ? updated : i))
    return updated
  }, [])

  const deleteInvestition = useCallback(async (id: number): Promise<void> => {
    await investitionenApi.delete(id)
    setInvestitionen(prev => prev.filter(i => i.id !== id))
  }, [])

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
