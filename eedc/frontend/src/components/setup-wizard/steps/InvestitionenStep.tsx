/**
 * InvestitionenStep - Investitionen vervollständigen im Setup-Wizard
 *
 * v0.8.0 - Komplett neu: Alle Investitionen auf einer Seite bearbeiten,
 * gruppiert nach Typ, mit Möglichkeit zum Hinzufügen und Löschen.
 */

import { useState } from 'react'
import {
  Car,
  Battery,
  Plug,
  Cpu,
  ArrowLeft,
  ArrowRight,
  Info,
  Flame,
  Sun,
  Plus,
  Trash2,
  ChevronDown,
  ChevronRight,
  Package,
  AlertCircle,
} from 'lucide-react'
import type { Investition, Anlage, InvestitionTyp } from '../../../types'
import { INVESTITION_TYP_ORDER, INVESTITION_TYP_LABELS, PARENT_MAPPING } from '../../../hooks/useSetupWizard'

interface InvestitionenStepProps {
  investitionen: Investition[]
  anlage: Anlage | null
  isLoading: boolean
  error: string | null
  onUpdateInvestition: (id: number, data: Partial<Investition>) => Promise<void>
  onDeleteInvestition: (id: number) => Promise<void>
  onAddInvestition: (typ: InvestitionTyp) => Promise<Investition>
  onNext: () => void
  onBack: () => void
}

// Icon basierend auf Gerätetyp
function getDeviceIcon(typ: InvestitionTyp) {
  switch (typ) {
    case 'e-auto':
      return <Car className="w-5 h-5" />
    case 'speicher':
      return <Battery className="w-5 h-5" />
    case 'wallbox':
      return <Plug className="w-5 h-5" />
    case 'wechselrichter':
      return <Cpu className="w-5 h-5" />
    case 'waermepumpe':
      return <Flame className="w-5 h-5" />
    case 'balkonkraftwerk':
    case 'pv-module':
      return <Sun className="w-5 h-5" />
    default:
      return <Package className="w-5 h-5" />
  }
}

