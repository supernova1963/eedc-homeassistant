/**
 * Parkbar — umhüllt EIN parkbares Element (KPICard, Chart, Tabelle …).
 *
 * Geste (kein sichtbares Icon, Affordanz = die Geste):
 *  • Desktop: Rechtsklick (contextmenu, preventDefault) → Park-Overlay,
 *             auf der **ganzen** Fläche
 *  • Mobil:   Long-Press (~500 ms, Bewegung < 10 px) → Park-Overlay,
 *             aber **nur in der Kopf-Zone** und nicht auf einem Bedienelement
 *             (N-390, s. {@link KOPFZONE_PX})
 * Overlay (Parkplatz-Symbol + „Parken") erscheint nur während der Geste, schließt bei
 * Außen-Tap. Zurückholen läuft NICHT hier, sondern per Chip-Tap im {@link GeparktBlock}.
 *
 * Release-sicher: außerhalb eines ParkProvider (`!aktiv`) reicht der Wrapper die
 * Kinder unverändert durch — keine Geste, kein Extra-Verhalten (Produktion/v3).
 *
 * SoT: docs/drafts/archive/flip-v4/SPEC-ELEMENT-LAYOUT-PAPIERKORB.md
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ParkingSquare } from 'lucide-react'
import { usePark } from './ParkContext'

const LONGPRESS_MS = 500
const BEWEGUNG_PX = 10

/**
 * N-390: Die Touch-Geste greift nur im oberen Streifen des Elements — seiner
 * **Kopf-Zone**. Das ist die zweite Stolperstein-Auflösung der SPEC
 * (`SPEC-ELEMENT-LAYOUT-PAPIERKORB.md:65`), die bis zum 2026-09-04 fehlte:
 * *„Geste an die Titel-/Kopf-Zone binden, nicht an den interaktiven Körper."*
 *
 * ⛔ **Warum die andere Auflösung derselben SPEC nicht reicht** (`:66`,
 * „Long-Press ≠ Chart-Tooltip-Touch: Timer + Bewegungs-Schwelle"): Sie setzt
 * voraus, dass ein Tooltip-Touch ein **Move/Pan** ist. Das gilt für
 * *Chart*-Tooltips (über die Kurve fahren) — **nicht** für `useTouchTitleTooltip`,
 * den app-globalen Touch-Ersatz für `title=`/`data-title`. Dort ist der
 * Tooltip-Touch ein **Halten ohne Bewegung**, also exakt die Park-Geste. Wer im
 * Energiefluss den Haus-Knoten antippte, um seine sieben Zeilen zu lesen, bekam
 * nach 500 ms das Park-Overlay über die ganze Fläche gelegt.
 *
 * ⚑ **Nur Touch** (Entscheid Gernot, 04.09.). Der Desktop-Rechtsklick bleibt auf
 * der **ganzen** Fläche — er kollidiert mit keinem Hover-Tooltip, eine
 * Einschränkung wäre dort reiner Komfortverlust.
 *
 * ⚠ **Der Kantenfall ist bewusst nicht gedeckelt:** Bei einem Element, das
 * flacher als diese Zone ist, greift die Geste weiterhin überall — also der
 * Zustand von heute. Das ist kein neuer Schaden, nur keine Verbesserung dort;
 * ein Deckel („höchstens die halbe Höhe") wäre eine Regel ohne gemessenen Anlass.
 */
const KOPFZONE_PX = 44

/** Elemente, die ihren Touch selbst brauchen — ein Long-Press auf dem ⤢-Knopf
 *  oder der Hintergrund-Auswahl des Energieflusses ist keine Park-Absicht.
 *  Deckt denselben SPEC-Satz ab („nicht an den interaktiven Körper"). */
const BEDIENELEMENTE = 'button, a, select, input, textarea, [role="button"]'

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

  // R17-5: als parkbares Element anmelden (auch wenn gerade geparkt → diese Instanz
  // rendert unten `null`, bleibt aber montiert und damit gezählt). Stabile
  // `registriere`-Referenz → läuft einmal pro Mount, kein Churn bei Park-State-Wechsel.
  const registriere = park.registriere
  useEffect(() => registriere(id), [registriere, id])

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
    // N-390, beide Hälften der SPEC-Auflösung: nur in der Kopf-Zone, und nicht
    // auf einem Bedienelement. `currentTarget` ist der Parkbar-Wrapper und wird
    // synchron gelesen (React 18 poolt Events nicht mehr).
    const oben = t.clientY - e.currentTarget.getBoundingClientRect().top
    if (oben > KOPFZONE_PX) return abbrechen()
    if ((e.target as Element | null)?.closest?.(BEDIENELEMENTE)) return abbrechen()
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
      // Selbst-Entdeckung für den Laufzeit-Leerblock-Gate (scripts/park-leertest.mjs):
      // jedes gerenderte parkbare Element trägt seine ID im DOM → keine Hand-ID-Liste,
      // driftfrei. Nur im aktiven+ungeparkten Zweig (geparkt → null; ohne Provider → v3
      // rendert ohne diesen Wrapper, also kein Attribut).
      data-park-id={id}
      // D18-4 (detlan #210, @402px gemessen): KEIN h-full mehr — als direktes
      // Grid-/Flex-Kind streckt der Container-Stretch (align-items) die Parkbar
      // ohnehin; height:100% griff dagegen auch in GESTAPELTEN Spalten auf die
      // Zeilenhöhe des Bilanz-Grids durch (224px-Wrapper um 16px Inhalt = detlans
      // „halbe Bildschirmhöhe leere Karte"). Aufrufer, die Füllung brauchen,
      // geben sie per className mit.
      className={`relative${className ? ` ${className}` : ''}`}
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
