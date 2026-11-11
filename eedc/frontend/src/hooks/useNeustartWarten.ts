/**
 * useNeustartWarten — nach «Neustart» (System → Protokolle) auf eedc warten (E5.7 L5, Lab rc29: der Knopf drehte endlos,
 * bis der Anwender die Seite neu lud). Nach dem Aufruf fragt der Hook `/api/health` alle 2 s, höchstens 90 s lang: meldet
 * eedc `healthy`, lädt die Seite neu; nach Ablauf steht der Satz da und der Knopf ist wieder frei.
 */
import { useEffect, useRef, useState } from 'react'
import { systemApi } from '../api/system'

export const NEUSTART_TAKT_MS = 2000
export const NEUSTART_HOECHSTENS_MS = 90000
export const NEUSTART_ZU_LANG = 'Der Neustart dauert länger als erwartet — Seite neu laden.'

export function useNeustartWarten(neuLaden: () => void = () => window.location.reload()) {
  const [wartet, setWartet] = useState(false)
  const [hinweis, setHinweis] = useState<string | null>(null)
  const uhr = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopp = () => {
    if (uhr.current) clearInterval(uhr.current)
    uhr.current = null
  }
  useEffect(() => stopp, [])

  const warten = () => {
    stopp()
    setHinweis(null)
    setWartet(true)
    const beginn = Date.now()
    uhr.current = setInterval(async () => {
      if (Date.now() - beginn >= NEUSTART_HOECHSTENS_MS) {
        stopp()
        setWartet(false)
        setHinweis(NEUSTART_ZU_LANG)
        return
      }
      try {
        if ((await systemApi.health()).status === 'healthy') {
          stopp()
          neuLaden()
        }
      } catch { /* eedc startet noch */ }
    }, NEUSTART_TAKT_MS)
  }

  return { wartet, hinweis, warten }
}
