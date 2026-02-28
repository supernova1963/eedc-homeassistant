/**
 * React Hook für Strompreise-Verwaltung
 */

import { useState, useEffect, useCallback } from 'react'
import { strompreiseApi, type StrompreisCreate, type StrompreisUpdate } from '../api'
import type { Strompreis } from '../types'

interface UseStrompreiseReturn {
  strompreise: Strompreis[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  createStrompreis: (data: StrompreisCreate) => Promise<Strompreis>
  updateStrompreis: (id: number, data: StrompreisUpdate) => Promise<Strompreis>
  deleteStrompreis: (id: number) => Promise<void>
}

export function useStrompreise(anlageId?: number): UseStrompreiseReturn {
  const [strompreise, setStrompreise] = useState<Strompreis[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await strompreiseApi.list(anlageId)
      setStrompreise(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden der Strompreise')
    } finally {
      setLoading(false)
    }
  }, [anlageId])

  useEffect(() => {
    refresh()
  }, [refresh])

  const createStrompreis = useCallback(async (data: StrompreisCreate): Promise<Strompreis> => {
    const newPreis = await strompreiseApi.create(data)
    setStrompreise(prev => [newPreis, ...prev])
    return newPreis
  }, [])

  const updateStrompreis = useCallback(async (id: number, data: StrompreisUpdate): Promise<Strompreis> => {
    const updated = await strompreiseApi.update(id, data)
    setStrompreise(prev => prev.map(p => p.id === id ? updated : p))
    return updated
  }, [])

  const deleteStrompreis = useCallback(async (id: number): Promise<void> => {
    await strompreiseApi.delete(id)
    setStrompreise(prev => prev.filter(p => p.id !== id))
  }, [])

  return {
    strompreise,
    loading,
    error,
    refresh,
    createStrompreis,
    updateStrompreis,
    deleteStrompreis,
  }
}

/**
 * Hook für aktuellen Strompreis einer Anlage
 */
export function useAktuellerStrompreis(anlageId: number | null) {
  const [strompreis, setStrompreis] = useState<Strompreis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (anlageId === null) {
      setStrompreis(null)
      return
    }

    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await strompreiseApi.getAktuell(anlageId)
        setStrompreis(data)
      } catch (e) {
        // Kein aktueller Preis ist OK
        setStrompreis(null)
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [anlageId])

  return { strompreis, loading, error }
}
