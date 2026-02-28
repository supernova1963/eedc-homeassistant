/**
 * Community Komponenten Tab
 *
 * Deep-Dives für einzelne Komponenten:
 * - Speicher: Zyklen, Wirkungsgrad, Ladestrategie
 * - Wärmepumpe: JAZ, Effizienz, Klimazone
 * - E-Auto: PV-Anteil, Verbrauch, V2H
 * - Wallbox: Ladeverhalten, PV-optimiert
 * - Balkonkraftwerk: Ertrag, Eigenverbrauch
 *
 * Jede Komponente zeigt:
 * - Deine Werte vs. Community-Durchschnitt
 * - Rang innerhalb der Kategorie
 * - Tipps zur Optimierung
 */

import { useState, useEffect, useMemo } from 'react'
import {
  Battery,
  Home,
  Car,
  Plug,
  Sun,
  TrendingUp,
  TrendingDown,
  Award,
  Lightbulb,
  BarChart3,
  Zap,
  Gauge,
  BatteryCharging,
  Thermometer,
  Route,
  Users,
  MapPin,
} from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import { communityApi } from '../../api'
import type {
  CommunityBenchmarkResponse,
  ZeitraumTyp,
  KPIVergleich,
  SpeicherByClass,
  WPByRegion,
  EAutoByUsage,
} from '../../api/community'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
  LabelList,
} from 'recharts'

interface KomponentenTabProps {
  anlageId: number
  zeitraum: ZeitraumTyp
}

