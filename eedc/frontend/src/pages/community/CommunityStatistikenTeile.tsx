/**
 * Community-Statistiken — geteilte Teile (Daten-Hook + Präsentations-Sektionen).
 * EINE Code-Wahrheit für IST (`StatistikenTab`) und IA-V4 (`CommunityStatistikenV4`).
 * Sektionen rendern Inhalt OHNE äußere Card/Block-Hülle (Aufrufer wickelt).
 * Zahlen de-DE (`fmtZahl`), Farben/Achsen aus der Zentrale.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  BarChart3,
  Users,
  Sun,
  Battery,
  Home,
  Car,
  Plug,
  MapPin,
  TrendingUp,
  CheckCircle2,
  XCircle,
  Calendar,
} from 'lucide-react'
import { communityApi } from '../../api'
import type { CommunityBenchmarkResponse, GlobaleStatistik, Ranking } from '../../api/community'
import { Parkbar } from '../../components/park'
import { Table, TableHead, TableBody } from '../../components/ui'
import { ZELLE, KOPF_ZELLE } from '../../components/ui/tabelleMasse'
import { fmtZahl } from '../../lib'
// Bundesland-Namen
import { REGION_NAMEN } from '../../lib/constants'

// Element-Park (IA-V4, Element-Park-Doktrin Gernot 2026-06-27): JEDE Anzeige
// (StatCard, Ranking-Box, DetailCard, Ausstattungs-Item, QuoteCard, Tabelle,
// Hinweis) ist einzeln parkbar. `Parkbar` ist OHNE ParkProvider inert → der
// IST-`StatistikenTab` (v3, kein Provider) bleibt optisch identisch; nur die
// V4-Sicht aktiviert die Geste. IDs view-eindeutig (Prefix 'stat-'); der
// V4-Builder blendet einen Block aus, wenn ALLE seine Element-IDs geparkt sind
// (alleGeparkt).
export const STAT_PARK_IDS = {
  uebersicht: ['stat-ueb-anlagen', 'stat-ueb-spezertrag', 'stat-ueb-region', 'stat-ueb-regionertrag'],
  position: ['stat-pos-gesamt', 'stat-pos-region'],
  anlage: [
    'stat-anlage-leistung', 'stat-anlage-ausrichtung', 'stat-anlage-neigung', 'stat-anlage-installation',
    'stat-ausstattung-speicher', 'stat-ausstattung-bkw', 'stat-ausstattung-wp', 'stat-ausstattung-wallbox', 'stat-ausstattung-eauto',
  ],
  quoten: [
    'stat-quote-speicher', 'stat-quote-bkw', 'stat-quote-wp', 'stat-quote-wallbox', 'stat-quote-eauto',
    'stat-typische',
  ],
  top10: ['stat-top10-tabelle', 'stat-top10-eigener'],
} as const

export interface CommunityStat {
  anzahlAnlagen: number
  anzahlRegion: number
  durchschnittErtrag: number
  regionErtrag: number
  region: string
  regionName: string
}

export interface AusstattungItem {
  name: string
  parkSlug: string
  icon: React.ReactNode
  vorhanden: boolean
  details: string | null
  cls: { bg: string; border: string; icon: string }
}

export interface PositionStat {
  rangGesamt: number
  vonGesamt: number
  perzentilGesamt: number
  rangRegion: number
  vonRegion: number
  perzentilRegion: number
}

export interface StatistikenDaten {
  globalStats: GlobaleStatistik | null
  ranking: Ranking | null
  communityStats: CommunityStat | null
  ausstattung: AusstattungItem[]
  position: PositionStat | null
  extraLoading: boolean
}

// ─── Daten-Hook (lädt globale Statistik + Top-10-Ranking; leitet Aggregate ab) ─

export function useStatistikenDaten(benchmark: CommunityBenchmarkResponse | null): StatistikenDaten {
  const [globalStats, setGlobalStats] = useState<GlobaleStatistik | null>(null)
  const [ranking, setRanking] = useState<Ranking | null>(null)
  const [extraLoading, setExtraLoading] = useState(false)

  // Globale Statistiken und Ranking laden (unabhängig vom Benchmark)
  useEffect(() => {
    const loadExtra = async () => {
      setExtraLoading(true)
      try {
        const [globalData, rankingData] = await Promise.all([
          communityApi.getGlobalStatistics().catch(() => null),
          communityApi.getRanking('spez_ertrag', 10).catch(() => null),
        ])
        setGlobalStats(globalData)
        setRanking(rankingData)
      } finally {
        setExtraLoading(false)
      }
    }
    loadExtra()
  }, [])

  // Community-Statistiken aus Benchmark ableiten
  const communityStats = useMemo<CommunityStat | null>(() => {
    if (!benchmark) return null

    return {
      anzahlAnlagen: benchmark.benchmark.anzahl_anlagen_gesamt,
      anzahlRegion: benchmark.benchmark.anzahl_anlagen_region,
      durchschnittErtrag: benchmark.benchmark.spez_ertrag_durchschnitt,
      regionErtrag: benchmark.benchmark.spez_ertrag_region,
      region: benchmark.anlage.region,
      regionName: REGION_NAMEN[benchmark.anlage.region] || benchmark.anlage.region,
    }
  }, [benchmark])

  // Ausstattungs-Vergleich (was hat deine Anlage vs. was ist möglich).
  // Reihenfolge folgt der SoT in `lib/constants.ts` (INVESTITION_TYP_ORDER):
  //   Speicher → BKW → WP → Wallbox → E-Auto
  // (#215 detLAN: BKW gehört nach Speicher, nicht ans Ende; WP vor Wallbox).
  // Farb-Klassen ausgeschrieben, weil Tailwind dynamische `bg-${color}-50`-
  // Klassen purged (#211 P1: Wallbox-Cyan unsichtbar).
  const ausstattung = useMemo<AusstattungItem[]>(() => {
    if (!benchmark) return []

    return [
      {
        name: 'Speicher',
        parkSlug: 'speicher',
        icon: <Battery className="h-5 w-5" />,
        vorhanden: !!benchmark.anlage.speicher_kwh,
        details: benchmark.anlage.speicher_kwh ? `${benchmark.anlage.speicher_kwh} kWh` : null,
        cls: { bg: 'bg-green-50 dark:bg-green-900/20',  border: 'border-green-200 dark:border-green-800',  icon: 'text-green-500' },
      },
      {
        name: 'Balkonkraftwerk',
        parkSlug: 'bkw',
        icon: <Sun className="h-5 w-5" />,
        vorhanden: benchmark.anlage.hat_balkonkraftwerk,
        details: benchmark.anlage.bkw_wp ? `${benchmark.anlage.bkw_wp} Wp` : null,
        cls: { bg: 'bg-amber-50 dark:bg-amber-900/20',  border: 'border-amber-200 dark:border-amber-800',  icon: 'text-amber-500' },
      },
      {
        name: 'Wärmepumpe',
        parkSlug: 'wp',
        icon: <Home className="h-5 w-5" />,
        vorhanden: benchmark.anlage.hat_waermepumpe,
        details: null,
        cls: { bg: 'bg-blue-50 dark:bg-blue-900/20',    border: 'border-blue-200 dark:border-blue-800',    icon: 'text-blue-500' },
      },
      {
        name: 'Wallbox',
        parkSlug: 'wallbox',
        icon: <Plug className="h-5 w-5" />,
        vorhanden: benchmark.anlage.hat_wallbox,
        details: benchmark.anlage.wallbox_kw ? `${benchmark.anlage.wallbox_kw} kW` : null,
        cls: { bg: 'bg-cyan-50 dark:bg-cyan-900/20',    border: 'border-cyan-200 dark:border-cyan-800',    icon: 'text-cyan-500' },
      },
      {
        name: 'E-Auto',
        parkSlug: 'eauto',
        icon: <Car className="h-5 w-5" />,
        vorhanden: benchmark.anlage.hat_eauto,
        details: null,
        cls: { bg: 'bg-purple-50 dark:bg-purple-900/20', border: 'border-purple-200 dark:border-purple-800', icon: 'text-purple-500' },
      },
    ]
  }, [benchmark])

  // Positionsberechnung
  const position = useMemo<PositionStat | null>(() => {
    if (!benchmark) return null

    const { rang_gesamt, anzahl_anlagen_gesamt, rang_region, anzahl_anlagen_region } = benchmark.benchmark
    const perzentilGesamt = Math.round((1 - rang_gesamt / anzahl_anlagen_gesamt) * 100)
    const perzentilRegion = Math.round((1 - rang_region / anzahl_anlagen_region) * 100)

    return {
      rangGesamt: rang_gesamt,
      vonGesamt: anzahl_anlagen_gesamt,
      perzentilGesamt,
      rangRegion: rang_region,
      vonRegion: anzahl_anlagen_region,
      perzentilRegion,
    }
  }, [benchmark])

  return { globalStats, ranking, communityStats, ausstattung, position, extraLoading }
}

// ─── Sektion: Community-Übersicht (4 StatCards) ───────────────────────────────

export function CommunityUebersicht({ communityStats }: { communityStats: CommunityStat }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
      <Parkbar id="stat-ueb-anlagen" titel="Anlagen gesamt">
        <StatCard
          label="Anlagen gesamt"
          value={communityStats.anzahlAnlagen}
          icon={<Users className="h-5 w-5 text-primary-500" />}
        />
      </Parkbar>
      <Parkbar id="stat-ueb-spezertrag" titel="Ø Spez. Ertrag">
        <StatCard
          label="Ø Spez. Ertrag"
          value={communityStats.durchschnittErtrag}
          suffix="kWh/kWp"
          icon={<Sun className="h-5 w-5 text-yellow-500" />}
        />
      </Parkbar>
      <Parkbar id="stat-ueb-region" titel={`In ${communityStats.regionName}`}>
        <StatCard
          label={`In ${communityStats.regionName}`}
          value={communityStats.anzahlRegion}
          suffix="Anlagen"
          icon={<MapPin className="h-5 w-5 text-blue-500" />}
        />
      </Parkbar>
      <Parkbar id="stat-ueb-regionertrag" titel="Ø Region">
        <StatCard
          label="Ø Region"
          value={communityStats.regionErtrag}
          suffix="kWh/kWp"
          icon={<BarChart3 className="h-5 w-5 text-green-500" />}
        />
      </Parkbar>
    </div>
  )
}

// ─── Sektion: Deine Position (Gesamt- + Regional-Ranking) ─────────────────────

export function DeinePosition({ position, communityStats }: { position: PositionStat; communityStats: CommunityStat }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {/* Gesamt-Ranking */}
      <Parkbar id="stat-pos-gesamt" titel="Community-weit">
      <div className="bg-gradient-to-br from-primary-50 to-primary-100 dark:from-primary-900/20 dark:to-primary-800/20 rounded-xl p-6">
        <div className="flex items-center gap-2 mb-4">
          <Users className="h-5 w-5 text-primary-500" />
          <span className="text-primary-700 dark:text-primary-300 font-medium">
            Community-weit
          </span>
        </div>
        <div className="flex items-baseline gap-2 mb-2">
          <span className="text-4xl font-bold text-primary-600 dark:text-primary-400">
            #{position.rangGesamt}
          </span>
          <span className="text-primary-500 dark:text-primary-400">
            von {position.vonGesamt}
          </span>
        </div>
        <ProgressBar value={position.perzentilGesamt} color="primary" />
        <p className="text-sm text-primary-600 dark:text-primary-400 mt-2">
          Besser als {position.perzentilGesamt} % der Community
        </p>
      </div>
      </Parkbar>

      {/* Regional-Ranking */}
      <Parkbar id="stat-pos-region" titel={`In ${communityStats.regionName}`}>
      <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 rounded-xl p-6">
        <div className="flex items-center gap-2 mb-4">
          <MapPin className="h-5 w-5 text-blue-500" />
          <span className="text-blue-700 dark:text-blue-300 font-medium">
            In {communityStats.regionName}
          </span>
        </div>
        <div className="flex items-baseline gap-2 mb-2">
          <span className="text-4xl font-bold text-blue-600 dark:text-blue-400">
            #{position.rangRegion}
          </span>
          <span className="text-blue-500 dark:text-blue-400">
            von {position.vonRegion}
          </span>
        </div>
        <ProgressBar value={position.perzentilRegion} color="blue" />
        <p className="text-sm text-blue-600 dark:text-blue-400 mt-2">
          Besser als {position.perzentilRegion} % in deiner Region
        </p>
      </div>
      </Parkbar>
    </div>
  )
}

