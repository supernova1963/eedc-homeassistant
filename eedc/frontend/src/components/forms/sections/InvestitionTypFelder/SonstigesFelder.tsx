import { FormSection, Input, Select } from '../../../ui'
import type { TypFelderProps } from './types'

const KATEGORIE_OPTIONEN = [
  { value: 'erzeuger', label: 'Erzeuger (z.B. Mini-BHKW, Mini-Wind)' },
  { value: 'verbraucher', label: 'Verbraucher (z.B. Klimaanlage, Pool)' },
  { value: 'speicher', label: 'Speicher (z.B. Wasserstoff)' },
]

export function SonstigesFelder({ paramData, onInputChange, setParam }: TypFelderProps) {
  return (
    <FormSection title="Sonstige Investition">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
        <Select
          label="Kategorie"
          name="param_kategorie"
          value={paramData.kategorie as string}
          onChange={(e) => setParam('kategorie', e.target.value)}
          options={KATEGORIE_OPTIONEN}
          hint="Bestimmt welche Monatsdaten erfasst werden"
        />
        <Input
          label="Beschreibung"
          name="param_beschreibung"
          value={paramData.beschreibung as string}
          onChange={onInputChange}
          placeholder="z.B. Mini-Blockheizkraftwerk Viessmann"
          hint="Kurze Beschreibung der Investition"
        />
      </div>
    </FormSection>
  )
}
