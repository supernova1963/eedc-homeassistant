/**
 * WetterWidget — Aktuelles Wetter + Stundenprognose + PV/Verbrauch-Chart.
 *
 * Breites Layout (volle Breite): Hero links, Stundenverlauf Mitte, KPI rechts.
 * Darunter: PV-Ertrag vs. gestapelter Verbrauch — IST (solid) + Prognose (dashed), volle 24h.
 */

import { useMemo, useState, useEffect } from 'react'
import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from 'recharts'
import ChartTooltip from '../ui/ChartTooltip'
import { Sun, Cloud, CloudRain, CloudSnow, CloudDrizzle, CloudFog, CloudLightning, Droplets, Thermometer, CloudSun, Zap, BatteryCharging } from 'lucide-react'
import type { LiveWetterResponse, TagesverlaufResponse } from '../../api/liveDashboard'

// Wetter-Symbol zu Lucide-Icon Mapping
function WetterIcon({ symbol, className = 'h-5 w-5' }: { symbol: string; className?: string }) {
  switch (symbol) {
    case 'sunny': return <Sun className={`${className} text-yellow-400`} />
    case 'mostly_sunny': return <CloudSun className={`${className} text-yellow-400`} />
    case 'partly_cloudy': return <CloudSun className={`${className} text-yellow-300`} />
    case 'cloudy': return <Cloud className={`${className} text-gray-400`} />
    case 'foggy': return <CloudFog className={`${className} text-gray-400`} />
    case 'drizzle': return <CloudDrizzle className={`${className} text-blue-300`} />
    case 'rainy':
    case 'showers': return <CloudRain className={`${className} text-blue-400`} />
    case 'snowy':
    case 'snow_showers': return <CloudSnow className={`${className} text-blue-200`} />
    case 'thunderstorm': return <CloudLightning className={`${className} text-purple-400`} />
    default: return <Cloud className={`${className} text-gray-400`} />
  }
}

// Verbrauchs-Kategorien für gestapeltes Chart
const VERBRAUCH_KATEGORIEN = [
  { key: 'haushalt', label: 'Haushalt', farbe: '#ef4444' },
  { key: 'batterie_ladung', label: 'Speicher-Ladung', farbe: '#8b5cf6' },
  { key: 'wallbox', label: 'Wallbox', farbe: '#22c55e' },
  { key: 'waermepumpe', label: 'Wärmepumpe', farbe: '#06b6d4' },
  { key: 'sonstige', label: 'Sonstige', farbe: '#9ca3af' },
] as const

interface WetterWidgetProps {
  wetter: LiveWetterResponse | null
  tagesverlauf?: TagesverlaufResponse | null
  loading?: boolean
  anlageId?: number | null
}

type ChartView = 'beides' | 'pv' | 'verbrauch'

