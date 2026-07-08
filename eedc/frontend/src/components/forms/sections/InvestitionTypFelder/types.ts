import type { ChangeEvent } from 'react'

/**
 * Gemeinsame Props der typ-spezifischen Parameterfeld-Komponenten (Slice 5).
 * Werte/Setter kommen aus der `InvestitionForm`-Shell; Validierungs-Helfer nutzt
 * derzeit nur die Wärmepumpe (Pflicht-COP/SCOP/JAZ je Modus).
 */
export interface TypFelderProps {
  paramData: Record<string, string | boolean>
  /** Für `Input name="param_…"` (Event; Shell strippt das `param_`-Präfix). */
  onInputChange: (e: ChangeEvent<HTMLInputElement>) => void
  /** Für `Switch`/`Select`/`RadioGroup` (roher Parametername + Wert). */
  setParam: (name: string, value: string | boolean) => void
  /** Sichtbarer Fehler eines Pflichtfelds (nach touched/submitted), sonst undefined. */
  zeige: (name: string) => string | undefined
  markTouched: (name: string) => void
  setFeldRef: (name: string) => (el: HTMLDivElement | null) => void
}
