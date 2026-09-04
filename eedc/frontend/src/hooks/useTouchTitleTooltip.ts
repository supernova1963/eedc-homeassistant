import { useEffect } from 'react'
import { TOOLTIP_FARBEN, Z_TOOLTIP } from '../lib'

/** Wie lange ein Touch-Tooltip ohne weitere Geste stehen bleibt (N-390).
 *  Sechs Sekunden reichen für die längste vorkommende Auskunft (der Haus-Knoten
 *  des Energieflusses, sieben Zeilen) und sind kurz genug, dass nichts über einer
 *  gewechselten Ansicht kleben bleibt. */
const AUTO_HIDE_MS = 6000

/**
 * Globaler Touch-Support für HTML title=""-Attribute.
 *
 * Browser zeigen title-Tooltips nur bei Hover (Desktop), nicht bei Touch (Mobile).
 * Dieser Hook registriert einmalig einen document-weiten Touch-Handler:
 *   - touchstart: Element-Baum nach title/data-title absuchen → Tooltip anzeigen;
 *                 ohne Treffer schließt er einen offenen Tooltip
 *   - touchmove:  Tooltip ausblenden (Scroll/Pan ist keine Leseabsicht)
 *   - Auto-Timeout als Rückfalltür
 *
 * Einmalig in App.tsx aufrufen — wirkt automatisch auf alle Seiten.
 *
 * ⛔ **`touchend` blendet NICHT mehr aus (N-390, 2026-09-04), und das ist der Kern
 * des Fundes.** Bis dahin verschwand der Tooltip in dem Moment, in dem der Finger
 * sich hob — bei einem mehrzeiligen Text (der Haus-Knoten des Energieflusses hat
 * sieben Zeilen) also **bevor** man ihn lesen konnte. Der Anwender ließ den Finger
 * deshalb liegen, und genau darauf wartete die Park-Geste: nach 500 ms legte sich
 * das Park-Overlay über die Fläche. **Wer lesen wollte, landete im Park-Modus.**
 *
 * ⚑ **Die Staffelung war dabei nie kaputt** — `Parkbar.onTouchEnd` bricht ihren
 * Timer ab, ein kurzer Tap hat also nie geparkt. Es fehlte allein das Zeitfenster
 * zum Lesen. Deshalb sitzt diese Hälfte des Fixes hier und nicht in der Parkbar
 * (dort sitzt die andere: die Geste greift nur noch in der Kopf-Zone).
 *
 * ⚠ **Warum kein zusätzliches Schließen-Kreuz:** Der Tooltip ist `pointerEvents:
 * none` und schließt beim nächsten Tap ohnehin (`onTouchStart` ruft ohne Treffer
 * `hide`). Ein Bedienelement darauf wäre eine neue Bauform neben `FormelTooltip`
 * und `SimpleTooltip` — die Hausregel kennt zwei, nicht drei.
 */
export function useTouchTitleTooltip() {
  useEffect(() => {
    let tooltip: HTMLDivElement | null = null
    let autoHide: ReturnType<typeof setTimeout> | null = null

    const hide = () => {
      if (autoHide) { clearTimeout(autoHide); autoHide = null }
      tooltip?.remove()
      tooltip = null
    }

    const show = (text: string, touchX: number, touchY: number) => {
      hide()
      tooltip = document.createElement('div')
      tooltip.textContent = text
      Object.assign(tooltip.style, {
        position: 'fixed',
        zIndex: String(Z_TOOLTIP),
        background: TOOLTIP_FARBEN.bg,
        color: 'white',
        padding: '5px 10px',
        borderRadius: '8px',  // Tooltip-Kanon (P3): rounded-lg
        fontSize: '12px',
        lineHeight: '1.4',
        maxWidth: '260px',
        wordBreak: 'break-word',
        pointerEvents: 'none',
        boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
        // Vorläufige Position — wird nach DOM-Einfügen korrigiert
        top: '0',
        left: '0',
      })
      document.body.appendChild(tooltip)

      // Position nach dem Einfügen berechnen (echte Größe bekannt)
      const rect = tooltip.getBoundingClientRect()
      const top = Math.max(8, touchY - rect.height - 12)
      const left = Math.min(
        Math.max(8, touchX - rect.width / 2),
        window.innerWidth - rect.width - 8
      )
      tooltip.style.top = `${top}px`
      tooltip.style.left = `${left}px`

      // Rückfalltür: Der Tooltip bleibt nach dem Loslassen stehen, damit er lesbar
      // ist — aber nicht endlos. Regulär schließt ihn der nächste Tap oder ein
      // Scroll; dieser Timeout fängt den Fall, in dem beides ausbleibt (Sicht
      // gewechselt, Gerät weggelegt), sonst klebte er über der nächsten Ansicht.
      autoHide = setTimeout(hide, AUTO_HIDE_MS)
    }

    const onTouchStart = (e: TouchEvent) => {
      let el = e.target as HTMLElement | null
      while (el && el !== document.body) {
        const title = el.getAttribute('data-title') || el.getAttribute('title')
        if (title) {
          const touch = e.touches[0]
          show(title, touch.clientX, touch.clientY)
          return
        }
        el = el.parentElement
      }
      // Kein title-Element gefunden → offenen Tooltip schließen
      hide()
    }

    // ⛔ KEIN `touchend` mehr (N-390) — s. Kopftext. Der Tooltip bleibt stehen,
    // bis der nächste Tap kommt (`onTouchStart` ohne Treffer), gescrollt wird
    // oder der Auto-Timeout greift.
    document.addEventListener('touchstart', onTouchStart, { passive: true })
    document.addEventListener('touchmove', hide, { passive: true })

    return () => {
      document.removeEventListener('touchstart', onTouchStart)
      document.removeEventListener('touchmove', hide)
      hide()
    }
  }, [])
}
