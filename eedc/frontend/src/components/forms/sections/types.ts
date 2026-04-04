/**
 * Gemeinsame Typen für alle Monats-Section-Komponenten.
 */

import type { Investition } from '../../../types'

export interface SonstigePosition {
  bezeichnung: string
  betrag: number
  typ: 'ertrag' | 'ausgabe'
}

export interface SectionProps {
  investitionen: Investition[]
  investitionsDaten: Record<string, Record<string, string>>
  onInvChange: (invId: number, field: string, value: string) => void
  sonstigePositionen: Record<string, SonstigePosition[]>
  onPositionenChange: (invId: number, positionen: SonstigePosition[]) => void
}
