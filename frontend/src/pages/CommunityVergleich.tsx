/**
 * Community Vergleich Page
 *
 * @deprecated Diese Komponente wurde nach /pages/community/UebersichtTab.tsx migriert.
 * Die Route /auswertungen/community wird jetzt nach /community redirected.
 * Diese Datei kann in einer zukünftigen Version entfernt werden.
 *
 * Zeigt erweiterte Benchmark-Daten im Vergleich zur Community.
 * WICHTIG: Nur verfügbar wenn die Anlage bereits mit der Community geteilt wurde!
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart3,
  Trophy,
  Battery,
  Home,
  Car,
  Plug,
  Sun,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  ExternalLink,
  MapPin,
} from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select } from '../components/ui'
import { useAnlagen } from '../hooks'
import { communityApi, anlagenApi } from '../api'
import type {
  CommunityBenchmarkResponse,
  ZeitraumTyp,
  KPIVergleich,
} from '../api/community'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

// Zeitraum-Labels
const ZEITRAUM_OPTIONS: { value: ZeitraumTyp; label: string }[] = [
  { value: 'letzter_monat', label: 'Letzter Monat' },
  { value: 'letzte_12_monate', label: 'Letzte 12 Monate' },
  { value: 'letztes_vollstaendiges_jahr', label: 'Letztes Jahr (vollständig)' },
  { value: 'seit_installation', label: 'Seit Installation' },
]

// Bundesland-Namen
const REGION_NAMEN: Record<string, string> = {
  BW: 'Baden-Württemberg',
  BY: 'Bayern',
  BE: 'Berlin',
  BB: 'Brandenburg',
  HB: 'Bremen',
  HH: 'Hamburg',
  HE: 'Hessen',
  MV: 'Mecklenburg-Vorpommern',
  NI: 'Niedersachsen',
  NW: 'Nordrhein-Westfalen',
  RP: 'Rheinland-Pfalz',
  SL: 'Saarland',
  SN: 'Sachsen',
  ST: 'Sachsen-Anhalt',
  SH: 'Schleswig-Holstein',
  TH: 'Thüringen',
  AT: 'Österreich',
  CH: 'Schweiz',
}

interface CommunityVergleichProps {
  /** Wenn true, wird ohne eigenen Header angezeigt (eingebettet in Auswertung) */
  embedded?: boolean
  /** Anlage-ID wenn embedded (überschreibt interne Auswahl) */
  anlageId?: number
}

