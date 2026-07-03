/**
 * DatumFeld — Formular-Hülle um den {@link DatumPicker} (D14-13, detLAN #116).
 *
 * Gleiche Label-/Hint-Anatomie wie {@link Input}, aber statt des nativen
 * `<input type="date">` sitzt der DatumPicker-SoT im Feld — ein Kalender-Icon,
 * ein Popover-Stil, mobil feste Trigger-Höhe. Für die Einstellungen-Formulare
 * (Strompreise · Anlage · Komponenten); Setup-Wizard/Repair bleiben bewusst
 * nativ (Entscheid Gernot 2026-07-03).
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
}: {
  label: string
  /** `YYYY-MM-DD` oder leer. */
  value: string
  onChange: (v: string) => void
  min?: string
  max?: string
  required?: boolean
  hint?: string
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
        ariaLabel={label}
        className="w-full min-h-[42px]"
      />
      {hint && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</p>}
    </div>
  )
}

export default DatumFeld
