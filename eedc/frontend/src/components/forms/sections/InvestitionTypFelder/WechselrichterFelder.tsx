import { FormSection, Input } from '../../../ui'
import { SchalterZeile } from '../SchalterZeile'
import type { TypFelderProps } from './types'

export function WechselrichterFelder({ paramData, onInputChange, setParam }: TypFelderProps) {
  return (
    <>
      <FormSection title="Wechselrichter">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
          <Input
            label="Max. Leistung (kW)"
            name="param_max_leistung_kw"
            type="number" step="any" min="0"
            value={paramData.max_leistung_kw as string}
            onChange={onInputChange}
          />
          <Input
            label="Wirkungsgrad (%)"
            name="param_wirkungsgrad_prozent"
            type="number" step="any" min="0" max="100"
            value={paramData.wirkungsgrad_prozent as string}
            onChange={onInputChange}
          />
        </div>
      </FormSection>

      <FormSection variant="erweitert" title="Optionen">
        <SchalterZeile
          checked={paramData.hybrid as boolean}
          onChange={(an) => setParam('hybrid', an)}
          label="Hybrid-Wechselrichter (mit Speicher-Anschluss)"
        />
      </FormSection>
    </>
  )
}
