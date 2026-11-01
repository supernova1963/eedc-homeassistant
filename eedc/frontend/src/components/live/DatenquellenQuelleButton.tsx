/**
 * Ein Quellen-Knopf der Datenquellen-Fläche (HA-Sensor · Gateway · Inbound · Keine).
 *
 * Herausgelöst aus `DatenquellenZuordnung.tsx` (Themen-Kacheln 4.2.0, TH-E1 §1.5) — **unverändert**, damit die
 * Feldzeile und die Zeile eines Themen-Eintrags (`DatenquellenThemen.tsx`) denselben Knopf tragen.
 */
import type { LucideIcon } from 'lucide-react'
import { Button } from '../ui'

/** Ein Quellen-Button (aktiv = gefüllt). Icon + Label; Klick öffnet Modal bzw. setzt direkt.
 *  Pro Feld ist immer genau EINE Quelle aktiv → der grün gefüllte Chip zeigt die
 *  aktuelle Wahl (auch „Keine"); inaktive bleiben neutral (secondary). */
export default function QuelleButton({
  icon: Icon, label, active, disabled, title, onClick,
}: {
  icon: LucideIcon
  label: string
  active: boolean
  disabled?: boolean
  title: string
  onClick: () => void
}) {
  return (
    <Button
      type="button"
      variant={active ? 'primary' : 'secondary'}
      size="sm"
      disabled={disabled}
      onClick={onClick}
      title={title}
      aria-pressed={active}
      aria-label={label}
    >
      <Icon className="h-4 w-4" />
      <span className="ml-1.5">{label}</span>
    </Button>
  )
}
