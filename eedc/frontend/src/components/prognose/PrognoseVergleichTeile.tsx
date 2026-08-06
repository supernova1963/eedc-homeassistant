/**
 * Prognosen-Vergleich — geteilte Element-Bausteine (A.5 Sub 4, Blöcke ④+⑤).
 *
 * Eine Code-Wahrheit: IST-Tab `pages/aussichten/PrognoseVergleichTab.tsx` UND die
 * v4-Sicht komponieren aus diesen Teilen. Jeder Teil = ein parkbares Element (v4)
 * bzw. direkt gerendert (IST). Datenladung + alle Steuer-States liegen im Hook
 * `usePrognoseVergleich` (einmal pro Sicht), die Karten sind reine Darstellung.
 *
 * Block ④ (Genauigkeit): KPI-Matrix · Status · Lernfaktor O1+O2 · Stratifizierung ·
 * Heatmap · Genauigkeits-Tracking (Tage-Fenster 7/10/30 gekapselt).
 * Block ⑤ (Profil): Stundenprofil-Chart · 24h-Tabelle · 7-Tage-Tabelle.
 *
 * Format: R3 Quellen-Farben via `PROGNOSE_QUELLEN_TEXT`/`PROGNOSE_QUELLEN_COLORS`
 * (statt inline text-yellow/orange/blue/green). R1: de-DE-Zahlen via `fmtZahl`. NK
 * bewusst tages-/stunden-präzise (kWh 1 NK, kW 2 NK) — diese Vergleichswerte leben
 * im kWh/kW-Regime, R2-MWh-Umschaltung greift hier nicht (Regel-0a-Einzelfall).
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { Sun, CloudSun, Cloud, CloudRain, CloudSnow, CloudLightning, BarChart3 } from 'lucide-react'
import { Button, Card, ChartLegende, Checkbox, SegmentControl, buttonClasses, Table, TableHead, TableBody, TableFoot } from '../ui'
import { ZELLE, KOPF_ZELLE } from '../ui/tabelleMasse'
import { SimpleTooltip } from '../ui/FormelTooltip'
import { useLegendenToggle } from '../../hooks'
import { Parkbar } from '../park'
import {
  aussichtenApi, PrognosenVergleich, GenauigkeitsResponse, AsymmetrieEintrag, Tageshaelfte,
} from '../../api/aussichten'
import { energieProfilApi } from '../../api/energie_profil'
import { getStratifizierung, StratifizierungResponse, Wetterklasse, wetterBackfill } from '../../api/korrekturprofil'
import { KorrekturprofilHeatmapCard } from '../../pages/aussichten/KorrekturprofilHeatmapCard'
import { PROGNOSE_QUELLEN_COLORS, PROGNOSE_QUELLEN_TEXT, PROGNOSE_DASH, STATUS_TEXT_CLASS, fmtZahl, xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, slotZeitspanne, heuteIso, verschiebeIsoTage } from '../../lib'
import { useChartTheme } from '../../context/ThemeContext'
import {
  ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine,
} from 'recharts'

const Q = PROGNOSE_QUELLEN_TEXT
const eedcKlasse = (hasEedc: boolean) => (hasEedc ? Q.eedc : 'text-gray-400 dark:text-gray-500')

function fmtKwh(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${fmtZahl(v, 1)} kWh`
}

// ── Daten-/State-Hook (geteilt von IST + v4) ──────────────────────────────────
export interface PrognoseVergleichVM {
  loading: boolean
  error: string | null
  data: PrognosenVergleich | null
  genauigkeit: GenauigkeitsResponse | null
  stratifizierung: StratifizierungResponse | null
  anlageId: number
  genauigkeitsModus: 'kompakt' | 'diagnostisch'
  setGenauigkeitsModus: (m: 'kompakt' | 'diagnostisch') => void
  genauigkeitsTage: number
  setGenauigkeitsTage: (t: number) => void
  ausreisserAusblenden: boolean
  setAusreisserAusblenden: (v: boolean) => void
  backfillRunning: boolean
  backfillResult: string | null
  backfillError: string | null
  handleWetterBackfill: () => Promise<void>
  reload: () => void
}

export function usePrognoseVergleich(anlageId: number): PrognoseVergleichVM {
  const [data, setData] = useState<PrognosenVergleich | null>(null)
  const [genauigkeit, setGenauigkeit] = useState<GenauigkeitsResponse | null>(null)
  const [stratifizierung, setStratifizierung] = useState<StratifizierungResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadTick, setReloadTick] = useState(0)
  const [genauigkeitsModus, setGenauigkeitsModus] = useState<'kompakt' | 'diagnostisch'>('kompakt')
  const [genauigkeitsTage, setGenauigkeitsTage] = useState(10)
  const [ausreisserAusblenden, setAusreisserAusblenden] = useState(false)
  const [backfillRunning, setBackfillRunning] = useState(false)
  const [backfillResult, setBackfillResult] = useState<string | null>(null)
  const [backfillError, setBackfillError] = useState<string | null>(null)

  const handleWetterBackfill = useCallback(async () => {
    // D11-9(a): die Status-Meldung am Anfang NICHT leeren — sonst verschwindet die
    // „✓ …"-Zeile kurz (Block schrumpft → der Block darunter springt eine Zeile hoch
    // und wieder runter = der von Gernot beschriebene Reflow). Alte Meldung bleibt
    // stehen, bis die neue sie atomar ersetzt; den jeweils anderen Zustand am ENDE leeren.
    setBackfillRunning(true)
    try {
      const res = await wetterBackfill(anlageId, 730)
      if (res.status === 'ok') {
        // Nur wenn wirklich etwas nachgeladen wurde, die Stratifizierung neu holen +
        // tauschen — sonst „blitzt" die Sicht bei „0 Stunden / 0 Tage" grundlos.
        const geladen = (res.stunden_geupdated ?? 0) > 0 || (res.tage_geupdated ?? 0) > 0
        if (geladen) {
          setBackfillResult(`${res.stunden_geupdated ?? 0} Stunden / ${res.tage_geupdated ?? 0} Tage geladen` +
            (res.von && res.bis ? ` (${res.von} – ${res.bis})` : ''))
          setStratifizierung(await getStratifizierung(anlageId, 90).catch(() => null))
        } else {
          setBackfillResult('Wetter-Historie ist bereits vollständig — nichts nachzuladen.')
        }
        setBackfillError(null)
      } else if (res.status === 'skipped') {
        setBackfillError(`Übersprungen: ${res.grund ?? 'unbekannter Grund'}`); setBackfillResult(null)
      } else {
        setBackfillError(res.fehler ?? 'Backfill fehlgeschlagen'); setBackfillResult(null)
      }
    } catch (err) {
      setBackfillError(err instanceof Error ? err.message : 'Netzwerk-Fehler'); setBackfillResult(null)
    } finally {
      setBackfillRunning(false)
    }
  }, [anlageId])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true); setError(null)
      try {
        const [prognosen, strat] = await Promise.all([
          aussichtenApi.getPrognosenVergleich(anlageId),
          getStratifizierung(anlageId, 90).catch(() => null),
        ])
        if (!cancelled) { setData(prognosen); setStratifizierung(strat) }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Fehler beim Laden')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [anlageId, reloadTick])

  useEffect(() => {
    let cancelled = false
    aussichtenApi.getPrognosenGenauigkeit(anlageId, genauigkeitsTage, ausreisserAusblenden)
      .then(acc => { if (!cancelled) setGenauigkeit(acc) })
      .catch(() => { if (!cancelled) setGenauigkeit(null) })
    return () => { cancelled = true }
  }, [anlageId, genauigkeitsTage, ausreisserAusblenden, reloadTick])

  return {
    loading, error, data, genauigkeit, stratifizierung, anlageId,
    genauigkeitsModus, setGenauigkeitsModus, genauigkeitsTage, setGenauigkeitsTage,
    ausreisserAusblenden, setAusreisserAusblenden,
    backfillRunning, backfillResult, backfillError, handleWetterBackfill,
    reload: () => setReloadTick(t => t + 1),
  }
}

// ── Abgeleitete Daten (Chart/Tabellen) ────────────────────────────────────────
function chartDatenVon(data: PrognosenVergleich) {
  return Array.from({ length: 24 }, (_, h) => {
    const om = data.openmeteo_stundenprofil.find(s => s.stunde === h)
    const eedc = data.eedc_stundenprofil.find(s => s.stunde === h)
    const sc = data.solcast_stundenprofil.find(s => s.stunde === h)
    const sfml = (data.sfml_stundenprofil ?? []).find(s => s.stunde === h)
    const ist = data.ist_stundenprofil.find(s => s.stunde === h)
    return {
      stunde: `${h}:00`, openmeteo: om?.kw ?? 0, eedc: eedc?.kw ?? null,
      solcast: sc?.kw ?? 0, solcast_p10: sc?.p10_kw ?? 0, solcast_p90: sc?.p90_kw ?? 0,
      sfml: sfml?.kw ?? null, ist: ist?.kw ?? null,
    }
  })
}
type ChartZeile = ReturnType<typeof chartDatenVon>[number]

/** Ab dieser Leistung gilt eine Stunde dem Chart als *hell*. */
const HELL_KW = 0.05
/** Ab dieser Leistung bekommt eine Stunde eine Tabellenzeile. */
const ZEILE_MIN_KW = 0.01

/**
 * Trägt diese Stunde einen Wert? — EINE Definition davon, **welche** Spalten
 * dabei zählen (N-51). Der Zeilenfilter der 24h-Tabelle kannte `eedc` nicht,
 * der Chart-Helfer schon: zwei Fassungen derselben Frage.
 *
 * Die **Schwelle** bleibt bewusst beim Aufrufer, und damit auch der Unterschied,
 * der keiner Drift entspringt: der Chart sucht den *hellen Bereich* und legt
 * absichtlich eine Randstunde daneben (`slice`), die Tabelle *wählt* Zeilen aus.
 * Beides zu vereinheitlichen wäre eine andere Tabelle gewesen — gemessen am
 * 04.08. gegen die Anlage: +2 Zeilen (6:00 und 22:00, beide ohne Ertrag).
 * Die Ergänzung um `eedc` selbst ändert dort 0 Zeilen (15 vorher wie nachher).
 */
function hatWert(r: ChartZeile, schwelleKw: number): boolean {
  return Math.max(r.openmeteo || 0, r.solcast || 0, r.eedc ?? 0, r.sfml ?? 0, r.ist ?? 0) > schwelleKw
}

function sichtbareStunden(chartData: ReturnType<typeof chartDatenVon>) {
  const helle: number[] = []
  for (let i = 0; i < chartData.length; i++) {
    if (hatWert(chartData[i], HELL_KW)) helle.push(i)
  }
  const hMin = helle.length > 0 ? Math.max(0, helle[0] - 1) : 0
  const hMax = helle.length > 0 ? Math.min(23, helle[helle.length - 1] + 1) : 23
  return chartData.slice(hMin, hMax + 1)
}
export interface StundenSumme {
  /** Letzte volle Stunde mit IST — `null`, wenn der Tag noch kein IST hat. */
  bisStunde: number | null
  /** Ganzer Tag abgedeckt ⇒ die Zeile trägt keine „bis HH:00"-Kennzeichnung. */
  vollerTag: boolean
  openmeteo: number
  eedc: number
  solcast: number
  sfml: number
  /** Σ IST derselben Stunden — `null`, solange nichts gemessen ist. */
  ist: number | null
}

