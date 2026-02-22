/**
 * Community Regional Tab
 *
 * Geografische Vergleiche:
 * - Regionale Position und Ranking
 * - Bundesland-Karte (Choropleth nach spez. Ertrag)
 * - Bundesland-Vergleich (tabellarisch)
 * - Regionale Insights
 */

import { useState, useEffect, useMemo } from 'react'
import { ComposableMap, Geographies, Geography } from 'react-simple-maps'
import {
  MapPin,
  Trophy,
  TrendingUp,
  TrendingDown,
  Users,
  Sun,
} from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import { communityApi } from '../../api'
import type { CommunityBenchmarkResponse, ZeitraumTyp, RegionStatistik } from '../../api/community'
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
  if (max === min) return '#fbbf24'
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)))
  // Farbverlauf: #dbeafe (hellblau, niedrig) → #fbbf24 (gelb, hoch)
  const r = Math.round(219 + (251 - 219) * t)
  const g = Math.round(234 + (191 - 234) * t)
  const b = Math.round(254 + (36 - 254) * t)
  return `rgb(${r},${g},${b})`
}

interface ChoroplethKarteProps {
  allRegions: RegionStatistik[]
  eigeneRegion: string | null
}

function ChoroplethKarte({ allRegions, eigeneRegion }: ChoroplethKarteProps) {
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
        <Geographies geography="/deutschland-bundeslaender.geo.json">
          {({ geographies }) =>
            geographies.map(geo => {
              const code = (geo.properties.id as string).replace('DE-', '')
              const wert = regionMap[code]
              const isOwn = code === eigeneRegion
              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill={wert !== undefined ? interpolateColor(wert, min, max) : '#e5e7eb'}
                  stroke={isOwn ? '#1d4ed8' : '#fff'}
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

      {/* Tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 shadow-lg pointer-events-none text-sm"
          style={{ left: tooltip.x + 12, top: tooltip.y - 40 }}
        >
          <p className="font-medium text-gray-900 dark:text-white">{tooltip.name}</p>
          <p className="text-blue-600 dark:text-blue-400 font-medium">{tooltip.wert.toFixed(0)} kWh/kWp</p>
          {tooltip.region && (
            <div className="mt-1 pt-1 border-t border-gray-100 dark:border-gray-700 space-y-0.5 text-xs text-gray-500 dark:text-gray-400">
              <p>{tooltip.region.anzahl_anlagen} Anlage{tooltip.region.anzahl_anlagen !== 1 ? 'n' : ''} · Ø {tooltip.region.durchschnitt_kwp.toFixed(1)} kWp</p>
              {tooltip.region.avg_speicher_ladung_kwh != null && <p>🔋 {tooltip.region.avg_speicher_ladung_kwh.toFixed(0)} ↑ / {tooltip.region.avg_speicher_entladung_kwh?.toFixed(0) ?? '–'} ↓ kWh/Mon</p>}
              {tooltip.region.avg_wp_jaz != null && <p>♨️ JAZ {tooltip.region.avg_wp_jaz.toFixed(1)}</p>}
              {tooltip.region.avg_eauto_km != null && <p>🚗 {tooltip.region.avg_eauto_km.toFixed(0)} km/Mon · {tooltip.region.avg_eauto_ladung_kwh != null ? `${tooltip.region.avg_eauto_ladung_kwh.toFixed(0)} kWh zuhause` : '–'}</p>}
              {tooltip.region.avg_wallbox_kwh != null && <p>🔌 {tooltip.region.avg_wallbox_kwh.toFixed(0)} kWh/Mon{tooltip.region.avg_wallbox_pv_anteil != null ? ` · ${tooltip.region.avg_wallbox_pv_anteil.toFixed(0)}% PV` : ''}</p>}
              {tooltip.region.avg_bkw_kwh != null && <p>🪟 {tooltip.region.avg_bkw_kwh.toFixed(0)} kWh/Mon</p>}
            </div>
          )}
        </div>
      )}

      {/* Legende */}
      <div className="flex items-center gap-2 mt-2 justify-center">
        <span className="text-xs text-gray-500">{min.toFixed(0)}</span>
        <div
          className="h-3 w-32 rounded"
          style={{ background: `linear-gradient(to right, ${interpolateColor(min, min, max)}, ${interpolateColor(max, min, max)})` }}
        />
        <span className="text-xs text-gray-500">{max.toFixed(0)} kWh/kWp</span>
      </div>
      {eigeneRegion && (
        <p className="text-xs text-center text-blue-600 dark:text-blue-400 mt-1">
          Dein Bundesland: blauer Rahmen
        </p>
      )}
    </div>
  )
}

interface RegionalTabProps {
  anlageId: number
  zeitraum: ZeitraumTyp
}

export default function RegionalTab({ anlageId, zeitraum }: RegionalTabProps) {
  const [benchmark, setBenchmark] = useState<CommunityBenchmarkResponse | null>(null)
  const [allRegions, setAllRegions] = useState<RegionStatistik[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Benchmark und regionale Statistiken laden
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      setError(null)
      try {
        const [benchmarkData, regionsData] = await Promise.all([
          communityApi.getBenchmark(anlageId, zeitraum),
          communityApi.getRegionalStatistics().catch(() => []),
        ])
        setBenchmark(benchmarkData)
        setAllRegions(regionsData)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [anlageId, zeitraum])

  // Regionale Kennzahlen berechnen
  const regionalStats = useMemo(() => {
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
      {
        name: 'Du',
        wert: regionalStats.spezErtrag,
        fill: 'var(--color-primary-500, #3b82f6)',
      },
      {
        name: regionalStats.regionName,
        wert: regionalStats.regionDurchschnitt,
        fill: '#60a5fa',
      },
      {
        name: 'Community',
        wert: regionalStats.communityDurchschnitt,
        fill: '#9ca3af',
      },
    ]
  }, [regionalStats])

  if (loading) {
    return <LoadingSpinner text="Lade regionale Daten..." />
  }

  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  if (!benchmark || !regionalStats) {
    return null
  }

  return (
    <div className="space-y-6">
      {/* Zeitraum-Hinweis */}
      <div className="flex items-center justify-end">
        <span className="text-sm text-gray-500 dark:text-gray-400">
          Betrachtungszeitraum: {benchmark.zeitraum_label}
        </span>
      </div>

      {/* Regionale Position */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Dein Bundesland */}
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30">
              <MapPin className="h-5 w-5 text-blue-500" />
            </div>
            <span className="text-sm text-gray-500 dark:text-gray-400">Dein Standort</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-gray-900 dark:text-white">
              {regionalStats.regionName}
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {regionalStats.anzahlAnlagen} Anlagen in der Region
          </p>
        </Card>

        {/* Rang in Region */}
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-lg bg-yellow-100 dark:bg-yellow-900/30">
              <Trophy className="h-5 w-5 text-yellow-500" />
            </div>
            <span className="text-sm text-gray-500 dark:text-gray-400">Rang in {BUNDESLAENDER[regionalStats.region]?.kurzname || regionalStats.region}</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-gray-900 dark:text-white">
              #{regionalStats.rang}
            </span>
            <span className="text-gray-500 dark:text-gray-400">
              von {regionalStats.anzahlAnlagen}
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Besser als {regionalStats.perzentilRegion}% in deiner Region
          </p>
        </Card>

        {/* Abweichung vom Regions-Durchschnitt */}
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className={`p-2 rounded-lg ${
              regionalStats.abweichungRegion >= 0
                ? 'bg-green-100 dark:bg-green-900/30'
                : 'bg-red-100 dark:bg-red-900/30'
            }`}>
              {regionalStats.abweichungRegion >= 0 ? (
                <TrendingUp className="h-5 w-5 text-green-500" />
              ) : (
                <TrendingDown className="h-5 w-5 text-red-500" />
              )}
            </div>
            <span className="text-sm text-gray-500 dark:text-gray-400">vs. Region</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className={`text-3xl font-bold ${
              regionalStats.abweichungRegion >= 0
                ? 'text-green-600 dark:text-green-400'
                : 'text-red-600 dark:text-red-400'
            }`}>
              {regionalStats.abweichungRegion >= 0 ? '+' : ''}
              {regionalStats.abweichungRegion.toFixed(1)}%
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Ø Region: {regionalStats.regionDurchschnitt.toFixed(0)} kWh/kWp
          </p>
        </Card>
      </div>

      {/* Vergleichs-Chart */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Sun className="h-5 w-5 text-primary-500" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Spezifischer Ertrag im Vergleich
          </h3>
        </div>

        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={vergleichsData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={true} vertical={false} />
              <XAxis
                type="number"
                tick={{ fill: '#6b7280', fontSize: 12 }}
                domain={[0, 'auto']}
                label={{
                  value: 'kWh/kWp',
                  position: 'bottom',
                  style: { fill: '#6b7280', fontSize: 12 },
                }}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: '#6b7280', fontSize: 12 }}
                width={100}
              />
              <Tooltip
                formatter={(value: number) => [`${value.toFixed(0)} kWh/kWp`, 'Spez. Ertrag']}
                contentStyle={{
                  background: 'rgba(255,255,255,0.95)',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                }}
              />
              <Bar dataKey="wert" radius={[0, 4, 4, 0]}>
                {vergleichsData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Regionale Insights */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Users className="h-5 w-5 text-primary-500" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Regionale Einordnung
          </h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Region vs. Community */}
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
                {regionalStats.abweichungCommunity.toFixed(1)}%
              </span>
              <span className="text-gray-500 dark:text-gray-400">
                {regionalStats.abweichungCommunity >= 0 ? 'über' : 'unter'} dem Durchschnitt
              </span>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Deine Region liegt {regionalStats.abweichungCommunity >= 0 ? 'über' : 'unter'} dem
              bundesweiten Community-Durchschnitt von {regionalStats.communityDurchschnitt.toFixed(0)} kWh/kWp.
            </p>
          </div>

          {/* Deine Anlage */}
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
                <span className="text-gray-900 dark:text-white">{benchmark.anlage.neigung_grad}°</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 dark:text-gray-400">Leistung:</span>
                <span className="text-gray-900 dark:text-white">{benchmark.anlage.kwp} kWp</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 dark:text-gray-400">Installation:</span>
                <span className="text-gray-900 dark:text-white">{benchmark.anlage.installation_jahr}</span>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Deutschland-Karte (Choropleth) */}
      {allRegions.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <MapPin className="h-5 w-5 text-blue-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Spezifischer Ertrag nach Bundesland
            </h3>
          </div>

          <ChoroplethKarte
            allRegions={allRegions}
            eigeneRegion={benchmark?.anlage.region ?? null}
          />
        </Card>
      )}

      {/* Bundesländer-Übersicht */}
      {allRegions.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <MapPin className="h-5 w-5 text-green-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Alle Regionen im Vergleich
            </h3>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="text-left py-2 px-3 text-gray-500 font-medium">Region</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">Anlagen</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">Ø kWp</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">Ø kWh/kWp</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium" title="Ø Ladung ↑ / Entladung ↓ pro Monat (kWh)">🔋 Ladung/Entl.</th>
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
                              index < 3 ? 'text-yellow-600' : 'text-gray-400'
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
                          {region.durchschnitt_kwp.toFixed(1)}
                        </td>
                        <td className="py-2 px-3 text-right font-medium text-gray-900 dark:text-white">
                          {region.durchschnitt_spez_ertrag.toFixed(0)}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400 leading-tight">
                          {region.avg_speicher_ladung_kwh != null
                            ? <><div>{region.avg_speicher_ladung_kwh.toFixed(0)} ↑</div><div className="text-xs text-gray-400">{region.avg_speicher_entladung_kwh?.toFixed(0) ?? '–'} ↓ kWh</div></>
                            : '-'}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400">
                          {region.avg_wp_jaz != null ? region.avg_wp_jaz.toFixed(1) : '-'}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400 leading-tight">
                          {region.avg_eauto_km != null
                            ? <><div>{region.avg_eauto_km.toFixed(0)} km</div><div className="text-xs text-gray-400">{region.avg_eauto_ladung_kwh != null ? `${region.avg_eauto_ladung_kwh.toFixed(0)} kWh` : '–'}</div></>
                            : '-'}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400 leading-tight">
                          {region.avg_wallbox_kwh != null
                            ? <><div>{region.avg_wallbox_kwh.toFixed(0)} kWh</div><div className="text-xs text-gray-400">{region.avg_wallbox_pv_anteil != null ? `${region.avg_wallbox_pv_anteil.toFixed(0)}% PV` : '–'}</div></>
                            : '-'}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400">
                          {region.avg_bkw_kwh != null ? `${region.avg_bkw_kwh.toFixed(0)} kWh` : '-'}
                        </td>
                      </tr>
                    )
                  })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
