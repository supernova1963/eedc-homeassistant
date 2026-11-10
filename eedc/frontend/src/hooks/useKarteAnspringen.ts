/**
 * useKarteAnspringen — scrollt zu einer Karte mit `data-karte="<name>"`, sobald sie im DOM steht (#440, gruaGit).
 *
 * **Der Fall.** «Beheben» der Wetterquellen-Prüfung (und jeder Daten-Checker-Link auf die Energieprofil-Pflege)
 * navigiert auf `/einstellungen/daten?block=energieprofil&karte=werkbank`. Der Block klappt auf, die Reparatur-Werkbank
 * liegt aber an seinem Ende — ohne Scroll sah der Anwender auf Notebook und Handy keine Wirkung.
 *
 * **Auch beim wiederholten Klick:** `anlass` ist der `location.key` des Routers. Der HashRouter legt bei jeder
 * Navigation — auch auf dieselbe Adresse — einen neuen Schlüssel an; der Effekt läuft damit bei jedem Klick, nicht nur,
 * wenn sich der Parameter ändert.
 *
 * Die Karte entsteht erst, wenn der Block aufgeklappt ist und sein Inhalt gerendert hat (Lazy-Inhalt, Abrufe). Der
 * Hook wartet darauf in kurzen Schritten, höchstens `WARTEN_MS`; findet er sie nicht, tut er nichts.
 */
import { useEffect } from 'react'

const WARTEN_MS = 5000
const SCHRITT_MS = 100

export function useKarteAnspringen(karte: string | undefined, anlass: string | undefined): void {
  useEffect(() => {
    if (!karte) return
    const bis = Date.now() + WARTEN_MS
    let timer: ReturnType<typeof setTimeout> | undefined
    const suche = () => {
      const el = document.querySelector(`[data-karte="${karte}"]`)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        return
      }
      if (Date.now() < bis) timer = setTimeout(suche, SCHRITT_MS)
    }
    suche()
    return () => { if (timer !== undefined) clearTimeout(timer) }
  }, [karte, anlass])
}
