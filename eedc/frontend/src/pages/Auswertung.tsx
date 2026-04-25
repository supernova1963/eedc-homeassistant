// Auswertung Hauptseite - Tab-Navigation
import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sun, ArrowRight, Calendar, FileText } from 'lucide-react'
import { Card, Button, LoadingSpinner, Alert } from '../components/ui'
import { useSelectedAnlage, useAggregierteDaten, useAggregierteStats, useAktuellerStrompreis, useStrompreise } from '../hooks'
import { EnergieTab, KomponentenTab, FinanzenTab, CO2Tab, InvestitionenTab, PVAnlageTab, TabelleTab, EnergieprofilTab } from './auswertung/index'

type TabType = 'energie' | 'pv' | 'komponenten' | 'finanzen' | 'co2' | 'investitionen' | 'tabelle' | 'energieprofil'

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

  const { anlagen, selectedAnlageId, setSelectedAnlageId, selectedAnlage: anlage, loading: anlagenLoading } = useSelectedAnlage()

  const anlageId = selectedAnlageId
  // Aggregierte Daten verwenden für korrekte PV-Erzeugung aus InvestitionMonatsdaten
  const { daten: aggregierteDaten, loading: mdLoading } = useAggregierteDaten(anlageId)
  const { strompreis } = useAktuellerStrompreis(anlageId ?? null)
  const { strompreise: alleTarife } = useStrompreise(anlageId)

  // Verfügbare Jahre
  const verfuegbareJahre = useMemo(() => {
    const jahre = [...new Set(aggregierteDaten.map(m => m.jahr))].sort((a, b) => b - a)
    return jahre
  }, [aggregierteDaten])

  // Gefilterte Daten nach Jahr
  const filteredData = useMemo(() => {
    if (selectedYear === 'all') return aggregierteDaten
    return aggregierteDaten.filter(m => m.jahr === selectedYear)
  }, [aggregierteDaten, selectedYear])

  // Stats für gefilterte Daten (mit korrekter PV-Erzeugung aus InvestitionMonatsdaten)
  const filteredStats = useAggregierteStats(filteredData)

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

  if (aggregierteDaten.length === 0) {
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

  const tabs: { key: TabType; label: string; beta?: boolean }[] = [
    { key: 'energie', label: 'Energie' },
    { key: 'pv', label: 'PV-Anlage' },
    { key: 'komponenten', label: 'Komponenten' },
    { key: 'finanzen', label: 'Finanzen' },
    { key: 'co2', label: 'CO2' },
    { key: 'investitionen', label: 'Investitionen' },
    { key: 'tabelle', label: 'Tabelle' },
    { key: 'energieprofil', label: 'Energieprofil', beta: true },
  ]

  // Zeitraum-Label berechnen
  const zeitraumLabel = getZeitraumLabel(selectedYear, verfuegbareJahre)

  return (
    <div className="space-y-6">
      {/* Sticky Header mit Filter */}
      <div className="sticky -top-3 sm:-top-6 z-30 bg-gray-50 dark:bg-gray-900 pb-4 -mx-3 sm:-mx-6 px-3 sm:px-6 pt-3 sm:pt-6">
        <div className="flex items-center justify-between gap-2 mb-4 flex-wrap">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Auswertung</h1>
            <Button variant="secondary" size="sm" onClick={() => navigate('/cockpit/monatsberichte')}>
              <FileText className="h-4 w-4 mr-1.5" />
              Monatsberichte
            </Button>
          </div>
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
          <nav className="flex gap-4 overflow-x-auto">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`py-3 px-1 border-b-2 text-sm font-medium whitespace-nowrap transition-colors ${
                  activeTab === tab.key
                    ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
                }`}
              >
                <span className="flex items-center gap-1.5">
                  {tab.label}
                  {tab.beta && (
                    <span className="text-[10px] font-semibold px-1 py-0.5 rounded bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400 leading-none">
                      Beta
                    </span>
                  )}
                </span>
              </button>
            ))}
          </nav>
        </div>
      </div>

      {/* Tab Content */}
      <div>
        {activeTab === 'energie' && (
          <EnergieTab data={filteredData} stats={filteredStats} anlage={anlage} strompreis={strompreis} alleTarife={alleTarife} zeitraumLabel={zeitraumLabel} />
        )}
        {activeTab === 'pv' && anlageId && (
          <PVAnlageTab anlageId={anlageId} selectedYear={selectedYear} verfuegbareJahre={verfuegbareJahre} zeitraumLabel={zeitraumLabel} />
        )}
        {activeTab === 'komponenten' && (
          <KomponentenTab anlage={anlage} strompreis={strompreis} selectedYear={selectedYear} zeitraumLabel={zeitraumLabel} />
        )}
        {activeTab === 'finanzen' && (
          <FinanzenTab data={filteredData} stats={filteredStats} strompreis={strompreis} alleTarife={alleTarife} anlageId={anlageId} zeitraumLabel={zeitraumLabel} />
        )}
        {activeTab === 'co2' && (
          <CO2Tab data={filteredData} stats={filteredStats} zeitraumLabel={zeitraumLabel} />
        )}
        {activeTab === 'investitionen' && anlageId && (
          <InvestitionenTab anlageId={anlageId} strompreis={strompreis} selectedYear={selectedYear} zeitraumLabel={zeitraumLabel} />
        )}
        {activeTab === 'tabelle' && (
          <TabelleTab data={filteredData} stats={filteredStats} anlage={anlage} strompreis={strompreis} alleTarife={alleTarife} zeitraumLabel={zeitraumLabel} alleDaten={aggregierteDaten} selectedYear={selectedYear} />
        )}
        {activeTab === 'energieprofil' && anlageId && (
          <EnergieprofilTab key={anlageId} anlageId={anlageId} />
        )}
      </div>
    </div>
  )
}
