/**
 * FormelTooltip - Tooltip zur Anzeige von Berechnungsformeln
 * Zeigt bei Hover über einen Wert die zugrunde liegende Formel und Berechnung an.
 */

import { useState, useRef, useEffect, useLayoutEffect, ReactNode } from 'react'
import { Info } from 'lucide-react'

/**
 * Zentralisierte Tooltip-Interaktionslogik (Desktop + Mobile).
 * - Desktop: onMouseEnter/Leave
 * - Mobile:  onClick toggle + document-click schließt
 */
function useTooltipInteraction() {
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    if (!isVisible) return
    const close = () => setIsVisible(false)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [isVisible])

  const interactionProps = {
    onMouseEnter: () => setIsVisible(true),
    onMouseLeave: () => setIsVisible(false),
    onClick: (e: React.MouseEvent) => { e.stopPropagation(); setIsVisible(v => !v) },
  }

  return { isVisible, setIsVisible, interactionProps }
}

interface FormelTooltipProps {
  children: ReactNode
  formel: string           // Die Formel als Text, z.B. "Eigenverbrauch × Netzbezugspreis"
  berechnung?: string      // Konkrete Berechnung, z.B. "150 kWh × 0,30 €/kWh"
  ergebnis?: string        // Ergebnis, z.B. "= 45,00 €"
  sicht?: string           // ROI-Sicht zur Einordnung, z.B. "Gesamt-Anlage, Prognose"
  className?: string
  showIcon?: boolean       // Info-Icon anzeigen (default: true)
}

export default function FormelTooltip({
  children,
  formel,
  berechnung,
  ergebnis,
  sicht,
  className = '',
  showIcon = true
}: FormelTooltipProps) {
  const { isVisible, interactionProps } = useTooltipInteraction()
  const [position, setPosition] = useState<'top' | 'bottom'>('top')
  const [coords, setCoords] = useState({ top: 0, left: 0 })
  const [measured, setMeasured] = useState(false)
  const triggerRef = useRef<HTMLSpanElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)

  // Tooltip wird via position:fixed gerendert, damit overflow-x:auto-Container
  // (z.B. Tabellen) ihn nicht clippen und horizontalen Scroll auslösen.
  // Breite wird nach dem ersten Render am DOM gemessen, damit der Viewport-Clamp
  // mit der echten Tooltip-Breite rechnet (statt hardcoded 280 — Forum #362).
  useLayoutEffect(() => {
    if (!isVisible) { setMeasured(false); return }
    if (!triggerRef.current || !tooltipRef.current) return
    const triggerRect = triggerRef.current.getBoundingClientRect()
    const tooltipWidth = tooltipRef.current.offsetWidth
    const showBelow = triggerRect.top < 140
    const padding = 8
    let left = triggerRect.left + triggerRect.width / 2
    if (left - tooltipWidth / 2 < padding) left = tooltipWidth / 2 + padding
    const vw = window.innerWidth
    if (left + tooltipWidth / 2 > vw - padding) left = vw - tooltipWidth / 2 - padding
    setPosition(showBelow ? 'bottom' : 'top')
    setCoords({
      top: showBelow ? triggerRect.bottom + 8 : triggerRect.top - 8,
      left,
    })
    setMeasured(true)
  }, [isVisible])

  return (
    <span
      ref={triggerRef}
      className={`relative inline-block cursor-help ${className}`}
      {...interactionProps}
    >
      {children}

      {/* Info-Icon als Hinweis — auf Mobile ausgeblendet (kein Hover, knapper Platz) */}
      {showIcon && (
        <Info className="hidden sm:inline-block w-3.5 h-3.5 ml-1 text-gray-400 opacity-60" />
      )}

      {/* Tooltip — fixed positioniert, damit overflow-Container nicht clippen */}
      {isVisible && (
        <div
          ref={tooltipRef}
          className="fixed z-50 px-3 py-2 text-sm bg-gray-900 dark:bg-gray-950 text-white rounded-lg shadow-lg pointer-events-none"
          style={{
            minWidth: '200px',
            maxWidth: '350px',
            whiteSpace: 'normal',
            left: coords.left,
            top: position === 'bottom' ? coords.top : 'auto',
            bottom: position === 'top' ? `calc(100vh - ${coords.top}px)` : 'auto',
            transform: 'translateX(-50%)',
            visibility: measured ? 'visible' : 'hidden',
          }}
        >
          {/* Inhalt */}
          <div className="space-y-1">
            {sicht && (
              <>
                <div className="font-medium text-purple-300 text-xs uppercase tracking-wide">
                  Sicht
                </div>
                <div className="text-gray-100 text-xs italic">
                  {sicht}
                </div>
                <div className="border-t border-gray-700 pt-1 mt-1" />
              </>
            )}
            <div className="font-medium text-yellow-300 text-xs uppercase tracking-wide">
              Formel
            </div>
            <div className="text-gray-100">
              {formel}
            </div>

            {berechnung && (
              <>
                <div className="font-medium text-blue-300 text-xs uppercase tracking-wide mt-2">
                  Berechnung
                </div>
                <div className="text-gray-200 font-mono text-xs">
                  {berechnung}
                </div>
              </>
            )}

            {ergebnis && (
              <div className="text-green-300 font-semibold mt-1 border-t border-gray-700 pt-1">
                {ergebnis}
              </div>
            )}
          </div>
        </div>
      )}
    </span>
  )
}

