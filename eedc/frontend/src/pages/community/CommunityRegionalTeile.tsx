/**
 * Community-Regional — geteilte Teile (Daten-Hook + Präsentations-Sektionen).
 * EINE Code-Wahrheit für IST (`RegionalTab`) und IA-V4 (`CommunityRegionalV4`).
 * Sektionen rendern Inhalt OHNE äußere Card/Block-Hülle (Aufrufer wickelt).
 * Zahlen de-DE (`fmtZahl`), Farben/Achsen aus der Zentrale.
 */
import { useEffect, useMemo, useState } from 'react'
import { ComposableMap, Geographies, Geography } from 'react-simple-maps'
import germanyGeoJson from '../../assets/deutschland-bundeslaender.geo.json'
import { MapPin, Trophy, TrendingUp, TrendingDown, Users, Sun } from 'lucide-react'
import { KPICard } from '../../components/ui'
import { ScrollSchatten } from '../../components/ui/ScrollSchatten'
import { Parkbar } from '../../components/park'
import ChartTooltip from '../../components/ui/ChartTooltip'
import { useChartTheme } from '../../context/ThemeContext'
import { useSchmaleAchse } from '../../hooks'
import { EIGENE_SERIE_FARBEN, KARTE_FARBEN, SOLAR_INTENSITAET, ACHSEN_TICK, fmtZahl } from '../../lib'
import { communityApi } from '../../api'
import type { CommunityBenchmarkResponse, RegionStatistik } from '../../api/community'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'

// Bundesland-Daten
const BUNDESLAENDER: Record<string, { name: string; kurzname: string }> = {
  BW: { name: 'Baden-Württemberg', kurzname: 'BaWü' },
  BY: { name: 'Bayern', kurzname: 'Bayern' },
  BE: { name: 'Berlin', kurzname: 'Berlin' },
  BB: { name: 'Brandenburg', kurzname: 'Brandenb.' },
  HB: { name: 'Bremen', kurzname: 'Bremen' },
  HH: { name: 'Hamburg', kurzname: 'Hamburg' },
  HE: { name: 'Hessen', kurzname: 'Hessen' },
  MV: { name: 'Mecklenburg-Vorpommern', kurzname: 'MeckPom' },
  NI: { name: 'Niedersachsen', kurzname: 'Nieders.' },
  NW: { name: 'Nordrhein-Westfalen', kurzname: 'NRW' },
  RP: { name: 'Rheinland-Pfalz', kurzname: 'RhPf' },
  SL: { name: 'Saarland', kurzname: 'Saarland' },
  SN: { name: 'Sachsen', kurzname: 'Sachsen' },
  ST: { name: 'Sachsen-Anhalt', kurzname: 'SaAnh' },
  SH: { name: 'Schleswig-Holstein', kurzname: 'SchlHol' },
  TH: { name: 'Thüringen', kurzname: 'Thüring.' },
  AT: { name: 'Österreich', kurzname: 'Österr.' },
  CH: { name: 'Schweiz', kurzname: 'Schweiz' },
}

// Farbinterpolation für Choropleth: hell (wenig Ertrag) → dunkel (viel Ertrag)
function interpolateColor(value: number, min: number, max: number): string {
  if (max === min) return SOLAR_INTENSITAET[1]
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)))
  // Farbverlauf: Hellblau (niedrig) → Gelb (hoch), als RGB-Stützwerte interpoliert
  const r = Math.round(219 + (251 - 219) * t)
  const g = Math.round(234 + (191 - 234) * t)
  const b = Math.round(254 + (36 - 254) * t)
  return `rgb(${r},${g},${b})`
}

// Element-Park (IA-V4, Element-Park-Doktrin Gernot 2026-06-27): JEDE Anzeige
// (KPI, Chart, Box, Karte, Tabelle) ist einzeln parkbar. `Parkbar` ist OHNE
// ParkProvider inert → der IST-`RegionalTab` (v3, kein Provider) bleibt optisch
// identisch; nur die V4-Sicht aktiviert die Geste. IDs view-eindeutig (persistKey
// 'v4-community-regional'); der V4-Builder blendet einen Block aus, wenn ALLE
// seine Element-IDs geparkt sind (alleGeparkt).
export const REG_PARK_IDS = {
  position: ['reg-position-standort', 'reg-position-rang', 'reg-position-vs-region'],
  vergleich: ['reg-vergleich-chart'],
  einordnung: ['reg-einordnung-vs', 'reg-einordnung-anlage'],
  karte: ['reg-karte'],
  tabelle: ['reg-tabelle'],
} as const

