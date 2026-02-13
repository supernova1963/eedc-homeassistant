// Auswertung Hauptseite - Tab-Navigation
import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sun, ArrowRight, Calendar } from 'lucide-react'
import { Card, Button, LoadingSpinner, Alert } from '../components/ui'
import { useAnlagen, useMonatsdaten, useMonatsdatenStats, useAktuellerStrompreis } from '../hooks'
import { EnergieTab, KomponentenTab, FinanzenTab, CO2Tab, InvestitionenTab, PVAnlageTab } from './auswertung'

type TabType = 'energie' | 'pv' | 'komponenten' | 'finanzen' | 'co2' | 'investitionen'

// Zeitraum-Label für Anzeige erstellen
function getZeitraumLabel(selectedYear: number | 'all', verfuegbareJahre: number[]): string {
  if (selectedYear === 'all') {
    if (verfuegbareJahre.length === 0) return 'Alle Jahre'
    if (verfuegbareJahre.length === 1) return `${verfuegbareJahre[0]}`
    const minJahr = Math.min(...verfuegbareJahre)
    const maxJahr = Math.max(...verfuegbareJahre)
    return `${minJahr}–${maxJahr}`
  }
  return `${selectedYear}`
}

export default function Auswertung() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<TabType>('energie')
  const [selectedYear, setSelectedYear] = useState<number | 'all'>('all')

  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)

  const anlageId = selectedAnlageId ?? anlagen[0]?.id
  const anlage = anlagen.find(a => a.id === anlageId)
  const { monatsdaten, loading: mdLoading } = useMonatsdaten(anlageId)
  const { strompreis } = useAktuellerStrompreis(anlageId ?? null)

  // Verfügbare Jahre
  const verfuegbareJahre = useMemo(() => {
    const jahre = [...new Set(monatsdaten.map(m => m.jahr))].sort((a, b) => b - a)
    return jahre
  }, [monatsdaten])

  // Gefilterte Daten nach Jahr
  const filteredData = useMemo(() => {
    if (selectedYear === 'all') return monatsdaten
    return monatsdaten.filter(m => m.jahr === selectedYear)
  }, [monatsdaten, selectedYear])

  // Stats für gefilterte Daten
  const filteredStats = useMonatsdatenStats(filteredData)

  const loading = anlagenLoading || mdLoading

  if (loading) {
    return <LoadingSpinner text="Lade Auswertungen..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Auswertung</h1>
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an.
        </Alert>
      </div>
    )
  }

  if (monatsdaten.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Auswertung</h1>
        <Card className="text-center py-12">
          <Sun className="h-12 w-12 mx-auto text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            Noch keine Daten vorhanden
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Erfasse Monatsdaten, um Auswertungen zu sehen.
          </p>
          <Button onClick={() => navigate('/monatsdaten')}>
            Monatsdaten erfassen
            <ArrowRight className="h-4 w-4 ml-2" />
          </Button>
        </Card>
      </div>
    )
  }

  const tabs: { key: TabType; label: string }[] = [
    { key: 'energie', label: 'Energie' },
    { key: 'pv', label: 'PV-Anlage' },
    { key: 'komponenten', label: 'Komponenten' },
    { key: 'finanzen', label: 'Finanzen' },
    { key: 'co2', label: 'CO2' },
    { key: 'investitionen', label: 'Investitionen' },
  ]

  // Zeitraum-Label berechnen
  const zeitraumLabel = getZeitraumLabel(selectedYear, verfuegbareJahre)

  return (
    <div className="space-y-6">
      {/* Sticky Header mit Filter */}
      <div className="sticky -top-6 z-10 bg-gray-50 dark:bg-gray-900 pb-4 -mx-6 px-6 pt-6">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Auswertung</h1>
          <div className="flex items-center gap-3">
            {/* Jahr-Filter - für alle Tabs */}
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-gray-400" />
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(e.target.value === 'all' ? 'all' : Number(e.target.value))}
                className="input w-auto"
              >
                <option value="all">Alle Jahre</option>
                {verfuegbareJahre.map(j => (
                  <option key={j} value={j}>{j}</option>
                ))}
              </select>
            </div>

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
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                  activeTab === tab.key
                    ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </div>

      {/* Tab Content */}
      <div>
        {activeTab === 'energie' && (
          <EnergieTab data={filteredData} stats={filteredStats} anlage={anlage} strompreis={strompreis} zeitraumLabel={zeitraumLabel} />
        )}
        {activeTab === 'pv' && anlageId && (
          <PVAnlageTab anlageId={anlageId} selectedYear={selectedYear} verfuegbareJahre={verfuegbareJahre} zeitraumLabel={zeitraumLabel} />
        )}
        {activeTab === 'komponenten' && (
          <KomponentenTab anlage={anlage} strompreis={strompreis} selectedYear={selectedYear} zeitraumLabel={zeitraumLabel} />
        )}
        {activeTab === 'finanzen' && (
          <FinanzenTab data={filteredData} stats={filteredStats} strompreis={strompreis} anlageId={anlageId} zeitraumLabel={zeitraumLabel} />
        )}
        {activeTab === 'co2' && (
          <CO2Tab data={filteredData} stats={filteredStats} zeitraumLabel={zeitraumLabel} />
        )}
        {activeTab === 'investitionen' && anlageId && (
          <InvestitionenTab anlageId={anlageId} strompreis={strompreis} selectedYear={selectedYear} zeitraumLabel={zeitraumLabel} />
        )}
      </div>
    </div>
  )
}
