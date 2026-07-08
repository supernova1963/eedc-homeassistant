import { ReactNode } from 'react'
import { Switch } from '../../ui'

/**
 * SchalterZeile — Switch-SoT + Beschriftung/Hint als Zeile (Ja/Nein, D1).
 * Geteilter DRY-Helfer für InvestitionForm-Shell + die Typ-Parameterfelder;
 * identisches Markup wie in AnlageForm/InfothekForm — kein neuer SoT-Baustein,
 * nur Komposition des bestehenden `Switch`
 * ([[feedback_bestehende_mechanik_nutzen_nicht_erfinden]]).
 */
export function SchalterZeile({
  checked, onChange, label, hint, disabled,
}: {
  checked: boolean
  onChange: (an: boolean) => void
  label: string
  hint?: ReactNode
  disabled?: boolean
}) {
  return (
    <div className="flex items-start gap-3">
      <Switch checked={checked} onChange={onChange} ariaLabel={label} disabled={disabled} />
      <div>
        <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{label}</span>
        {hint && <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{hint}</p>}
      </div>
    </div>
  )
}
