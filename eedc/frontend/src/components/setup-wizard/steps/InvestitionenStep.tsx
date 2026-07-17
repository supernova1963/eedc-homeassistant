/**
 * InvestitionenStep - Investitionen vervollständigen im Setup-Wizard
 *
 * Slice 6 (Setup→V4-SoT): der Inline-Editor + Add-Menü sind nach
 * `../sections/` ausgelagert; Felder auf SoT (Variante B).
 * Paket F (2026-07-17): Aktions-Buttons auf `Button`-SoT (amber = Setup-Identitäts-
 * Variante); Auswahl-Karten/Typ-Kacheln bleiben rohe Struktur-Elemente (ROH_INFRA).
 */

import { useState, useEffect, useRef } from 'react'
import { ArrowLeft, ArrowRight, Sun, Plus } from 'lucide-react'
import { Alert, Button } from '../../ui'
import type { Investition, Anlage, InvestitionTyp } from '../../../types'
import { INVESTITION_TYP_ORDER, TYP_LABELS as INVESTITION_TYP_LABELS } from '../../../lib/constants'
import { SetupInvestitionForm } from '../sections/SetupInvestitionForm'
import { SetupInvestitionMenu } from '../sections/SetupInvestitionMenu'
import { getDeviceIcon } from '../sections/setupInvestitionHelpers'

interface InvestitionenStepProps {
  investitionen: Investition[]
  anlage: Anlage | null
  isLoading: boolean
  error: string | null
  onUpdateInvestition: (id: number, data: Partial<Investition>) => Promise<void>
  onDeleteInvestition: (id: number) => Promise<void>
  onAddInvestition: (typ: InvestitionTyp) => Promise<Investition>
  onCreateDefaultPVSystem?: () => Promise<void>
  onNext: () => void
  onBack: () => void
}

