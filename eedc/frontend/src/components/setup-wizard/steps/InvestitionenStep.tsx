/**
 * InvestitionenStep - Investitionen vervollständigen im Setup-Wizard
 */

import { Car, Battery, Plug, Cpu, ArrowLeft, ArrowRight, SkipForward, Info } from 'lucide-react'
import type { DiscoveredDevice } from '../../../api/ha'
import type { InvestitionFormData } from '../../../hooks/useSetupWizard'

interface InvestitionenStepProps {
  devices: DiscoveredDevice[]
  formData: Record<string, InvestitionFormData>
  isLoading: boolean
  error: string | null
  onUpdateFormData: (deviceId: string, data: Partial<InvestitionFormData>) => void
  onSubmit: () => Promise<void>
  onSkip: () => void
  onBack: () => void
}

// Icon basierend auf Gerätetyp
function getDeviceIcon(typ: string | null) {
  switch (typ) {
    case 'e-auto':
      return <Car className="w-5 h-5" />
    case 'speicher':
      return <Battery className="w-5 h-5" />
    case 'wallbox':
      return <Plug className="w-5 h-5" />
    case 'wechselrichter':
      return <Cpu className="w-5 h-5" />
    default:
      return <Cpu className="w-5 h-5" />
  }
}

// Typ-Label
function getTypeLabel(typ: string | null): string {
  switch (typ) {
    case 'e-auto': return 'E-Auto'
    case 'speicher': return 'Speicher'
    case 'wallbox': return 'Wallbox'
    case 'wechselrichter': return 'Wechselrichter'
    default: return 'Investition'
  }
}