export default function CommunityVergleich({ embedded = false, anlageId: propsAnlageId }: CommunityVergleichProps) {
  const navigate = useNavigate()
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>()
  const [zeitraum, setZeitraum] = useState<ZeitraumTyp>('letzte_12_monate')
  const [benchmark, setBenchmark] = useState<CommunityBenchmarkResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notShared, setNotShared] = useState(false)

  // Prüfen ob Anlage bereits geteilt wurde
  const [communityHash, setCommunityHash] = useState<string | null>(null)

  // Effektive Anlage-ID (Props > Selected > First)
  const effectiveAnlageId = propsAnlageId ?? selectedAnlageId

  useEffect(() => {
    // Nur setzen wenn nicht embedded (dort kommt ID von Props)
    if (!embedded && anlagen.length > 0 && !selectedAnlageId) {
      setSelectedAnlageId(anlagen[0].id)
    }
  }, [anlagen, selectedAnlageId, embedded])

  // Community Hash für die Anlage abrufen
  useEffect(() => {
    if (!effectiveAnlageId) return

    const checkCommunityStatus = async () => {
      try {
        const anlage = await anlagenApi.get(effectiveAnlageId)
        setCommunityHash(anlage.community_hash || null)
        setNotShared(!anlage.community_hash)
      } catch {
        setCommunityHash(null)
        setNotShared(true)
      }
    }
    checkCommunityStatus()
  }, [effectiveAnlageId])

  // Benchmark laden
  useEffect(() => {
    if (!effectiveAnlageId || notShared) {
      setBenchmark(null)
      return
    }

    const loadBenchmark = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await communityApi.getBenchmark(effectiveAnlageId, zeitraum)
        setBenchmark(data)
      } catch (e) {
        if (e instanceof Error && e.message.includes('403')) {
          setNotShared(true)
        } else {
          setError(e instanceof Error ? e.message : 'Fehler beim Laden')
        }
      } finally {
        setLoading(false)
      }
    }

    loadBenchmark()
  }, [effectiveAnlageId, zeitraum, notShared])

  // Im embedded-Modus kein Loading für Anlagen zeigen
  if (!embedded && anlagenLoading) return <LoadingSpinner text="Lade..." />

  if (!embedded && anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Community Vergleich</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  // Nicht geteilt - Hinweis anzeigen (wird im embedded-Modus nicht erreicht, da Tab ausgeblendet)
  if (notShared) {
    return (
      <div className="space-y-6">
        {!embedded && (
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-3">
              <BarChart3 className="h-8 w-8 text-orange-500" />
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Community Vergleich</h1>
            </div>
            {anlagen.length > 1 && (
              <Select
                value={selectedAnlageId?.toString() || ''}
                onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
                options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
              />
            )}
          </div>
        )}

        <Card>
          <div className="text-center py-12">
            <AlertCircle className="h-16 w-16 text-orange-500 mx-auto mb-4" />
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
              className="inline-flex items-center gap-2 px-6 py-3 bg-orange-500 text-white rounded-lg hover:bg-orange-600 font-medium"
            >
              <ExternalLink className="h-5 w-5" />
              Jetzt teilen
            </button>
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header mit Anlagen- und Zeitraum-Auswahl (nur im Standalone-Modus) */}
      {!embedded ? (
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <BarChart3 className="h-8 w-8 text-orange-500" />
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Community Vergleich</h1>
          </div>
          <div className="flex items-center gap-3">
            {anlagen.length > 1 && (
              <Select
                value={selectedAnlageId?.toString() || ''}
                onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
                options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
              />
            )}
            <Select
              value={zeitraum}
              onChange={(e) => setZeitraum(e.target.value as ZeitraumTyp)}
              options={ZEITRAUM_OPTIONS}
            />
          </div>
        </div>
      ) : (
        // Im embedded-Modus nur Zeitraum-Auswahl rechts
        <div className="flex justify-end">
          <Select
            value={zeitraum}
            onChange={(e) => setZeitraum(e.target.value as ZeitraumTyp)}
            options={ZEITRAUM_OPTIONS}
          />
        </div>
      )}

      {error && <Alert type="error">{error}</Alert>}

      {loading ? (
        <LoadingSpinner text="Lade Community-Daten..." />
      ) : benchmark ? (
        <>
          {/* Haupt-Benchmark Karte */}
          <Card>
            <div className="flex items-center gap-2 mb-6">
              <Trophy className="h-6 w-6 text-yellow-500" />
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                Dein PV-Ertrag im Vergleich
              </h2>
              <span className="ml-auto text-sm text-gray-500">
                {benchmark.zeitraum_label}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Haupt-KPI */}
              <div className="text-center md:col-span-1">
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Dein spez. Ertrag</p>
                <p className="text-4xl font-bold text-orange-500">
                  {benchmark.benchmark.spez_ertrag_anlage.toFixed(0)}
                </p>
                <p className="text-gray-500">kWh/kWp</p>
                <AbweichungBadge
                  wert={benchmark.benchmark.spez_ertrag_anlage}
                  durchschnitt={benchmark.benchmark.spez_ertrag_durchschnitt}
                />
              </div>

              {/* Vergleichswerte */}
              <div className="md:col-span-2">
                <div className="grid grid-cols-2 gap-4">
                  <VergleichsBox
                    label="Community Durchschnitt"
                    wert={benchmark.benchmark.spez_ertrag_durchschnitt}
                    einheit="kWh/kWp"
                    icon={<BarChart3 className="h-5 w-5 text-gray-400" />}
                  />
                  <VergleichsBox
                    label={REGION_NAMEN[benchmark.anlage.region] || benchmark.anlage.region}
                    wert={benchmark.benchmark.spez_ertrag_region}
                    einheit="kWh/kWp"
                    icon={<MapPin className="h-5 w-5 text-blue-400" />}
                  />
                  <VergleichsBox
                    label="Rang gesamt"
                    wert={benchmark.benchmark.rang_gesamt}
                    zusatz={`von ${benchmark.benchmark.anzahl_anlagen_gesamt}`}
                    icon={<Trophy className="h-5 w-5 text-yellow-500" />}
                    isRank
                  />
                  <VergleichsBox
                    label="Rang Region"
                    wert={benchmark.benchmark.rang_region}
                    zusatz={`von ${benchmark.benchmark.anzahl_anlagen_region}`}
                    icon={<Trophy className="h-5 w-5 text-blue-500" />}
                    isRank
                  />
                </div>
              </div>
            </div>
          </Card>

          {/* Komponenten-Benchmarks */}
          {benchmark.benchmark_erweitert && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Speicher */}
              {benchmark.benchmark_erweitert.speicher && benchmark.anlage.speicher_kwh && (
                <KomponentenCard
                  title="Speicher"
                  icon={<Battery className="h-6 w-6 text-green-500" />}
                  kapazitaet={`${benchmark.anlage.speicher_kwh} kWh`}
                >
                  <KPIRow
                    label="Zyklen/Jahr"
                    kpi={benchmark.benchmark_erweitert.speicher.zyklen_jahr}
                    einheit=""
                  />
                  <KPIRow
                    label="Wirkungsgrad"
                    kpi={benchmark.benchmark_erweitert.speicher.wirkungsgrad}
                    einheit="%"
                  />
                  <KPIRow
                    label="Netzladung"
                    kpi={benchmark.benchmark_erweitert.speicher.netz_anteil}
                    einheit="%"
                    invertColors
                  />
                </KomponentenCard>
              )}

              {/* Wärmepumpe */}
              {benchmark.benchmark_erweitert.waermepumpe && benchmark.anlage.hat_waermepumpe && (
                <KomponentenCard
                  title="Wärmepumpe"
                  icon={<Home className="h-6 w-6 text-blue-500" />}
                >
                  <KPIRow
                    label="JAZ (Jahresarbeitszahl)"
                    kpi={benchmark.benchmark_erweitert.waermepumpe.jaz}
                    einheit=""
                  />
                  <KPIRow
                    label="Stromverbrauch"
                    kpi={benchmark.benchmark_erweitert.waermepumpe.stromverbrauch}
                    einheit="kWh"
                    hideComparison
                  />
                  <KPIRow
                    label="Wärmeerzeugung"
                    kpi={benchmark.benchmark_erweitert.waermepumpe.waermeerzeugung}
                    einheit="kWh"
                    hideComparison
                  />
                </KomponentenCard>
              )}

              {/* E-Auto */}
              {benchmark.benchmark_erweitert.eauto && benchmark.anlage.hat_eauto && (
                <KomponentenCard
                  title="E-Auto"
                  icon={<Car className="h-6 w-6 text-purple-500" />}
                >
                  <KPIRow
                    label="PV-Anteil"
                    kpi={benchmark.benchmark_erweitert.eauto.pv_anteil}
                    einheit="%"
                  />
                  <KPIRow
                    label="Ladung gesamt"
                    kpi={benchmark.benchmark_erweitert.eauto.ladung_gesamt}
                    einheit="kWh"
                    hideComparison
                  />
                  <KPIRow
                    label="Verbrauch"
                    kpi={benchmark.benchmark_erweitert.eauto.verbrauch_100km}
                    einheit="kWh/100km"
                    invertColors
                  />
                  {benchmark.benchmark_erweitert.eauto.v2h && (
                    <KPIRow
                      label="V2H Entladung"
                      kpi={benchmark.benchmark_erweitert.eauto.v2h}
                      einheit="kWh"
                      hideComparison
                    />
                  )}
                </KomponentenCard>
              )}

              {/* Wallbox */}
              {benchmark.benchmark_erweitert.wallbox && benchmark.anlage.hat_wallbox && (
                <KomponentenCard
                  title="Wallbox"
                  icon={<Plug className="h-6 w-6 text-cyan-500" />}
                  kapazitaet={benchmark.anlage.wallbox_kw ? `${benchmark.anlage.wallbox_kw} kW` : undefined}
                >
                  <KPIRow
                    label="PV-Anteil Ladung"
                    kpi={benchmark.benchmark_erweitert.wallbox.pv_anteil}
                    einheit="%"
                  />
                  <KPIRow
                    label="Ladung gesamt"
                    kpi={benchmark.benchmark_erweitert.wallbox.ladung}
                    einheit="kWh"
                    hideComparison
                  />
                  <KPIRow
                    label="Ladevorgänge"
                    kpi={benchmark.benchmark_erweitert.wallbox.ladevorgaenge}
                    einheit=""
                    hideComparison
                  />
                </KomponentenCard>
              )}

              {/* Balkonkraftwerk */}
              {benchmark.benchmark_erweitert.balkonkraftwerk && benchmark.anlage.hat_balkonkraftwerk && (
                <KomponentenCard
                  title="Balkonkraftwerk"
                  icon={<Sun className="h-6 w-6 text-amber-500" />}
                  kapazitaet={benchmark.anlage.bkw_wp ? `${benchmark.anlage.bkw_wp} Wp` : undefined}
                >
                  <KPIRow
                    label="Spez. Ertrag"
                    kpi={benchmark.benchmark_erweitert.balkonkraftwerk.spez_ertrag}
                    einheit="kWh/kWp"
                  />
                  <KPIRow
                    label="Erzeugung"
                    kpi={benchmark.benchmark_erweitert.balkonkraftwerk.erzeugung}
                    einheit="kWh"
                    hideComparison
                  />
                  <KPIRow
                    label="Eigenverbrauchsquote"
                    kpi={benchmark.benchmark_erweitert.balkonkraftwerk.eigenverbrauch}
                    einheit="%"
                    hideComparison
                  />
                </KomponentenCard>
              )}
            </div>
          )}

          {/* Monatlicher Vergleich Chart */}
          {benchmark.anlage.monatswerte && benchmark.anlage.monatswerte.length > 0 && (
            <Card>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Monatlicher Ertrag
              </h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={benchmark.anlage.monatswerte.slice(-12).map(m => ({
                      name: `${m.monat}/${m.jahr % 100}`,
                      ertrag: m.spez_ertrag_kwh_kwp || 0,
                    }))}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#6b7280', fontSize: 12 }} />
                    <Tooltip
                      formatter={(value: number) => [`${value.toFixed(1)} kWh/kWp`, 'Spez. Ertrag']}
                      contentStyle={{ background: '#fff', border: '1px solid #e5e7eb' }}
                    />
                    <Bar dataKey="ertrag" radius={[4, 4, 0, 0]}>
                      {benchmark.anlage.monatswerte.slice(-12).map((_, index) => (
                        <Cell key={`cell-${index}`} fill="#f97316" />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          )}

          {/* Link zur Community-Seite */}
          <div className="text-center">
            <a
              href={`https://energy.raunet.eu?anlage=${communityHash}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-orange-600 hover:text-orange-700"
            >
              <ExternalLink className="h-4 w-4" />
              Vollständiges Benchmark auf energy.raunet.eu
            </a>
          </div>
        </>
      ) : null}
    </div>
  )
}

// Hilfsfunktion: Abweichung berechnen und anzeigen
function AbweichungBadge({ wert, durchschnitt }: { wert: number; durchschnitt: number }) {
  const abweichung = ((wert - durchschnitt) / durchschnitt) * 100
  const isPositive = abweichung >= 0

  return (
    <span
      className={`inline-flex items-center gap-1 mt-2 px-2 py-1 rounded text-sm font-medium ${
        isPositive
          ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
          : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
      }`}
    >
      {isPositive ? (
        <TrendingUp className="h-4 w-4" />
      ) : (
        <TrendingDown className="h-4 w-4" />
      )}
      {isPositive ? '+' : ''}
      {abweichung.toFixed(1)}% vs. Durchschnitt
    </span>
  )
}

// Vergleichsbox Komponente
function VergleichsBox({
  label,
  wert,
  einheit,
  zusatz,
  icon,
  isRank,
}: {
  label: string
  wert: number
  einheit?: string
  zusatz?: string
  icon?: React.ReactNode
  isRank?: boolean
}) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      </div>
      <p className="text-xl font-semibold text-gray-900 dark:text-white">
        {isRank ? '#' : ''}
        {wert.toFixed(isRank ? 0 : 0)}
        {einheit && <span className="text-sm font-normal text-gray-500 ml-1">{einheit}</span>}
        {zusatz && <span className="text-sm font-normal text-gray-400 ml-2">{zusatz}</span>}
      </p>
    </div>
  )
}

// Komponenten-Karte
function KomponentenCard({
  title,
  icon,
  kapazitaet,
  children,
}: {
  title: string
  icon: React.ReactNode
  kapazitaet?: string
  children: React.ReactNode
}) {
  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          {icon}
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>
        </div>
        {kapazitaet && (
          <span className="text-sm text-gray-500 dark:text-gray-400">{kapazitaet}</span>
        )}
      </div>
      <div className="space-y-3">{children}</div>
    </Card>
  )
}

// KPI-Zeile mit optionalem Vergleich
function KPIRow({
  label,
  kpi,
  einheit,
  hideComparison,
  invertColors,
}: {
  label: string
  kpi?: KPIVergleich | null
  einheit: string
  hideComparison?: boolean
  invertColors?: boolean
}) {
  if (!kpi) return null

  const hasComparison = !hideComparison && kpi.community_avg !== undefined && kpi.community_avg !== null
  const abweichung = hasComparison ? ((kpi.wert - kpi.community_avg!) / kpi.community_avg!) * 100 : null

  // Bei invertColors ist weniger besser (z.B. Netzladung, Verbrauch)
  const isPositive = abweichung !== null ? (invertColors ? abweichung < 0 : abweichung > 0) : null

  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <span className="text-gray-600 dark:text-gray-400">{label}</span>
      <div className="flex items-center gap-3">
        <span className="font-semibold text-gray-900 dark:text-white">
          {kpi.wert.toFixed(einheit === '%' || einheit === '' ? 1 : 0)} {einheit}
        </span>
        {hasComparison && abweichung !== null && (
          <span
            className={`text-sm ${
              isPositive
                ? 'text-green-600 dark:text-green-400'
                : 'text-red-600 dark:text-red-400'
            }`}
          >
            ({abweichung >= 0 ? '+' : ''}{abweichung.toFixed(1)}%)
          </span>
        )}
      </div>
    </div>
  )
}
