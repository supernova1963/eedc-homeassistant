/**
 * Community-Komponenten — geteilte Teile (Daten-Hook + Präsentations-Sektionen).
 * EINE Code-Wahrheit für IST (`KomponentenTab`) und IA-V4 (`CommunityKomponentenV4`).
 * Sektionen rendern den Body OHNE äußere Card UND ohne Card-Kopf
 * (Icon-Box + Titel + Untertitel + RangBadge) — den wickelt der Aufrufer
 * (IST = Card-Kopf, V4 = Block.title/summary/badge). Zahlen de-DE (`fmtZahl`),
 * Farben/Achsen aus der Zentrale.
 */
import { useEffect, useMemo, useState } from 'react'
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
import ChartTooltip from '../../components/ui/ChartTooltip'
import { Parkbar } from '../../components/park'
import { useChartTheme } from '../../context/ThemeContext'
import { SERIEN_PALETTE, EIGENE_SERIE_FARBEN, LADEQUELLEN_FARBEN, ACHSEN_TICK, fmtZahl } from '../../lib'
import { communityApi } from '../../api'
import type {
  CommunityBenchmarkResponse,
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
  Legend,
} from 'recharts'
import { useSchmaleAchse } from '../../hooks'

// ─── Daten-Hook (lädt Speicher-/WP-/E-Auto-Deep-Dive-Statistiken) ─────────────

export interface KomponentenDaten {
  speicherByClass: SpeicherByClass | null
  wpByRegion: WPByRegion | null
  eautoByUsage: EAutoByUsage | null
  verfuegbareKomponenten: string[]
  extraLoading: boolean
}