// ─── Sektion: Deine Anlage (Detail-Cards + Ausstattungs-Grid) ─────────────────

export function DeineAnlage({ benchmark, ausstattung }: { benchmark: CommunityBenchmarkResponse; ausstattung: AusstattungItem[] }) {
  return (
    <div>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-6">
        <Parkbar id="stat-anlage-leistung" titel="Leistung">
          <DetailCard
            label="Leistung"
            value={`${fmtZahl(benchmark.anlage.kwp, 1)} kWp`}
            icon={<Sun className="h-5 w-5 text-yellow-500" />}
          />
        </Parkbar>
        <Parkbar id="stat-anlage-ausrichtung" titel="Ausrichtung">
          <DetailCard
            label="Ausrichtung"
            value={benchmark.anlage.ausrichtung}
            icon={<TrendingUp className="h-5 w-5 text-blue-500" />}
            capitalize
          />
        </Parkbar>
        <Parkbar id="stat-anlage-neigung" titel="Neigung">
          <DetailCard
            label="Neigung"
            value={`${benchmark.anlage.neigung_grad}°`}
            icon={<BarChart3 className="h-5 w-5 text-green-500" />}
          />
        </Parkbar>
        <Parkbar id="stat-anlage-installation" titel="Installation">
          <DetailCard
            label="Installation"
            value={String(benchmark.anlage.installation_jahr)}
            icon={<Calendar className="h-5 w-5 text-gray-500" />}
          />
        </Parkbar>
      </div>

      {/* Ausstattung */}
      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
        Ausstattung
      </h4>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {ausstattung.map((item) => (
          <Parkbar key={item.name} id={`stat-ausstattung-${item.parkSlug}`} titel={item.name}>
          <div
            className={`flex items-center gap-2 p-3 rounded-lg border ${
              item.vorhanden
                ? `${item.cls.bg} ${item.cls.border}`
                : 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
            }`}
          >
            <div className={`flex-shrink-0 ${item.vorhanden ? item.cls.icon : 'text-gray-400 dark:text-gray-500'}`}>
              {item.icon}
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium truncate ${
                item.vorhanden
                  ? 'text-gray-900 dark:text-white'
                  : 'text-gray-400 dark:text-gray-500'
              }`} title={item.name}>
                {item.name}
              </p>
              {/* D13-17: Subzeile IMMER rendern (nbsp-Platzhalter wenn leer),
                  damit Kacheln mit/ohne Detail gleich hoch sind (D11-1-Muster). */}
              <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                {item.details || ' '}
              </p>
            </div>
            {item.vorhanden ? (
              <CheckCircle2 className={`h-4 w-4 flex-shrink-0 ${item.cls.icon}`} />
            ) : (
              <XCircle className="h-4 w-4 flex-shrink-0 text-gray-300 dark:text-gray-600" />
            )}
          </div>
          </Parkbar>
        ))}
      </div>
    </div>
  )
}

// ─── Sektion: Ausstattungsquoten (QuoteCards + typische Anlage) ───────────────

export function Ausstattungsquoten({ globalStats }: { globalStats: GlobaleStatistik }) {
  return (
    <div>
      {/* #215 detLAN: Reihenfolge folgt INVESTITION_TYP_ORDER —
          Speicher → BKW → WP → Wallbox → E-Auto. */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Parkbar id="stat-quote-speicher" titel="Quote Speicher">
          <QuoteCard label="Speicher" value={globalStats.ausstattungsquoten.speicher} color="green" />
        </Parkbar>
        <Parkbar id="stat-quote-bkw" titel="Quote Balkonkraftwerk">
          <QuoteCard label="Balkonkraftwerk" value={globalStats.ausstattungsquoten.balkonkraftwerk} color="amber" />
        </Parkbar>
        <Parkbar id="stat-quote-wp" titel="Quote Wärmepumpe">
          <QuoteCard label="Wärmepumpe" value={globalStats.ausstattungsquoten.waermepumpe} color="blue" />
        </Parkbar>
        <Parkbar id="stat-quote-wallbox" titel="Quote Wallbox">
          <QuoteCard label="Wallbox" value={globalStats.ausstattungsquoten.wallbox} color="cyan" />
        </Parkbar>
        <Parkbar id="stat-quote-eauto" titel="Quote E-Auto">
          <QuoteCard label="E-Auto" value={globalStats.ausstattungsquoten.eauto} color="purple" />
        </Parkbar>
      </div>

      {/* Typische Anlage */}
      <Parkbar id="stat-typische" titel="Die typische Community-Anlage">
      <div className="mt-6 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
          Die typische Community-Anlage
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 text-sm">
          <div>
            <span className="text-gray-500">Leistung:</span>
            <span className="ml-2 font-medium">{fmtZahl(globalStats.typische_anlage.kwp, 1)} kWp</span>
          </div>
          <div>
            <span className="text-gray-500">Ausrichtung:</span>
            <span className="ml-2 font-medium capitalize">{globalStats.typische_anlage.ausrichtung}</span>
          </div>
          <div>
            <span className="text-gray-500">Neigung:</span>
            <span className="ml-2 font-medium">{globalStats.typische_anlage.neigung_grad}°</span>
          </div>
          {globalStats.typische_anlage.speicher_kwh && (
            <div>
              <span className="text-gray-500">Speicher:</span>
              <span className="ml-2 font-medium">{globalStats.typische_anlage.speicher_kwh} kWh</span>
            </div>
          )}
        </div>
      </div>
      </Parkbar>
    </div>
  )
}

// ─── Sektion: Top-10 Bestenliste (Tabelle + eigener-Rang-Hinweis) ─────────────

export function Top10Bestenliste({ ranking }: { ranking: Ranking }) {
  return (
    <div>
      <Parkbar id="stat-top10-tabelle" titel="Top-10-Tabelle">
      <Table>
        <TableHead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            <th className={`${KOPF_ZELLE} text-left text-gray-500`}>Rang</th>
            <th className={`${KOPF_ZELLE} text-left text-gray-500`}>Region</th>
            <th className={`${KOPF_ZELLE} text-right text-gray-500`}>kWp</th>
            <th className={`${KOPF_ZELLE} text-right text-gray-500`}>kWh/kWp</th>
          </tr>
        </TableHead>
        <TableBody>
          {ranking.ranking.map((eintrag) => (
            <tr key={eintrag.rang} className="border-b border-gray-100 dark:border-gray-800">
              <td className={ZELLE}>
                <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                  eintrag.rang === 1 ? 'bg-yellow-100 text-yellow-700' :
                  eintrag.rang === 2 ? 'bg-gray-200 text-gray-700' :
                  eintrag.rang === 3 ? 'bg-orange-100 text-orange-700' :
                  'bg-gray-100 text-gray-600'
                }`}>
                  {eintrag.rang}
                </span>
              </td>
              <td className={`${ZELLE} text-gray-900 dark:text-white`}>
                {REGION_NAMEN[eintrag.region] || eintrag.region}
              </td>
              <td className={`${ZELLE} text-right text-gray-600 dark:text-gray-400`}>
                {fmtZahl(eintrag.kwp, 1)}
              </td>
              <td className={`${ZELLE} text-right font-medium text-gray-900 dark:text-white`}>
                {fmtZahl(eintrag.wert, 0)}
              </td>
            </tr>
          ))}
        </TableBody>
      </Table>
      </Parkbar>

      {ranking.eigener_rang && (
        <Parkbar id="stat-top10-eigener" titel="Dein Rang">
        <div className="mt-4 p-3 bg-primary-50 dark:bg-primary-900/20 rounded-lg text-center">
          <span className="text-primary-700 dark:text-primary-300">
            Dein Rang: <strong>#{ranking.eigener_rang}</strong> mit <strong>{fmtZahl(ranking.eigener_wert, 0)} kWh/kWp</strong>
          </span>
        </div>
        </Parkbar>
      )}
    </div>
  )
}

