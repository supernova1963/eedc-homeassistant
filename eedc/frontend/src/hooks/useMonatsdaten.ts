/**
 * React Hook für Monatsdaten-Verwaltung
 */

import { useState, useEffect, useCallback } from 'react'
import { monatsdatenApi, type MonatsdatenCreate, type MonatsdatenUpdate } from '../api'
import type { Monatsdaten } from '../types'

interface UseMonatsdatenReturn {
  monatsdaten: Monatsdaten[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  createMonatsdaten: (data: MonatsdatenCreate) => Promise<Monatsdaten>
  updateMonatsdaten: (id: number, data: MonatsdatenUpdate) => Promise<Monatsdaten>
  deleteMonatsdaten: (id: number) => Promise<void>
}

export function useMonatsdaten(anlageId?: number, jahr?: number): UseMonatsdatenReturn {
  const [monatsdaten, setMonatsdaten] = useState<Monatsdaten[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await monatsdatenApi.list(anlageId, jahr)
      setMonatsdaten(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden der Monatsdaten')
    } finally {
      setLoading(false)
    }
  }, [anlageId, jahr])

  useEffect(() => {
    refresh()
  }, [refresh])

  const createMonatsdaten = useCallback(async (data: MonatsdatenCreate): Promise<Monatsdaten> => {
    const newData = await monatsdatenApi.create(data)
    setMonatsdaten(prev => [newData, ...prev])
    return newData
  }, [])

  const updateMonatsdaten = useCallback(async (id: number, data: MonatsdatenUpdate): Promise<Monatsdaten> => {
    const updated = await monatsdatenApi.update(id, data)
    setMonatsdaten(prev => prev.map(m => m.id === id ? updated : m))
    return updated
  }, [])

  const deleteMonatsdaten = useCallback(async (id: number): Promise<void> => {
    await monatsdatenApi.delete(id)
    setMonatsdaten(prev => prev.filter(m => m.id !== id))
  }, [])

  return {
    monatsdaten,
    loading,
    error,
    refresh,
    createMonatsdaten,
    updateMonatsdaten,
    deleteMonatsdaten,
  }
}

/**
 * Aggregierte Statistiken aus Monatsdaten berechnen
 */
export function useMonatsdatenStats(monatsdaten: Monatsdaten[]) {
  return {
    gesamtErzeugung: monatsdaten.reduce((sum, m) => sum + (m.pv_erzeugung_kwh || 0), 0),
    gesamtEinspeisung: monatsdaten.reduce((sum, m) => sum + m.einspeisung_kwh, 0),
    gesamtNetzbezug: monatsdaten.reduce((sum, m) => sum + m.netzbezug_kwh, 0),
    gesamtEigenverbrauch: monatsdaten.reduce((sum, m) => sum + (m.eigenverbrauch_kwh || 0), 0),
    durchschnittAutarkie: monatsdaten.length > 0
      ? monatsdaten.reduce((sum, m) => {
          const ev = m.eigenverbrauch_kwh || 0
          const gesamt = (m.eigenverbrauch_kwh || 0) + m.netzbezug_kwh
          return sum + (gesamt > 0 ? (ev / gesamt) * 100 : 0)
        }, 0) / monatsdaten.length
      : 0,
    anzahlMonate: monatsdaten.length,
  }
}
