import { Zap } from 'lucide-react'
import type { FeldStatus } from '../../api'
import FeldInput from './FeldInput'

export default function BasisStep({
  felder,
  values,
  onChange,
}: {
  felder: FeldStatus[]
  values: Record<string, number | null>
  onChange: (feld: string, wert: number | null) => void
}) {
  // Nur die wichtigsten Felder anzeigen
  // direktverbrauch_kwh wird automatisch berechnet (PV - Einspeisung), daher nicht hier
  const wichtigeFelder = ['einspeisung_kwh', 'netzbezug_kwh']
  const wetterdatenFelder = ['globalstrahlung_kwh_m2', 'sonnenstunden', 'durchschnittstemperatur']

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
        <Zap className="w-5 h-5 text-amber-500" />
        Zählerdaten
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {felder
          .filter(f => wichtigeFelder.includes(f.feld))
          .map(feld => (
            <FeldInput
              key={feld.feld}
              feld={feld}
              value={values[feld.feld]}
              onChange={(wert) => onChange(feld.feld, wert)}
            />
          ))}
      </div>

      {/* Wetterdaten (optional) */}
      <details className="mt-6">
        <summary className="cursor-pointer text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
          Wetterdaten (optional)
        </summary>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
          {felder
            .filter(f => wetterdatenFelder.includes(f.feld))
            .map(feld => (
              <FeldInput
                key={feld.feld}
                feld={feld}
                value={values[feld.feld]}
                onChange={(wert) => onChange(feld.feld, wert)}
                compact
              />
            ))}
        </div>
      </details>
    </div>
  )
}
