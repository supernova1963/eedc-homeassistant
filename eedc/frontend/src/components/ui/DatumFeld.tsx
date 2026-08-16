/**
 * DatumFeld — Formular-Hülle um den {@link DatumPicker} (D14-13, detLAN #116).
 *
 * Gleiche Label-/Hint-Anatomie wie {@link Input}, aber statt des nativen
 * `<input type="date">` sitzt der DatumPicker-SoT im Feld — ein Kalender-Icon,
 * ein Popover-Stil, mobil feste Trigger-Höhe. Für Formularfelder mit gestapeltem
 * Label (Einstellungen-Formulare, Setup-Wizard-Steps, Reparatur-Werkbank).
 * Inline-Datumsfilter (Label links neben dem Feld) nutzen den {@link DatumPicker}
 * direkt. (Die frühere Ausnahme „Setup/Repair bleiben nativ" vom 2026-07-03 ist
 * durch die Forms→V4-Abnahme 2026-07-08 aufgehoben — Style-Guide Teil D, M2.)
 */
import { DatumPicker } from './DatumPicker'

export function DatumFeld({
  label,
  value,
  onChange,
  min = '2000-01-01',
  max = '2099-12-31',
  required,
  hint,
  warnung,
  disabled = false,
}: {
  label: string
  /** `YYYY-MM-DD` oder leer. */
  value: string
  onChange: (v: string) => void
  min?: string
  max?: string
  required?: boolean
  hint?: string
  /**
   * Warn-MELDUNG unterhalb der Fehler-Schwelle (F3-Status-Achse: warnung ≠
   * error) — steht amber über dem `hint`. Für Felder, deren Fehlen die Auswertung
   * beeinträchtigt, das Speichern aber nicht blockieren soll.
   *
   * ⚠ Bewusst eine MELDUNG und kein Rand-Zustand wie bei {@link Input}: Der
   * `DatumPicker` trägt seine Rahmenfarbe fest im Trigger, VOR dem
   * durchgereichten `className` — welche Tailwind-Utility dann gewinnt,
   * entscheidet die Reihenfolge im generierten Stylesheet, nicht die im
   * Attribut. Ein amber Rand von außen wäre also nicht verlässlich, und kein
   * Gate würde es merken.
   */
  warnung?: string
  /** Feld deaktivieren (z. B. während eines Reparatur-Laufs). */
  disabled?: boolean
}) {
  return (
    <div className="w-full">
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
        {label}
        {required && <span className="text-red-500 ml-1">*</span>}
      </label>
      <DatumPicker
        modus="tag"
        value={value}
        onChange={onChange}
        min={min}
        max={max}
        disabled={disabled}
        ariaLabel={label}
        className="w-full min-h-[42px]"
      />
      {warnung && (
        <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">{warnung}</p>
      )}
      {hint && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</p>}
    </div>
  )
}

export default DatumFeld
