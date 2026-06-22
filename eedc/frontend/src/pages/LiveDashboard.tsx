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
import { useSearchParams } from 'react-router-dom'
import { Activity, AlertCircle } from 'lucide-react'
import { useSelectedAnlage } from '../hooks'
import { liveDashboardApi } from '../api/liveDashboard'
import type { LiveDashboardResponse, LiveWetterResponse, TagesverlaufResponse, MqttInboundStatus } from '../api/liveDashboard'
import { wetterApi } from '../api/wetter'
import type { SolarPrognoseTag } from '../api/wetter'
import EnergieFluss from '../components/live/EnergieFluss'
import TagesverlaufChart from '../components/live/TagesverlaufChart'
import WetterWidget from '../components/live/WetterWidget'
import SunProgressBar from '../components/live/SunProgressBar'
import LiveHeuteKacheln from '../components/live/LiveHeuteKacheln'
import SolarAussicht3Tage from '../components/live/SolarAussicht3Tage'
import LiveSocBalken from '../components/live/LiveSocBalken'
import LiveTemperaturen from '../components/live/LiveTemperaturen'
import { CommunityNudge } from '../components/dashboard'

const REFRESH_INTERVAL = 5_000 // 5 Sekunden
const WETTER_REFRESH_INTERVAL = 300_000 // 5 Minuten
const TAGESVERLAUF_REFRESH_INTERVAL = 60_000 // 1 Minute

