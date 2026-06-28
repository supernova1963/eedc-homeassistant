/**
 * Parkbar — umhüllt EIN parkbares Element (KPICard, Chart, Tabelle …).
 *
 * Geste (kein sichtbares Icon, Affordanz = die Geste):
 *  • Desktop: Rechtsklick (contextmenu, preventDefault) → Park-Overlay
 *  • Mobil:   Long-Press (~500 ms, Bewegung < 10 px) → Park-Overlay
 * Overlay (Parkplatz-Symbol + „Parken") erscheint nur während der Geste, schließt bei
 * Außen-Tap. Zurückholen läuft NICHT hier, sondern per Chip-Tap im {@link GeparktBlock}.
 *
 * Release-sicher: außerhalb eines ParkProvider (`!aktiv`) reicht der Wrapper die
 * Kinder unverändert durch — keine Geste, kein Extra-Verhalten (Produktion/v3).
 *
 * SoT: docs/drafts/SPEC-ELEMENT-LAYOUT-PAPIERKORB.md
 */
import { useRef, useState, type ReactNode } from 'react'
import { ParkingSquare } from 'lucide-react'
import { usePark } from './ParkContext'

const LONGPRESS_MS = 500
const BEWEGUNG_PX = 10

export function Parkbar({
  id,
  titel,
  className,
  children,
}: {
  id: string
  /** Klartext für den Parkplatz-Chip (wird beim Parken mitpersistiert). */
  titel: string
  /** Zusatz-Klassen für den Wrapper (z. B. Grid-Span `xl:col-span-2`). Wird auch
   *  ohne Provider angewandt, damit das Layout in Produktion/v3 erhalten bleibt. */
  className?: string
  children: ReactNode
}) {
  const park = usePark()
  const [overlay, setOverlay] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const start = useRef<{ x: number; y: number } | null>(null)

  // Inert ohne Provider bzw. wenn geparkt → nichts an der kanonischen Stelle.
  if (!park.aktiv) return className ? <div className={className}>{children}</div> : <>{children}</>
  if (park.istGeparkt(id)) return null

  const abbrechen = () => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null }
    start.current = null
  }

  const onTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length !== 1) return abbrechen()
    const t = e.touches[0]
    start.current = { x: t.clientX, y: t.clientY }
    timer.current = setTimeout(() => setOverlay(true), LONGPRESS_MS)
  }
  const onTouchMove = (e: React.TouchEvent) => {
    if (!start.current) return
    const t = e.touches[0]
    // Bewegung > Schwelle = Scroll/Tooltip-Pan, kein Long-Press → abbrechen.
    if (Math.abs(t.clientX - start.current.x) > BEWEGUNG_PX ||
        Math.abs(t.clientY - start.current.y) > BEWEGUNG_PX) {
      abbrechen()
    }
  }

  const onContextMenu = (e: React.MouseEvent) => {
    e.preventDefault()
    setOverlay(true)
  }

  const parke = () => {
    park.park(id, titel)
    setOverlay(false)
  }

  return (
    <div
      className={`relative h-full${className ? ` ${className}` : ''}`}
      onContextMenu={onContextMenu}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={abbrechen}
      onTouchCancel={abbrechen}
    >
      {children}
      {overlay && (
        <>
          {/* Außen-Tap schließt das Overlay (deckt den Rest der Sicht ab). */}
          <button
            type="button"
            aria-label="Abbrechen"
            className="fixed inset-0 z-40 cursor-default"
            onClick={() => setOverlay(false)}
            onContextMenu={(e) => { e.preventDefault(); setOverlay(false) }}
          />
          <button
            type="button"
            onClick={parke}
            className="absolute inset-0 z-40 flex flex-col items-center justify-center gap-1 rounded-xl bg-gray-900/70 text-white backdrop-blur-sm transition-colors hover:bg-gray-900/80"
          >
            <ParkingSquare className="h-5 w-5" />
            <span className="text-xs font-medium">Parken</span>
          </button>
        </>
      )}
    </div>
  )
}
