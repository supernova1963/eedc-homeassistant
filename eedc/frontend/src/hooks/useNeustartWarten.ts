/**
 * useNeustartWarten — nach «Neustart» (System → Protokolle) auf eedc warten (E5.7 L5, Lab rc29: der Knopf drehte endlos,
 * bis der Anwender die Seite neu lud). Nach dem Aufruf fragt der Hook `/api/health` alle 2 s, höchstens 90 s lang: meldet
 * eedc `healthy`, lädt die Seite neu; nach Ablauf steht der Satz da und der Knopf ist wieder frei.
 *
 * E6.B G1 (Lab rc32 Nr. 8: «dauert ohne Hinweis auf Aktivität etwas, dann blitzt es kurz»): `warten(aufruf)` setzt
 * `wartet` **vor** dem Neustart-Aufruf — Knopf und Satz `NEUSTART_LAEUFT` stehen ab dem ersten Moment, auch solange der
 * Aufruf im Add-on auf den Supervisor wartet. Gefragt wird erst, wenn der Aufruf zurück ist (oder die Verbindung brach):
 * vorher antwortet noch das alte eedc `healthy`, und die Seite lüde neu, bevor der Neustart begonnen hat.
 */
import { useEffect, useRef, useState } from 'react'
import { systemApi } from '../api/system'

export const NEUSTART_TAKT_MS = 2000
export const NEUSTART_HOECHSTENS_MS = 90000
export const NEUSTART_ZU_LANG = 'Der Neustart dauert länger als erwartet — Seite neu laden.'
export const NEUSTART_LAEUFT = 'eedc startet neu — die Seite lädt gleich von selbst.'

export function useNeustartWarten(neuLaden: () => void = () => window.location.reload()) {
  const [wartet, setWartet] = useState(false)
  const [hinweis, setHinweis] = useState<string | null>(null)
  const uhr = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopp = () => {
    if (uhr.current) clearInterval(uhr.current)
    uhr.current = null
  }
  useEffect(() => stopp, [])

  const warten = async (aufruf?: () => Promise<unknown>) => {
    stopp()
    setHinweis(null)
    setWartet(true)
    if (aufruf) {
      try { await aufruf() } catch { /* Verbindung bricht ab — erwartet */ }
    }
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
