import { FormSection, Input, Alert } from '../../../ui'
import { SchalterZeile } from '../SchalterZeile'
import type { TypFelderProps } from './types'

export function EAutoFelder({ paramData, onInputChange, setParam }: TypFelderProps) {
  return (
    <>
      <FormSection title="E-Auto">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
          <Input
            label="Batteriekapazität (kWh)"
            name="param_batteriekapazitaet_kwh"
            type="number" step="any" min="0"
            value={paramData.batteriekapazitaet_kwh as string}
            onChange={onInputChange}
          />
          <Input
            label="Verbrauch (kWh/100km)"
            name="param_verbrauch_kwh_100km"
            type="number" step="any" min="0"
            value={paramData.verbrauch_kwh_100km as string}
            onChange={onInputChange}
          />
          <Input
            label="Jahresfahrleistung (km)"
            name="param_jahresfahrleistung_km"
            type="number" step="any" min="0"
            value={paramData.jahresfahrleistung_km as string}
            onChange={onInputChange}
          />
          <Input
            label="PV-Ladeanteil (%)"
            name="param_pv_ladeanteil_prozent"
            type="number" step="1" min="0" max="100"
            value={paramData.pv_ladeanteil_prozent as string}
            onChange={onInputChange}
            hint="Anteil der Ladung aus PV-Strom"
          />
        </div>
      </FormSection>

      <FormSection variant="erweitert" title="Vergleich & Betrieb (ROI)">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
          <Input
            label="Verbrenner-Verbrauch (L/100km)"
            name="param_vergleich_verbrauch_l_100km"
            type="number" step="any" min="0"
            value={paramData.vergleich_verbrauch_l_100km as string}
            onChange={onInputChange}
            hint="Verbrauch des alternativen Verbrenners"
          />
          <Input
            label="Benzinpreis (€/L)"
            name="param_benzinpreis_euro"
            type="number" step="0.01" min="0"
            value={paramData.benzinpreis_euro as string}
            onChange={onInputChange}
            hint="Aktueller Benzin/Diesel-Preis"
          />
        </div>
        <div className="space-y-3 mt-4">
          <SchalterZeile
            checked={paramData.v2h_faehig as boolean}
            onChange={(an) => setParam('v2h_faehig', an)}
            label="V2H-fähig (Vehicle-to-Home)"
          />
          {paramData.v2h_faehig && (
            <Input
              label="V2H Entladeleistung (kW)"
              name="param_v2h_entladeleistung_kw"
              type="number" step="any" min="0"
              value={paramData.v2h_entladeleistung_kw as string}
              onChange={onInputChange}
            />
          )}
          <SchalterZeile
            checked={paramData.ist_dienstlich as boolean}
            onChange={(an) => setParam('ist_dienstlich', an)}
            label="Firmenwagen (dienstlich – kein Benzinvergleich im ROI)"
          />
          {paramData.ist_dienstlich && (
            <Alert type="warning">
              Die Kraftstoffersparnis geht an den Arbeitgeber. ROI-Berechnung: nur PV-Eigenverbrauchsvorteil
              und AG-Erstattung (als „Sonstiger Ertrag" im Monatsabschluss erfassen).
            </Alert>
          )}
        </div>
      </FormSection>
    </>
  )
}
