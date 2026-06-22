/**
 * CockpitLiveV4 — die echte Live-Sicht der Cockpit-Zeit-Achse (IA-V4 A.3).
 *
 * KONZEPT-IA-V4 Z.76: Live behält bewusst sein heutiges, reiches Layout — kein
 * Neubau, nur in die v4-Shell eingepasst. IST-treue (Gernot 2026-06-22):
 *   - Kopf-Region „auf einen Blick" (ab xl nebeneinander, wie IST):
 *       links 2/3 = Energiefluss · rechts 1/3 = Sidebar (Heute · Sonnenstand ·
 *       Solar-Aussicht · Ladezustand · Temperaturen, unter Heute gestapelt).
 *   - darunter (volle Breite, wie IST): Wetter heute · Tagesverlauf (eigener Block).
 *   - KEIN Energiefluss⇄Tagesverlauf-Umschalter (verworfen).
 *   - JEDE Sektion ist eine {@link FokusKachel} mit ⤢ Fokus/Vollbild (durchgängig).
 *
 * Daten + Polling identisch zum IST-`pages/LiveDashboard.tsx` (5 s / 60 s / 5 min),
 * bestehende Endpoints — kein neuer Read-Pfad. Sub-Komponenten geteilt
 * (`components/live/*`) → eine Code-Wahrheit.
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Activity, Battery, Calendar, CloudSun, LineChart, Maximize2, Sun, Sunrise, Thermometer, Workflow } from 'lucide-react'
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
import { FokusKachel, FokusVollbild } from '../components/blocks'
import { Card } from '../components/ui'
import { DEMO_DEFAULT } from '../lib/flags'

const REFRESH_INTERVAL = 5_000
const WETTER_REFRESH_INTERVAL = 300_000
const TAGESVERLAUF_REFRESH_INTERVAL = 60_000

export default function CockpitLiveV4({ anlageId }: { anlageId: number | undefined }) {
  const { selectedAnlage } = useSelectedAnlage()
  const [searchParams] = useSearchParams()
  // Guest-Box (kein echter Live-Sensor): Demo per Build-Flag vorab an + Schalter
  // sichtbar, damit Tester sofort befüllte Live-Daten sehen ([[DEMO_DEFAULT]]).
  const isDebug = searchParams.has('debug') || DEMO_DEFAULT
  const [data, setData] = useState<LiveDashboardResponse | null>(null)
  const [wetter, setWetter] = useState<LiveWetterResponse | null>(null)
  const [tagesverlauf, setTagesverlauf] = useState<TagesverlaufResponse | null>(null)
  const [prognose3Tage, setPrognose3Tage] = useState<SolarPrognoseTag[] | null>(null)
  const [mqttStatus, setMqttStatus] = useState<MqttInboundStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)
  const [demoMode, setDemoMode] = useState(DEMO_DEFAULT)
  const [eflFokus, setEflFokus] = useState(false) // Energiefluss-Vollbild (⤢ in seiner eigenen Kopfzeile)

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const wetterIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const tagesverlaufIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const activeAnlageRef = useRef(anlageId)
  activeAnlageRef.current = anlageId

  const fetchData = useCallback(async (isAutoRefresh = false) => {
    if (!anlageId) return
    const reqId = anlageId
    if (!isAutoRefresh) setLoading(true)
    try {
      const result = await liveDashboardApi.getData(reqId, demoMode)
      if (activeAnlageRef.current !== reqId) return
      setData(result)
      setLastUpdate(new Date().toLocaleTimeString('de-DE'))
      setError(null)
    } catch (err) {
      if (activeAnlageRef.current !== reqId) return
      if (!isAutoRefresh) setError(err instanceof Error ? err.message : 'Fehler beim Laden der Live-Daten')
    } finally {
      setLoading(false)
    }
  }, [anlageId, demoMode])

  const fetchWetter = useCallback(async () => {
    if (!anlageId) return
    const reqId = anlageId
    const [wetterResult, prognoseResult] = await Promise.allSettled([
      liveDashboardApi.getWetter(reqId, demoMode),
      wetterApi.getSolarPrognose(reqId, 3, false),
    ])
    if (activeAnlageRef.current !== reqId) return
    if (wetterResult.status === 'fulfilled') setWetter(wetterResult.value)
    if (prognoseResult.status === 'fulfilled') setPrognose3Tage(prognoseResult.value.tage?.slice(0, 3) ?? null)
    wetterApi.getSolarPrognose(reqId, 14, false).catch(() => {})
  }, [anlageId, demoMode])

  const fetchTagesverlauf = useCallback(async () => {
    if (!anlageId) return
    const reqId = anlageId
    try {
      const result = await liveDashboardApi.getTagesverlauf(reqId, demoMode)
      if (activeAnlageRef.current !== reqId) return
      setTagesverlauf(result)
    } catch {
      // still ignorieren
    }
  }, [anlageId, demoMode])

  useEffect(() => {
    liveDashboardApi.getMqttStatus().then(setMqttStatus).catch(() => {})
  }, [])

  useEffect(() => {
    fetchData(false)
    fetchWetter()
    fetchTagesverlauf()
    intervalRef.current = setInterval(() => fetchData(true), REFRESH_INTERVAL)
    wetterIntervalRef.current = setInterval(() => fetchWetter(), WETTER_REFRESH_INTERVAL)
    tagesverlaufIntervalRef.current = setInterval(() => fetchTagesverlauf(), TAGESVERLAUF_REFRESH_INTERVAL)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (wetterIntervalRef.current) clearInterval(wetterIntervalRef.current)
      if (tagesverlaufIntervalRef.current) clearInterval(tagesverlaufIntervalRef.current)
    }
  }, [fetchData, fetchWetter, fetchTagesverlauf])

  // PV-SOLL der aktuellen Stunde (SFML → eedc-Fallback) für den Energiefluss.
  const pvSollKw = useMemo<number | null>(() => {
    if (!wetter?.verbrauchsprofil?.length) return null
    const h = new Date().getHours()
    const stunde = wetter.verbrauchsprofil.find((v) => new Date(v.zeit).getHours() === h)
    if (stunde?.pv_ml_prognose_kw != null && stunde.pv_ml_prognose_kw > 0) return stunde.pv_ml_prognose_kw
    if (stunde && stunde.pv_ertrag_kw > 0) return stunde.pv_ertrag_kw
    return null
  }, [wetter])

  const hatTagesverlauf = !!(tagesverlauf && tagesverlauf.punkte.length > 0 && tagesverlauf.serien?.length > 0)
  const hatSoc = !!data?.gauges.some((g) => g.key.startsWith('soc_'))
  const hatSonne = !!(wetter?.sunrise && wetter?.sunset)
  const hatAussicht = !!(prognose3Tage && prognose3Tage.length > 0)
  const hatTemp = !!(wetter?.aktuell?.temperatur_c != null || data?.warmwasser_temperatur_c != null)

  if (!anlageId) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage gewählt.</p></Card>
      </div>
    )
  }

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      {/* L-Header: Live-Status-Zeile (Anlage-Wahl liegt global in der Shell). */}
      <div className="flex items-center justify-end gap-4 flex-wrap">
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
        {mqttStatus?.subscriber_aktiv && (
          <span
            className="text-xs px-2 py-1 rounded-md bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400"
            title={`MQTT: ${mqttStatus.broker}\nNachrichten: ${mqttStatus.empfangene_nachrichten ?? 0}${mqttStatus.letzte_nachricht ? `\nLetzte: ${new Date(mqttStatus.letzte_nachricht).toLocaleTimeString('de-DE')}` : ''}`}
          >
            MQTT {mqttStatus.empfangene_nachrichten ? `(${mqttStatus.empfangene_nachrichten})` : ''}
          </span>
        )}
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          {data?.verfuegbar && (
            <span className="inline-block h-2 w-2 rounded-full bg-green-500" aria-label="Live-Daten verfügbar" />
          )}
          {lastUpdate && <span aria-live="polite">Update: {lastUpdate}</span>}
          <span className="text-xs">(5s)</span>
        </div>
      </div>

      {error && (
        <div role="alert" className="flex items-center gap-2 p-4 bg-red-50 dark:bg-red-900/20 rounded-lg text-red-700 dark:text-red-400">
          <Activity className="h-5 w-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
        </div>
      )}

      {!loading && data && !data.verfuegbar && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-8 text-center">
          <Activity className="h-12 w-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">Keine Live-Daten verfügbar</h2>
          <p className="text-gray-500 dark:text-gray-400 max-w-md mx-auto">
            Um Live-Daten zu sehen, konfiguriere Leistungs-Sensoren über eine der beiden Optionen:
            Sensor-Zuordnung (Einstellungen → Home Assistant) oder MQTT-Inbound (Einstellungen → MQTT).
          </p>
        </div>
      )}

      {!loading && data?.verfuegbar && (() => {
        // Energiefluss-Props einmal — für Karte UND Vollbild-Overlay.
        const flussProps = {
          komponenten: data.komponenten,
          summeErzeugung: data.summe_erzeugung_kw,
          summeVerbrauch: data.summe_verbrauch_kw,
          summePv: data.summe_pv_kw,
          tagesWerte: data.heute_kwh_pro_komponente ?? undefined,
          gauges: data.gauges,
          netzPufferW: selectedAnlage?.netz_puffer_w ?? 100,
          pvSollKw,
        }
        return (
        <div className="space-y-4">
          {/* Energiefluss-Vollbild (⤢ liegt in seiner eigenen Kopfzeile, nicht in
              einer Leerzeile) — Overlay ist fixed, Position im JSX egal. */}
          {eflFokus && (
            <FokusVollbild titel="Energiefluss" icon={Workflow} onClose={() => setEflFokus(false)}>
              <EnergieFluss {...flussProps} />
            </FokusVollbild>
          )}
          {/* Kopf-Region „auf einen Blick": Energiefluss (2/3) ⟷ Sidebar (1/3),
              ab xl nebeneinander (IST, #164 detLAN: Side-by-Side erst ab xl). */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <div className="xl:col-span-2 bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6 flex flex-col">
              {!eflFokus && (
                <EnergieFluss
                  {...flussProps}
                  kopfAktion={
                    <button
                      type="button"
                      onClick={() => setEflFokus(true)}
                      aria-label="Energiefluss: Fokus / Vollbild"
                      className="p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700/50"
                    >
                      <Maximize2 className="h-4 w-4" />
                    </button>
                  }
                />
              )}
            </div>

            {/* Sidebar unter „Heute": Sektionen gestapelt, je eigene FokusKachel. */}
            <div className="space-y-3">
              <FokusKachel titel="Heute" icon={Calendar} kompakt>
                <LiveHeuteKacheln data={data} />
              </FokusKachel>
              {hatSonne && (
                <FokusKachel titel="Sonnenstand" icon={Sunrise} kompakt zeigeTitel>
                  <SunProgressBar
                    sunrise={wetter!.sunrise!}
                    sunset={wetter!.sunset!}
                    solar_noon={wetter!.solar_noon ?? undefined}
                    sonnenstunden={wetter!.sonnenstunden}
                    sonnenstundenBisher={wetter!.sonnenstunden_bisher}
                    sonnenstundenRest={wetter!.sonnenstunden_rest}
                  />
                </FokusKachel>
              )}
              {hatAussicht && (
                <FokusKachel titel="Solar-Aussicht" icon={Sun} kompakt>
                  <SolarAussicht3Tage prognose3Tage={prognose3Tage!} wetter={wetter} heutePvKwh={data.heute_pv_kwh} />
                </FokusKachel>
              )}
              {hatSoc && (
                <FokusKachel titel="Ladezustand" icon={Battery} kompakt>
                  <LiveSocBalken gauges={data.gauges} />
                </FokusKachel>
              )}
              {hatTemp && (
                <FokusKachel titel="Temperaturen" icon={Thermometer} kompakt zeigeTitel>
                  <LiveTemperaturen
                    aussenC={wetter?.aktuell?.temperatur_c}
                    tempMinC={wetter?.temperatur_min_c}
                    tempMaxC={wetter?.temperatur_max_c}
                    warmwasserC={data.warmwasser_temperatur_c}
                  />
                </FokusKachel>
              )}
            </div>
          </div>

          {/* Volle Breite (wie IST): Wetter heute, dann Tagesverlauf als eigener Block. */}
          {wetter && (
            <FokusKachel titel="Wetter heute" icon={CloudSun} zeigeTitel>
              <WetterWidget wetter={wetter} tagesverlauf={tagesverlauf} anlageId={anlageId ?? null} />
            </FokusKachel>
          )}
          {hatTagesverlauf && (
            <FokusKachel titel="Tagesverlauf" icon={LineChart}>
              <TagesverlaufChart serien={tagesverlauf!.serien} punkte={tagesverlauf!.punkte} uebersprungen={tagesverlauf!.uebersprungen} />
            </FokusKachel>
          )}
        </div>
        )
      })()}
    </div>
  )
}
