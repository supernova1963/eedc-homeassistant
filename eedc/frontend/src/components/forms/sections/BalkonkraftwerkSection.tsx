import { Zap } from 'lucide-react'
import type { SectionProps } from './types'
import { SonstigePositionenFields } from './SonstigePositionenFields'
import { readFeldWert } from '../../../lib/fieldDefinitions'

export function BalkonkraftwerkSection({
  investitionen, investitionsDaten, onInvChange, sonstigePositionen, onPositionenChange,
}: SectionProps) {
  if (investitionen.length === 0) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Zap className="h-5 w-5 text-amber-500" />
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Balkonkraftwerk</h3>
      </div>
      {investitionen.map((inv) => {
        const hatSpeicher = Boolean(inv.parameter?.hat_speicher)
        const daten = investitionsDaten[inv.id] ?? {}
        return (
          <div key={inv.id} className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {inv.bezeichnung}
              {inv.leistung_kwp && <span className="text-xs text-gray-500 ml-2">({inv.leistung_kwp} kWp)</span>}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              {hatSpeicher
                ? 'Mit Speicher: Bei Nulleinspeisung entspricht Eigenverbrauch meist der Erzeugung.'
                : 'Ohne Speicher: Eigenverbrauch ist der direkt genutzte Anteil (typisch 30-40% der Erzeugung).'}
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  Erzeugung <span className="text-gray-400">(kWh)</span>
                </label>
                <input
                  type="number" step="0.01" min="0"
                  value={readFeldWert(daten, 'pv_erzeugung_kwh')}
                  onChange={(e) => onInvChange(inv.id, 'pv_erzeugung_kwh', e.target.value)}
                  placeholder="z.B. 45" className="input text-sm py-1.5"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  Eigenverbrauch <span className="text-gray-400">(kWh)</span>
                </label>
                <input
                  type="number" step="0.01" min="0"
                  value={readFeldWert(daten, 'eigenverbrauch_kwh')}
                  onChange={(e) => onInvChange(inv.id, 'eigenverbrauch_kwh', e.target.value)}
                  placeholder={hatSpeicher ? 'z.B. 43 (≈Erzeugung)' : 'z.B. 15 (30-40%)'}
                  className="input text-sm py-1.5"
                />
              </div>
              {hatSpeicher && (
                <>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      Speicher Ladung <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number" step="0.01" min="0"
                      value={readFeldWert(daten, 'speicher_ladung_kwh')}
                      onChange={(e) => onInvChange(inv.id, 'speicher_ladung_kwh', e.target.value)}
                      placeholder="z.B. 30" className="input text-sm py-1.5"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      Speicher Entladung <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number" step="0.01" min="0"
                      value={readFeldWert(daten, 'speicher_entladung_kwh')}
                      onChange={(e) => onInvChange(inv.id, 'speicher_entladung_kwh', e.target.value)}
                      placeholder="z.B. 28" className="input text-sm py-1.5"
                    />
                  </div>
                </>
              )}
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
