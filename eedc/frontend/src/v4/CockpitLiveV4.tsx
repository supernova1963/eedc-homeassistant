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
import { Activity, CloudSun, Coins, LineChart, Maximize2, Workflow } from 'lucide-react'
import { useSelectedAnlage } from '../hooks'
import { swrCachePeek, swrCacheStore } from '../hooks/useApiData'
import { liveDashboardApi } from '../api/liveDashboard'
import type {
  BoersenpreisResponse, LiveDashboardResponse, LiveWetterResponse, TagesverlaufResponse,
} from '../api/liveDashboard'
import { wetterApi } from '../api/wetter'
import type { SolarPrognoseTag } from '../api/wetter'
import EnergieFluss from '../components/live/EnergieFluss'
import TagesverlaufChart, { tagesverlaufTabelle } from '../components/live/TagesverlaufChart'
import BoersenpreisBlock, { boersenpreisVollGeparkt } from '../components/live/BoersenpreisBlock'
import WetterWidget from '../components/live/WetterWidget'
import LiveAufEinenBlick, { aufEinenBlickVollGeparkt } from '../components/live/LiveAufEinenBlick'
import { zaehlerstaendeApi, type ZaehlerStand } from '../api/zaehlerstaende'
import { FokusKachel, FokusVollbild } from '../components/blocks'
import { FokusFehltOverlay } from '../components/blocks/FokusFehlt'
import { EinbettenKnopf } from '../components/blocks/EinbettenKnopf'
import { useDeepLinkFokus } from '../hooks/useDeepLinkFokus'
import { ChartDatenTabelle } from '../components/ui'
import { ParkProvider, ParkFuss, Parkbar, usePark } from '../components/park'
import { AnlageLeer } from './OnboardingLeer'
import { useDemoMode, useReportDatenStatus } from './status/AppStatusContext'

const REFRESH_INTERVAL = 5_000
const WETTER_REFRESH_INTERVAL = 300_000
const TAGESVERLAUF_REFRESH_INTERVAL = 60_000
// Börsenpreise ändern sich einmal am Tag (Day-Ahead-Auktion, ~13 Uhr). Der
// 15-Minuten-Takt ist kein Datenbedarf, sondern der Zeitpunkt, zu dem der Block
// die Preise von morgen aufnimmt, ohne dass jemand die Seite neu lädt.
const BOERSENPREIS_REFRESH_INTERVAL = 900_000

// R18-2 (SWR, Erst-Paint): Live pollt ohnehin — aber beim Tab-Wechsel (unmount →
// remount) verlor die Sicht ihren State und zeigte den Spinner. Die letzten Werte
// werden im Sicht-Cache (useApiData-Store, EINE Wahrheit) gehalten und beim
// Remount sofort gezeigt; die Poll-Schleife aktualisiert dann in-place.
interface LiveSeed {
  data: LiveDashboardResponse | null
  wetter: LiveWetterResponse | null
  tagesverlauf: TagesverlaufResponse | null
  prognose3Tage: SolarPrognoseTag[] | null
  boersenpreise: BoersenpreisResponse | null
  /** #377 — Verbrauchszähler; `null`, solange nichts geladen wurde. */
  zaehlerstaende: ZaehlerStand[] | null
  lastUpdate: string | null
}

// persistKey-SoT der Sicht (Element-Park-Scope `eedc-park:v4-cockpit-live`).
const SICHT_KEY = 'v4-cockpit-live'

/**
 * FD-1: Die fünf fokussierbaren Anzeigen dieser Sicht — und damit ihre
 * Deep-Link-Adressen (`#/cockpit/live?fokus=<id>`).
 *
 * ⚠ Vier davon tragen **dieselbe Zeichenkette** wie ihre Park-ID; das ist
 * Absicht (zwei Namen für dieselbe Kachel hülfen niemandem), aber eine ANDERE
 * Ebene: der Park räumt weg, der Deep-Link zeigt her. `live:auf-einen-blick`
 * hat **keine** Park-ID — der Block ist eine Hülle, geparkt werden seine
 * Abschnitte einzeln; für ihn ist die ID hier neu.
 *
 * Diese Liste ist öffentlicher Vertrag (sie steht in fremden HA-Dashboards) —
 * gewächtert von `src/test/fokus-id-vertrag.test.ts`.
 */