export default function KomponentenTab({ anlageId, zeitraum }: KomponentenTabProps) {
  const [benchmark, setBenchmark] = useState<CommunityBenchmarkResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Community Deep-Dive Daten
  const [speicherByClass, setSpeicherByClass] = useState<SpeicherByClass | null>(null)
  const [wpByRegion, setWpByRegion] = useState<WPByRegion | null>(null)
  const [eautoByUsage, setEautoByUsage] = useState<EAutoByUsage | null>(null)

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

  // Deep-Dive Statistiken laden (unabhängig vom Zeitraum)
  useEffect(() => {
    const loadDeepDive = async () => {
      try {
        const [speicher, wp, eauto] = await Promise.all([
          communityApi.getSpeicherByClass().catch(() => null),
          communityApi.getWaermepumpeByRegion().catch(() => null),
          communityApi.getEAutoByUsage().catch(() => null),
        ])
        setSpeicherByClass(speicher)
        setWpByRegion(wp)
        setEautoByUsage(eauto)
      } catch {
        // Ignoriere Fehler bei Deep-Dive-Daten
      }
    }

    loadDeepDive()
  }, [])

  // Verfügbare Komponenten ermitteln
  const verfuegbareKomponenten = useMemo(() => {
    if (!benchmark) return []

    const komponenten: string[] = []

    if (benchmark.anlage.speicher_kwh && benchmark.benchmark_erweitert?.speicher) {
      komponenten.push('speicher')
    }
    if (benchmark.anlage.hat_waermepumpe && benchmark.benchmark_erweitert?.waermepumpe) {
      komponenten.push('waermepumpe')
    }
    if (benchmark.anlage.hat_eauto && benchmark.benchmark_erweitert?.eauto) {
      komponenten.push('eauto')
    }
    if (benchmark.anlage.hat_wallbox && benchmark.benchmark_erweitert?.wallbox) {
      komponenten.push('wallbox')
    }
    if (benchmark.anlage.hat_balkonkraftwerk && benchmark.benchmark_erweitert?.balkonkraftwerk) {
      komponenten.push('bkw')
    }

    return komponenten
  }, [benchmark])

  if (loading) {
    return <LoadingSpinner text="Lade Komponenten-Daten..." />
  }

  if (error) {
    // Bei "letzter Monat" ohne Daten freundlichere Meldung
    if (zeitraum === 'letzter_monat') {
      return (
        <Card>
          <div className="text-center py-8">
            <Battery className="h-12 w-12 text-gray-300 mx-auto mb-3" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              Keine Daten für letzten Monat
            </h3>
            <p className="text-gray-500 dark:text-gray-400">
              Für den letzten Monat liegen noch keine Komponenten-Daten vor.
              Wähle einen längeren Zeitraum für den Vergleich.
            </p>
          </div>
        </Card>
      )
    }
    return <Alert type="error">{error}</Alert>
  }

  if (!benchmark) {
    return null
  }

  if (verfuegbareKomponenten.length === 0) {
    return (
      <Card>
        <div className="text-center py-12">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-100 dark:bg-gray-800 mb-4">
            <Battery className="h-8 w-8 text-gray-400" />
          </div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-3">
            Keine Komponenten-Daten
          </h2>
          <p className="text-gray-600 dark:text-gray-400 max-w-md mx-auto">
            Für Komponenten-Vergleiche benötigst du mindestens eine Zusatzkomponente
            (Speicher, Wärmepumpe, E-Auto, Wallbox oder Balkonkraftwerk) mit erfassten Monatsdaten.
          </p>
        </div>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {/* Zeitraum-Hinweis */}
      <div className="flex items-center justify-end">
        <span className="text-sm text-gray-500 dark:text-gray-400">
          Betrachtungszeitraum: {benchmark.zeitraum_label}
        </span>
      </div>

      {/* Speicher Deep-Dive */}
      {verfuegbareKomponenten.includes('speicher') && (
        <SpeicherDeepDive
          benchmark={benchmark}
          communityStats={speicherByClass}
        />
      )}

      {/* Wärmepumpe Deep-Dive */}
      {verfuegbareKomponenten.includes('waermepumpe') && (
        <WaermepumpeDeepDive
          benchmark={benchmark}
          communityStats={wpByRegion}
        />
      )}

      {/* E-Auto Deep-Dive */}
      {verfuegbareKomponenten.includes('eauto') && (
        <EAutoDeepDive
          benchmark={benchmark}
          communityStats={eautoByUsage}
        />
      )}

      {/* Wallbox Deep-Dive */}
      {verfuegbareKomponenten.includes('wallbox') && (
        <WallboxDeepDive
          benchmark={benchmark}
        />
      )}

      {/* Balkonkraftwerk Deep-Dive */}
      {verfuegbareKomponenten.includes('bkw') && (
        <BKWDeepDive
          benchmark={benchmark}
        />
      )}
    </div>
  )
}

// =============================================================================
// Speicher Deep-Dive
// =============================================================================

// Farben für Speicherklassen
const SPEICHER_COLORS = ['#22c55e', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6']

function SpeicherDeepDive({
  benchmark,
  communityStats,
}: {
  benchmark: CommunityBenchmarkResponse
  communityStats: SpeicherByClass | null
}) {
  const speicher = benchmark.benchmark_erweitert?.speicher
  if (!speicher) return null

  const kapazitaet = benchmark.anlage.speicher_kwh || 0

  // Eigene Kapazitätsklasse ermitteln
  const eigeneKlasse = useMemo(() => {
    if (kapazitaet <= 5) return '≤5 kWh'
    if (kapazitaet <= 10) return '5-10 kWh'
    if (kapazitaet <= 15) return '10-15 kWh'
    if (kapazitaet <= 20) return '15-20 kWh'
    return '>20 kWh'
  }, [kapazitaet])

  // Chart-Daten für Vergleich
  const vergleichsData = useMemo(() => {
    const data: { name: string; du: number; community: number }[] = []

    if (speicher.wirkungsgrad?.community_avg) {
      data.push({
        name: 'Wirkungsgrad',
        du: speicher.wirkungsgrad.wert,
        community: speicher.wirkungsgrad.community_avg,
      })
    }

    if (speicher.netz_anteil?.community_avg) {
      data.push({
        name: 'Netz-Anteil',
        du: speicher.netz_anteil.wert,
        community: speicher.netz_anteil.community_avg,
      })
    }

    return data
  }, [speicher])

  // Community-Verteilung nach Kapazitätsklasse
  const klassenData = useMemo(() => {
    if (!communityStats?.klassen) return []
    // Nur Klassen mit mindestens einer Anlage anzeigen
    return communityStats.klassen
      .filter((k) => k.anzahl > 0)
      .map((k, i) => {
        // Klassen-Label aus von_kwh/bis_kwh erzeugen
        const label = k.bis_kwh
          ? `${k.von_kwh}-${k.bis_kwh} kWh`
          : `>${k.von_kwh} kWh`
        return {
          name: label,
          anzahl: k.anzahl,
          fill: SPEICHER_COLORS[i % SPEICHER_COLORS.length],
          avg_zyklen: k.durchschnitt_zyklen ?? 0,
          avg_wirkungsgrad: k.durchschnitt_wirkungsgrad ?? 0,
        }
      })
  }, [communityStats])

  // Gesamtanzahl berechnen
  const gesamtAnzahl = useMemo(() => {
    if (!communityStats?.klassen) return 0
    return communityStats.klassen.reduce((sum, k) => sum + k.anzahl, 0)
  }, [communityStats])

  // Tipps generieren
  const tipps = useMemo(() => {
    const tips: string[] = []

    if (speicher.netz_anteil && speicher.netz_anteil.wert > 20) {
      tips.push('Hoher Netzlade-Anteil: Prüfe, ob die PV-Überschussladung optimal konfiguriert ist.')
    }

    if (speicher.wirkungsgrad && speicher.wirkungsgrad.wert < 85) {
      tips.push('Der Wirkungsgrad liegt unter 85%. Bei älteren Speichern kann die Kapazität nachlassen.')
    }

    if (speicher.zyklen_jahr && speicher.zyklen_jahr.wert < 200) {
      tips.push('Wenige Zyklen: Der Speicher wird nicht voll genutzt. Überlege, mehr Eigenverbrauch zu priorisieren.')
    }

    if (tips.length === 0) {
      tips.push('Dein Speicher arbeitet im normalen Bereich.')
    }

    return tips
  }, [speicher])

  return (
    <Card>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-green-100 dark:bg-green-900/30">
            <Battery className="h-6 w-6 text-green-500" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Speicher
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {kapazitaet} kWh Kapazität
            </p>
          </div>
        </div>
        {speicher.zyklen_jahr?.rang && speicher.zyklen_jahr.von && (
          <RangBadge rang={speicher.zyklen_jahr.rang} von={speicher.zyklen_jahr.von} />
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* KPI-Übersicht */}
        <div className="space-y-4">
          <KPICard
            label="Zyklen/Jahr"
            icon={<BatteryCharging className="h-5 w-5 text-green-500" />}
            kpi={speicher.zyklen_jahr}
            einheit=""
            beschreibung="Vollständige Lade-/Entladezyklen"
          />
          <KPICard
            label="Wirkungsgrad"
            icon={<Gauge className="h-5 w-5 text-blue-500" />}
            kpi={speicher.wirkungsgrad}
            einheit="%"
            beschreibung="Entladen / Geladen"
          />
          <KPICard
            label="Netzlade-Anteil"
            icon={<Zap className="h-5 w-5 text-yellow-500" />}
            kpi={speicher.netz_anteil}
            einheit="%"
            beschreibung="Anteil Ladung aus Netz statt PV"
            invertColors
          />
        </div>

        {/* Vergleichs-Chart */}
        {vergleichsData.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              Vergleich mit Community
            </h4>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={vergleichsData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} tick={{ fill: '#6b7280', fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" tick={{ fill: '#6b7280', fontSize: 12 }} width={90} />
                  <Tooltip
                    formatter={(value: number) => [`${value.toFixed(1)}%`, '']}
                    contentStyle={{
                      background: 'rgba(255,255,255,0.95)',
                      border: '1px solid #e5e7eb',
                      borderRadius: '8px',
                    }}
                  />
                  <Bar dataKey="du" name="Du" fill="#22c55e" radius={[0, 4, 4, 0]} />
                  <Bar dataKey="community" name="Community" fill="#9ca3af" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="flex items-center justify-center gap-6 mt-2 text-xs">
              <div className="flex items-center gap-1">
                <div className="w-3 h-3 bg-green-500 rounded" />
                <span className="text-gray-500">Du</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-3 h-3 bg-gray-400 rounded" />
                <span className="text-gray-500">Community Ø</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Community Speicher-Verteilung */}
      {klassenData.length > 0 && (
        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 mb-4">
            <Users className="h-5 w-5 text-gray-500" />
            <h4 className="font-medium text-gray-700 dark:text-gray-300">
              Community: Speicher nach Kapazitätsklasse
            </h4>
            <span className="text-xs text-gray-400">
              ({gesamtAnzahl} Anlagen)
            </span>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Pie Chart */}
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={klassenData}
                    dataKey="anzahl"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={70}
                    label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                    labelLine={false}
                  >
                    {klassenData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={entry.fill}
                        stroke={entry.name === eigeneKlasse ? '#000' : 'none'}
                        strokeWidth={entry.name === eigeneKlasse ? 2 : 0}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number, name: string) => [
                      `${value} Anlagen`,
                      name,
                    ]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            {/* Tabelle mit Details */}
            <div className="text-sm">
              <table className="w-full">
                <thead>
                  <tr className="text-gray-500 dark:text-gray-400">
                    <th className="text-left pb-2">Klasse</th>
                    <th className="text-right pb-2">Ø Zyklen/Jahr</th>
                    <th className="text-right pb-2">Ø Wirkungsgrad</th>
                  </tr>
                </thead>
                <tbody>
                  {klassenData.map((k) => (
                    <tr
                      key={k.name}
                      className={k.name === eigeneKlasse ? 'bg-primary-50 dark:bg-primary-900/20 font-medium' : ''}
                    >
                      <td className="py-1 flex items-center gap-2">
                        <div className="w-3 h-3 rounded" style={{ backgroundColor: k.fill }} />
                        {k.name}
                        {k.name === eigeneKlasse && <span className="text-xs text-primary-500">(Du)</span>}
                      </td>
                      <td className="text-right py-1">{k.avg_zyklen.toFixed(0)}</td>
                      <td className="text-right py-1">{k.avg_wirkungsgrad.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tipps */}
      <TippsSection tipps={tipps} />
    </Card>
  )
}

// =============================================================================
// Wärmepumpe Deep-Dive
// =============================================================================

function WaermepumpeDeepDive({
  benchmark,
  communityStats,
}: {
  benchmark: CommunityBenchmarkResponse
  communityStats: WPByRegion | null
}) {
  const wp = benchmark.benchmark_erweitert?.waermepumpe
  if (!wp) return null

  const eigeneRegion = benchmark.anlage.region

  // Community-Daten nach Region
  const regionData = useMemo(() => {
    if (!communityStats?.regionen) return []
    return communityStats.regionen
      .filter((r) => r.anzahl > 0 && r.durchschnitt_jaz != null)
      .sort((a, b) => (b.durchschnitt_jaz ?? 0) - (a.durchschnitt_jaz ?? 0))
      .slice(0, 10)
      .map((r) => ({
        name: r.region.replace('_', ' '),
        region: r.region,
        jaz: r.durchschnitt_jaz ?? 0,
        anzahl: r.anzahl,
      }))
  }, [communityStats])

  // Gesamtanzahl
  const gesamtAnzahlWP = useMemo(() => {
    if (!communityStats?.regionen) return 0
    return communityStats.regionen.reduce((sum, r) => sum + r.anzahl, 0)
  }, [communityStats])

  // Tipps generieren - berücksichtigt Community-Größe
  const tipps = useMemo(() => {
    const tips: string[] = []

    if (wp.jaz && wp.jaz.wert < 3.0) {
      tips.push('JAZ unter 3.0: Prüfe Vorlauftemperaturen und Wärmedämmung. Höhere Temperaturen senken die Effizienz.')
    }

    // Nur Community-Vergleich wenn genug Anlagen vorhanden
    if (gesamtAnzahlWP >= 3 && wp.jaz && wp.jaz.community_avg && wp.jaz.wert < wp.jaz.community_avg * 0.9) {
      tips.push('Deine JAZ liegt deutlich unter dem Community-Durchschnitt. Eine Optimierung der Heizkurve könnte helfen.')
    }

    if (tips.length === 0 && wp.jaz && wp.jaz.wert >= 3.5) {
      // Absolute Bewertung statt Vergleich bei wenig Daten
      tips.push('Gute Effizienz! Eine JAZ von 3.5+ ist ein solider Wert für Wärmepumpen.')
    } else if (tips.length === 0) {
      tips.push('Deine Wärmepumpe arbeitet im normalen Effizienzbereich.')
    }

    return tips
  }, [wp, gesamtAnzahlWP])

  return (
    <Card>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30">
            <Home className="h-6 w-6 text-blue-500" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Wärmepumpe
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Effizienz-Analyse
            </p>
          </div>
        </div>
        {wp.jaz?.rang && wp.jaz.von && (
          <RangBadge rang={wp.jaz.rang} von={wp.jaz.von} />
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KPICard
          label="Jahresarbeitszahl (JAZ)"
          icon={<Thermometer className="h-5 w-5 text-blue-500" />}
          kpi={wp.jaz}
          einheit=""
          beschreibung="Wärmeenergie / Stromverbrauch"
          large
        />
        <KPICard
          label="Stromverbrauch"
          icon={<Zap className="h-5 w-5 text-yellow-500" />}
          kpi={wp.stromverbrauch}
          einheit="kWh"
          beschreibung="Gesamt im Zeitraum"
        />
        <KPICard
          label="Wärmeerzeugung"
          icon={<Home className="h-5 w-5 text-red-500" />}
          kpi={wp.waermeerzeugung}
          einheit="kWh"
          beschreibung="Heizung + Warmwasser"
        />
      </div>

      {/* Community Wärmepumpen nach Region - nur bei mehreren Regionen sinnvoll */}
      {regionData.length > 0 && (
        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 mb-4">
            <MapPin className="h-5 w-5 text-gray-500" />
            <h4 className="font-medium text-gray-700 dark:text-gray-300">
              Community: JAZ nach Region
            </h4>
            <span className="text-xs text-gray-400">
              ({gesamtAnzahlWP} {gesamtAnzahlWP === 1 ? 'Anlage' : 'Anlagen'})
            </span>
          </div>
          {gesamtAnzahlWP < 3 ? (
            // Bei weniger als 3 Anlagen: Hinweis statt Chart
            <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
              <p className="text-sm text-blue-700 dark:text-blue-300">
                <strong>Noch nicht genug Vergleichsdaten.</strong> Für einen aussagekräftigen
                regionalen Vergleich werden mindestens 3 Anlagen mit Wärmepumpe benötigt.
              </p>
              {regionData.length === 1 && (
                <p className="text-sm text-blue-600 dark:text-blue-400 mt-2">
                  Aktuell: {regionData[0].name} mit JAZ {regionData[0].jaz.toFixed(2)} ({regionData[0].anzahl} Anlage)
                </p>
              )}
            </div>
          ) : (
            <>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={regionData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
                    <XAxis type="number" domain={[0, 5]} tick={{ fill: '#6b7280', fontSize: 11 }} />
                    <YAxis
                      type="category"
                      dataKey="name"
                      tick={{ fill: '#6b7280', fontSize: 11 }}
                      width={120}
                    />
                    <Tooltip
                      formatter={(value: number) => [`JAZ: ${value.toFixed(2)}`, '']}
                      contentStyle={{
                        background: 'rgba(255,255,255,0.95)',
                        border: '1px solid #e5e7eb',
                        borderRadius: '8px',
                      }}
                    />
                    <Bar dataKey="jaz" radius={[0, 4, 4, 0]}>
                      {regionData.map((entry, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={entry.region === eigeneRegion ? '#3b82f6' : '#9ca3af'}
                        />
                      ))}
                      <LabelList
                        dataKey="jaz"
                        position="right"
                        formatter={(value: number) => value.toFixed(2)}
                        style={{ fill: '#374151', fontSize: 11 }}
                      />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="flex items-center justify-center gap-6 mt-2 text-xs">
                <div className="flex items-center gap-1">
                  <div className="w-3 h-3 bg-blue-500 rounded" />
                  <span className="text-gray-500">Deine Region</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-3 h-3 bg-gray-400 rounded" />
                  <span className="text-gray-500">Andere Regionen</span>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Tipps */}
      <TippsSection tipps={tipps} />
    </Card>
  )
}

// =============================================================================
// E-Auto Deep-Dive
// =============================================================================

// Farben für E-Auto Nutzungsklassen
const EAUTO_COLORS = ['#22c55e', '#3b82f6', '#f59e0b', '#ef4444']

function EAutoDeepDive({
  benchmark,
  communityStats,
}: {
  benchmark: CommunityBenchmarkResponse
  communityStats: EAutoByUsage | null
}) {
  const eauto = benchmark.benchmark_erweitert?.eauto
  if (!eauto) return null

  // Eigene Nutzungsklasse ermitteln (basierend auf km)
  const eigeneKlasse = useMemo(() => {
    if (!eauto.km?.wert) return null
    const kmMonat = eauto.km.wert / 12 // Grobe Schätzung wenn Jahreswert
    if (kmMonat <= 500) return 'Wenig'
    if (kmMonat <= 1000) return 'Normal'
    if (kmMonat <= 2000) return 'Viel'
    return 'Intensiv'
  }, [eauto.km])

  // Community-Daten nach Nutzungsintensität
  const nutzungData = useMemo(() => {
    if (!communityStats?.klassen) return []
    return communityStats.klassen
      .filter((k) => k.anzahl > 0)
      .map((k, i) => ({
        name: k.klasse.charAt(0).toUpperCase() + k.klasse.slice(1), // Capitalize
        beschreibung: k.beschreibung,
        anzahl: k.anzahl,
        fill: EAUTO_COLORS[i % EAUTO_COLORS.length],
        avg_pv_anteil: k.durchschnitt_pv_anteil ?? 0,
        avg_verbrauch: k.durchschnitt_verbrauch_100km ?? 0,
      }))
  }, [communityStats])

  // Gesamtanzahl E-Autos
  const gesamtAnzahlEAuto = useMemo(() => {
    if (!communityStats?.klassen) return 0
    return communityStats.klassen.reduce((sum, k) => sum + k.anzahl, 0)
  }, [communityStats])

  // Chart-Daten für Ladequellen
  const ladequellenData = useMemo(() => {
    if (!eauto.pv_anteil) return []

    const pvAnteil = eauto.pv_anteil.wert
    return [
      { name: 'PV', wert: pvAnteil, fill: '#22c55e' },
      { name: 'Netz/Extern', wert: 100 - pvAnteil, fill: '#ef4444' },
    ]
  }, [eauto])

  // Tipps generieren
  const tipps = useMemo(() => {
    const tips: string[] = []

    if (eauto.pv_anteil && eauto.pv_anteil.wert < 50) {
      tips.push('Unter 50% PV-Anteil: Versuche, das Laden tagsüber bei PV-Überschuss zu priorisieren.')
    }

    if (eauto.verbrauch_100km && eauto.verbrauch_100km.wert > 20) {
      tips.push('Hoher Verbrauch: Prüfe Reifendruck, Fahrweise und Klimaanlagen-Nutzung.')
    }

    if (eauto.v2h && eauto.v2h.wert > 0) {
      tips.push('V2H aktiv: Du nutzt dein Auto als zusätzlichen Speicher - sehr gut!')
    }

    if (tips.length === 0) {
      tips.push('Dein E-Auto ist gut in das Energiesystem integriert.')
    }

    return tips
  }, [eauto])

  return (
    <Card>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-purple-100 dark:bg-purple-900/30">
            <Car className="h-6 w-6 text-purple-500" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              E-Auto
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Lade- und Verbrauchsanalyse
            </p>
          </div>
        </div>
        {eauto.pv_anteil?.rang && eauto.pv_anteil.von && (
          <RangBadge rang={eauto.pv_anteil.rang} von={eauto.pv_anteil.von} />
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* KPIs */}
        <div className="space-y-4">
          <KPICard
            label="PV-Ladeanteil"
            icon={<Sun className="h-5 w-5 text-yellow-500" />}
            kpi={eauto.pv_anteil}
            einheit="%"
            beschreibung="Anteil PV an Gesamtladung"
          />
          <KPICard
            label="Ladung gesamt"
            icon={<BatteryCharging className="h-5 w-5 text-purple-500" />}
            kpi={eauto.ladung_gesamt}
            einheit="kWh"
            beschreibung="Gesamte Lademenge"
          />
          <KPICard
            label="Verbrauch"
            icon={<Gauge className="h-5 w-5 text-blue-500" />}
            kpi={eauto.verbrauch_100km}
            einheit="kWh/100km"
            beschreibung="Durchschnittsverbrauch"
            invertColors
          />
          {eauto.km && (
            <KPICard
              label="Gefahrene km"
              icon={<Route className="h-5 w-5 text-gray-500" />}
              kpi={eauto.km}
              einheit="km"
              beschreibung="Im Zeitraum"
            />
          )}
          {eauto.v2h && eauto.v2h.wert > 0 && (
            <KPICard
              label="V2H Entladung"
              icon={<Zap className="h-5 w-5 text-green-500" />}
              kpi={eauto.v2h}
              einheit="kWh"
              beschreibung="Rückspeisung ins Haus"
            />
          )}
        </div>

        {/* Ladequellen-Verteilung */}
        {ladequellenData.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              Ladequellen-Verteilung
            </h4>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={ladequellenData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} tick={{ fill: '#6b7280', fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" tick={{ fill: '#6b7280', fontSize: 12 }} width={80} />
                  <Tooltip
                    formatter={(value: number) => [`${value.toFixed(1)}%`, '']}
                    contentStyle={{
                      background: 'rgba(255,255,255,0.95)',
                      border: '1px solid #e5e7eb',
                      borderRadius: '8px',
                    }}
                  />
                  <Bar dataKey="wert" radius={[0, 4, 4, 0]}>
                    {ladequellenData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>

      {/* Community E-Auto nach Nutzungsintensität */}
      {nutzungData.length > 0 && (
        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 mb-4">
            <Users className="h-5 w-5 text-gray-500" />
            <h4 className="font-medium text-gray-700 dark:text-gray-300">
              Community: E-Autos nach Nutzungsintensität
            </h4>
            <span className="text-xs text-gray-400">
              ({gesamtAnzahlEAuto} E-Autos)
            </span>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Pie Chart */}
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={nutzungData}
                    dataKey="anzahl"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={70}
                    label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                    labelLine={false}
                  >
                    {nutzungData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={entry.fill}
                        stroke={entry.name.toLowerCase() === eigeneKlasse?.toLowerCase() ? '#000' : 'none'}
                        strokeWidth={entry.name.toLowerCase() === eigeneKlasse?.toLowerCase() ? 2 : 0}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number, name: string) => [
                      `${value} E-Autos`,
                      name,
                    ]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            {/* Tabelle mit Details */}
            <div className="text-sm">
              <table className="w-full">
                <thead>
                  <tr className="text-gray-500 dark:text-gray-400">
                    <th className="text-left pb-2">Nutzung</th>
                    <th className="text-right pb-2">Ø Verbrauch</th>
                    <th className="text-right pb-2">Ø PV-Anteil</th>
                  </tr>
                </thead>
                <tbody>
                  {nutzungData.map((k) => (
                    <tr
                      key={k.name}
                      className={k.name.toLowerCase() === eigeneKlasse?.toLowerCase() ? 'bg-primary-50 dark:bg-primary-900/20 font-medium' : ''}
                    >
                      <td className="py-1 flex items-center gap-2">
                        <div className="w-3 h-3 rounded" style={{ backgroundColor: k.fill }} />
                        <span title={k.beschreibung}>{k.name}</span>
                        {k.name.toLowerCase() === eigeneKlasse?.toLowerCase() && <span className="text-xs text-primary-500">(Du)</span>}
                      </td>
                      <td className="text-right py-1">{k.avg_verbrauch.toFixed(1)} kWh/100km</td>
                      <td className="text-right py-1">{k.avg_pv_anteil.toFixed(0)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tipps */}
      <TippsSection tipps={tipps} />
    </Card>
  )
}

// =============================================================================
// Wallbox Deep-Dive
// =============================================================================

function WallboxDeepDive({ benchmark }: { benchmark: CommunityBenchmarkResponse }) {
  const wallbox = benchmark.benchmark_erweitert?.wallbox
  if (!wallbox) return null

  const leistung = benchmark.anlage.wallbox_kw

  // Tipps generieren
  const tipps = useMemo(() => {
    const tips: string[] = []

    if (wallbox.pv_anteil && wallbox.pv_anteil.wert < 60) {
      tips.push('Der PV-Anteil könnte höher sein. Nutze PV-geführtes Laden für mehr Eigenverbrauch.')
    }

    if (wallbox.pv_anteil && wallbox.pv_anteil.wert >= 80) {
      tips.push('Exzellenter PV-Anteil! Deine Wallbox ist optimal ins PV-System integriert.')
    }

    if (tips.length === 0) {
      tips.push('Deine Wallbox arbeitet im normalen Bereich.')
    }

    return tips
  }, [wallbox])

  return (
    <Card>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-cyan-100 dark:bg-cyan-900/30">
            <Plug className="h-6 w-6 text-cyan-500" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Wallbox
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {leistung ? `${leistung} kW Ladeleistung` : 'Ladeverhalten'}
            </p>
          </div>
        </div>
        {wallbox.pv_anteil?.rang && wallbox.pv_anteil.von && (
          <RangBadge rang={wallbox.pv_anteil.rang} von={wallbox.pv_anteil.von} />
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KPICard
          label="PV-Ladeanteil"
          icon={<Sun className="h-5 w-5 text-yellow-500" />}
          kpi={wallbox.pv_anteil}
          einheit="%"
          beschreibung="Anteil PV an Gesamtladung"
          large
        />
        <KPICard
          label="Ladung gesamt"
          icon={<Zap className="h-5 w-5 text-cyan-500" />}
          kpi={wallbox.ladung}
          einheit="kWh"
          beschreibung="Im Zeitraum"
        />
        <KPICard
          label="Ladevorgänge"
          icon={<BarChart3 className="h-5 w-5 text-gray-500" />}
          kpi={wallbox.ladevorgaenge}
          einheit=""
          beschreibung="Anzahl"
        />
      </div>

      {/* Tipps */}
      <TippsSection tipps={tipps} />
    </Card>
  )
}

// =============================================================================
// Balkonkraftwerk Deep-Dive
// =============================================================================

function BKWDeepDive({ benchmark }: { benchmark: CommunityBenchmarkResponse }) {
  const bkw = benchmark.benchmark_erweitert?.balkonkraftwerk
  if (!bkw) return null

  const leistung = benchmark.anlage.bkw_wp

  // Tipps generieren
  const tipps = useMemo(() => {
    const tips: string[] = []

    if (bkw.spez_ertrag && bkw.spez_ertrag.community_avg) {
      const abweichung = ((bkw.spez_ertrag.wert - bkw.spez_ertrag.community_avg) / bkw.spez_ertrag.community_avg) * 100
      if (abweichung < -15) {
        tips.push('Dein spezifischer Ertrag liegt deutlich unter dem Durchschnitt. Prüfe Verschattung und Ausrichtung.')
      }
    }

    if (bkw.eigenverbrauch && bkw.eigenverbrauch.wert < 70) {
      tips.push('Der Eigenverbrauchsanteil könnte höher sein. Versuche, Verbraucher tagsüber zu nutzen.')
    }

    if (tips.length === 0) {
      tips.push('Dein Balkonkraftwerk arbeitet gut!')
    }

    return tips
  }, [bkw])

  return (
    <Card>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-900/30">
            <Sun className="h-6 w-6 text-amber-500" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Balkonkraftwerk
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {leistung ? `${leistung} Wp` : 'Mini-PV'}
            </p>
          </div>
        </div>
        {bkw.spez_ertrag?.rang && bkw.spez_ertrag.von && (
          <RangBadge rang={bkw.spez_ertrag.rang} von={bkw.spez_ertrag.von} />
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KPICard
          label="Spezifischer Ertrag"
          icon={<TrendingUp className="h-5 w-5 text-amber-500" />}
          kpi={bkw.spez_ertrag}
          einheit="kWh/kWp"
          beschreibung="Normierter Ertrag"
          large
        />
        <KPICard
          label="Erzeugung"
          icon={<Zap className="h-5 w-5 text-yellow-500" />}
          kpi={bkw.erzeugung}
          einheit="kWh"
          beschreibung="Im Zeitraum"
        />
        <KPICard
          label="Eigenverbrauch"
          icon={<Home className="h-5 w-5 text-green-500" />}
          kpi={bkw.eigenverbrauch}
          einheit="%"
          beschreibung="Direkt genutzt"
        />
      </div>

      {/* Tipps */}
      <TippsSection tipps={tipps} />
    </Card>
  )
}

// =============================================================================
// Hilfskomponenten
// =============================================================================

function RangBadge({ rang, von }: { rang: number; von: number }) {
  const prozent = (rang / von) * 100

  let bgColor = 'bg-gray-100 dark:bg-gray-800'
  let textColor = 'text-gray-600 dark:text-gray-400'

  if (prozent <= 10) {
    bgColor = 'bg-yellow-100 dark:bg-yellow-900/30'
    textColor = 'text-yellow-600 dark:text-yellow-400'
  } else if (prozent <= 25) {
    bgColor = 'bg-blue-100 dark:bg-blue-900/30'
    textColor = 'text-blue-600 dark:text-blue-400'
  } else if (prozent <= 50) {
    bgColor = 'bg-green-100 dark:bg-green-900/30'
    textColor = 'text-green-600 dark:text-green-400'
  }

  return (
    <div className={`flex items-center gap-1 px-3 py-1 rounded-full ${bgColor}`}>
      <Award className={`h-4 w-4 ${textColor}`} />
      <span className={`text-sm font-medium ${textColor}`}>
        #{rang} von {von}
      </span>
    </div>
  )
}

function KPICard({
  label,
  icon,
  kpi,
  einheit,
  beschreibung,
  invertColors,
  large,
}: {
  label: string
  icon: React.ReactNode
  kpi?: KPIVergleich | null
  einheit: string
  beschreibung: string
  invertColors?: boolean
  large?: boolean
}) {
  if (!kpi) return null

  const hasComparison = kpi.community_avg !== undefined && kpi.community_avg !== null
  const abweichung = hasComparison ? ((kpi.wert - kpi.community_avg!) / kpi.community_avg!) * 100 : null
  const isPositive = abweichung !== null ? (invertColors ? abweichung < 0 : abweichung > 0) : null

  return (
    <div className={`bg-gray-50 dark:bg-gray-800 rounded-lg p-4 ${large ? 'md:col-span-1' : ''}`}>
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className={`font-bold text-gray-900 dark:text-white ${large ? 'text-3xl' : 'text-xl'}`}>
          {kpi.wert.toFixed(einheit === '%' ? 1 : einheit === '' ? 1 : 0)}
        </span>
        {einheit && (
          <span className="text-gray-500 dark:text-gray-400">{einheit}</span>
        )}
      </div>
      {hasComparison && abweichung !== null && (
        <div className={`flex items-center gap-1 mt-1 text-sm ${
          isPositive
            ? 'text-green-600 dark:text-green-400'
            : 'text-red-600 dark:text-red-400'
        }`}>
          {isPositive ? (
            <TrendingUp className="h-3 w-3" />
          ) : (
            <TrendingDown className="h-3 w-3" />
          )}
          <span>
            {abweichung >= 0 ? '+' : ''}{abweichung.toFixed(1)}% vs. Ø
          </span>
        </div>
      )}
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{beschreibung}</p>
    </div>
  )
}

function TippsSection({ tipps }: { tipps: string[] }) {
  return (
    <div className="mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
      <div className="flex items-center gap-2 mb-3">
        <Lightbulb className="h-5 w-5 text-yellow-500" />
        <span className="font-medium text-gray-700 dark:text-gray-300">Tipps</span>
      </div>
      <ul className="space-y-2">
        {tipps.map((tipp, idx) => (
          <li key={idx} className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400">
            <span className="text-primary-500 mt-0.5">•</span>
            <span>{tipp}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