export interface RegionalStats {
  region: string
  regionName: string
  spezErtrag: number
  regionDurchschnitt: number
  communityDurchschnitt: number
  rang: number
  anzahlAnlagen: number
  abweichungRegion: number
  abweichungCommunity: number
  perzentilRegion: number
}

export interface RegionalDaten {
  allRegions: RegionStatistik[]
  regionalStats: RegionalStats | null
  vergleichsData: { name: string; kurz: string; wert: number; fill: string }[]
  extraLoading: boolean
}

// ─── Daten-Hook (lädt Regional-Statistik; leitet Kennzahlen + Vergleich ab) ────

export function useRegionalDaten(benchmark: CommunityBenchmarkResponse | null): RegionalDaten {
  const achsen = useChartTheme()
  const [allRegions, setAllRegions] = useState<RegionStatistik[]>([])
  const [extraLoading, setExtraLoading] = useState(false)

  // Regionale Statistiken laden (unabhängig vom Benchmark)
  useEffect(() => {
    const loadRegions = async () => {
      setExtraLoading(true)
      try {
        const regionsData = await communityApi.getRegionalStatistics().catch(() => [])
        setAllRegions(regionsData)
      } finally {
        setExtraLoading(false)
      }
    }
    loadRegions()
  }, [])

  // Regionale Kennzahlen berechnen
  const regionalStats = useMemo<RegionalStats | null>(() => {
    if (!benchmark) return null

    const { spez_ertrag_anlage, spez_ertrag_region, spez_ertrag_durchschnitt, rang_region, anzahl_anlagen_region } = benchmark.benchmark
    const region = benchmark.anlage.region

    return {
      region,
      regionName: BUNDESLAENDER[region]?.name || region,
      spezErtrag: spez_ertrag_anlage,
      regionDurchschnitt: spez_ertrag_region,
      communityDurchschnitt: spez_ertrag_durchschnitt,
      rang: rang_region,
      anzahlAnlagen: anzahl_anlagen_region,
      abweichungRegion: ((spez_ertrag_anlage - spez_ertrag_region) / spez_ertrag_region) * 100,
      abweichungCommunity: ((spez_ertrag_region - spez_ertrag_durchschnitt) / spez_ertrag_durchschnitt) * 100,
      perzentilRegion: Math.round((1 - rang_region / anzahl_anlagen_region) * 100),
    }
  }, [benchmark])

  // Vergleichsdaten für Chart
  const vergleichsData = useMemo(() => {
    if (!regionalStats) return []

    return [
      { name: 'Du', kurz: 'Du', wert: regionalStats.spezErtrag, fill: EIGENE_SERIE_FARBEN.du },
      { name: regionalStats.regionName, kurz: BUNDESLAENDER[regionalStats.region]?.kurzname || regionalStats.region, wert: regionalStats.regionDurchschnitt, fill: EIGENE_SERIE_FARBEN.region },
      { name: 'Community', kurz: 'Community', wert: regionalStats.communityDurchschnitt, fill: achsen.referenz },
    ]
  }, [regionalStats, achsen.referenz])

  return { allRegions, regionalStats, vergleichsData, extraLoading }
}

// ─── Choropleth-Karte (Hilfs-Komponente für den Karten-Block) ─────────────────

interface ChoroplethKarteProps {
  allRegions: RegionStatistik[]
  eigeneRegion: string | null
}