export function useKomponentenDaten(benchmark: CommunityBenchmarkResponse | null): KomponentenDaten {
  const [speicherByClass, setSpeicherByClass] = useState<SpeicherByClass | null>(null)
  const [wpByRegion, setWpByRegion] = useState<WPByRegion | null>(null)
  const [eautoByUsage, setEautoByUsage] = useState<EAutoByUsage | null>(null)
  const [extraLoading, setExtraLoading] = useState(false)

  // Deep-Dive Statistiken laden (unabhängig vom Zeitraum)
  useEffect(() => {
    let ab = false
    setExtraLoading(true)
    Promise.all([
      communityApi.getSpeicherByClass().catch(() => null),
      communityApi.getWaermepumpeByRegion().catch(() => null),
      communityApi.getEAutoByUsage().catch(() => null),
    ])
      .then(([speicher, wp, eauto]) => {
        if (!ab) {
          setSpeicherByClass(speicher)
          setWpByRegion(wp)
          setEautoByUsage(eauto)
        }
      })
      .finally(() => { if (!ab) setExtraLoading(false) })
    return () => { ab = true }
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

  return { speicherByClass, wpByRegion, eautoByUsage, verfuegbareKomponenten, extraLoading }
}

// =============================================================================
// Element-Park-IDs je Deep-Dive (Element-Park-Doktrin Gernot 2026-06-27)
// -----------------------------------------------------------------------------
// JEDE Anzeige (KPI-Karte, Chart, Pie, Tabelle, Tipps) ist einzeln parkbar; die
// `Parkbar`-Wrapper sitzen in den Deep-Dive-Sektionen (KPI-Karte: INNEN, nach dem
// `if(!kpi) return null`, damit kein leerer Div an datenloser Stelle steht).
// Da die KPI-/Chart-Präsenz DATENABHÄNGIG ist, liefern diese Funktionen GENAU die
// IDs, die die jeweilige Sektion tatsächlich rendert — gleiche Bedingungen wie die
// `CommunityVergleichsKPI`/Chart/Pie/Tabelle/Tipps-Zweige. Der V4-Builder nutzt sie
// für `alleGeparkt`: ein Block entfällt erst, wenn ALLE seine Element-IDs geparkt
// sind. Ohne ParkProvider sind die Wrapper inert → der IST-`KomponentenTab` bleibt
// optisch identisch.
// =============================================================================

export function speicherParkIds(
  benchmark: CommunityBenchmarkResponse,
  communityStats: SpeicherByClass | null,
): string[] {
  const speicher = benchmark.benchmark_erweitert?.speicher
  if (!speicher) return []
  const ids: string[] = []
  if (speicher.zyklen_jahr) ids.push('komp-speicher-kpi-zyklen')
  if (speicher.wirkungsgrad) ids.push('komp-speicher-kpi-wirkungsgrad')
  if (speicher.netz_anteil) ids.push('komp-speicher-kpi-netzanteil')
  // Vergleichs-Chart: rendert nur, wenn Wirkungsgrad ODER Netz-Anteil community_avg hat.
  if (speicher.wirkungsgrad?.community_avg || speicher.netz_anteil?.community_avg) {
    ids.push('komp-speicher-chart')
  }
  // Community-Verteilung (Pie + Tabelle): nur wenn Klassen mit Anlagen vorhanden.
  if (communityStats?.klassen?.some((k) => k.anzahl > 0)) {
    ids.push('komp-speicher-pie', 'komp-speicher-tabelle')
  }
  ids.push('komp-speicher-tipps')
  return ids
}

export function bkwParkIds(benchmark: CommunityBenchmarkResponse): string[] {
  const bkw = benchmark.benchmark_erweitert?.balkonkraftwerk
  if (!bkw) return []
  const ids: string[] = []
  if (bkw.spez_ertrag) ids.push('komp-bkw-kpi-spezertrag')
  if (bkw.erzeugung) ids.push('komp-bkw-kpi-erzeugung')
  if (bkw.eigenverbrauch) ids.push('komp-bkw-kpi-eigenverbrauch')
  ids.push('komp-bkw-tipps')
  return ids
}

export function waermepumpeParkIds(
  benchmark: CommunityBenchmarkResponse,
  communityStats: WPByRegion | null,
): string[] {
  const wp = benchmark.benchmark_erweitert?.waermepumpe
  if (!wp) return []
  const ids: string[] = []
  if (wp.jaz) ids.push('komp-wp-kpi-jaz')
  if (wp.stromverbrauch) ids.push('komp-wp-kpi-stromverbrauch')
  if (wp.waermeerzeugung) ids.push('komp-wp-kpi-waermeerzeugung')
  // JAZ-nach-Region-Block (Chart bzw. Hinweis-Box): nur wenn ≥1 Region mit JAZ.
  const regionVorhanden = communityStats?.regionen?.some(
    (r) => r.anzahl > 0 && r.durchschnitt_jaz != null,
  )
  if (regionVorhanden) ids.push('komp-wp-chart')
  ids.push('komp-wp-tipps')
  return ids
}

export function wallboxParkIds(benchmark: CommunityBenchmarkResponse): string[] {
  const wallbox = benchmark.benchmark_erweitert?.wallbox
  if (!wallbox) return []
  const ids: string[] = []
  if (wallbox.pv_anteil) ids.push('komp-wallbox-kpi-pvanteil')
  if (wallbox.ladung) ids.push('komp-wallbox-kpi-ladung')
  if (wallbox.ladevorgaenge) ids.push('komp-wallbox-kpi-ladevorgaenge')
  ids.push('komp-wallbox-tipps')
  return ids
}

export function eautoParkIds(
  benchmark: CommunityBenchmarkResponse,
  communityStats: EAutoByUsage | null,
): string[] {
  const eauto = benchmark.benchmark_erweitert?.eauto
  if (!eauto) return []
  const ids: string[] = []
  if (eauto.pv_anteil) ids.push('komp-eauto-kpi-pvanteil')
  if (eauto.ladung_gesamt) ids.push('komp-eauto-kpi-ladung')
  if (eauto.verbrauch_100km) ids.push('komp-eauto-kpi-verbrauch')
  if (eauto.km) ids.push('komp-eauto-kpi-km')
  if (eauto.v2h && eauto.v2h.wert > 0) ids.push('komp-eauto-kpi-v2h')
  // Ladequellen-Chart: nur wenn PV-Anteil bekannt.
  if (eauto.pv_anteil) ids.push('komp-eauto-chart')
  // Community-Verteilung (Pie + Tabelle): nur wenn Klassen mit Anlagen vorhanden.
  if (communityStats?.klassen?.some((k) => k.anzahl > 0)) {
    ids.push('komp-eauto-pie', 'komp-eauto-tabelle')
  }
  ids.push('komp-eauto-tipps')
  return ids
}

// =============================================================================
// Speicher Deep-Dive (Body ohne Card/Kopf)
// =============================================================================

export function SpeicherDeepDive({
  benchmark,
  communityStats,
}: {
  benchmark: CommunityBenchmarkResponse
  communityStats: SpeicherByClass | null
}) {
  const achsen = useChartTheme()
  const schmal = useSchmaleAchse()
  const speicher = benchmark.benchmark_erweitert?.speicher
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
    if (!speicher) return data

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
          fill: SERIEN_PALETTE[i % SERIEN_PALETTE.length],
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
    if (!speicher) return tips

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

  if (!speicher) return null

  return (
    <>
      {/* D13-5: KPIs als Kachelreihe (wie WP/Wallbox/BKW) statt gestapelter
          Spalte neben dem Chart — konsistentes V4-Muster, kein Leerraum. */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <CommunityVergleichsKPI
          label="Zyklen/Jahr"
          icon={<BatteryCharging className="h-5 w-5 text-green-500" />}
          kpi={speicher.zyklen_jahr}
          einheit=""
          beschreibung="Vollständige Lade-/Entladezyklen"
          parkId="komp-speicher-kpi-zyklen"
          parkTitel="Speicher · Zyklen/Jahr"
        />
        <CommunityVergleichsKPI
          label="Wirkungsgrad"
          icon={<Gauge className="h-5 w-5 text-blue-500" />}
          kpi={speicher.wirkungsgrad}
          einheit="%"
          beschreibung="Entladen / Geladen"
          parkId="komp-speicher-kpi-wirkungsgrad"
          parkTitel="Speicher · Wirkungsgrad"
        />
        <CommunityVergleichsKPI
          label="Netzlade-Anteil"
          icon={<Zap className="h-5 w-5 text-yellow-500" />}
          kpi={speicher.netz_anteil}
          einheit="%"
          beschreibung="Anteil Ladung aus Netz statt PV"
          invertColors
          parkId="komp-speicher-kpi-netzanteil"
          parkTitel="Speicher · Netzlade-Anteil"
        />
      </div>

      {/* Vergleichs-Chart (Full-Width unter den KPIs) */}
      {vergleichsData.length > 0 && (
        <Parkbar id="komp-speicher-chart" titel="Speicher · Vergleich mit Community">
          <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              Vergleich mit Community
            </h4>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={vergleichsData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} tick={ACHSEN_TICK} tickFormatter={(v) => `${fmtZahl(v, 0)} %`} /* achsen-allow: Wert-Achse waagerecht, Einheit/Format pro Tick (de-DE) */ />
                  <YAxis type="category" dataKey="name" tick={ACHSEN_TICK} width={90} /* achsen-allow: Kategorie-Namen */ />
                  <Tooltip content={<ChartTooltip unit="%" decimals={1} />} />
                  <Bar dataKey="du" name="Du" fill={EIGENE_SERIE_FARBEN.du} radius={[0, 2, 2, 0]} />
                  <Bar dataKey="community" name="Community" fill={achsen.referenz} radius={[0, 2, 2, 0]} />
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
        </Parkbar>
      )}

      {/* Community Speicher-Verteilung */}
      {klassenData.length > 0 && (
        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 mb-4">
            <Users className="h-5 w-5 text-gray-500" />
            <h4 className="font-medium text-gray-700 dark:text-gray-300">
              Community: Speicher nach Kapazitätsklasse
            </h4>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              ({fmtZahl(gesamtAnzahl, 0)} Anlagen)
            </span>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Pie Chart */}
            <Parkbar id="komp-speicher-pie" titel="Speicher · Verteilung (Diagramm)">
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
                    label={schmal ? undefined : ({ name, percent }) => `${name} (${fmtZahl(percent * 100, 0)} %)`}
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
                  {schmal && <Legend />}
                  <Tooltip content={<ChartTooltip unit="Anlagen" />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            </Parkbar>
            {/* Tabelle mit Details */}
            <Parkbar id="komp-speicher-tabelle" titel="Speicher · Verteilung (Tabelle)">
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
                      <td className="text-right py-1">{fmtZahl(k.avg_zyklen, 0)}</td>
                      <td className="text-right py-1">{fmtZahl(k.avg_wirkungsgrad, 1)} %</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            </Parkbar>
          </div>
        </div>
      )}

      {/* Tipps */}
      <TippsSection tipps={tipps} parkId="komp-speicher-tipps" parkTitel="Speicher · Tipps" />
    </>
  )
}

// =============================================================================
// Wärmepumpe Deep-Dive (Body ohne Card/Kopf)
// =============================================================================

export function WaermepumpeDeepDive({
  benchmark,
  communityStats,
}: {
  benchmark: CommunityBenchmarkResponse
  communityStats: WPByRegion | null
}) {
  const achsen = useChartTheme()
  const schmal = useSchmaleAchse()
  const wp = benchmark.benchmark_erweitert?.waermepumpe
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
    if (!wp) return tips

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

  if (!wp) return null

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <CommunityVergleichsKPI
          label="Jahresarbeitszahl (JAZ)"
          icon={<Thermometer className="h-5 w-5 text-blue-500" />}
          kpi={wp.jaz}
          einheit=""
          beschreibung="Wärmeenergie / Stromverbrauch"
          large
          parkId="komp-wp-kpi-jaz"
          parkTitel="Wärmepumpe · JAZ"
        />
        <CommunityVergleichsKPI
          label="Stromverbrauch"
          icon={<Zap className="h-5 w-5 text-yellow-500" />}
          kpi={wp.stromverbrauch}
          einheit="kWh"
          beschreibung="Gesamt im Zeitraum"
          parkId="komp-wp-kpi-stromverbrauch"
          parkTitel="Wärmepumpe · Stromverbrauch"
        />
        <CommunityVergleichsKPI
          label="Wärmeerzeugung"
          icon={<Home className="h-5 w-5 text-red-500" />}
          kpi={wp.waermeerzeugung}
          einheit="kWh"
          beschreibung="Heizung + Warmwasser"
          parkId="komp-wp-kpi-waermeerzeugung"
          parkTitel="Wärmepumpe · Wärmeerzeugung"
        />
      </div>

      {/* Community Wärmepumpen nach Region - nur bei mehreren Regionen sinnvoll */}
      {regionData.length > 0 && (
        <Parkbar id="komp-wp-chart" titel="Wärmepumpe · JAZ nach Region">
        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 mb-4">
            <MapPin className="h-5 w-5 text-gray-500" />
            <h4 className="font-medium text-gray-700 dark:text-gray-300">
              Community: JAZ nach Region
            </h4>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              ({fmtZahl(gesamtAnzahlWP, 0)} {gesamtAnzahlWP === 1 ? 'Anlage' : 'Anlagen'})
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
                  Aktuell: {regionData[0].name} mit JAZ {fmtZahl(regionData[0].jaz, 2)} ({fmtZahl(regionData[0].anzahl, 0)} Anlage)
                </p>
              )}
            </div>
          ) : (
            <>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={regionData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} horizontal={false} />
                    <XAxis type="number" domain={[0, 5]} tick={ACHSEN_TICK} tickFormatter={(v) => fmtZahl(v, 2)} /* achsen-allow: Wert-Achse waagerecht (JAZ), Format pro Tick (de-DE) */ />
                    <YAxis
                      type="category"
                      dataKey="name"
                      tick={ACHSEN_TICK}
                      width={schmal ? 48 : 72}
                      /* achsen-allow: Kategorie-Namen */
                    />
                    <Tooltip content={<ChartTooltip formatter={(value) => `JAZ: ${fmtZahl(value, 2)}`} />} />
                    <Bar dataKey="jaz" radius={[0, 2, 2, 0]}>
                      {regionData.map((entry, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={entry.region === eigeneRegion ? EIGENE_SERIE_FARBEN.du : achsen.referenz}
                        />
                      ))}
                      <LabelList
                        dataKey="jaz"
                        position="right"
                        formatter={(value: number) => fmtZahl(value, 2)}
                        style={{ fill: achsen.achse, fontSize: 11 }}
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
        </Parkbar>
      )}

      {/* Tipps */}
      <TippsSection tipps={tipps} parkId="komp-wp-tipps" parkTitel="Wärmepumpe · Tipps" />
    </>
  )
}

