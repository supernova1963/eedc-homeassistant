import { useEffect } from 'react'

/**
 * Globaler Touch-Support für HTML title=""-Attribute.
 *
 * Browser zeigen title-Tooltips nur bei Hover (Desktop), nicht bei Touch (Mobile).
 * Dieser Hook registriert einmalig einen document-weiten Touch-Handler:
 *   - touchstart: Element-Baum nach title-Attribut absuchen → Tooltip anzeigen
 *   - touchend / touchmove: Tooltip ausblenden
 *
 * Einmalig in App.tsx aufrufen — wirkt automatisch auf alle Seiten.
 */
export function useTouchTitleTooltip() {
  useEffect(() => {
    let tooltip: HTMLDivElement | null = null

    const hide = () => {
      tooltip?.remove()
      tooltip = null
    }

    const show = (text: string, touchX: number, touchY: number) => {
      hide()
      tooltip = document.createElement('div')
      tooltip.textContent = text
      Object.assign(tooltip.style, {
        position: 'fixed',
        zIndex: '10000',
        background: '#1f2937',
        color: 'white',
        padding: '5px 10px',
        borderRadius: '4px',
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
    }

    const onTouchStart = (e: TouchEvent) => {
      let el = e.target as HTMLElement | null
      while (el && el !== document.body) {
        const title = el.getAttribute('title')
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

    document.addEventListener('touchstart', onTouchStart, { passive: true })
    document.addEventListener('touchend', hide, { passive: true })
    document.addEventListener('touchmove', hide, { passive: true })

    return () => {
      document.removeEventListener('touchstart', onTouchStart)
      document.removeEventListener('touchend', hide)
      document.removeEventListener('touchmove', hide)
      hide()
    }
  }, [])
}
