/**
 * Kurzfrist-Tab: 7-14 Tage PV-Prognose basierend auf Wettervorhersage
 *
 * Unterstützt zwei Prognose-Modi:
 * - Standard: Open-Meteo Forecast API (GHI-basiert)
 * - Solar GTI: Open-Meteo Solar mit GTI-Berechnung für geneigte Module
 */
import { useState, useEffect } from 'react'
import { Sun, Cloud, CloudRain, CloudSnow, CloudLightning, Thermometer, Zap, Settings2, Info } from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import { aussichtenApi, KurzfristPrognose } from '../../api/aussichten'
import { wetterApi, SolarPrognose } from '../../api/wetter'
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'

type PrognoseMode = 'standard' | 'solar-gti'

interface Props {
  anlageId: number
}

// Wetter-Symbol zu Icon
function WetterIcon({ symbol, className = "h-6 w-6" }: { symbol: string; className?: string }) {
  switch (symbol) {
    case 'sunny':
      return <Sun className={`${className} text-yellow-500`} />
    case 'partly_cloudy':
      return <Cloud className={`${className} text-gray-400`} />
    case 'cloudy':
      return <Cloud className={`${className} text-gray-500`} />
    case 'rainy':
    case 'drizzle':
    case 'showers':
      return <CloudRain className={`${className} text-blue-500`} />
    case 'snowy':
    case 'snow_showers':
      return <CloudSnow className={`${className} text-blue-300`} />
    case 'thunderstorm':
      return <CloudLightning className={`${className} text-purple-500`} />
    case 'foggy':
      return <Cloud className={`${className} text-gray-300`} />
    default:
      return <Sun className={`${className} text-yellow-400`} />
  }
}

// Datum formatieren
function formatDatum(datum: string): string {
  const d = new Date(datum)
  return d.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })
}

function formatDatumKurz(datum: string): string {
  const d = new Date(datum)
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
}

// Bewölkung zu Wetter-Symbol mappen (für Solar-Prognose)
function mapWetterSymbol(bewoelkung: number | null | undefined): string {
  if (bewoelkung === null || bewoelkung === undefined) return 'sunny'
  if (bewoelkung < 20) return 'sunny'
  if (bewoelkung < 50) return 'partly_cloudy'
  if (bewoelkung < 80) return 'cloudy'
  return 'cloudy'
}

