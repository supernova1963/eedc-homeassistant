/**
 * Aussichten Hauptseite - Tab-Navigation für Prognosen
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sun, TrendingUp, Calendar, ArrowRight, Euro } from 'lucide-react'
import { Card, Button, LoadingSpinner, Alert } from '../components/ui'
import { SimpleTooltip } from '../components/ui/FormelTooltip'
import { useAnlagen } from '../hooks'
import { KurzfristTab, LangfristTab, TrendTab, FinanzenTab } from './aussichten/index'

type TabType = 'kurzfristig' | 'langfristig' | 'trend' | 'finanzen'

export default function Aussichten() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<TabType>('kurzfristig')

  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)

  const anlageId = selectedAnlageId ?? anlagen[0]?.id

  if (anlagenLoading) {
    return <LoadingSpinner text="Lade Aussichten..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Aussichten</h1>
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an.
        </Alert>
      </div>
    )
  }

  // Prüfe ob Anlage Koordinaten hat
  const anlage = anlagen.find(a => a.id === anlageId)
  const hatKoordinaten = anlage?.latitude && anlage?.longitude

  if (!hatKoordinaten) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Aussichten</h1>
        <Card className="text-center py-12">
          <Sun className="h-12 w-12 mx-auto text-yellow-500 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            Standort nicht konfiguriert
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Für Prognosen werden die Koordinaten der Anlage benötigt.
            <br />
            Bitte konfiguriere den Standort in den Anlagen-Einstellungen.
          </p>
          <Button onClick={() => navigate('/einstellungen/anlage')}>
            Anlage konfigurieren
            <ArrowRight className="h-4 w-4 ml-2" />
          </Button>
        </Card>
      </div>
    )
  }

  const tabs: { key: TabType; label: string; icon: typeof Sun; tooltip: string }[] = [
    { key: 'kurzfristig', label: 'Kurzfristig', icon: Sun, tooltip: '7-14 Tage Wetterprognose mit PV-Ertragsprognose' },
    { key: 'langfristig', label: 'Langfristig', icon: Calendar, tooltip: '12-Monats-Prognose basierend auf PVGIS-Daten' },
    { key: 'trend', label: 'Trend', icon: TrendingUp, tooltip: 'Historische Trends und Degradationsanalyse' },
    { key: 'finanzen', label: 'Finanzen', icon: Euro, tooltip: 'Finanzielle Prognosen und Amortisation' },
  ]

  return (
    <div className="space-y-6">
      {/* Sticky Header mit Filter */}
      <div className="sticky -top-6 z-10 bg-gray-50 dark:bg-gray-900 pb-4 -mx-6 px-6 pt-6">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Aussichten</h1>
          <div className="flex items-center gap-3">
            {/* Anlagen-Filter */}
            {anlagen.length > 1 && (
              <select
                value={anlageId ?? ''}
                onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
                className="input w-auto"
              >
                {anlagen.map((a) => (
                  <option key={a.id} value={a.id}>{a.anlagenname}</option>
                ))}
              </select>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200 dark:border-gray-700">
          <nav className="flex gap-4">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <SimpleTooltip key={tab.key} text={tab.tooltip}>
                  <button
                    onClick={() => setActiveTab(tab.key)}
                    className={`py-3 px-1 border-b-2 text-sm font-medium transition-colors flex items-center gap-2 ${
                      activeTab === tab.key
                        ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                        : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    {tab.label}
                  </button>
                </SimpleTooltip>
              )
            })}
          </nav>
        </div>
      </div>

      {/* Tab-Inhalte */}
      {anlageId && (
        <>
          {activeTab === 'kurzfristig' && <KurzfristTab anlageId={anlageId} />}
          {activeTab === 'langfristig' && <LangfristTab anlageId={anlageId} />}
          {activeTab === 'trend' && <TrendTab anlageId={anlageId} />}
          {activeTab === 'finanzen' && <FinanzenTab anlageId={anlageId} />}
        </>
      )}
    </div>
  )
}
