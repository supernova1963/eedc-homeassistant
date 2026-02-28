/**
 * React Hook für Anlagen-Verwaltung
 */

import { useState, useEffect, useCallback } from 'react'
import { anlagenApi } from '../api'
import type { Anlage, AnlageCreate, AnlageUpdate } from '../types'

interface UseAnlagenReturn {
  anlagen: Anlage[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  createAnlage: (data: AnlageCreate) => Promise<Anlage>
  updateAnlage: (id: number, data: AnlageUpdate) => Promise<Anlage>
  deleteAnlage: (id: number) => Promise<void>
}

export function useAnlagen(): UseAnlagenReturn {
  const [anlagen, setAnlagen] = useState<Anlage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await anlagenApi.list()
      setAnlagen(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden der Anlagen')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const createAnlage = useCallback(async (data: AnlageCreate): Promise<Anlage> => {
    const newAnlage = await anlagenApi.create(data)
    setAnlagen(prev => [...prev, newAnlage])
    return newAnlage
  }, [])

  const updateAnlage = useCallback(async (id: number, data: AnlageUpdate): Promise<Anlage> => {
    const updated = await anlagenApi.update(id, data)
    setAnlagen(prev => prev.map(a => a.id === id ? updated : a))
    return updated
  }, [])

  const deleteAnlage = useCallback(async (id: number): Promise<void> => {
    await anlagenApi.delete(id)
    setAnlagen(prev => prev.filter(a => a.id !== id))
  }, [])

  return {
    anlagen,
    loading,
    error,
    refresh,
    createAnlage,
    updateAnlage,
    deleteAnlage,
  }
}

/**
 * Hook für einzelne Anlage
 */
export function useAnlage(id: number | null) {
  const [anlage, setAnlage] = useState<Anlage | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (id === null) {
      setAnlage(null)
      return
    }

    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await anlagenApi.get(id)
        setAnlage(data)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden der Anlage')
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [id])

  return { anlage, loading, error }
}
