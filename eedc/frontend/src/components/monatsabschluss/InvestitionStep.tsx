import type { InvestitionStatus, SonstigePosition } from '../../api'
import SonstigePositionenFields from '../forms/SonstigePositionenFields'
import FeldInput from './FeldInput'
import { TYP_ICONS, getTypLabel } from './helpers'

export default function InvestitionStep({
  typ,
  investitionen,
  values,
  onChange,
  sonstigePositionen,
  onSonstigePositionenChange,
}: {
  typ: string
  investitionen: InvestitionStatus[]
  values: Record<number, Record<string, number | null>>
  onChange: (invId: number, feld: string, wert: number | null) => void
  sonstigePositionen: Record<number, SonstigePosition[]>
  onSonstigePositionenChange: (invId: number, positionen: SonstigePosition[]) => void
}) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
        {TYP_ICONS[typ]}
        {getTypLabel(typ)}
      </h2>

      {investitionen.map(inv => (
        <div
          key={inv.id}
          className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden"
        >
          <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/50">
            <h3 className="font-medium text-gray-900 dark:text-white">
              {inv.bezeichnung}
              {inv.kategorie && (
                <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">
                  ({inv.kategorie})
                </span>
              )}
            </h3>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {inv.felder.map(feld => (
                <FeldInput
                  key={feld.feld}
                  feld={feld}
                  value={values[inv.id]?.[feld.feld]}
                  onChange={(wert) => onChange(inv.id, feld.feld, wert)}
                />
              ))}
            </div>
            <SonstigePositionenFields
              positionen={sonstigePositionen[inv.id] || []}
              onChange={(pos) => onSonstigePositionenChange(inv.id, pos)}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