/**
 * Σ-Zeile des Stundenvergleichs: sie vergleicht **nur den bisher gelaufenen
 * Tag** (Entscheid B4, Rainer PN 90004/89980).
 *
 * Vorher stand die Prognose des **ganzen** Tages gegen das IST **bis jetzt** —
 * „Σ eedc 64,1 ▲ 59,7" gegen „IST 4,4". Die Abweichung maß damit vor allem,
 * wie spät am Tag man hinsieht.
 *
 * Grenze ist die letzte Stunde, für die ein IST vorliegt, höchstens jedoch
 * `aktuelleStunde`: nach der Backward-Konvention trägt Slot N die Energie von
 * [N-1, N), Slot `aktuelleStunde + 1` läuft also noch. Stunden ohne IST bleiben
 * in **allen** Spalten außen vor, damit die vier Summen paarweise dasselbe
 * Fenster meinen — auch bei einer Messlücke mittendrin.
 *
 * Kein IST im Tag (Prognose für morgen) ⇒ `bisStunde === null`: die Zeile zeigt
 * die volle Prognosesumme und **kein** Delta — keine 0-%-Behauptung.
 */
export function stundenSummeVon(chartData: ReturnType<typeof chartDatenVon>, aktuelleStunde: number | null): StundenSumme {
  const grenze = aktuelleStunde ?? 23
  const mitIst = chartData.filter((r, h) => h <= grenze && r.ist !== null)
  const bisStunde = mitIst.length > 0 ? parseInt(mitIst[mitIst.length - 1].stunde) : null
  const zeilen = bisStunde === null ? chartData : mitIst
  const summe = (f: (r: ReturnType<typeof chartDatenVon>[number]) => number) => zeilen.reduce((s, r) => s + f(r), 0)
  return {
    bisStunde,
    vollerTag: bisStunde !== null && mitIst.length === chartData.length,
    openmeteo: summe(r => r.openmeteo),
    eedc: summe(r => r.eedc ?? 0),
    solcast: summe(r => r.solcast),
    sfml: summe(r => r.sfml ?? 0),
    ist: bisStunde === null ? null : summe(r => r.ist ?? 0),
  }
}

function vergleichsTageVon(data: PrognosenVergleich, genauigkeit: GenauigkeitsResponse | null, hasEedc: boolean) {
  // LOKALES Datum (F-5): mit `toISOString()` stand hier zwischen 00:00 und 02:00
  // Ortszeit noch gestern, während `data.*_heute_kwh` vom Backend den heutigen
  // Tag beschreibt. Die „heute"-Zeile trug dann das Datum D−1 mit den Werten
  // von D, und `zukunft` (Filter `> heute`) lieferte D gleich noch einmal —
  // zwei Zeilen mit identischen Zahlen in allen drei Quellenspalten.
  const heute = heuteIso()
  const historisch = (genauigkeit?.tage ?? []).filter(t => t.datum < heute).slice(-4).map(t => ({
    datum: t.datum, om_kwh: t.openmeteo_kwh, eedc_kwh: t.eedc_kwh, sc_kwh: t.solcast_kwh,
    sc_p10: null as number | null, sc_p90: null as number | null,
    // SFML hat für die Vergangenheit keinen Wert: eedc führt darüber bewusst keine
    // Mitschrift — genau die wäre das „rolling", gegen das die Tom-HA-Zusage geht.
    sfml_kwh: null as number | null,
    wetter_symbol: t.wetter_symbol ?? null, temp_max: t.temperatur_max_c ?? null, ist_kwh: t.ist_kwh, ist_partiell: false,
  }))
  const omHeute = data.openmeteo_tage.find(om => om.datum === heute)
  const heuteZeile = {
    datum: heute, om_kwh: data.openmeteo_heute_kwh, eedc_kwh: hasEedc ? data.eedc_heute_kwh : null,
    sc_kwh: data.solcast_heute_kwh, sc_p10: data.solcast_p10_kwh ?? null, sc_p90: data.solcast_p90_kwh ?? null,
    sfml_kwh: data.sfml_heute_kwh ?? null,
    wetter_symbol: (omHeute?.wetter_symbol ?? null) as string | null, temp_max: (omHeute?.temperatur_max_c ?? null) as number | null,
    ist_kwh: data.ist_heute_kwh, ist_partiell: true,
  }
  // SFML liefert zwei Zukunftstage (morgen, übermorgen); der dritte bleibt leer.
  // Zuordnung über das **Datum**, nicht über die Position in der OpenMeteo-Liste:
  // fehlt dort ein Tag, säße der Übermorgen-Wert sonst auf dem falschen Datum.
  const tagPlus = (n: number) => verschiebeIsoTage(heute, n)
  const sfmlJeDatum: Record<string, number | null> = {
    [tagPlus(1)]: data.sfml_morgen_kwh ?? null,
    [tagPlus(2)]: data.sfml_uebermorgen_kwh ?? null,
  }
  const zukunft = data.openmeteo_tage.filter(om => om.datum > heute).slice(0, 3).map((om) => {
    const sc = data.solcast_tage.find(s => s.datum === om.datum)
    return {
      datum: om.datum, om_kwh: om.pv_prognose_kwh as number | null,
      // Prognose-Kanon: eedc je Tag kommt jetzt vom Backend (kein client-
      // seitiges `om × Lernfaktor`-Nachrechnen mehr — war eine Drift-Quelle).
      eedc_kwh: hasEedc ? (om.eedc_kwh ?? null) : null,
      sc_kwh: sc?.kwh ?? null, sc_p10: sc?.p10 ?? null, sc_p90: sc?.p90 ?? null,
      sfml_kwh: sfmlJeDatum[om.datum] ?? null,
      wetter_symbol: om.wetter_symbol as string | null, temp_max: om.temperatur_max_c as number | null,
      ist_kwh: null as number | null, ist_partiell: false,
    }
  })
  return [...historisch, heuteZeile, ...zukunft]
}

// ── Hilfskomponenten ──────────────────────────────────────────────────────────
function WetterIcon({ symbol, className = 'h-5 w-5' }: { symbol: string; className?: string }) {
  switch (symbol) {
    case 'sunny': return <Sun className={`${className} text-yellow-500`} />
    case 'mostly_sunny': return <CloudSun className={`${className} text-yellow-400`} />
    case 'partly_cloudy': return <CloudSun className={`${className} text-yellow-300`} />
    case 'cloudy': return <Cloud className={`${className} text-gray-500`} />
    case 'rainy': case 'drizzle': case 'showers': return <CloudRain className={`${className} text-blue-500`} />
    case 'snowy': case 'snow_showers': return <CloudSnow className={`${className} text-blue-300`} />
    case 'thunderstorm': return <CloudLightning className={`${className} text-purple-500`} />
    default: return <Sun className={`${className} text-yellow-400`} />
  }
}
function formatDatum(datum: string): string {
  return new Date(datum).toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })
}
/**
 * Tabelle ab `sm` — darunter übernimmt die Kartenliste daneben (N-127).
 *
 * Vorher stand hier `DatendichtFallback`: unter `sm` ersetzte er die Tabelle
 * durch einen Hinweiskasten („bitte Gerät ins Querformat drehen oder Desktop
 * verwenden"), und im Querformat durch „Auflösung zu gering". Der Inhalt war
 * auf dem Handy also **gar nicht** erreichbar — genau das schließt
 * `KONZEPT-MOBILE.md` M1 aus (Gernot, 2026-05-31: „der `<HideOnMobile>`-Wrapper
 * entfällt … nichts wird auf Mobile unerreichbar, nur de-priorisiert").
 * Das Muster dafür gab es im Baum längst — eine Datenliste, zwei Render-Pfade
 * (`PVStringVergleich`, `KomponentenFinanzTabelle`, `TKonto`).
 */
function TabelleAbSm({ children }: { children: React.ReactNode }) {
  return <div className="hidden sm:block">{children}</div>
}

/** Kartenliste unter `sm` — die mobile Hälfte derselben Datenliste. */
function MobilKarten({ children }: { children: React.ReactNode }) {
  return <div className="sm:hidden space-y-2">{children}</div>
}

interface KartenZeile {
  label: React.ReactNode
  wert: React.ReactNode
  /** Farbklasse der Quelle — dieselbe wie ihre Tabellenspalte. */
  klasse?: string
  /** Zusatz unter dem Wert (Δ, VM/NM, Band) — klein und grau. */
  zusatz?: React.ReactNode
}