export default function KurzfristTab({ anlageId }: Props) {
  const [prognose, setPrognose] = useState<KurzfristPrognose | null>(null)
  const [solarPrognose, setSolarPrognose] = useState<SolarPrognose | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tage, setTage] = useState(14)
  const [modus, setModus] = useState<PrognoseMode>('standard')
  const [showModusInfo, setShowModusInfo] = useState(false)

  useEffect(() => {
    loadPrognose()
  }, [anlageId, tage, modus])

  async function loadPrognose() {
    setLoading(true)
    setError(null)
    try {
      if (modus === 'solar-gti') {
        // GTI-basierte Solar-Prognose
        const data = await wetterApi.getSolarPrognose(anlageId, tage, false)
        setSolarPrognose(data)
        setPrognose(null)
      } else {
        // Standard-Prognose
        const data = await aussichtenApi.getKurzfristPrognose(anlageId, tage)
        setPrognose(data)
        setSolarPrognose(null)
      }
    } catch (err: any) {
      setError(err.message || 'Fehler beim Laden der Prognose')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <LoadingSpinner text="Lade Kurzfrist-Prognose..." />
  }

  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  if (!prognose && !solarPrognose) {
    return <Alert type="warning">Keine Prognose verfügbar</Alert>
  }

  // Chart-Daten vorbereiten - je nach Modus
  const chartData = modus === 'solar-gti' && solarPrognose
    ? solarPrognose.tage.map(tag => ({
        datum: formatDatumKurz(tag.datum),
        datumFull: formatDatum(tag.datum),
        pv_kwh: tag.pv_ertrag_kwh,
        sonnenstunden: null,
        temperatur: tag.temperatur_max_c,
        gti: tag.gti_kwh_m2,
      }))
    : prognose?.tageswerte.map(tag => ({
        datum: formatDatumKurz(tag.datum),
        datumFull: formatDatum(tag.datum),
        pv_kwh: tag.pv_prognose_kwh,
        sonnenstunden: tag.sonnenstunden,
        temperatur: tag.temperatur_max_c,
        gti: null,
      })) || []

  // Heute und morgen
  const heute = modus === 'solar-gti' && solarPrognose
    ? { ...solarPrognose.tage[0], pv_prognose_kwh: solarPrognose.tage[0]?.pv_ertrag_kwh, wetter_symbol: mapWetterSymbol(solarPrognose.tage[0]?.bewoelkung_prozent) }
    : prognose?.tageswerte[0]
  const morgen = modus === 'solar-gti' && solarPrognose
    ? { ...solarPrognose.tage[1], pv_prognose_kwh: solarPrognose.tage[1]?.pv_ertrag_kwh, wetter_symbol: mapWetterSymbol(solarPrognose.tage[1]?.bewoelkung_prozent) }
    : prognose?.tageswerte[1]

  // Summen berechnen
  const summeKwh = modus === 'solar-gti' && solarPrognose
    ? solarPrognose.tage.reduce((sum, t) => sum + (t.pv_ertrag_kwh || 0), 0)
    : prognose?.summe_kwh || 0
  const durchschnittKwh = chartData.length > 0 ? summeKwh / chartData.length : 0
  const anlagenleistungKwp = modus === 'solar-gti' && solarPrognose
    ? solarPrognose.anlage.leistung_kwp
    : prognose?.anlagenleistung_kwp || 0
  const datenquelle = modus === 'solar-gti' && solarPrognose
    ? 'Open-Meteo Solar (GTI)'
    : prognose?.datenquelle || ''

  return (
    <div className="space-y-6">
      {/* Prognose-Modus Auswahl */}
      <Card className="p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Settings2 className="h-5 w-5 text-gray-500" />
            <span className="font-medium text-gray-700 dark:text-gray-300">Prognose-Modus:</span>
            <select
              value={modus}
              onChange={(e) => setModus(e.target.value as PrognoseMode)}
              className="input w-auto text-sm"
            >
              <option value="standard">Standard (GHI-basiert)</option>
              <option value="solar-gti">Solar GTI (Modulneigung)</option>
            </select>
            <button
              onClick={() => setShowModusInfo(!showModusInfo)}
              className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              title="Info zum Prognose-Modus"
            >
              <Info className="h-4 w-4" />
            </button>
          </div>
        </div>
        {showModusInfo && (
          <div className="mt-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm text-gray-600 dark:text-gray-400">
            <p className="font-medium mb-1">Prognose-Modi:</p>
            <ul className="list-disc list-inside space-y-1">
              <li><strong>Standard:</strong> Basiert auf horizontaler Globalstrahlung (GHI). Guter Überblick.</li>
              <li><strong>Solar GTI:</strong> Berücksichtigt Modulneigung und -ausrichtung für genauere Prognose. Nutzt Open-Meteo Solar API.</li>
            </ul>
          </div>
        )}
      </Card>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-yellow-100 dark:bg-yellow-900/30 rounded-lg">
              <Zap className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Summe {chartData.length} Tage</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {summeKwh.toFixed(0)} kWh
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <Sun className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Durchschnitt/Tag</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {durchschnittKwh.toFixed(1)} kWh
              </p>
            </div>
          </div>
        </Card>

        {heute && (
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <WetterIcon symbol={heute.wetter_symbol || 'sunny'} className="h-8 w-8" />
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Heute</p>
                <p className="text-xl font-bold text-gray-900 dark:text-white">
                  {(heute.pv_prognose_kwh ?? 0).toFixed(1)} kWh
                </p>
              </div>
            </div>
          </Card>
        )}

        {morgen && (
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <WetterIcon symbol={morgen.wetter_symbol || 'sunny'} className="h-8 w-8" />
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Morgen</p>
                <p className="text-xl font-bold text-gray-900 dark:text-white">
                  {(morgen.pv_prognose_kwh ?? 0).toFixed(1)} kWh
                </p>
              </div>
            </div>
          </Card>
        )}
      </div>

      {/* Wetter-Streifen */}
      <Card className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-gray-900 dark:text-white">
            {modus === 'solar-gti' ? 'Solar-Prognose (GTI)' : 'Wettervorhersage'}
          </h3>
          <select
            value={tage}
            onChange={(e) => setTage(Number(e.target.value))}
            className="input w-auto text-sm"
          >
            <option value={7}>7 Tage</option>
            <option value={14}>14 Tage</option>
            <option value={16}>16 Tage</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <div className="flex gap-2 min-w-max pb-2">
            {modus === 'solar-gti' && solarPrognose ? (
              solarPrognose.tage.map((tag, index) => (
                <div
                  key={tag.datum}
                  className={`flex flex-col items-center p-3 rounded-lg min-w-[80px] ${
                    index === 0
                      ? 'bg-primary-50 dark:bg-primary-900/30 ring-2 ring-primary-500'
                      : 'bg-gray-50 dark:bg-gray-800'
                  }`}
                >
                  <span className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                    {formatDatum(tag.datum)}
                  </span>
                  <WetterIcon symbol={mapWetterSymbol(tag.bewoelkung_prozent)} className="h-8 w-8 my-1" />
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">
                    {tag.pv_ertrag_kwh.toFixed(1)} kWh
                  </span>
                  <div className="flex items-center gap-1 mt-1">
                    <Thermometer className="h-3 w-3 text-gray-400" />
                    <span className="text-xs text-gray-500">
                      {tag.temperatur_max_c?.toFixed(0) ?? '-'}°C
                    </span>
                  </div>
                  {tag.gti_kwh_m2 !== null && tag.gti_kwh_m2 > 0 && (
                    <div className="flex items-center gap-1 mt-1">
                      <Sun className="h-3 w-3 text-orange-500" />
                      <span className="text-xs text-gray-500">
                        {tag.gti_kwh_m2.toFixed(1)} GTI
                      </span>
                    </div>
                  )}
                </div>
              ))
            ) : prognose ? (
              prognose.tageswerte.map((tag, index) => (
                <div
                  key={tag.datum}
                  className={`flex flex-col items-center p-3 rounded-lg min-w-[80px] ${
                    index === 0
                      ? 'bg-primary-50 dark:bg-primary-900/30 ring-2 ring-primary-500'
                      : 'bg-gray-50 dark:bg-gray-800'
                  }`}
                >
                  <span className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                    {formatDatum(tag.datum)}
                  </span>
                  <WetterIcon symbol={tag.wetter_symbol} className="h-8 w-8 my-1" />
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">
                    {tag.pv_prognose_kwh.toFixed(1)} kWh
                  </span>
                  <div className="flex items-center gap-1 mt-1">
                    <Thermometer className="h-3 w-3 text-gray-400" />
                    <span className="text-xs text-gray-500">
                      {tag.temperatur_max_c?.toFixed(0) ?? '-'}°C
                    </span>
                  </div>
                  {tag.sonnenstunden !== null && tag.sonnenstunden > 0 && (
                    <div className="flex items-center gap-1 mt-1">
                      <Sun className="h-3 w-3 text-yellow-500" />
                      <span className="text-xs text-gray-500">
                        {tag.sonnenstunden.toFixed(0)}h
                      </span>
                    </div>
                  )}
                </div>
              ))
            ) : null}
          </div>
        </div>
      </Card>

      {/* Chart */}
      <Card className="p-4">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">PV-Prognose</h3>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis
                dataKey="datum"
                tick={{ fontSize: 12 }}
                className="text-gray-600 dark:text-gray-400"
              />
              <YAxis
                yAxisId="left"
                tick={{ fontSize: 12 }}
                className="text-gray-600 dark:text-gray-400"
                label={{ value: 'kWh', angle: -90, position: 'insideLeft' }}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: 12 }}
                className="text-gray-600 dark:text-gray-400"
                label={{ value: '°C', angle: 90, position: 'insideRight' }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--tooltip-bg, white)',
                  borderColor: 'var(--tooltip-border, #e5e7eb)',
                }}
                formatter={(value: number, name: string) => {
                  if (name === 'pv_kwh') return [`${value.toFixed(1)} kWh`, 'PV-Prognose']
                  if (name === 'sonnenstunden') return [`${value.toFixed(1)} h`, 'Sonnenstunden']
                  if (name === 'temperatur') return [`${value.toFixed(0)} °C`, 'Temperatur']
                  return [value, name]
                }}
              />
              <Legend />
              <Bar
                yAxisId="left"
                dataKey="pv_kwh"
                name="PV-Prognose"
                fill="#eab308"
                radius={[4, 4, 0, 0]}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="temperatur"
                name="Temperatur"
                stroke="#ef4444"
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Detail-Tabelle */}
      <Card className="p-4">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Details</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-2 px-3">Datum</th>
                <th className="text-left py-2 px-3">Wetter</th>
                <th className="text-right py-2 px-3">PV-Prognose</th>
                <th className="text-right py-2 px-3">{modus === 'solar-gti' ? 'GTI' : 'Strahlung'}</th>
                <th className="text-right py-2 px-3">{modus === 'solar-gti' ? 'Bewölkung' : 'Sonnenstunden'}</th>
                <th className="text-right py-2 px-3">Temperatur</th>
                <th className="text-right py-2 px-3">Niederschlag</th>
              </tr>
            </thead>
            <tbody>
              {modus === 'solar-gti' && solarPrognose ? (
                solarPrognose.tage.map((tag, index) => (
                  <tr
                    key={tag.datum}
                    className={`border-b border-gray-100 dark:border-gray-800 ${
                      index === 0 ? 'bg-primary-50 dark:bg-primary-900/20' : ''
                    }`}
                  >
                    <td className="py-2 px-3 font-medium">{formatDatum(tag.datum)}</td>
                    <td className="py-2 px-3">
                      <WetterIcon symbol={mapWetterSymbol(tag.bewoelkung_prozent)} className="h-5 w-5" />
                    </td>
                    <td className="py-2 px-3 text-right font-semibold text-yellow-600">
                      {tag.pv_ertrag_kwh.toFixed(1)} kWh
                    </td>
                    <td className="py-2 px-3 text-right">
                      {tag.gti_kwh_m2?.toFixed(2) ?? '-'} kWh/m²
                    </td>
                    <td className="py-2 px-3 text-right">
                      {tag.bewoelkung_prozent?.toFixed(0) ?? '-'} %
                    </td>
                    <td className="py-2 px-3 text-right">
                      {tag.temperatur_max_c?.toFixed(0) ?? '-'}°C
                    </td>
                    <td className="py-2 px-3 text-right">
                      {tag.niederschlag_mm !== null && tag.niederschlag_mm !== undefined && tag.niederschlag_mm > 0 ? (
                        <span className="text-blue-500">{tag.niederschlag_mm.toFixed(1)} mm</span>
                      ) : (
                        '-'
                      )}
                    </td>
                  </tr>
                ))
              ) : prognose ? (
                prognose.tageswerte.map((tag, index) => (
                  <tr
                    key={tag.datum}
                    className={`border-b border-gray-100 dark:border-gray-800 ${
                      index === 0 ? 'bg-primary-50 dark:bg-primary-900/20' : ''
                    }`}
                  >
                    <td className="py-2 px-3 font-medium">{formatDatum(tag.datum)}</td>
                    <td className="py-2 px-3">
                      <WetterIcon symbol={tag.wetter_symbol} className="h-5 w-5" />
                    </td>
                    <td className="py-2 px-3 text-right font-semibold text-yellow-600">
                      {tag.pv_prognose_kwh.toFixed(1)} kWh
                    </td>
                    <td className="py-2 px-3 text-right">
                      {tag.globalstrahlung_kwh_m2?.toFixed(1) ?? '-'} kWh/m²
                    </td>
                    <td className="py-2 px-3 text-right">
                      {tag.sonnenstunden?.toFixed(1) ?? '-'} h
                    </td>
                    <td className="py-2 px-3 text-right">
                      {tag.temperatur_max_c?.toFixed(0) ?? '-'}°C
                    </td>
                    <td className="py-2 px-3 text-right">
                      {tag.niederschlag_mm !== null && tag.niederschlag_mm > 0 ? (
                        <span className="text-blue-500">{tag.niederschlag_mm.toFixed(1)} mm</span>
                      ) : (
                        '-'
                      )}
                    </td>
                  </tr>
                ))
              ) : null}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Meta-Info */}
      <Card className="p-4 bg-gray-50 dark:bg-gray-800">
        <div className="flex flex-wrap gap-4 text-sm text-gray-500 dark:text-gray-400">
          <span>Anlagenleistung: {anlagenleistungKwp.toFixed(1)} kWp</span>
          {modus === 'solar-gti' && solarPrognose && (
            <>
              <span>Neigung: {solarPrognose.anlage.neigung}°</span>
              <span>Ausrichtung: {solarPrognose.anlage.azimut}°</span>
            </>
          )}
          {modus !== 'solar-gti' && prognose && (
            <span>Systemverluste: {prognose.system_losses_prozent.toFixed(0)}%</span>
          )}
          <span>Datenquelle: {datenquelle}</span>
          <span>Abgerufen: {new Date(
            modus === 'solar-gti' && solarPrognose
              ? solarPrognose.abgerufen_am
              : prognose?.abgerufen_am || new Date().toISOString()
          ).toLocaleString('de-DE')}</span>
        </div>
      </Card>
    </div>
  )
}
