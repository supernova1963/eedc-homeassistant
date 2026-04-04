import type { ElementType } from 'react'
import type { Investition } from '../../../types'
import type { SonstigePosition } from './types'
import { SonstigePositionenFields } from './SonstigePositionenFields'
import { readFeldWert } from '../../../lib/fieldDefinitions'

export interface FeldConfig {
  key: string
  label: string
  unit: string
  placeholder: string
  hint?: string
}

interface InvestitionSectionProps {
  title: string
  icon: ElementType
  iconColor: string
  investitionen: Investition[]
  investitionsDaten: Record<string, Record<string, string>>
  onInvChange: (invId: number, field: string, value: string) => void
  felder: FeldConfig[]
  felderFn?: (inv: Investition) => FeldConfig[] | undefined
  sonstigePositionen: Record<string, SonstigePosition[]>
  onPositionenChange: (invId: number, positionen: SonstigePosition[]) => void
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
}: InvestitionSectionProps) {
  if (investitionen.length === 0) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Icon className={`h-5 w-5 ${iconColor}`} />
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">{title}</h3>
      </div>
      {investitionen.map((inv) => {
        const aktiveFelder = (felderFn ? felderFn(inv) : undefined) ?? felder
        const daten = investitionsDaten[inv.id] ?? {}
        return (
          <div key={inv.id} className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">{inv.bezeichnung}</p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {aktiveFelder.map((feld) => (
                <div key={feld.key}>
                  <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                    {feld.label} {feld.unit && <span className="text-gray-400">({feld.unit})</span>}
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={readFeldWert(daten, feld.key)}
                    onChange={(e) => onInvChange(inv.id, feld.key, e.target.value)}
                    placeholder={feld.placeholder}
                    className="input text-sm py-1.5"
                    title={feld.hint}
                  />
                  {feld.hint && (
                    <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5 truncate" title={feld.hint}>
                      {feld.hint}
                    </p>
                  )}
                </div>
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
  )
}