/** Eine Karte = eine Tabellenzeile der Breitansicht, hochkant gelesen. */
function MobilKarte({ titel, kopfWert, zeilen, rahmenKlasse = '' }: {
  titel: React.ReactNode
  kopfWert?: React.ReactNode
  zeilen: KartenZeile[]
  rahmenKlasse?: string
}) {
  return (
    <div className={`rounded-lg border border-gray-200 dark:border-gray-700 p-3 ${rahmenKlasse}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-gray-900 dark:text-white">{titel}</span>
        {kopfWert}
      </div>
      <dl className="mt-2 space-y-1 text-sm">
        {zeilen.map((z, i) => (
          <div key={i} className="flex items-baseline justify-between gap-3">
            <dt className={`shrink-0 ${z.klasse || 'text-gray-500 dark:text-gray-400'}`}>{z.label}</dt>
            <dd className="text-right tabular-nums text-gray-700 dark:text-gray-300">
              {z.wert}
              {z.zusatz && <span className="ml-1.5">{z.zusatz}</span>}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
function IstUnvollstaendigPopover({ fehlendeStunden, anlageId, onReloaded }: { fehlendeStunden: number[]; anlageId: number; onReloaded: () => void }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<{ tone: 'success' | 'warning' | 'error'; msg: string } | null>(null)
  const ref = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])
  // `fehlendeStunden` sind Backward-Slots (Slot h = [h-1, h)) — die Zeitspanne
  // kommt deshalb aus demselben SoT wie die Chart-Tooltips, nicht aus `h + 1`.
  const stundenLabel = fehlendeStunden.length === 0 ? '—'
    : fehlendeStunden.length === 1 ? `Stunde ${slotZeitspanne(fehlendeStunden[0]).replace(' Uhr', '')}`
    : `Stunden ${fehlendeStunden.map(h => `${h}:00`).join(', ')}`
  const handleReaggregate = async () => {
    setBusy(true); setFeedback(null)
    try {
      // Lokales Datum (F-5): mit dem UTC-Datum hat dieser Knopf nachts
      // **gestern** neu berechnet — und die Meldung „0/24 Stunden mit Daten"
      // bezog sich dann auf den falschen Tag.
      const heute = heuteIso()
      const res = await energieProfilApi.reaggregateTag(anlageId, heute)
      if (res.stunden_mit_messdaten > 0) setFeedback({ tone: 'success', msg: `Neu berechnet: ${res.stunden_mit_messdaten}/24 Stunden mit Daten.` })
      else setFeedback({ tone: 'warning', msg: 'Reaggregiert, aber HA Statistics liefert noch keine Werte. In ~10 Min erneut versuchen.' })
      onReloaded()
    } catch (e) {
      setFeedback({ tone: 'error', msg: e instanceof Error ? e.message : 'Reaggregation fehlgeschlagen' })
    } finally { setBusy(false) }
  }
  return (
    <span ref={ref} className="relative inline-block">
      <button type="button" onClick={(e) => { e.stopPropagation(); setOpen(o => !o) }} className="ml-1 text-amber-500 hover:text-amber-600 cursor-pointer" aria-label="IST-Daten unvollständig">⚠</button>
      {open && (
        // D14-12 (detLAN #113): Pop-up-Kanon — dunkel in beiden Modi (= ChartTooltip/
        // SimpleTooltip-Linie); vorher als einziges Pop-up hell (bg-white).
        <div className="absolute right-0 top-full mt-1 z-[10000] w-72 max-w-[calc(100vw-2rem)] p-3 bg-gray-900 dark:bg-gray-950 border border-gray-700 rounded-lg shadow-xl text-left">
          <div className="text-xs font-semibold text-white mb-1">IST-Daten unvollständig</div>
          <div className="text-xs text-gray-300 leading-relaxed mb-2">
            Ohne Werte für {stundenLabel}. Falls eedc oder HA kürzlich neu gestartet wurden, schließt sich die Lücke beim nächsten Snapshot-Zyklus (max. 1 h). Bleibt sie bestehen, ist wahrscheinlich der kumulative Zähler im Sensor-Mapping nicht gesetzt.
          </div>
          {feedback && (
            // Chips auf dem dunklen Pop-up in beiden Modi in der Dark-Variante.
            <div className={`text-xs mb-2 px-2 py-1 rounded ${feedback.tone === 'success' ? 'bg-green-900/30 text-green-300' : feedback.tone === 'warning' ? 'bg-amber-900/30 text-amber-300' : 'bg-red-900/30 text-red-300'}`}>{feedback.msg}</div>
          )}
          <div className="flex gap-2">
            <Button type="button" variant="primary" size="sm" className="flex-1" onClick={handleReaggregate} loading={busy}>{busy ? 'Berechne…' : 'Tag neu berechnen'}</Button>
            {/* Absprung in die Datenquellen-Fläche (Sensor-/Topic-Zuordnung). */}
            <a
              href="#/einstellungen/datenquellen"
              className={buttonClasses({ variant: 'secondary', size: 'sm' })}
            >Sensor-Mapping</a>
          </div>
        </div>
      )}
    </span>
  )
}
function fmtKwhBand(v: number | null, p10: number | null, p90: number | null): JSX.Element {
  if (v === null) return <span className="text-gray-400 dark:text-gray-500">—</span>
  return (
    <span>
      <span className="font-semibold">{fmtZahl(v, 1)}</span>
      {p10 != null && p90 != null && (p10 > 0 || p90 > 0) && (
        <span className="text-gray-400 dark:text-gray-500 text-xs ml-1">({fmtZahl(p10, 0)}–{fmtZahl(p90, 0)})</span>
      )}
      <span className="text-gray-500 ml-1">kWh</span>
    </span>
  )
}
function fmtVmNm(th: { vormittag_kwh: number; nachmittag_kwh: number } | null): string {
  if (!th) return '—'
  return `${fmtZahl(th.vormittag_kwh, 0)} / ${fmtZahl(th.nachmittag_kwh, 0)}`
}
function MaeMbeCard({ label, mae, mbe, color, hint }: { label: string; mae: number | null; mbe: number | null; color: string; hint?: string }) {
  const fmtMbe = (v: number) => `${v > 0 ? '+' : ''}${fmtZahl(v, 0)} %`
  return (
    <div className="text-center p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
      <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{label}</div>
      <div className="flex items-baseline justify-center gap-3">
        <SimpleTooltip text="MAPE = Mean Absolute Percentage Error: durchschnittliche Abweichung |Prognose − IST| / IST in % — Streuung">
          <div><span className="text-xs text-gray-500 mr-1">MAPE</span><span className={`text-lg font-bold ${color}`}>{mae !== null ? `${fmtZahl(mae, 0)} %` : '—'}</span></div>
        </SimpleTooltip>
        <SimpleTooltip text="MPE = Mean Percentage Error: durchschnittliche vorzeichenbehaftete Abweichung in % vom IST — positiv = systematisch zu hoch. |MPE| ≪ MAPE → Streuung; |MPE| ≈ MAPE → systematischer Bias.">
          <div><span className="text-xs text-gray-500 mr-1">Bias</span><span className={`text-lg font-bold ${mbe === null ? 'text-gray-400' : 'text-gray-700 dark:text-gray-200'}`}>{mbe !== null ? fmtMbe(mbe) : '—'}</span></div>
        </SimpleTooltip>
      </div>
      {hint && <div className="text-[10px] text-gray-400 dark:text-gray-500 mt-1">{hint}</div>}
    </div>
  )
}
function AsymmetrieCard({ label, asym, color, hint }: { label: string; asym: AsymmetrieEintrag | null; color: string; hint?: string }) {
  const fmtPct = (v: number | null) => v === null ? '—' : `${v > 0 ? '+' : ''}${fmtZahl(v, 0)} %`
  const overCount = asym?.over_count ?? 0
  const underCount = asym?.under_count ?? 0
  const tagWord = (n: number) => n === 1 ? 'Tag' : 'Tage'
  return (
    <div className="text-center p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
      <div className={`text-xs font-medium mb-2 ${color}`}>{label}</div>
      <div className="grid grid-cols-2 gap-2">
        <SimpleTooltip text="Tage an denen die Prognose über dem IST lag — durchschnittliche relative Überschätzung">
          <div className="px-2 py-1.5 rounded bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-700">
            <div className="text-[10px] text-gray-500 dark:text-gray-400">darüber</div>
            <div className="text-sm font-bold text-amber-600 dark:text-amber-400">{fmtPct(asym?.over_avg_prozent ?? null)}</div>
            <div className="text-[10px] text-gray-400 dark:text-gray-500">{overCount} {tagWord(overCount)}</div>
          </div>
        </SimpleTooltip>
        <SimpleTooltip text="Tage an denen die Prognose unter dem IST lag — durchschnittliche relative Unterschätzung">
          <div className="px-2 py-1.5 rounded bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-700">
            <div className="text-[10px] text-gray-500 dark:text-gray-400">darunter</div>
            <div className="text-sm font-bold text-sky-600 dark:text-sky-400">{fmtPct(asym?.under_avg_prozent ?? null)}</div>
            <div className="text-[10px] text-gray-400 dark:text-gray-500">{underCount} {tagWord(underCount)}</div>
          </div>
        </SimpleTooltip>
      </div>
      {hint && <div className="text-[10px] text-gray-400 dark:text-gray-500 mt-1">{hint}</div>}
    </div>
  )
}
// ── Abweichungs-Sprache (P-5 / N-50) ──────────────────────────────────────────
// Die Schwellen dieser Seite als benannte Konstanten — vorher standen sie zweimal
// als Literale nebeneinander und wichen im Rotton auseinander.
/** Ab hier gelb, ab {@link ABW_ROT_AB_PROZENT} rot. */
const ABW_GELB_AB_PROZENT = 10
const ABW_ROT_AB_PROZENT = 30
/** Unter dieser Referenz ist jede Prozentzahl erfunden — dann nur der absolute Wert. */
const ABW_REF_MIN_KWH = 0.05
/** Was betragsmäßig darunter liegt, rundet auf 0,0 und bekommt kein Richtungs-Symbol. */
const ABW_NULL_KWH = 0.05
/** Ohne gemessene Referenz gilt ein Δ darunter als Rauschen und wird unterdrückt. */
const ABW_RAUSCHEN_KWH = 0.03

/** Ampel-Stufe einer Abweichung — eine Schwellen-Basis für alle drei Tabellen. */
function abweichungsStufe(pct: number): keyof typeof STATUS_TEXT_CLASS {
  return pct < ABW_GELB_AB_PROZENT ? 'ok' : pct < ABW_ROT_AB_PROZENT ? 'warnung' : 'kritisch'
}

/**
 * Abweichungs-Annotation — die EINE Stelle, an der ein Δ gerendert wird, und
 * seit P-5 auch die EINE Sprache, in der es das tut.
 *
 * Vorher beantworteten drei Tabellen auf derselben Seite dieselbe Frage
 * verschieden: das Genauigkeits-Tracking rein **relativ** („+16 %"),
 * Stundenvergleich und 7-Tage-Vergleich rein **absolut** („▲ 9,7") — und zwar
 * über dieselben vier Tage, die beide Tabellen aus `genauigkeit.tage` ziehen
 * (`.slice(-7)` hier, `.slice(-4)` dort). Gemessen am 04.08. gegen die Anlage
 * stand der 03.08./OM oben als „+16 %" und zwei Blöcke tiefer als „▲ 9,7".
 * Entscheid Gernot: **absolut und Prozent in Klammern, überall** — die Form,
 * die die Σ-Zeile seit B4 ohnehin trug.
 *
 * `gemessen` ist **keine** zweite Sprache, sondern eine Aussage über die
 * Referenz: sie ist ein gemessenes IST. Dann steht die Annotation immer, auch
 * als „± 0,0" (Rainer PN 90004) — vorher unterdrückte sie sich bei |Δ| < 0,03
 * kWh und traf je Spalte unterschiedlich zu, was in der Tabelle wie eine Lücke
 * aussah. Ohne gemessenes IST — die 7-Tage-Zukunftszeilen vergleichen gegen das
 * Mittel der Prognosen — bleibt die Unterdrückung: dort ist ein „0,0" keine
 * Aussage über die Wirklichkeit.
 */
function Abweichung({ prognose, ist, gemessen = false }: { prognose: number; ist: number; gemessen?: boolean }) {
  const diff = prognose - ist
  if (!gemessen) {
    if (ist < ABW_REF_MIN_KWH && prognose < ABW_REF_MIN_KWH) return null
    if (Math.abs(diff) < ABW_RAUSCHEN_KWH) return null
  }
  const refTraegt = ist > ABW_REF_MIN_KWH
  const pct = refTraegt ? Math.abs(diff / ist) * 100 : (prognose > ABW_REF_MIN_KWH ? 100 : 0)
  // Was auf 0,0 rundet, bekommt kein Richtungs-Symbol — ein „▼ 0,0" behauptet
  // eine Unterschreitung, die die angezeigte Zahl gar nicht hergibt.
  const arrow = Math.abs(diff) < ABW_NULL_KWH ? '±' : diff > 0 ? '▲' : '▼'
  return (
    <span className={`text-[10px] ${STATUS_TEXT_CLASS[abweichungsStufe(pct)]}`}>
      {arrow} {fmtZahl(Math.abs(diff), 1)}{refTraegt && ` (${prozentText(pct)})`}
    </span>
  )
}

/** Ab hier sagt die Prozentzahl nichts mehr — die absolute kWh-Zahl daneben schon. */
const ABW_PROZENT_DECKEL = 999

/**
 * Relative Abweichung als Text — gekappt (N-128).
 *
 * Der Quotient ist nach oben unbegrenzt: bei IST 0,2 kWh und Prognose 5,0 stand
 * dort „(2400 %)". Vorbestehend, aber seit P-5 an mehr Stellen erreichbar (das
 * Tracking hatte mit `ist < 0.5` ein Gate, das mit der gemeinsamen
 * Abweichungs-Sprache entfiel). Es trifft Ausfall- und Tiefwinter-Tage sowie
 * Randstunden. Gekappt wird nur die **Anzeige**; die Ampel-Stufe rechnet
 * weiter mit dem echten Wert, und der absolute kWh-Wert steht unverändert
 * daneben — dort ist die Größenordnung ablesbar, ohne dass eine vierstellige
 * Prozentzahl die Zeile sprengt.
 */
function prozentText(pct: number): string {
  return pct > ABW_PROZENT_DECKEL ? `> ${ABW_PROZENT_DECKEL} %` : `${fmtZahl(pct, 0)} %`
}

/** Kopfzelle der Δ-Spalte — je Quelle eine, farblich an ihre Wert-Spalte gebunden. */
function AbweichungKopf({ quelle, klasse }: { quelle: string; klasse: string }) {
  return (
    <th className={`${KOPF_ZELLE} text-right ${klasse}`}>
      <SimpleTooltip text={`Abweichung ${quelle} gegen die Referenz: absolut in kWh, dahinter relativ`}>
        <span aria-label={`Abweichung ${quelle}`}>Δ</span>
      </SimpleTooltip>
    </th>
  )
}
interface StundenTooltipPayload { dataKey?: string; value?: number | null; stroke?: string; fill?: string }
function StundenTooltip({ active, payload, label, hasEedc }: { active?: boolean; payload?: StundenTooltipPayload[]; label?: string | number; hasEedc?: boolean }) {
  if (!active || !payload?.length) return null
  // Beschriftung aus dem Backward-SoT (`lib/stundenSlot.ts`) — dieselbe Quelle,
  // aus der auch Cockpit → Live seine Zeitspanne nimmt (#144/#297).
  const intervalLabel = slotZeitspanne(parseInt(String(label ?? '').replace(':00', '')))
  return (
    <div className="bg-gray-900 dark:bg-gray-950 text-white p-3 rounded-lg shadow-lg text-xs">
      <div className="font-medium mb-1">{intervalLabel}</div>
      {payload.map((p: StundenTooltipPayload) => {
        const key = p.dataKey ?? ''
        if (['solcast_p10', 'solcast_p90'].includes(key)) return null
        if (key === 'ist' && p.value === null) return null
        if (key === 'eedc' && !hasEedc) return null
        if (key === 'sfml' && p.value === null) return null
        const labels: Record<string, string> = { openmeteo: 'OpenMeteo (roh)', eedc: 'eedc (kalibriert)', solcast: 'Solcast', sfml: 'SFML (gewählte Quelle)', ist: 'IST' }
        return (
          <div key={key} className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: p.stroke || p.fill }} />
            <span className="text-gray-300">{labels[key] || key}:</span>
            <span className="font-mono font-medium">{fmtZahl(p.value ?? 0, 2)} kW</span>
          </div>
        )
      })}
    </div>
  )
}

// Präsenz-Prädikate — damit die v4-Sicht nur tatsächlich gerenderte Elemente in
// `Parkbar` hüllt (sonst phantom-leere Park-Boxen bei null-Rendern).
export const hatLernfaktorO12 = (vm: PrognoseVergleichVM) => vm.data?.eedc_lernfaktor_o12 != null
export const hatStratifizierung = (vm: PrognoseVergleichVM) => {
  const s = vm.stratifizierung
  return !!s && (s.stunden_klassifiziert > 0 || s.tage_ohne_wetter > 0 || s.tep_tage_ohne_wetter > 0)
}
export const hatTracking = (vm: PrognoseVergleichVM) => !!vm.genauigkeit && vm.genauigkeit.anzahl_tage > 0

// ════ BLOCK ④ — Genauigkeit ════════════════════════════════════════════════════
export function PvgKpiMatrix({ vm }: { vm: PrognoseVergleichVM }) {
  const { data } = vm
  if (!data) return null
  const hasSolcast = data.solcast_verfuegbar
  const hasEedc = data.eedc_lernfaktor !== null || data.eedc_heute_kwh !== null
  const lf = data.eedc_lernfaktor
  const progBasisLabel = 'OpenMeteo'
  // Mobil (< sm): je Tag eine Karte, Quellen als Zeilen — dieselbe Datenlage
  // transponiert. Die Tabelle ist quellen-spaltig, die Karte tag-weise; das ist
  // die Leserichtung, die auf einem schmalen Gerät trägt.
  const tagesKarten = [
    {
      titel: 'Heute',
      werte: [data.openmeteo_heute_kwh, data.eedc_heute_kwh, data.solcast_heute_kwh, data.ist_heute_kwh] as (number | null)[],
      haelften: 0,
      verbleibend: [data.verbleibend_om_kwh, data.verbleibend_eedc_kwh, data.verbleibend_solcast_kwh, data.verbleibend_kwh] as (number | null)[],
    },
    {
      titel: 'Morgen',
      werte: [data.openmeteo_morgen_kwh, data.eedc_morgen_kwh, data.solcast_morgen_kwh, null] as (number | null)[],
      haelften: 1,
      verbleibend: null,
    },
    {
      titel: 'Übermorgen',
      werte: [data.openmeteo_uebermorgen_kwh, data.eedc_uebermorgen_kwh, data.solcast_uebermorgen_kwh, null] as (number | null)[],
      haelften: 2,
      verbleibend: null,
    },
  ]
  const quellenSpalten: { label: string; klasse: string; haelften: (Tageshaelfte | null)[] | null | undefined }[] = [
    { label: 'OpenMeteo', klasse: Q.openmeteo, haelften: data.openmeteo_tageshaelften },
    { label: 'eedc', klasse: eedcKlasse(hasEedc), haelften: data.eedc_tageshaelften },
    { label: 'Solcast', klasse: Q.solcast, haelften: data.solcast_tageshaelften },
    { label: 'IST', klasse: Q.ist, haelften: null },
  ]
  return (
    <Card>
      <MobilKarten>
        {tagesKarten.map((tk) => (
          <MobilKarte
            key={tk.titel}
            titel={tk.titel}
            zeilen={quellenSpalten.flatMap((sp, idx) => {
              if (sp.label === 'Solcast' && !hasSolcast) return []
              if (sp.label === 'eedc' && !hasEedc) {
                return [{ label: 'eedc', klasse: sp.klasse, wert: '—' }]
              }
              const wert = tk.werte[idx]
              const th = sp.haelften?.[tk.haelften] ?? null
              const zusatzTeile: string[] = []
              if (th) zusatzTeile.push(`VM/NM ${fmtVmNm(th)}`)
              if (tk.verbleibend && tk.verbleibend[idx] != null) {
                zusatzTeile.push(`verbleibend ${fmtKwh(tk.verbleibend[idx])}`)
              }
              return [{
                label: sp.label,
                klasse: sp.klasse,
                wert: sp.label === 'IST' && tk.titel !== 'Heute' ? '—' : fmtKwh(wert),
                zusatz: zusatzTeile.length > 0
                  ? <span className="text-[10px] text-gray-400 dark:text-gray-500">{zusatzTeile.join(' · ')}</span>
                  : null,
              }]
            })}
          />
        ))}
      </MobilKarten>
      <TabelleAbSm>
        <Table className="table-fixed">
          <colgroup><col className="w-32" /><col /><col />{hasSolcast && <col />}<col /></colgroup>
          <TableHead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className={`${KOPF_ZELLE} text-left text-gray-500 dark:text-gray-400`}></th>
              <th className={`${KOPF_ZELLE} text-right ${Q.openmeteo}`}>
                <SimpleTooltip text="Open-Meteo: GTI-basierte Prognose aus Wettermodell (ICON/ECMWF), 14 Tage Horizont"><span>OpenMeteo</span></SimpleTooltip>
              </th>
              <th className={`${KOPF_ZELLE} text-right ${eedcKlasse(hasEedc)}`}>
                <SimpleTooltip text={hasEedc && lf != null ? `eedc: ${progBasisLabel} × Lernfaktor ${fmtZahl(lf, 3)} (MOS-kalibriert${data.eedc_lernfaktor_stufe ? ', ' + data.eedc_lernfaktor_stufe : ''})` : `eedc: Lernfaktor noch nicht verfügbar — siehe Hinweis unten`}>
                  <span>eedc {hasEedc && lf != null && <span className="text-xs font-normal">×{fmtZahl(lf, 2)}</span>}</span>
                </SimpleTooltip>
              </th>
              {hasSolcast && (
                <th className={`${KOPF_ZELLE} text-right ${Q.solcast}`}>
                  <SimpleTooltip text={`Solcast: Satellitenbasierte PV-Prognose mit Konfidenzband, 7 Tage (${data.solcast_quelle === 'solcast_api' ? 'API' : 'HA-Sensor'})`}><span>Solcast</span></SimpleTooltip>
                </th>
              )}
              <th className={`${KOPF_ZELLE} text-right ${Q.ist}`}>
                <SimpleTooltip text="IST: Tatsächliche PV-Erzeugung aus Sensor-Daten (TagesEnergieProfil)"><span>IST</span></SimpleTooltip>
              </th>
            </tr>
          </TableHead>
          <TableBody>
            <tr className="border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/20">
              <td className={`${ZELLE} font-medium text-gray-900 dark:text-white`}>Heute</td>
              <td className={`${ZELLE} text-right font-mono`}>{fmtKwh(data.openmeteo_heute_kwh)}</td>
              <td className={`${ZELLE} text-right font-mono ${hasEedc ? `font-semibold ${Q.eedc}` : 'text-gray-400 dark:text-gray-500'}`}>{hasEedc ? fmtKwh(data.eedc_heute_kwh) : '—'}</td>
              {hasSolcast && <td className={`${ZELLE} text-right font-mono`}>{fmtKwhBand(data.solcast_heute_kwh, data.solcast_p10_kwh, data.solcast_p90_kwh)}</td>}
              <td className={`${ZELLE} text-right font-mono font-semibold text-green-600 dark:text-green-400`}>
                {fmtKwh(data.ist_heute_kwh)}
                {data.ist_unvollstaendig && (
                  <IstUnvollstaendigPopover fehlendeStunden={data.ist_stundenprofil.filter(s => s.kw === null && s.stunde < new Date().getHours()).map(s => s.stunde)} anlageId={vm.anlageId} onReloaded={vm.reload} />
                )}
              </td>
            </tr>
            <tr className="border-b border-gray-100 dark:border-gray-800">
              <td className={`${ZELLE} text-gray-500 dark:text-gray-400`}>
                <SimpleTooltip text="Tagesprojektion: IST bisher + Prognose für die restlichen Stunden. Pro Spalte mit der jeweiligen Quelle; Gesamtspalte mit der in den Einstellungen gewählten Prognosequelle."><span>↳ Verbleibend</span></SimpleTooltip>
              </td>
              <td className={`${ZELLE} text-right font-mono text-gray-500`}>{fmtKwh(data.verbleibend_om_kwh)}</td>
              <td className={`${ZELLE} text-right font-mono text-gray-500`}>{hasEedc ? fmtKwh(data.verbleibend_eedc_kwh) : <span className="text-gray-400 dark:text-gray-500">—</span>}</td>
              {hasSolcast && <td className={`${ZELLE} text-right font-mono text-gray-500`}>{fmtKwh(data.verbleibend_solcast_kwh)}</td>}
              <td className={`${ZELLE} text-right font-mono text-emerald-500`}>{fmtKwh(data.verbleibend_kwh)}</td>
            </tr>
            <tr className="border-b border-gray-100 dark:border-gray-800">
              <td className={`${ZELLE} text-gray-400 dark:text-gray-500`}>↳ VM / NM</td>
              <td className={`${ZELLE} text-right font-mono text-gray-500`}>{fmtVmNm(data.openmeteo_tageshaelften?.[0])}</td>
              <td className={`${ZELLE} text-right font-mono text-gray-500`}>{hasEedc ? fmtVmNm(data.eedc_tageshaelften?.[0]) : <span className="text-gray-400 dark:text-gray-500">—</span>}</td>
              {hasSolcast && <td className={`${ZELLE} text-right font-mono text-gray-500`}>{fmtVmNm(data.solcast_tageshaelften?.[0])}</td>}
              <td className={`${ZELLE} text-right font-mono text-green-500`}>{fmtVmNm(data.ist_tageshaelfte)}</td>
            </tr>
            <tr className="border-b border-gray-100 dark:border-gray-800">
              <td className={`${ZELLE} font-medium text-gray-900 dark:text-white`}>Morgen</td>
              <td className={`${ZELLE} text-right font-mono`}>{fmtKwh(data.openmeteo_morgen_kwh)}</td>
              <td className={`${ZELLE} text-right font-mono ${eedcKlasse(hasEedc)}`}>{hasEedc ? fmtKwh(data.eedc_morgen_kwh) : '—'}</td>
              {hasSolcast && <td className={`${ZELLE} text-right font-mono`}>{fmtKwhBand(data.solcast_morgen_kwh, data.solcast_morgen_p10_kwh, data.solcast_morgen_p90_kwh)}</td>}
              <td className={`${ZELLE} text-right text-gray-400 dark:text-gray-500`}>—</td>
            </tr>
            <tr className="border-b border-gray-100 dark:border-gray-800">
              <td className={`${ZELLE} text-gray-400 dark:text-gray-500`}>↳ VM / NM</td>
              <td className={`${ZELLE} text-right font-mono text-gray-500`}>{fmtVmNm(data.openmeteo_tageshaelften?.[1])}</td>
              <td className={`${ZELLE} text-right font-mono text-gray-500`}>{hasEedc ? fmtVmNm(data.eedc_tageshaelften?.[1]) : <span className="text-gray-400 dark:text-gray-500">—</span>}</td>
              {hasSolcast && <td className={`${ZELLE} text-right font-mono text-gray-500`}>{fmtVmNm(data.solcast_tageshaelften?.[1])}</td>}
              <td className={ZELLE}></td>
            </tr>
            <tr className="border-b border-gray-100 dark:border-gray-800">
              <td className={`${ZELLE} font-medium text-gray-900 dark:text-white`}>Übermorgen</td>
              <td className={`${ZELLE} text-right font-mono`}>{fmtKwh(data.openmeteo_uebermorgen_kwh)}</td>
              <td className={`${ZELLE} text-right font-mono ${eedcKlasse(hasEedc)}`}>{hasEedc ? fmtKwh(data.eedc_uebermorgen_kwh) : '—'}</td>
              {hasSolcast && <td className={`${ZELLE} text-right font-mono`}>{fmtKwh(data.solcast_uebermorgen_kwh)}</td>}
              <td className={`${ZELLE} text-right text-gray-400 dark:text-gray-500`}>—</td>
            </tr>
            <tr>
              <td className={`${ZELLE} text-gray-400 dark:text-gray-500`}>↳ VM / NM</td>
              <td className={`${ZELLE} text-right font-mono text-gray-500`}>{fmtVmNm(data.openmeteo_tageshaelften?.[2])}</td>
              <td className={`${ZELLE} text-right font-mono text-gray-500`}>{hasEedc ? fmtVmNm(data.eedc_tageshaelften?.[2]) : <span className="text-gray-400 dark:text-gray-500">—</span>}</td>
              {hasSolcast && <td className={`${ZELLE} text-right font-mono text-gray-500`}>{fmtVmNm(data.solcast_tageshaelften?.[2])}</td>}
              <td className={ZELLE}></td>
            </tr>
          </TableBody>
        </Table>
      </TabelleAbSm>
    </Card>
  )
}

export function PvgStatusHinweise({ vm, parkbar }: {
  vm: PrognoseVergleichVM
  /** v4: parkbar umhüllen (Chip-id/-titel). IST-Sicht ruft ohne Prop → DOM-gleich. */
  parkbar?: { id: string; titel: string }
}) {
  const { data, genauigkeit } = vm
  if (!data) return null
  const hasEedc = data.eedc_lernfaktor !== null || data.eedc_heute_kwh !== null
  const zeigeSolcast = !!(data.solcast_status && data.solcast_status !== 'ok' && data.solcast_hinweis)
  // D17-15/R17-5: kein Inhalt → nichts rendern (kein leerer parkbarer Rahmen).
  if (!zeigeSolcast && hasEedc) return null
  const inhalt = (
    <>
      {zeigeSolcast && (
        <div className={`rounded-lg p-4 text-sm ${data.solcast_status === 'tageslimit' ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-200' : 'bg-blue-50 dark:bg-blue-900/20 text-blue-800 dark:text-blue-200'}`}>{data.solcast_hinweis}</div>
      )}
      {!hasEedc && (() => {
        const usableDays = (genauigkeit?.tage ?? []).filter(t => t.openmeteo_kwh != null && t.openmeteo_kwh > 0 && t.ist_kwh != null && t.ist_kwh > 0.5).length
        const fehlend = Math.max(0, 7 - usableDays)
        return (
          <div className="rounded-lg p-4 text-sm bg-blue-50 dark:bg-blue-900/20 text-blue-800 dark:text-blue-200">
            eedc-Prognose nicht verfügbar — benötigt mindestens 7 Tage mit IST-Ertragsdaten, um den Lernfaktor (Verhältnis IST/Prognose) zu berechnen
            {' '}(<strong>{usableDays} von 7 Tagen</strong>{fehlend > 0 ? `, noch ${fehlend} Tag${fehlend === 1 ? '' : 'e'}` : ''}).
            Der Lernfaktor kalibriert die OpenMeteo-Prognose anlagenspezifisch und gleicht systematische Abweichungen (Verschattung, Ausrichtung, Alterung) aus.
          </div>
        )
      })()}
    </>
  )
  return parkbar ? <Parkbar id={parkbar.id} titel={parkbar.titel}>{inhalt}</Parkbar> : inhalt
}

