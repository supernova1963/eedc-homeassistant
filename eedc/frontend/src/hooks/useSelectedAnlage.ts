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

/**
 * Liest die gespeicherte Anlagen-ID und verwirft, was keine sein kann.
 *
 * ⚠ N-265: `parseInt` liefert für einen fremden Speicherwert **NaN**, und NaN
 * kommt durch jedes `== null` der aufrufenden Seiten hindurch — die ID gilt dann
 * als vorhanden und landet als `anlage_id` in einem Schreib-Request.
 */
export function gespeicherteAnlageId(roh: string | null): number | undefined {
  if (roh === null) return undefined
  const id = Number.parseInt(roh, 10)
  return Number.isInteger(id) && id > 0 ? id : undefined
}

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
  const { anlagen, loading, error, refresh } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageIdRaw] = useState<number | undefined>(
    () => gespeicherteAnlageId(localStorage.getItem(STORAGE_KEY))
  )

  // Auto-Select: Gespeicherte ID validieren oder erste Anlage wählen
  //
  // ⚠ N-265: Hier stand bis 17.08.2026 `if (anlagen.length === 0) return` — die
  // Prüfung stieg damit genau in dem Fall aus, für den es sie gibt. Wer seine
  // einzige Anlage löschte, behielt eine tote ID (der Speicher-Key wurde
  // nirgends geräumt); sie ist als Zahl `truthy`, kam durch jedes `== null` und
  // quittierte erst beim Speichern mit dem rohen Backend-404 „Anlage nicht
  // gefunden". Herausgefallen ist der Melder bei der Ersteinrichtung
  // (T89667 #170) — er kam nur wieder heraus, weil eine NEUE Anlage die Liste
  // füllte und die Prüfung damit endlich lief.
  useEffect(() => {
    // Solange die Liste nicht feststeht, ist eine leere Liste keine Aussage:
    // `useAnlagen` startet mit [] und meldet auch einen Ladefehler so. Ein
    // Backend-Aussetzer darf eine gültige Auswahl nicht verwerfen.
    if (loading || error) return

    if (anlagen.length === 0) {
      // Es gibt wirklich keine Anlage ⇒ die gespeicherte ID kann keine treffen.
      if (selectedAnlageId !== undefined) {
        setSelectedAnlageIdRaw(undefined)
        localStorage.removeItem(STORAGE_KEY)
      }
      return
    }

    if (selectedAnlageId != null) {
      // Gespeicherte ID existiert noch? Wenn nicht → erste Anlage
      const exists = anlagen.some(a => a.id === selectedAnlageId)
      if (exists) return
    }

    // Erste Anlage auswählen
    setSelectedAnlageIdRaw(anlagen[0].id)
    localStorage.setItem(STORAGE_KEY, String(anlagen[0].id))
  }, [anlagen, loading, error, selectedAnlageId])

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