export default function InvestitionenStep({
  investitionen,
  anlage,
  isLoading,
  error,
  onUpdateInvestition,
  onDeleteInvestition,
  onAddInvestition,
  onCreateDefaultPVSystem,
  onNext,
  onBack,
}: InvestitionenStepProps) {
  const [addingType, setAddingType] = useState<InvestitionTyp | null>(null)
  const [newlyAddedId, setNewlyAddedId] = useState<number | null>(null)
  const newInvestitionRef = useRef<HTMLDivElement>(null)

  // Scroll zur neu hinzugefügten Investition
  useEffect(() => {
    if (newlyAddedId && newInvestitionRef.current) {
      newInvestitionRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
      const timer = setTimeout(() => setNewlyAddedId(null), 2000)
      return () => clearTimeout(timer)
    }
  }, [newlyAddedId])

  // Investitionen nach Typ gruppieren und sortieren
  const groupedInvestitionen = INVESTITION_TYP_ORDER.reduce((acc, typ) => {
    const items = investitionen.filter(i => i.typ === typ)
    if (items.length > 0) acc.push({ typ, items })
    return acc
  }, [] as { typ: InvestitionTyp; items: Investition[] }[])

  const handleAdd = async (typ: InvestitionTyp) => {
    setAddingType(typ)
    try {
      const newInvestition = await onAddInvestition(typ)
      if (newInvestition?.id) setNewlyAddedId(newInvestition.id)
    } finally {
      setAddingType(null)
    }
  }

  // Keine Investitionen - Startseite mit Schnellstart-Optionen
  if (investitionen.length === 0 && !isLoading) {
    return (
      <div>
        <div className="p-6 md:p-8">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-amber-100 dark:bg-amber-900/30 rounded-full mb-4">
              <Sun className="w-8 h-8 text-amber-600 dark:text-amber-400" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
              PV-System einrichten
            </h2>
            <p className="text-gray-500 dark:text-gray-400 max-w-md mx-auto">
              Erfassen Sie Ihre PV-Komponenten für die Ertragsanalyse und ROI-Berechnung.
            </p>
          </div>

          {/* Schnellstart-Karte + Typ-Kacheln unten: Struktur-Elemente (mehrzeilige
              Auswahl-Karten), keine Aktions-Buttons — rohe <button> sind hier die
              Impl (ROH_INFRA-Freigabe Gernot 2026-07-17, Paket F). */}
          {onCreateDefaultPVSystem && (
            <div className="mb-8">
              <button
                type="button"
                onClick={onCreateDefaultPVSystem}
                disabled={isLoading}
                className="w-full p-6 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-900/20 dark:to-orange-900/20 border-2 border-amber-200 dark:border-amber-800 rounded-xl hover:border-amber-400 dark:hover:border-amber-600 transition-all group"
              >
                <div className="flex items-center gap-4">
                  <div className="w-14 h-14 bg-amber-500 rounded-xl flex items-center justify-center flex-shrink-0 group-hover:scale-105 transition-transform">
                    <Sun className="w-7 h-7 text-white" />
                  </div>
                  <div className="text-left flex-1">
                    <h3 className="font-semibold text-gray-900 dark:text-white text-lg">
                      PV-System anlegen (empfohlen)
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      Erstellt automatisch Wechselrichter + PV-Module mit {anlage?.leistung_kwp || 0} kWp
                    </p>
                  </div>
                  <ArrowRight className="w-5 h-5 text-amber-500 group-hover:translate-x-1 transition-transform" />
                </div>
              </button>
            </div>
          )}

          <div className="relative mb-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-200 dark:border-gray-700" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-3 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                oder einzeln hinzufügen
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
            {(['balkonkraftwerk', 'speicher', 'wallbox', 'waermepumpe', 'e-auto'] as InvestitionTyp[]).map(typ => (
              <button
                key={typ}
                type="button"
                onClick={() => handleAdd(typ)}
                disabled={addingType !== null}
                className="p-4 border border-gray-200 dark:border-gray-700 rounded-xl hover:border-amber-400 dark:hover:border-amber-600 hover:bg-amber-50 dark:hover:bg-amber-900/10 transition-all text-center"
              >
                <div className="w-10 h-10 mx-auto mb-2 bg-gray-100 dark:bg-gray-700 rounded-lg flex items-center justify-center text-gray-600 dark:text-gray-400">
                  {getDeviceIcon(typ)}
                </div>
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {INVESTITION_TYP_LABELS[typ]}
                </span>
              </button>
            ))}
          </div>

          <div className="text-center">
            <SetupInvestitionMenu onAdd={handleAdd} />
          </div>

          {addingType && (
            <p className="mt-4 text-sm text-amber-600 dark:text-amber-400 text-center">
              Füge {INVESTITION_TYP_LABELS[addingType]} hinzu...
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 md:px-8 py-4 bg-gray-50 dark:bg-gray-700/50 border-t border-gray-200 dark:border-gray-700 flex justify-between">
          <Button type="button" variant="ghost" onClick={onBack}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Zurück
          </Button>
          <Button type="button" variant="ghost" onClick={onNext}>
            Überspringen
            <ArrowRight className="w-4 h-4 ml-2" />
          </Button>
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

        {error && <Alert type="error" className="mb-6">{error}</Alert>}

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
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-amber-600 dark:text-amber-400">{getDeviceIcon(typ)}</span>
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                    {INVESTITION_TYP_LABELS[typ]} ({items.length})
                  </h3>
                </div>

                <div className="space-y-3">
                  {items.map(inv => (
                    <div
                      key={inv.id}
                      ref={inv.id === newlyAddedId ? newInvestitionRef : undefined}
                      className={`transition-all duration-500 ${
                        inv.id === newlyAddedId
                          ? 'ring-2 ring-amber-500 ring-offset-2 dark:ring-offset-gray-900 rounded-xl'
                          : ''
                      }`}
                    >
                      <SetupInvestitionForm
                        investition={inv}
                        allInvestitionen={investitionen}
                        onUpdate={(data) => onUpdateInvestition(inv.id, data)}
                        onDelete={() => onDeleteInvestition(inv.id)}
                        isNew={inv.id === newlyAddedId}
                      />
                    </div>
                  ))}
                </div>
              </div>
            ))}

            {/* Weitere Komponenten hinzufügen */}
            <div className="pt-6 border-t border-gray-200 dark:border-gray-700">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                <Plus className="w-4 h-4 text-amber-500" />
                Weitere Komponenten hinzufügen
              </h3>

              {/* Typ-Kacheln: Struktur-Elemente, rohes <button> = Impl (ROH_INFRA, s. o.) */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
                {(['speicher', 'wallbox', 'waermepumpe', 'e-auto', 'balkonkraftwerk'] as InvestitionTyp[]).map(typ => {
                  const hasType = investitionen.some(i => i.typ === typ)
                  return (
                    <button
                      key={typ}
                      type="button"
                      onClick={() => handleAdd(typ)}
                      disabled={addingType !== null}
                      className={`p-3 border rounded-xl transition-all text-center ${
                        hasType
                          ? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20'
                          : 'border-gray-200 dark:border-gray-700 hover:border-amber-400 dark:hover:border-amber-600 hover:bg-amber-50 dark:hover:bg-amber-900/10'
                      }`}
                    >
                      <div className={`w-8 h-8 mx-auto mb-1 rounded-lg flex items-center justify-center ${
                        hasType
                          ? 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400'
                          : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                      }`}>
                        {getDeviceIcon(typ)}
                      </div>
                      <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                        {INVESTITION_TYP_LABELS[typ]}
                        {hasType && ' ✓'}
                      </span>
                    </button>
                  )
                })}
              </div>

              <SetupInvestitionMenu onAdd={handleAdd} />
              {addingType && (
                <span className="ml-3 text-sm text-amber-600 dark:text-amber-400">
                  Füge {INVESTITION_TYP_LABELS[addingType]} hinzu...
                </span>
              )}
            </div>
          </div>
        )}

        {/* Info-Box */}
        <Alert type="info" className="mt-6">
          <strong>Pflichtfelder</strong> sind mit * markiert. Der Kaufpreis ist besonders wichtig
          für die Amortisationsberechnung. Sie können alle Angaben später jederzeit unter
          Einstellungen → Investitionen ändern.
        </Alert>
      </div>

      {/* Footer */}
      <div className="px-6 md:px-8 py-4 bg-gray-50 dark:bg-gray-700/50 border-t border-gray-200 dark:border-gray-700 flex justify-between">
        <Button type="button" variant="ghost" onClick={onBack}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Zurück
        </Button>
        <Button type="button" variant="amber" onClick={onNext} disabled={isLoading}>
          Weiter
          <ArrowRight className="w-4 h-4 ml-2" />
        </Button>
      </div>
    </div>
  )
}
