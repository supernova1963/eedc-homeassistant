/**
 * Community Übersicht Tab
 *
 * Zeigt erweiterte Benchmark-Daten im Vergleich zur Community:
 * - Ranking-Badges (Top 10%, 25%, 50%)
 * - Achievements (Gamification)
 * - Stärken/Schwächen-Anzeige
 * - Radar-Chart: Eigene vs. Community
 * - Komponenten-Benchmarks
 */

import { useState, useEffect, useMemo } from 'react'
import {
  Trophy,
  Battery,
  Home,
  Car,
  Plug,
  Sun,
  TrendingUp,
  TrendingDown,
  MapPin,
  BarChart3,
  Award,
  ThumbsUp,
  ThumbsDown,
  Zap,
  Medal,
  Flame,
  Target,
  Sparkles,
  Shield,
  HelpCircle,
} from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import { SimpleTooltip } from '../../components/ui/FormelTooltip'
import { communityApi } from '../../api'
import type {
  CommunityBenchmarkResponse,
  ZeitraumTyp,
  KPIVergleich,
} from '../../api/community'
import {
  ResponsiveContainer,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Legend,
} from 'recharts'

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

interface UebersichtTabProps {
  anlageId: number
  zeitraum: ZeitraumTyp
}

// Stärken/Schwächen Analyse
interface PerformanceMetrik {
  label: string
  abweichungProzent: number
  icon: React.ReactNode
  kategorie: 'pv' | 'speicher' | 'waermepumpe' | 'eauto' | 'wallbox'
}

// Achievement-Definitionen
interface Achievement {
  id: string
  name: string
  beschreibung: string
  icon: React.ReactNode
  farbe: string
  erreicht: boolean
  fortschritt?: number // 0-100 für teilweise erreichte
}

// Achievement-Kriterien definieren
const ACHIEVEMENT_DEFINITIONEN = {
  solarprofi: {
    name: 'Solarprofi',
    beschreibung: 'Top 10% beim spezifischen Ertrag',
    icon: <Sun className="h-5 w-5" />,
    farbe: 'yellow',
  },
  autarkiemeister: {
    name: 'Autarkiemeister',
    beschreibung: 'Autarkiegrad über 80%',
    icon: <Shield className="h-5 w-5" />,
    farbe: 'green',
  },
  effizienzwunder: {
    name: 'Effizienzwunder',
    beschreibung: 'Speicher-Wirkungsgrad über 90%',
    icon: <Battery className="h-5 w-5" />,
    farbe: 'emerald',
  },
  waermekoenig: {
    name: 'Wärmekönig',
    beschreibung: 'Wärmepumpe JAZ über 4.0',
    icon: <Home className="h-5 w-5" />,
    farbe: 'blue',
  },
  gruenerfahrer: {
    name: 'Grüner Fahrer',
    beschreibung: 'E-Auto PV-Ladeanteil über 70%',
    icon: <Car className="h-5 w-5" />,
    farbe: 'purple',
  },
  regionalchampion: {
    name: 'Regionalchampion',
    beschreibung: 'Top 3 in deiner Region',
    icon: <MapPin className="h-5 w-5" />,
    farbe: 'cyan',
  },
  dauerbrenner: {
    name: 'Dauerbrenner',
    beschreibung: '12 Monate in Folge über Durchschnitt',
    icon: <Flame className="h-5 w-5" />,
    farbe: 'orange',
  },
  perfektionist: {
    name: 'Perfektionist',
    beschreibung: 'Alle Komponenten über Community-Durchschnitt',
    icon: <Target className="h-5 w-5" />,
    farbe: 'indigo',
  },
}

