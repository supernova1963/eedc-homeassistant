/**
 * LiveDashboard — Echtzeit-Leistungsdaten mit 5s Auto-Refresh.
 *
 * Layout:
 *   Zeile 1: Energiebilanz (2/3) | Zustandswerte/Gauges (1/3)
 *   Zeile 2: Wetter + Prognose (volle Breite)
 *   Zeile 3: Tagesenergie (volle Breite)
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { Activity, AlertCircle } from 'lucide-react'
import { useAnlagen } from '../hooks'
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
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)
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

  // Auto-select erste Anlage
  useEffect(() => {
    if (anlagen.length > 0 && !selectedAnlageId) {
      setSelectedAnlageId(anlagen[0].id)
    }
  }, [anlagen, selectedAnlageId])

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
            Um Live-Daten zu sehen, konfiguriere Leistungs-Sensoren in der Sensor-Zuordnung
            (Einstellungen → Home Assistant → Sensor-Zuordnung) im Bereich „Live-Sensoren".
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
                tagesWerte={{
                  pv: data.heute_pv_kwh,
                  netz: data.heute_netzbezug_kwh,
                  haushalt: data.heute_eigenverbrauch_kwh,
                }}
                gauges={data.gauges}
              />
            </div>

            {/* Zustandswerte (Gauges) */}
            {data.gauges.length > 0 && (
              <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                  Zustandswerte
                </h3>
                <div className="grid grid-cols-2 gap-4">
                  {data.gauges.map((gauge) => {
                    // Tageswert zuordnen wo möglich
                    const tagesMap: Record<string, number | null> = {
                      netz: data.heute_netzbezug_kwh !== null && data.heute_einspeisung_kwh !== null
                        ? data.heute_netzbezug_kwh - data.heute_einspeisung_kwh
                        : null,
                    }
                    const tagesKwh = tagesMap[gauge.key] ?? null
                    const tip = [
                      `${gauge.label}: ${gauge.wert} ${gauge.einheit}`,
                      `Bereich: ${gauge.min_wert} – ${gauge.max_wert} ${gauge.einheit}`,
                      ...(tagesKwh !== null ? [`Heute netto: ${tagesKwh.toFixed(1)} kWh`] : []),
                    ].join('\n')

                    return (
                      <div key={gauge.key} title={tip} className="cursor-default">
                        <GaugeChart
                          wert={gauge.wert}
                          min={gauge.min_wert}
                          max={gauge.max_wert}
                          label={gauge.label}
                          einheit={gauge.einheit}
                        />
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Zeile 2: Wetter + Prognose (volle Breite) */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              Wetter heute
            </h3>
            <WetterWidget wetter={wetter} />
          </div>

          {/* Zeile 3: Tagesverlauf-Chart */}
          {tagesverlauf && tagesverlauf.punkte.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6">
              <TagesverlaufChart punkte={tagesverlauf.punkte} />
            </div>
          )}

          {/* Zeile 4: Tagesenergie (IST + Prognose + Gestern) */}
          {(data.heute_pv_kwh !== null || data.heute_einspeisung_kwh !== null || data.heute_netzbezug_kwh !== null || wetter?.pv_prognose_kwh !== null) && (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                Heute (kWh)
              </h3>
              <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                {data.heute_pv_kwh !== null && (
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">PV: </span>
                    <span className="font-semibold text-gray-900 dark:text-white">
                      {data.heute_pv_kwh.toFixed(1)} kWh
                    </span>
                    {data.gestern_pv_kwh !== null && (
                      <span className="text-xs text-gray-400 dark:text-gray-500 ml-1">
                        (gestern: {data.gestern_pv_kwh.toFixed(1)})
                      </span>
                    )}
                  </div>
                )}
                {data.heute_einspeisung_kwh !== null && (
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Einspeisung: </span>
                    <span className="font-semibold text-gray-900 dark:text-white">
                      {data.heute_einspeisung_kwh.toFixed(1)} kWh
                    </span>
                    {data.gestern_einspeisung_kwh !== null && (
                      <span className="text-xs text-gray-400 dark:text-gray-500 ml-1">
                        (gestern: {data.gestern_einspeisung_kwh.toFixed(1)})
                      </span>
                    )}
                  </div>
                )}
                {data.heute_netzbezug_kwh !== null && (
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Bezug: </span>
                    <span className="font-semibold text-gray-900 dark:text-white">
                      {data.heute_netzbezug_kwh.toFixed(1)} kWh
                    </span>
                    {data.gestern_netzbezug_kwh !== null && (
                      <span className="text-xs text-gray-400 dark:text-gray-500 ml-1">
                        (gestern: {data.gestern_netzbezug_kwh.toFixed(1)})
                      </span>
                    )}
                  </div>
                )}
                {/* Prognose-Werte aus Wetter */}
                {wetter?.pv_prognose_kwh !== null && wetter?.pv_prognose_kwh !== undefined && (
                  <div className="border-l border-gray-200 dark:border-gray-700 pl-6">
                    <span className="text-gray-400 dark:text-gray-500">PV-Prognose: </span>
                    <span className="font-semibold text-yellow-600 dark:text-yellow-400">
                      ~{wetter.pv_prognose_kwh.toFixed(1)} kWh
                    </span>
                  </div>
                )}
                {wetter?.verbrauchsprofil && wetter.verbrauchsprofil.length > 0 && (
                  <div>
                    <span className="text-gray-400 dark:text-gray-500">Verbrauch-Prognose: </span>
                    <span className="font-semibold text-red-500 dark:text-red-400">
                      ~{wetter.verbrauchsprofil.reduce((s, v) => s + v.verbrauch_kw, 0).toFixed(1)} kWh
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