export const LIVE_FOKUS_IDS = [
  'live:energiefluss',
  'live:auf-einen-blick',
  'live:wetter-heute',
  'live:tagesverlauf',
  'live:boersenpreis',
] as const

/** Was die Sicht gerade an Daten und Park-Zustand hat — Eingang von
 *  {@link liveFokusVorhanden}. Als eigener Typ, damit die Regel ohne React
 *  prüfbar ist (die Live-Sicht hat keine Render-Probe mit echten Sensoren). */
export interface LiveFokusLage {
  data: LiveDashboardResponse | null
  wetter: LiveWetterResponse | null
  prognose3Tage: SolarPrognoseTag[] | null
  zaehlerstaende: ZaehlerStand[] | null
  boersenpreise: BoersenpreisResponse | null
  hatTagesverlauf: boolean
  boersenpreisAllesGeparkt: boolean
  istGeparkt: (id: string) => boolean
}

/**
 * ⭐ FD-5 für die Live-Sicht: Gibt es die angefragte Anzeige gerade?
 *
 * Die Sicht hat keine `BlockShell` — ohne diese Regel hätten fünf der acht
 * Beispiel-Anzeigen keinen Degradations-Fall, und eine Webseiten-Karte mit
 * falscher, geparkter oder datenloser ID zeigte klaglos die ganze Live-Sicht
 * statt der bestellten Anzeige.
 *
 * ⚠ Die Bedingungen sind dieselben, unter denen die Kachel weiter unten
 * überhaupt gemountet wird. Sie stehen absichtlich in DERSELBEN Datei — eine
 * Änderung am Mount-Zweig muss hier mitgehen, und die Probe prüft beide Seiten.
 */
export function liveFokusVorhanden(id: string, l: LiveFokusLage): boolean {
  if (!(LIVE_FOKUS_IDS as readonly string[]).includes(id)) return false
  if (id === 'live:boersenpreis') {
    const b = l.boersenpreise
    return !!b && (b.tage.length > 0 || !!b.hinweis) && !l.boersenpreisAllesGeparkt && !l.istGeparkt(id)
  }
  // Alles Übrige hängt am Live-Abruf.
  const data = l.data
  if (data == null || !data.verfuegbar) return false
  if (id === 'live:energiefluss') return !l.istGeparkt(id)
  if (id === 'live:wetter-heute') return l.wetter != null && !l.istGeparkt(id)
  if (id === 'live:tagesverlauf') return l.hatTagesverlauf && !l.istGeparkt(id)
  // „Auf einen Blick" ist eine Hülle ohne eigene Park-ID: sie verschwindet,
  // wenn ALLE ihre verfügbaren Abschnitte geparkt sind (R2).
  return !aufEinenBlickVollGeparkt(
    { data, wetter: l.wetter, prognose3Tage: l.prognose3Tage, zaehlerstaende: l.zaehlerstaende ?? undefined },
    l.istGeparkt,
  )
}

export default function CockpitLiveV4(props: { anlageId: number | undefined }) {
  // Element-Park (SLICE 1): Live-Sektionen werden parkbar (Element-Ebene, KEINE
  // BlockShell-Block-Ebene — Gernot 2026-06-26). Energiefluss-Fokus/Vollbild bleibt.
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <CockpitLiveInner {...props} />
    </ParkProvider>
  )
}

