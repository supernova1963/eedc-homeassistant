import type { SonstigePosition } from '../../api'

export interface WizardState {
  basis: Record<string, number | null>
  optionale: Record<string, number | string | null>  // Sonderkosten, Notizen
  investitionen: Record<number, Record<string, number | null>>
  sonstigePositionen: Record<number, SonstigePosition[]>
}
