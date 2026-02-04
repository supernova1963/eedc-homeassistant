/**
 * FormelTooltip - Tooltip zur Anzeige von Berechnungsformeln
 * Zeigt bei Hover über einen Wert die zugrunde liegende Formel und Berechnung an.
 */

import { useState, useRef, useEffect, ReactNode } from 'react'
import { Info } from 'lucide-react'

interface FormelTooltipProps {
  children: ReactNode
  formel: string           // Die Formel als Text, z.B. "Eigenverbrauch × Netzbezugspreis"
  berechnung?: string      // Konkrete Berechnung, z.B. "150 kWh × 0,30 €/kWh"
  ergebnis?: string        // Ergebnis, z.B. "= 45,00 €"
  className?: string
  showIcon?: boolean       // Info-Icon anzeigen (default: true)
}

export default function FormelTooltip({
  children,
  formel,
  berechnung,
  ergebnis,
  className = '',
  showIcon = true
}: FormelTooltipProps) {
  const [isVisible, setIsVisible] = useState(false)
  const [position, setPosition] = useState<'top' | 'bottom'>('top')
  const triggerRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (isVisible && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()
      // Wenn weniger als 120px Platz oben, zeige unten
      setPosition(rect.top < 120 ? 'bottom' : 'top')
    }
  }, [isVisible])

  return (
    <span
      ref={triggerRef}
      className={`relative inline-block cursor-help ${className}`}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {children}

      {/* Info-Icon als Hinweis */}
      {showIcon && (
        <Info className="inline-block w-3.5 h-3.5 ml-1 text-gray-400 opacity-60" />
      )}

      {/* Tooltip */}
      {isVisible && (
        <div
          className={`absolute z-50 px-3 py-2 text-sm bg-gray-900 dark:bg-gray-950 text-white rounded-lg shadow-lg
            ${position === 'top' ? 'bottom-full mb-2' : 'top-full mt-2'}
            left-1/2 -translate-x-1/2
          `}
          style={{ minWidth: '200px', maxWidth: '350px', whiteSpace: 'normal' }}
        >
          {/* Pfeil */}
          <div
            className={`absolute left-1/2 -translate-x-1/2 w-0 h-0
              border-l-[6px] border-l-transparent
              border-r-[6px] border-r-transparent
              ${position === 'top'
                ? 'top-full border-t-[6px] border-t-gray-900 dark:border-t-gray-950'
                : 'bottom-full border-b-[6px] border-b-gray-900 dark:border-b-gray-950'
              }
            `}
          />

          {/* Inhalt */}
          <div className="space-y-1">
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
export function fmtCalc(num: number | null | undefined, decimals = 2): string {
  if (num === null || num === undefined || isNaN(num)) return '?'
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
  const [isVisible, setIsVisible] = useState(false)
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

      setCoords({
        top: position === 'bottom' ? rect.bottom + 6 : rect.top - 6,
        left: rect.left + rect.width / 2
      })
    }
  }, [isVisible, fixedPosition, position])

  return (
    <span
      ref={triggerRef}
      className={`relative inline-block cursor-help ${className}`}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {children}

      {isVisible && (
        <div
          className="fixed z-[9999] px-2 py-1 text-xs bg-gray-800 text-white rounded shadow-lg whitespace-nowrap"
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
