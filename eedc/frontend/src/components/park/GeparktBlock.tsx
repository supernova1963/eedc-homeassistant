/**
 * GeparktBlock — der „Parkplatz (n)" am Fuß einer Sicht (Sammelzone für geparkte
 * Elemente, passend zur Aktion „parken").
 *
 * Nur sichtbar bei n > 0, eingeklappt-default. Je geparktem Element ein Chip
 * (Titel) → ANTIPPEN holt es an seine feste kanonische Position zurück (Chip-Tap,
 * Gernot-Abnahme 2026-06-25). Plus „alles zurückholen".
 *
 * KEIN BlockShell-Block (nicht verschiebbar/parkbar/in der Block-Order) — eine
 * schlichte, feste, einklappbare Section.
 *
 * SoT: docs/drafts/SPEC-ELEMENT-LAYOUT-PAPIERKORB.md
 */
import { useState } from 'react'
import { ChevronDown, RotateCcw, ParkingSquare, Undo2 } from 'lucide-react'
import { usePark } from './ParkContext'

export function GeparktBlock() {
  const park = usePark()
  const [offen, setOffen] = useState(false)

  if (!park.aktiv || park.geparkt.length === 0) return null
  const n = park.geparkt.length

  // D7-4: optisch als seitenbezogene Zone abgesetzt (gestrichelter Rahmen + gedämpfter
  // Grund) — NICHT der solide Karten-Look eines Inhalts-Blocks, damit die Sonderbreite/
  // Funktion (block-übergreifend) als gewollt liest.
  return (
    <section className="rounded-lg border border-dashed border-gray-300 dark:border-gray-600 bg-gray-100/50 dark:bg-gray-800/30 overflow-hidden">
      <div className="flex items-center gap-2 px-3 min-h-[44px]">
        <button
          type="button"
          onClick={() => setOffen((o) => !o)}
          className="flex-1 flex items-center gap-2 text-left py-2 min-w-0"
        >
          <ParkingSquare className="h-4 w-4 flex-shrink-0 text-gray-400 dark:text-gray-500" />
          <span className="text-sm font-semibold text-gray-900 dark:text-white whitespace-nowrap">
            Parkplatz ({n})
          </span>
          <span className="text-xs text-gray-400 dark:text-gray-500 truncate">
            ausgeblendete Anzeigen · antippen holt zurück
          </span>
        </button>
        <button
          type="button"
          onClick={park.zuruecksetzen}
          className="flex-shrink-0 inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
        >
          <RotateCcw className="h-3.5 w-3.5" /> alles zurückholen
        </button>
        <button
          type="button"
          onClick={() => setOffen((o) => !o)}
          aria-label={offen ? 'einklappen' : 'aufklappen'}
          className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
        >
          <ChevronDown className={`h-4 w-4 transition-transform ${offen ? '' : '-rotate-90'}`} />
        </button>
      </div>
      {offen && (
        <div className="px-3 pb-3 flex flex-wrap gap-2">
          {park.geparkt.map((e) => (
            <button
              key={e.id}
              type="button"
              onClick={() => park.entparke(e.id)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700/40 px-2.5 py-1.5 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              <Undo2 className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
              {e.titel}
            </button>
          ))}
        </div>
      )}
    </section>
  )
}
