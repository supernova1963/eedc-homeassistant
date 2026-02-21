/**
 * Community Hauptseite - Tab-Navigation für Community-Vergleiche
 *
 * Eigenständiger Hauptmenüpunkt mit 6 Tabs:
 * - Übersicht: Ranking, Quick-Stats, Badges
 * - PV-Ertrag: Detaillierter Ertragsvergleich
 * - Komponenten: Deep-Dives für Speicher, WP, E-Auto, etc.
 * - Regional: Bundesland-Vergleiche
 * - Trends: Zeitliche Entwicklungen
 * - Statistiken: Community-weite Insights
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Users,
  Trophy,
  Sun,
  Battery,
  MapPin,
  TrendingUp,
  BarChart3,
  ExternalLink,
  AlertCircle,
  HelpCircle,
} from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../components/ui'
import { SimpleTooltip } from '../components/ui/FormelTooltip'
import { useAnlagen } from '../hooks'
import { anlagenApi } from '../api'
import type { ZeitraumTyp } from '../api/community'
import {
  UebersichtTab,
  PVErtragTab,
  KomponentenTab,
  RegionalTab,
  TrendsTab,
  StatistikenTab,
} from './community'

type TabType = 'uebersicht' | 'pv-ertrag' | 'komponenten' | 'regional' | 'trends' | 'statistiken'

// Zeitraum-Optionen mit Erklärungen
const ZEITRAUM_OPTIONS: { value: ZeitraumTyp; label: string; tooltip: string }[] = [
  { value: 'letzter_monat', label: 'Letzter Monat', tooltip: 'Daten des letzten vollständigen Monats' },
  { value: 'letzte_12_monate', label: 'Letzte 12 Monate', tooltip: 'Rollierender 12-Monats-Zeitraum bis heute' },
  { value: 'letztes_vollstaendiges_jahr', label: 'Letztes Jahr', tooltip: 'Das letzte vollständige Kalenderjahr' },
  { value: 'seit_installation', label: 'Seit Installation', tooltip: 'Alle Daten seit Inbetriebnahme der Anlage' },
]

export default function Community() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<TabType>('uebersicht')
  const [zeitraum, setZeitraum] = useState<ZeitraumTyp>('letzte_12_monate')

  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)
  const [communityHash, setCommunityHash] = useState<string | null>(null)
  const [checkingAccess, setCheckingAccess] = useState(true)

  const anlageId = selectedAnlageId ?? anlagen[0]?.id

  // Community-Hash prüfen
  useEffect(() => {
    if (!anlageId) {
      setCheckingAccess(false)
      return
    }

    const checkCommunityStatus = async () => {
      setCheckingAccess(true)
      try {
        const anlage = await anlagenApi.get(anlageId)
        setCommunityHash(anlage.community_hash || null)
      } catch {
        setCommunityHash(null)
      } finally {
        setCheckingAccess(false)
      }
    }
    checkCommunityStatus()
  }, [anlageId])

  if (anlagenLoading || checkingAccess) {
    return <LoadingSpinner text="Lade Community..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Community</h1>
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an.
        </Alert>
      </div>
    )
  }

  // Nicht geteilt - Hinweis anzeigen
  if (!communityHash) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Users className="h-8 w-8 text-primary-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Community</h1>
        </div>

        <Card>
          <div className="text-center py-12">
            <AlertCircle className="h-16 w-16 text-primary-500 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-3">
              Teile erst deine Daten
            </h2>
            <p className="text-gray-600 dark:text-gray-400 max-w-md mx-auto mb-6">
              Um den Community-Vergleich nutzen zu können, musst du zuerst deine anonymisierten
              Anlagendaten mit der Community teilen. So können wir dir zeigen, wie deine Anlage
              im Vergleich zu anderen abschneidet.
            </p>
            <button
              onClick={() => navigate('/einstellungen/community')}
              className="inline-flex items-center gap-2 px-6 py-3 bg-primary-500 text-white rounded-lg hover:bg-primary-600 font-medium"
            >
              <ExternalLink className="h-5 w-5" />
              Jetzt teilen
            </button>
          </div>
        </Card>
      </div>
    )
  }

  const tabs: { key: TabType; label: string; icon: typeof Trophy; hatZeitraum: boolean }[] = [
    { key: 'uebersicht', label: 'Übersicht', icon: Trophy, hatZeitraum: true },
    { key: 'pv-ertrag', label: 'PV-Ertrag', icon: Sun, hatZeitraum: true },
    { key: 'komponenten', label: 'Komponenten', icon: Battery, hatZeitraum: true },
    { key: 'regional', label: 'Regional', icon: MapPin, hatZeitraum: true },
    { key: 'trends', label: 'Trends', icon: TrendingUp, hatZeitraum: false },
    { key: 'statistiken', label: 'Statistiken', icon: BarChart3, hatZeitraum: false },
  ]

  // Prüfen ob aktueller Tab Zeitraum-Filter unterstützt
  const zeigeZeitraumFilter = tabs.find(t => t.key === activeTab)?.hatZeitraum ?? false

  return (
    <div className="space-y-6">
      {/* Sticky Header mit Filter */}
      <div className="sticky -top-6 z-10 bg-gray-50 dark:bg-gray-900 pb-4 -mx-6 px-6 pt-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Users className="h-8 w-8 text-primary-500" />
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Community</h1>
          </div>
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
            {/* Zeitraum-Filter - nur bei relevanten Tabs */}
            {zeigeZeitraumFilter && (
              <div className="flex items-center gap-1">
                <select
                  value={zeitraum}
                  onChange={(e) => setZeitraum(e.target.value as ZeitraumTyp)}
                  className="input w-auto"
                >
                  {ZEITRAUM_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
                <SimpleTooltip text={ZEITRAUM_OPTIONS.find(o => o.value === zeitraum)?.tooltip || 'Betrachtungszeitraum wählen'}>
                  <HelpCircle className="h-4 w-4 text-gray-400 cursor-help" />
                </SimpleTooltip>
              </div>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200 dark:border-gray-700">
          <nav className="flex gap-4 overflow-x-auto">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`py-3 px-1 border-b-2 text-sm font-medium transition-colors flex items-center gap-2 whitespace-nowrap ${
                    activeTab === tab.key
                      ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                      : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {tab.label}
                </button>
              )
            })}
          </nav>
        </div>
      </div>

      {/* Tab-Inhalte */}
      {anlageId && (
        <>
          {activeTab === 'uebersicht' && (
            <UebersichtTab anlageId={anlageId} zeitraum={zeitraum} />
          )}
          {activeTab === 'pv-ertrag' && (
            <PVErtragTab anlageId={anlageId} zeitraum={zeitraum} />
          )}
          {activeTab === 'komponenten' && (
            <KomponentenTab anlageId={anlageId} zeitraum={zeitraum} />
          )}
          {activeTab === 'regional' && (
            <RegionalTab anlageId={anlageId} zeitraum={zeitraum} />
          )}
          {activeTab === 'trends' && (
            <TrendsTab anlageId={anlageId} zeitraum={zeitraum} />
          )}
          {activeTab === 'statistiken' && (
            <StatistikenTab anlageId={anlageId} zeitraum={zeitraum} />
          )}
        </>
      )}
    </div>
  )
}
