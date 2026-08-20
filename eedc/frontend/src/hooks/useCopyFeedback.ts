/**
 * useCopyFeedback — Text in die Zwischenablage, mit kurzer Bestätigung.
 *
 * SoT für „Kopieren" (Regel 0a): Bis 2026-08-20 lag die Logik zweimal inline
 * (`ProtokolleTeile.tsx` als lokaler Hook, `HAExportSettingsTeile.tsx` als
 * Funktion mit `execCommand`-Fallback). Die dritte Stelle (MQTT-Topic-Liste in
 * `DatenquellenZuordnung`) war der Anlass, sie zusammenzuziehen — dieselbe
 * Klasse wie N-138 (drei Inline-Kopien → eine Komponente).
 *
 * Der `execCommand`-Fallback stammt aus der HA-Export-Fassung und gilt jetzt für
 * alle Aufrufer: `navigator.clipboard` fehlt in unsicheren Kontexten (http auf
 * einer LAN-IP) — genau der Normalfall einer Add-on-Installation.
 */
import { useState, useCallback, useRef, useEffect } from 'react'

/** Wie lange die Bestätigung stehen bleibt (ms). */
const FEEDBACK_MS = 2000

export function useCopyFeedback(dauerMs: number = FEEDBACK_MS) {
  /** Zuletzt kopierte Kennung — `true`/Marke = gerade bestätigt. */
  const [kopiert, setKopiert] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current)
  }, [])

  /**
   * Kopiert `text`. `marke` unterscheidet mehrere Kopier-Knöpfe auf einer
   * Fläche (z. B. je Zeile); ohne Angabe gilt die Sammelmarke `'default'`.
   */
  const kopiere = useCallback(async (text: string, marke: string = 'default') => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Fallback: kein `navigator.clipboard` (unsicherer Kontext / alter Browser).
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'absolute'
      textarea.style.left = '-9999px'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    setKopiert(marke)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => setKopiert(null), dauerMs)
  }, [dauerMs])

  /** Ist genau diese Marke gerade bestätigt? */
  const istKopiert = useCallback((marke: string = 'default') => kopiert === marke, [kopiert])

  return { kopiert, istKopiert, kopiere }
}

export default useCopyFeedback