export default function InvestitionenStep({
  devices,
  formData,
  isLoading,
  error,
  onUpdateFormData,
  onSubmit,
  onSkip,
  onBack,
}: InvestitionenStepProps) {
  // Keine Geräte ausgewählt
  if (devices.length === 0) {
    return (
      <div>
        <div className="p-6 md:p-8">
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-gray-100 dark:bg-gray-700 rounded-full mb-4">
              <Info className="w-8 h-8 text-gray-400" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
              Keine Geräte ausgewählt
            </h2>
            <p className="text-gray-500 dark:text-gray-400 max-w-md mx-auto">
              Sie haben keine Geräte zur Erstellung ausgewählt.
              Investitionen können jederzeit später unter Einstellungen → Investitionen angelegt werden.
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
            onClick={onSkip}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-amber-500 text-white font-medium rounded-lg hover:bg-amber-600 transition-colors"
          >
            Weiter
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
        <div className="mb-6">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
            Investitionen vervollständigen
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Ergänzen Sie die Details für die erkannten Geräte.
            Diese Informationen werden für die ROI-Berechnung benötigt.
          </p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        {/* Geräte-Formulare */}
        <div className="space-y-6">
          {devices.map((device) => {
            const data = formData[device.id] || {
              bezeichnung: device.name,
              kaufdatum: new Date().toISOString().split('T')[0],
              kaufpreis: 0,
            }

            return (
              <div
                key={device.id}
                className="p-5 bg-gray-50 dark:bg-gray-700/50 rounded-xl border border-gray-200 dark:border-gray-700"
              >
                {/* Device Header */}
                <div className="flex items-center gap-3 mb-4 pb-4 border-b border-gray-200 dark:border-gray-600">
                  <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/30 rounded-lg flex items-center justify-center text-amber-600 dark:text-amber-400">
                    {getDeviceIcon(device.suggested_investition_typ)}
                  </div>
                  <div>
                    <div className="font-medium text-gray-900 dark:text-white">
                      {getTypeLabel(device.suggested_investition_typ)}
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">
                      {device.manufacturer && `${device.manufacturer} • `}
                      {device.integration}
                    </div>
                  </div>
                </div>

                {/* Formular */}
                <div className="grid md:grid-cols-2 gap-4">
                  <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Bezeichnung
                    </label>
                    <input
                      type="text"
                      value={data.bezeichnung}
                      onChange={(e) => onUpdateFormData(device.id, { bezeichnung: e.target.value })}
                      className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Kaufdatum
                    </label>
                    <input
                      type="date"
                      value={data.kaufdatum}
                      onChange={(e) => onUpdateFormData(device.id, { kaufdatum: e.target.value })}
                      className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Kaufpreis (€)
                    </label>
                    <input
                      type="number"
                      value={data.kaufpreis || ''}
                      onChange={(e) => onUpdateFormData(device.id, { kaufpreis: parseFloat(e.target.value) || 0 })}
                      placeholder="z.B. 5000"
                      min="0"
                      step="100"
                      className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                    />
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      Für ROI-Berechnung
                    </p>
                  </div>

                  {/* Typ-spezifische Felder - E-Auto */}
                  {device.suggested_investition_typ === 'e-auto' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Batteriekapazität (kWh)
                      </label>
                      <input
                        type="number"
                        value={data.batteriekapazitaet_kwh ?? (device.suggested_parameters.batterie_kwh as number | undefined) ?? ''}
                        onChange={(e) => onUpdateFormData(device.id, { batteriekapazitaet_kwh: parseFloat(e.target.value) || undefined })}
                        placeholder="z.B. 66"
                        min="0"
                        step="0.1"
                        className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                      />
                    </div>
                  )}

                  {/* Typ-spezifische Felder - Speicher */}
                  {device.suggested_investition_typ === 'speicher' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Kapazität (kWh)
                      </label>
                      <input
                        type="number"
                        value={data.kapazitaet_kwh ?? (device.suggested_parameters.kapazitaet_kwh as number | undefined) ?? ''}
                        onChange={(e) => onUpdateFormData(device.id, { kapazitaet_kwh: parseFloat(e.target.value) || undefined })}
                        placeholder="z.B. 10"
                        min="0"
                        step="0.1"
                        className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                      />
                    </div>
                  )}

                  {/* Typ-spezifische Felder - Wallbox */}
                  {device.suggested_investition_typ === 'wallbox' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Max. Ladeleistung (kW)
                      </label>
                      <input
                        type="number"
                        value={data.leistung_kw ?? (device.suggested_parameters.leistung_kw as number | undefined) ?? ''}
                        onChange={(e) => onUpdateFormData(device.id, { leistung_kw: parseFloat(e.target.value) || undefined })}
                        placeholder="z.B. 11"
                        min="0"
                        step="0.1"
                        className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                      />
                    </div>
                  )}

                  {/* Typ-spezifische Felder - Wechselrichter */}
                  {device.suggested_investition_typ === 'wechselrichter' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Max. Leistung (kW)
                      </label>
                      <input
                        type="number"
                        value={data.leistung_kw ?? (device.suggested_parameters.leistung_kw as number | undefined) ?? ''}
                        onChange={(e) => onUpdateFormData(device.id, { leistung_kw: parseFloat(e.target.value) || undefined })}
                        placeholder="z.B. 10"
                        min="0"
                        step="0.1"
                        className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                      />
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Info-Box */}
        <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
          <p className="text-sm text-blue-700 dark:text-blue-300 flex items-start gap-2">
            <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>
              Sie können diese Angaben später jederzeit unter Einstellungen → Investitionen
              ergänzen oder ändern. Der Kaufpreis ist besonders wichtig für die
              Amortisationsberechnung.
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
          <button
            type="button"
            onClick={onSkip}
            className="inline-flex items-center gap-2 px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
          >
            <SkipForward className="w-4 h-4" />
            Später ergänzen
          </button>

          <button
            type="button"
            onClick={onSubmit}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-amber-500 text-white font-medium rounded-lg hover:bg-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Erstellen...
              </>
            ) : (
              <>
                {devices.length} Investition{devices.length !== 1 ? 'en' : ''} erstellen
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
