/**
 * SonstigePositionenFields — EIN SoT für „Sonstige Erträge & Ausgaben".
 *
 * Konsolidiert (Slice 5, Forms→V4) die zwei früheren Near-Duplikate
 * (`forms/SonstigePositionenFields` default + `forms/sections/…` named) zu einer
 * SoT-reinen Komponente ([[feedback_bestehende_mechanik_nutzen_nicht_erfinden]]).
 * Genutzt von `MonatsdatenForm` (via `sections/InvestitionSection`, mit `invId`
 * für eindeutige aria-Labels) und `monatsabschluss/InvestitionStep` (ohne `invId`).
 *
 * Controls = SoT (Style-Guide Teil D, M1): `Input` (Bezeichnung/Betrag),
 * `SegmentControl` (Ertrag/Ausgabe = Auswahl 2, D1), `Button` (Position entfernen).
 */
import { useState } from 'react'
import { Input, SegmentControl, Button } from '../ui'
import { fmtZahl } from '../../lib'
import { X } from 'lucide-react'
import type { SonstigePosition } from '../../types'

// SoT-Kanon in types/index.ts (G19-1) — hier nur Re-Export für Bestand
export type { SonstigePosition }

interface Props {
  /** Nur für eindeutige aria-Labels bei mehreren Instanzen (Monatsdaten je Investition). */
  invId?: number
  positionen: SonstigePosition[]
  onChange: (positionen: SonstigePosition[]) => void
}

const TYP_OPTIONEN = [
  { key: 'ertrag' as const, label: 'Ertrag' },
  { key: 'ausgabe' as const, label: 'Ausgabe' },
]

export function SonstigePositionenFields({ invId, positionen, onChange }: Props) {
  const [expanded, setExpanded] = useState(positionen.length > 0)
  const suffix = invId != null ? ` (Investition ${invId})` : ''

  const addPosition = () => {
    onChange([...positionen, { bezeichnung: '', betrag: 0, typ: 'ausgabe' }])
    setExpanded(true)
  }

  const removePosition = (index: number) => {
    onChange(positionen.filter((_, i) => i !== index))
  }

  const updatePosition = (index: number, patch: Partial<SonstigePosition>) => {
    const updated = [...positionen]
    updated[index] = { ...updated[index], ...patch }
    onChange(updated)
  }

  const ertraege = positionen.filter(p => p.typ === 'ertrag').reduce((s, p) => s + (p.betrag || 0), 0)
  const ausgaben = positionen.filter(p => p.typ === 'ausgabe').reduce((s, p) => s + (p.betrag || 0), 0)
  const netto = ertraege - ausgaben

  return (
    <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
      {!expanded && positionen.length === 0 ? (
        <Button type="button" variant="ghost" size="sm" onClick={addPosition}>
          + Sonstige Erträge &amp; Ausgaben erfassen
        </Button>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
              Sonstige Erträge &amp; Ausgaben
            </span>
            <Button type="button" variant="ghost" size="sm" onClick={addPosition}>
              + Position
            </Button>
          </div>

          {positionen.map((pos, index) => (
            <div key={index} className="grid grid-cols-12 gap-2 items-end">
              <div className="col-span-5">
                <Input
                  label={index === 0 ? 'Bezeichnung' : undefined}
                  aria-label={`Bezeichnung Position ${index + 1}${suffix}`}
                  value={pos.bezeichnung}
                  onChange={(e) => updatePosition(index, { bezeichnung: e.target.value })}
                  placeholder="z.B. THG-Quote, Reparatur"
                />
              </div>
              <div className="col-span-3">
                <Input
                  label={index === 0 ? 'Betrag (€)' : undefined}
                  aria-label={`Betrag Position ${index + 1}${suffix}`}
                  type="number"
                  step="0.01"
                  min="0"
                  value={pos.betrag || ''}
                  onChange={(e) => updatePosition(index, { betrag: parseFloat(e.target.value) || 0 })}
                  placeholder="0,00"
                />
              </div>
              <div className="col-span-3">
                {index === 0 && (
                  <span className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Typ</span>
                )}
                <SegmentControl
                  ariaLabel={`Typ Position ${index + 1}${suffix}`}
                  optionen={TYP_OPTIONEN}
                  value={pos.typ}
                  onChange={(typ) => updatePosition(index, { typ })}
                />
              </div>
              <div className="col-span-1 flex justify-center">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => removePosition(index)}
                  title={`Position ${index + 1} entfernen`}
                  aria-label={`Position ${index + 1} entfernen`}
                  className="text-red-500 hover:text-red-600 dark:text-red-400"
                >
                  <X className="w-4 h-4" />
                </Button>
              </div>
            </div>
          ))}

          {positionen.length > 0 && (
            <div className="text-xs flex gap-3 pt-1">
              <span className="text-green-600 dark:text-green-400">
                Erträge: {fmtZahl(ertraege, 2)} €
              </span>
              <span className="text-red-600 dark:text-red-400">
                Ausgaben: {fmtZahl(ausgaben, 2)} €
              </span>
              <span className={`font-medium ${netto >= 0 ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}`}>
                Netto: {netto >= 0 ? '+' : ''}{fmtZahl(netto, 2)} €
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default SonstigePositionenFields