function ChoroplethKarte({ allRegions, eigeneRegion }: ChoroplethKarteProps) {
  const achsen = useChartTheme()
  const [tooltip, setTooltip] = useState<{ name: string; region: RegionStatistik | null; wert: number; x: number; y: number } | null>(null)

  const regionMap = useMemo(() => {
    const map: Record<string, number> = {}
    allRegions.forEach(r => { map[r.region] = r.durchschnitt_spez_ertrag })
    return map
  }, [allRegions])

  const regionDataMap = useMemo(() => {
    const map: Record<string, RegionStatistik> = {}
    allRegions.forEach(r => { map[r.region] = r })
    return map
  }, [allRegions])

  const { min, max } = useMemo(() => {
    const werte = allRegions.map(r => r.durchschnitt_spez_ertrag)
    return { min: Math.min(...werte), max: Math.max(...werte) }
  }, [allRegions])

  return (
    <div className="relative">
      <ComposableMap
        projection="geoMercator"
        projectionConfig={{ center: [10.4515, 51.2], scale: 2800 }}
        width={500}
        height={560}
        style={{ width: '100%', height: 'auto' }}
      >
        <Geographies geography={germanyGeoJson}>
          {({ geographies }) =>
            geographies.map(geo => {
              const code = (geo.properties.id as string).replace('DE-', '')
              const wert = regionMap[code]
              const isOwn = code === eigeneRegion
              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill={wert !== undefined ? interpolateColor(wert, min, max) : achsen.grid}
                  stroke={isOwn ? EIGENE_SERIE_FARBEN.duRand : KARTE_FARBEN.grenze}
                  strokeWidth={isOwn ? 2.5 : 0.8}
                  style={{
                    default: { outline: 'none' },
                    hover: { outline: 'none', opacity: 0.85, cursor: 'pointer' },
                    pressed: { outline: 'none' },
                  }}
                  onMouseEnter={e => {
                    if (wert !== undefined) {
                      setTooltip({ name: geo.properties.name as string, region: regionDataMap[code] ?? null, wert, x: e.clientX, y: e.clientY })
                    }
                  }}
                  onMouseMove={e => {
                    if (tooltip) setTooltip(prev => prev ? { ...prev, x: e.clientX, y: e.clientY } : null)
                  }}
                  onMouseLeave={() => setTooltip(null)}
                />
              )
            })
          }
        </Geographies>
      </ComposableMap>

      {/* Tooltip — D14-12 (detLAN #113, SS 14-28-19): Pop-up-Kanon = dunkel in
          beiden Modi (ChartTooltip-Linie); war als einziger Karten-Tooltip hell. */}
      {tooltip && (
        <div
          className="fixed z-50 bg-gray-900 dark:bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 shadow-lg pointer-events-none text-sm"
          style={{ left: tooltip.x + 12, top: tooltip.y - 40 }}
        >
          <p className="font-medium text-white">{tooltip.name}</p>
          <p className="text-blue-400 font-medium">{fmtZahl(tooltip.wert, 0)} kWh/kWp</p>
          {tooltip.region && (
            <div className="mt-1 pt-1 border-t border-gray-700 space-y-0.5 text-xs text-gray-300">
              <p>{tooltip.region.anzahl_anlagen} Anlage{tooltip.region.anzahl_anlagen !== 1 ? 'n' : ''} · Ø {fmtZahl(tooltip.region.durchschnitt_kwp, 1)} kWp</p>
              {tooltip.region.avg_speicher_ladung_kwh != null && <p>🔋 {fmtZahl(tooltip.region.avg_speicher_ladung_kwh, 0)} ↓ / {tooltip.region.avg_speicher_entladung_kwh != null ? fmtZahl(tooltip.region.avg_speicher_entladung_kwh, 0) : '–'} ↑ kWh/Mon</p>}
              {tooltip.region.avg_wp_jaz != null && <p>♨️ JAZ {fmtZahl(tooltip.region.avg_wp_jaz, 1)}</p>}
              {tooltip.region.avg_eauto_km != null && <p>🚗 {fmtZahl(tooltip.region.avg_eauto_km, 0)} km/Mon · {tooltip.region.avg_eauto_ladung_kwh != null ? `${fmtZahl(tooltip.region.avg_eauto_ladung_kwh, 0)} kWh zuhause` : '–'}</p>}
              {tooltip.region.avg_wallbox_kwh != null && <p>🔌 {fmtZahl(tooltip.region.avg_wallbox_kwh, 0)} kWh/Mon{tooltip.region.avg_wallbox_pv_anteil != null ? ` · ${fmtZahl(tooltip.region.avg_wallbox_pv_anteil, 0)} % PV` : ''}</p>}
              {tooltip.region.avg_bkw_kwh != null && <p>🪟 {fmtZahl(tooltip.region.avg_bkw_kwh, 0)} kWh/Mon</p>}
            </div>
          )}
        </div>
      )}

      {/* Legende */}
      <div className="flex items-center gap-2 mt-2 justify-center">
        <span className="text-xs text-gray-500">{fmtZahl(min, 0)}</span>
        <div
          className="h-3 w-32 rounded"
          style={{ background: `linear-gradient(to right, ${interpolateColor(min, min, max)}, ${interpolateColor(max, min, max)})` }}
        />
        <span className="text-xs text-gray-500">{fmtZahl(max, 0)} kWh/kWp</span>
      </div>
      {eigeneRegion && (
        <p className="text-xs text-center text-blue-600 dark:text-blue-400 mt-1">
          Dein Bundesland: blauer Rahmen
        </p>
      )}
    </div>
  )
}

