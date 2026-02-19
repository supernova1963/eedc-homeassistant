/**
 * React Hook für Monatsdaten-Verwaltung
 */

import { useState, useEffect, useCallback } from 'react'
import { monatsdatenApi, type MonatsdatenCreate, type MonatsdatenUpdate, type AggregierteMonatsdaten } from '../api'
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
 * Hook für aggregierte Monatsdaten (inkl. InvestitionMonatsdaten)
 *
 * WICHTIG: Dieser Hook sollte für Auswertungen verwendet werden,
 * da er die PV-Erzeugung aus InvestitionMonatsdaten korrekt aggregiert.
 */
export function useAggregierteDaten(anlageId?: number, jahr?: number) {
  const [daten, setDaten] = useState<AggregierteMonatsdaten[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!anlageId) {
      setDaten([])
      setLoading(false)
      return
    }
    try {
      setLoading(true)
      setError(null)
      const data = await monatsdatenApi.listAggregiert(anlageId, jahr)
      setDaten(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden der aggregierten Daten')
    } finally {
      setLoading(false)
    }
  }, [anlageId, jahr])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { daten, loading, error, refresh }
}

/**
 * Aggregierte Statistiken aus Monatsdaten berechnen
 *
 * @deprecated Verwende useAggregierteStats für korrekte PV-Erzeugung aus InvestitionMonatsdaten
 */
export function useMonatsdatenStats(monatsdaten: Monatsdaten[]) {
  return {
    // HINWEIS: pv_erzeugung_kwh ist ein Legacy-Feld und wird nicht mehr gepflegt!
    // Für korrekte Werte verwende useAggregierteStats mit aggregierten Daten.
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

/**
 * Aggregierte Statistiken aus aggregierten Monatsdaten berechnen
 *
 * Diese Funktion verwendet die korrekten Werte aus InvestitionMonatsdaten:
 * - PV-Erzeugung aus PV-Modulen
 * - Speicher-Daten aus Speicher-Investitionen
 * - Eigenverbrauch korrekt berechnet
 */
export function useAggregierteStats(daten: AggregierteMonatsdaten[]) {
  return {
    // PV-Erzeugung aus InvestitionMonatsdaten (korrekt aggregiert)
    gesamtErzeugung: daten.reduce((sum, m) => sum + (m.pv_erzeugung_kwh || 0), 0),
    gesamtEinspeisung: daten.reduce((sum, m) => sum + m.einspeisung_kwh, 0),
    gesamtNetzbezug: daten.reduce((sum, m) => sum + m.netzbezug_kwh, 0),
    gesamtEigenverbrauch: daten.reduce((sum, m) => sum + (m.eigenverbrauch_kwh || 0), 0),
    gesamtDirektverbrauch: daten.reduce((sum, m) => sum + (m.direktverbrauch_kwh || 0), 0),
    // Speicher
    gesamtSpeicherLadung: daten.reduce((sum, m) => sum + (m.speicher_ladung_kwh || 0), 0),
    gesamtSpeicherEntladung: daten.reduce((sum, m) => sum + (m.speicher_entladung_kwh || 0), 0),
    // Wärmepumpe
    gesamtWpStrom: daten.reduce((sum, m) => sum + (m.wp_strom_kwh || 0), 0),
    gesamtWpHeizung: daten.reduce((sum, m) => sum + (m.wp_heizung_kwh || 0), 0),
    // E-Auto
    gesamtEautoLadung: daten.reduce((sum, m) => sum + (m.eauto_ladung_kwh || 0), 0),
    gesamtEautoKm: daten.reduce((sum, m) => sum + (m.eauto_km || 0), 0),
    // Durchschnittliche Autarkie
    durchschnittAutarkie: daten.length > 0
      ? daten.reduce((sum, m) => sum + (m.autarkie_prozent || 0), 0) / daten.length
      : 0,
    anzahlMonate: daten.length,
  }
}
