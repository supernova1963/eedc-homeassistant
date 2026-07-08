import type { ElementType } from 'react'
import type { Investition } from '../../../types'
import type { SonstigePosition } from './types'
import { SonstigePositionenFields } from '../SonstigePositionenFields'
import { readFeldWert, type FeldDefinition } from '../../../lib/fieldDefinitions'
import { Input, FormSection } from '../../ui'

interface InvestitionSectionProps {
  title: string
  icon: ElementType
  iconColor: string
  investitionen: Investition[]
  investitionsDaten: Record<string, Record<string, string>>
  onInvChange: (invId: number, field: string, value: string) => void
  /** Statische Felder (für alle Investitionen gleich) */
  felder?: FeldDefinition[]
  /** Dynamische Felder pro Investition (hat Vorrang vor felder) */
  felderFn?: (inv: Investition) => FeldDefinition[]
  sonstigePositionen: Record<string, SonstigePosition[]>
  onPositionenChange: (invId: number, positionen: SonstigePosition[]) => void
  /** Optionaler Hinweistext unter dem Titel */
  hinweisFn?: (inv: Investition) => string | null
  /** Optionale Zusatzinfo pro Investition (z.B. leistung_kwp) */
  subtitleFn?: (inv: Investition) => string | null
}

export function InvestitionSection({
  title,
  icon: Icon,
  iconColor,
  investitionen,
  investitionsDaten,
  onInvChange,
  felder,
  felderFn,
  sonstigePositionen,
  onPositionenChange,
  hinweisFn,
  subtitleFn,
}: InvestitionSectionProps) {
  if (investitionen.length === 0) return null

  return (
    <FormSection title={title} icon={Icon} iconColor={iconColor}>
      <div className="space-y-4">
        {investitionen.map((inv) => {
          const aktiveFelder = felderFn ? felderFn(inv) : (felder ?? [])
          const daten = investitionsDaten[inv.id] ?? {}
          const subtitle = subtitleFn?.(inv)
          const hinweis = hinweisFn?.(inv)
          return (
            <div key={inv.id} className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/60 p-4">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {inv.bezeichnung}
                {subtitle && <span className="text-xs text-gray-500 ml-2">({subtitle})</span>}
              </p>
              {hinweis && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">{hinweis}</p>
              )}
              {/* D17-7: max 3 Spalten (mehr → 3-zeiliger Umbruch) + Subgrid: die
                  Label-Höhe stellt sich PRO Zeile automatisch ein (einzeilig, wenn
                  alle Titel kurz; zweizeilig nur wo einer umbricht) → Felder immer
                  in einer Linie, ohne globalen Leerraum-Reserve. */}
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 [grid-auto-rows:auto] gap-x-3 gap-y-2">
                {aktiveFelder.map((feld) => (
                  <Input
                    key={feld.feld}
                    denseRow
                    label={feld.einheit ? `${feld.label} (${feld.einheit})` : feld.label}
                    type="number"
                    step="0.01"
                    min="0"
                    value={readFeldWert(daten, feld.feld)}
                    onChange={(e) => onInvChange(inv.id, feld.feld, e.target.value)}
                    placeholder={feld.placeholder}
                    hint={feld.hint}
                  />
                ))}
              </div>
              <SonstigePositionenFields
                invId={inv.id}
                positionen={sonstigePositionen[String(inv.id)] || []}
                onChange={(pos) => onPositionenChange(inv.id, pos)}
              />
            </div>
          )
        })}
      </div>
    </FormSection>
  )
}