function CockpitLiveInner({ anlageId }: { anlageId: number | undefined }) {
  const { selectedAnlage } = useSelectedAnlage()
  // Demo-Modus ist global (Status-Fusszeile schaltet ihn); Live liest ihn nur.
  const { demoMode } = useDemoMode()
  const liveKey = `v4-live:${anlageId}:${demoMode}`
  const seed = useRef(swrCachePeek<LiveSeed>(liveKey)).current // nur am Mount gelesen
  const [data, setData] = useState<LiveDashboardResponse | null>(seed?.data ?? null)
  const [wetter, setWetter] = useState<LiveWetterResponse | null>(seed?.wetter ?? null)
  const [tagesverlauf, setTagesverlauf] = useState<TagesverlaufResponse | null>(seed?.tagesverlauf ?? null)
  const [prognose3Tage, setPrognose3Tage] = useState<SolarPrognoseTag[] | null>(seed?.prognose3Tage ?? null)
  const [boersenpreise, setBoersenpreise] = useState<BoersenpreisResponse | null>(seed?.boersenpreise ?? null)
  const [zaehlerstaende, setZaehlerstaende] = useState<ZaehlerStand[] | null>(seed?.zaehlerstaende ?? null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<string | null>(seed?.lastUpdate ?? null)
  const [eflFokusState, setEflFokus] = useState(false) // Energiefluss-Vollbild (⤢ in seiner eigenen Kopfzeile)
  // FD-1: Im Deep-Link-Modus entscheidet die Adresse — je Render abgeleitet,
  // nie als Initialisierer (die Live-Daten kommen erst mit dem ersten Abruf).
  const deep = useDeepLinkFokus()
  const eflFokus = deep.deepLink ? deep.fokusId === 'live:energiefluss' : eflFokusState

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const wetterIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const tagesverlaufIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const boersenpreisIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const zaehlerIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const activeAnlageRef = useRef(anlageId)
  activeAnlageRef.current = anlageId

  const dataRef = useRef(data)
  dataRef.current = data

  const fetchData = useCallback(async (isAutoRefresh = false) => {
    if (!anlageId) return
    const reqId = anlageId
    // Spinner nur ohne Vor-Daten (R18-2): mit Seed/Poll-Stand wird still
    // aktualisiert — der Remount-Spinner beim Tab-Wechsel entfällt.
    if (!isAutoRefresh && dataRef.current == null) setLoading(true)
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

  // #377 — Zählerstände. Eigener Abruf statt Anhängsel an die Live-Antwort:
  // ein Zählerstand ist keine Energiegröße und hat in ihr nichts zu suchen.
  // Fehlschlag ist still — wer keinen Zähler pflegt, soll keine Fehlermeldung
  // über eine Funktion sehen, die er nicht benutzt.
  const fetchZaehlerstaende = useCallback(async () => {
    if (!anlageId) return
    const reqId = anlageId
    try {
      const result = await zaehlerstaendeApi.heute(reqId)
      if (activeAnlageRef.current !== reqId) return
      setZaehlerstaende(result)
    } catch {
      // still ignorieren — der Abschnitt entfällt, die übrige Sicht bleibt
    }
  }, [anlageId])

  // Börsenpreise sind KEINE Anlagendaten, sondern öffentliche Marktpreise —
  // deshalb ohne `demo`-Schalter: im Demo-Modus wäre eine erfundene Preiskurve
  // nicht anschaulicher, nur falsch.
  const fetchBoersenpreise = useCallback(async () => {
    if (!anlageId) return
    const reqId = anlageId
    try {
      const result = await liveDashboardApi.getBoersenpreise(reqId)
      if (activeAnlageRef.current !== reqId) return
      setBoersenpreise(result)
    } catch {
      // still ignorieren — der Block entfällt, die übrige Sicht bleibt
    }
  }, [anlageId])

  // R18-2: letzten Stand in den Sicht-Cache spiegeln (billiger Map-Write je
  // Poll-Tick) — Quelle für den Erst-Paint-Seed beim nächsten Remount.
  useEffect(() => {
    if (data || wetter || tagesverlauf) {
      swrCacheStore(liveKey, {
        data, wetter, tagesverlauf, prognose3Tage, boersenpreise, zaehlerstaende, lastUpdate,
      } satisfies LiveSeed)
    }
  }, [liveKey, data, wetter, tagesverlauf, prognose3Tage, boersenpreise, zaehlerstaende, lastUpdate])

  useEffect(() => {
    const stoppePolling = () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (wetterIntervalRef.current) clearInterval(wetterIntervalRef.current)
      if (tagesverlaufIntervalRef.current) clearInterval(tagesverlaufIntervalRef.current)
      if (boersenpreisIntervalRef.current) clearInterval(boersenpreisIntervalRef.current)
      if (zaehlerIntervalRef.current) clearInterval(zaehlerIntervalRef.current)
      intervalRef.current = null
      wetterIntervalRef.current = null
      tagesverlaufIntervalRef.current = null
      boersenpreisIntervalRef.current = null
      zaehlerIntervalRef.current = null
    }

    const startePolling = () => {
      stoppePolling()
      intervalRef.current = setInterval(() => fetchData(true), REFRESH_INTERVAL)
      wetterIntervalRef.current = setInterval(() => fetchWetter(), WETTER_REFRESH_INTERVAL)
      tagesverlaufIntervalRef.current = setInterval(() => fetchTagesverlauf(), TAGESVERLAUF_REFRESH_INTERVAL)
      boersenpreisIntervalRef.current = setInterval(() => fetchBoersenpreise(), BOERSENPREIS_REFRESH_INTERVAL)
      // #377: Ein Gas- oder Wasserzähler bewegt sich stündlich, nicht im
      // 5-Sekunden-Takt des Energieflusses — derselbe Takt wie der Tagesverlauf.
      zaehlerIntervalRef.current = setInterval(() => fetchZaehlerstaende(), TAGESVERLAUF_REFRESH_INTERVAL)
    }

    // Eine unsichtbare Seite pollt nicht. Der 5-s-Takt ist für den
    // Energiefluss richtig, solange jemand hinsieht — ein vergessener Tab
    // oder ein Wandtablet im Standby fragte HA sonst rund um die Uhr ab, und
    // im Add-on läuft jeder dieser Abrufe durch den Ingress-Proxy von HA Core.
    const beiSichtwechsel = () => {
      if (document.visibilityState === 'hidden') {
        stoppePolling()
        return
      }
      // Rückkehr: sofort auffrischen, statt bis zum nächsten Tick alte Werte
      // zu zeigen.
      fetchData(true)
      fetchWetter()
      fetchTagesverlauf()
      fetchBoersenpreise()
      fetchZaehlerstaende()
      startePolling()
    }

    fetchData(false)
    fetchWetter()
    fetchTagesverlauf()
    fetchBoersenpreise()
    fetchZaehlerstaende()
    startePolling()
    document.addEventListener('visibilitychange', beiSichtwechsel)
    return () => {
      document.removeEventListener('visibilitychange', beiSichtwechsel)
      stoppePolling()
    }
  }, [fetchData, fetchWetter, fetchTagesverlauf, fetchBoersenpreise, fetchZaehlerstaende])

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

  // R2 der Park-Doktrin: Seit dem 22.09.2026 sind die neun Börsenpreis-Kennzahlen
  // und das Diagramm EINZELN parkbar — also muss die Hülle darum verschwinden,
  // sobald der Anwender sie alle geparkt hat. Sonst bliebe die Karte samt Titel
  // und ⤢-Knopf leer im Bild stehen (`check:park-gate` R2).
  //
  // ⚠ Welche IDs das sind und warum eine LEERE Liste nicht als „alles geparkt"
  // zählt, steht in `boersenpreisVollGeparkt` — dort unter einer Probe, weil
  // diese Sicht keine Render-Probe hat.
  //
  // Der äußere `<Parkbar id="live:boersenpreis">` bleibt: Wer den ganzen Block
  // auf einmal wegräumen will, tut das weiterhin mit EINER Geste und bekommt
  // EINEN Chip statt zehn.
  const park = usePark()
  const boersenpreisAllesGeparkt = useMemo(
    () => !!boersenpreise && boersenpreisVollGeparkt(boersenpreise, park.istGeparkt),
    [boersenpreise, park],
  )

  // FD-5: Lage der Sicht für die Deep-Link-Degradation (Regel s. o. am Modul).
  const fokusLage: LiveFokusLage = {
    data, wetter, prognose3Tage, zaehlerstaende, boersenpreise,
    hatTagesverlauf, boersenpreisAllesGeparkt, istGeparkt: park.istGeparkt,
  }

  // Live-Status in die app-weite Fusszeile melden (G11): Frische · Live-Punkt ·
  // Quelle (P5-Provenance; erster Konsument). MQTT/Verbindung liegt seit P2 im
  // globalen Status-Hook der Fusszeile.
  useReportDatenStatus({
    live: data?.verfuegbar,
    aktualisiertText: lastUpdate,
    intervallText: '(5s)',
    quelle: demoMode ? 'Demo-Daten' : 'Live-Sensoren',
  })

  if (!anlageId) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <AnlageLeer titel="Noch keine Anlage gewählt." />
      </div>
    )
  }

  // ⚠ Erst entscheiden, wenn der erste Abruf durch ist UND Daten da sind:
  // `loading` steht beim allerersten Render noch auf `false` (es wird im Effekt
  // gesetzt) — ohne diese Bedingung blitzte der Hinweis vor dem Spinner auf.
  // Und ein Abruf-FEHLER ohne Daten (Backend-Neustart, Netz weg) ist kein Urteil
  // über die Anzeige: dann fällt die Sicht unten in ihren Fehlerbanner, statt in
  // der HA-Karte „gibt es nicht (mehr)" zu behaupten (Nachmessung 22.09., Punkt 3).
  const abrufDurch = data != null
  if (deep.deepLink && deep.fokusId != null && !loading && abrufDurch && !liveFokusVorhanden(deep.fokusId, fokusLage)) {
    // Ohne Zeitraum-Teil: Live hat keine Zeitraum-Navigation, an der sich etwas
    // ändern ließe — „nicht für diesen Zeitraum" wäre hier ein falscher Rat.
    return <FokusFehltOverlay fokusId={deep.fokusId} />
  }

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      {/* Live-Status (Punkt · Update · MQTT · Demo) liegt jetzt in der app-weiten
          Status-Fusszeile (G11) — via useReportDatenStatus gemeldet. */}
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
            <FokusVollbild
              titel="Energiefluss" icon={Workflow}
              deepLink={deep.deepLink}
              // FD-2: auch der Energiefluss ist verlinkbar — er hat sein eigenes
              // Overlay (kein FokusKachel), also auch seinen eigenen Knopf.
              aktionen={(ansicht) => <EinbettenKnopf fokusId="live:energiefluss" ansicht={ansicht} />}
              onClose={() => setEflFokus(false)}
            >
              <EnergieFluss {...flussProps} />
            </FokusVollbild>
          )}
          {/* Kopf-Region „auf einen Blick": Energiefluss (2/3) ⟷ Kennzahl-Block (1/3),
              ab xl nebeneinander (IST, #164 detLAN: Side-by-Side erst ab xl).
              Der Kennzahl-Block ist EIN Container (eine Vollbild-Funktion) mit
              ausblendbaren Abschnitten — ersetzt die früheren fünf verschachtelten
              Fokus-Kacheln, die das Stapeln zerlegten (detLAN 2026-06-28). */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 items-start">
            {/* Energiefluss ist parkbar (Element-Ebene); Grid-Span am Parkbar-Wrapper,
                damit das Layout beim Parken sauber reflowt. Vollbild bleibt erhalten. */}
            <Parkbar id="live:energiefluss" titel="Energiefluss" className="xl:col-span-2">
              <div className="h-full bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6 flex flex-col">
                {!eflFokus && (
                  <EnergieFluss
                    {...flussProps}
                    kopfAktion={
                      // D14-16: „Vergrößern" unter 640 px ausblenden (nicht entfernen).
                      // In der Deep-Link-Ansicht gibt es nichts zu vergrößern (das
                      // Overlay IST die Karte) und keinen Weg zurück.
                      deep.deepLink ? undefined : (
                        <button
                          type="button"
                          onClick={() => setEflFokus(true)}
                          aria-label="Energiefluss: Fokus / Vollbild"
                          className="max-sm:hidden p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700/50"
                        >
                          <Maximize2 className="h-4 w-4" />
                        </button>
                      )
                    }
                  />
                )}
              </div>
            </Parkbar>

            {/* Kennzahl-Block „Auf einen Blick" (1/3): Heute · Sonnenstand ·
                Solar-Aussicht · Ladezustand · Temperaturen als ausblendbare
                Abschnitte in EINEM Container mit einer Vollbild-Funktion. */}
            <LiveAufEinenBlick data={data} wetter={wetter} prognose3Tage={prognose3Tage} zaehlerstaende={zaehlerstaende ?? undefined} />
          </div>

          {/* Volle Breite (wie IST): Wetter heute, dann Tagesverlauf — je parkbar. */}
          {wetter && (
            <Parkbar id="live:wetter-heute" titel="Wetter heute">
              <FokusKachel titel="Wetter heute" fokusId="live:wetter-heute" icon={CloudSun} zeigeTitel>
                <WetterWidget wetter={wetter} tagesverlauf={tagesverlauf} anlageId={anlageId ?? null} />
              </FokusKachel>
            </Parkbar>
          )}
          {hatTagesverlauf && (
            <Parkbar id="live:tagesverlauf" titel="Tagesverlauf">
              <FokusKachel
                titel="Tagesverlauf"
                fokusId="live:tagesverlauf"
                icon={LineChart}
                // Paket CT (Pilot): Tabellen-Ablesung im Fokus-Overlay — dieselben
                // Serien/Punkte wie der Butterfly-Chart, Vorzeichen statt _pos/_neg.
                tabelle={(() => {
                  const t = tagesverlaufTabelle(tagesverlauf!.serien, tagesverlauf!.punkte)
                  return (
                    <ChartDatenTabelle
                      xLabel="Zeit"
                      xKey="zeit"
                      spalten={t.spalten}
                      daten={t.daten}
                      zeilen={24}
                      csvDateiname="live_tagesverlauf.csv"
                    />
                  )
                })()}
              >
                <TagesverlaufChart serien={tagesverlauf!.serien} punkte={tagesverlauf!.punkte} uebersprungen={tagesverlauf!.uebersprungen} />
              </FokusKachel>
            </Parkbar>
          )}
        </div>
        )
      })()}

      {/* Börsenpreis heute + morgen (#335) — BEWUSST außerhalb des
          `data.verfuegbar`-Zweigs. Day-Ahead-Preise sind öffentliche Marktdaten
          und hängen an keinem Sensor: Wer noch keine Leistungssensoren zugeordnet
          hat, sieht auf dieser Seite sonst nur „Keine Live-Daten verfügbar" —
          und einen Block, der ohne jede Einrichtung funktioniert hätte, nie.
          Eigener Block statt Overlay im Tagesverlauf: der zeigt 10-Minuten-
          Leistung von heute, dieser Stundenpreise über zwei Tage.
          Erscheint mit Preisen ODER mit dem Grund, warum es keine gibt.

          `!loading` seit 13.08.2026 (rapahl + Gernot, beide sichtbar): Die
          Börsenpreise sind öffentliche Marktdaten und brauchen keinen
          Sensor-Abruf — ihr Fetch ist regelmäßig als erster zurück. Der Block
          stand dann für ~1 s als EINZIGER Inhalt oben im Bild, direkt unter dem
          ~80 px hohen Lade-Spinner, und rutschte weit nach unten, sobald
          Energiefluss und Kennzahlen den Spinner ersetzten. Das las sich wie
          „der Chart wird überschrieben"; tatsächlich ist der Platzhalter nur
          viel kleiner als sein Inhalt. Der Block bleibt bewusst außerhalb des
          `data.verfuegbar`-Zweigs (s. o.) — er wartet jetzt nur, bis der
          Ladezustand entschieden ist. Die Alternative, ein Skeleton in
          Blockhöhe, müsste die Höhe des Energieflusses raten. */}
      {!loading && boersenpreise && (boersenpreise.tage.length > 0 || boersenpreise.hinweis)
        && !boersenpreisAllesGeparkt && (
        <Parkbar id="live:boersenpreis" titel="Börsenpreis">
          <FokusKachel titel="Börsenpreis heute & morgen" fokusId="live:boersenpreis" icon={Coins} zeigeTitel>
            <BoersenpreisBlock daten={boersenpreise} />
          </FokusKachel>
        </Parkbar>
      )}

      {/* Element-Park-Fuß (SLICE 1): Hinweiszeile + „Geparkt (n)". Inert leer. */}
      <ParkFuss bereit={!loading} />
    </div>
  )
}
