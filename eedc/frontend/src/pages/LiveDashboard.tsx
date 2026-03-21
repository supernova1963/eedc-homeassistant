/**
 * LiveDashboard — Echtzeit-Leistungsdaten mit 5s Auto-Refresh.
 *
 * Layout:
 *   Zeile 1: Energiebilanz (2/3) | Sidebar: Heute + SoC + Netz (1/3)
 *   Zeile 2: Wetter (volle Breite)
 *   Zeile 3: Tagesverlauf (volle Breite)
 *   Zeile 4: Prognose (optional)
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { Activity, AlertCircle } from 'lucide-react'
import { useSelectedAnlage } from '../hooks'
import { liveDashboardApi } from '../api/liveDashboard'
import type { LiveDashboardResponse, LiveWetterResponse, TagesverlaufResponse, MqttInboundStatus } from '../api/liveDashboard'
import EnergieFluss from '../components/live/EnergieFluss'
import GaugeChart from '../components/live/GaugeChart'
import TagesverlaufChart from '../components/live/TagesverlaufChart'
import WetterWidget from '../components/live/WetterWidget'

const REFRESH_INTERVAL = 5_000 // 5 Sekunden
const WETTER_REFRESH_INTERVAL = 300_000 // 5 Minuten
const TAGESVERLAUF_REFRESH_INTERVAL = 60_000 // 1 Minute

export default function LiveDashboard() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const [data, setData] = useState<LiveDashboardResponse | null>(null)
  const [wetter, setWetter] = useState<LiveWetterResponse | null>(null)
  const [tagesverlauf, setTagesverlauf] = useState<TagesverlaufResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [demoMode, setDemoMode] = useState(false)
  const [mqttStatus, setMqttStatus] = useState<MqttInboundStatus | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const wetterIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const tagesverlaufIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Daten laden
  const fetchData = useCallback(async (isAutoRefresh = false) => {
    if (!selectedAnlageId) return
    if (!isAutoRefresh) setLoading(true)
    else setIsRefreshing(true)

    try {
      const result = await liveDashboardApi.getData(selectedAnlageId, demoMode)
      setData(result)
      setLastUpdate(new Date().toLocaleTimeString('de-DE'))
      setError(null)
    } catch (err) {
      if (!isAutoRefresh) {
        setError(err instanceof Error ? err.message : 'Fehler beim Laden der Live-Daten')
      }
    } finally {
      setLoading(false)
      setIsRefreshing(false)
    }
  }, [selectedAnlageId, demoMode])

  // Wetter laden (seltener, alle 5 Min)
  const fetchWetter = useCallback(async () => {
    if (!selectedAnlageId) return
    try {
      const result = await liveDashboardApi.getWetter(selectedAnlageId, demoMode)
      setWetter(result)
    } catch {
      // Wetter-Fehler still ignorieren — nicht kritisch
    }
  }, [selectedAnlageId, demoMode])

  // Tagesverlauf laden (alle 60s)
  const fetchTagesverlauf = useCallback(async () => {
    if (!selectedAnlageId) return
    try {
      const result = await liveDashboardApi.getTagesverlauf(selectedAnlageId, demoMode)
      setTagesverlauf(result)
    } catch {
      // Tagesverlauf-Fehler still ignorieren
    }
  }, [selectedAnlageId, demoMode])

  // MQTT-Status einmalig laden
  useEffect(() => {
    liveDashboardApi.getMqttStatus().then(setMqttStatus).catch(() => {})
  }, [])

  // Initial laden + Auto-Refresh
  useEffect(() => {
    fetchData(false)
    fetchWetter()
    fetchTagesverlauf()

    intervalRef.current = setInterval(() => {
      fetchData(true)
    }, REFRESH_INTERVAL)

    wetterIntervalRef.current = setInterval(() => {
      fetchWetter()
    }, WETTER_REFRESH_INTERVAL)

    tagesverlaufIntervalRef.current = setInterval(() => {
      fetchTagesverlauf()
    }, TAGESVERLAUF_REFRESH_INTERVAL)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (wetterIntervalRef.current) clearInterval(wetterIntervalRef.current)
      if (tagesverlaufIntervalRef.current) clearInterval(tagesverlaufIntervalRef.current)
    }
  }, [fetchData, fetchWetter, fetchTagesverlauf])

  // Loading State
  if (anlagenLoading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
      </div>
    )
  }

  if (anlagen.length === 0) {
    return (
      <div className="p-6 text-center text-gray-500 dark:text-gray-400">
        Keine Anlagen vorhanden. Bitte zuerst eine Anlage anlegen.
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <Activity className="h-6 w-6 text-primary-600 dark:text-primary-400" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">
            Live-Daten
          </h1>
          {/* Pulsierender Punkt */}
          {data?.verfuegbar && (
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500" />
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          {/* Anlage-Auswahl */}
          {anlagen.length > 1 && (
            <select
              value={selectedAnlageId ?? ''}
              onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
              className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
            >
              {anlagen.map((a) => (
                <option key={a.id} value={a.id}>{a.anlagenname}</option>
              ))}
            </select>
          )}
          {/* Demo-Toggle */}
          <button
            onClick={() => setDemoMode(!demoMode)}
            className={`text-xs px-2.5 py-1.5 rounded-md font-medium transition-colors ${
              demoMode
                ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
          >
            {demoMode ? 'Demo an' : 'Demo'}
          </button>
          {/* MQTT-Status */}
          {mqttStatus?.subscriber_aktiv && (
            <span
              className="text-xs px-2 py-1 rounded-md bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400"
              title={`MQTT: ${mqttStatus.broker}\nNachrichten: ${mqttStatus.empfangene_nachrichten ?? 0}${mqttStatus.letzte_nachricht ? `\nLetzte: ${new Date(mqttStatus.letzte_nachricht).toLocaleTimeString('de-DE')}` : ''}`}
            >
              MQTT {mqttStatus.empfangene_nachrichten ? `(${mqttStatus.empfangene_nachrichten})` : ''}
            </span>
          )}
          {/* Refresh-Status */}
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            {isRefreshing && (
              <div className="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-primary-500" />
            )}
            {lastUpdate && <span>Update: {lastUpdate}</span>}
            <span className="text-xs">(5s)</span>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-4 bg-red-50 dark:bg-red-900/20 rounded-lg text-red-700 dark:text-red-400">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
        </div>
      )}

      {/* Kein Live-Sensor konfiguriert */}
      {!loading && data && !data.verfuegbar && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-8 text-center">
          <Activity className="h-12 w-12 text-gray-400 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">
            Keine Live-Daten verfügbar
          </h2>
          <p className="text-gray-500 dark:text-gray-400 max-w-md mx-auto">
            Um Live-Daten zu sehen, konfiguriere Leistungs-Sensoren über eine der beiden Optionen:
            Sensor-Zuordnung (Einstellungen → Home Assistant) oder MQTT-Inbound (Einstellungen → MQTT).
          </p>
        </div>
      )}

      {/* Dashboard Content */}
      {!loading && data?.verfuegbar && (
        <div className="space-y-6">
          {/* Zeile 1: Energiebilanz (2/3) + Zustandswerte (1/3) */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6 flex flex-col">
              <EnergieFluss
                komponenten={data.komponenten}
                summeErzeugung={data.summe_erzeugung_kw}
                summeVerbrauch={data.summe_verbrauch_kw}
                tagesWerte={data.heute_kwh_pro_komponente ?? undefined}
                gauges={data.gauges}
              />
            </div>

            {/* Sidebar: Heute + SoC + Netz — Höhe bestimmt durch EnergieFluss-SVG */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6 flex flex-col justify-between gap-3">
              {/* Heute — Tageswerte */}
              {(data.heute_pv_kwh !== null || data.heute_einspeisung_kwh !== null || data.heute_netzbezug_kwh !== null) && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Heute</h3>
                  <div className="grid grid-cols-2 gap-2">
                    {data.heute_pv_kwh !== null && (
                      <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg px-3 py-2"
                           title={data.gestern_pv_kwh !== null ? `Gestern: ${data.gestern_pv_kwh.toFixed(1)} kWh` : undefined}>
                        <div className="text-xs text-gray-500 dark:text-gray-400">PV-Erzeugung</div>
                        <div className="text-lg font-bold text-yellow-600 dark:text-yellow-400">{data.heute_pv_kwh.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
                      </div>
                    )}
                    {data.heute_eigenverbrauch_kwh !== null && (
                      <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg px-3 py-2"
                           title={data.gestern_eigenverbrauch_kwh !== null ? `Gestern: ${data.gestern_eigenverbrauch_kwh.toFixed(1)} kWh` : undefined}>
                        <div className="text-xs text-gray-500 dark:text-gray-400">Eigenverbrauch</div>
                        <div className="text-lg font-bold text-blue-600 dark:text-blue-400">{data.heute_eigenverbrauch_kwh.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
                      </div>
                    )}
                    {data.heute_einspeisung_kwh !== null && (
                      <div className="bg-green-50 dark:bg-green-900/20 rounded-lg px-3 py-2"
                           title={data.gestern_einspeisung_kwh !== null ? `Gestern: ${data.gestern_einspeisung_kwh.toFixed(1)} kWh` : undefined}>
                        <div className="text-xs text-gray-500 dark:text-gray-400">Einspeisung</div>
                        <div className="text-lg font-bold text-green-600 dark:text-green-400">{data.heute_einspeisung_kwh.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
                      </div>
                    )}
                    {data.heute_netzbezug_kwh !== null && (
                      <div className="bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2"
                           title={data.gestern_netzbezug_kwh !== null ? `Gestern: ${data.gestern_netzbezug_kwh.toFixed(1)} kWh` : undefined}>
                        <div className="text-xs text-gray-500 dark:text-gray-400">Netzbezug</div>
                        <div className="text-lg font-bold text-red-600 dark:text-red-400">{data.heute_netzbezug_kwh.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
                      </div>
                    )}
                  </div>
                  {/* Autarkie + Eigenverbrauchsquote */}
                  {(() => {
                    const ev = data.heute_eigenverbrauch_kwh
                    const nb = data.heute_netzbezug_kwh
                    const pv = data.heute_pv_kwh
                    const autarkie = ev !== null && nb !== null && (ev + nb) > 0
                      ? (ev / (ev + nb)) * 100 : null
                    const evQuote = ev !== null && pv !== null && pv > 0
                      ? (ev / pv) * 100 : null
                    if (autarkie === null && evQuote === null) return null
                    return (
                      <div className="flex gap-3 mt-2">
                        {autarkie !== null && (
                          <div className="flex-1 text-center bg-emerald-50 dark:bg-emerald-900/20 rounded-lg px-2 py-1.5">
                            <div className="text-xs text-gray-500 dark:text-gray-400">Autarkie</div>
                            <div className="text-base font-bold text-emerald-600 dark:text-emerald-400">{autarkie.toFixed(0)}<span className="text-xs font-normal">%</span></div>
                          </div>
                        )}
                        {evQuote !== null && (
                          <div className="flex-1 text-center bg-sky-50 dark:bg-sky-900/20 rounded-lg px-2 py-1.5">
                            <div className="text-xs text-gray-500 dark:text-gray-400">Eigenverbr.</div>
                            <div className="text-base font-bold text-sky-600 dark:text-sky-400">{evQuote.toFixed(0)}<span className="text-xs font-normal">%</span></div>
                          </div>
                        )}
                      </div>
                    )
                  })()}
                </div>
              )}

              {/* Prognose */}
              {wetter?.pv_prognose_kwh != null && (
                <div className="flex gap-2">
                  <div className="flex-1 bg-amber-50 dark:bg-amber-900/20 rounded-lg px-3 py-1.5">
                    <div className="text-xs text-gray-500 dark:text-gray-400">PV-Prognose</div>
                    <div className="text-base font-bold text-amber-600 dark:text-amber-400">~{wetter.pv_prognose_kwh.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
                  </div>
                  {wetter?.verbrauchsprofil && wetter.verbrauchsprofil.length > 0 && (
                    <div className="flex-1 bg-orange-50 dark:bg-orange-900/20 rounded-lg px-3 py-1.5"
                         title={wetter.profil_typ?.startsWith('individuell')
                           ? `Individuelles Profil (${wetter.profil_typ === 'individuell_wochenende' ? 'Wochenende' : 'Werktag'}, ${wetter.profil_tage ?? '?'} Tage, Quelle: ${wetter.profil_quelle === 'mqtt' ? 'MQTT' : 'HA'})`
                           : 'BDEW H0 Standardlastprofil (keine History verfügbar)'
                         }>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        Verbr.-Prognose
                        {wetter.profil_typ?.startsWith('individuell') && (
                          <span className="ml-1 text-[9px] text-emerald-500" title="Basiert auf deinem individuellen Verbrauchsmuster">
                            (individuell)
                          </span>
                        )}
                      </div>
                      <div className="text-base font-bold text-orange-600 dark:text-orange-400">~{wetter.verbrauchsprofil.reduce((s, v) => s + v.verbrauch_kw, 0).toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
                    </div>
                  )}
                </div>
              )}

              {/* SoC Gauges — nur Batterie/E-Auto */}
              {data.gauges.filter(g => g.key.startsWith('soc_')).length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Ladezustand</h3>
                  <div className="grid grid-cols-2 gap-3">
                    {data.gauges.filter(g => g.key.startsWith('soc_')).map((gauge) => (
                      <div key={gauge.key} title={`${gauge.label}: ${gauge.wert} ${gauge.einheit}`} className="cursor-default">
                        <GaugeChart
                          wert={gauge.wert}
                          min={gauge.min_wert}
                          max={gauge.max_wert}
                          label={gauge.label}
                          einheit={gauge.einheit}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Netz — Ampel-Farbgebung: Grün=Balance, Orange=Einspeisung, Rot=Bezug */}
              {(() => {
                const netzGauge = data.gauges.find(g => g.key === 'netz')
                if (!netzGauge) return null
                const PUFFER_W = 100 // ±100 W = ideal (grün)
                const maxAbs = Math.max(Math.abs(netzGauge.min_wert), Math.abs(netzGauge.max_wert)) || 1
                const absWert = Math.abs(netzGauge.wert)
                const ratio = Math.min(1, absWert / maxAbs)
                const isExport = netzGauge.wert < 0
                const isPuffer = absWert <= PUFFER_W
                const displayW = absWert >= 1000
                  ? `${(Math.abs(netzGauge.wert) / 1000).toFixed(1)} kW`
                  : `${Math.round(absWert)} W`
                // Farben: Grün=ideal, Orange=Einspeisung (EV wäre besser), Rot=Bezug (kostet)
                const barColor = isPuffer ? '' : isExport ? 'bg-amber-500' : 'bg-red-500'
                const textColor = isPuffer
                  ? 'text-green-600 dark:text-green-400'
                  : isExport
                    ? 'text-amber-700 dark:text-amber-300'
                    : 'text-red-700 dark:text-red-300'
                const statusLabel = isPuffer ? 'Balance' : isExport ? 'Einspeisung' : 'Netzbezug'
                return (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Netz</h3>
                    <div className="relative h-8 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                      {/* Mittellinie */}
                      <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gray-300 dark:bg-gray-500 z-10" />
                      {/* Balken — nur außerhalb der Pufferzone */}
                      {!isPuffer && (
                        <div
                          className={`absolute top-0 bottom-0 transition-all duration-500 ${barColor}`}
                          style={isExport
                            ? { right: '50%', width: `${ratio * 50}%` }
                            : { left: '50%', width: `${ratio * 50}%` }
                          }
                        />
                      )}
                      {/* Grüner Puffer-Hintergrund bei Balance */}
                      {isPuffer && (
                        <div className="absolute inset-0 bg-green-500/20 dark:bg-green-500/15 rounded-full" />
                      )}
                      {/* Wert */}
                      <div className={`absolute inset-0 flex items-center justify-center z-20 ${textColor}`}>
                        {isPuffer ? (
                          <span className="text-base font-extrabold">✓ {displayW}</span>
                        ) : (
                          <span className="text-xs font-bold">{statusLabel} {displayW}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex justify-between text-[10px] text-gray-400 dark:text-gray-500 mt-0.5 px-1">
                      <span>← Einspeisung</span>
                      <span>Bezug →</span>
                    </div>
                  </div>
                )
              })()}
            </div>
          </div>

          {/* Zeile 2: Wetter + Prognose (volle Breite) */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              Wetter heute
            </h3>
            <WetterWidget wetter={wetter} tagesverlauf={tagesverlauf} />
          </div>

          {/* Zeile 3: Tagesverlauf-Chart (Butterfly) */}
          {tagesverlauf && tagesverlauf.punkte.length > 0 && tagesverlauf.serien?.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6">
              <TagesverlaufChart serien={tagesverlauf.serien} punkte={tagesverlauf.punkte} />
            </div>
          )}

        </div>
      )}
    </div>
  )
}