// Investition-Form für einzelne Investition
function InvestitionForm({
  investition,
  allInvestitionen,
  anlage,
  onUpdate,
  onDelete,
}: {
  investition: Investition
  allInvestitionen: Investition[]
  anlage: Anlage | null
  onUpdate: (data: Partial<Investition>) => void
  onDelete: () => void
}) {
  const [expanded, setExpanded] = useState(true)
  const [confirmDelete, setConfirmDelete] = useState(false)

  // Mögliche Parents für diesen Typ
  const parentTyp = PARENT_MAPPING[investition.typ]
  const possibleParents = parentTyp
    ? allInvestitionen.filter(i => i.typ === parentTyp && i.id !== investition.id)
    : []

  // Typ-spezifische Parameter aus dem parameter-Objekt extrahieren
  const getParam = (key: string) => investition.parameter?.[key] as number | string | undefined

  const updateParam = (key: string, value: unknown) => {
    onUpdate({
      parameter: {
        ...investition.parameter,
        [key]: value,
      },
    })
  }

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden bg-white dark:bg-gray-800">
      {/* Header - klickbar zum Auf-/Zuklappen */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
      >
        <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/30 rounded-lg flex items-center justify-center text-amber-600 dark:text-amber-400 flex-shrink-0">
          {getDeviceIcon(investition.typ)}
        </div>
        <div className="flex-1 text-left min-w-0">
          <div className="font-medium text-gray-900 dark:text-white truncate">
            {investition.bezeichnung || INVESTITION_TYP_LABELS[investition.typ]}
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">
            {INVESTITION_TYP_LABELS[investition.typ]}
            {investition.anschaffungskosten_gesamt ? (
              <span className="ml-2">• {investition.anschaffungskosten_gesamt.toLocaleString('de-DE')} €</span>
            ) : null}
          </div>
        </div>
        {expanded ? (
          <ChevronDown className="w-5 h-5 text-gray-400 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-5 h-5 text-gray-400 flex-shrink-0" />
        )}
      </button>

      {/* Form Content */}
      {expanded && (
        <div className="p-4 pt-0 space-y-4 border-t border-gray-100 dark:border-gray-700">
          {/* Basis-Felder */}
          <div className="grid md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Bezeichnung *
              </label>
              <input
                type="text"
                value={investition.bezeichnung}
                onChange={(e) => onUpdate({ bezeichnung: e.target.value })}
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                placeholder="z.B. SMA Sunny Tripower"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Anschaffungsdatum *
              </label>
              <input
                type="date"
                value={investition.anschaffungsdatum || ''}
                onChange={(e) => onUpdate({ anschaffungsdatum: e.target.value || undefined })}
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Kaufpreis (€) *
              </label>
              <input
                type="number"
                value={investition.anschaffungskosten_gesamt ?? ''}
                onChange={(e) => onUpdate({ anschaffungskosten_gesamt: parseFloat(e.target.value) || 0 })}
                placeholder="z.B. 5000"
                min="0"
                step="100"
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
              />
            </div>
          </div>

          {/* Parent-Zuordnung wenn möglich */}
          {possibleParents.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Gehört zu ({INVESTITION_TYP_LABELS[parentTyp!]})
              </label>
              <select
                value={investition.parent_investition_id || ''}
                onChange={(e) => onUpdate({ parent_investition_id: e.target.value ? parseInt(e.target.value) : undefined })}
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
              >
                <option value="">-- Kein Parent --</option>
                {possibleParents.map(p => (
                  <option key={p.id} value={p.id}>{p.bezeichnung}</option>
                ))}
              </select>
            </div>
          )}

          {/* Typ-spezifische Felder */}
          {investition.typ === 'wechselrichter' && (
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Max. Leistung (kW)
                </label>
                <input
                  type="number"
                  value={getParam('leistung_kw') ?? ''}
                  onChange={(e) => updateParam('leistung_kw', parseFloat(e.target.value) || undefined)}
                  placeholder="z.B. 10"
                  min="0"
                  step="0.1"
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                />
              </div>
            </div>
          )}

          {investition.typ === 'pv-module' && (
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Leistung (kWp) *
                </label>
                <input
                  type="number"
                  value={investition.leistung_kwp ?? ''}
                  onChange={(e) => onUpdate({ leistung_kwp: parseFloat(e.target.value) || undefined })}
                  placeholder="z.B. 10"
                  min="0"
                  step="0.1"
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Ausrichtung
                </label>
                <select
                  value={investition.ausrichtung || anlage?.ausrichtung || ''}
                  onChange={(e) => onUpdate({ ausrichtung: e.target.value || undefined })}
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                >
                  <option value="">-- Wählen --</option>
                  <option value="Süd">Süd</option>
                  <option value="Südost">Südost</option>
                  <option value="Südwest">Südwest</option>
                  <option value="Ost">Ost</option>
                  <option value="West">West</option>
                  <option value="Nord">Nord</option>
                  <option value="Ost-West">Ost-West</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Neigung (Grad)
                </label>
                <input
                  type="number"
                  value={investition.neigung_grad ?? anlage?.neigung_grad ?? ''}
                  onChange={(e) => onUpdate({ neigung_grad: parseFloat(e.target.value) || undefined })}
                  placeholder="z.B. 35"
                  min="0"
                  max="90"
                  step="1"
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                />
              </div>
            </div>
          )}

          {investition.typ === 'speicher' && (
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Kapazität (kWh)
                </label>
                <input
                  type="number"
                  value={getParam('kapazitaet_kwh') ?? ''}
                  onChange={(e) => updateParam('kapazitaet_kwh', parseFloat(e.target.value) || undefined)}
                  placeholder="z.B. 10"
                  min="0"
                  step="0.1"
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                />
              </div>
            </div>
          )}

          {investition.typ === 'wallbox' && (
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Max. Ladeleistung (kW)
                </label>
                <input
                  type="number"
                  value={getParam('leistung_kw') ?? ''}
                  onChange={(e) => updateParam('leistung_kw', parseFloat(e.target.value) || undefined)}
                  placeholder="z.B. 11"
                  min="0"
                  step="0.1"
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                />
              </div>
            </div>
          )}

          {investition.typ === 'e-auto' && (
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Batteriekapazität (kWh)
                </label>
                <input
                  type="number"
                  value={getParam('batterie_kwh') ?? ''}
                  onChange={(e) => updateParam('batterie_kwh', parseFloat(e.target.value) || undefined)}
                  placeholder="z.B. 66"
                  min="0"
                  step="0.1"
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Verbrauch (kWh/100km)
                </label>
                <input
                  type="number"
                  value={getParam('verbrauch_kwh_100km') ?? ''}
                  onChange={(e) => updateParam('verbrauch_kwh_100km', parseFloat(e.target.value) || undefined)}
                  placeholder="z.B. 15"
                  min="0"
                  step="0.1"
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                />
              </div>
            </div>
          )}

          {investition.typ === 'waermepumpe' && (
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Nennleistung (kW)
                </label>
                <input
                  type="number"
                  value={getParam('leistung_kw') ?? ''}
                  onChange={(e) => updateParam('leistung_kw', parseFloat(e.target.value) || undefined)}
                  placeholder="z.B. 9"
                  min="0"
                  step="0.1"
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  COP (Leistungszahl)
                </label>
                <input
                  type="number"
                  value={getParam('cop') ?? '3.5'}
                  onChange={(e) => updateParam('cop', parseFloat(e.target.value) || undefined)}
                  placeholder="z.B. 3.5"
                  min="1"
                  max="10"
                  step="0.1"
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                />
              </div>
            </div>
          )}

          {investition.typ === 'balkonkraftwerk' && (
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Leistung (Wp)
                </label>
                <input
                  type="number"
                  value={getParam('leistung_wp') ?? ''}
                  onChange={(e) => updateParam('leistung_wp', parseFloat(e.target.value) || undefined)}
                  placeholder="z.B. 800"
                  min="0"
                  step="10"
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Anzahl Module
                </label>
                <input
                  type="number"
                  value={getParam('anzahl') ?? ''}
                  onChange={(e) => updateParam('anzahl', parseInt(e.target.value) || undefined)}
                  placeholder="z.B. 2"
                  min="1"
                  step="1"
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                />
              </div>
            </div>
          )}

          {/* Löschen-Button */}
          <div className="pt-2 border-t border-gray-100 dark:border-gray-700">
            {confirmDelete ? (
              <div className="flex items-center gap-3">
                <span className="text-sm text-red-600 dark:text-red-400">
                  Wirklich löschen?
                </span>
                <button
                  type="button"
                  onClick={() => {
                    onDelete()
                    setConfirmDelete(false)
                  }}
                  className="px-3 py-1.5 text-sm text-white bg-red-500 rounded-lg hover:bg-red-600 transition-colors"
                >
                  Ja, löschen
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmDelete(false)}
                  className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
                >
                  Abbrechen
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                className="inline-flex items-center gap-2 px-3 py-1.5 text-sm text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
              >
                <Trash2 className="w-4 h-4" />
                Investition löschen
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Add Investment Button
function AddInvestitionButton({ onAdd }: { onAdd: (typ: InvestitionTyp) => void }) {
  const [showMenu, setShowMenu] = useState(false)

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setShowMenu(!showMenu)}
        className="inline-flex items-center gap-2 px-4 py-2.5 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 font-medium rounded-lg hover:bg-amber-200 dark:hover:bg-amber-900/50 transition-colors"
      >
        <Plus className="w-5 h-5" />
        Investition hinzufügen
      </button>

      {showMenu && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setShowMenu(false)}
          />
          {/* Menu */}
          <div className="absolute left-0 mt-2 w-64 bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-200 dark:border-gray-700 z-20 py-2">
            {INVESTITION_TYP_ORDER.map(typ => (
              <button
                key={typ}
                type="button"
                onClick={() => {
                  onAdd(typ)
                  setShowMenu(false)
                }}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors text-left"
              >
                <span className="text-amber-600 dark:text-amber-400">
                  {getDeviceIcon(typ)}
                </span>
                <span className="text-gray-900 dark:text-white">
                  {INVESTITION_TYP_LABELS[typ]}
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default function InvestitionenStep({
  investitionen,
  anlage,
  isLoading,
  error,
  onUpdateInvestition,
  onDeleteInvestition,
  onAddInvestition,
  onNext,
  onBack,
}: InvestitionenStepProps) {
  const [addingType, setAddingType] = useState<InvestitionTyp | null>(null)

  // Investitionen nach Typ gruppieren und sortieren
  const groupedInvestitionen = INVESTITION_TYP_ORDER.reduce((acc, typ) => {
    const items = investitionen.filter(i => i.typ === typ)
    if (items.length > 0) {
      acc.push({ typ, items })
    }
    return acc
  }, [] as { typ: InvestitionTyp; items: Investition[] }[])

  // Handler für Hinzufügen
  const handleAdd = async (typ: InvestitionTyp) => {
    setAddingType(typ)
    try {
      await onAddInvestition(typ)
    } finally {
      setAddingType(null)
    }
  }

  // Keine Investitionen
  if (investitionen.length === 0 && !isLoading) {
    return (
      <div>
        <div className="p-6 md:p-8">
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-gray-100 dark:bg-gray-700 rounded-full mb-4">
              <Package className="w-8 h-8 text-gray-400" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
              Keine Investitionen vorhanden
            </h2>
            <p className="text-gray-500 dark:text-gray-400 max-w-md mx-auto mb-6">
              Sie können jetzt manuell Investitionen anlegen oder diesen Schritt überspringen
              und später unter Einstellungen → Investitionen ergänzen.
            </p>

            <AddInvestitionButton onAdd={handleAdd} />

            {addingType && (
              <p className="mt-4 text-sm text-amber-600 dark:text-amber-400">
                Füge {INVESTITION_TYP_LABELS[addingType]} hinzu...
              </p>
            )}
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

          <button
            type="button"
            onClick={onNext}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-amber-500 text-white font-medium rounded-lg hover:bg-amber-600 transition-colors"
          >
            Weiter ohne Investitionen
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="p-6 md:p-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-1">
              Investitionen vervollständigen
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Ergänzen Sie Kaufdatum, Kaufpreis und technische Details.
              Diese Angaben werden für die ROI-Berechnung benötigt.
            </p>
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">
            {investitionen.length} Investition{investitionen.length !== 1 ? 'en' : ''}
          </div>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <span className="text-red-700 dark:text-red-300">{error}</span>
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="text-center py-8">
            <div className="w-8 h-8 border-2 border-amber-500/30 border-t-amber-500 rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-500 dark:text-gray-400">Lade Investitionen...</p>
          </div>
        )}

        {/* Investitionen gruppiert nach Typ */}
        {!isLoading && (
          <div className="space-y-6">
            {groupedInvestitionen.map(({ typ, items }) => (
              <div key={typ}>
                {/* Typ-Header */}
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-amber-600 dark:text-amber-400">
                    {getDeviceIcon(typ)}
                  </span>
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                    {INVESTITION_TYP_LABELS[typ]} ({items.length})
                  </h3>
                </div>

                {/* Investitionen dieses Typs */}
                <div className="space-y-3">
                  {items.map(inv => (
                    <InvestitionForm
                      key={inv.id}
                      investition={inv}
                      allInvestitionen={investitionen}
                      anlage={anlage}
                      onUpdate={(data) => onUpdateInvestition(inv.id, data)}
                      onDelete={() => onDeleteInvestition(inv.id)}
                    />
                  ))}
                </div>
              </div>
            ))}

            {/* Hinzufügen-Button */}
            <div className="pt-4">
              <AddInvestitionButton onAdd={handleAdd} />
              {addingType && (
                <span className="ml-3 text-sm text-amber-600 dark:text-amber-400">
                  Füge {INVESTITION_TYP_LABELS[addingType]} hinzu...
                </span>
              )}
            </div>
          </div>
        )}

        {/* Info-Box */}
        <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
          <p className="text-sm text-blue-700 dark:text-blue-300 flex items-start gap-2">
            <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>
              <strong>Pflichtfelder</strong> sind mit * markiert. Der Kaufpreis ist besonders wichtig
              für die Amortisationsberechnung. Sie können alle Angaben später jederzeit unter
              Einstellungen → Investitionen ändern.
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

        <button
          type="button"
          onClick={onNext}
          disabled={isLoading}
          className="inline-flex items-center gap-2 px-6 py-2.5 bg-amber-500 text-white font-medium rounded-lg hover:bg-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Weiter
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
