/**
 * HerkunftZeile — DIE Kopfzeile für „woher kommen diese Zahlen?".
 *
 * Zustands-Badge (`ErfassungZustandBadge`, iconOnly) + optionale Überschrift/
 * Bezugs-Label + Erklärsatz darunter. Eine Komponente, weil die Zeile mit A4
 * an der dritten Stelle gebraucht wurde (Verteilungsbalken · Verlauf-Chart im
 * Komponenten-Hub · PV-String-Vergleich) und dreimal dasselbe Markup daneben zu
 * stellen genau der Drift ist, den Regel 0a verhindert: Text kam schon aus einer
 * Quelle ({@link WertHerkunft}), das Markup nicht.
 *
 * Rendert nichts, wenn weder Titel noch Herkunft gesetzt sind.
 */
import { Link } from 'react-router-dom'
import ErfassungZustandBadge from '../ui/ErfassungZustandBadge'
import type { WertHerkunft } from './types'

/** Überschriften-Typografie der Zeile — geteilt von Titel und Bezugs-Label. */
const LABEL = 'text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider'

export function HerkunftZeile({ herkunft, titel, ziel, className = '' }: {
  herkunft?: WertHerkunft
  /** Überschrift links vom Badge (z. B. der Titel des Verteilungsbalkens). */
  titel?: string
  /** N-799 (E-11 b/c): Link hinter dem Erklärsatz — der Befund im Daten-Checker, der die Herkunft erklärt. */
  ziel?: { pfad: string; text: string }
  className?: string
}) {
  if (!titel && !herkunft) return null
  return (
    <div className={`space-y-1 ${className}`}>
      <div className="flex items-center gap-1.5">
        {titel && <p className={LABEL}>{titel}</p>}
        {herkunft && (
          <ErfassungZustandBadge zustand={herkunft.zustand} quelleLabel={herkunft.quelleLabel} iconOnly />
        )}
        {herkunft?.bezug && <span className={LABEL}>{herkunft.bezug}</span>}
      </div>
      {herkunft?.hinweis && (
        <p className="text-xs text-gray-400 dark:text-gray-500">
          {herkunft.hinweis}
          {ziel && <>{' '}<Link to={ziel.pfad} className="underline hover:text-gray-600 dark:hover:text-gray-300">{ziel.text}</Link></>}
        </p>
      )}
    </div>
  )
}

export default HerkunftZeile
