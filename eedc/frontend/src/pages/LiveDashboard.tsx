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
import { Activity, AlertCircle, Info } from 'lucide-react'
import { useSelectedAnlage } from '../hooks'
import { liveDashboardApi } from '../api/liveDashboard'
import type { LiveDashboardResponse, LiveWetterResponse, TagesverlaufResponse, MqttInboundStatus } from '../api/liveDashboard'
import { wetterApi } from '../api/wetter'
import type { SolarPrognoseTag } from '../api/wetter'
import EnergieFluss from '../components/live/EnergieFluss'
import TagesverlaufChart from '../components/live/TagesverlaufChart'
import WetterWidget from '../components/live/WetterWidget'
import SunProgressBar from '../components/live/SunProgressBar'
import { CommunityNudge } from '../components/dashboard'
import { SimpleTooltip } from '../components/ui/FormelTooltip'

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
  const [isRefreshing, setIsRefreshing] = useState(false)
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
    else setIsRefreshing(true)

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
      setIsRefreshing(false)
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
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-primary-600 dark:text-primary-400" />
          <h1 className="text-lg font-bold text-gray-900 dark:text-white">
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
          {/* Refresh-Status */}
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            {isRefreshing && (
              <div className="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-primary-500" />
            )}
            {lastUpdate && <span aria-live="polite">Update: {lastUpdate}</span>}
            <span className="text-xs">(5s)</span>
          </div>
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
        <div className="space-y-4">
          {/* Zeile 1: Energiebilanz (2/3) + Zustandswerte (1/3) */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6 flex flex-col">
              <p className="text-[10px] text-gray-400 dark:text-gray-500 mb-2">
                Momentwerte · aktualisiert alle ~30s
              </p>
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
                    // Fallback: EEDC-Prognose der aktuellen Stunde
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
                      <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg px-3 py-2">
                        <div className="text-xs text-gray-500 dark:text-gray-400">Eigenverbrauch <SimpleTooltip text={`Selbst genutzter PV-Strom (Direktverbrauch + Batterieentladung)${data.gestern_eigenverbrauch_kwh !== null ? ` | Gestern: ${data.gestern_eigenverbrauch_kwh.toFixed(1)} kWh` : ''}`}><Info className="inline w-3 h-3 opacity-50 cursor-help" /></SimpleTooltip></div>
                        <div className="text-lg font-bold text-blue-600 dark:text-blue-400">{data.heute_eigenverbrauch_kwh.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
                      </div>
                    )}
                    {data.heute_einspeisung_kwh !== null && (
                      <div className="bg-green-50 dark:bg-green-900/20 rounded-lg px-3 py-2"
                           title={`PV-Strom der ins Netz eingespeist wird${data.gestern_einspeisung_kwh !== null ? `\nGestern: ${data.gestern_einspeisung_kwh.toFixed(1)} kWh` : ''}`}>
                        <div className="text-xs text-gray-500 dark:text-gray-400">Einspeisung</div>
                        <div className="text-lg font-bold text-green-600 dark:text-green-400">{data.heute_einspeisung_kwh.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
                      </div>
                    )}
                    {/* Batterie heute (Ladung/Entladung) — neben Einspeisung (Überschuss-Verwertung) */}
                    {(() => {
                      const komp = data.heute_kwh_pro_komponente
                      if (!komp) return null
                      let ladung = 0, entladung = 0, found = false
                      for (const [k, v] of Object.entries(komp)) {
                        if (k.endsWith('_ladung') && k.startsWith('batterie_')) { ladung += v; found = true }
                        if (k.endsWith('_entladung') && k.startsWith('batterie_')) { entladung += v; found = true }
                      }
                      if (!found) return null
                      return (
                        <div className="bg-teal-50 dark:bg-teal-900/20 rounded-lg px-3 py-2"
                             title={`Batterie heute\nLadung: ${ladung.toFixed(1)} kWh\nEntladung: ${entladung.toFixed(1)} kWh`}>
                          <div className="text-xs text-gray-500 dark:text-gray-400">Batterie</div>
                          <div className="text-lg font-bold text-teal-600 dark:text-teal-400">
                            <span title="Ladung">&#9650;{ladung.toFixed(1)}</span>
                            <span className="text-gray-400 mx-0.5">/</span>
                            <span title="Entladung">&#9660;{entladung.toFixed(1)}</span>
                            <span className="text-xs font-normal ml-0.5">kWh</span>
                          </div>
                        </div>
                      )
                    })()}
                    {/* Hausverbrauch heute */}
                    {data.heute_kwh_pro_komponente?.haushalt != null && (
                      <div className="bg-indigo-50 dark:bg-indigo-900/20 rounded-lg px-3 py-2">
                        <div className="text-xs text-gray-500 dark:text-gray-400">Hausverbrauch <SimpleTooltip text="Gesamter Stromverbrauch des Haushalts (Eigenverbrauch + Netzbezug)"><Info className="inline w-3 h-3 opacity-50 cursor-help" /></SimpleTooltip></div>
                        <div className="text-lg font-bold text-indigo-600 dark:text-indigo-400">{data.heute_kwh_pro_komponente.haushalt.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
                      </div>
                    )}
                    {data.heute_netzbezug_kwh !== null && (
                      <div className="bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">
                        <div className="text-xs text-gray-500 dark:text-gray-400">Netzbezug <SimpleTooltip text={`Strom der aus dem Netz bezogen wird (nicht durch PV gedeckt)${data.gestern_netzbezug_kwh !== null ? ` | Gestern: ${data.gestern_netzbezug_kwh.toFixed(1)} kWh` : ''}`}><Info className="inline w-3 h-3 opacity-50 cursor-help" /></SimpleTooltip></div>
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
                      <div className="grid grid-cols-2 gap-2 mt-2">
                        {autarkie !== null && (
                          <div className="bg-emerald-50 dark:bg-emerald-900/20 rounded-lg px-3 py-1.5">
                            <div className="text-xs text-gray-500 dark:text-gray-400">Autarkie</div>
                            <div className="text-base font-bold text-emerald-600 dark:text-emerald-400">{autarkie.toFixed(0)}<span className="text-xs font-normal">%</span></div>
                          </div>
                        )}
                        {evQuote !== null && (
                          <div className="bg-sky-50 dark:bg-sky-900/20 rounded-lg px-3 py-1.5">
                            <div className="text-xs text-gray-500 dark:text-gray-400">Eigenverbr.</div>
                            <div className="text-base font-bold text-sky-600 dark:text-sky-400">{evQuote.toFixed(0)}<span className="text-xs font-normal">%</span></div>
                          </div>
                        )}
                      </div>
                    )
                  })()}
                </div>
              )}

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


              {/* 3-Tage Solar-Vorschau (VM/NM) */}
              {prognose3Tage && prognose3Tage.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                    Solar-Aussicht <SimpleTooltip text="GTI-basierte Prognose (Open-Meteo) mit Neigung/Ausrichtung der Module. VM/NM = Split an Solar Noon."><Info className="inline w-3 h-3 text-gray-400 opacity-50 cursor-help" /></SimpleTooltip>
                  </h3>
                  {prognose3Tage.some(t => t.pv_ertrag_morgens_kwh != null) && (
                    <div className="grid grid-cols-[auto_1fr_7rem] px-3 mb-0.5">
                      <span />
                      <span />
                      <span className="text-[10px] text-right">
                        <span className="text-amber-500">VM</span>
                        <span className="text-gray-400 mx-0.5">/</span>
                        <span className="text-yellow-500">NM</span>
                      </span>
                    </div>
                  )}
                  <div className="space-y-1.5">
                    {prognose3Tage.map((tag, i) => {
                      const label = i === 0 ? 'Heute' : i === 1 ? 'Morgen' : 'Übermorgen'
                      const hasVmNm = tag.pv_ertrag_morgens_kwh != null
                      const sfml = i === 0 ? wetter?.sfml_prognose_kwh : i === 1 ? wetter?.sfml_tomorrow_kwh : null
                      const isProminent = i < 3
                      const verbrPrognKwh = i === 0 && wetter?.verbrauchsprofil?.length
                        ? wetter.verbrauchsprofil.reduce((s, v) => s + v.verbrauch_kw, 0)
                        : null
                      const verbrTooltip = wetter?.profil_typ?.startsWith('individuell')
                        ? `Individuelles Profil (${wetter.profil_typ === 'individuell_wochenende' ? 'Wochenende' : 'Werktag'}, ${wetter.profil_tage ?? '?'} Tage) — Haus + Batterie + WP + Wallbox + Sonstige`
                        : 'BDEW H0 Standardlastprofil — Haus + Batterie + WP + Wallbox + Sonstige'
                      const verbleibenKwh = i === 0 && wetter?.pv_prognose_kwh != null ? (() => {
                        const diff = wetter.pv_prognose_kwh - (data.heute_pv_kwh ?? 0)
                        const nachSU = wetter.sunset ? (() => {
                          const now = new Date()
                          const [h, m] = wetter.sunset!.split(':').map(Number)
                          return now.getHours() * 60 + now.getMinutes() >= h * 60 + m
                        })() : false
                        if (nachSU) return null
                        return diff
                      })() : null
                      return (
                        <div key={tag.datum}>
                        <div className={`grid grid-cols-[auto_1fr_7rem] items-center gap-x-2 rounded-lg px-3 py-2 ${
                          i === 0 ? 'bg-yellow-50 dark:bg-yellow-900/20' :
                          'bg-amber-50/60 dark:bg-amber-900/10'
                        }`}>
                          <span className={`shrink-0 ${isProminent ? 'text-sm font-medium text-gray-600 dark:text-gray-300' : 'text-xs text-gray-400 dark:text-gray-500'}`}>{label}</span>
                          <div className="flex flex-col items-end">
                            <span className={`font-bold text-yellow-600 dark:text-yellow-400 ${isProminent ? 'text-base' : 'text-xs'}`}
                                  title={sfml != null ? `ML: ${sfml.toFixed(1)} kWh` : undefined}>
                              {(i === 0 && wetter?.pv_prognose_kwh != null ? wetter.pv_prognose_kwh : tag.pv_ertrag_kwh).toFixed(1)}
                              {sfml != null && <span className="text-[10px] text-purple-400 font-normal ml-1">{sfml.toFixed(0)}</span>}
                              <span className="text-xs font-normal ml-0.5">kWh</span>
                            </span>
                            {verbleibenKwh != null && (
                              <span className={`text-[10px] ${verbleibenKwh > 0 ? 'text-lime-600 dark:text-lime-400' : 'text-emerald-600 dark:text-emerald-400'}`}
                                    title={verbleibenKwh > 0
                                      ? `Noch ~${verbleibenKwh.toFixed(1)} kWh ausstehend`
                                      : `Prognose um ${Math.abs(verbleibenKwh).toFixed(1)} kWh übertroffen`}>
                                {verbleibenKwh > 0 ? `~${verbleibenKwh.toFixed(1)} verbl.` : `+${Math.abs(verbleibenKwh).toFixed(1)} über Progn.`}
                              </span>
                            )}
                          </div>
                          <span className="text-right text-xs w-28">
                            {hasVmNm ? (
                              <>
                                <span className="font-semibold text-amber-500">{tag.pv_ertrag_morgens_kwh!.toFixed(1)}</span>
                                <span className="text-gray-400 mx-0.5">/</span>
                                <span className="font-semibold text-yellow-500">{(tag.pv_ertrag_nachmittags_kwh ?? 0).toFixed(1)}</span>
                              </>
                            ) : null}
                          </span>
                        </div>
                        {/* Verbrauchsprognose im Stil der Prognose-Zeilen — nur unter Heute */}
                        {verbrPrognKwh != null && (
                          <div className="grid grid-cols-[auto_1fr_7rem] items-center gap-x-2 rounded-lg px-3 py-1 bg-gray-50 dark:bg-gray-700/50">
                            <span className="text-xs text-gray-400 dark:text-gray-300 flex items-center gap-1">
                              Verbrauchsprognose
                              {wetter?.profil_typ?.startsWith('individuell') && (
                                <span className="text-[9px] text-emerald-500">(ind.)</span>
                              )}
                              <SimpleTooltip text={verbrTooltip}><Info className="w-3 h-3 opacity-40 cursor-help" /></SimpleTooltip>
                            </span>
                            <div className="flex flex-col items-end">
                              <span className="text-xs font-bold text-orange-500 dark:text-orange-400">
                                ~{verbrPrognKwh.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span>
                              </span>
                            </div>
                            <span className="w-28" />
                          </div>
                        )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* SoC Balken — nur Batterie/E-Auto */}
              {data.gauges.filter(g => g.key.startsWith('soc_')).length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Ladezustand</h3>
                  <div className="space-y-2">
                    {data.gauges.filter(g => g.key.startsWith('soc_')).map((gauge) => {
                      const pct = gauge.max_wert > gauge.min_wert
                        ? ((gauge.wert - gauge.min_wert) / (gauge.max_wert - gauge.min_wert)) * 100 : 0
                      const color = pct < 20 ? 'bg-red-500' : pct < 50 ? 'bg-yellow-500' : 'bg-green-500'
                      return (
                        <div key={gauge.key} title={`${gauge.label}: ${gauge.wert} ${gauge.einheit}`}>
                          <div className="flex items-center justify-between text-xs mb-0.5">
                            <span className="text-gray-600 dark:text-gray-400 truncate mr-2">{gauge.label}</span>
                            <span className="font-bold text-gray-900 dark:text-white shrink-0">{Math.round(gauge.wert)}{gauge.einheit}</span>
                          </div>
                          <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Temperaturen */}
              {(wetter?.aktuell?.temperatur_c != null || data.warmwasser_temperatur_c != null) && (
                <div className="flex gap-2">
                  {wetter?.aktuell?.temperatur_c != null && (
                    <div className="flex-1 bg-cyan-50 dark:bg-cyan-900/20 rounded-lg px-3 py-1.5"
                         title={wetter.temperatur_min_c != null && wetter.temperatur_max_c != null
                           ? `Min ${wetter.temperatur_min_c.toFixed(0)}° / Max ${wetter.temperatur_max_c.toFixed(0)}°C`
                           : undefined}>
                      <div className="text-xs text-gray-500 dark:text-gray-400">Außen</div>
                      <div className="text-base font-bold text-cyan-600 dark:text-cyan-400">
                        {wetter.aktuell.temperatur_c.toFixed(1)}<span className="text-xs font-normal ml-0.5">°C</span>
                      </div>
                    </div>
                  )}
                  {data.warmwasser_temperatur_c != null && (
                    <div className="flex-1 bg-orange-50 dark:bg-orange-900/20 rounded-lg px-3 py-1.5">
                      <div className="text-xs text-gray-500 dark:text-gray-400">Warmwasser</div>
                      <div className="text-base font-bold text-orange-600 dark:text-orange-400">
                        {data.warmwasser_temperatur_c.toFixed(1)}<span className="text-xs font-normal ml-0.5">°C</span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Netz-Balken entfernt — Netz-Farbe im Energiefluss SVG zeigt dieselbe Info */}
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
