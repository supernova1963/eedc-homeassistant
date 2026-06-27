import { useSyncExternalStore } from 'react'

/**
 * useSchmaleAchse — true bei schmalem Viewport (< Tailwind `sm` = 640 px, i. d. R.
 * Mobile). Genutzt, um die X-Achsen-Beschriftung von Zeitreihen-Charts dort 90° zu
 * drehen, damit lange Labels (Monat/Tag/Datum) nicht überlappen (detLAN R7/D7-5).
 *
 * Reaktiv auf Resize/Orientierung via `matchMedia`. SSR/Test-Default: false.
 */
const QUERY = '(max-width: 639px)'

function subscribe(cb: () => void): () => void {
  if (typeof window === 'undefined' || !window.matchMedia) return () => {}
  const mql = window.matchMedia(QUERY)
  mql.addEventListener('change', cb)
  return () => mql.removeEventListener('change', cb)
}

export function useSchmaleAchse(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => (typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia(QUERY).matches),
    () => false,
  )
}