export function PvgLernfaktorO12({ vm }: { vm: PrognoseVergleichVM }) {
  const { data } = vm
  if (!data || data.eedc_lernfaktor_o12 == null) return null
  return (
    <Card>
      <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
        <BarChart3 className="h-4 w-4 text-orange-500" />Lernfaktor — Doppel-Variante O1+O2
      </h3>
      <div className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        Trim-Mean (entfernt Ausreißer-Tage durch Sensor-Aussetzer) + Recency-Boost (gewichtet die letzten 30 Tage stärker). Läuft parallel zum Live-Faktor — eine Aktivierung als Default erfolgt erst nach mehrwöchiger Beobachtung.
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div><div className="text-xs text-gray-500 dark:text-gray-400">Live (Legacy)</div><div className="font-mono text-base font-semibold">{data.eedc_lernfaktor != null ? fmtZahl(data.eedc_lernfaktor, 3) : '—'}</div></div>
        <div><div className="text-xs text-gray-500 dark:text-gray-400">O1+O2</div><div className="font-mono text-base font-semibold">{fmtZahl(data.eedc_lernfaktor_o12, 3)}</div></div>
      </div>
      {data.eedc_lernfaktor_o12_delta_pct != null && (
        <div className="mt-2 text-xs">Δ{' '}
          <span className={Math.abs(data.eedc_lernfaktor_o12_delta_pct) < 0.5 ? 'text-gray-500' : data.eedc_lernfaktor_o12_delta_pct > 0 ? 'text-green-600' : 'text-red-600'}>
            {data.eedc_lernfaktor_o12_delta_pct >= 0 ? '+' : ''}{fmtZahl(data.eedc_lernfaktor_o12_delta_pct, 2)} %
          </span>{' '}<span className="text-gray-400 dark:text-gray-500">(O12 vs Legacy)</span>
        </div>
      )}
    </Card>
  )
}

