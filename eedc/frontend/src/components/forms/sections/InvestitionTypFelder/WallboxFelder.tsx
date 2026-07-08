import { FormSection, Input, Alert } from '../../../ui'
import { SchalterZeile } from '../SchalterZeile'
import type { TypFelderProps } from './types'

export function WallboxFelder({ paramData, onInputChange, setParam }: TypFelderProps) {
  return (
    <>
      <FormSection title="Wallbox">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
          <Input
            label="Max. Ladeleistung (kW)"
            name="param_max_ladeleistung_kw"
            type="number" step="any" min="0"
            value={paramData.max_ladeleistung_kw as string}
            onChange={onInputChange}
            hint="Typisch 11 kW oder 22 kW"
          />
        </div>
      </FormSection>

      <FormSection variant="erweitert" title="Optionen">
        <div className="space-y-3">
          <SchalterZeile
            checked={paramData.bidirektional as boolean}
            onChange={(an) => setParam('bidirektional', an)}
            label="Bidirektional (V2H/V2G)"
          />
          <SchalterZeile
            checked={paramData.pv_optimiert as boolean}
            onChange={(an) => setParam('pv_optimiert', an)}
            label="PV-Überschussladen möglich"
          />
          <SchalterZeile
            checked={paramData.ist_dienstlich as boolean}
            onChange={(an) => setParam('ist_dienstlich', an)}
            label="Ausschließlich dienstliches Laden (Firmenwagen)"
          />
          {paramData.ist_dienstlich && (
            <Alert type="warning">
              ROI-Berechnung: Netzkosten + entgangene Einspeisung als Ausgaben.
              Erträge (z. B. AG-Erstattung) als „Sonstige Erträge" im Monatsabschluss erfassen.
              Für gemischte Nutzung (privat + dienstlich): zwei separate Wallbox-Einträge anlegen.
            </Alert>
          )}
        </div>
      </FormSection>
    </>
  )
}
