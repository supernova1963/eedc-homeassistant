/**
 * Generischer Hook für async Datenfetch mit Loading/Error-State.
 *
 * Ersetzt das in 30+ Seiten duplizierte Pattern:
 *   const [data, setData] = useState<T | null>(null)
 *   const [loading, setLoading] = useState(true)
 *   const [error, setError] = useState<string | null>(null)
 *   useEffect(() => { fetchData().then(setData).catch(setError) }, [deps])
 *
 * SWR-Sicht-Cache (R18-2, opt-in via `swrKey`): Die V4-Sichten fetchen bei jedem
 * Tab-Wechsel neu (unmount → remount) und zeigten dabei ein Lade-Skeleton, obwohl
 * die Daten Sekunden vorher noch da waren (rapahl #218). Mit `swrKey` werden
 * Ergebnisse in einem Modul-Cache gehalten: beim Remount stehen die ALTEN Daten
 * sofort (loading bleibt false), still revalidiert wird trotzdem (`reloading`).
 * Skeleton nur noch beim echten Erst-Load (kein Cache-Eintrag) — genau das
 * Community-Muster (Benchmark einmal laden), ohne den Dispatcher zum
 * Fetch-Monolithen zu machen. SoT: docs/drafts/KONZEPT-LADEZEIT-CACHE-SWR.md.
 * Ohne `swrKey` ist das Verhalten unverändert (V3-Seiten unberührt).
 */

import { useState, useEffect, useCallback, useRef } from 'react'

// Modul-Singleton — überlebt unmount/remount, stirbt mit dem Browser-Tab (bewusst:
// nach Browser-Refresh ist ein Erst-Load korrekt und ehrlich). Kleine LRU-Grenze,
// damit ausgiebiges Monats-/Anlagen-Browsen den Speicher nicht füllt.
const swrCache = new Map<string, unknown>()
const SWR_CACHE_MAX = 50

function swrCacheSet(key: string, value: unknown) {
  // Re-Insert ans Ende = LRU-Reihenfolge über Map-Insertion-Order.
  swrCache.delete(key)
  swrCache.set(key, value)
  if (swrCache.size > SWR_CACHE_MAX) {
    const aeltester = swrCache.keys().next().value
    if (aeltester !== undefined) swrCache.delete(aeltester)
  }
}

/** Nur für Tests: Sicht-Cache leeren (Modul-Singleton). */
export function _clearSwrCacheForTests() {
  swrCache.clear()
}

/**
 * Direkter Lese-/Schreib-Zugriff auf denselben Sicht-Cache — für Sichten mit
 * eigener Poll-Schleife (CockpitLiveV4), wo useApiData nicht passt, der
 * Erst-Paint nach Tab-Wechsel aber trotzdem die letzten Werte zeigen soll
 * (R18-2). EINE Store-Wahrheit, kein zweiter Cache daneben.
 */
export function swrCachePeek<T>(key: string): T | undefined {
  return swrCache.has(key) ? (swrCache.get(key) as T) : undefined
}
export function swrCacheStore(key: string, value: unknown): void {
  swrCacheSet(key, value)
}

interface UseApiDataReturn<T> {
  /** Die geladenen Daten (oder null wenn noch nicht geladen / Fehler). */
  data: T | null
  /** Daten werden geladen — bei `swrKey` NUR wenn kein Cache-Stand existiert (Skeleton-Fall). */
  loading: boolean
  /** Stiller Hintergrund-Refetch läuft (alte Daten bleiben sichtbar; ReloadButton-Spin). */
  reloading: boolean
  /** Fehlermeldung (oder null). Bei vorhandenen Daten bleiben diese stehen. */
  error: string | null
  /** Daten manuell neu laden (bei vorhandenen Daten still, kein Skeleton). */
  refetch: () => Promise<void>
}

