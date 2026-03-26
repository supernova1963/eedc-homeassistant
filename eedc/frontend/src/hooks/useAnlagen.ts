/**
 * React Hook für Anlagen-Verwaltung mit Shared Module-Level Cache.
 *
 * Alle Hook-Instanzen teilen denselben Cache — egal ob TopNavigation,
 * SubTabs oder eine Seite den Hook nutzt, es wird nur EIN API-Call gemacht.
 * Mutationen (create/update/delete) aktualisieren den Cache und benachrichtigen
 * alle Instanzen via CustomEvent.
 */

import { useState, useEffect, useCallback } from 'react'
import { anlagenApi } from '../api'
import type { Anlage, AnlageCreate, AnlageUpdate } from '../types'

// ── Shared Module-Level Cache ───────────────────────────────────────────────

/** Cache-Status: null = noch nie geladen, [] = geladen (evtl. leer) */
let cachedAnlagen: Anlage[] | null = null
let cachePromise: Promise<Anlage[]> | null = null

const CACHE_EVENT = 'eedc-anlagen-changed'

/** Benachrichtigt alle Hook-Instanzen über Cache-Änderung. */
function notifyChange(anlagen: Anlage[]) {
  cachedAnlagen = anlagen
  cachePromise = null
  window.dispatchEvent(new CustomEvent(CACHE_EVENT, { detail: anlagen }))
}

/** Lädt Anlagen — dedupliziert parallele Aufrufe via Shared Promise. */
async function fetchAnlagen(): Promise<Anlage[]> {
  if (!cachePromise) {
    cachePromise = anlagenApi.list().then(data => {
      cachedAnlagen = data
      cachePromise = null
      return data
    }).catch(err => {
      cachePromise = null
      throw err
    })
  }
  return cachePromise
}

// ── Hook ────────────────────────────────────────────────────────────────────

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
  const [anlagen, setAnlagen] = useState<Anlage[]>(cachedAnlagen ?? [])
  const [loading, setLoading] = useState(cachedAnlagen === null)
  const [error, setError] = useState<string | null>(null)

  // Auf Cache-Änderungen von anderen Instanzen reagieren
  useEffect(() => {
    const handler = (e: Event) => {
      setAnlagen((e as CustomEvent<Anlage[]>).detail)
      setLoading(false)
    }
    window.addEventListener(CACHE_EVENT, handler)
    return () => window.removeEventListener(CACHE_EVENT, handler)
  }, [])

  // Initial laden (nur wenn Cache leer)
  useEffect(() => {
    if (cachedAnlagen !== null) return

    fetchAnlagen()
      .then(data => {
        setAnlagen(data)
        setLoading(false)
        setError(null)
      })
      .catch(e => {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden der Anlagen')
        setLoading(false)
      })
  }, [])

  const refresh = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      cachedAnlagen = null  // Cache invalidieren
      const data = await fetchAnlagen()
      notifyChange(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden der Anlagen')
      setLoading(false)
    }
  }, [])

  const createAnlage = useCallback(async (data: AnlageCreate): Promise<Anlage> => {
    const newAnlage = await anlagenApi.create(data)
    notifyChange([...(cachedAnlagen ?? []), newAnlage])
    return newAnlage
  }, [])

  const updateAnlage = useCallback(async (id: number, data: AnlageUpdate): Promise<Anlage> => {
    const updated = await anlagenApi.update(id, data)
    notifyChange((cachedAnlagen ?? []).map(a => a.id === id ? updated : a))
    return updated
  }, [])

  const deleteAnlage = useCallback(async (id: number): Promise<void> => {
    await anlagenApi.delete(id)
    notifyChange((cachedAnlagen ?? []).filter(a => a.id !== id))
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
 * Hook für einzelne Anlage — nutzt den Shared Cache wenn möglich.
 */
export function useAnlage(id: number | null) {
  const [anlage, setAnlage] = useState<Anlage | null>(() => {
    if (id === null) return null
    return cachedAnlagen?.find(a => a.id === id) ?? null
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (id === null) {
      setAnlage(null)
      return
    }

    // Erst im Cache schauen
    const cached = cachedAnlagen?.find(a => a.id === id)
    if (cached) {
      setAnlage(cached)
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

  // Auf Cache-Updates reagieren
  useEffect(() => {
    if (id === null) return
    const handler = (e: Event) => {
      const updated = (e as CustomEvent<Anlage[]>).detail.find(a => a.id === id)
      if (updated) setAnlage(updated)
    }
    window.addEventListener(CACHE_EVENT, handler)
    return () => window.removeEventListener(CACHE_EVENT, handler)
  }, [id])

  return { anlage, loading, error }
}