/**
 * Hilfsfunktion zum Formatieren von Zahlen in Tooltips
 */
export function fmtCalc(num: number | null | undefined, decimals = 2, fallback = '?'): string {
  if (num === null || num === undefined || isNaN(num)) return fallback
  return num.toLocaleString('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  })
}

/**
 * SimpleTooltip - Vereinfachte Variante nur mit Text
 */
interface SimpleTooltipProps {
  children: ReactNode
  text: string
  className?: string
  position?: 'auto' | 'top' | 'bottom'
}

export function SimpleTooltip({
  children,
  text,
  className = '',
  position: fixedPosition = 'auto'
}: SimpleTooltipProps) {
  const { isVisible, interactionProps } = useTooltipInteraction()
  const [position, setPosition] = useState<'top' | 'bottom'>('bottom')
  const [coords, setCoords] = useState({ top: 0, left: 0 })
  const triggerRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (isVisible && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()

      if (fixedPosition === 'auto') {
        setPosition(rect.top < 60 ? 'bottom' : 'top')
      } else {
        setPosition(fixedPosition)
      }

      // Edge-Clamp: Tooltip-Mitte (max. 160px halbe Breite bei max-w-xs/320px) im Viewport halten,
      // mind. 8px Abstand zu den Rändern.
      const halfWidth = 160
      const margin = 8
      const idealLeft = rect.left + rect.width / 2
      const clampedLeft = Math.max(
        halfWidth + margin,
        Math.min(idealLeft, window.innerWidth - halfWidth - margin)
      )

      setCoords({
        top: position === 'bottom' ? rect.bottom + 6 : rect.top - 6,
        left: clampedLeft
      })
    }
  }, [isVisible, fixedPosition, position])

  return (
    <span
      ref={triggerRef}
      className={`relative inline-block cursor-help ${className}`}
      {...interactionProps}
    >
      {children}

      {isVisible && (
        <div
          className="fixed z-[9999] px-2 py-1 text-xs bg-gray-800 text-white rounded shadow-lg max-w-xs whitespace-normal break-words"
          style={{
            top: position === 'bottom' ? coords.top : 'auto',
            bottom: position === 'top' ? `calc(100vh - ${coords.top}px)` : 'auto',
            left: coords.left,
            transform: 'translateX(-50%)'
          }}
        >
          {text}
          <div
            className={`absolute left-1/2 -translate-x-1/2 w-0 h-0
              border-l-[4px] border-l-transparent
              border-r-[4px] border-r-transparent
              ${position === 'top'
                ? 'top-full border-t-[4px] border-t-gray-800'
                : 'bottom-full border-b-[4px] border-b-gray-800'
              }`}
          />
        </div>
      )}
    </span>
  )
}
