/**
 * PVModuleStep - PV-Module/Strings im Setup-Wizard anlegen
 *
 * Ermöglicht das Anlegen von PV-Modulgruppen (Strings) mit:
 * - Bezeichnung
 * - Leistung (kWp)
 * - Ausrichtung (Süd, Ost, West, etc.)
 * - Neigung (Grad)
 * - Optionaler HA-Sensor für String-Daten
 */

import { useState } from 'react'
import { Sun, Plus, Trash2, ArrowLeft, ArrowRight, SkipForward, Info } from 'lucide-react'

export interface PVModulData {
  id: string  // Temporäre ID für UI
  bezeichnung: string
  leistung_kwp: number
  ausrichtung: string
  neigung_grad: number
  ha_entity_id?: string
}

interface PVModuleStepProps {
  anlagenLeistungKwp: number
  pvModule: PVModulData[]
  isLoading: boolean
  error: string | null
  onAddModule: (modul: Omit<PVModulData, 'id'>) => void
  onUpdateModule: (id: string, data: Partial<PVModulData>) => void
  onRemoveModule: (id: string) => void
  onNext: () => void
  onSkip: () => void
  onBack: () => void
}

const AUSRICHTUNG_OPTIONS = [
  { value: 'Süd', label: 'Süd (optimal)' },
  { value: 'Südost', label: 'Südost' },
  { value: 'Südwest', label: 'Südwest' },
  { value: 'Ost', label: 'Ost' },
  { value: 'West', label: 'West' },
  { value: 'Nord', label: 'Nord' },
]

