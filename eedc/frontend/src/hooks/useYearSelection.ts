/**
 * Hook für Jahr-Selektion mit automatischer Ableitung verfügbarer Jahre.
 *
 * Ersetzt das in Dashboard, Monatsdaten, Auswertung etc. duplizierte Pattern:
 *   const [selectedYear, setSelectedYear] = useState<number | undefined>()
 *   const [availableYears, setAvailableYears] = useState<number[]>([])
 *   useEffect(() => { setAvailableYears([...new Set(data.map(d => d.jahr))]); ... }, [data])
 */

import { useState, useCallback } from 'react'

interface UseYearSelectionReturn {
  /** Aktuell ausgewähltes Jahr (undefined = alle Jahre). */
  selectedYear: number | undefined
  /** Jahr setzen (undefined = alle Jahre). */
  setSelectedYear: (year: number | undefined) => void
  /** Verfügbare Jahre (sortiert, absteigend). */
  availableYears: number[]
  /** Verfügbare Jahre setzen (z.B. aus geladenen Daten abgeleitet). */
  setAvailableYears: (years: number[]) => void
}

export function useYearSelection(defaultYear?: number): UseYearSelectionReturn {
  const [selectedYear, setSelectedYear] = useState<number | undefined>(defaultYear)
  const [availableYears, setAvailableYearsRaw] = useState<number[]>([])

  const setAvailableYears = useCallback((years: number[]) => {
    const sorted = [...new Set(years)].sort((a, b) => b - a)
    setAvailableYearsRaw(sorted)
  }, [])

  return {
    selectedYear,
    setSelectedYear,
    availableYears,
    setAvailableYears,
  }
}