// =============================================================================
// E-Auto Deep-Dive (Body ohne Card/Kopf)
// =============================================================================

export function EAutoDeepDive({
  benchmark,
  communityStats,
}: {
  benchmark: CommunityBenchmarkResponse
  communityStats: EAutoByUsage | null
}) {
  const achsen = useChartTheme()
  const schmal = useSchmaleAchse()
  const eauto = benchmark.benchmark_erweitert?.eauto

  // Eigene Nutzungsklasse ermitteln (basierend auf km)
  const eigeneKlasse = useMemo(() => {
    if (!eauto?.km?.wert) return null
    const kmMonat = eauto.km.wert / 12 // Grobe Schätzung wenn Jahreswert
    if (kmMonat <= 500) return 'Wenig'
    if (kmMonat <= 1000) return 'Normal'
    if (kmMonat <= 2000) return 'Viel'
    return 'Intensiv'
  }, [eauto?.km])

  // Community-Daten nach Nutzungsintensität
  const nutzungData = useMemo(() => {
    if (!communityStats?.klassen) return []
    return communityStats.klassen
      .filter((k) => k.anzahl > 0)
      .map((k, i) => ({
        name: k.klasse.charAt(0).toUpperCase() + k.klasse.slice(1), // Capitalize
        beschreibung: k.beschreibung,
        anzahl: k.anzahl,
        fill: SERIEN_PALETTE[i % SERIEN_PALETTE.length],
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
    if (!eauto?.pv_anteil) return []

    const pvAnteil = eauto.pv_anteil.wert
    return [
      { name: 'PV', wert: pvAnteil, fill: LADEQUELLEN_FARBEN.pv },
      { name: 'Netz/Extern', wert: 100 - pvAnteil, fill: LADEQUELLEN_FARBEN.netz },
    ]
  }, [eauto])

  // Tipps generieren
  const tipps = useMemo(() => {
    const tips: string[] = []
    if (!eauto) return tips

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

  if (!eauto) return null

  return (
    <>
      {/* D13-5: KPIs als Kachelreihe (wie WP/Wallbox/BKW) statt gestapelter
          Spalte neben dem Chart — konsistentes V4-Muster, kein Leerraum. */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <CommunityVergleichsKPI
          label="PV-Ladeanteil"
          icon={<Sun className="h-5 w-5 text-yellow-500" />}
          kpi={eauto.pv_anteil}
          einheit="%"
          beschreibung="Anteil PV an Gesamtladung"
          parkId="komp-eauto-kpi-pvanteil"
          parkTitel="E-Auto · PV-Ladeanteil"
        />
        <CommunityVergleichsKPI
          label="Ladung gesamt"
          icon={<BatteryCharging className="h-5 w-5 text-purple-500" />}
          kpi={eauto.ladung_gesamt}
          einheit="kWh"
          beschreibung="Gesamte Lademenge"
          parkId="komp-eauto-kpi-ladung"
          parkTitel="E-Auto · Ladung gesamt"
        />
        <CommunityVergleichsKPI
          label="Verbrauch"
          icon={<Gauge className="h-5 w-5 text-blue-500" />}
          kpi={eauto.verbrauch_100km}
          einheit="kWh/100km"
          beschreibung="Durchschnittsverbrauch"
          invertColors
          parkId="komp-eauto-kpi-verbrauch"
          parkTitel="E-Auto · Verbrauch"
        />
        {eauto.km && (
          <CommunityVergleichsKPI
            label="Gefahrene km"
            icon={<Route className="h-5 w-5 text-gray-500" />}
            kpi={eauto.km}
            einheit="km"
            beschreibung="Im Zeitraum"
            parkId="komp-eauto-kpi-km"
            parkTitel="E-Auto · Gefahrene km"
          />
        )}
        {eauto.v2h && eauto.v2h.wert > 0 && (
          <CommunityVergleichsKPI
            label="V2H Entladung"
            icon={<Zap className="h-5 w-5 text-green-500" />}
            kpi={eauto.v2h}
            einheit="kWh"
            beschreibung="Rückspeisung ins Haus"
            parkId="komp-eauto-kpi-v2h"
            parkTitel="E-Auto · V2H Entladung"
          />
        )}
      </div>

      {/* Ladequellen-Verteilung (Full-Width unter den KPIs) */}
      {ladequellenData.length > 0 && (
        <Parkbar id="komp-eauto-chart" titel="E-Auto · Ladequellen-Verteilung">
          <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              Ladequellen-Verteilung
            </h4>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={ladequellenData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} tick={ACHSEN_TICK} tickFormatter={(v) => `${fmtZahl(v, 0)} %`} /* achsen-allow: Wert-Achse waagerecht, Einheit/Format pro Tick (de-DE) */ />
                  <YAxis type="category" dataKey="name" tick={ACHSEN_TICK} width={80} /* achsen-allow: Kategorie-Namen */ />
                  <Tooltip content={<ChartTooltip unit="%" decimals={1} />} />
                  <Bar dataKey="wert" radius={[0, 2, 2, 0]}>
                    {ladequellenData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </Parkbar>
      )}

      {/* Community E-Auto nach Nutzungsintensität */}
      {nutzungData.length > 0 && (
        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 mb-4">
            <Users className="h-5 w-5 text-gray-500" />
            <h4 className="font-medium text-gray-700 dark:text-gray-300">
              Community: E-Autos nach Nutzungsintensität
            </h4>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              ({fmtZahl(gesamtAnzahlEAuto, 0)} E-Autos)
            </span>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Pie Chart */}
            <Parkbar id="komp-eauto-pie" titel="E-Auto · Nutzungsintensität (Diagramm)">
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
                    label={schmal ? undefined : ({ name, percent }) => `${name} (${fmtZahl(percent * 100, 0)} %)`}
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
                  {schmal && <Legend />}
                  <Tooltip content={<ChartTooltip unit="E-Autos" />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            </Parkbar>
            {/* Tabelle mit Details */}
            <Parkbar id="komp-eauto-tabelle" titel="E-Auto · Nutzungsintensität (Tabelle)">
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
                      <td className="text-right py-1">{fmtZahl(k.avg_verbrauch, 1)} kWh/100km</td>
                      <td className="text-right py-1">{fmtZahl(k.avg_pv_anteil, 0)} %</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            </Parkbar>
          </div>
        </div>
      )}

      {/* Tipps */}
      <TippsSection tipps={tipps} parkId="komp-eauto-tipps" parkTitel="E-Auto · Tipps" />
    </>
  )
}

// =============================================================================
// Wallbox Deep-Dive (Body ohne Card/Kopf)
// =============================================================================

export function WallboxDeepDive({ benchmark }: { benchmark: CommunityBenchmarkResponse }) {
  const wallbox = benchmark.benchmark_erweitert?.wallbox

  // Tipps generieren
  const tipps = useMemo(() => {
    const tips: string[] = []
    if (!wallbox) return tips

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

  if (!wallbox) return null

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <CommunityVergleichsKPI
          label="PV-Ladeanteil"
          icon={<Sun className="h-5 w-5 text-yellow-500" />}
          kpi={wallbox.pv_anteil}
          einheit="%"
          beschreibung="Anteil PV an Gesamtladung"
          large
          parkId="komp-wallbox-kpi-pvanteil"
          parkTitel="Wallbox · PV-Ladeanteil"
        />
        <CommunityVergleichsKPI
          label="Ladung gesamt"
          icon={<Zap className="h-5 w-5 text-cyan-500" />}
          kpi={wallbox.ladung}
          einheit="kWh"
          beschreibung="Im Zeitraum"
          parkId="komp-wallbox-kpi-ladung"
          parkTitel="Wallbox · Ladung gesamt"
        />
        <CommunityVergleichsKPI
          label="Ladevorgänge"
          icon={<BarChart3 className="h-5 w-5 text-gray-500" />}
          kpi={wallbox.ladevorgaenge}
          einheit=""
          beschreibung="Anzahl"
          parkId="komp-wallbox-kpi-ladevorgaenge"
          parkTitel="Wallbox · Ladevorgänge"
        />
      </div>

      {/* Tipps */}
      <TippsSection tipps={tipps} parkId="komp-wallbox-tipps" parkTitel="Wallbox · Tipps" />
    </>
  )
}

// =============================================================================
// Balkonkraftwerk Deep-Dive (Body ohne Card/Kopf)
// =============================================================================

export function BKWDeepDive({ benchmark }: { benchmark: CommunityBenchmarkResponse }) {
  const bkw = benchmark.benchmark_erweitert?.balkonkraftwerk

  // Tipps generieren
  const tipps = useMemo(() => {
    const tips: string[] = []
    if (!bkw) return tips

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

  if (!bkw) return null

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <CommunityVergleichsKPI
          label="Spezifischer Ertrag"
          icon={<TrendingUp className="h-5 w-5 text-amber-500" />}
          kpi={bkw.spez_ertrag}
          einheit="kWh/kWp"
          beschreibung="Normierter Ertrag"
          large
          parkId="komp-bkw-kpi-spezertrag"
          parkTitel="Balkonkraftwerk · Spezifischer Ertrag"
        />
        <CommunityVergleichsKPI
          label="Erzeugung"
          icon={<Zap className="h-5 w-5 text-yellow-500" />}
          kpi={bkw.erzeugung}
          einheit="kWh"
          beschreibung="Im Zeitraum"
          parkId="komp-bkw-kpi-erzeugung"
          parkTitel="Balkonkraftwerk · Erzeugung"
        />
        <CommunityVergleichsKPI
          label="Eigenverbrauch"
          icon={<Home className="h-5 w-5 text-green-500" />}
          kpi={bkw.eigenverbrauch}
          einheit="%"
          beschreibung="Direkt genutzt"
          parkId="komp-bkw-kpi-eigenverbrauch"
          parkTitel="Balkonkraftwerk · Eigenverbrauch"
        />
      </div>

      {/* Tipps */}
      <TippsSection tipps={tipps} parkId="komp-bkw-tipps" parkTitel="Balkonkraftwerk · Tipps" />
    </>
  )
}

// =============================================================================
// Hilfskomponenten
// =============================================================================

export function RangBadge({ rang, von }: { rang: number; von: number }) {
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
        #{fmtZahl(rang, 0)} von {fmtZahl(von, 0)}
      </span>
    </div>
  )
}

/**
 * Dokumentierter Sonderfall der KPICard-SoT (Style-Guide B9): Community-Vergleichs-
 * Kachel mit community_avg-Delta + invertColors-Logik. Bewusst NICHT die zentrale
 * `components/ui/KPICard`, weil die Vergleichsmechanik (Abweichung %, Trend-Färbung)
 * dort nicht hingehört. Farb-/Größenlogik bleibt an die SoT-Konventionen angelehnt.
 */
function CommunityVergleichsKPI({
  label,
  icon,
  kpi,
  einheit,
  beschreibung,
  invertColors,
  large,
  parkId,
  parkTitel,
}: {
  label: string
  icon: React.ReactNode
  kpi?: KPIVergleich | null
  einheit: string
  beschreibung: string
  invertColors?: boolean
  large?: boolean
  /** Element-Park-Doktrin: macht DIESE KPI-Karte einzeln parkbar. Da die Karte
   *  bei `!kpi` null zurückgibt, MUSS der Wrapper INNEN (nach dem null-Guard)
   *  sitzen — sonst stünde ein leerer Park-Div an einer datenlosen Stelle. */
  parkId?: string
  parkTitel?: string
}) {
  if (!kpi) return null

  const hasComparison = kpi.community_avg !== undefined && kpi.community_avg !== null
  const abweichung = hasComparison ? ((kpi.wert - kpi.community_avg!) / kpi.community_avg!) * 100 : null
  const isPositive = abweichung !== null ? (invertColors ? abweichung < 0 : abweichung > 0) : null

  const inhalt = (
    <div className={`bg-gray-50 dark:bg-gray-800 rounded-lg p-4 ${large ? 'md:col-span-1' : ''}`}>
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className={`font-bold text-gray-900 dark:text-white ${large ? 'text-3xl' : 'text-xl'}`}>
          {fmtZahl(kpi.wert, einheit === '%' ? 1 : einheit === '' ? 1 : 0)}
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
            {abweichung >= 0 ? '+' : ''}{fmtZahl(abweichung, 1)} % vs. Ø
          </span>
        </div>
      )}
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{beschreibung}</p>
    </div>
  )

  return parkId ? <Parkbar id={parkId} titel={parkTitel ?? label}>{inhalt}</Parkbar> : inhalt
}

function TippsSection({ tipps, parkId, parkTitel }: { tipps: string[]; parkId?: string; parkTitel?: string }) {
  const inhalt = (
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
  return parkId ? <Parkbar id={parkId} titel={parkTitel ?? 'Tipps'}>{inhalt}</Parkbar> : inhalt
}

// ─── Kopf-Metadaten je Komponente (Untertitel-String für IST/V4) ──────────────

export function speicherUntertitel(benchmark: CommunityBenchmarkResponse): string {
  return `${fmtZahl(benchmark.anlage.speicher_kwh || 0, 0)} kWh Kapazität`
}

export function bkwUntertitel(benchmark: CommunityBenchmarkResponse): string {
  const leistung = benchmark.anlage.bkw_wp
  return leistung ? `${fmtZahl(leistung, 0)} Wp` : 'Mini-PV'
}

export function wallboxUntertitel(benchmark: CommunityBenchmarkResponse): string {
  const leistung = benchmark.anlage.wallbox_kw
  return leistung ? `${fmtZahl(leistung, 0)} kW Ladeleistung` : 'Ladeverhalten'
}

// Re-Export der Icons für die Aufrufer (Card-/Block-Köpfe).
export { Battery, Sun, Home, Plug, Car }
