import { FormSection, Input } from '../../../ui'
import type { TypFelderProps } from './types'

export function WechselrichterFelder({ paramData, onInputChange }: TypFelderProps) {
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
        </div>
      </FormSection>
    </>
  )
}
