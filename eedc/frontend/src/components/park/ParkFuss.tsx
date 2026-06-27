/**
 * ParkFuss — Sicht-Fußzeile der Element-Park-Ebene: dezente Hinweiszeile
 * (Discoverability der versteckten Geste, Gernot-Abnahme 2026-06-25) + der
 * {@link GeparktBlock} („Geparkt (n)"). Eine Komponente pro v4-Sicht ans Ende.
 *
 * Inert ohne ParkProvider (`!aktiv`) → rendert nichts (Produktion/v3).
 *
 * SoT: docs/drafts/SPEC-ELEMENT-LAYOUT-PAPIERKORB.md
 */
import { MousePointerClick } from 'lucide-react'
import { usePark } from './ParkContext'
import { GeparktBlock } from './GeparktBlock'

export function ParkFuss() {
  const park = usePark()
  if (!park.aktiv) return null
  return (
    <div className="space-y-3">
      <GeparktBlock />
      <p className="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1.5 px-1">
        <MousePointerClick className="h-3 w-3 flex-shrink-0" />
        <span>
          Tipp: eine Anzeige lange drücken (Rechtsklick) → auf den Parkplatz.
        </span>
      </p>
    </div>
  )
}