export default function WetterWidget({ wetter, tagesverlauf, loading, anlageId }: WetterWidgetProps) {
  const now = new Date()
  const currentHour = now.getHours()

  // Chart-Ansicht (PV / Verbrauch / Beides) — pro Anlage in localStorage
  const storageKey = anlageId != null ? `wetterChartView_${anlageId}` : 'wetterChartView'
  const [chartView, setChartView] = useState<ChartView>('beides')
  useEffect(() => {
    const saved = localStorage.getItem(storageKey)
    if (saved === 'pv' || saved === 'verbrauch' || saved === 'beides') {
      setChartView(saved)
    } else {
      setChartView('beides')
    }
  }, [storageKey])
  const updateChartView = (v: ChartView) => {
    setChartView(v)
    localStorage.setItem(storageKey, v)
  }
  const showPv = chartView === 'pv' || chartView === 'beides'
  const showVerbrauch = chartView === 'verbrauch' || chartView === 'beides'

  // IST-Daten aus Tagesverlauf aggregieren — gestapelt nach Kategorie
  const { istDaten, vorhandeneKategorien, serienKategorien } = useMemo(() => {
    if (!tagesverlauf?.punkte?.length || !tagesverlauf?.serien?.length) {
      return { istDaten: null, vorhandeneKategorien: new Set<string>(), serienKategorien: new Set<string>() }
    }

    const pvKeys = tagesverlauf.serien
      .filter(s => s.kategorie === 'pv')
      .map(s => s.key)

    // Kategorien der Serien indexieren
    const keyKategorie: Record<string, string> = {}
    for (const s of tagesverlauf.serien) {
      keyKategorie[s.key] = s.kategorie
    }
    // E-Auto überspringen wenn Wallbox existiert (Wallbox misst bereits die Ladeleistung)
    const hasWallbox = tagesverlauf.serien.some(s => s.kategorie === 'wallbox')
    const skipKeys = new Set(
      tagesverlauf.serien
        .filter(s => s.kategorie === 'eauto' && hasWallbox)
        .map(s => s.key)
    )

    const kategorienGesehen = new Set<string>()
    const result: Record<number, {
      pv: number
      haushalt: number
      batterie_ladung: number
      wallbox: number
      waermepumpe: number
      sonstige: number
      verbrauch_gesamt: number
    }> = {}

    for (const punkt of tagesverlauf.punkte) {
      const h = parseInt(punkt.zeit.split(':')[0])
      if (h > currentHour) continue

      let pvSum = 0
      let haushalt = 0
      let batterie_ladung = 0
      let wallbox = 0
      let waermepumpe = 0
      let sonstige = 0
      const netzValue = punkt.werte['netz'] ?? 0

      for (const [key, val] of Object.entries(punkt.werte)) {
        if (skipKeys.has(key)) continue
        const kat = keyKategorie[key]

        if (pvKeys.includes(key)) {
          pvSum += val
        } else if (kat === 'batterie') {
          // Batterie: negativ = Ladung (Verbrauch), positiv = Entladung (Quelle)
          if (val < 0) {
            batterie_ladung += Math.abs(val)
            kategorienGesehen.add('batterie_ladung')
          }
        } else if (kat === 'netz') {
          // Netz wird separat behandelt (in Energiebilanz)
        } else if (kat === 'haushalt') {
          haushalt += Math.abs(val)
          if (val !== 0) kategorienGesehen.add('haushalt')
        } else if (kat === 'wallbox' || kat === 'eauto') {
          wallbox += Math.abs(val)
          if (val !== 0) kategorienGesehen.add('wallbox')
        } else if (kat === 'waermepumpe') {
          waermepumpe += Math.abs(val)
          if (val !== 0) kategorienGesehen.add('waermepumpe')
        } else if (kat && kat !== 'pv') {
          sonstige += Math.abs(val)
          if (val !== 0) kategorienGesehen.add('sonstige')
        }
      }

      // Energiebilanz: Gesamtverbrauch = PV + Netz
      const verbrauch_gesamt = Math.max(0, pvSum + netzValue)

      // Wenn wir keine Kategorien-Aufschlüsselung haben,
      // Haushalt als Residual berechnen
      const kategorien_summe = haushalt + batterie_ladung + wallbox + waermepumpe + sonstige
      if (kategorien_summe === 0 && verbrauch_gesamt > 0) {
        haushalt = verbrauch_gesamt
        kategorienGesehen.add('haushalt')
      }

      result[h] = {
        pv: pvSum,
        haushalt,
        batterie_ladung,
        wallbox,
        waermepumpe,
        sonstige,
        verbrauch_gesamt,
      }
    }

    // Nur Kategorien behalten, die tatsächlich als Investition/Serie existieren
    const serienKategorien = new Set(tagesverlauf.serien.map(s => {
      if (s.kategorie === 'batterie') return 'batterie_ladung'
      if (s.kategorie === 'eauto') return 'wallbox'
      return s.kategorie
    }))
    // Haushalt ist immer erlaubt (Residualwert)
    serienKategorien.add('haushalt')
    for (const kat of kategorienGesehen) {
      if (!serienKategorien.has(kat)) kategorienGesehen.delete(kat)
    }

    return {
      istDaten: Object.keys(result).length > 0 ? result : null,
      vorhandeneKategorien: kategorienGesehen,
      serienKategorien,
    }
  }, [tagesverlauf, currentHour])

  // Chart-Daten: 24h mit IST (gestapelt) + Prognose
  const chartData = useMemo(() => {
    if (!wetter?.verfuegbar) return []

    // Prognose-Daten indexieren
    const prognoseMap: Record<number, { pv: number; verbrauch: number; pv_ml: number | null }> = {}
    for (const v of wetter.verbrauchsprofil) {
      const h = parseInt(v.zeit.replace(':00', ''))
      prognoseMap[h] = { pv: v.pv_ertrag_kw, verbrauch: v.verbrauch_kw, pv_ml: v.pv_ml_prognose_kw ?? null }
    }

    const data: Array<Record<string, number | string | null>> = []

    for (let h = 0; h < 24; h++) {
      const punkt: Record<string, number | string | null> = { zeit: String(h) }
      const prognose = prognoseMap[h]
      const ist = istDaten?.[h]

      // Prognose immer setzen (volle 24h, für Vergleich)
      if (prognose) {
        punkt.pv_prognose = prognose.pv
        punkt.verbrauch_prognose = prognose.verbrauch
        if (prognose.pv_ml != null) {
          punkt.pv_ml = prognose.pv_ml
        }
      }

      if (h <= currentHour) {
        // Vergangene + aktuelle Stunde: IST (gestapelt)
        if (ist) {
          punkt.pv_ist = ist.pv
          // 0 als 0 belassen (nicht null) — Recharts braucht das für korrektes Stacking
          punkt.haushalt_ist = ist.haushalt
          punkt.batterie_ladung_ist = ist.batterie_ladung
          punkt.wallbox_ist = ist.wallbox
          punkt.waermepumpe_ist = ist.waermepumpe
          punkt.sonstige_ist = ist.sonstige
        } else if (prognose) {
          // Fallback auf Prognose wenn kein IST
          punkt.pv_ist = prognose.pv
          punkt.haushalt_ist = prognose.verbrauch
        }
      }

      data.push(punkt)
    }

    return data
  }, [wetter, istDaten, currentHour])

  // Echte Gerätenamen für "Sonstige" aus Tagesverlauf-Serien
  const sonstigeLabel = useMemo(() => {
    if (!tagesverlauf?.serien?.length) return 'Sonstige'
    const namen = tagesverlauf.serien
      .filter(s => s.kategorie === 'sonstige')
      .map(s => s.label)
    return namen.length > 0 ? namen.join(', ') : 'Sonstige'
  }, [tagesverlauf?.serien])

  // Nur vorhandene Kategorien in Legende anzeigen
  const aktiveKategorien = useMemo(() =>
    VERBRAUCH_KATEGORIEN
      .filter(k => vorhandeneKategorien.has(k.key))
      .map(k => k.key === 'sonstige' ? { ...k, label: sonstigeLabel } : k),
    [vorhandeneKategorien, sonstigeLabel]
  )

  // Stunden-Index für 24h-Timeline (Wetter-Icons über dem Chart)
  const stundenMap = useMemo(() => {
    if (!wetter?.stunden) return {}
    const map: Record<number, (typeof wetter.stunden)[0]> = {}
    for (const s of wetter.stunden) {
      const h = parseInt(s.zeit.split(':')[0])
      map[h] = s
    }
    return map
  }, [wetter?.stunden])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-600" />
      </div>
    )
  }

  if (!wetter?.verfuegbar) {
    return (
      <div className="text-center py-6">
        <Cloud className="h-8 w-8 text-gray-400 mx-auto mb-2" />
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Keine Wetterdaten verfügbar
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
          Standort-Koordinaten in den Stammdaten hinterlegen
        </p>
      </div>
    )
  }

  const { aktuell, stunden } = wetter

  // Tooltip-Labels für gestapelte Kategorien
  const tooltipLabels: Record<string, string> = {
    pv_ist: 'PV (IST)',
    pv_prognose: 'PV (Prognose)',
    pv_ml: 'PV (ML-Prognose)',
    haushalt_ist: 'Haushalt',
    batterie_ladung_ist: 'Speicher-Ladung',
    wallbox_ist: 'Wallbox',
    waermepumpe_ist: 'Wärmepumpe',
    sonstige_ist: sonstigeLabel,
    verbrauch_prognose: 'Verbrauch (Prognose)',
  }

  return (
    <div className="space-y-4">
      {/* Obere Zeile: Hero + KPIs */}
      <div className="flex flex-col sm:flex-row gap-4 sm:gap-6">
        {/* Aktuelles Wetter — Hero */}
        {aktuell && (
          <div className="flex items-center gap-3 shrink-0">
            <WetterIcon symbol={aktuell.wetter_symbol} className="h-12 w-12" />
            <div>
              <div className="text-4xl font-bold text-gray-900 dark:text-white leading-none">
                {aktuell.temperatur_c !== null ? `${aktuell.temperatur_c.toFixed(0)}°` : '–'}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {wetterBeschreibung(aktuell.wetter_symbol)}
              </div>
            </div>
          </div>
        )}

        {/* KPIs */}
        <div className="flex flex-wrap sm:flex-row gap-3 sm:gap-4 text-xs">
          {wetter.temperatur_min_c !== null && wetter.temperatur_max_c !== null && (
            <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
              <Thermometer className="h-3.5 w-3.5" />
              <span>{wetter.temperatur_min_c.toFixed(0)}° / {wetter.temperatur_max_c.toFixed(0)}°</span>
            </div>
          )}
          {wetter.sonnenstunden !== null && (
            <div className="flex items-center gap-1.5 text-yellow-600 dark:text-yellow-400">
              <Sun className="h-3.5 w-3.5" />
              <span>{(() => { const h = Math.floor(wetter.sonnenstunden!); const m = Math.round((wetter.sonnenstunden! - h) * 60); return `${h}h ${m.toString().padStart(2, '0')}m Sonne` })()}</span>
            </div>
          )}
{/* SA/SU/Noon werden als vertikale Linien im Chart angezeigt */}
          {wetter.pv_prognose_kwh !== null && (
            <div className="flex items-center gap-1.5 text-green-600 dark:text-green-400 font-medium"
                 title="EEDC PV-Tagesprognose (GTI-basiert)">
              <BatteryCharging className="h-3.5 w-3.5" />
              <span>~{wetter.pv_prognose_kwh} kWh PV</span>
            </div>
          )}
          {wetter.grundlast_kw != null && wetter.grundlast_kw > 0 && (
            <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
              <Zap className="h-3.5 w-3.5" />
              <span>Grundlast {(wetter.grundlast_kw * 1000).toFixed(0)} W</span>
            </div>
          )}
          {stunden.some((s) => (s.niederschlag_mm || 0) > 0) && (
            <div className="flex items-center gap-1.5 text-blue-500 dark:text-blue-400">
              <Droplets className="h-3.5 w-3.5" />
              <span>
                {stunden.reduce((sum, s) => sum + (s.niederschlag_mm || 0), 0).toFixed(1)} mm
              </span>
            </div>
          )}
        </div>
      </div>

      {/* PV-Ertrag vs. Verbrauch — IST (gestapelt) + Prognose */}
      {chartData.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-1 gap-2 flex-wrap">
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {chartView === 'pv' ? 'PV-Ertrag — IST + Prognose'
                : chartView === 'verbrauch' ? 'Verbrauch — IST + Prognose'
                : 'PV-Ertrag vs. Verbrauch — IST + Prognose'}
            </div>
            <div className="inline-flex rounded-lg border border-gray-200 dark:border-gray-700 text-[10px] overflow-hidden shrink-0">
              {([
                { k: 'pv', label: 'Nur PV' },
                { k: 'verbrauch', label: 'Nur Verbrauch' },
                { k: 'beides', label: 'Beides' },
              ] as const).map(({ k, label }) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => updateChartView(k)}
                  className={`px-2 py-1 transition-colors ${
                    chartView === k
                      ? 'bg-primary-600 text-white'
                      : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                  }`}
                  title={`Chart: ${label}`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {/* Wetter-Timeline: 24h-Grid, aligned mit Chart-X-Achse */}
          {/* Chart-Margins: left=-20 + YAxis ~60px = ~40px offset, right=5px */}
          <div className="flex" style={{ paddingLeft: 40, paddingRight: 5 }}>
            {Array.from({ length: 24 }, (_, h) => {
              const s = stundenMap[h]
              const istJetzt = h === currentHour
              const istVergangen = h < currentHour
              return (
                <div
                  key={h}
                  className={`flex-1 flex flex-col items-center py-0.5 rounded transition-opacity ${
                    istVergangen ? 'opacity-40' : ''
                  } ${istJetzt ? 'ring-1 ring-primary-400 bg-primary-50 dark:bg-primary-900/20' : ''}`}
                  title={s ? `${s.zeit}: ${s.temperatur_c?.toFixed(1)}°C, ${s.globalstrahlung_wm2?.toFixed(0)} W/m²` : `${h}:00`}
                >
                  {s ? (
                    <>
                      <WetterIcon symbol={s.wetter_symbol} className="h-4 w-4" />
                      <span className="text-[9px] text-gray-600 dark:text-gray-400 leading-none">
                        {s.temperatur_c !== null ? `${s.temperatur_c.toFixed(0)}°` : ''}
                      </span>
                    </>
                  ) : (
                    <div className="h-4" />
                  )}
                </div>
              )
            })}
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
              <defs>
                {/* PV-Gradienten */}
                <linearGradient id="pvIstGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#eab308" stopOpacity={0.5} />
                  <stop offset="95%" stopColor="#eab308" stopOpacity={0.1} />
                </linearGradient>
                <linearGradient id="pvProgGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#eab308" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#eab308" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="pvMlGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a855f7" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#a855f7" stopOpacity={0.02} />
                </linearGradient>
                {/* Verbrauch-Gradienten pro Kategorie */}
                <linearGradient id="haushaltGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0.05} />
                </linearGradient>
                <linearGradient id="batterieGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.6} />
                  <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0.2} />
                </linearGradient>
                <linearGradient id="wallboxGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22c55e" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0.05} />
                </linearGradient>
                <linearGradient id="wpGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.05} />
                </linearGradient>
                <linearGradient id="sonstigeGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#9ca3af" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#9ca3af" stopOpacity={0.05} />
                </linearGradient>
                {/* Prognose-Verbrauch */}
                <linearGradient id="vrbProgGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="zeit"
                tick={{ fontSize: 10 }}
                className="fill-gray-400 dark:fill-gray-500"
                interval={2}
              />
              <YAxis
                tick={{ fontSize: 10 }}
                className="fill-gray-400 dark:fill-gray-500"
                tickFormatter={(v: number) => `${v.toFixed(1)}`}
                label={{ value: 'kW', angle: -90, position: 'insideLeft', offset: 25, fontSize: 10, className: 'fill-gray-400 dark:fill-gray-500' }}
              />
              <Tooltip content={<ChartTooltip
                labelFormatter={(label) => `${label}:00 Uhr`}
                nameFormatter={(name) => tooltipLabels[name] ?? name}
                formatter={(value, name) => {
                  if (value === null || value === undefined) return null
                  // Verbrauchs-Kategorien nur anzeigen, wenn Investition existiert
                  if (name.endsWith('_ist')) {
                    const katKey = name.replace('_ist', '')
                    if (!serienKategorien.has(katKey)) return null
                  }
                  return `${value.toFixed(2)} kW`
                }}
                itemSorter={() => 0}
              />} />
              {/* Aktuelle Stunde — Trennlinie IST/Prognose */}
              <ReferenceLine
                x={String(currentHour)}
                stroke="#6366f1"
                strokeDasharray="3 3"
                strokeWidth={1}
                label={{ value: 'Jetzt', position: 'top', fontSize: 9, fill: '#6366f1' }}
              />
              {/* Sonnenaufgang */}
              {wetter.sunrise && (
                <ReferenceLine
                  x={String(parseInt(wetter.sunrise.split(':')[0]))}
                  stroke="#f59e0b"
                  strokeDasharray="4 3"
                  strokeWidth={0.8}
                  label={{ value: `SA ${wetter.sunrise}`, position: 'insideTopLeft', fontSize: 10, fill: '#f59e0b' }}
                />
              )}
              {/* Solar Noon */}
              {wetter.solar_noon && (
                <ReferenceLine
                  x={String(parseInt(wetter.solar_noon.split(':')[0]))}
                  stroke="#f97316"
                  strokeDasharray="4 3"
                  strokeWidth={0.8}
                  label={{ value: `Noon ${wetter.solar_noon}`, position: 'insideTopLeft', fontSize: 10, fill: '#f97316' }}
                />
              )}
              {/* Sonnenuntergang */}
              {wetter.sunset && (
                <ReferenceLine
                  x={String(parseInt(wetter.sunset.split(':')[0]))}
                  stroke="#f59e0b"
                  strokeDasharray="4 3"
                  strokeWidth={0.8}
                  label={{ value: `SU ${wetter.sunset}`, position: 'insideTopLeft', fontSize: 10, fill: '#f59e0b' }}
                />
              )}

              {/* IST: PV — solid, kräftig (kein Stack) */}
              {showPv && (
                <Area
                  type="monotone"
                  dataKey="pv_ist"
                  stroke="#eab308"
                  fill="url(#pvIstGrad)"
                  strokeWidth={2}
                  connectNulls={false}
                  dot={false}
                />
              )}

              {/* IST: Gestapelter Verbrauch */}
              {showVerbrauch && (
                <Area
                  type="monotone"
                  dataKey="haushalt_ist"
                  stackId="verbrauch"
                  stroke="#ef4444"
                  fill="url(#haushaltGrad)"
                  strokeWidth={1.5}
                  connectNulls={false}
                  dot={false}
                />
              )}
              {showVerbrauch && (
                <Area
                  type="monotone"
                  dataKey="batterie_ladung_ist"
                  stackId="verbrauch"
                  stroke="#8b5cf6"
                  fill="url(#batterieGrad)"
                  strokeWidth={1.5}
                  connectNulls={false}
                  dot={false}
                />
              )}
              {showVerbrauch && (
                <Area
                  type="monotone"
                  dataKey="wallbox_ist"
                  stackId="verbrauch"
                  stroke="#22c55e"
                  fill="url(#wallboxGrad)"
                  strokeWidth={1.5}
                  connectNulls={false}
                  dot={false}
                />
              )}
              {showVerbrauch && (
                <Area
                  type="monotone"
                  dataKey="waermepumpe_ist"
                  stackId="verbrauch"
                  stroke="#06b6d4"
                  fill="url(#wpGrad)"
                  strokeWidth={1.5}
                  connectNulls={false}
                  dot={false}
                />
              )}
              {showVerbrauch && (
                <Area
                  type="monotone"
                  dataKey="sonstige_ist"
                  stackId="verbrauch"
                  stroke="#9ca3af"
                  fill="url(#sonstigeGrad)"
                  strokeWidth={1}
                  connectNulls={false}
                  dot={false}
                />
              )}

              {/* Prognose: PV — dashed, blass */}
              {showPv && (
                <Area
                  type="monotone"
                  dataKey="pv_prognose"
                  stroke="#eab308"
                  fill="url(#pvProgGrad)"
                  strokeWidth={1.5}
                  strokeDasharray="6 3"
                  connectNulls={false}
                  dot={false}
                />
              )}
              {/* ML-Prognose: PV — dotted, lila */}
              {showPv && (
                <Area
                  type="monotone"
                  dataKey="pv_ml"
                  stroke="#a855f7"
                  fill="url(#pvMlGrad)"
                  strokeWidth={1.5}
                  strokeDasharray="3 3"
                  connectNulls={false}
                  dot={false}
                />
              )}
              {/* Prognose: Verbrauch — dashed, blass (nur Gesamt) */}
              {showVerbrauch && (
                <Area
                  type="monotone"
                  dataKey="verbrauch_prognose"
                  stroke="#ef4444"
                  fill="url(#vrbProgGrad)"
                  strokeWidth={1}
                  strokeDasharray="4 2"
                  connectNulls={false}
                  dot={false}
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
          {/* Legende */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-gray-500 dark:text-gray-400 mt-1 justify-center">
            {showPv && (
              <span className="flex items-center gap-1">
                <span className="w-3 h-0.5 bg-yellow-500 rounded" /> PV (IST)
              </span>
            )}
            {showPv && (
              <span className="flex items-center gap-1">
                <span className="w-3 h-0.5 bg-yellow-500/40 rounded" style={{ borderTop: '1px dashed #eab308' }} /> PV (Prognose)
              </span>
            )}
            {showPv && wetter.sfml_prognose_kwh != null && (
              <span className="flex items-center gap-1">
                <span className="w-3 h-0.5 bg-purple-500/40 rounded" style={{ borderTop: '1.5px dotted #a855f7' }} /> PV (ML)
              </span>
            )}
            {showVerbrauch && aktiveKategorien.map(k => (
              <span key={k.key} className="flex items-center gap-1">
                <span className="w-2.5 h-2 rounded-sm" style={{ backgroundColor: k.farbe, opacity: 0.7 }} /> {k.label}
              </span>
            ))}
            {showVerbrauch && (
              <span className="flex items-center gap-1"
                    title={wetter.profil_typ?.startsWith('individuell')
                      ? `Basiert auf ${wetter.profil_tage ?? '?'} Tagen ${wetter.profil_typ === 'individuell_wochenende' ? 'Wochenende' : 'Werktag'}-History (${wetter.profil_quelle === 'mqtt' ? 'MQTT' : 'HA'})`
                      : 'Standardlastprofil — wird durch individuelles Profil ersetzt sobald History verfügbar'
                    }>
                <span className="w-3 h-0.5 bg-red-400/40 rounded" style={{ borderTop: '1px dashed #ef4444' }} />
                {wetter.profil_typ?.startsWith('individuell')
                  ? `Verbr. (ind., ${wetter.profil_typ === 'individuell_wochenende' ? 'WE' : 'WT'})`
                  : 'Verbr. (BDEW H0)'
                }
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function wetterBeschreibung(symbol: string): string {
  switch (symbol) {
    case 'sunny': return 'Sonnig'
    case 'partly_cloudy': return 'Teilweise bewölkt'
    case 'cloudy': return 'Bewölkt'
    case 'foggy': return 'Nebelig'
    case 'drizzle': return 'Nieselregen'
    case 'rainy': return 'Regen'
    case 'showers': return 'Schauer'
    case 'snowy': return 'Schnee'
    case 'snow_showers': return 'Schneeschauer'
    case 'thunderstorm': return 'Gewitter'
    default: return 'Bewölkt'
  }
}
