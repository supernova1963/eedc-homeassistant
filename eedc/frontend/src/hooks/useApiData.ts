/**
 * Generischer Hook für async Datenfetch mit Loading/Error-State.
 *
 * Ersetzt das in 30+ Seiten duplizierte Pattern:
 *   const [data, setData] = useState<T | null>(null)
 *   const [loading, setLoading] = useState(true)
 *   const [error, setError] = useState<string | null>(null)
 *   useEffect(() => { fetchData().then(setData).catch(setError) }, [deps])
 */

import { useState, useEffect, useCallback, useRef } from 'react'

interface UseApiDataReturn<T> {
  /** Die geladenen Daten (oder null wenn noch nicht geladen / Fehler). */
  data: T | null
  /** Daten werden geladen. */
  loading: boolean
  /** Fehlermeldung (oder null). */
  error: string | null
  /** Daten manuell neu laden. */
  refetch: () => Promise<void>
}

interface UseApiDataOptions {
  /** Fetch nur ausführen wenn true (Default: true). */
  enabled?: boolean
}

/**
 * Generischer async Datenfetch-Hook.
 *
 * @param fetcher - Async Funktion die Daten lädt
 * @param deps - Dependency-Array (bei Änderung wird neu geladen)
 * @param options - Optionen (enabled)
 *
 * @example
 * const { data, loading, error } = useApiData(
 *   () => cockpitApi.getUebersicht(anlageId!, year),
 *   [anlageId, year],
 *   { enabled: anlageId != null }
 * )
 */
export function useApiData<T>(
  fetcher: () => Promise<T>,
  deps: unknown[],
  options?: UseApiDataOptions,
): UseApiDataReturn<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const enabled = options?.enabled ?? true

  const refetch = useCallback(async () => {
    if (!enabled) return
    try {
      setLoading(true)
      setError(null)
      const result = await fetcherRef.current()
      setData(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unbekannter Fehler')
    } finally {
      setLoading(false)
    }
  }, [enabled])

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    refetch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled])

  return { data, loading, error, refetch }
}
