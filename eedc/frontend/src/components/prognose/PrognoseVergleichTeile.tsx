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
import { Card, ChartLegende, buttonClasses } from '../ui'
import { SimpleTooltip } from '../ui/FormelTooltip'
import {
  aussichtenApi, PrognosenVergleich, GenauigkeitsResponse, AsymmetrieEintrag,
} from '../../api/aussichten'
import { energieProfilApi } from '../../api/energie_profil'
import { getStratifizierung, StratifizierungResponse, Wetterklasse, wetterBackfill } from '../../api/korrekturprofil'
import { KorrekturprofilHeatmapCard } from '../../pages/aussichten/KorrekturprofilHeatmapCard'
import { PROGNOSE_QUELLEN_COLORS, PROGNOSE_QUELLEN_TEXT, PROGNOSE_DASH, fmtZahl } from '../../lib'
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
    setBackfillRunning(true); setBackfillResult(null); setBackfillError(null)
    try {
      const res = await wetterBackfill(anlageId, 730)
      if (res.status === 'ok') {
        setBackfillResult(`${res.stunden_geupdated ?? 0} Stunden / ${res.tage_geupdated ?? 0} Tage geladen` +
          (res.von && res.bis ? ` (${res.von} – ${res.bis})` : ''))
        setStratifizierung(await getStratifizierung(anlageId, 90).catch(() => null))
      } else if (res.status === 'skipped') {
        setBackfillError(`Übersprungen: ${res.grund ?? 'unbekannter Grund'}`)
      } else {
        setBackfillError(res.fehler ?? 'Backfill fehlgeschlagen')
      }
    } catch (err) {
      setBackfillError(err instanceof Error ? err.message : 'Netzwerk-Fehler')
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
    const ist = data.ist_stundenprofil.find(s => s.stunde === h)
    return {
      stunde: `${h}:00`, openmeteo: om?.kw ?? 0, eedc: eedc?.kw ?? null,
      solcast: sc?.kw ?? 0, solcast_p10: sc?.p10_kw ?? 0, solcast_p90: sc?.p90_kw ?? 0, ist: ist?.kw ?? null,
    }
  })
}
function sichtbareStunden(chartData: ReturnType<typeof chartDatenVon>) {
  const HELL_KW = 0.05
  const helle: number[] = []
  for (let i = 0; i < chartData.length; i++) {
    const d = chartData[i]
    const max = Math.max((d.openmeteo as number) || 0, (d.solcast as number) || 0, (d.eedc as number | null) ?? 0, (d.ist as number | null) ?? 0)
    if (max > HELL_KW) helle.push(i)
  }
  const hMin = helle.length > 0 ? Math.max(0, helle[0] - 1) : 0
  const hMax = helle.length > 0 ? Math.min(23, helle[helle.length - 1] + 1) : 23
  return chartData.slice(hMin, hMax + 1)
}
function vergleichsTageVon(data: PrognosenVergleich, genauigkeit: GenauigkeitsResponse | null, hasEedc: boolean) {
  const heute = new Date().toISOString().slice(0, 10)
  const historisch = (genauigkeit?.tage ?? []).filter(t => t.datum < heute).slice(-4).map(t => ({
    datum: t.datum, om_kwh: t.openmeteo_kwh, eedc_kwh: t.eedc_kwh, sc_kwh: t.solcast_kwh,
    sc_p10: null as number | null, sc_p90: null as number | null,
    wetter_symbol: t.wetter_symbol ?? null, temp_max: t.temperatur_max_c ?? null, ist_kwh: t.ist_kwh, ist_partiell: false,
  }))
  const omHeute = data.openmeteo_tage.find(om => om.datum === heute)
  const heuteZeile = {
    datum: heute, om_kwh: data.openmeteo_heute_kwh, eedc_kwh: hasEedc ? data.eedc_heute_kwh : null,
    sc_kwh: data.solcast_heute_kwh, sc_p10: data.solcast_p10_kwh ?? null, sc_p90: data.solcast_p90_kwh ?? null,
    wetter_symbol: (omHeute?.wetter_symbol ?? null) as string | null, temp_max: (omHeute?.temperatur_max_c ?? null) as number | null,
    ist_kwh: data.ist_heute_kwh, ist_partiell: true,
  }
  const zukunft = data.openmeteo_tage.filter(om => om.datum > heute).slice(0, 3).map(om => {
    const sc = data.solcast_tage.find(s => s.datum === om.datum)
    return {
      datum: om.datum, om_kwh: om.pv_prognose_kwh as number | null,
      // Prognose-Kanon: eedc je Tag kommt jetzt vom Backend (kein client-
      // seitiges `om × Lernfaktor`-Nachrechnen mehr — war eine Drift-Quelle).
      eedc_kwh: hasEedc ? (om.eedc_kwh ?? null) : null,
      sc_kwh: sc?.kwh ?? null, sc_p10: sc?.p10 ?? null, sc_p90: sc?.p90 ?? null,
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
function DatendichtFallback({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="hidden sm:block">{children}</div>
      <div className="sm:hidden p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded text-sm text-amber-900 dark:text-amber-200">
        <span className="portrait:inline landscape:hidden">Datendichte Tabelle — bitte Gerät ins Querformat drehen oder Desktop verwenden.</span>
        <span className="portrait:hidden landscape:inline">Auflösung zu gering für datendichte Anzeige — bitte Desktop verwenden.</span>
      </div>
    </>
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
  const stundenLabel = fehlendeStunden.length === 0 ? '—'
    : fehlendeStunden.length === 1 ? `Stunde ${fehlendeStunden[0]}:00–${fehlendeStunden[0] + 1}:00`
    : `Stunden ${fehlendeStunden.map(h => `${h}:00`).join(', ')}`
  const handleReaggregate = async () => {
    setBusy(true); setFeedback(null)
    try {
      const heute = new Date().toISOString().slice(0, 10)
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
        <div className="absolute right-0 top-full mt-1 z-[10000] w-72 max-w-[calc(100vw-2rem)] p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-xl text-left">
          <div className="text-xs font-semibold text-gray-900 dark:text-white mb-1">IST-Daten unvollständig</div>
          <div className="text-xs text-gray-600 dark:text-gray-300 leading-relaxed mb-2">
            Ohne Werte für {stundenLabel}. Falls eedc oder HA kürzlich neu gestartet wurden, schließt sich die Lücke beim nächsten Snapshot-Zyklus (max. 1 h). Bleibt sie bestehen, ist wahrscheinlich der kumulative Zähler im Sensor-Mapping nicht gesetzt.
          </div>
          {feedback && (
            <div className={`text-xs mb-2 px-2 py-1 rounded ${feedback.tone === 'success' ? 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300' : feedback.tone === 'warning' ? 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300' : 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300'}`}>{feedback.msg}</div>
          )}
          <div className="flex gap-2">
            <button type="button" onClick={handleReaggregate} disabled={busy} className={buttonClasses({ variant: 'primary', size: 'sm', className: 'flex-1' })}>{busy ? 'Berechne…' : 'Tag neu berechnen'}</button>
            <a href="#/einstellungen/sensor-mapping" className={buttonClasses({ variant: 'secondary', size: 'sm' })}>Sensor-Mapping</a>
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
function DevBadge({ prognose, ist }: { prognose: number; ist: number }) {
  if (ist < 0.05 && prognose < 0.05) return null
  const diff = prognose - ist
  if (Math.abs(diff) < 0.03) return null
  const pct = ist > 0.05 ? Math.abs(diff / ist) * 100 : (prognose > 0.05 ? 100 : 0)
  const color = pct < 10 ? 'text-green-500' : pct < 30 ? 'text-yellow-500' : 'text-red-400'
  const arrow = diff > 0 ? '▲' : '▼'
  return <span className={`text-[10px] ml-1 ${color}`}>{arrow} {fmtZahl(Math.abs(diff), 1)}</span>
}
function AbweichungCell({ prognose, ist }: { prognose: number; ist: number | null }) {
  if (ist === null || ist < 0.5) return <span>{fmtZahl(prognose, 1)}</span>
  const pct = ((prognose - ist) / ist) * 100
  const color = Math.abs(pct) < 10 ? 'text-green-500' : Math.abs(pct) < 30 ? 'text-yellow-500' : 'text-red-500'
  return <span>{fmtZahl(prognose, 1)}<span className={`text-xs ml-1 ${color}`}>{pct > 0 ? '+' : ''}{fmtZahl(pct, 0)} %</span></span>
}
interface StundenTooltipPayload { dataKey?: string; value?: number | null; stroke?: string; fill?: string }
function StundenTooltip({ active, payload, label, hasEedc }: { active?: boolean; payload?: StundenTooltipPayload[]; label?: string | number; hasEedc?: boolean }) {
  if (!active || !payload?.length) return null
  const h = parseInt(String(label ?? '').replace(':00', ''))
  const prev = (h - 1 + 24) % 24
  const intervalLabel = `${String(prev).padStart(2, '0')}:00–${String(h).padStart(2, '0')}:00 Uhr`
  return (
    <div className="bg-gray-900 dark:bg-gray-950 text-white p-3 rounded-lg shadow-lg text-xs">
      <div className="font-medium mb-1">{intervalLabel}</div>
      {payload.map((p: StundenTooltipPayload) => {
        const key = p.dataKey ?? ''
        if (['solcast_p10', 'solcast_p90'].includes(key)) return null
        if (key === 'ist' && p.value === null) return null
        if (key === 'eedc' && !hasEedc) return null
        const labels: Record<string, string> = { openmeteo: 'OpenMeteo (roh)', eedc: 'eedc (kalibriert)', solcast: 'Solcast', ist: 'IST' }
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
  return (
    <Card>
      <DatendichtFallback>
        <div className="overflow-x-auto">
          <table className="w-full text-sm table-fixed">
            <colgroup><col className="w-32" /><col /><col />{hasSolcast && <col />}<col /></colgroup>
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-2 px-3 font-medium text-gray-500 dark:text-gray-400"></th>
                <th className={`text-right py-2 px-3 font-medium ${Q.openmeteo}`}>
                  <SimpleTooltip text="Open-Meteo: GTI-basierte Prognose aus Wettermodell (ICON/ECMWF), 14 Tage Horizont"><span>OpenMeteo</span></SimpleTooltip>
                </th>
                <th className={`text-right py-2 px-3 font-medium ${eedcKlasse(hasEedc)}`}>
                  <SimpleTooltip text={hasEedc && lf != null ? `eedc: ${progBasisLabel} × Lernfaktor ${fmtZahl(lf, 3)} (MOS-kalibriert${data.eedc_lernfaktor_stufe ? ', ' + data.eedc_lernfaktor_stufe : ''})` : `eedc: Lernfaktor noch nicht verfügbar — siehe Hinweis unten`}>
                    <span>eedc {hasEedc && lf != null && <span className="text-xs font-normal">×{fmtZahl(lf, 2)}</span>}</span>
                  </SimpleTooltip>
                </th>
                {hasSolcast && (
                  <th className={`text-right py-2 px-3 font-medium ${Q.solcast}`}>
                    <SimpleTooltip text={`Solcast: Satellitenbasierte PV-Prognose mit Konfidenzband, 7 Tage (${data.solcast_quelle === 'solcast_api' ? 'API' : 'HA-Sensor'})`}><span>Solcast</span></SimpleTooltip>
                  </th>
                )}
                <th className={`text-right py-2 px-3 font-medium ${Q.ist}`}>
                  <SimpleTooltip text="IST: Tatsächliche PV-Erzeugung aus Sensor-Daten (TagesEnergieProfil)"><span>IST</span></SimpleTooltip>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/20">
                <td className="py-2 px-3 font-medium text-gray-900 dark:text-white">Heute</td>
                <td className="py-2 px-3 text-right font-mono">{fmtKwh(data.openmeteo_heute_kwh)}</td>
                <td className={`py-2 px-3 text-right font-mono ${hasEedc ? `font-semibold ${Q.eedc}` : 'text-gray-400 dark:text-gray-500'}`}>{hasEedc ? fmtKwh(data.eedc_heute_kwh) : '—'}</td>
                {hasSolcast && <td className="py-2 px-3 text-right font-mono">{fmtKwhBand(data.solcast_heute_kwh, data.solcast_p10_kwh, data.solcast_p90_kwh)}</td>}
                <td className="py-2 px-3 text-right font-mono font-semibold text-green-600 dark:text-green-400">
                  {fmtKwh(data.ist_heute_kwh)}
                  {data.ist_unvollstaendig && (
                    <IstUnvollstaendigPopover fehlendeStunden={data.ist_stundenprofil.filter(s => s.kw === null && s.stunde < new Date().getHours()).map(s => s.stunde)} anlageId={vm.anlageId} onReloaded={vm.reload} />
                  )}
                </td>
              </tr>
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-2 px-3 text-gray-500 dark:text-gray-400 text-xs">
                  <SimpleTooltip text="Tagesprojektion: IST bisher + Prognose für die restlichen Stunden. Pro Spalte mit der jeweiligen Quelle; Gesamtspalte mit der in den Einstellungen gewählten Prognosequelle."><span>↳ Verbleibend</span></SimpleTooltip>
                </td>
                <td className="py-2 px-3 text-right font-mono text-xs text-gray-500">{fmtKwh(data.verbleibend_om_kwh)}</td>
                <td className="py-2 px-3 text-right font-mono text-xs text-gray-500">{hasEedc ? fmtKwh(data.verbleibend_eedc_kwh) : <span className="text-gray-400 dark:text-gray-500">—</span>}</td>
                {hasSolcast && <td className="py-2 px-3 text-right font-mono text-xs text-gray-500">{fmtKwh(data.verbleibend_solcast_kwh)}</td>}
                <td className="py-2 px-3 text-right font-mono text-emerald-500">{fmtKwh(data.verbleibend_kwh)}</td>
              </tr>
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-1 px-3 text-gray-400 dark:text-gray-500 text-xs">↳ VM / NM</td>
                <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{fmtVmNm(data.openmeteo_tageshaelften?.[0])}</td>
                <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{hasEedc ? fmtVmNm(data.eedc_tageshaelften?.[0]) : <span className="text-gray-400 dark:text-gray-500">—</span>}</td>
                {hasSolcast && <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{fmtVmNm(data.solcast_tageshaelften?.[0])}</td>}
                <td className="py-1 px-3 text-right font-mono text-xs text-green-500">{fmtVmNm(data.ist_tageshaelfte)}</td>
              </tr>
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-2 px-3 font-medium text-gray-900 dark:text-white">Morgen</td>
                <td className="py-2 px-3 text-right font-mono">{fmtKwh(data.openmeteo_morgen_kwh)}</td>
                <td className={`py-2 px-3 text-right font-mono ${eedcKlasse(hasEedc)}`}>{hasEedc ? fmtKwh(data.eedc_morgen_kwh) : '—'}</td>
                {hasSolcast && <td className="py-2 px-3 text-right font-mono">{fmtKwhBand(data.solcast_morgen_kwh, data.solcast_morgen_p10_kwh, data.solcast_morgen_p90_kwh)}</td>}
                <td className="py-2 px-3 text-right text-gray-400 dark:text-gray-500">—</td>
              </tr>
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-1 px-3 text-gray-400 dark:text-gray-500 text-xs">↳ VM / NM</td>
                <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{fmtVmNm(data.openmeteo_tageshaelften?.[1])}</td>
                <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{hasEedc ? fmtVmNm(data.eedc_tageshaelften?.[1]) : <span className="text-gray-400 dark:text-gray-500">—</span>}</td>
                {hasSolcast && <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{fmtVmNm(data.solcast_tageshaelften?.[1])}</td>}
                <td className="py-1 px-3"></td>
              </tr>
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-2 px-3 font-medium text-gray-900 dark:text-white">Übermorgen</td>
                <td className="py-2 px-3 text-right font-mono">{fmtKwh(data.openmeteo_uebermorgen_kwh)}</td>
                <td className={`py-2 px-3 text-right font-mono ${eedcKlasse(hasEedc)}`}>{hasEedc ? fmtKwh(data.eedc_uebermorgen_kwh) : '—'}</td>
                {hasSolcast && <td className="py-2 px-3 text-right font-mono">{fmtKwh(data.solcast_uebermorgen_kwh)}</td>}
                <td className="py-2 px-3 text-right text-gray-400 dark:text-gray-500">—</td>
              </tr>
              <tr>
                <td className="py-1 px-3 text-gray-400 dark:text-gray-500 text-xs">↳ VM / NM</td>
                <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{fmtVmNm(data.openmeteo_tageshaelften?.[2])}</td>
                <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{hasEedc ? fmtVmNm(data.eedc_tageshaelften?.[2]) : <span className="text-gray-400 dark:text-gray-500">—</span>}</td>
                {hasSolcast && <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{fmtVmNm(data.solcast_tageshaelften?.[2])}</td>}
                <td className="py-1 px-3"></td>
              </tr>
            </tbody>
          </table>
        </div>
      </DatendichtFallback>
    </Card>
  )
}

export function PvgStatusHinweise({ vm }: { vm: PrognoseVergleichVM }) {
  const { data, genauigkeit } = vm
  if (!data) return null
  const hasEedc = data.eedc_lernfaktor !== null || data.eedc_heute_kwh !== null
  return (
    <>
      {data.solcast_status && data.solcast_status !== 'ok' && data.solcast_hinweis && (
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
        <button type="button" onClick={vm.handleWetterBackfill} disabled={vm.backfillRunning} className="px-3 py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-white rounded transition-colors">{vm.backfillRunning ? 'Lädt Wetter-Historie…' : 'Wetter-Historie nachladen (2 Jahre)'}</button>
        {vm.backfillError && <div className="mt-3 text-xs text-red-600 dark:text-red-400">Fehler: {vm.backfillError}</div>}
        {vm.backfillResult && <div className="mt-3 text-xs text-green-700 dark:text-green-400">✓ {vm.backfillResult} — Stratifizierung wird neu berechnet</div>}
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
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Genauigkeits-Tracking <span className="text-sm font-normal text-gray-500 ml-2">(letzte {genauigkeit.anzahl_tage} Tage)</span></h3>
        <div className="flex items-center gap-3">
          <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 text-xs overflow-hidden">
            {([7, 10, 30] as const).map(t => (
              <button key={t} type="button" onClick={() => vm.setGenauigkeitsTage(t)} className={`px-3 py-1 transition-colors ${vm.genauigkeitsTage === t ? 'bg-primary-600 text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}>{t} T</button>
            ))}
          </div>
          <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 text-xs overflow-hidden">
            <button type="button" onClick={() => vm.setGenauigkeitsModus('kompakt')} className={`px-3 py-1 transition-colors ${vm.genauigkeitsModus === 'kompakt' ? 'bg-primary-600 text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}>Kompakt</button>
            <button type="button" onClick={() => vm.setGenauigkeitsModus('diagnostisch')} className={`px-3 py-1 transition-colors ${vm.genauigkeitsModus === 'diagnostisch' ? 'bg-primary-600 text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}>Diagnostisch</button>
          </div>
          <SimpleTooltip text={`Ausreißer = Tage, an denen eine Quelle > ${fmtZahl(genauigkeit.ausreisser_schwelle_prozent ?? 50, 0)} % daneben lag (z. B. Sensor-Aussetzer). Standardmäßig bleiben sie in der Statistik — gerade Schlechtprognose-Tage haben Erkenntniswert. Hier optional ausblenden.`}>
            <label className={`flex items-center gap-1.5 text-xs cursor-pointer select-none ${(genauigkeit.anzahl_ausreisser ?? 0) === 0 ? 'opacity-50' : ''}`}>
              <input type="checkbox" checked={vm.ausreisserAusblenden} onChange={e => vm.setAusreisserAusblenden(e.target.checked)} className="h-3.5 w-3.5 rounded border-gray-300 dark:border-gray-600 text-primary-600 focus:ring-primary-500" />
              <span className="text-gray-600 dark:text-gray-400">Ausreißer ausblenden{(genauigkeit.anzahl_ausreisser ?? 0) > 0 ? ` (${genauigkeit.anzahl_ausreisser})` : ''}</span>
            </label>
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
        MAPE/Bias oben über {genauigkeit.anzahl_tage} Tage{vm.ausreisserAusblenden && (genauigkeit.anzahl_ausreisser ?? 0) > 0 ? ` (ohne ${genauigkeit.anzahl_ausreisser} Ausreißer)` : ''} · Tabelle unten: letzte 7 Tage
      </div>
      <DatendichtFallback>
        <div className="overflow-x-auto">
          <table className="w-full text-sm table-fixed">
            <colgroup><col className="w-28" /><col /><col /><col /><col /></colgroup>
            <thead><tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="text-left py-2 px-3 font-medium text-gray-500">Datum</th>
              <th className={`text-right py-2 px-3 font-medium ${Q.openmeteo}`}>OpenMeteo</th>
              <th className={`text-right py-2 px-3 font-medium ${lf != null ? Q.eedc : 'text-gray-400 dark:text-gray-500'}`}>
                <SimpleTooltip text={lf == null ? 'Lernfaktor noch nicht verfügbar — siehe Hinweis oben' : `eedc = OpenMeteo × Lernfaktor ${fmtZahl(lf, 3)}`}><span>eedc</span></SimpleTooltip>
              </th>
              <th className={`text-right py-2 px-3 font-medium ${Q.solcast}`}>Solcast</th>
              <th className={`text-right py-2 px-3 font-medium ${Q.ist}`}>IST</th>
            </tr></thead>
            <tbody>
              {genauigkeit.tage.slice(-7).reverse().map((tag) => {
                const ausgeschlossen = vm.ausreisserAusblenden && tag.ist_ausreisser
                return (
                  <tr key={tag.datum} className={`border-b border-gray-100 dark:border-gray-800 ${tag.ist_ausreisser ? 'border-l-2 border-l-amber-400 dark:border-l-amber-500' : ''} ${ausgeschlossen ? 'opacity-40' : ''}`}>
                    <td className="py-2 px-3 text-gray-900 dark:text-white">
                      {formatDatum(tag.datum)}
                      {tag.ist_ausreisser && (<SimpleTooltip text={ausgeschlossen ? 'Ausreißer — aus MAE/MBE ausgeschlossen' : 'Ausreißer — große Abweichung, bleibt in der Statistik'}><span className="ml-1 text-amber-500 text-[10px]">⚠</span></SimpleTooltip>)}
                    </td>
                    <td className="py-2 px-3 text-right font-mono">{tag.openmeteo_kwh !== null ? <AbweichungCell prognose={tag.openmeteo_kwh} ist={tag.ist_kwh} /> : '—'}</td>
                    <td className="py-2 px-3 text-right font-mono">{tag.eedc_kwh !== null ? <AbweichungCell prognose={tag.eedc_kwh} ist={tag.ist_kwh} /> : <span className="text-gray-400 dark:text-gray-500">—</span>}</td>
                    <td className="py-2 px-3 text-right font-mono">{tag.solcast_kwh !== null ? <AbweichungCell prognose={tag.solcast_kwh} ist={tag.ist_kwh} /> : <span className="text-gray-400 dark:text-gray-500">—</span>}</td>
                    <td className="py-2 px-3 text-right font-mono font-semibold text-green-600 dark:text-green-400">{tag.ist_kwh !== null ? fmtZahl(tag.ist_kwh, 1) : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </DatendichtFallback>
    </Card>
  )
}

// ════ BLOCK ⑤ — Profil ═════════════════════════════════════════════════════════
export function PvgStundenprofil({ vm }: { vm: PrognoseVergleichVM }) {
  const achsen = useChartTheme()
  const { data } = vm
  if (!data) return null
  const hasSolcast = data.solcast_verfuegbar
  const hasEedc = data.eedc_lernfaktor !== null || data.eedc_heute_kwh !== null
  const lf = data.eedc_lernfaktor
  const visibleChartData = sichtbareStunden(chartDatenVon(data))
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Tagesverlauf — Stundenprofil</h3>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={visibleChartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} opacity={0.3} />
            <XAxis dataKey="stunde" tick={{ fontSize: 10 }} tickFormatter={(v) => v.replace(':00', '')} padding={{ left: 8, right: 8 }} />
            <YAxis tick={{ fontSize: 10 }} label={{ value: 'kW', angle: -90, position: 'insideLeft', style: { fontSize: 11 } }} />
            <Tooltip content={<StundenTooltip hasEedc={hasEedc} />} />
            <Legend content={<ChartLegende formatter={(v) => ({ ist: 'IST', eedc: `eedc${lf != null ? ` (OpenMeteo ×${fmtZahl(lf, 2)})` : ''}`, solcast: 'Solcast', openmeteo: 'OpenMeteo (roh)' }[v] || v)} />} />
            {data.aktuelle_stunde !== null && (<ReferenceLine x={`${data.aktuelle_stunde}:00`} stroke={achsen.referenz} strokeDasharray="3 3" label={{ value: 'Jetzt', position: 'top', fontSize: 10, fill: achsen.achse }} />)}
            <Area dataKey="ist" stroke={PROGNOSE_QUELLEN_COLORS.ist} fill={PROGNOSE_QUELLEN_COLORS.ist} fillOpacity={0.3} strokeWidth={2} dot={false} name="ist" connectNulls={false} />
            {hasSolcast && <Line dataKey="solcast" stroke={PROGNOSE_QUELLEN_COLORS.solcast} strokeWidth={2} strokeDasharray={PROGNOSE_DASH} dot={false} name="solcast" />}
            {hasEedc && <Line dataKey="eedc" stroke={PROGNOSE_QUELLEN_COLORS.eedc} strokeWidth={2} strokeDasharray={PROGNOSE_DASH} dot={false} name="eedc" />}
            <Line dataKey="openmeteo" stroke={PROGNOSE_QUELLEN_COLORS.openmeteo} strokeWidth={1.5} strokeDasharray={PROGNOSE_DASH} dot={false} name="openmeteo" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

export function Pvg24hTabelle({ vm }: { vm: PrognoseVergleichVM }) {
  const { data } = vm
  if (!data) return null
  const hasSolcast = data.solcast_verfuegbar
  const hasEedc = data.eedc_lernfaktor !== null || data.eedc_heute_kwh !== null
  const chartData = chartDatenVon(data)
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Stundenvergleich heute</h3>
      <div>
        <table className="w-full text-xs table-fixed">
          <colgroup><col className="w-16" /><col /><col />{hasSolcast && <col />}<col /></colgroup>
          <thead className="bg-white dark:bg-gray-900"><tr className="border-b border-gray-200 dark:border-gray-700">
            <th className="text-left py-1.5 px-2 font-medium text-gray-500">Std.</th>
            <th className={`text-right py-1.5 px-2 font-medium ${Q.openmeteo}`}>OM</th>
            <th className={`text-right py-1.5 px-2 font-medium ${eedcKlasse(hasEedc)}`}>eedc</th>
            {hasSolcast && <th className={`text-right py-1.5 px-2 font-medium ${Q.solcast}`}>SC</th>}
            <th className={`text-right py-1.5 pl-2 pr-3 font-medium ${Q.ist}`}>IST</th>
          </tr></thead>
          <tbody>
            {chartData.filter(r => r.openmeteo > 0.01 || r.solcast > 0.01 || (r.ist !== null && r.ist > 0.01)).map((row) => {
              const h = parseInt(row.stunde)
              const isPast = data.aktuelle_stunde !== null && h <= data.aktuelle_stunde
              const istVal = row.ist
              return (
                <tr key={row.stunde} className={`border-b border-gray-50 dark:border-gray-800 ${isPast ? 'bg-gray-50/50 dark:bg-gray-800/30' : ''}`}>
                  <td className="py-1 px-2 font-mono text-gray-900 dark:text-white">{row.stunde}</td>
                  <td className="py-1 px-2 text-right font-mono">{fmtZahl(row.openmeteo, 2)}{istVal !== null && <DevBadge prognose={row.openmeteo} ist={istVal} />}</td>
                  <td className={`py-1 px-2 text-right font-mono ${eedcKlasse(hasEedc)}`}>{hasEedc ? (<>{row.eedc != null ? fmtZahl(row.eedc, 2) : '—'}{istVal !== null && row.eedc !== null && <DevBadge prognose={row.eedc} ist={istVal} />}</>) : '—'}</td>
                  {hasSolcast && (<td className="py-1 px-2 text-right font-mono">{fmtZahl(row.solcast, 2)}{istVal !== null && <DevBadge prognose={row.solcast} ist={istVal} />}</td>)}
                  <td className="py-1 pl-2 pr-3 text-right font-mono font-semibold text-green-600 dark:text-green-400">{istVal !== null ? fmtZahl(istVal, 2) : <span className="text-gray-400 dark:text-gray-500">—</span>}</td>
                </tr>
              )
            })}
          </tbody>
          <tfoot className="bg-white dark:bg-gray-900">
            {(() => {
              const omSum = chartData.reduce((s, r) => s + r.openmeteo, 0)
              const eedcSum = chartData.reduce((s, r) => s + (r.eedc ?? 0), 0)
              const scSum = chartData.reduce((s, r) => s + r.solcast, 0)
              const istSum = data.ist_heute_kwh
              return (
                <tr className="border-t-2 border-gray-300 dark:border-gray-600 font-semibold">
                  <td className="py-1.5 px-2 text-gray-900 dark:text-white">Σ</td>
                  <td className={`py-1.5 px-2 text-right font-mono ${Q.openmeteo}`}>{fmtZahl(omSum, 1)}{istSum !== null && <DevBadge prognose={omSum} ist={istSum} />}</td>
                  <td className={`py-1.5 px-2 text-right font-mono ${eedcKlasse(hasEedc)}`}>{hasEedc ? (<>{fmtZahl(eedcSum, 1)}{istSum !== null && <DevBadge prognose={eedcSum} ist={istSum} />}</>) : '—'}</td>
                  {hasSolcast && (<td className={`py-1.5 px-2 text-right font-mono ${Q.solcast}`}>{fmtZahl(scSum, 1)}{istSum !== null && <DevBadge prognose={scSum} ist={istSum} />}</td>)}
                  <td className={`py-1.5 pl-2 pr-3 text-right font-mono ${Q.ist}`}>{istSum !== null ? fmtZahl(istSum, 1) : '—'}</td>
                </tr>
              )
            })()}
          </tfoot>
        </table>
      </div>
    </Card>
  )
}

export function Pvg7TageTabelle({ vm }: { vm: PrognoseVergleichVM }) {
  const { data, genauigkeit } = vm
  if (!data) return null
  const hasSolcast = data.solcast_verfuegbar
  const hasEedc = data.eedc_lernfaktor !== null || data.eedc_heute_kwh !== null
  const vergleichsTage = vergleichsTageVon(data, genauigkeit, hasEedc)
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">7-Tage-Vergleich</h3>
      <DatendichtFallback>
        <div className="overflow-x-auto">
          <table className="w-full text-sm table-fixed">
            <colgroup><col className="w-20" /><col className="w-24" /><col /><col />{hasSolcast && <col />}<col /></colgroup>
            <thead><tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="py-2 px-2" aria-label="Wetter"></th>
              <th className="text-left py-2 px-2 font-medium text-gray-500">Datum</th>
              <th className={`text-right py-2 px-2 font-medium ${Q.openmeteo}`}>OM</th>
              <th className={`text-right py-2 px-2 font-medium ${eedcKlasse(hasEedc)}`}>eedc</th>
              {hasSolcast && <th className={`text-right py-2 px-2 font-medium ${Q.solcast}`}>Solcast</th>}
              <th className={`text-right py-2 pl-2 pr-3 font-medium ${Q.ist}`}>IST</th>
            </tr></thead>
            <tbody>
              {vergleichsTage.map((tag, idx) => {
                const ref = tag.ist_kwh
                const prognosen = [tag.om_kwh, tag.eedc_kwh, tag.sc_kwh].filter((v): v is number => v !== null)
                const mean = prognosen.length > 1 ? prognosen.reduce((a, b) => a + b, 0) / prognosen.length : null
                const devRef = tag.ist_partiell ? mean : (ref ?? mean)
                const isFirstFuture = idx > 0 && vergleichsTage[idx - 1].ist_kwh !== null && tag.ist_kwh === null
                return (
                  <tr key={tag.datum} className={`border-b border-gray-100 dark:border-gray-800${isFirstFuture ? ' border-t-2 border-t-gray-300 dark:border-t-gray-600' : ''}`}>
                    <td className="py-2 px-2 text-center">{tag.wetter_symbol !== null ? (<div className="flex items-center justify-center gap-1"><WetterIcon symbol={tag.wetter_symbol} className="h-4 w-4" />{tag.temp_max !== null && <span className="text-xs text-gray-500">{tag.temp_max}°</span>}</div>) : null}</td>
                    <td className="py-2 px-2 text-gray-900 dark:text-white">{formatDatum(tag.datum)}</td>
                    <td className="py-2 px-2 text-right font-mono">{tag.om_kwh !== null ? fmtZahl(tag.om_kwh, 1) : '—'}{devRef !== null && tag.om_kwh !== null && <DevBadge prognose={tag.om_kwh} ist={devRef} />}</td>
                    <td className={`py-2 px-2 text-right font-mono ${eedcKlasse(hasEedc)}`}>{hasEedc ? (<>{tag.eedc_kwh != null ? fmtZahl(tag.eedc_kwh, 1) : '—'}{devRef !== null && tag.eedc_kwh !== null && <DevBadge prognose={tag.eedc_kwh} ist={devRef} />}</>) : '—'}</td>
                    {hasSolcast && (<td className="py-2 px-2 text-right font-mono">{tag.sc_kwh !== null ? (<><span className="font-semibold">{fmtZahl(tag.sc_kwh, 1)}</span>{devRef !== null && <DevBadge prognose={tag.sc_kwh} ist={devRef} />}{tag.sc_p10 !== null && tag.sc_p90 !== null && (<span className="text-gray-400 dark:text-gray-500 text-xs ml-1">({fmtZahl(tag.sc_p10, 0)}–{fmtZahl(tag.sc_p90, 0)})</span>)}</>) : '—'}</td>)}
                    <td className="py-2 pl-2 pr-3 text-right font-mono font-semibold text-green-600 dark:text-green-400">{tag.ist_kwh !== null ? (<>{fmtZahl(tag.ist_kwh, 1)}{tag.ist_partiell && <span className="text-gray-400 dark:text-gray-500 text-[10px] font-normal ml-1">bisher</span>}</>) : <span className="text-gray-400 dark:text-gray-500 text-xs">⌀{mean != null ? fmtZahl(mean, 0) : '—'}</span>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </DatendichtFallback>
    </Card>
  )
}