export default function PVModuleStep({
  anlagenLeistungKwp,
  pvModule,
  isLoading,
  error,
  onAddModule,
  onUpdateModule,
  onRemoveModule,
  onNext,
  onSkip,
  onBack,
}: PVModuleStepProps) {
  // Formular für neues Modul
  const [showAddForm, setShowAddForm] = useState(pvModule.length === 0)
  const [newModule, setNewModule] = useState({
    bezeichnung: '',
    leistung_kwp: '',
    ausrichtung: 'Süd',
    neigung_grad: '30',
  })

  // Gesamtleistung der Module
  const totalModuleKwp = pvModule.reduce((sum, m) => sum + m.leistung_kwp, 0)
  const remainingKwp = anlagenLeistungKwp - totalModuleKwp

  const handleAddModule = () => {
    if (!newModule.bezeichnung.trim() || !newModule.leistung_kwp) return

    onAddModule({
      bezeichnung: newModule.bezeichnung.trim(),
      leistung_kwp: parseFloat(newModule.leistung_kwp),
      ausrichtung: newModule.ausrichtung,
      neigung_grad: parseFloat(newModule.neigung_grad),
    })

    // Formular zurücksetzen
    setNewModule({
      bezeichnung: '',
      leistung_kwp: remainingKwp > 0 ? Math.min(remainingKwp, parseFloat(newModule.leistung_kwp)).toString() : '',
      ausrichtung: 'Süd',
      neigung_grad: '30',
    })
    setShowAddForm(false)
  }

  const suggestModuleName = () => {
    const count = pvModule.length + 1
    const directions: Record<string, string> = {
      'Süd': 'Süd',
      'Südost': 'SO',
      'Südwest': 'SW',
      'Ost': 'Ost',
      'West': 'West',
      'Nord': 'Nord',
    }
    return `PV ${directions[newModule.ausrichtung] || newModule.ausrichtung} ${count}`
  }

  return (
    <div>
      <div className="p-6 md:p-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/30 rounded-xl flex items-center justify-center">
            <Sun className="w-5 h-5 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              PV-Module / Strings
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Modulgruppen nach Ausrichtung für PVGIS-Prognose
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        {/* Leistungs-Übersicht */}
        <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-xl">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-sm text-gray-500 dark:text-gray-400">Anlagenleistung:</span>
              <span className="ml-2 font-semibold text-gray-900 dark:text-white">
                {anlagenLeistungKwp} kWp
              </span>
            </div>
            <div>
              <span className="text-sm text-gray-500 dark:text-gray-400">Module zugewiesen:</span>
              <span className={`ml-2 font-semibold ${
                totalModuleKwp === anlagenLeistungKwp
                  ? 'text-green-600 dark:text-green-400'
                  : totalModuleKwp > anlagenLeistungKwp
                    ? 'text-red-600 dark:text-red-400'
                    : 'text-amber-600 dark:text-amber-400'
              }`}>
                {totalModuleKwp.toFixed(2)} kWp
              </span>
            </div>
          </div>
          {remainingKwp > 0 && (
            <p className="mt-2 text-sm text-amber-600 dark:text-amber-400">
              Noch {remainingKwp.toFixed(2)} kWp nicht zugewiesen
            </p>
          )}
        </div>

        {/* Bestehende Module */}
        {pvModule.length > 0 && (
          <div className="mb-6 space-y-3">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
              Angelegte Module ({pvModule.length})
            </h3>
            {pvModule.map((modul) => (
              <div
                key={modul.id}
                className="p-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                        Bezeichnung
                      </label>
                      <input
                        type="text"
                        value={modul.bezeichnung}
                        onChange={(e) => onUpdateModule(modul.id, { bezeichnung: e.target.value })}
                        className="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                        Leistung (kWp)
                      </label>
                      <input
                        type="number"
                        value={modul.leistung_kwp}
                        onChange={(e) => onUpdateModule(modul.id, { leistung_kwp: parseFloat(e.target.value) || 0 })}
                        step="0.01"
                        min="0.1"
                        className="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                        Ausrichtung
                      </label>
                      <select
                        value={modul.ausrichtung}
                        onChange={(e) => onUpdateModule(modul.id, { ausrichtung: e.target.value })}
                        className="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      >
                        {AUSRICHTUNG_OPTIONS.map(opt => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                        Neigung (°)
                      </label>
                      <input
                        type="number"
                        value={modul.neigung_grad}
                        onChange={(e) => onUpdateModule(modul.id, { neigung_grad: parseFloat(e.target.value) || 0 })}
                        min="0"
                        max="90"
                        className="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onRemoveModule(modul.id)}
                    className="ml-4 p-2 text-gray-400 hover:text-red-500 transition-colors"
                    title="Modul entfernen"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Neues Modul hinzufügen */}
        {showAddForm ? (
          <div className="p-4 bg-amber-50 dark:bg-amber-900/20 border-2 border-dashed border-amber-300 dark:border-amber-700 rounded-xl">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4">
              Neues PV-Modul anlegen
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  Bezeichnung
                </label>
                <input
                  type="text"
                  value={newModule.bezeichnung}
                  onChange={(e) => setNewModule(prev => ({ ...prev, bezeichnung: e.target.value }))}
                  onFocus={() => {
                    if (!newModule.bezeichnung) {
                      setNewModule(prev => ({ ...prev, bezeichnung: suggestModuleName() }))
                    }
                  }}
                  placeholder="z.B. PV Süd 1"
                  className="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  Leistung (kWp)
                </label>
                <input
                  type="number"
                  value={newModule.leistung_kwp}
                  onChange={(e) => setNewModule(prev => ({ ...prev, leistung_kwp: e.target.value }))}
                  placeholder={remainingKwp > 0 ? remainingKwp.toFixed(2) : '5.0'}
                  step="0.01"
                  min="0.1"
                  className="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  Ausrichtung
                </label>
                <select
                  value={newModule.ausrichtung}
                  onChange={(e) => setNewModule(prev => ({ ...prev, ausrichtung: e.target.value }))}
                  className="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  {AUSRICHTUNG_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  Neigung (°)
                </label>
                <input
                  type="number"
                  value={newModule.neigung_grad}
                  onChange={(e) => setNewModule(prev => ({ ...prev, neigung_grad: e.target.value }))}
                  placeholder="30"
                  min="0"
                  max="90"
                  className="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleAddModule}
                disabled={!newModule.bezeichnung.trim() || !newModule.leistung_kwp}
                className="px-4 py-2 bg-amber-500 text-white text-sm font-medium rounded-lg hover:bg-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Modul hinzufügen
              </button>
              {pvModule.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowAddForm(false)}
                  className="px-4 py-2 text-gray-600 dark:text-gray-400 text-sm hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
                >
                  Abbrechen
                </button>
              )}
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setShowAddForm(true)}
            className="w-full p-4 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl text-gray-500 dark:text-gray-400 hover:border-amber-400 hover:text-amber-600 dark:hover:border-amber-500 dark:hover:text-amber-400 transition-colors"
          >
            <Plus className="w-5 h-5 inline mr-2" />
            Weiteres PV-Modul hinzufügen
          </button>
        )}

        {/* Info-Box */}
        <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
          <p className="text-sm text-blue-700 dark:text-blue-300 flex items-start gap-2">
            <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>
              <strong>Warum Module anlegen?</strong> Für die PVGIS-Ertragsprognose benötigen wir
              die Ausrichtung und Neigung jeder Modulgruppe. Bei Ost-West-Anlagen legen Sie
              zwei Module mit unterschiedlicher Ausrichtung an.
            </span>
          </p>
        </div>
      </div>

      {/* Footer */}
      <div className="px-6 md:px-8 py-4 bg-gray-50 dark:bg-gray-700/50 border-t border-gray-200 dark:border-gray-700 flex justify-between">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-2 px-4 py-2 text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Zurück
        </button>

        <div className="flex gap-3">
          {pvModule.length === 0 && (
            <button
              type="button"
              onClick={onSkip}
              className="inline-flex items-center gap-2 px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
            >
              <SkipForward className="w-4 h-4" />
              Später anlegen
            </button>
          )}

          <button
            type="button"
            onClick={onNext}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-amber-500 text-white font-medium rounded-lg hover:bg-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Speichern...
              </>
            ) : (
              <>
                Weiter
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