interface UseApiDataOptions {
  /** Fetch nur ausführen wenn true (Default: true). */
  enabled?: boolean
  /**
   * SWR-Sicht-Cache-Key (z. B. `aussicht-kurz:${anlageId}`). Muss ALLE Parameter
   * enthalten, die das Ergebnis bestimmen (Anlage, Zeitraum, Horizont, …) —
   * Key-Wechsel ohne Cache-Stand = ehrlicher Erst-Load mit Skeleton.
   */
  swrKey?: string
  /**
   * Bei Key-Wechsel OHNE Cache-Stand die alten Daten stehen lassen und still
   * nachladen (In-Place-Update statt Skeleton) — für Zeitraum-Stepper wie den
   * Monatswechsel (detLAN D7-2): der Block-Stack bleibt stehen und aktualisiert
   * sich. Ohne Cache UND ohne Vordaten bleibt es beim ehrlichen Skeleton.
   */
  keepPreviousData?: boolean
}

/**
 * Generischer async Datenfetch-Hook.
 *
 * @param fetcher - Async Funktion die Daten lädt
 * @param deps - Dependency-Array (bei Änderung wird neu geladen)
 * @param options - Optionen (enabled, swrKey)
 *
 * @example
 * const { data, loading, error } = useApiData(
 *   () => cockpitApi.getUebersicht(anlageId!, year),
 *   [anlageId, year],
 *   { enabled: anlageId != null, swrKey: `cockpit:${anlageId}:${year}` }
 * )
 */
export function useApiData<T>(
  fetcher: () => Promise<T>,
  deps: unknown[],
  options?: UseApiDataOptions,
): UseApiDataReturn<T> {
  const swrKey = options?.swrKey
  const initialCache = swrKey !== undefined && swrCache.has(swrKey)
    ? (swrCache.get(swrKey) as T)
    : undefined
  const [data, setData] = useState<T | null>(initialCache ?? null)
  const [loading, setLoading] = useState(initialCache === undefined)
  const [reloading, setReloading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher
  const swrKeyRef = useRef(swrKey)
  swrKeyRef.current = swrKey
  const dataRef = useRef<T | null>(data)
  dataRef.current = data
  const keepPreviousData = options?.keepPreviousData ?? false
  // Race-Schutz: nur die JÜNGSTE Anfrage schreibt State/Cache (Key-Wechsel oder
  // schneller Doppel-Reload dürfen keinen alten Response hinterherliefern lassen).
  const requestIdRef = useRef(0)

  const enabled = options?.enabled ?? true

  const ladeIntern = useCallback(async (silent: boolean) => {
    if (!enabled) return
    const reqId = ++requestIdRef.current
    const keyBeiStart = swrKeyRef.current
    try {
      silent ? setReloading(true) : setLoading(true)
      setError(null)
      const result = await fetcherRef.current()
      if (reqId !== requestIdRef.current) return
      setData(result)
      if (keyBeiStart !== undefined) swrCacheSet(keyBeiStart, result)
    } catch (e) {
      if (reqId !== requestIdRef.current) return
      // Alte Daten bewusst stehen lassen (SWR: Fehler beim Refetch ≠ Datenverlust).
      setError(e instanceof Error ? e.message : 'Unbekannter Fehler')
    } finally {
      if (reqId === requestIdRef.current) {
        silent ? setReloading(false) : setLoading(false)
      }
    }
  }, [enabled])

  const refetch = useCallback(async () => {
    // Manueller Reload: bei vorhandenem Cache-Stand still (kein Skeleton-Blitz).
    const hit = swrKeyRef.current !== undefined && swrCache.has(swrKeyRef.current)
    await ladeIntern(hit)
  }, [ladeIntern])

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    const hit = swrKey !== undefined && swrCache.has(swrKey)
    const inPlace = !hit && keepPreviousData && dataRef.current != null
    if (swrKey !== undefined) {
      // Key-Wechsel (Anlage/Zeitraum/Horizont): Cache-Stand sofort zeigen; ohne
      // Cache entweder In-Place-Update (keepPreviousData, D7-2) oder ehrlich
      // auf den Skeleton-Fall zurücksetzen.
      if (hit) {
        setData(swrCache.get(swrKey) as T)
        setLoading(false)
      } else if (!inPlace) {
        setData(null)
        setLoading(true)
      }
    }
    ladeIntern(hit || inPlace)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, swrKey])

  return { data, loading, reloading, error, refetch }
}