export default function UebersichtTab({ anlageId, zeitraum }: UebersichtTabProps) {
  const [benchmark, setBenchmark] = useState<CommunityBenchmarkResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Benchmark laden
  useEffect(() => {
    const loadBenchmark = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await communityApi.getBenchmark(anlageId, zeitraum)
        setBenchmark(data)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden')
      } finally {
        setLoading(false)
      }
    }

    loadBenchmark()
  }, [anlageId, zeitraum])

  // Ranking-Badge berechnen
  const rankingBadge = useMemo(() => {
    if (!benchmark) return null
    const { rang_gesamt, anzahl_anlagen_gesamt } = benchmark.benchmark
    const prozent = (rang_gesamt / anzahl_anlagen_gesamt) * 100

    if (prozent <= 10) return { label: 'Top 10%', color: 'bg-yellow-500', textColor: 'text-yellow-500' }
    if (prozent <= 25) return { label: 'Top 25%', color: 'bg-gray-400', textColor: 'text-gray-500' }
    if (prozent <= 50) return { label: 'Top 50%', color: 'bg-amber-700', textColor: 'text-amber-700' }
    return null
  }, [benchmark])

  // Achievements berechnen
  const achievements = useMemo((): { erreichte: Achievement[]; nichtErreichte: Achievement[] } => {
    if (!benchmark) return { erreichte: [], nichtErreichte: [] }

    const erreichte: Achievement[] = []
    const nichtErreichte: Achievement[] = []

    const { rang_gesamt, anzahl_anlagen_gesamt, rang_region, anzahl_anlagen_region } = benchmark.benchmark
    const perzentilGesamt = (rang_gesamt / anzahl_anlagen_gesamt) * 100

    // Solarprofi: Top 10%
    const solarprofiErreicht = perzentilGesamt <= 10
    const solarprofi: Achievement = {
      id: 'solarprofi',
      ...ACHIEVEMENT_DEFINITIONEN.solarprofi,
      erreicht: solarprofiErreicht,
      fortschritt: solarprofiErreicht ? 100 : Math.max(0, 100 - perzentilGesamt),
    }
    if (solarprofiErreicht) erreichte.push(solarprofi)
    else nichtErreichte.push(solarprofi)

    // Regionalchampion: Top 3 in Region
    const regionalchampionErreicht = rang_region <= 3
    const regionalchampion: Achievement = {
      id: 'regionalchampion',
      ...ACHIEVEMENT_DEFINITIONEN.regionalchampion,
      erreicht: regionalchampionErreicht,
      fortschritt: regionalchampionErreicht ? 100 : Math.max(0, (1 - rang_region / Math.min(10, anzahl_anlagen_region)) * 100),
    }
    if (regionalchampionErreicht) erreichte.push(regionalchampion)
    else nichtErreichte.push(regionalchampion)

    // Autarkiemeister: Autarkie > 80%
    const letzterMonat = benchmark.anlage.monatswerte?.[benchmark.anlage.monatswerte.length - 1]
    if (letzterMonat?.autarkie_prozent !== undefined && letzterMonat.autarkie_prozent !== null) {
      const autarkieErreicht = letzterMonat.autarkie_prozent >= 80
      const autarkiemeister: Achievement = {
        id: 'autarkiemeister',
        ...ACHIEVEMENT_DEFINITIONEN.autarkiemeister,
        erreicht: autarkieErreicht,
        fortschritt: autarkieErreicht ? 100 : (letzterMonat.autarkie_prozent / 80) * 100,
      }
      if (autarkieErreicht) erreichte.push(autarkiemeister)
      else nichtErreichte.push(autarkiemeister)
    }

    // Effizienzwunder: Speicher > 90%
    const speicher = benchmark.benchmark_erweitert?.speicher
    if (speicher?.wirkungsgrad) {
      const effizienzErreicht = speicher.wirkungsgrad.wert >= 90
      const effizienzwunder: Achievement = {
        id: 'effizienzwunder',
        ...ACHIEVEMENT_DEFINITIONEN.effizienzwunder,
        erreicht: effizienzErreicht,
        fortschritt: effizienzErreicht ? 100 : (speicher.wirkungsgrad.wert / 90) * 100,
      }
      if (effizienzErreicht) erreichte.push(effizienzwunder)
      else nichtErreichte.push(effizienzwunder)
    }

    // Wärmekönig: JAZ > 4.0
    const wp = benchmark.benchmark_erweitert?.waermepumpe
    if (wp?.jaz) {
      const jazErreicht = wp.jaz.wert >= 4.0
      const waermekoenig: Achievement = {
        id: 'waermekoenig',
        ...ACHIEVEMENT_DEFINITIONEN.waermekoenig,
        erreicht: jazErreicht,
        fortschritt: jazErreicht ? 100 : (wp.jaz.wert / 4.0) * 100,
      }
      if (jazErreicht) erreichte.push(waermekoenig)
      else nichtErreichte.push(waermekoenig)
    }

    // Grüner Fahrer: E-Auto PV-Anteil > 70%
    const eauto = benchmark.benchmark_erweitert?.eauto
    if (eauto?.pv_anteil) {
      const pvAnteilErreicht = eauto.pv_anteil.wert >= 70
      const gruenerfahrer: Achievement = {
        id: 'gruenerfahrer',
        ...ACHIEVEMENT_DEFINITIONEN.gruenerfahrer,
        erreicht: pvAnteilErreicht,
        fortschritt: pvAnteilErreicht ? 100 : (eauto.pv_anteil.wert / 70) * 100,
      }
      if (pvAnteilErreicht) erreichte.push(gruenerfahrer)
      else nichtErreichte.push(gruenerfahrer)
    }

    // Dauerbrenner: 12 Monate über Durchschnitt
    const monatswerte = benchmark.anlage.monatswerte || []
    const letzteZwoelf = monatswerte.slice(-12)
    const durchschnittMonat = benchmark.benchmark.spez_ertrag_durchschnitt / 12
    let ueberDurchschnittCount = 0
    for (const m of letzteZwoelf) {
      if ((m.spez_ertrag_kwh_kwp || 0) > durchschnittMonat) {
        ueberDurchschnittCount++
      }
    }
    const dauerbrennerErreicht = ueberDurchschnittCount === 12 && letzteZwoelf.length === 12
    const dauerbrenner: Achievement = {
      id: 'dauerbrenner',
      ...ACHIEVEMENT_DEFINITIONEN.dauerbrenner,
      erreicht: dauerbrennerErreicht,
      fortschritt: letzteZwoelf.length > 0 ? (ueberDurchschnittCount / Math.max(12, letzteZwoelf.length)) * 100 : 0,
    }
    if (dauerbrennerErreicht) erreichte.push(dauerbrenner)
    else if (letzteZwoelf.length >= 6) nichtErreichte.push(dauerbrenner)

    return { erreichte, nichtErreichte }
  }, [benchmark])

  // Stärken und Schwächen ermitteln
  const { staerken, schwaechen } = useMemo(() => {
    if (!benchmark) return { staerken: [], schwaechen: [] }

    const metriken: PerformanceMetrik[] = []

    // PV Ertrag
    const pvAbw = ((benchmark.benchmark.spez_ertrag_anlage - benchmark.benchmark.spez_ertrag_durchschnitt) /
      benchmark.benchmark.spez_ertrag_durchschnitt) * 100
    metriken.push({
      label: 'PV-Ertrag',
      abweichungProzent: pvAbw,
      icon: <Sun className="h-4 w-4" />,
      kategorie: 'pv',
    })

    // Speicher
    if (benchmark.benchmark_erweitert?.speicher) {
      const sp = benchmark.benchmark_erweitert.speicher
      if (sp.wirkungsgrad?.community_avg) {
        const abw = ((sp.wirkungsgrad.wert - sp.wirkungsgrad.community_avg) / sp.wirkungsgrad.community_avg) * 100
        metriken.push({
          label: 'Speicher-Effizienz',
          abweichungProzent: abw,
          icon: <Battery className="h-4 w-4" />,
          kategorie: 'speicher',
        })
      }
      if (sp.netz_anteil?.community_avg) {
        // Invertiert: weniger ist besser
        const abw = ((sp.netz_anteil.community_avg - sp.netz_anteil.wert) / sp.netz_anteil.community_avg) * 100
        metriken.push({
          label: 'PV-Ladeanteil Speicher',
          abweichungProzent: abw,
          icon: <Zap className="h-4 w-4" />,
          kategorie: 'speicher',
        })
      }
    }

    // Wärmepumpe
    if (benchmark.benchmark_erweitert?.waermepumpe?.jaz?.community_avg) {
      const wp = benchmark.benchmark_erweitert.waermepumpe
      const abw = ((wp.jaz!.wert - wp.jaz!.community_avg!) / wp.jaz!.community_avg!) * 100
      metriken.push({
        label: 'Wärmepumpe JAZ',
        abweichungProzent: abw,
        icon: <Home className="h-4 w-4" />,
        kategorie: 'waermepumpe',
      })
    }

    // E-Auto
    if (benchmark.benchmark_erweitert?.eauto?.pv_anteil?.community_avg) {
      const ea = benchmark.benchmark_erweitert.eauto
      const abw = ((ea.pv_anteil!.wert - ea.pv_anteil!.community_avg!) / ea.pv_anteil!.community_avg!) * 100
      metriken.push({
        label: 'E-Auto PV-Anteil',
        abweichungProzent: abw,
        icon: <Car className="h-4 w-4" />,
        kategorie: 'eauto',
      })
    }

    // Wallbox
    if (benchmark.benchmark_erweitert?.wallbox?.pv_anteil?.community_avg) {
      const wb = benchmark.benchmark_erweitert.wallbox
      const abw = ((wb.pv_anteil!.wert - wb.pv_anteil!.community_avg!) / wb.pv_anteil!.community_avg!) * 100
      metriken.push({
        label: 'Wallbox PV-Anteil',
        abweichungProzent: abw,
        icon: <Plug className="h-4 w-4" />,
        kategorie: 'wallbox',
      })
    }

    // Sortieren und Top 3 Stärken/Schwächen
    const sortiert = [...metriken].sort((a, b) => b.abweichungProzent - a.abweichungProzent)
    const staerken = sortiert.filter(m => m.abweichungProzent > 0).slice(0, 3)
    const schwaechen = sortiert.filter(m => m.abweichungProzent < 0).slice(-3).reverse()

    return { staerken, schwaechen }
  }, [benchmark])

  // Radar-Chart Daten
  const radarData = useMemo(() => {
    if (!benchmark) return []

    const data: { kategorie: string; du: number; community: number; fullMark: number }[] = []

    // PV-Ertrag (normalisiert auf 0-100 Skala)
    const pvMax = Math.max(benchmark.benchmark.spez_ertrag_anlage, benchmark.benchmark.spez_ertrag_durchschnitt) * 1.2
    data.push({
      kategorie: 'PV-Ertrag',
      du: (benchmark.benchmark.spez_ertrag_anlage / pvMax) * 100,
      community: (benchmark.benchmark.spez_ertrag_durchschnitt / pvMax) * 100,
      fullMark: 100,
    })

    // Autarkie (falls vorhanden)
    const letzterMonat = benchmark.anlage.monatswerte?.[benchmark.anlage.monatswerte.length - 1]
    if (letzterMonat?.autarkie_prozent) {
      data.push({
        kategorie: 'Autarkie',
        du: letzterMonat.autarkie_prozent,
        community: 65, // Annahme Community-Durchschnitt
        fullMark: 100,
      })
    }

    // Eigenverbrauch
    if (letzterMonat?.eigenverbrauch_prozent) {
      data.push({
        kategorie: 'Eigenverbrauch',
        du: letzterMonat.eigenverbrauch_prozent,
        community: 45, // Annahme Community-Durchschnitt
        fullMark: 100,
      })
    }

    // Speicher-Effizienz
    if (benchmark.benchmark_erweitert?.speicher?.wirkungsgrad?.community_avg) {
      const sp = benchmark.benchmark_erweitert.speicher
      data.push({
        kategorie: 'Speicher',
        du: sp.wirkungsgrad!.wert,
        community: sp.wirkungsgrad!.community_avg!,
        fullMark: 100,
      })
    }

    // WP JAZ (normalisiert)
    if (benchmark.benchmark_erweitert?.waermepumpe?.jaz?.community_avg) {
      const wp = benchmark.benchmark_erweitert.waermepumpe
      const jazMax = Math.max(wp.jaz!.wert, wp.jaz!.community_avg!) * 1.2
      data.push({
        kategorie: 'WP-Effizienz',
        du: (wp.jaz!.wert / jazMax) * 100,
        community: (wp.jaz!.community_avg! / jazMax) * 100,
        fullMark: 100,
      })
    }

    // E-Auto PV-Anteil
    if (benchmark.benchmark_erweitert?.eauto?.pv_anteil?.community_avg) {
      const ea = benchmark.benchmark_erweitert.eauto
      data.push({
        kategorie: 'E-Auto PV',
        du: ea.pv_anteil!.wert,
        community: ea.pv_anteil!.community_avg!,
        fullMark: 100,
      })
    }

    return data
  }, [benchmark])

  if (loading) {
    return <LoadingSpinner text="Lade Community-Daten..." />
  }

  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  if (!benchmark) {
    return null
  }

  return (
    <div className="space-y-6">
      {/* Ranking-Badge + Haupt-KPI */}
      <Card>
        <div className="flex items-center gap-2 mb-6">
          <Trophy className="h-6 w-6 text-yellow-500" />
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Dein PV-Ertrag im Vergleich
          </h2>
          {rankingBadge && (
            <span className={`ml-2 px-3 py-1 rounded-full text-white text-sm font-medium ${rankingBadge.color}`}>
              <Award className="h-4 w-4 inline mr-1" />
              {rankingBadge.label}
            </span>
          )}
          <span className="ml-auto text-sm text-gray-500">
            {benchmark.zeitraum_label}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Haupt-KPI */}
          <div className="text-center md:col-span-1">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Dein spez. Ertrag</p>
            <p className="text-4xl font-bold text-primary-500">
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

      {/* Stärken & Schwächen + Radar-Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Stärken & Schwächen */}
        {(staerken.length > 0 || schwaechen.length > 0) && (
          <Card>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Deine Performance
            </h3>

            {staerken.length > 0 && (
              <div className="mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <ThumbsUp className="h-5 w-5 text-green-500" />
                  <span className="font-medium text-gray-700 dark:text-gray-300">Stärken</span>
                </div>
                <div className="space-y-2">
                  {staerken.map((s, idx) => (
                    <div key={idx} className="flex items-center justify-between bg-green-50 dark:bg-green-900/20 rounded-lg px-3 py-2">
                      <div className="flex items-center gap-2">
                        {s.icon}
                        <span className="text-gray-700 dark:text-gray-300">{s.label}</span>
                      </div>
                      <span className="font-semibold text-green-600 dark:text-green-400">
                        +{s.abweichungProzent.toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {schwaechen.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <ThumbsDown className="h-5 w-5 text-red-500" />
                  <span className="font-medium text-gray-700 dark:text-gray-300">Verbesserungspotenzial</span>
                </div>
                <div className="space-y-2">
                  {schwaechen.map((s, idx) => (
                    <div key={idx} className="flex items-center justify-between bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">
                      <div className="flex items-center gap-2">
                        {s.icon}
                        <span className="text-gray-700 dark:text-gray-300">{s.label}</span>
                      </div>
                      <span className="font-semibold text-red-600 dark:text-red-400">
                        {s.abweichungProzent.toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>
        )}

        {/* Radar-Chart */}
        {radarData.length >= 3 && (
          <Card>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Performance-Profil
            </h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarData}>
                  <PolarGrid stroke="#e5e7eb" />
                  <PolarAngleAxis
                    dataKey="kategorie"
                    tick={{ fill: '#6b7280', fontSize: 11 }}
                  />
                  <PolarRadiusAxis
                    angle={90}
                    domain={[0, 100]}
                    tick={{ fill: '#9ca3af', fontSize: 10 }}
                  />
                  <Radar
                    name="Du"
                    dataKey="du"
                    stroke="var(--color-primary-500, #3b82f6)"
                    fill="var(--color-primary-500, #3b82f6)"
                    fillOpacity={0.3}
                  />
                  <Radar
                    name="Community"
                    dataKey="community"
                    stroke="#9ca3af"
                    fill="#9ca3af"
                    fillOpacity={0.1}
                  />
                  <Legend />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        )}
      </div>

      {/* Achievements */}
      {(achievements.erreichte.length > 0 || achievements.nichtErreichte.length > 0) && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="h-5 w-5 text-yellow-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Achievements
            </h3>
            {achievements.erreichte.length > 0 && (
              <span className="ml-auto text-sm text-gray-500">
                {achievements.erreichte.length} von {achievements.erreichte.length + achievements.nichtErreichte.length} erreicht
              </span>
            )}
          </div>

          {/* Erreichte Achievements */}
          {achievements.erreichte.length > 0 && (
            <div className="mb-4">
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">Erreicht</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {achievements.erreichte.map((a) => (
                  <AchievementBadge key={a.id} achievement={a} />
                ))}
              </div>
            </div>
          )}

          {/* Nicht erreichte Achievements (mit Fortschritt) */}
          {achievements.nichtErreichte.length > 0 && (
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">In Reichweite</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {achievements.nichtErreichte.slice(0, 4).map((a) => (
                  <AchievementBadge key={a.id} achievement={a} />
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

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

// Vergleichsbox-Erklärungen
const VERGLEICH_TOOLTIPS: Record<string, string> = {
  'Rang gesamt': 'Deine Position im Vergleich zu allen teilnehmenden Anlagen',
  'Rang Region': 'Deine Position im Vergleich zu Anlagen in deiner Region',
  'Spez. Ertrag': 'Dein normierter Ertrag (kWh/kWp) im Vergleichszeitraum',
}

// Vergleichsbox Komponente
function VergleichsBox({
  label,
  wert,
  einheit,
  zusatz,
  icon,
  isRank,
  tooltip,
}: {
  label: string
  wert: number
  einheit?: string
  zusatz?: string
  icon?: React.ReactNode
  isRank?: boolean
  tooltip?: string
}) {
  const tooltipText = tooltip || VERGLEICH_TOOLTIPS[label]

  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-1">
          {label}
          {tooltipText && (
            <SimpleTooltip text={tooltipText}>
              <HelpCircle className="h-3 w-3 text-gray-400 opacity-60" />
            </SimpleTooltip>
          )}
        </span>
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
// KPI-Erklärungen
const KPI_TOOLTIPS: Record<string, string> = {
  'Spez. Ertrag': 'Ertrag normiert auf installierte Leistung (kWh pro kWp)',
  'Autarkie': 'Anteil des Eigenverbrauchs am Gesamtverbrauch',
  'Eigenverbrauch': 'Anteil der selbst genutzten PV-Erzeugung',
  'Eigenverbrauchsquote': 'Anteil der selbst genutzten PV-Erzeugung',
  'Zyklen/Jahr': 'Vollständige Lade-/Entladezyklen pro Jahr',
  'Wirkungsgrad': 'Verhältnis von Entladung zu Ladung (Effizienz)',
  'Netzlade-Anteil': 'Anteil der Speicherladung aus dem Netz statt PV',
  'JAZ': 'Jahresarbeitszahl: Wärmeenergie geteilt durch Stromverbrauch',
  'Stromverbrauch': 'Gesamter Stromverbrauch der Wärmepumpe',
  'Wärmeerzeugung': 'Erzeugte Wärme für Heizung und Warmwasser',
  'PV-Anteil': 'Anteil der Ladung aus PV-Überschuss',
  'Ladung': 'Gesamte Lademenge im Zeitraum',
  'Verbrauch': 'Durchschnittlicher Energieverbrauch',
  'Erzeugung': 'Gesamte PV-Erzeugung im Zeitraum',
}

function KPIRow({
  label,
  kpi,
  einheit,
  hideComparison,
  invertColors,
  tooltip,
}: {
  label: string
  kpi?: KPIVergleich | null
  einheit: string
  hideComparison?: boolean
  invertColors?: boolean
  tooltip?: string
}) {
  if (!kpi) return null

  const hasComparison = !hideComparison && kpi.community_avg !== undefined && kpi.community_avg !== null
  const abweichung = hasComparison ? ((kpi.wert - kpi.community_avg!) / kpi.community_avg!) * 100 : null

  // Bei invertColors ist weniger besser (z.B. Netzladung, Verbrauch)
  const isPositive = abweichung !== null ? (invertColors ? abweichung < 0 : abweichung > 0) : null

  // Tooltip aus KPI_TOOLTIPS oder explizit übergeben
  const tooltipText = tooltip || KPI_TOOLTIPS[label]

  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <span className="text-gray-600 dark:text-gray-400 flex items-center gap-1">
        {label}
        {tooltipText && (
          <SimpleTooltip text={tooltipText}>
            <HelpCircle className="h-3.5 w-3.5 text-gray-400 opacity-60" />
          </SimpleTooltip>
        )}
      </span>
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

// Achievement-Badge Komponente
function AchievementBadge({ achievement }: { achievement: Achievement }) {
  const colorClasses: Record<string, { bg: string; border: string; icon: string; text: string }> = {
    yellow: {
      bg: achievement.erreicht ? 'bg-yellow-100 dark:bg-yellow-900/30' : 'bg-gray-100 dark:bg-gray-800',
      border: achievement.erreicht ? 'border-yellow-300 dark:border-yellow-700' : 'border-gray-200 dark:border-gray-700',
      icon: achievement.erreicht ? 'text-yellow-500' : 'text-gray-400',
      text: achievement.erreicht ? 'text-yellow-700 dark:text-yellow-300' : 'text-gray-500',
    },
    green: {
      bg: achievement.erreicht ? 'bg-green-100 dark:bg-green-900/30' : 'bg-gray-100 dark:bg-gray-800',
      border: achievement.erreicht ? 'border-green-300 dark:border-green-700' : 'border-gray-200 dark:border-gray-700',
      icon: achievement.erreicht ? 'text-green-500' : 'text-gray-400',
      text: achievement.erreicht ? 'text-green-700 dark:text-green-300' : 'text-gray-500',
    },
    emerald: {
      bg: achievement.erreicht ? 'bg-emerald-100 dark:bg-emerald-900/30' : 'bg-gray-100 dark:bg-gray-800',
      border: achievement.erreicht ? 'border-emerald-300 dark:border-emerald-700' : 'border-gray-200 dark:border-gray-700',
      icon: achievement.erreicht ? 'text-emerald-500' : 'text-gray-400',
      text: achievement.erreicht ? 'text-emerald-700 dark:text-emerald-300' : 'text-gray-500',
    },
    blue: {
      bg: achievement.erreicht ? 'bg-blue-100 dark:bg-blue-900/30' : 'bg-gray-100 dark:bg-gray-800',
      border: achievement.erreicht ? 'border-blue-300 dark:border-blue-700' : 'border-gray-200 dark:border-gray-700',
      icon: achievement.erreicht ? 'text-blue-500' : 'text-gray-400',
      text: achievement.erreicht ? 'text-blue-700 dark:text-blue-300' : 'text-gray-500',
    },
    purple: {
      bg: achievement.erreicht ? 'bg-purple-100 dark:bg-purple-900/30' : 'bg-gray-100 dark:bg-gray-800',
      border: achievement.erreicht ? 'border-purple-300 dark:border-purple-700' : 'border-gray-200 dark:border-gray-700',
      icon: achievement.erreicht ? 'text-purple-500' : 'text-gray-400',
      text: achievement.erreicht ? 'text-purple-700 dark:text-purple-300' : 'text-gray-500',
    },
    cyan: {
      bg: achievement.erreicht ? 'bg-cyan-100 dark:bg-cyan-900/30' : 'bg-gray-100 dark:bg-gray-800',
      border: achievement.erreicht ? 'border-cyan-300 dark:border-cyan-700' : 'border-gray-200 dark:border-gray-700',
      icon: achievement.erreicht ? 'text-cyan-500' : 'text-gray-400',
      text: achievement.erreicht ? 'text-cyan-700 dark:text-cyan-300' : 'text-gray-500',
    },
    orange: {
      bg: achievement.erreicht ? 'bg-orange-100 dark:bg-orange-900/30' : 'bg-gray-100 dark:bg-gray-800',
      border: achievement.erreicht ? 'border-orange-300 dark:border-orange-700' : 'border-gray-200 dark:border-gray-700',
      icon: achievement.erreicht ? 'text-orange-500' : 'text-gray-400',
      text: achievement.erreicht ? 'text-orange-700 dark:text-orange-300' : 'text-gray-500',
    },
    indigo: {
      bg: achievement.erreicht ? 'bg-indigo-100 dark:bg-indigo-900/30' : 'bg-gray-100 dark:bg-gray-800',
      border: achievement.erreicht ? 'border-indigo-300 dark:border-indigo-700' : 'border-gray-200 dark:border-gray-700',
      icon: achievement.erreicht ? 'text-indigo-500' : 'text-gray-400',
      text: achievement.erreicht ? 'text-indigo-700 dark:text-indigo-300' : 'text-gray-500',
    },
  }

  const colors = colorClasses[achievement.farbe] || colorClasses.yellow

  return (
    <div
      className={`relative rounded-xl p-3 border ${colors.bg} ${colors.border} ${
        achievement.erreicht ? '' : 'opacity-70'
      }`}
      title={achievement.beschreibung}
    >
      <div className="flex items-center gap-2 mb-1">
        <div className={colors.icon}>{achievement.icon}</div>
        <span className={`text-sm font-medium ${colors.text}`}>{achievement.name}</span>
      </div>
      <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
        {achievement.beschreibung}
      </p>

      {/* Fortschrittsbalken für nicht erreichte */}
      {!achievement.erreicht && achievement.fortschritt !== undefined && (
        <div className="mt-2">
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
            <div
              className={`h-1.5 rounded-full ${
                achievement.farbe === 'yellow' ? 'bg-yellow-400' :
                achievement.farbe === 'green' ? 'bg-green-400' :
                achievement.farbe === 'blue' ? 'bg-blue-400' :
                achievement.farbe === 'purple' ? 'bg-purple-400' :
                achievement.farbe === 'cyan' ? 'bg-cyan-400' :
                achievement.farbe === 'orange' ? 'bg-orange-400' :
                'bg-gray-400'
              }`}
              style={{ width: `${Math.min(100, Math.max(0, achievement.fortschritt))}%` }}
            />
          </div>
          <p className="text-xs text-gray-400 mt-1">
            {achievement.fortschritt.toFixed(0)}%
          </p>
        </div>
      )}

      {/* Checkmark für erreichte */}
      {achievement.erreicht && (
        <div className="absolute top-2 right-2">
          <Medal className={`h-4 w-4 ${colors.icon}`} />
        </div>
      )}
    </div>
  )
}