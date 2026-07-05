/**
 * CommunityV4 — Community-Sicht der IA-V4 (Dispatcher mit 6 Sub-Tabs).
 *
 * Struktur 1:1 aus der IST-Seite (`pages/Community.tsx`): Übersicht · PV-Ertrag ·
 * Komponenten · Regional · Trends · Statistiken. Shell = geteilte `ViewShell` +
 * `IASubTabBar` (SoT); Steuerleiste (Anlage · Zeitraum · Community-Server) läuft
 * darunter mit. Benchmark wird EINMAL geladen und an die Sub-Sichten gereicht.
 *
 * Inhalt je Sub-Tab = Blockbildung (BlockShell) aus den geteilten Community-Teilen.
 * Übersicht ist gebaut; die übrigen Tabs folgen nach gleichem Schema (Platzhalter).
 */
import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { Users, ExternalLink, HelpCircle } from 'lucide-react'
import { IASubTabBar } from '../components/layout/IASubTabBar'
import { ViewShell } from './ViewShell'
import { Card, Alert, EmptyState, Button } from '../components/ui'
import { BlockStackSkeleton } from '../components/blocks'
import { SimpleTooltip } from '../components/ui/FormelTooltip'
import { useSelectedAnlage } from '../hooks'
import { anlagenApi } from '../api'
import { DEMO_DEFAULT } from '../lib/flags'
import { communityApi, type CommunityBenchmarkResponse, type ZeitraumTyp } from '../api/community'
import CommunityUebersichtV4 from './CommunityUebersichtV4'
import CommunityPVErtragV4 from './CommunityPVErtragV4'
import CommunityKomponentenV4 from './CommunityKomponentenV4'
import CommunityRegionalV4 from './CommunityRegionalV4'
import CommunityTrendsV4 from './CommunityTrendsV4'
import CommunityStatistikenV4 from './CommunityStatistikenV4'

const SUBS: { key: string; label: string }[] = [
  { key: 'uebersicht', label: 'Übersicht' },
  { key: 'pv-ertrag', label: 'PV-Ertrag' },
  { key: 'komponenten', label: 'Komponenten' },
  { key: 'regional', label: 'Regional' },
  { key: 'trends', label: 'Trends' },
  { key: 'statistiken', label: 'Statistiken' },
]
// Sub-Tabs mit Zeitraum-Filter (Trends/Statistiken = community-weite Zeitreihen).
const ZEITRAUM_SUBS = new Set(['uebersicht', 'pv-ertrag', 'komponenten', 'regional'])

const ZEITRAUM_OPTIONS: { value: ZeitraumTyp; label: string; tooltip: string }[] = [
  { value: 'letzter_monat', label: 'Letzter Monat', tooltip: 'Daten des letzten vollständigen Monats' },
  { value: 'letzte_12_monate', label: 'Letzte 12 Monate', tooltip: 'Rollierender 12-Monats-Zeitraum bis heute' },
  { value: 'letztes_vollstaendiges_jahr', label: 'Letztes Jahr', tooltip: 'Das letzte vollständige Kalenderjahr' },
  { value: 'seit_installation', label: 'Seit Installation', tooltip: 'Alle Daten seit Inbetriebnahme der Anlage' },
]

