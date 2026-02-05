/**
 * SummaryStep - Zusammenfassung vor Abschluss des Setup-Wizards
 *
 * v0.8.0 - Angepasst für neuen Wizard-Flow mit Investitionen und SensorConfig
 */

import {
  Sun,
  Zap,
  Car,
  Battery,
  Plug,
  Cpu,
  Flame,
  Package,
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react'
import type { Anlage, Strompreis, Investition, SensorConfig, InvestitionTyp } from '../../../types'

interface SummaryStepProps {
  anlage: Anlage | null
  strompreis: Strompreis | null
  investitionen: Investition[]
  sensorConfig: SensorConfig
  onComplete: () => void
  onBack: () => void
}

// Icon basierend auf Investitionstyp
function getInvestitionIcon(typ: InvestitionTyp) {
  switch (typ) {
    case 'e-auto':
      return <Car className="w-4 h-4" />
    case 'speicher':
      return <Battery className="w-4 h-4" />
    case 'wallbox':
      return <Plug className="w-4 h-4" />
    case 'wechselrichter':
      return <Cpu className="w-4 h-4" />
    case 'waermepumpe':
      return <Flame className="w-4 h-4" />
    case 'pv-module':
    case 'balkonkraftwerk':
      return <Sun className="w-4 h-4" />
    default:
      return <Package className="w-4 h-4" />
  }
}

export default function SummaryStep({
  anlage,
  strompreis,
  investitionen,
  sensorConfig,
  onComplete,
  onBack,
}: SummaryStepProps) {
  // Prüfen was konfiguriert wurde
  const hasAnlage = !!anlage
  const hasStrompreis = !!strompreis
  const hasInvestitionen = investitionen.length > 0
  const hasSensorConfig = !!(
    sensorConfig.pv_erzeugung ||
    sensorConfig.einspeisung ||
    sensorConfig.netzbezug
  )

  // Anzahl konfigurierter Sensoren
  const sensorCount = Object.values(sensorConfig).filter(v => v).length

  // Gesamtinvestition berechnen
  const totalInvestition = investitionen.reduce(
    (sum, inv) => sum + (inv.anschaffungskosten_gesamt || 0),
    0
  )

  return (
    <div>
      <div className="p-6 md:p-8">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-full mb-4">
            <CheckCircle2 className="w-8 h-8 text-green-500" />
          </div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
            Einrichtung abschließen
          </h2>
          <p className="text-gray-500 dark:text-gray-400">
            Überprüfen Sie Ihre Konfiguration
          </p>
        </div>

        {/* Zusammenfassung */}
        <div className="space-y-4">
          {/* Anlage */}
          <SummaryCard
            icon={<Sun className="w-5 h-5" />}
            title="PV-Anlage"
            status={hasAnlage ? 'success' : 'warning'}
          >
            {hasAnlage ? (
              <div className="space-y-1">
                <div className="font-medium text-gray-900 dark:text-white">
                  {anlage.anlagenname}
                </div>
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  {anlage.leistung_kwp} kWp
                  {anlage.standort_ort && ` • ${anlage.standort_ort}`}
                  {anlage.latitude && anlage.longitude && (
                    <span className="text-green-600 dark:text-green-400 ml-2">
                      (Koordinaten gesetzt)
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-amber-600 dark:text-amber-400">
                Keine Anlage konfiguriert
              </div>
            )}
          </SummaryCard>

          {/* Strompreis */}
          <SummaryCard
            icon={<Zap className="w-5 h-5" />}
            title="Stromtarif"
            status={hasStrompreis ? 'success' : 'warning'}
          >
            {hasStrompreis ? (
              <div className="space-y-1">
                <div className="text-gray-900 dark:text-white">
                  <span className="font-medium">{strompreis.netzbezug_arbeitspreis_cent_kwh}</span>
                  <span className="text-sm text-gray-500 dark:text-gray-400"> ct/kWh Netzbezug</span>
                  <span className="mx-2 text-gray-300 dark:text-gray-600">|</span>
                  <span className="font-medium">{strompreis.einspeiseverguetung_cent_kwh}</span>
                  <span className="text-sm text-gray-500 dark:text-gray-400"> ct/kWh Einspeisung</span>
                </div>
                {strompreis.tarifname && (
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    {strompreis.tarifname}
                    {strompreis.anbieter && ` (${strompreis.anbieter})`}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-amber-600 dark:text-amber-400">
                Kein Stromtarif konfiguriert - Berechnungen sind unvollständig
              </div>
            )}
          </SummaryCard>

          {/* Investitionen */}
          <SummaryCard
            icon={<Cpu className="w-5 h-5" />}
            title="Investitionen"
            status={hasInvestitionen ? 'success' : 'neutral'}
          >
            {hasInvestitionen ? (
              <div className="space-y-2">
                {investitionen.slice(0, 5).map((inv) => (
                  <div key={inv.id} className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
                    <span className="text-gray-400 dark:text-gray-500">
                      {getInvestitionIcon(inv.typ)}
                    </span>
                    <span className="truncate">{inv.bezeichnung}</span>
                    {inv.anschaffungskosten_gesamt ? (
                      <span className="text-sm text-gray-500 dark:text-gray-400 ml-auto flex-shrink-0">
                        {inv.anschaffungskosten_gesamt.toLocaleString('de-DE')} €
                      </span>
                    ) : null}
                  </div>
                ))}
                {investitionen.length > 5 && (
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    ... und {investitionen.length - 5} weitere
                  </div>
                )}
                {totalInvestition > 0 && (
                  <div className="pt-2 border-t border-gray-200 dark:border-gray-700 mt-2">
                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                      Gesamt: {totalInvestition.toLocaleString('de-DE')} €
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-gray-500 dark:text-gray-400">
                Keine Investitionen erstellt - können später hinzugefügt werden
              </div>
            )}
          </SummaryCard>

          {/* Sensor-Konfiguration */}
          <SummaryCard
            icon={<Zap className="w-5 h-5" />}
            title="HA Sensor-Zuordnung"
            status={hasSensorConfig ? 'success' : 'neutral'}
          >
            {hasSensorConfig ? (
              <div className="space-y-1">
                <div className="text-gray-700 dark:text-gray-300">
                  {sensorCount} Sensor{sensorCount !== 1 ? 'en' : ''} zugeordnet
                </div>
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  Monatsdaten können aus Home Assistant importiert werden
                </div>
                <div className="flex flex-wrap gap-2 mt-2">
                  {sensorConfig.pv_erzeugung && (
                    <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 text-xs rounded-full">
                      PV-Erzeugung
                    </span>
                  )}
                  {sensorConfig.einspeisung && (
                    <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 text-xs rounded-full">
                      Einspeisung
                    </span>
                  )}
                  {sensorConfig.netzbezug && (
                    <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 text-xs rounded-full">
                      Netzbezug
                    </span>
                  )}
                  {sensorConfig.batterie_ladung && (
                    <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 text-xs rounded-full">
                      Batterie
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-gray-500 dark:text-gray-400">
                Keine Sensoren zugeordnet - Import manuell möglich
              </div>
            )}
          </SummaryCard>
        </div>

        {/* Hinweise */}
        <div className="mt-8 space-y-3">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
            Nächste Schritte nach der Einrichtung:
          </h3>
          <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
            <li className="flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
              <span>Monatsdaten aus Home Assistant importieren oder manuell erfassen</span>
            </li>
            <li className="flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
              <span>PVGIS-Prognose für Ihre Module abrufen (unter Auswertungen → Prognose)</span>
            </li>
            <li className="flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
              <span>Dashboard und Auswertungen erkunden</span>
            </li>
          </ul>
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
          onClick={onComplete}
          className="inline-flex items-center gap-2 px-8 py-3 bg-gradient-to-r from-green-500 to-emerald-500 text-white font-semibold rounded-xl shadow-lg hover:shadow-xl hover:from-green-600 hover:to-emerald-600 transition-all"
        >
          Einrichtung abschließen
          <CheckCircle2 className="w-5 h-5" />
        </button>
      </div>
    </div>
  )
}

// Summary Card Component
function SummaryCard({
  icon,
  title,
  status,
  children,
}: {
  icon: React.ReactNode
  title: string
  status: 'success' | 'warning' | 'neutral'
  children: React.ReactNode
}) {
  const statusColors = {
    success: 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20',
    warning: 'border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20',
    neutral: 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50',
  }

  const iconColors = {
    success: 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400',
    warning: 'bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400',
    neutral: 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400',
  }

  return (
    <div className={`p-4 rounded-xl border ${statusColors[status]}`}>
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${iconColors[status]}`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h4 className="font-medium text-gray-900 dark:text-white">
              {title}
            </h4>
            {status === 'success' && (
              <CheckCircle2 className="w-4 h-4 text-green-500" />
            )}
            {status === 'warning' && (
              <AlertCircle className="w-4 h-4 text-amber-500" />
            )}
          </div>
          {children}
        </div>
      </div>
    </div>
  )
}
