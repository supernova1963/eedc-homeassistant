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
import { useNavigate, useParams } from 'react-router-dom'
import {
  Users,
  ExternalLink,
  AlertCircle,
  HelpCircle,
} from 'lucide-react'
import { Card, Alert } from '../components/ui'
import { communityApi, type CommunityBenchmarkResponse } from '../api/community'
import { SimpleTooltip } from '../components/ui/FormelTooltip'
import { DataLoadingState } from '../components/common'
import { useSelectedAnlage } from '../hooks'
import { anlagenApi } from '../api'
import type { ZeitraumTyp } from '../api/community'
import {
  UebersichtTab,
  PVErtragTab,
  KomponentenTab,
  RegionalTab,
  TrendsTab,
  StatistikenTab,
} from './community/index'

type TabType = 'uebersicht' | 'pv-ertrag' | 'komponenten' | 'regional' | 'trends' | 'statistiken'

const COMMUNITY_TABS = ['uebersicht', 'pv-ertrag', 'komponenten', 'regional', 'trends', 'statistiken'] as const
// Tabs mit Zeitraum-Filter (Trends/Statistiken zeigen community-weite Zeitreihen ohne Selektor).
const ZEITRAUM_TABS = new Set<TabType>(['uebersicht', 'pv-ertrag', 'komponenten', 'regional'])

// Zeitraum-Optionen mit Erklärungen
const ZEITRAUM_OPTIONS: { value: ZeitraumTyp; label: string; tooltip: string }[] = [
  { value: 'letzter_monat', label: 'Letzter Monat', tooltip: 'Daten des letzten vollständigen Monats' },
  { value: 'letzte_12_monate', label: 'Letzte 12 Monate', tooltip: 'Rollierender 12-Monats-Zeitraum bis heute' },
  { value: 'letztes_vollstaendiges_jahr', label: 'Letztes Jahr', tooltip: 'Das letzte vollständige Kalenderjahr' },
  { value: 'seit_installation', label: 'Seit Installation', tooltip: 'Alle Daten seit Inbetriebnahme der Anlage' },
]

export default function Community() {
  const navigate = useNavigate()
  // Aktiver Tab aus der URL (`/community/<tab>`); Default = uebersicht.
  const { tab } = useParams()
  const activeTab: TabType = (COMMUNITY_TABS as readonly string[]).includes(tab ?? '')
    ? (tab as TabType)
    : 'uebersicht'
  const [zeitraum, setZeitraum] = useState<ZeitraumTyp>('letzte_12_monate')

  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const [communityHash, setCommunityHash] = useState<string | null>(null)
  const [checkingAccess, setCheckingAccess] = useState(true)

  // Benchmark zentral laden — wird an alle Tabs weitergereicht
  const [benchmark, setBenchmark] = useState<CommunityBenchmarkResponse | null>(null)
  const [benchmarkLoading, setBenchmarkLoading] = useState(false)
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null)

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

  // Benchmark einmal laden, Ergebnis an alle Tabs weitergeben
  useEffect(() => {
    if (!anlageId || !communityHash) return

    const loadBenchmark = async () => {
      setBenchmarkLoading(true)
      setBenchmarkError(null)
      try {
        const data = await communityApi.getBenchmark(anlageId, zeitraum)
        setBenchmark(data)
      } catch (e) {
        setBenchmarkError(e instanceof Error ? e.message : 'Fehler beim Laden')
      } finally {
        setBenchmarkLoading(false)
      }
    }
    loadBenchmark()
  }, [anlageId, zeitraum, communityHash])


  if (anlagenLoading || checkingAccess) {
    return <DataLoadingState loading={true} error={null}><div /></DataLoadingState>
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

  // Prüfen ob aktueller Tab Zeitraum-Filter unterstützt
  const zeigeZeitraumFilter = ZEITRAUM_TABS.has(activeTab)

  return (
    <div className="space-y-6">
      {/* Sticky Header mit Filter */}
      <div className="sticky -top-3 sm:-top-6 z-30 bg-gray-50 dark:bg-gray-900 pb-4 -mx-3 sm:-mx-6 px-3 sm:px-6 pt-3 sm:pt-6">
        <div className="flex items-center justify-end gap-3 mb-4 flex-wrap">
          {/* Link zum Community-Server */}
          <a
            href="https://energy.raunet.eu"
            target="_blank"
            rel="noopener noreferrer"
            title="Community-Server im Browser öffnen"
            className="p-2 rounded-lg text-gray-400 dark:text-gray-500 hover:text-primary-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <ExternalLink className="h-5 w-5" />
          </a>
          {/* Anlagen-Filter */}
          {anlagen.length > 1 && (
            <select
              value={anlageId ?? ''}
              onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
              aria-label="Anlage wählen"
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
                aria-label="Zeitraum wählen"
                className="input w-auto"
              >
                {ZEITRAUM_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <SimpleTooltip text={ZEITRAUM_OPTIONS.find(o => o.value === zeitraum)?.tooltip || 'Betrachtungszeitraum wählen'}>
                <HelpCircle className="h-4 w-4 text-gray-400 dark:text-gray-500 cursor-help" />
              </SimpleTooltip>
            </div>
          )}
        </div>
      </div>

      {/* Tab-Inhalte (Sub-Tab-Leiste lebt in der Layout-SubTabs) */}
      {anlageId && (
        <>
          {activeTab === 'uebersicht' && (
            <UebersichtTab anlageId={anlageId} zeitraum={zeitraum} benchmark={benchmark} benchmarkLoading={benchmarkLoading} benchmarkError={benchmarkError} />
          )}
          {activeTab === 'pv-ertrag' && (
            <PVErtragTab anlageId={anlageId} zeitraum={zeitraum} benchmark={benchmark} benchmarkLoading={benchmarkLoading} benchmarkError={benchmarkError} />
          )}
          {activeTab === 'komponenten' && (
            <KomponentenTab anlageId={anlageId} zeitraum={zeitraum} benchmark={benchmark} benchmarkLoading={benchmarkLoading} benchmarkError={benchmarkError} />
          )}
          {activeTab === 'regional' && (
            <RegionalTab anlageId={anlageId} zeitraum={zeitraum} benchmark={benchmark} benchmarkLoading={benchmarkLoading} benchmarkError={benchmarkError} />
          )}
          {activeTab === 'trends' && (
            <TrendsTab anlageId={anlageId} zeitraum={zeitraum} benchmark={benchmark} benchmarkLoading={benchmarkLoading} benchmarkError={benchmarkError} />
          )}
          {activeTab === 'statistiken' && (
            <StatistikenTab anlageId={anlageId} zeitraum={zeitraum} benchmark={benchmark} benchmarkLoading={benchmarkLoading} benchmarkError={benchmarkError} />
          )}
        </>
      )}
    </div>
  )
}
