/**
 * useScrollErhalt — Scroll-Position beim Zeitraum-Wechsel halten (B1, v3-Regression).
 *
 * Beim Wechsel von Tag/Monat/Jahr kollabiert der Inhalt kurz auf einen
 * Lade-Spinner → der umgebende Scroll-Container klemmt seinen `scrollTop` auf 0,
 * danach mountet die Block-Liste mit neuem `key` frisch → die Seite springt nach
 * oben. In v3 war das gelöst (MonatsabschlussView, #182). Dieser Hook stellt das
 * Verhalten für die v4-Cockpit-Zeitsichten generisch wieder her.
 *
 * Anders als in v3 ist der Scroll-Container in v4 nicht fix `main` (mobil), sondern
 * ab `lg` der ViewShell-Innencontainer — er wird daher vom `ref`-Element aus nach
 * oben gesucht. `merke()` vor dem State-Wechsel aufrufen (Scroll-Position sichern);
 * die Wiederherstellung läuft per `useLayoutEffect` VOR dem Paint, sobald `signal`
 * (das geladene Datenobjekt bzw. der `loading`-Flip) wechselt.
 */
import { useCallback, useLayoutEffect, useRef } from 'react'
import type { RefObject } from 'react'

function findeScrollContainer(start: HTMLElement | null): HTMLElement | null {
  let el: HTMLElement | null = start
  while (el) {
    const oy = getComputedStyle(el).overflowY
    if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight) return el
    el = el.parentElement
  }
  return null
}

export function useScrollErhalt(ref: RefObject<HTMLElement>, signal: unknown): () => void {
  const restoreRef = useRef<number | null>(null)

  const merke = useCallback(() => {
    const c = findeScrollContainer(ref.current)
    restoreRef.current = c?.scrollTop ?? null
  }, [ref])

  // Erst nach dem Daten-Reload wiederherstellen (Inhalt wieder hoch → scrollTop
  // hält). useLayoutEffect läuft vor dem Browser-Paint → kein sichtbares Springen.
  useLayoutEffect(() => {
    if (restoreRef.current === null) return
    const c = findeScrollContainer(ref.current)
    if (c && c.scrollHeight > c.clientHeight) {
      c.scrollTop = restoreRef.current
      restoreRef.current = null
    }
  }, [signal, ref])

  return merke
}
