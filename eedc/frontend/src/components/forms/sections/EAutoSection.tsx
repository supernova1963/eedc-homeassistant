import { Car } from 'lucide-react'
import type { SectionProps } from './types'
import { SonstigePositionenFields } from './SonstigePositionenFields'
import { readFeldWert } from '../../../lib/fieldDefinitions'

type EAutoFeld = { key: string; label: string; unit: string; placeholder: string; hint?: string }

// Kanonische Feldnamen: v2h_entladung_kwh (ehemals entladung_v2h_kwh)
const BASIS_FELDER: EAutoFeld[] = [
  { key: 'km_gefahren',       label: 'km gefahren',    unit: 'km',  placeholder: 'z.B. 1200' },
  { key: 'verbrauch_kwh',     label: 'Verbrauch',      unit: 'kWh', placeholder: 'z.B. 216'  },
  { key: 'ladung_pv_kwh',     label: 'Heim: PV',       unit: 'kWh', placeholder: 'z.B. 130',  hint: 'Wallbox mit PV-Strom' },
  { key: 'ladung_netz_kwh',   label: 'Heim: Netz',     unit: 'kWh', placeholder: 'z.B. 50',   hint: 'Wallbox mit Netzstrom' },
  { key: 'ladung_extern_kwh', label: 'Extern',         unit: 'kWh', placeholder: 'z.B. 36',   hint: 'Autobahn, Arbeit, etc.' },
  { key: 'ladung_extern_euro',label: 'Extern Kosten',  unit: '€',   placeholder: 'z.B. 18.00' },
]
const V2H_FELD: EAutoFeld = { key: 'v2h_entladung_kwh', label: 'V2H Entladung', unit: 'kWh', placeholder: 'z.B. 25' }

export function EAutoSection({
  investitionen, investitionsDaten, onInvChange, sonstigePositionen, onPositionenChange,
}: SectionProps) {
  if (investitionen.length === 0) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Car className="h-5 w-5 text-blue-500" />
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">E-Auto</h3>
      </div>
      {investitionen.map((inv) => {
        const hatV2H = inv.parameter?.v2h_faehig || inv.parameter?.nutzt_v2h
        const felder = hatV2H ? [...BASIS_FELDER, V2H_FELD] : BASIS_FELDER
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
