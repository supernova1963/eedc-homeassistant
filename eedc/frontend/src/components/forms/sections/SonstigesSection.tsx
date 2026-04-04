import { MoreHorizontal } from 'lucide-react'
import type { SectionProps } from './types'
import { SonstigePositionenFields } from './SonstigePositionenFields'
import { readFeldWert } from '../../../lib/fieldDefinitions'

const KATEGORIE_LABELS: Record<string, string> = {
  erzeuger: 'Erzeuger',
  verbraucher: 'Verbraucher',
  speicher: 'Speicher',
}

export function SonstigesSection({
  investitionen, investitionsDaten, onInvChange, sonstigePositionen, onPositionenChange,
}: SectionProps) {
  if (investitionen.length === 0) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <MoreHorizontal className="h-5 w-5 text-gray-500" />
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Sonstiges</h3>
      </div>
      {investitionen.map((inv) => {
        const kategorie = (inv.parameter?.kategorie as string) || 'erzeuger'
        const daten = investitionsDaten[inv.id] ?? {}
        return (
          <div key={inv.id} className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{inv.bezeichnung}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              {KATEGORIE_LABELS[kategorie] || kategorie}
              {inv.parameter?.beschreibung ? ` - ${String(inv.parameter.beschreibung)}` : ''}
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {kategorie === 'erzeuger' && (
                <>
                  {[
                    { key: 'erzeugung_kwh',     label: 'Erzeugung',     placeholder: 'z.B. 100' },
                    { key: 'eigenverbrauch_kwh', label: 'Eigenverbrauch',placeholder: 'z.B. 85'  },
                    { key: 'einspeisung_kwh',    label: 'Einspeisung',   placeholder: 'z.B. 15'  },
                  ].map(f => (
                    <div key={f.key}>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                        {f.label} <span className="text-gray-400">(kWh)</span>
                      </label>
                      <input
                        type="number" step="0.01" min="0"
                        value={readFeldWert(daten, f.key)}
                        onChange={(e) => onInvChange(inv.id, f.key, e.target.value)}
                        placeholder={f.placeholder} className="input text-sm py-1.5"
                      />
                    </div>
                  ))}
                </>
              )}
              {kategorie === 'verbraucher' && (
                <>
                  {[
                    { key: 'verbrauch_sonstig_kwh', label: 'Verbrauch',  placeholder: 'z.B. 50' },
                    { key: 'bezug_pv_kwh',          label: 'davon PV',   placeholder: 'z.B. 30' },
                    { key: 'bezug_netz_kwh',         label: 'davon Netz', placeholder: 'z.B. 20' },
                  ].map(f => (
                    <div key={f.key}>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                        {f.label} <span className="text-gray-400">(kWh)</span>
                      </label>
                      <input
                        type="number" step="0.01" min="0"
                        value={readFeldWert(daten, f.key)}
                        onChange={(e) => onInvChange(inv.id, f.key, e.target.value)}
                        placeholder={f.placeholder} className="input text-sm py-1.5"
                      />
                    </div>
                  ))}
                </>
              )}
              {kategorie === 'speicher' && (
                <>
                  {/* Kanonische Feldnamen: erzeugung_kwh / verbrauch_sonstig_kwh
                      Lese-Kompatibilität: alte DB-Einträge hatten ladung_kwh / entladung_kwh */}
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      Erzeugung/Entladung <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number" step="0.01" min="0"
                      value={readFeldWert(daten, 'erzeugung_kwh') || readFeldWert(daten, 'ladung_kwh')}
                      onChange={(e) => onInvChange(inv.id, 'erzeugung_kwh', e.target.value)}
                      placeholder="z.B. 20" className="input text-sm py-1.5"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                      Verbrauch/Ladung <span className="text-gray-400">(kWh)</span>
                    </label>
                    <input
                      type="number" step="0.01" min="0"
                      value={readFeldWert(daten, 'verbrauch_sonstig_kwh') || readFeldWert(daten, 'entladung_kwh')}
                      onChange={(e) => onInvChange(inv.id, 'verbrauch_sonstig_kwh', e.target.value)}
                      placeholder="z.B. 18" className="input text-sm py-1.5"
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
