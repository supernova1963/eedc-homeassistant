/**
 * ScrollSchatten — generischer Scroll-Overflow-Schatten (L1, Triage 2026-06-24).
 *
 * Wrappt einen Scroll-Container und blendet je Kante einen halbtransparenten
 * Fade NUR ein, wenn in diese Richtung noch Inhalt scrollbar ist — als Affordanz
 * „hier geht's weiter". **Overflow-getrieben, NICHT breakpoint-gated**
 * ([[feedback_flex_layout_breakpoints]] umgekehrt: hier hängt die Affordanz vom
 * Inhalt × Container ab, nicht vom Viewport) → wirkt automatisch app-weit, mobil
 * UND Desktop (z. B. überlaufende Sub-Tab-Leiste im schmalen Fenster, lange
 * Listen). Erkennung via `ResizeObserver` (Container + Inhalt) + Scroll-Event.
 *
 * Der Fade maskiert den Rand in der **Flächenfarbe** (`fadeFrom`, Default
 * gray-50/gray-900 = Layout-/Leisten-Fläche) → in hell UND dunkel gut sichtbar
 * (ein schwarz-alpha-Schatten verschwindet auf dunklem Grund). Für abweichende
 * Flächen (z. B. Karten = weiß) `fadeFrom` überschreiben.
 *
 * **Rad-Umleitung (A9, Gernot 2026-07-03):** auf NUR horizontal scrollenden
 * Containern (`achse='horizontal'`, kein vertikaler Überlauf) scrollt das
 * normale Mausrad horizontal — ohne sichtbaren Balken wäre das Rad am Desktop
 * sonst wirkungslos (Shift+Rad kennen nur Profis, bleibt nativ erhalten).
 * Höflich wie Scroll-Chaining: am Anfang/Ende wird das Event NICHT abgefangen,
 * die Seite scrollt weiter. Modifier-Gesten bleiben nativ (Strg=Zoom,
 * Shift=horizontal), echte Horizontal-Gesten (Trackpad, deltaX) ebenso.
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'

type Achse = 'horizontal' | 'vertikal' | 'beide'

interface Kanten { top: boolean; bottom: boolean; left: boolean; right: boolean }

export function ScrollSchatten({
  children,
  achse = 'horizontal',
  className = '',
  aussenClassName = '',
  fadeFrom = 'from-gray-50 dark:from-gray-900',
}: {
  children: ReactNode
  /** Welche Richtungen Schatten zeigen dürfen. Default horizontal (Leisten). */
  achse?: Achse
  /** Klassen für den Scroll-Container selbst (Höhe, gap, overflow-Variante …). */
  className?: string
  /** Klassen für den äußeren Positionierungs-Wrapper (Display-Gating wie
   *  `hidden sm:block`, sticky, Außenabstände) — spart die extra Wrapper-Div. */
  aussenClassName?: string
  /** Fade-Grundfarbe = Flächenfarbe der Leiste (Tailwind `from-…`). Default
   *  Layout-/Leisten-Fläche gray-50/gray-900; für Karten `from-white dark:from-gray-800`. */
  fadeFrom?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [k, setK] = useState<Kanten>({ top: false, bottom: false, left: false, right: false })

  const update = useCallback(() => {
    const el = ref.current
    if (!el) return
    setK({
      top: el.scrollTop > 1,
      bottom: el.scrollTop + el.clientHeight < el.scrollHeight - 1,
      left: el.scrollLeft > 1,
      right: el.scrollLeft + el.clientWidth < el.scrollWidth - 1,
    })
  }, [])

  useEffect(() => {
    const el = ref.current
    if (!el) return
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    if (el.firstElementChild) ro.observe(el.firstElementChild) // Inhalts-Größenänderung
    el.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', update)
    return () => {
      ro.disconnect()
      el.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
    }
  }, [update])

  // Rad-Umleitung (s. Docblock): non-passiv, weil preventDefault nötig ist.
  useEffect(() => {
    const el = ref.current
    if (!el || achse !== 'horizontal') return
    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.shiftKey || e.altKey || e.metaKey) return
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return
      if (el.scrollWidth <= el.clientWidth) return
      if (el.scrollHeight > el.clientHeight) return // vertikal scrollbar → Rad bleibt vertikal
      // deltaMode 1 = Zeilen (Firefox-Mausrad) → auf Pixel normieren.
      const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY
      const kannWeiter = delta > 0
        ? el.scrollLeft + el.clientWidth < el.scrollWidth - 1
        : el.scrollLeft > 1
      if (!kannWeiter) return
      e.preventDefault()
      el.scrollLeft += delta
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [achse])

  const horiz = achse === 'horizontal' || achse === 'beide'
  const vert = achse === 'vertikal' || achse === 'beide'
  // Fade maskiert den Rand in der Flächenfarbe (from-…) → transparent nach innen.
  const fade = `pointer-events-none absolute z-10 to-transparent transition-opacity ${fadeFrom}`

  return (
    <div className={`relative ${aussenClassName}`}>
      <div ref={ref} className={`overflow-auto scrollbar-none ${className}`}>{children}</div>
      {/* D5-2 (detLAN): breiterer, weicher Fade → erkennbarer als Scroll-Affordanz,
          aber durch die Flächenfarben-Maske nicht aufdringlich (Gernot: „erkennbarer,
          nicht auffälliger"). Etwas größere Fläche (h-7/w-12) liest sich klarer. */}
      {vert && <div className={`${fade} inset-x-0 top-0 h-7 bg-gradient-to-b ${k.top ? 'opacity-100' : 'opacity-0'}`} />}
      {vert && <div className={`${fade} inset-x-0 bottom-0 h-7 bg-gradient-to-t ${k.bottom ? 'opacity-100' : 'opacity-0'}`} />}
      {horiz && <div className={`${fade} inset-y-0 left-0 w-12 bg-gradient-to-r ${k.left ? 'opacity-100' : 'opacity-0'}`} />}
      {horiz && <div className={`${fade} inset-y-0 right-0 w-12 bg-gradient-to-l ${k.right ? 'opacity-100' : 'opacity-0'}`} />}
    </div>
  )
}

export default ScrollSchatten