export default function CommunityV4() {
  const navigate = useNavigate()
  const { sub = 'uebersicht' } = useParams<{ sub: string }>()
  const [zeitraum, setZeitraum] = useState<ZeitraumTyp>('letzte_12_monate')

  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const [communityHash, setCommunityHash] = useState<string | null>(null)
  const [checkingAccess, setCheckingAccess] = useState(true)
  const [benchmark, setBenchmark] = useState<CommunityBenchmarkResponse | null>(null)
  const [benchmarkLoading, setBenchmarkLoading] = useState(false)
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null)

  const anlageId = selectedAnlageId ?? anlagen[0]?.id

  useEffect(() => {
    // Demo-Build: Community-Server kennt die Demo-Anlage nicht → Gate überbrücken,
    // `communityApi` liefert die Demo-Fixtures (DEMO_DEFAULT).
    if (DEMO_DEFAULT) { setCommunityHash('demo'); setCheckingAccess(false); return }
    if (!anlageId) { setCheckingAccess(false); return }
    let ab = false
    setCheckingAccess(true)
    anlagenApi.get(anlageId)
      .then((a) => { if (!ab) setCommunityHash(a.community_hash || null) })
      .catch(() => { if (!ab) setCommunityHash(null) })
      .finally(() => { if (!ab) setCheckingAccess(false) })
    return () => { ab = true }
  }, [anlageId])

  useEffect(() => {
    if (!anlageId || !communityHash) return
    let ab = false
    setBenchmarkLoading(true)
    setBenchmarkError(null)
    communityApi.getBenchmark(anlageId, zeitraum)
      .then((data) => { if (!ab) setBenchmark(data) })
      .catch((e) => { if (!ab) setBenchmarkError(e instanceof Error ? e.message : 'Fehler beim Laden') })
      .finally(() => { if (!ab) setBenchmarkLoading(false) })
    return () => { ab = true }
  }, [anlageId, zeitraum, communityHash])

  // Index / unbekannter Sub → Default (Übersicht).
  if (!SUBS.some((s) => s.key === sub)) return <Navigate to="/v4/community/uebersicht" replace />

  const nav = <IASubTabBar items={SUBS.map((s) => ({ key: s.key, label: s.label, to: `/v4/community/${s.key}` }))} />

  // Steuerleiste (Anlage · Zeitraum · Community-Server) unter den Sub-Tabs.
  const steuerleiste = (
    <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-3 sm:px-6">
      <div className="max-w-[1920px] mx-auto flex items-center justify-end gap-3 py-2 flex-wrap">
        <a
          href="https://energy.raunet.eu" target="_blank" rel="noopener noreferrer"
          title="Community-Server im Browser öffnen"
          className="p-2 rounded-lg text-gray-400 dark:text-gray-500 hover:text-primary-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          <ExternalLink className="h-5 w-5" />
        </a>
        {anlagen.length > 1 && (
          <select value={anlageId ?? ''} onChange={(e) => setSelectedAnlageId(Number(e.target.value))} aria-label="Anlage wählen" className="input w-auto">
            {anlagen.map((a) => <option key={a.id} value={a.id}>{a.anlagenname}</option>)}
          </select>
        )}
        {ZEITRAUM_SUBS.has(sub) && (
          <div className="flex items-center gap-1">
            <select value={zeitraum} onChange={(e) => setZeitraum(e.target.value as ZeitraumTyp)} aria-label="Zeitraum wählen" className="input w-auto">
              {ZEITRAUM_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
            </select>
            <SimpleTooltip text={ZEITRAUM_OPTIONS.find((o) => o.value === zeitraum)?.tooltip || 'Betrachtungszeitraum wählen'}>
              <HelpCircle className="h-4 w-4 text-gray-400 dark:text-gray-500 cursor-help" />
            </SimpleTooltip>
          </div>
        )}
      </div>
    </div>
  )

  const bar = <>{nav}{steuerleiste}</>

  // ── Gates ──
  let inhalt: React.ReactNode
  if (anlagenLoading || checkingAccess) {
    inhalt = <div className="p-3 sm:p-6"><BlockStackSkeleton label="Lade…" /></div>
  } else if (anlagen.length === 0) {
    inhalt = <div className="p-3 sm:p-6"><Alert type="warning">Bitte lege zuerst eine PV-Anlage an.</Alert></div>
  } else if (!communityHash) {
    inhalt = (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card>
          <EmptyState
            icon={Users}
            title="Teile erst deine Daten"
            description="Um den Community-Vergleich nutzen zu können, musst du zuerst deine anonymisierten Anlagendaten mit der Community teilen."
            action={
              /* B15: ui/Button-SoT (size="lg" = px-6 py-3 wie vorher, Töne 600/700 statt 500/600). */
              <Button variant="primary" size="lg" className="gap-2" onClick={() => navigate('/v4/einstellungen/stammdaten')}>
                <Users className="h-5 w-5 max-sm:hidden" /> Jetzt teilen
              </Button>
            }
          />
        </Card>
      </div>
    )
  } else if (sub === 'uebersicht') {
    inhalt = <CommunityUebersichtV4 benchmark={benchmark} loading={benchmarkLoading} error={benchmarkError} />
  } else if (sub === 'pv-ertrag') {
    inhalt = <CommunityPVErtragV4 benchmark={benchmark} loading={benchmarkLoading} error={benchmarkError} />
  } else if (sub === 'komponenten') {
    inhalt = <CommunityKomponentenV4 benchmark={benchmark} loading={benchmarkLoading} error={benchmarkError} />
  } else if (sub === 'regional') {
    inhalt = <CommunityRegionalV4 benchmark={benchmark} loading={benchmarkLoading} error={benchmarkError} />
  } else if (sub === 'trends') {
    inhalt = <CommunityTrendsV4 benchmark={benchmark} loading={benchmarkLoading} error={benchmarkError} />
  } else {
    inhalt = <CommunityStatistikenV4 benchmark={benchmark} loading={benchmarkLoading} error={benchmarkError} />
  }

  return <ViewShell bar={bar}>{inhalt}</ViewShell>
}
