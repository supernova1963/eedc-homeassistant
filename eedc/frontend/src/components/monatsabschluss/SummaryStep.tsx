import { CheckCircle, FileText } from 'lucide-react'
import type { MonatsabschlussResponse } from '../../api'
import type { WizardState } from './types'
import SummaryRow from './SummaryRow'
import { TYP_ICONS } from './helpers'

export default function SummaryStep({
  data,
  values,
}: {
  data: MonatsabschlussResponse
  values: WizardState
}) {
  // Statistiken berechnen
  let gefuellt = 0
  let gesamt = 0

  // Gruppierung über das gruppe-Attribut aus der Backend-Registry
  const zaehlerFelder = data.basis_felder.filter(f => f.gruppe === 'zaehler')
  const zusatzFelder = data.basis_felder.filter(f => f.gruppe !== 'zaehler')

  for (const feld of zaehlerFelder) {
    gesamt++
    if (values.basis[feld.feld] !== null && values.basis[feld.feld] !== undefined) {
      gefuellt++
    }
  }

  for (const inv of data.investitionen) {
    for (const feld of inv.felder) {
      const wert = values.investitionen[inv.id]?.[feld.feld]
      const hatWert = wert !== null && wert !== undefined
      const hatQuelle = feld.strategie || feld.vorschlaege.length > 0 || feld.aktueller_wert != null
      // Felder ohne Wert und ohne Datenquelle nicht als "fehlend" zählen
      if (!hatWert && !hatQuelle) continue
      gesamt++
      if (hatWert) gefuellt++
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
        <CheckCircle className="w-5 h-5 text-green-500" />
        Zusammenfassung
      </h2>

      {/* Statistik */}
      <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
        <div className="flex items-center gap-2">
          <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
          <span className="font-medium text-green-800 dark:text-green-200">
            {gefuellt} von {gesamt} Feldern ausgefüllt
          </span>
        </div>
      </div>

      {/* Basis-Werte */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/50">
          <h3 className="font-medium text-gray-900 dark:text-white">Zählerdaten</h3>
        </div>
        <div className="divide-y divide-gray-100 dark:divide-gray-700">
          {zaehlerFelder.map(feld => (
              <SummaryRow
                key={feld.feld}
                label={feld.label}
                wert={values.basis[feld.feld]}
                einheit={feld.einheit}
              />
            ))}
          {zusatzFelder.map(feld => (
            <SummaryRow
              key={feld.feld}
              label={feld.label}
              wert={values.basis[feld.feld]}
              einheit={feld.einheit}
              optional
            />
          ))}
        </div>
      </div>

      {/* Investitionen */}
      {data.investitionen.map(inv => (
        <div
          key={inv.id}
          className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden"
        >
          <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/50 flex items-center gap-2">
            {TYP_ICONS[inv.typ]}
            <h3 className="font-medium text-gray-900 dark:text-white">{inv.bezeichnung}</h3>
          </div>
          <div className="divide-y divide-gray-100 dark:divide-gray-700">
            {inv.felder.map(feld => {
              const wert = values.investitionen[inv.id]?.[feld.feld]
              const hatQuelle = feld.strategie || feld.vorschlaege.length > 0 || feld.aktueller_wert != null
              return (
                <SummaryRow
                  key={feld.feld}
                  label={feld.label}
                  wert={wert}
                  einheit={feld.einheit}
                  optional={!hatQuelle}
                />
              )
            })}
          </div>
        </div>
      ))}

      {/* Optionale Felder */}
      {data.optionale_felder && data.optionale_felder.length > 0 && (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/50 flex items-center gap-2">
            <FileText className="w-5 h-5 text-gray-500" />
            <h3 className="font-medium text-gray-900 dark:text-white">Sonstiges</h3>
          </div>
          <div className="divide-y divide-gray-100 dark:divide-gray-700">
            {data.optionale_felder.map(feld => (
              <SummaryRow
                key={feld.feld}
                label={feld.label}
                wert={feld.typ === 'text'
                  ? (values.optionale[feld.feld] as string)
                  : (values.optionale[feld.feld] as number)}
                einheit={feld.einheit}
                isText={feld.typ === 'text'}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