// ─── Sektion: KPI-Strip (Standort · Rang · vs. Region) ────────────────────────

export function RegionalKpiStrip({ regionalStats }: { regionalStats: RegionalStats }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Dein Bundesland */}
      <Parkbar id="reg-position-standort" titel="Dein Standort">
        <KPICard
          title="Dein Standort"
          value={regionalStats.regionName}
          subtitle={`${regionalStats.anzahlAnlagen} Anlagen in der Region`}
          color="blue"
          icon={MapPin}
        />
      </Parkbar>

      {/* Rang in Region */}
      <Parkbar id="reg-position-rang" titel="Rang in der Region">
        <KPICard
          title={`Rang in ${BUNDESLAENDER[regionalStats.region]?.kurzname || regionalStats.region}`}
          value={`#${regionalStats.rang} von ${regionalStats.anzahlAnlagen}`}
          subtitle={`Besser als ${fmtZahl(regionalStats.perzentilRegion, 0)} % in deiner Region`}
          color="yellow"
          icon={Trophy}
        />
      </Parkbar>

      {/* Abweichung vom Regions-Durchschnitt */}
      <Parkbar id="reg-position-vs-region" titel="vs. Region">
        <KPICard
          title="vs. Region"
          value={`${regionalStats.abweichungRegion >= 0 ? '+' : ''}${fmtZahl(regionalStats.abweichungRegion, 1)}`}
          unit="%"
          subtitle={`Ø Region: ${fmtZahl(regionalStats.regionDurchschnitt, 0)} kWh/kWp`}
          color={regionalStats.abweichungRegion >= 0 ? 'green' : 'red'}
          icon={regionalStats.abweichungRegion >= 0 ? TrendingUp : TrendingDown}
        />
      </Parkbar>
    </div>
  )
}

// ─── Sektion: Vergleichs-Chart (spez. Ertrag) ─────────────────────────────────

export function VergleichsChart({ vergleichsData }: { vergleichsData: RegionalDaten['vergleichsData'] }) {
  const achsen = useChartTheme()
  const schmal = useSchmaleAchse()
  return (
    <Parkbar id="reg-vergleich-chart" titel="Spezifischer Ertrag im Vergleich">
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={vergleichsData} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} horizontal={true} vertical={false} />
          <XAxis
            type="number"
            tick={ACHSEN_TICK}
            domain={[0, 'auto']}
            tickFormatter={(v) => `${fmtZahl(v, 0)} kWh/kWp`}
            /* achsen-allow: Wert-Achse waagerecht, Einheit/Format pro Tick (de-DE) */
          />
          <YAxis
            type="category"
            dataKey={schmal ? 'kurz' : 'name'}
            tick={ACHSEN_TICK}
            width={schmal ? 64 : 100}
            /* achsen-allow: Kategorie-Namen */
          />
          <Tooltip content={<ChartTooltip unit="kWh/kWp" />} />
          <Bar dataKey="wert" radius={[0, 2, 2, 0]}>
            {vergleichsData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
    </Parkbar>
  )
}

// ─── Sektion: Regionale Einordnung (2 Boxen) ──────────────────────────────────

