import { FormSection, Input } from '../../../ui'
import { fmtZahl } from '../../../../lib'
import type { TypFelderProps } from './types'

/**
 * PV-Modul: nur die optionalen Modul-Details. Die Kern-Felder (Leistung kWp,
 * Ausrichtung, Neigung) liegen in der `InvestitionForm`-Shell (direkte Spalten).
 */
export function PvModulFelder({ paramData, onInputChange }: TypFelderProps) {
  const anzahl = parseInt(paramData.anzahl_module as string) || 0
  const wp = parseInt(paramData.modul_leistung_wp as string) || 0
  return (
    <FormSection variant="erweitert" title="Modul-Details (optional)">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
        <Input
          label="Anzahl Module"
          name="param_anzahl_module"
          type="number" step="1" min="1"
          value={paramData.anzahl_module as string}
          onChange={onInputChange}
          hint="Anzahl der PV-Module in diesem String"
        />
        <Input
          label="Leistung pro Modul (Wp)"
          name="param_modul_leistung_wp"
          type="number" step="1" min="0"
          value={paramData.modul_leistung_wp as string}
          onChange={onInputChange}
          hint="z.B. 400 Wp, 500 Wp"
        />
        <Input
          label="Modul-Typ"
          name="param_modul_typ"
          type="text"
          value={paramData.modul_typ as string}
          onChange={onInputChange}
          placeholder="z.B. Longi Hi-MO 5"
          hint="Hersteller und Modell"
        />
      </div>
      {anzahl > 0 && wp > 0 && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-3">
          Berechnete Leistung: {fmtZahl((anzahl * wp) / 1000, 2)} kWp
        </p>
      )}
    </FormSection>
  )
}
