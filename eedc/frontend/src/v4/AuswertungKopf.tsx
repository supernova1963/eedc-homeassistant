/**
 * AuswertungKopf — gemeinsamer Kopf der Auswertungen-Sub-Sichten: Titel + Jahr-
 * Filter (+ optionale Zusatz-Controls als `children`, z. B. Vergleichsjahr).
 * Hält die Sub-Sichten optisch konsistent (Muster), ohne den Select je Sicht zu
 * duplizieren.
 */
import type { ReactNode } from 'react'

export function AuswertungKopf({
  titel, jahr, setJahr, jahre, children,
}: {
  titel: string
  jahr: number | 'alle'
  setJahr: (j: number | 'alle') => void
  jahre: number[]
  children?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between flex-wrap gap-2">
      <h1 className="text-lg font-bold text-gray-900 dark:text-white">{titel}</h1>
      <div className="flex items-center gap-2 flex-wrap">
        {children}
        <select
          value={jahr === 'alle' ? '' : jahr}
          onChange={(e) => setJahr(e.target.value ? Number(e.target.value) : 'alle')}
          aria-label="Jahr filtern"
          className="input w-auto"
        >
          <option value="">Alle Jahre</option>
          {jahre.map((j) => <option key={j} value={j}>{j}</option>)}
        </select>
      </div>
    </div>
  )
}
