import { Battery } from 'lucide-react'
import type { SectionProps } from './types'
import { SonstigePositionenFields } from './SonstigePositionenFields'
import { readFeldWert } from '../../../lib/fieldDefinitions'

// Kanonische Feldnamen: ladung_netz_kwh (ehemals speicher_ladung_netz_kwh)
type SpeicherFeld = { key: string; label: string; unit: string; placeholder: string; hint?: string }

const BASIS_FELDER: SpeicherFeld[] = [
  { key: 'ladung_kwh',    label: 'Ladung',     unit: 'kWh',    placeholder: 'z.B. 150' },
  { key: 'entladung_kwh', label: 'Entladung',  unit: 'kWh',    placeholder: 'z.B. 140' },
]
const ARBITRAGE_FELDER: SpeicherFeld[] = [
  { key: 'ladung_netz_kwh',         label: 'Netzladung',   unit: 'kWh',    placeholder: 'z.B. 50', hint: 'Arbitrage: Laden aus Netz' },
  { key: 'speicher_ladepreis_cent', label: 'Ø Ladepreis',  unit: 'ct/kWh', placeholder: 'z.B. 15', hint: 'Durchschnittl. Strompreis beim Netzladen' },
]

export function SpeicherSection({
  investitionen, investitionsDaten, onInvChange, sonstigePositionen, onPositionenChange,
}: SectionProps) {
  if (investitionen.length === 0) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Battery className="h-5 w-5 text-green-500" />
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Speicher</h3>
      </div>
      {investitionen.map((inv) => {
        const hatArbitrage = inv.parameter?.arbitrage_faehig
        const felder = hatArbitrage ? [...BASIS_FELDER, ...ARBITRAGE_FELDER] : BASIS_FELDER
        const daten = investitionsDaten[inv.id] ?? {}
        return (
          <div key={inv.id} className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">{inv.bezeichnung}</p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {felder.map((feld) => (
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
