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
      {hint && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</p>}
    </div>
  )
}

export default DatumFeld