// =============================================================================
// Hilfskomponenten (intern)
// =============================================================================

// Hilfskomponente für Ausstattungsquoten
function QuoteCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className={`p-4 rounded-lg bg-${color}-50 dark:bg-${color}-900/20`}>
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">{label}</p>
      <p className={`text-2xl font-bold text-${color}-600 dark:text-${color}-400`}>
        {fmtZahl(value, 1)} %
      </p>
    </div>
  )
}

function StatCard({
  label,
  value,
  suffix,
  icon,
}: {
  label: string
  value: number
  suffix?: string
  icon: React.ReactNode
}) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-bold text-gray-900 dark:text-white">
          {typeof value === 'number' && value >= 1000
            ? value.toLocaleString('de-DE')
            : fmtZahl(value, value < 10 ? 1 : 0)}
        </span>
        {suffix && (
          <span className="text-sm text-gray-500 dark:text-gray-400">{suffix}</span>
        )}
      </div>
    </div>
  )
}

function DetailCard({
  label,
  value,
  icon,
  capitalize,
}: {
  label: string
  value: string
  icon: React.ReactNode
  capitalize?: boolean
}) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-xs text-gray-500 dark:text-gray-400">{label}</span>
      </div>
      <span className={`text-lg font-semibold text-gray-900 dark:text-white ${capitalize ? 'capitalize' : ''}`}>
        {value}
      </span>
    </div>
  )
}

function ProgressBar({ value, color }: { value: number; color: 'primary' | 'blue' }) {
  const colorClasses = {
    primary: 'bg-primary-500',
    blue: 'bg-blue-500',
  }

  return (
    <div className="w-full bg-white/50 dark:bg-gray-700/50 rounded-sm h-2">
      <div
        className={`h-2 rounded-sm ${colorClasses[color]} transition-all duration-500`}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  )
}