export function PvgStratifizierung({ vm }: { vm: PrognoseVergleichVM }) {
  const { stratifizierung } = vm
  if (!stratifizierung) return null
  if (stratifizierung.stunden_klassifiziert > 0) {
    return (
      <Card>
        <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2"><Cloud className="h-4 w-4 text-gray-500" />Wetter-Stratifizierung</h3>
        <div className="text-xs text-gray-500 dark:text-gray-400 mb-3">
          Stündliche Day-Ahead-Genauigkeit pro Wetter-Klasse, letzte {stratifizierung.tage_zeitraum} Tage, {stratifizierung.stunden_klassifiziert} Tageslicht-Stunden. MAPE = Streuung, MPE = systematischer Bias (positiv = IST &gt; Prognose).
        </div>
        {/* tabelle-allow: Kennzahlen-Mini-Tabelle (max. 3 Zeilen klar/diffus/wechselhaft),
            kein Datensatz-Raster. Höhenfenster/sticky-Kopf greifen nie, eigene text-xs-Dichte
            bewusst — Regel-T-Sonderfall (Gernot 2026-07-10, KONZEPT-TABELLEN-SOT §6b.8). */}
        <table className="w-full text-xs">
          <thead><tr className="border-b border-gray-200 dark:border-gray-700">
            <th className="text-left py-1 pr-2 font-medium text-gray-500">Klasse</th>
            <th className="text-right py-1 px-2 font-medium text-gray-500">n</th>
            <th className="text-right py-1 px-2 font-medium text-gray-500">MAPE %</th>
            <th className="text-right py-1 pl-2 font-medium text-gray-500">MPE %</th>
          </tr></thead>
          <tbody>
            {(['klar', 'diffus', 'wechselhaft'] as Wetterklasse[]).map(k => {
              const e = stratifizierung.pro_klasse[k]
              if (!e || e.stunden_count === 0) return null
              return (
                <tr key={k} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-1 pr-2 capitalize">{k}</td>
                  <td className="py-1 px-2 text-right font-mono">{e.stunden_count}</td>
                  <td className="py-1 px-2 text-right font-mono">{e.mae_pct != null ? fmtZahl(e.mae_pct, 1) : '—'}</td>
                  <td className="py-1 pl-2 text-right font-mono">{e.mbe_pct != null ? fmtZahl(e.mbe_pct, 1) : '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {vm.backfillResult && <div className="mt-3 text-xs text-green-700 dark:text-green-400">✓ Wetter-Historie nachgeladen: {vm.backfillResult}</div>}
      </Card>
    )
  }
  if (stratifizierung.tage_ohne_wetter > 0 || stratifizierung.tep_tage_ohne_wetter > 0) {
    return (
      <Card>
        <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2"><Cloud className="h-4 w-4 text-gray-500" />Wetter-Stratifizierung</h3>
        <div className="text-xs text-gray-500 dark:text-gray-400 mb-3">
          Wetter-Historie (Bewölkung, Niederschlag, WMO-Code) für {Math.max(stratifizierung.tage_ohne_wetter, stratifizierung.tep_tage_ohne_wetter)} Tage noch nicht geladen. eedc kann sie kostenlos aus dem Open-Meteo-Archiv nachholen. {stratifizierung.tage_mit_prognose > 0 ? (<>Danach zeigt diese Card MAPE/MPE getrennt nach <em>klar</em>, <em>diffus</em> und <em>wechselhaft</em>.</>) : (<>Solange noch keine Day-Ahead-Stundenprofile gespeichert sind, bleibt die Stratifizierungs-Tabelle leer — die Wetter-Daten dienen dann der Vorbereitung für das stündliche Korrekturprofil (Päckchen 2).</>)}
        </div>
        {/* B15: Aktions-Button → Button-SoT (primary; das frühere bg-blue-600 war
            eine lokale Improvisation neben dem primary-Kanon). */}
        <Button type="button" variant="primary" size="sm" onClick={vm.handleWetterBackfill} loading={vm.backfillRunning}>
          {vm.backfillRunning ? 'Lädt Wetter-Historie…' : 'Wetter-Historie nachladen (2 Jahre)'}
        </Button>
        {/* D11-9(a)/R12 (Gernot): Status-Zeile IMMER rendern — vorher (kein Ergebnis)
            ein neutraler Zustands-Hinweis, nach dem Klick Ergebnis/Fehler im selben Slot.
            So entsteht beim Erst-Klick kein „Zucken" (0→1 Zeile) mehr. */}
        <div className="mt-3 text-xs">
          {vm.backfillError
            ? <span className="text-red-600 dark:text-red-400">Fehler: {vm.backfillError}</span>
            : vm.backfillResult
              ? <span className="text-green-700 dark:text-green-400">✓ {vm.backfillResult}</span>
              : <span className="text-gray-500 dark:text-gray-400">Nachladen empfohlen — die fehlenden Tage werden kostenlos aus dem Open-Meteo-Archiv geholt.</span>}
        </div>
      </Card>
    )
  }
  return null
}

export function PvgHeatmap({ vm }: { vm: PrognoseVergleichVM }) {
  return <KorrekturprofilHeatmapCard anlageId={vm.anlageId} />
}

export function PvgGenauigkeitsTracking({ vm }: { vm: PrognoseVergleichVM }) {
  const { genauigkeit } = vm
  if (!genauigkeit || genauigkeit.anzahl_tage === 0) return null
  const lf = vm.data?.eedc_lernfaktor ?? null
  return (
    <Card>
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        {/* D19-1 (detlan): Kopf zeigt das GEWÄHLTE Fenster; weicht die Datenlage ab,
            steht das ehrlich daneben (vorher: Kopf = Backend-anzahl_tage → „7 T"
            gewählt, aber „(letzte 1 Tage)" — drei widersprüchliche Zeitangaben). */}
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Genauigkeits-Tracking <span className="text-sm font-normal text-gray-500 ml-2">(letzte {vm.genauigkeitsTage} Tage{genauigkeit.anzahl_tage < vm.genauigkeitsTage ? ` · ${genauigkeit.anzahl_tage} ${genauigkeit.anzahl_tage === 1 ? 'Tag' : 'Tage'} mit Daten` : ''})</span></h3>
        {/* D14-19 (detLAN #107 v7): Controls umbruchfähig + Gruppen shrink-0 — vorher
            klemmte das `overflow-hidden` der Toggle-Gruppe „Diagnostisch" auf
            „Diagnost" und die Ausreißer-Checkbox lief mobil rechts aus dem Bild. */}
        <div className="flex flex-wrap items-center gap-3">
          {/* B15/S4: 1-aus-N-Umschalter → SegmentControl-SoT (löst zwei handgebaute
              Pillen-Gruppen ab); Ausreißer-Filter → Checkbox-SoT. */}
          <SegmentControl
            ariaLabel="Zeitraum (Tage)" size="sm"
            optionen={([7, 10, 30] as const).map((t) => ({ key: String(t), label: `${t} T` }))}
            value={String(vm.genauigkeitsTage)}
            onChange={(k) => vm.setGenauigkeitsTage(Number(k) as 7 | 10 | 30)}
          />
          <SegmentControl
            ariaLabel="Darstellung" size="sm"
            optionen={[{ key: 'kompakt', label: 'Kompakt' }, { key: 'diagnostisch', label: 'Diagnostisch' }]}
            value={vm.genauigkeitsModus}
            onChange={(k) => vm.setGenauigkeitsModus(k as 'kompakt' | 'diagnostisch')}
          />
          <SimpleTooltip text={`Ausreißer = Tage, an denen eine Quelle > ${fmtZahl(genauigkeit.ausreisser_schwelle_prozent ?? 50, 0)} % daneben lag (z. B. Sensor-Aussetzer). Standardmäßig bleiben sie in der Statistik — gerade Schlechtprognose-Tage haben Erkenntniswert. Hier optional ausblenden.`}>
            <span className={`inline-block select-none ${(genauigkeit.anzahl_ausreisser ?? 0) === 0 ? 'opacity-50' : ''}`}>
              <Checkbox
                checked={vm.ausreisserAusblenden}
                onChange={(e) => vm.setAusreisserAusblenden(e.target.checked)}
                label={<span className="text-xs text-gray-600 dark:text-gray-400">Ausreißer ausblenden{(genauigkeit.anzahl_ausreisser ?? 0) > 0 ? ` (${genauigkeit.anzahl_ausreisser})` : ''}</span>}
              />
            </span>
          </SimpleTooltip>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
        {vm.genauigkeitsModus === 'kompakt' ? (
          <>
            <MaeMbeCard label="OpenMeteo" mae={genauigkeit.openmeteo_mae_prozent} mbe={genauigkeit.openmeteo_mbe_prozent} color={Q.openmeteo} />
            <MaeMbeCard label="eedc" mae={genauigkeit.eedc_mae_prozent} mbe={genauigkeit.eedc_mbe_prozent} color={Q.eedc} hint={lf == null ? 'Lernfaktor noch nicht verfügbar' : undefined} />
            <MaeMbeCard label="Solcast" mae={genauigkeit.solcast_mae_prozent} mbe={genauigkeit.solcast_mbe_prozent} color={Q.solcast} />
          </>
        ) : (
          <>
            <AsymmetrieCard label="OpenMeteo" asym={genauigkeit.openmeteo_asymmetrie} color={Q.openmeteo} />
            <AsymmetrieCard label="eedc" asym={genauigkeit.eedc_asymmetrie} color={Q.eedc} hint={lf == null ? 'Lernfaktor noch nicht verfügbar' : undefined} />
            <AsymmetrieCard label="Solcast" asym={genauigkeit.solcast_asymmetrie} color={Q.solcast} />
          </>
        )}
      </div>
      <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
        MAPE/Bias oben über {genauigkeit.anzahl_tage} {genauigkeit.anzahl_tage === 1 ? 'Tag' : 'Tage'} mit Daten{vm.ausreisserAusblenden && (genauigkeit.anzahl_ausreisser ?? 0) > 0 ? ` (ohne ${genauigkeit.anzahl_ausreisser} Ausreißer)` : ''} · Tabelle unten: {Math.min(7, genauigkeit.tage.length) === 1 ? 'letzter Tag' : `letzte ${Math.min(7, genauigkeit.tage.length)} Tage`}
      </div>
      <MobilKarten>
        {genauigkeit.tage.slice(-7).reverse().map((tag) => {
          const ausgeschlossen = vm.ausreisserAusblenden && tag.ist_ausreisser
          const quellen: { label: string; klasse: string; wert: number | null }[] = [
            { label: 'OpenMeteo', klasse: Q.openmeteo, wert: tag.openmeteo_kwh },
            { label: 'eedc', klasse: lf != null ? Q.eedc : 'text-gray-400 dark:text-gray-500', wert: tag.eedc_kwh },
            { label: 'Solcast', klasse: Q.solcast, wert: tag.solcast_kwh },
          ]
          return (
            <MobilKarte
              key={tag.datum}
              rahmenKlasse={`${tag.ist_ausreisser ? 'border-l-2 border-l-amber-400 dark:border-l-amber-500' : ''} ${ausgeschlossen ? 'opacity-40' : ''}`}
              titel={
                <>
                  {formatDatum(tag.datum)}
                  {tag.ist_ausreisser && <span className="ml-1 text-amber-500 text-[10px]">⚠</span>}
                </>
              }
              kopfWert={
                <span className={`font-mono font-semibold tabular-nums ${Q.ist}`}>
                  IST {tag.ist_kwh !== null ? fmtZahl(tag.ist_kwh, 1) : '—'}
                </span>
              }
              zeilen={quellen.map((q) => ({
                label: q.label,
                klasse: q.klasse,
                wert: q.wert !== null ? fmtZahl(q.wert, 1) : '—',
                zusatz: q.wert !== null && tag.ist_kwh !== null
                  ? <Abweichung prognose={q.wert} ist={tag.ist_kwh} gemessen />
                  : null,
              }))}
            />
          )
        })}
      </MobilKarten>
      <TabelleAbSm>
        <Table className="table-fixed">
          <colgroup>
            <col className="w-28" /><col /><col className="w-24" /><col /><col className="w-24" />
            <col /><col className="w-24" /><col className="w-16" />
          </colgroup>
          <TableHead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className={`${KOPF_ZELLE} text-left text-gray-500`}>Datum</th>
              <th className={`${KOPF_ZELLE} text-right ${Q.openmeteo}`}>OpenMeteo</th>
              <AbweichungKopf quelle="OpenMeteo" klasse={Q.openmeteo} />
              <th className={`${KOPF_ZELLE} text-right ${lf != null ? Q.eedc : 'text-gray-400 dark:text-gray-500'}`}>
                <SimpleTooltip text={lf == null ? 'Lernfaktor noch nicht verfügbar — siehe Hinweis oben' : `eedc = OpenMeteo × Lernfaktor ${fmtZahl(lf, 3)}`}><span>eedc</span></SimpleTooltip>
              </th>
              <AbweichungKopf quelle="eedc" klasse={lf != null ? Q.eedc : 'text-gray-400 dark:text-gray-500'} />
              <th className={`${KOPF_ZELLE} text-right ${Q.solcast}`}>Solcast</th>
              <AbweichungKopf quelle="Solcast" klasse={Q.solcast} />
              <th className={`${KOPF_ZELLE} text-right ${Q.ist}`}>IST</th>
            </tr>
          </TableHead>
          <TableBody>
            {genauigkeit.tage.slice(-7).reverse().map((tag) => {
              const ausgeschlossen = vm.ausreisserAusblenden && tag.ist_ausreisser
              return (
                <tr key={tag.datum} className={`border-b border-gray-100 dark:border-gray-800 ${tag.ist_ausreisser ? 'border-l-2 border-l-amber-400 dark:border-l-amber-500' : ''} ${ausgeschlossen ? 'opacity-40' : ''}`}>
                  <td className={`${ZELLE} text-gray-900 dark:text-white`}>
                    {formatDatum(tag.datum)}
                    {tag.ist_ausreisser && (<SimpleTooltip text={ausgeschlossen ? 'Ausreißer — aus MAE/MBE ausgeschlossen' : 'Ausreißer — große Abweichung, bleibt in der Statistik'}><span className="ml-1 text-amber-500 text-[10px]">⚠</span></SimpleTooltip>)}
                  </td>
                  <PvgPrognoseZelle wert={tag.openmeteo_kwh} ist={tag.ist_kwh} stellen={1} />
                  <PvgPrognoseZelle wert={tag.eedc_kwh} ist={tag.ist_kwh} stellen={1} leerGedimmt />
                  <PvgPrognoseZelle wert={tag.solcast_kwh} ist={tag.ist_kwh} stellen={1} leerGedimmt />
                  <td className={`${ZELLE} text-right font-mono font-semibold text-green-600 dark:text-green-400`}>{tag.ist_kwh !== null ? fmtZahl(tag.ist_kwh, 1) : '—'}</td>
                </tr>
              )
            })}
          </TableBody>
        </Table>
      </TabelleAbSm>
    </Card>
  )
}

// ════ BLOCK ⑤ — Profil ═════════════════════════════════════════════════════════
export function PvgStundenprofil({ vm }: { vm: PrognoseVergleichVM }) {
  const achsen = useChartTheme()
  const legende = useLegendenToggle()
  const { data } = vm
  if (!data) return null
  const hasSolcast = data.solcast_verfuegbar
  const hasEedc = data.eedc_lernfaktor !== null || data.eedc_heute_kwh !== null
  const hasSfml = data.sfml_verfuegbar === true
  const visibleChartData = sichtbareStunden(chartDatenVon(data))
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Tagesverlauf — Stundenprofil</h3>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={visibleChartData} margin={{ top: ACHSEN_MARGIN_TOP, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} opacity={0.3} />
            <XAxis dataKey="stunde" {...xAchse()} tickFormatter={(v) => v.replace(':00', '')} padding={{ left: 8, right: 8 }} /* achsen-allow: Zeit-/Kategorie-Achse */ />
            <YAxis {...yAchse(false)} tickFormatter={achsenTick} label={achsenEinheit('kW')} />
            <Tooltip content={<StundenTooltip hasEedc={hasEedc} />} />
            {/* Roh- und Korrektur-Kurve müssen in der Legende unterscheidbar
                sein (Backlog-Beifang R21-1). „×Faktor" stand hier noch aus der
                Zeit des reinen Skalars; korrigiert wird längst pro Stunden-Slot
                (Korrekturprofil-Kaskade) — der Skalar ist nur noch Fallback. */}
            <Legend content={<ChartLegende onItemClick={legende.onItemClick} formatter={(v) => ({ ist: 'IST', eedc: 'eedc (kalibriert)', solcast: 'Solcast', openmeteo: 'OpenMeteo (roh)', sfml: 'SFML (gewählte Quelle)' }[v] || v)} />} />
            {data.aktuelle_stunde !== null && (<ReferenceLine x={`${data.aktuelle_stunde}:00`} stroke={achsen.referenz} strokeDasharray="3 3" label={{ value: 'Jetzt', position: 'top', fontSize: 10, fill: achsen.achse }} />)}
            <Area dataKey="ist" stroke={PROGNOSE_QUELLEN_COLORS.ist} fill={PROGNOSE_QUELLEN_COLORS.ist} fillOpacity={0.3} strokeWidth={2} dot={false} name="ist" connectNulls={false} hide={legende.istVersteckt('ist')} />
            {hasSfml && <Line dataKey="sfml" stroke={PROGNOSE_QUELLEN_COLORS.sfml} strokeWidth={2} strokeDasharray={PROGNOSE_DASH} dot={false} name="sfml" connectNulls={false} hide={legende.istVersteckt('sfml')} />}
            {hasSolcast && <Line dataKey="solcast" stroke={PROGNOSE_QUELLEN_COLORS.solcast} strokeWidth={2} strokeDasharray={PROGNOSE_DASH} dot={false} name="solcast" hide={legende.istVersteckt('solcast')} />}
            {hasEedc && <Line dataKey="eedc" stroke={PROGNOSE_QUELLEN_COLORS.eedc} strokeWidth={2} strokeDasharray={PROGNOSE_DASH} dot={false} name="eedc" hide={legende.istVersteckt('eedc')} />}
            <Line dataKey="openmeteo" stroke={PROGNOSE_QUELLEN_COLORS.openmeteo} strokeWidth={1.5} strokeDasharray={PROGNOSE_DASH} dot={false} name="openmeteo" hide={legende.istVersteckt('openmeteo')} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

/**
 * Eine Prognose-Spalte: **zwei** Zellen — der Wert, daneben seine Einwertung
 * (Entscheid Gernot, 04.08.). Vorher standen beide in einer Zelle; sobald die
 * Prozentangabe dazukam (P-5), wanderte die rechtsbündige Zahl mit der Länge des
 * Δ und die Werte fluchteten nicht mehr untereinander. Getrennt bleibt die
 * Wert-Achse ruhig und die Einwertung wird selbst zu einer Leseachse.
 *
 * Die Delta-Bedingung stand davor dreimal nebeneinander in der Zeile, je Spalte
 * leicht anders (PN 90004); seit P-5 rendert auch das Genauigkeits-Tracking
 * hierüber, das bis dahin eine eigene Zelle mit eigener Sprache hatte.
 *
 * `leerGedimmt` = ein fehlender Wert heißt hier „diese Quelle gibt es nicht"
 * (kein Lernfaktor, kein Solcast) und nicht „Messlücke".
 */
function PvgPrognoseZelle({ wert, ist, klasse = '', stellen = 2, leerGedimmt = false, gemessen = true, wertKlasse = '', extra }: {
  wert: number | null; ist: number | null; klasse?: string; stellen?: number
  leerGedimmt?: boolean; gemessen?: boolean; wertKlasse?: string; extra?: React.ReactNode
}) {
  return (
    <>
      <td className={`${ZELLE} text-right font-mono ${klasse}`}>
        {wert === null
          ? (leerGedimmt ? <span className="text-gray-400 dark:text-gray-500">—</span> : '—')
          : <span className={wertKlasse}>{fmtZahl(wert, stellen)}</span>}
        {wert !== null && extra}
      </td>
      <td className={`${ZELLE} text-right font-mono ${klasse}`}>
        {wert !== null && ist !== null && <Abweichung prognose={wert} ist={ist} gemessen={gemessen} />}
      </td>
    </>
  )
}

/**
 * Eine Prognose-Zelle **ohne** Einwertung — der Weg, auf dem SFML in den
 * Vergleich kommt.
 *
 * Warum ohne Δ: eedc hat Tom-HA zugesagt, SFML in **keine** Genauigkeits-
 * Gegenüberstellung gegen eedc/Solcast zu stellen. Die Zusage steht seit jeher
 * im Backend, an genau der Stelle, die die SFML-Werte liefert
 * (`api/routes/prognosen.py`: „Einzelquellen-Treue (#110 A) … KEIN
 * Cross-Quellen-Genauigkeits-Ranking").
 *
 * Den **Wert treu anzuzeigen** ist davon ausdrücklich nicht betroffen — und er
 * fehlte bisher ausgerechnet denen, die SFML als Quelle gewählt haben: das
 * Backend liefert `sfml_*` seit jeher mit, der Vergleich las es nie. Sie sahen
 * drei Zahlen, aber nicht die, mit der eedc bei ihnen rechnet.
 */
function PvgWertZelle({ wert, klasse = '', stellen = 2 }: { wert: number | null; klasse?: string; stellen?: number }) {
  return (
    <td className={`${ZELLE} text-right font-mono ${klasse}`}>
      {wert === null ? <span className="text-gray-400 dark:text-gray-500">—</span> : fmtZahl(wert, stellen)}
    </td>
  )
}

export function Pvg24hTabelle({ vm }: { vm: PrognoseVergleichVM }) {
  const { data } = vm
  if (!data) return null
  const hasSolcast = data.solcast_verfuegbar
  const hasEedc = data.eedc_lernfaktor !== null || data.eedc_heute_kwh !== null
  const hasSfml = data.sfml_verfuegbar === true
  const chartData = chartDatenVon(data)
  const summe = stundenSummeVon(chartData, data.aktuelle_stunde)
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Stundenvergleich heute</h3>
      <Table zeilen={24} mitFuss className="table-fixed">
        <colgroup>
          <col className="w-16" /><col /><col className="w-24" /><col /><col className="w-24" />
          {hasSolcast && <><col /><col className="w-24" /></>}{hasSfml && <col />}<col />
        </colgroup>
        <TableHead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            <th className={`${KOPF_ZELLE} text-left text-gray-500`}>Std.</th>
            <th className={`${KOPF_ZELLE} text-right ${Q.openmeteo}`}>OM</th>
            <AbweichungKopf quelle="OpenMeteo" klasse={Q.openmeteo} />
            <th className={`${KOPF_ZELLE} text-right ${eedcKlasse(hasEedc)}`}>eedc</th>
            <AbweichungKopf quelle="eedc" klasse={eedcKlasse(hasEedc)} />
            {hasSolcast && <th className={`${KOPF_ZELLE} text-right ${Q.solcast}`}>SC</th>}
            {hasSolcast && <AbweichungKopf quelle="Solcast" klasse={Q.solcast} />}
            {hasSfml && (
              <th className={`${KOPF_ZELLE} text-right ${Q.sfml}`}>
                <SimpleTooltip text="Solar Forecast ML — deine gewählte Prognosequelle. Wird als Wert gezeigt, aber nicht gegen die anderen Quellen bewertet.">
                  <span>SFML</span>
                </SimpleTooltip>
              </th>
            )}
            <th className={`${KOPF_ZELLE} text-right ${Q.ist}`}>IST</th>
          </tr>
        </TableHead>
        <TableBody>
          {chartData.filter(r => hatWert(r, ZEILE_MIN_KW)).map((row) => {
            const h = parseInt(row.stunde)
            const isPast = data.aktuelle_stunde !== null && h <= data.aktuelle_stunde
            const istVal = row.ist
            return (
              <tr key={row.stunde} className={`border-b border-gray-50 dark:border-gray-800 ${isPast ? 'bg-gray-50/50 dark:bg-gray-800/30' : ''}`}>
                <td className={`${ZELLE} font-mono text-gray-900 dark:text-white`}>{row.stunde}</td>
                <PvgPrognoseZelle wert={row.openmeteo} ist={istVal} />
                <PvgPrognoseZelle wert={hasEedc ? row.eedc : null} ist={istVal} klasse={eedcKlasse(hasEedc)} />
                {hasSolcast && <PvgPrognoseZelle wert={row.solcast} ist={istVal} />}
                {hasSfml && <PvgWertZelle wert={row.sfml} klasse={Q.sfml} />}
                <td className={`${ZELLE} text-right font-mono font-semibold text-green-600 dark:text-green-400`}>{istVal !== null ? fmtZahl(istVal, 2) : <span className="text-gray-400 dark:text-gray-500">—</span>}</td>
              </tr>
            )
          })}
        </TableBody>
        <TableFoot>
          <tr>
            <td className={`${ZELLE} text-gray-900 dark:text-white`}>
              Σ
              {summe.bisStunde !== null && !summe.vollerTag && (
                <SimpleTooltip text={`Verglichen wird nur der bereits gelaufene Tag: Prognose und IST derselben Stunden, bis ${summe.bisStunde}:00. Die Tagesprognose steht in den Kacheln darüber.`}>
                  <span className="block text-[10px] font-normal text-gray-500 dark:text-gray-400">bis {summe.bisStunde}:00</span>
                </SimpleTooltip>
              )}
            </td>
            <PvgPrognoseZelle wert={summe.openmeteo} ist={summe.ist} klasse={Q.openmeteo} stellen={1} />
            <PvgPrognoseZelle wert={hasEedc ? summe.eedc : null} ist={summe.ist} klasse={eedcKlasse(hasEedc)} stellen={1} />
            {hasSolcast && <PvgPrognoseZelle wert={summe.solcast} ist={summe.ist} klasse={Q.solcast} stellen={1} />}
            {hasSfml && <PvgWertZelle wert={summe.sfml} klasse={Q.sfml} stellen={1} />}
            <td className={`${ZELLE} text-right font-mono ${Q.ist}`}>{summe.ist !== null ? fmtZahl(summe.ist, 1) : '—'}</td>
          </tr>
        </TableFoot>
      </Table>
    </Card>
  )
}

export function Pvg7TageTabelle({ vm }: { vm: PrognoseVergleichVM }) {
  const { data, genauigkeit } = vm
  if (!data) return null
  const hasSolcast = data.solcast_verfuegbar
  const hasEedc = data.eedc_lernfaktor !== null || data.eedc_heute_kwh !== null
  const hasSfml = data.sfml_verfuegbar === true
  const vergleichsTage = vergleichsTageVon(data, genauigkeit, hasEedc)
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">7-Tage-Vergleich</h3>
      <MobilKarten>
        {vergleichsTage.map((tag) => {
          const ref = tag.ist_kwh
          const prognosen = [tag.om_kwh, tag.eedc_kwh, tag.sc_kwh].filter((v): v is number => v !== null)
          const mean = prognosen.length > 1 ? prognosen.reduce((a, b) => a + b, 0) / prognosen.length : null
          const devRef = tag.ist_partiell ? mean : (ref ?? mean)
          const devGemessen = !tag.ist_partiell && ref !== null
          const quellen: { label: string; klasse: string; wert: number | null; bewertet: boolean; extra?: React.ReactNode }[] = [
            { label: 'OM', klasse: Q.openmeteo, wert: tag.om_kwh, bewertet: true },
            { label: 'eedc', klasse: eedcKlasse(hasEedc), wert: hasEedc ? tag.eedc_kwh : null, bewertet: true },
          ]
          if (hasSolcast) quellen.push({
            label: 'Solcast', klasse: Q.solcast, wert: tag.sc_kwh, bewertet: true,
            extra: tag.sc_p10 !== null && tag.sc_p90 !== null
              ? <span className="text-gray-400 dark:text-gray-500 text-[10px] ml-1">({fmtZahl(tag.sc_p10, 0)}–{fmtZahl(tag.sc_p90, 0)})</span>
              : null,
          })
          // SFML steht als Wert, ohne Δ und ohne Bewertung — dieselbe Linie wie
          // in der Tabelle (kein Cross-Quellen-Ranking).
          if (hasSfml) quellen.push({ label: 'SFML', klasse: Q.sfml, wert: tag.sfml_kwh, bewertet: false })
          return (
            <MobilKarte
              key={tag.datum}
              titel={
                <span className="flex items-center gap-1.5">
                  {tag.wetter_symbol !== null && <WetterIcon symbol={tag.wetter_symbol} className="h-4 w-4" />}
                  {formatDatum(tag.datum)}
                  {tag.temp_max !== null && <span className="text-xs font-normal text-gray-500">{tag.temp_max}°</span>}
                </span>
              }
              kopfWert={
                <span className={`font-mono font-semibold tabular-nums ${tag.ist_kwh !== null ? Q.ist : 'text-gray-400 dark:text-gray-500'}`}>
                  {tag.ist_kwh !== null
                    ? <>IST {fmtZahl(tag.ist_kwh, 1)}{tag.ist_partiell && <span className="text-gray-400 dark:text-gray-500 text-[10px] font-normal ml-1">bisher</span>}</>
                    : <span className="text-xs">⌀ {mean != null ? fmtZahl(mean, 0) : '—'}</span>}
                </span>
              }
              zeilen={quellen.map((q) => ({
                label: q.label,
                klasse: q.klasse,
                wert: <>{q.wert !== null ? fmtZahl(q.wert, 1) : '—'}{q.extra}</>,
                zusatz: q.bewertet && q.wert !== null && devRef !== null
                  ? <Abweichung prognose={q.wert} ist={devRef} gemessen={devGemessen} />
                  : null,
              }))}
            />
          )
        })}
      </MobilKarten>
      <TabelleAbSm>
        <Table className="table-fixed">
          <colgroup>
            <col className="w-20" /><col className="w-24" /><col /><col className="w-24" />
            <col /><col className="w-24" />{hasSolcast && <><col /><col className="w-24" /></>}
            {hasSfml && <col />}<col />
          </colgroup>
          <TableHead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className={KOPF_ZELLE} aria-label="Wetter"></th>
              <th className={`${KOPF_ZELLE} text-left text-gray-500`}>Datum</th>
              <th className={`${KOPF_ZELLE} text-right ${Q.openmeteo}`}>OM</th>
              <AbweichungKopf quelle="OpenMeteo" klasse={Q.openmeteo} />
              <th className={`${KOPF_ZELLE} text-right ${eedcKlasse(hasEedc)}`}>eedc</th>
              <AbweichungKopf quelle="eedc" klasse={eedcKlasse(hasEedc)} />
              {hasSolcast && <th className={`${KOPF_ZELLE} text-right ${Q.solcast}`}>Solcast</th>}
              {hasSolcast && <AbweichungKopf quelle="Solcast" klasse={Q.solcast} />}
              {hasSfml && (
                <th className={`${KOPF_ZELLE} text-right ${Q.sfml}`}>
                  <SimpleTooltip text="Solar Forecast ML — deine gewählte Prognosequelle. Wird als Wert gezeigt, aber nicht gegen die anderen Quellen bewertet; für zurückliegende Tage führt eedc dazu keine Mitschrift.">
                    <span>SFML</span>
                  </SimpleTooltip>
                </th>
              )}
              <th className={`${KOPF_ZELLE} text-right ${Q.ist}`}>IST</th>
            </tr>
          </TableHead>
          <TableBody>
            {vergleichsTage.map((tag, idx) => {
              const ref = tag.ist_kwh
              const prognosen = [tag.om_kwh, tag.eedc_kwh, tag.sc_kwh].filter((v): v is number => v !== null)
              const mean = prognosen.length > 1 ? prognosen.reduce((a, b) => a + b, 0) / prognosen.length : null
              const devRef = tag.ist_partiell ? mean : (ref ?? mean)
              // Die Referenz ist nur dann ein gemessenes IST, wenn der Tag durch ist.
              // Beim laufenden Tag und in der Zukunft steht dort das Mittel der
              // Prognosen — dagegen ist ein „± 0,0" keine Aussage über die Welt.
              // Vorher rief diese Tabelle als einzige nie mit `gemessen`, weshalb sie
              // auch für abgeschlossene Tage unterdrückte (P-5, am Code gefunden).
              const devGemessen = !tag.ist_partiell && ref !== null
              const isFirstFuture = idx > 0 && vergleichsTage[idx - 1].ist_kwh !== null && tag.ist_kwh === null
              return (
                <tr key={tag.datum} className={`border-b border-gray-100 dark:border-gray-800${isFirstFuture ? ' border-t-2 border-t-gray-300 dark:border-t-gray-600' : ''}`}>
                  <td className={`${ZELLE} text-center`}>{tag.wetter_symbol !== null ? (<div className="flex items-center justify-center gap-1"><WetterIcon symbol={tag.wetter_symbol} className="h-4 w-4" />{tag.temp_max !== null && <span className="text-xs text-gray-500">{tag.temp_max}°</span>}</div>) : null}</td>
                  <td className={`${ZELLE} text-gray-900 dark:text-white`}>{formatDatum(tag.datum)}</td>
                  <PvgPrognoseZelle wert={tag.om_kwh} ist={devRef} stellen={1} gemessen={devGemessen} />
                  <PvgPrognoseZelle wert={hasEedc ? tag.eedc_kwh : null} ist={devRef} klasse={eedcKlasse(hasEedc)} stellen={1} gemessen={devGemessen} />
                  {hasSolcast && (
                    <PvgPrognoseZelle
                      wert={tag.sc_kwh} ist={devRef} stellen={1} gemessen={devGemessen} wertKlasse="font-semibold"
                      extra={tag.sc_p10 !== null && tag.sc_p90 !== null
                        ? <span className="text-gray-400 dark:text-gray-500 text-xs ml-1">({fmtZahl(tag.sc_p10, 0)}–{fmtZahl(tag.sc_p90, 0)})</span>
                        : null}
                    />
                  )}
                  {hasSfml && <PvgWertZelle wert={tag.sfml_kwh} klasse={Q.sfml} stellen={1} />}
                  <td className={`${ZELLE} text-right font-mono font-semibold text-green-600 dark:text-green-400`}>{tag.ist_kwh !== null ? (<>{fmtZahl(tag.ist_kwh, 1)}{tag.ist_partiell && <span className="text-gray-400 dark:text-gray-500 text-[10px] font-normal ml-1">bisher</span>}</>) : <span className="text-gray-400 dark:text-gray-500 text-xs">⌀{mean != null ? fmtZahl(mean, 0) : '—'}</span>}</td>
                </tr>
              )
            })}
          </TableBody>
        </Table>
      </TabelleAbSm>
    </Card>
  )
}

