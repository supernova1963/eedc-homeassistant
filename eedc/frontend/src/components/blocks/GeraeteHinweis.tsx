/**
 * GeraeteHinweis — dezenter „aggregiert aus …"-Hinweis für Blöcke, die mehrere
 * Geräte zu einer Summe zusammenfassen (z. B. PV aus mehreren Strings + WR,
 * E-Mobilität aus Auto + Wallbox). Listet die Einzel-Geräte beim Namen; erscheint
 * nur ab 2 Geräten. Die Per-Gerät-WERTE bleiben bewusst der Komponenten-Achse
 * (Deep-Dive) vorbehalten — hier nur die Zusammensetzung.
 *
 * SoT-Komponente: überall dieselbe Bildsprache (eine Klasse = eine Komponente).
 */
import { Layers } from 'lucide-react'

export function GeraeteHinweis({ namen, label = 'Aggregiert aus', minAnzahl = 2 }: {
  namen: string[]
  label?: string
  /** Ab wie vielen Namen die Zeile erscheint. Default 2 (Aggregations-Fall: bei
   *  einem Gerät ist die Summe das Gerät). #350 nennt dagegen die Geräte **ohne**
   *  eigene Tageswerte — dort zählt schon **ein** fehlendes, weil es eine
   *  Spalte ist, die der Anwender sonst vergeblich sucht. */
  minAnzahl?: number
}) {
  if (namen.length < minAnzahl) return null
  return (
    <p className="flex items-start gap-1.5 text-xs text-gray-400 dark:text-gray-500">
      <Layers className="h-3.5 w-3.5 shrink-0 mt-0.5" aria-hidden="true" />
      <span>{label}: {namen.join(' · ')}</span>
    </p>
  )
}
