/**
 * Gemeinsame Typen für alle Monats-Section-Komponenten.
 */

import type { Investition, SonstigePosition } from '../../../types'

// SoT-Kanon in types/index.ts (G19-1) — hier nur Re-Export für Bestand
export type { SonstigePosition }

export interface SectionProps {
  investitionen: Investition[]
  investitionsDaten: Record<string, Record<string, string>>
  onInvChange: (invId: number, field: string, value: string) => void
  sonstigePositionen: Record<string, SonstigePosition[]>
  onPositionenChange: (invId: number, positionen: SonstigePosition[]) => void
}
