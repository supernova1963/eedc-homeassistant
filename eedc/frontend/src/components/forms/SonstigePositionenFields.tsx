/**
 * Wiederverwendbare Komponente für "Sonstige Erträge & Ausgaben"
 * Wird in MonatsdatenForm und MonatsabschlussWizard verwendet.
 */

import { useState } from 'react'

export interface SonstigePosition {
  bezeichnung: string
  betrag: number
  typ: 'ertrag' | 'ausgabe'
}

interface Props {
  positionen: SonstigePosition[]
  onChange: (positionen: SonstigePosition[]) => void
}

export default function SonstigePositionenFields({ positionen, onChange }: Props) {
  const [expanded, setExpanded] = useState(positionen.length > 0)

  const addPosition = () => {
    onChange([...positionen, { bezeichnung: '', betrag: 0, typ: 'ausgabe' }])
    setExpanded(true)
  }

  const removePosition = (index: number) => {
    onChange(positionen.filter((_, i) => i !== index))
  }

  const updatePosition = (index: number, field: keyof SonstigePosition, value: string | number) => {
    const updated = [...positionen]
    updated[index] = { ...updated[index], [field]: value }
    onChange(updated)
  }

  const ertraege = positionen.filter(p => p.typ === 'ertrag').reduce((s, p) => s + (p.betrag || 0), 0)
  const ausgaben = positionen.filter(p => p.typ === 'ausgabe').reduce((s, p) => s + (p.betrag || 0), 0)
  const netto = ertraege - ausgaben

  return (
    <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
      {!expanded && positionen.length === 0 ? (
        <button
          type="button"
          onClick={addPosition}
          className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
        >
          + Sonstige Ertr&auml;ge &amp; Ausgaben erfassen
        </button>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
              Sonstige Ertr&auml;ge &amp; Ausgaben
            </span>
            <button
              type="button"
              onClick={addPosition}
              className="text-xs text-amber-600 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-300"
            >
              + Position
            </button>
          </div>

          {positionen.map((pos, index) => (
            <div key={index} className="grid grid-cols-12 gap-2 items-end">
              <div className="col-span-5">
                {index === 0 && (
                  <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Bezeichnung</label>
                )}
                <input
                  type="text"
                  value={pos.bezeichnung}
                  onChange={(e) => updatePosition(index, 'bezeichnung', e.target.value)}
                  placeholder="z.B. THG-Quote, Reparatur"
                  className="input text-sm py-1.5"
                />
              </div>
              <div className="col-span-3">
                {index === 0 && (
                  <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Betrag (EUR)</label>
                )}
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={pos.betrag || ''}
                  onChange={(e) => updatePosition(index, 'betrag', parseFloat(e.target.value) || 0)}
                  placeholder="0.00"
                  className="input text-sm py-1.5"
                />
              </div>
              <div className="col-span-3">
                {index === 0 && (
                  <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Typ</label>
                )}
                <select
                  value={pos.typ}
                  onChange={(e) => updatePosition(index, 'typ', e.target.value)}
                  className="input text-sm py-1.5"
                  title="Typ: Ertrag oder Ausgabe"
                >
                  <option value="ertrag">Ertrag</option>
                  <option value="ausgabe">Ausgabe</option>
                </select>
              </div>
              <div className="col-span-1 flex justify-center">
                {index === 0 && (
                  <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">&nbsp;</label>
                )}
                <button
                  type="button"
                  onClick={() => removePosition(index)}
                  className="text-red-400 hover:text-red-600 dark:text-red-500 dark:hover:text-red-400 p-1 text-sm"
                  title="Position entfernen"
                >
                  &times;
                </button>
              </div>
            </div>
          ))}

          {positionen.length > 0 && (
            <div className="text-xs flex gap-3 pt-1">
              <span className="text-green-600 dark:text-green-400">
                Ertr&auml;ge: {ertraege.toFixed(2)} &euro;
              </span>
              <span className="text-red-600 dark:text-red-400">
                Ausgaben: {ausgaben.toFixed(2)} &euro;
              </span>
              <span className={`font-medium ${netto >= 0 ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}`}>
                Netto: {netto >= 0 ? '+' : ''}{netto.toFixed(2)} &euro;
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
