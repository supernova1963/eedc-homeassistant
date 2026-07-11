/**
 * AuswertungKopf — gemeinsamer Kopf der Auswertungen-Sub-Sichten: Titel
 * (+ optionale Zusatz-Controls als `children`). Der Jahr-Filter sitzt seit
 * R18-3 (Option B) NICHT mehr hier, sondern als EINE Steuerleiste im
 * Dispatcher (`AuswertungenV4`, Community-Muster) — kein Select je Sicht.
 */
import type { ReactNode } from 'react'

export function AuswertungKopf({ titel, children }: { titel: string; children?: ReactNode }) {
  return (
    <div className="flex items-center justify-between flex-wrap gap-2">
      <h1 className="text-lg font-bold text-gray-900 dark:text-white">{titel}</h1>
      {children && <div className="flex items-center gap-2 flex-wrap">{children}</div>}
    </div>
  )
}