export function RegionaleEinordnung({ benchmark, regionalStats }: { benchmark: CommunityBenchmarkResponse; regionalStats: RegionalStats }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Region vs. Community */}
      <Parkbar id="reg-einordnung-vs" titel="Region vs. Community">
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
        <h4 className="font-medium text-gray-900 dark:text-white mb-2">
          {regionalStats.regionName} vs. Community
        </h4>
        <div className="flex items-center gap-2 mb-2">
          <span className={`text-lg font-semibold ${
            regionalStats.abweichungCommunity >= 0
              ? 'text-green-600 dark:text-green-400'
              : 'text-red-600 dark:text-red-400'
          }`}>
            {regionalStats.abweichungCommunity >= 0 ? '+' : ''}
            {fmtZahl(regionalStats.abweichungCommunity, 1)} %
          </span>
          <span className="text-gray-500 dark:text-gray-400">
            {regionalStats.abweichungCommunity >= 0 ? 'über' : 'unter'} dem Durchschnitt
          </span>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Deine Region liegt {regionalStats.abweichungCommunity >= 0 ? 'über' : 'unter'} dem
          bundesweiten Community-Durchschnitt von {fmtZahl(regionalStats.communityDurchschnitt, 0)} kWh/kWp.
        </p>
      </div>
      </Parkbar>

      {/* Deine Anlage */}
      <Parkbar id="reg-einordnung-anlage" titel="Deine Anlage">
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
        <h4 className="font-medium text-gray-900 dark:text-white mb-2">
          Deine Anlage
        </h4>
        <div className="space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500 dark:text-gray-400">Ausrichtung:</span>
            <span className="text-gray-900 dark:text-white capitalize">{benchmark.anlage.ausrichtung}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500 dark:text-gray-400">Neigung:</span>
            <span className="text-gray-900 dark:text-white">{fmtZahl(benchmark.anlage.neigung_grad, 0)}°</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500 dark:text-gray-400">Leistung:</span>
            <span className="text-gray-900 dark:text-white">{fmtZahl(benchmark.anlage.kwp, 1)} kWp</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500 dark:text-gray-400">Installation:</span>
            <span className="text-gray-900 dark:text-white">{benchmark.anlage.installation_jahr}</span>
          </div>
        </div>
      </div>
      </Parkbar>
    </div>
  )
}

// ─── Sektion: Choropleth-Block (Deutschland-Karte) ────────────────────────────

export function ChoroplethBlock({ allRegions, benchmark }: { allRegions: RegionStatistik[]; benchmark: CommunityBenchmarkResponse }) {
  return (
    <Parkbar id="reg-karte" titel="Spezifischer Ertrag nach Bundesland">
      <ChoroplethKarte
        allRegions={allRegions}
        eigeneRegion={benchmark?.anlage.region ?? null}
      />
    </Parkbar>
  )
}

// ─── Sektion: Bundesländer-Tabelle ────────────────────────────────────────────