export default function LiveDashboard() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, selectedAnlage, loading: anlagenLoading } = useSelectedAnlage()
  const [searchParams] = useSearchParams()
  const isDebug = searchParams.has('debug')
  const [data, setData] = useState<LiveDashboardResponse | null>(null)
  const [wetter, setWetter] = useState<LiveWetterResponse | null>(null)
  const [tagesverlauf, setTagesverlauf] = useState<TagesverlaufResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)
  const [demoMode, setDemoMode] = useState(false)
  const [mqttStatus, setMqttStatus] = useState<MqttInboundStatus | null>(null)
  const [prognose3Tage, setPrognose3Tage] = useState<SolarPrognoseTag[] | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const wetterIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const tagesverlaufIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Stale-Guard: aktuelle Anlage-ID als Ref, damit in-flight Requests
  // nach Anlage-Wechsel kein setState auf veraltete Daten machen
  const activeAnlageRef = useRef(selectedAnlageId)
  activeAnlageRef.current = selectedAnlageId

  // Daten laden
  const fetchData = useCallback(async (isAutoRefresh = false) => {
    if (!selectedAnlageId) return
    const requestAnlageId = selectedAnlageId
    if (!isAutoRefresh) setLoading(true)

    try {
      const result = await liveDashboardApi.getData(requestAnlageId, demoMode)
      if (activeAnlageRef.current !== requestAnlageId) return // Anlage gewechselt → verwerfen
      setData(result)
      setLastUpdate(new Date().toLocaleTimeString('de-DE'))
      setError(null)
    } catch (err) {
      if (activeAnlageRef.current !== requestAnlageId) return
      if (!isAutoRefresh) {
        setError(err instanceof Error ? err.message : 'Fehler beim Laden der Live-Daten')
      }
    } finally {
      setLoading(false)
    }
  }, [selectedAnlageId, demoMode])

  // Wetter + 3-Tage-Prognose parallel laden (alle 5 Min — ICON-D2 aktualisiert 3-stündlich)
  const fetchWetter = useCallback(async () => {
    if (!selectedAnlageId) return
    const requestAnlageId = selectedAnlageId
    // Beide Calls parallel statt sequentiell + 14-Tage-Cache-Warmup im Hintergrund
    const [wetterResult, prognoseResult] = await Promise.allSettled([
      liveDashboardApi.getWetter(requestAnlageId, demoMode),
      wetterApi.getSolarPrognose(requestAnlageId, 3, false),
    ])
    if (activeAnlageRef.current !== requestAnlageId) return // Anlage gewechselt → verwerfen
    if (wetterResult.status === 'fulfilled') setWetter(wetterResult.value)
    if (prognoseResult.status === 'fulfilled') {
      setPrognose3Tage(prognoseResult.value.tage?.slice(0, 3) ?? null)
    }
    // 14-Tage-Prognose im Hintergrund vorwärmen — kein await, Ergebnis wird ignoriert
    // Damit ist der Cache warm wenn der User zu Aussichten navigiert
    wetterApi.getSolarPrognose(requestAnlageId, 14, false).catch(() => {})
  }, [selectedAnlageId, demoMode])

  // Tagesverlauf laden (alle 60s)
  const fetchTagesverlauf = useCallback(async () => {
    if (!selectedAnlageId) return
    const requestAnlageId = selectedAnlageId
    try {
      const result = await liveDashboardApi.getTagesverlauf(requestAnlageId, demoMode)
      if (activeAnlageRef.current !== requestAnlageId) return // Anlage gewechselt → verwerfen
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
    <div className="p-3 sm:p-4 space-y-4">
      {/* Header — #207: pulsierender Live-Punkt + Refresh-Spinner waren auf
          schmalen Fenstern unruhig, Mehrwert minimal. Indikator zusammengelegt
          mit der Update-Zeile und entanimiert. */}
      <div className="flex items-center justify-end gap-4 flex-wrap">
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
        {/* Demo-Toggle — nur sichtbar mit ?debug=1 */}
        {isDebug && (
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
        )}
        {/* MQTT-Status */}
        {mqttStatus?.subscriber_aktiv && (
          <span
            className="text-xs px-2 py-1 rounded-md bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400"
            title={`MQTT: ${mqttStatus.broker}\nNachrichten: ${mqttStatus.empfangene_nachrichten ?? 0}${mqttStatus.letzte_nachricht ? `\nLetzte: ${new Date(mqttStatus.letzte_nachricht).toLocaleTimeString('de-DE')}` : ''}`}
          >
            MQTT {mqttStatus.empfangene_nachrichten ? `(${mqttStatus.empfangene_nachrichten})` : ''}
          </span>
        )}
        {/* Refresh-Status: statischer Live-Punkt + Update-Zeit. Kein Spinner,
            kein animate-ping. */}
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          {data?.verfuegbar && (
            <span
              className="inline-block h-2 w-2 rounded-full bg-green-500"
              aria-label="Live-Daten verfügbar"
            />
          )}
          {lastUpdate && <span aria-live="polite">Update: {lastUpdate}</span>}
          <span className="text-xs">(5s)</span>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div role="alert" className="flex items-center gap-2 p-4 bg-red-50 dark:bg-red-900/20 rounded-lg text-red-700 dark:text-red-400">
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
          <Activity className="h-12 w-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
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
        <div className="space-y-4">
          {/* Zeile 1: Energiebilanz (2/3) + Zustandswerte (1/3).
              Side-by-Side erst ab xl (≥1280px) — bei lg-Breite (1024–1280) führt
              die hohe Heute-Box zu Aspect-Lücken im Energiefluss-SVG (#164 detLAN). */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <div className="xl:col-span-2 bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6 flex flex-col">
              <EnergieFluss
                komponenten={data.komponenten}
                summeErzeugung={data.summe_erzeugung_kw}
                summeVerbrauch={data.summe_verbrauch_kw}
                summePv={data.summe_pv_kw}
                tagesWerte={data.heute_kwh_pro_komponente ?? undefined}
                gauges={data.gauges}
                netzPufferW={selectedAnlage?.netz_puffer_w ?? 100}
                pvSollKw={(() => {
                  // SFML: aktuelle Stunde aus Verbrauchsprofil
                  if (wetter?.verbrauchsprofil?.length) {
                    const h = new Date().getHours()
                    const stunde = wetter.verbrauchsprofil.find(v => {
                      const vh = new Date(v.zeit).getHours()
                      return vh === h
                    })
                    if (stunde?.pv_ml_prognose_kw != null && stunde.pv_ml_prognose_kw > 0) {
                      return stunde.pv_ml_prognose_kw
                    }
                    // Fallback: eedc-Prognose der aktuellen Stunde
                    if (stunde && stunde.pv_ertrag_kw > 0) {
                      return stunde.pv_ertrag_kw
                    }
                  }
                  return null
                })()}
              />
            </div>

            {/* Sidebar: Heute + SoC + Netz — Höhe bestimmt durch EnergieFluss-SVG */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6 flex flex-col justify-between gap-3">
              {/* Heute — Tageswerte (geteilte Komponente, eine Code-Wahrheit mit Cockpit/Live) */}
              <LiveHeuteKacheln data={data} />

              {/* Sonnentags-Fortschritt — Trenner Ist / Prognose */}
              {wetter?.sunrise && wetter?.sunset && (
                <SunProgressBar
                  sunrise={wetter.sunrise}
                  sunset={wetter.sunset}
                  solar_noon={wetter.solar_noon ?? undefined}
                  sonnenstunden={wetter.sonnenstunden}
                  sonnenstundenBisher={wetter.sonnenstunden_bisher}
                  sonnenstundenRest={wetter.sonnenstunden_rest}
                />
              )}


              {/* 3-Tage Solar-Vorschau (geteilte Komponente, eine Code-Wahrheit mit Cockpit/Live) */}
              <SolarAussicht3Tage prognose3Tage={prognose3Tage ?? []} wetter={wetter} heutePvKwh={data.heute_pv_kwh} />

              {/* SoC + Temperaturen — geteilte Komponenten, eine Code-Wahrheit mit Cockpit/Live */}
              <LiveSocBalken gauges={data.gauges} />
              <LiveTemperaturen
                aussenC={wetter?.aktuell?.temperatur_c}
                tempMinC={wetter?.temperatur_min_c}
                tempMaxC={wetter?.temperatur_max_c}
                warmwasserC={data.warmwasser_temperatur_c}
              />

              {/* Netz-Balken entfernt — Netz-Farbe im Energiefluss SVG zeigt dieselbe Info */}
            </div>
          </div>

          {/* Zeile 2: Wetter + Prognose (volle Breite) */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              Wetter heute
            </h3>
            <WetterWidget wetter={wetter} tagesverlauf={tagesverlauf} anlageId={selectedAnlageId} />
          </div>

          {/* Zeile 3: Tagesverlauf-Chart (Butterfly) */}
          {tagesverlauf && tagesverlauf.punkte.length > 0 && tagesverlauf.serien?.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6">
              <TagesverlaufChart serien={tagesverlauf.serien} punkte={tagesverlauf.punkte} uebersprungen={tagesverlauf.uebersprungen} />
            </div>
          )}

          {/* Community-Nudge (wenn noch nicht geteilt) */}
          {!selectedAnlage?.community_hash && <CommunityNudge />}

        </div>
      )}
    </div>
  )
}
