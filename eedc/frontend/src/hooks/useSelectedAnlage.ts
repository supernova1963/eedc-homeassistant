/**
 * Hook für Anlage-Selektion mit Auto-Select und localStorage-Persistierung.
 *
 * Ersetzt das in 27 Seiten duplizierte Pattern:
 *   const { anlagen } = useAnlagen()
 *   const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>()
 *   useEffect(() => { if (anlagen.length > 0 && !selectedAnlageId) setSelectedAnlageId(anlagen[0].id) }, ...)
 */

import { useState, useEffect, useCallback } from 'react'
import { useAnlagen } from './useAnlagen'
import type { Anlage } from '../types'

const STORAGE_KEY = 'eedc-selected-anlage-id'
const CHANGE_EVENT = 'eedc-anlage-changed'

interface UseSelectedAnlageReturn {
  /** Alle verfügbaren Anlagen. */
  anlagen: Anlage[]
  /** ID der aktuell ausgewählten Anlage (oder undefined wenn noch keine geladen). */
  selectedAnlageId: number | undefined
  /** Die ausgewählte Anlage als Objekt (oder undefined). */
  selectedAnlage: Anlage | undefined
  /** Anlage wechseln (wird in localStorage persistiert). */
  setSelectedAnlageId: (id: number) => void
  /** Anlagen werden geladen. */
  loading: boolean
  /** Anlagen-Liste neu laden. */
  refresh: () => Promise<void>
}

export function useSelectedAnlage(): UseSelectedAnlageReturn {
  const { anlagen, loading, refresh } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageIdRaw] = useState<number | undefined>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored ? parseInt(stored, 10) : undefined
  })

  // Auto-Select: Gespeicherte ID validieren oder erste Anlage wählen
  useEffect(() => {
    if (anlagen.length === 0) return

    if (selectedAnlageId != null) {
      // Gespeicherte ID existiert noch? Wenn nicht → erste Anlage
      const exists = anlagen.some(a => a.id === selectedAnlageId)
      if (exists) return
    }

    // Erste Anlage auswählen
    setSelectedAnlageIdRaw(anlagen[0].id)
    localStorage.setItem(STORAGE_KEY, String(anlagen[0].id))
  }, [anlagen, selectedAnlageId])

  // Auf Änderungen von anderen Hook-Instanzen reagieren
  useEffect(() => {
    const handleChange = (e: Event) => {
      const newId = (e as CustomEvent<number>).detail
      setSelectedAnlageIdRaw(newId)
    }
    window.addEventListener(CHANGE_EVENT, handleChange)
    return () => window.removeEventListener(CHANGE_EVENT, handleChange)
  }, [])

  const setSelectedAnlageId = useCallback((id: number) => {
    setSelectedAnlageIdRaw(id)
    localStorage.setItem(STORAGE_KEY, String(id))
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: id }))
  }, [])

  const selectedAnlage = anlagen.find(a => a.id === selectedAnlageId)

  return {
    anlagen,
    selectedAnlageId,
    selectedAnlage,
    setSelectedAnlageId,
    loading,
    refresh,
  }
}