export function RegionenTabelle({ allRegions, benchmark }: { allRegions: RegionStatistik[]; benchmark: CommunityBenchmarkResponse }) {
  const schmal = useSchmaleAchse()

  if (schmal) {
    const sortiert = [...allRegions].sort((a, b) => b.durchschnitt_spez_ertrag - a.durchschnitt_spez_ertrag)
    return (
      <Parkbar id="reg-tabelle" titel="Alle Regionen im Vergleich">
      <div className="space-y-3">
        {sortiert.map((region, index) => {
          const isOwn = region.region === benchmark?.anlage.region
          return (
            <div
              key={region.region}
              className={`rounded-lg border p-3 ${
                isOwn
                  ? 'bg-primary-50 dark:bg-primary-900/20 border-primary-200 dark:border-primary-800'
                  : 'border-gray-200 dark:border-gray-700'
              }`}
            >
              {/* Kopf: Rang + Bundesland-Name */}
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-xs font-medium w-5 text-center ${
                  index < 3 ? 'text-yellow-600' : 'text-gray-400 dark:text-gray-500'
                }`}>
                  {index + 1}
                </span>
                <span className={`font-medium ${isOwn ? 'text-primary-600 dark:text-primary-400' : 'text-gray-900 dark:text-white'}`}>
                  {BUNDESLAENDER[region.region]?.name || region.region}
                </span>
                {isOwn && <span className="text-xs text-primary-500">(Du)</span>}
              </div>

              {/* Kennzahlen als Label/Wert-Paare */}
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500 dark:text-gray-400">Anlagen</span>
                  <span className="text-gray-600 dark:text-gray-400">{region.anzahl_anlagen}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500 dark:text-gray-400">Ø kWp</span>
                  <span className="text-gray-600 dark:text-gray-400">{fmtZahl(region.durchschnitt_kwp, 1)}</span>
                </div>
                <div className="flex justify-between col-span-2">
                  <span className="text-gray-500 dark:text-gray-400">Ø kWh/kWp</span>
                  <span className="font-medium text-gray-900 dark:text-white">{fmtZahl(region.durchschnitt_spez_ertrag, 0)}</span>
                </div>
                {region.avg_speicher_ladung_kwh != null && (
                  <div className="flex justify-between col-span-2" title="Ø Ladung ↓ / Entladung ↑ pro Monat (kWh)">
                    <span className="text-gray-500 dark:text-gray-400">🔋 Ladung/Entl.</span>
                    <span className="text-gray-600 dark:text-gray-400">
                      {fmtZahl(region.avg_speicher_ladung_kwh, 0)} ↓ / {region.avg_speicher_entladung_kwh != null ? fmtZahl(region.avg_speicher_entladung_kwh, 0) : '–'} ↑ kWh
                    </span>
                  </div>
                )}
                {region.avg_wp_jaz != null && (
                  <div className="flex justify-between" title="Ø Jahresarbeitszahl (Σ Wärme ÷ Σ Strom)">
                    <span className="text-gray-500 dark:text-gray-400">♨️ JAZ</span>
                    <span className="text-gray-600 dark:text-gray-400">{fmtZahl(region.avg_wp_jaz, 1)}</span>
                  </div>
                )}
                {region.avg_eauto_km != null && (
                  <div className="flex justify-between col-span-2" title="Ø km/Mon · Ø kWh zuhause geladen">
                    <span className="text-gray-500 dark:text-gray-400">🚗 km / kWh</span>
                    <span className="text-gray-600 dark:text-gray-400">
                      {fmtZahl(region.avg_eauto_km, 0)} km{region.avg_eauto_ladung_kwh != null ? ` · ${fmtZahl(region.avg_eauto_ladung_kwh, 0)} kWh` : ''}
                    </span>
                  </div>
                )}
                {region.avg_wallbox_kwh != null && (
                  <div className="flex justify-between col-span-2" title="Ø kWh geladen/Mon · davon PV-Anteil (wo messbar)">
                    <span className="text-gray-500 dark:text-gray-400">🔌 kWh / PV%</span>
                    <span className="text-gray-600 dark:text-gray-400">
                      {fmtZahl(region.avg_wallbox_kwh, 0)} kWh{region.avg_wallbox_pv_anteil != null ? ` · ${fmtZahl(region.avg_wallbox_pv_anteil, 0)} % PV` : ''}
                    </span>
                  </div>
                )}
                {region.avg_bkw_kwh != null && (
                  <div className="flex justify-between col-span-2" title="Ø BKW-Ertrag pro Monat (kWh)">
                    <span className="text-gray-500 dark:text-gray-400">🪟 kWh/Mon</span>
                    <span className="text-gray-600 dark:text-gray-400">{fmtZahl(region.avg_bkw_kwh, 0)} kWh</span>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
      </Parkbar>
    )
  }

  return (
    <Parkbar id="reg-tabelle" titel="Alle Regionen im Vergleich">
    <ScrollSchatten achse="horizontal" fadeFrom="from-white dark:from-gray-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            <th className="text-left py-2 px-3 text-gray-500 font-medium">Region</th>
            <th className="text-right py-2 px-3 text-gray-500 font-medium">Anlagen</th>
            <th className="text-right py-2 px-3 text-gray-500 font-medium">Ø kWp</th>
            <th className="text-right py-2 px-3 text-gray-500 font-medium">Ø kWh/kWp</th>
            <th className="text-right py-2 px-3 text-gray-500 font-medium" title="Ø Ladung ↓ / Entladung ↑ pro Monat (kWh)">🔋 Ladung/Entl.</th>
            <th className="text-right py-2 px-3 text-gray-500 font-medium" title="Ø Jahresarbeitszahl (Σ Wärme ÷ Σ Strom)">♨️ JAZ</th>
            <th className="text-right py-2 px-3 text-gray-500 font-medium" title="Ø km/Mon · Ø kWh zuhause geladen">🚗 km / kWh</th>
            <th className="text-right py-2 px-3 text-gray-500 font-medium" title="Ø kWh geladen/Mon · davon PV-Anteil (wo messbar)">🔌 kWh / PV%</th>
            <th className="text-right py-2 px-3 text-gray-500 font-medium" title="Ø BKW-Ertrag pro Monat (kWh)">🪟 kWh/Mon</th>
          </tr>
        </thead>
        <tbody>
          {allRegions
            .sort((a, b) => b.durchschnitt_spez_ertrag - a.durchschnitt_spez_ertrag)
            .map((region, index) => {
              const isOwn = region.region === benchmark?.anlage.region
              return (
                <tr
                  key={region.region}
                  className={`border-b border-gray-100 dark:border-gray-800 ${
                    isOwn ? 'bg-primary-50 dark:bg-primary-900/20' : ''
                  }`}
                >
                  <td className="py-2 px-3">
                    <div className="flex items-center gap-2">
                      <span className={`text-xs font-medium w-5 text-center ${
                        index < 3 ? 'text-yellow-600' : 'text-gray-400 dark:text-gray-500'
                      }`}>
                        {index + 1}
                      </span>
                      <span className={`font-medium ${isOwn ? 'text-primary-600 dark:text-primary-400' : 'text-gray-900 dark:text-white'}`}>
                        {BUNDESLAENDER[region.region]?.name || region.region}
                      </span>
                      {isOwn && <span className="text-xs text-primary-500">(Du)</span>}
                    </div>
                  </td>
                  <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400">
                    {region.anzahl_anlagen}
                  </td>
                  <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400">
                    {fmtZahl(region.durchschnitt_kwp, 1)}
                  </td>
                  <td className="py-2 px-3 text-right font-medium text-gray-900 dark:text-white">
                    {fmtZahl(region.durchschnitt_spez_ertrag, 0)}
                  </td>
                  <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400 leading-tight">
                    {region.avg_speicher_ladung_kwh != null
                      ? <><div>{fmtZahl(region.avg_speicher_ladung_kwh, 0)} ↓</div><div className="text-xs text-gray-400 dark:text-gray-500">{region.avg_speicher_entladung_kwh != null ? fmtZahl(region.avg_speicher_entladung_kwh, 0) : '–'} ↑ kWh</div></>
                      : '-'}
                  </td>
                  <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400">
                    {region.avg_wp_jaz != null ? fmtZahl(region.avg_wp_jaz, 1) : '-'}
                  </td>
                  <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400 leading-tight">
                    {region.avg_eauto_km != null
                      ? <><div>{fmtZahl(region.avg_eauto_km, 0)} km</div><div className="text-xs text-gray-400 dark:text-gray-500">{region.avg_eauto_ladung_kwh != null ? `${fmtZahl(region.avg_eauto_ladung_kwh, 0)} kWh` : '–'}</div></>
                      : '-'}
                  </td>
                  <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400 leading-tight">
                    {region.avg_wallbox_kwh != null
                      ? <><div>{fmtZahl(region.avg_wallbox_kwh, 0)} kWh</div><div className="text-xs text-gray-400 dark:text-gray-500">{region.avg_wallbox_pv_anteil != null ? `${fmtZahl(region.avg_wallbox_pv_anteil, 0)} % PV` : '–'}</div></>
                      : '-'}
                  </td>
                  <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400">
                    {region.avg_bkw_kwh != null ? `${fmtZahl(region.avg_bkw_kwh, 0)} kWh` : '-'}
                  </td>
                </tr>
              )
            })}
        </tbody>
      </table>
    </ScrollSchatten>
    </Parkbar>
  )
}

// Re-Export der Icons für den Komposer (Card-Köpfe).
export { MapPin, Sun, Users }
