/**
 * Monatsberichte — vertikaler Zeitstrahl + vollständige Detailansicht
 *
 * Linke Spalte : Vertikaler Zeitstrahl mit Jahres-Divider, Monatspunkten
 *                und SVG-Mini-Bar (PV-Auslastung relativ zum Jahresmax).
 * Rechte Spalte: Accordion-Sektionen mit KPICard, Vergleichen (VM/VJ),
 *                Max/Min/Ø-Einordnung, Wasserfall, Komponenten-Detail.
 */

import { useState, useMemo, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Sun, Battery, Flame, Car, Euro,
  ChevronDown, BarChart3, Wrench, Home, Zap, TrendingUp,
  Plug, Gauge, ArrowUpDown, RefreshCw, CalendarClock, Users, Share2,
} from 'lucide-react'
import { Card, LoadingSpinner, Alert, KPICard, FormelTooltip, fmtCalc } from '../components/ui'
import { useSelectedAnlage, useAggregierteDaten } from '../hooks'
import { aktuellerMonatApi, AktuellerMonatResponse } from '../api/aktuellerMonat'
import { cockpitApi } from '../api/cockpit'
import { communityApi, MonatsVergleich } from '../api/community'
import { MONAT_NAMEN } from '../lib/constants'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'


// ─── Helpers ──────────────────────────────────────────────────────────────────
const fmt  = (v: number | null | undefined, d = 1) => fmtCalc(v, d, '—')
const fmtE = (v: number | null | undefined) =>
  v == null ? '—' : `${v >= 0 ? '+' : ''}${fmtCalc(v, 2)} €`

/** Delta-Badge: ▲/▼ % relativ zu Basis */
function Δ({ a, b, inv = false }: { a: number | null | undefined; b: number | null | undefined; inv?: boolean }) {
  if (a == null || b == null || b === 0) return null
  const pct = ((a - b) / Math.abs(b)) * 100
  const positive = inv ? pct <= 0 : pct >= 0
  return (
    <span className={`text-xs font-medium px-1 py-0.5 rounded ${
      positive
        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
        : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
    }`}>
      {pct >= 0 ? '▲' : '▼'} {Math.abs(pct).toFixed(0)} %
    </span>
  )
}


// ─── Vergleichs-Zeile ─────────────────────────────────────────────────────────
function VglZeile({ label, aktuell, vm, vj, unit, inv = false, formel, ergebnis }: {
  label: string
  aktuell: number | null | undefined
  vm?: number | null
  vj?: number | null
  unit: string
  inv?: boolean
  formel?: string
  ergebnis?: string
}) {
  const row = (
    <div className="flex items-center justify-between py-1.5 border-b border-gray-100 dark:border-gray-700/50 last:border-0 gap-2 flex-wrap">
      <span className="text-sm text-gray-600 dark:text-gray-400 shrink-0">{label}</span>
      <div className="flex items-center gap-2 flex-wrap justify-end">
        <span className="text-sm font-semibold text-gray-900 dark:text-white tabular-nums">
          {fmt(aktuell, unit === '€' ? 2 : 0)} {unit}
        </span>
        {vm != null && (
          <span className="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1">
            VM: {fmt(vm, unit === '€' ? 2 : 0)} <Δ a={aktuell} b={vm} inv={inv} />
          </span>
        )}
        {vj != null && (
          <span className="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1">
            VJ: {fmt(vj, unit === '€' ? 2 : 0)} <Δ a={aktuell} b={vj} inv={inv} />
          </span>
        )}
      </div>
    </div>
  )
  if (formel) {
    return (
      <FormelTooltip formel={formel} ergebnis={ergebnis}>{row}</FormelTooltip>
    )
  }
  return row
}

// ─── Accordion ────────────────────────────────────────────────────────────────
function Section({
  icon: Icon, title, summary, children, defaultOpen = false, color = 'text-blue-500',
}: {
  icon: React.ElementType
  title: string
  summary: React.ReactNode
  children: React.ReactNode
  defaultOpen?: boolean
  color?: string
}) {
  const storageKey = `monatsberichte_section_${title}`
  const [open, setOpen] = useState(() => {
    try {
      const stored = localStorage.getItem(storageKey)
      return stored !== null ? stored === 'true' : defaultOpen
    } catch {
      return defaultOpen
    }
  })

  const toggle = () => {
    setOpen(o => {
      const next = !o
      try { localStorage.setItem(storageKey, String(next)) } catch {}
      return next
    })
  }
  return (
    <Card className="!p-0">
      <button
        type="button"
        onClick={toggle}
        className="w-full flex items-center gap-3 px-4 py-3.5 text-left rounded-xl hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
      >
        <Icon className={`h-5 w-5 shrink-0 ${color}`} />
        <span className="font-semibold text-gray-900 dark:text-white text-sm">{title}</span>
        <span className="ml-2 text-sm text-gray-500 dark:text-gray-400 flex-1 min-w-0 truncate">{summary}</span>
        <ChevronDown className={`h-4 w-4 text-gray-400 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="px-4 pb-5 pt-2 border-t border-gray-100 dark:border-gray-700">
          {children}
        </div>
      )}
    </Card>
  )
}

// ─── Typen ────────────────────────────────────────────────────────────────────
type TimelineEntry = { jahr: number; monat: number; pv_kwh: number; autarkie: number; laufend?: boolean }

// ─── Vertikaler Zeitstrahl ────────────────────────────────────────────────────
function VerticalTimeline({ entries, selectedJahr, selectedMonat, onSelect }: {
  entries: TimelineEntry[]
  selectedJahr: number
  selectedMonat: number
  onSelect: (j: number, m: number) => void
}) {
  const selectedRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selectedJahr, selectedMonat])

  const byJahr = useMemo(() => {
    const map = new Map<number, typeof entries>()
    const sorted = [...entries].sort((a, b) =>
      b.jahr !== a.jahr ? b.jahr - a.jahr : b.monat - a.monat)
    sorted.forEach(e => {
      if (!map.has(e.jahr)) map.set(e.jahr, [])
      map.get(e.jahr)!.push(e)
    })
    return map
  }, [entries])

  // Max PV pro Jahr für relative Balken
  const maxPvByJahr = useMemo(() => {
    const m = new Map<number, number>()
    byJahr.forEach((es, j) => m.set(j, Math.max(...es.map(e => e.pv_kwh), 1)))
    return m
  }, [byJahr])

  const jahre = [...byJahr.keys()].sort((a, b) => b - a)

  return (
    <div className="space-y-3">
      {jahre.map(jahr => (
        <div key={jahr}>
          <div className="flex items-center gap-2 mb-1 px-1">
            <div className="h-px flex-1 bg-gray-200 dark:bg-gray-700" />
            <span className="text-xs font-bold text-gray-400 dark:text-gray-500 uppercase tracking-wider">{jahr}</span>
            <div className="h-px flex-1 bg-gray-200 dark:bg-gray-700" />
          </div>
          <div className="relative ml-3">
            <div className="absolute left-[6px] top-3 bottom-0 w-px bg-gray-200 dark:bg-gray-700" />
            {byJahr.get(jahr)!.map(e => {
              const isSel = e.jahr === selectedJahr && e.monat === selectedMonat
              const maxPv = maxPvByJahr.get(jahr) ?? 1
              const barW = Math.max(6, Math.round((e.pv_kwh / maxPv) * 100))
              return (
                <button
                  key={e.monat}
                  ref={isSel ? selectedRef : null}
                  type="button"
                  onClick={() => onSelect(e.jahr, e.monat)}
                  title={e.laufend
                    ? `${MONAT_NAMEN[e.monat]} ${e.jahr} — laufender Monat`
                    : `${MONAT_NAMEN[e.monat]} ${e.jahr}: ${Math.round(e.pv_kwh)} kWh · ${Math.round(e.autarkie)} % Autarkie`}
                  className={`relative flex items-start gap-2 w-full text-left py-1.5 pr-1 rounded-lg transition-colors group ${
                    isSel ? 'text-blue-700 dark:text-blue-300' : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                  }`}
                >
                  <span className={`relative z-10 mt-1 h-3 w-3 rounded-full border-2 shrink-0 transition-all ${
                    e.laufend
                      ? isSel
                        ? 'bg-emerald-500 border-emerald-500 animate-pulse'
                        : 'bg-emerald-400 border-emerald-500 animate-pulse group-hover:border-emerald-400'
                      : isSel
                        ? 'bg-blue-600 border-blue-600 shadow shadow-blue-400/50'
                        : 'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600 group-hover:border-blue-400'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline justify-between gap-1">
                      <span className={`text-sm font-medium ${isSel ? 'text-blue-700 dark:text-blue-300' : ''}`}>
                        {MONAT_NAMEN[e.monat].substring(0, 3)}
                      </span>
                      <span className={`text-xs tabular-nums ${
                        e.laufend ? 'text-emerald-500 dark:text-emerald-400' : isSel ? 'text-blue-500 dark:text-blue-400' : 'text-gray-400'
                      }`}>
                        {e.laufend ? 'läuft' : `${Math.round(e.pv_kwh)} kWh`}
                      </span>
                    </div>
                    {!e.laufend && (
                      <svg className="mt-0.5 w-full h-1" aria-hidden="true">
                        <rect width="100%" height="4" rx="2" className="fill-gray-100 dark:fill-gray-700" />
                        <rect width={`${barW}%`} height="4" rx="2" className={isSel ? 'fill-blue-500' : 'fill-yellow-400 dark:fill-yellow-500'} />
                      </svg>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Hauptkomponente ──────────────────────────────────────────────────────────
export default function MonatsabschlussView() {
  const navigate = useNavigate()
  const { anlagen, selectedAnlageId, setSelectedAnlageId, selectedAnlage, loading: anlagenLoading } = useSelectedAnlage()
  const { daten: alleMonate, loading: monateLoading } = useAggregierteDaten(selectedAnlageId)

  const heute = useMemo(() => new Date(), [])
  const heuteJahr  = heute.getFullYear()
  const heuteMonat = heute.getMonth() + 1

  const timelineEntries = useMemo((): TimelineEntry[] => {
    const completed: TimelineEntry[] = alleMonate.map(m => ({
      jahr: m.jahr, monat: m.monat,
      pv_kwh: m.pv_erzeugung_kwh ?? 0,
      autarkie: m.autarkie_prozent ?? 0,
    }))
    // Aktuellen Monat einfügen wenn noch nicht abgeschlossen
    const istAbgeschlossen = completed.some(m => m.jahr === heuteJahr && m.monat === heuteMonat)
    if (!istAbgeschlossen) {
      completed.unshift({ jahr: heuteJahr, monat: heuteMonat, pv_kwh: 0, autarkie: 0, laufend: true })
    }
    return completed
  }, [alleMonate, heuteJahr, heuteMonat])

  const defaultEntry = useMemo(() =>
    // Aktueller Monat ist immer der sinnvollste Einstieg
    timelineEntries.find(e => e.laufend)
    ?? [...timelineEntries].sort((a, b) => b.jahr !== a.jahr ? b.jahr - a.jahr : b.monat - a.monat)[0]
    ?? null,
    [timelineEntries]
  )

  const [selectedJahr, setSelectedJahr] = useState<number | null>(null)
  const [selectedMonat, setSelectedMonat] = useState<number | null>(null)

  useEffect(() => {
    if (defaultEntry && selectedJahr === null) {
      setSelectedJahr(defaultEntry.jahr)
      setSelectedMonat(defaultEntry.monat)
    }
  }, [defaultEntry, selectedJahr])

  const handleSelect = useCallback((j: number, m: number) => {
    setSelectedJahr(j); setSelectedMonat(m)
  }, [])

  // Vormonat aus alleMonate
  const vormonatAgg = useMemo((): AggregierteMonatsdaten | null => {
    if (selectedJahr === null || selectedMonat === null) return null
    const vm = selectedMonat === 1 ? { jahr: selectedJahr - 1, monat: 12 } : { jahr: selectedJahr, monat: selectedMonat - 1 }
    return alleMonate.find(m => m.jahr === vm.jahr && m.monat === vm.monat) ?? null
  }, [alleMonate, selectedJahr, selectedMonat])

  // Ø gleicher Monat (z.B. alle März-Monate außer dem aktuell gewählten Jahr)
  const glMonStats = useMemo(() => {
    if (selectedMonat === null) return null
    const monate = alleMonate.filter(m => m.monat === selectedMonat && m.jahr !== selectedJahr)
    if (monate.length === 0) return null
    const avg = (vals: number[]) => vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : null
    return {
      pv:       avg(monate.map(m => m.pv_erzeugung_kwh).filter((v): v is number => v != null && v > 0)),
      ev:       avg(monate.map(m => m.eigenverbrauch_kwh).filter((v): v is number => v != null && v > 0)),
      einsp:    avg(monate.map(m => m.einspeisung_kwh).filter((v): v is number => v != null && v > 0)),
      netz:     avg(monate.map(m => m.netzbezug_kwh).filter((v): v is number => v != null && v > 0)),
      gesamt:   avg(monate.map(m => m.gesamtverbrauch_kwh).filter((v): v is number => v != null && v > 0)),
      autarkie: avg(monate.map(m => m.autarkie_prozent).filter((v): v is number => v != null && v > 0)),
      count: monate.length,
    }
  }, [alleMonate, selectedMonat, selectedJahr])

  // Live-Monatsdaten
  const [monatData, setMonatData] = useState<AktuellerMonatResponse | null>(null)
  const [monatLoading, setMonatLoading] = useState(false)
  const [monatError, setMonatError] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedAnlageId || selectedJahr === null || selectedMonat === null) return
    setMonatLoading(true); setMonatError(null)
    aktuellerMonatApi.getData(selectedAnlageId, selectedJahr, selectedMonat)
      .then(setMonatData)
      .catch(e => setMonatError(e.message || 'Fehler'))
      .finally(() => setMonatLoading(false))
  }, [selectedAnlageId, selectedJahr, selectedMonat])

  // Sonderkosten
  const [sonderkosten, setSonderkosten] = useState<number | null>(null)
  useEffect(() => {
    if (!selectedAnlageId || selectedJahr === null || selectedMonat === null) return
    cockpitApi.getKomponentenZeitreihe(selectedAnlageId, selectedJahr)
      .then(kt => setSonderkosten(kt.monatswerte?.find(v => v.monat === selectedMonat)?.sonstige_ausgaben_euro ?? null))
      .catch(() => setSonderkosten(null))
  }, [selectedAnlageId, selectedJahr, selectedMonat])


  const nettoNachAllem = useMemo(() => {
    if (!monatData?.gesamtnettoertrag_euro) return null
    return monatData.gesamtnettoertrag_euro - (monatData.betriebskosten_anteilig_euro || 0) - (sonderkosten || 0)
  }, [monatData, sonderkosten])

  // Community-Monats-Benchmark
  const [monatsVergleich, setMonatsVergleich] = useState<MonatsVergleich | null>(null)
  useEffect(() => {
    if (selectedJahr === null || selectedMonat === null) return
    setMonatsVergleich(null)
    communityApi.getMonatsBenchmark(selectedJahr, selectedMonat)
      .then(setMonatsVergleich)
      .catch(() => setMonatsVergleich(null)) // still, kein Fehler-Block nötig
  }, [selectedJahr, selectedMonat])

  // "Abschluss starten" nur wenn Vergangenheits-Monate noch offen sind
  const hatOffeneAbschluesse = useMemo(() => {
    const vormonat = heuteMonat === 1
      ? { jahr: heuteJahr - 1, monat: 12 }
      : { jahr: heuteJahr,     monat: heuteMonat - 1 }
    if (alleMonate.length === 0) return true
    const sorted = [...alleMonate].sort((a, b) => b.jahr !== a.jahr ? b.jahr - a.jahr : b.monat - a.monat)
    const letzter = sorted[0]
    return letzter.jahr < vormonat.jahr
      || (letzter.jahr === vormonat.jahr && letzter.monat < vormonat.monat)
  }, [alleMonate, heuteJahr, heuteMonat])

  // ── Guards ──────────────────────────────────────────────────────────────────
  if (anlagenLoading || monateLoading) return <LoadingSpinner text="Lade Monatsberichte…" />
  if (anlagen.length === 0) return <Alert type="warning">Bitte lege zuerst eine PV-Anlage an.</Alert>
  if (timelineEntries.length === 0) return (
    <Card className="text-center py-12">
      <BarChart3 className="h-12 w-12 mx-auto text-gray-400 mb-4" />
      <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">Keine Monatsdaten</h3>
      <p className="text-gray-500 dark:text-gray-400 mb-4">Bitte wähle eine Anlage mit konfigurierten Sensoren.</p>
    </Card>
  )

  const d = monatData
  const vj = d?.vorjahr
  const vm = vormonatAgg
  const isLaufend = selectedJahr === heuteJahr && selectedMonat === heuteMonat
    && !alleMonate.some(m => m.jahr === heuteJahr && m.monat === heuteMonat)
  const titel = selectedJahr && selectedMonat ? `${MONAT_NAMEN[selectedMonat]} ${selectedJahr}` : '…'

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col lg:flex-row gap-6 min-h-0">

      {/* Zeitstrahl Desktop */}
      <aside className="hidden lg:block w-48 shrink-0 self-start sticky top-4">
        <div>
          {anlagen.length > 1 && (
            <div className="mb-3">
              <select aria-label="Anlage" value={selectedAnlageId?.toString() || ''}
                onChange={e => setSelectedAnlageId(parseInt(e.target.value))}
                className="input w-full text-xs py-1.5">
                {anlagen.map(a => <option key={a.id} value={a.id}>{a.anlagenname}</option>)}
              </select>
            </div>
          )}
          <div className="overflow-y-auto max-h-[calc(100vh-6rem)] scrollbar-none">
            {selectedJahr !== null && selectedMonat !== null && (
              <VerticalTimeline
                entries={timelineEntries}
                selectedJahr={selectedJahr}
                selectedMonat={selectedMonat}
                onSelect={handleSelect}
              />
            )}
          </div>
        </div>
      </aside>

      {/* Hauptinhalt */}
      <main className="flex-1 min-w-0 space-y-4">

        {/* Mobil: horizontaler Selektor */}
        <div className="lg:hidden -mx-3 sm:-mx-6 px-3 sm:px-6 overflow-x-auto scrollbar-none">
          <div className="flex gap-1.5 pb-1">
            {[...timelineEntries]
              .sort((a, b) => b.jahr !== a.jahr ? b.jahr - a.jahr : b.monat - a.monat)
              .map(e => {
                const isSel = e.jahr === selectedJahr && e.monat === selectedMonat
                return (
                  <button key={`${e.jahr}-${e.monat}`} type="button" onClick={() => handleSelect(e.jahr, e.monat)}
                    className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
                      isSel
                        ? 'bg-blue-600 text-white'
                        : e.laufend
                          ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400'
                          : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                    }`}>
                    {MONAT_NAMEN[e.monat].substring(0, 3)} {e.jahr}
                    {e.laufend && <span className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse align-middle" />}
                  </button>
                )
              })}
          </div>
        </div>

        {/* Titel */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">{titel}</h2>
            {isLaufend && (
              <span className="flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                laufend
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {isLaufend && (
              <>
                <button
                  type="button"
                  onClick={() => {
                    if (!selectedAnlageId || selectedJahr === null || selectedMonat === null) return
                    setMonatLoading(true); setMonatError(null)
                    aktuellerMonatApi.getData(selectedAnlageId, selectedJahr, selectedMonat)
                      .then(setMonatData).catch(e => setMonatError(e.message || 'Fehler')).finally(() => setMonatLoading(false))
                  }}
                  disabled={monatLoading}
                  className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${monatLoading ? 'animate-spin' : ''}`} />
                  Aktualisieren
                </button>
                {hatOffeneAbschluesse && (
                  <button
                    type="button"
                    onClick={() => navigate('/einstellungen/monatsabschluss')}
                    className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
                  >
                    <CalendarClock className="h-3.5 w-3.5" />
                    Abschluss starten
                  </button>
                )}
              </>
            )}
            {d && Object.entries(d.quellen).filter(([, v]) => v).map(([k]) => (
              <span key={k} className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">
                {k === 'ha_statistics' ? 'HA-Statistik' : k === 'connector' ? 'Connector' : k === 'gespeichert' ? 'Gespeichert' : k}
              </span>
            ))}
          </div>
        </div>

        {monatLoading && <LoadingSpinner text="Lade Monatsdaten…" />}
        {monatError   && <Alert type="error">{monatError}</Alert>}

        {d && !monatLoading && (
          <div className="space-y-3">

            {/* ════ SEKTION 1: Energie-Bilanz ════════════════════════════ */}
            <Section icon={Sun} color="text-yellow-500" title="Energie-Bilanz" defaultOpen
              summary={
                <span className="flex items-center gap-3">
                  {d.pv_erzeugung_kwh != null && <span className="font-medium text-gray-700 dark:text-gray-300">{fmt(d.pv_erzeugung_kwh, 0)} kWh PV</span>}
                  {d.autarkie_prozent != null && <span className="text-green-600 dark:text-green-400 font-medium">{fmt(d.autarkie_prozent, 0)} % Autarkie</span>}
                  {d.soll_pv_kwh != null && d.pv_erzeugung_kwh != null && (
                    <span className="text-gray-400 text-xs">SOLL {Math.round(d.pv_erzeugung_kwh / d.soll_pv_kwh * 100)} %</span>
                  )}
                </span>
              }
            >
              {/* KPI-Zeile */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mt-2">
                <KPICard title="PV-Erzeugung" value={fmt(d.pv_erzeugung_kwh, 0)} unit="kWh" icon={Sun} color="yellow"
                  subtitle={d.soll_pv_kwh != null && d.pv_erzeugung_kwh != null
                    ? `SOLL ${fmt(d.soll_pv_kwh, 0)} kWh · ${Math.round(d.pv_erzeugung_kwh / d.soll_pv_kwh * 100)} %`
                    : vm ? `VM: ${fmt(vm.pv_erzeugung_kwh, 0)} kWh` : undefined} />
                <KPICard title="Autarkie" value={fmt(d.autarkie_prozent, 0)} unit="%" icon={Home} color="green"
                  subtitle={vm ? `VM: ${fmt(vm.autarkie_prozent, 0)} %` : undefined}
                  formel="Eigenverbrauch ÷ Gesamtverbrauch × 100"
                  berechnung={d.eigenverbrauch_kwh != null && d.gesamtverbrauch_kwh != null ? `${fmt(d.eigenverbrauch_kwh, 0)} ÷ ${fmt(d.gesamtverbrauch_kwh, 0)} kWh` : undefined}
                  ergebnis={d.autarkie_prozent != null ? `= ${fmtCalc(d.autarkie_prozent, 1)} %` : undefined} />
                <KPICard title="Eigenverbrauch" value={fmt(d.eigenverbrauch_kwh, 0)} unit="kWh" icon={Home} color="purple"
                  subtitle={`EV-Quote ${fmt(d.eigenverbrauch_quote_prozent, 0)} %${vm ? ` · VM: ${fmt(vm.eigenverbrauch_kwh, 0)} kWh` : ''}`}
                  formel="PV-Direktverbrauch + Speicher-Entladung" />
                <KPICard title="Einspeisung" value={fmt(d.einspeisung_kwh, 0)} unit="kWh" icon={TrendingUp} color="green"
                  subtitle={vm ? `VM: ${fmt(vm.einspeisung_kwh, 0)} kWh` : undefined} />
                <KPICard title="Netzbezug" value={fmt(d.netzbezug_kwh, 0)} unit="kWh" icon={Zap} color="red"
                  subtitle={vm ? `VM: ${fmt(vm.netzbezug_kwh, 0)} kWh` : undefined} />
              </div>

              <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-4">

                {/* Vergleichstabelle (2/3 Breite) */}
                <div className="lg:col-span-2">
                  {(() => {
                    const rows: Array<{
                      label: string
                      ist: number | null | undefined
                      vmV: number | null | undefined
                      vjV: number | null | undefined
                      gm: number | null | undefined
                      unit: string
                      inv?: boolean
                    }> = [
                      { label: 'PV-Erzeugung',    ist: d.pv_erzeugung_kwh,   vmV: vm?.pv_erzeugung_kwh,   vjV: vj?.pv_erzeugung_kwh,   gm: glMonStats?.pv,       unit: 'kWh' },
                      { label: 'Eigenverbrauch',  ist: d.eigenverbrauch_kwh,  vmV: vm?.eigenverbrauch_kwh, vjV: vj?.eigenverbrauch_kwh, gm: glMonStats?.ev,       unit: 'kWh' },
                      { label: 'Einspeisung',     ist: d.einspeisung_kwh,     vmV: vm?.einspeisung_kwh,    vjV: vj?.einspeisung_kwh,    gm: glMonStats?.einsp,    unit: 'kWh' },
                      { label: 'Netzbezug',       ist: d.netzbezug_kwh,       vmV: vm?.netzbezug_kwh,      vjV: vj?.netzbezug_kwh,      gm: glMonStats?.netz,     unit: 'kWh', inv: true },
                      { label: 'Gesamtverbrauch', ist: d.gesamtverbrauch_kwh, vmV: vm?.gesamtverbrauch_kwh, vjV: null,                   gm: glMonStats?.gesamt,   unit: 'kWh' },
                      { label: 'Autarkie',        ist: d.autarkie_prozent,    vmV: vm?.autarkie_prozent,   vjV: vj?.autarkie_prozent,   gm: glMonStats?.autarkie, unit: '%'   },
                    ]
                    const cell = (val: number | null | undefined, row: typeof rows[0]) =>
                      val != null
                        ? <span
                            className="flex items-center justify-end gap-1"
                            title={`${fmt(val, row.unit === '%' ? 1 : 0)} ${row.unit}`}
                          >
                            <span className="hidden sm:inline text-gray-400 dark:text-gray-500">{fmt(val, row.unit === '%' ? 1 : 0)}</span>
                            <Δ a={row.ist} b={val} inv={row.inv} />
                          </span>
                        : <span className="text-gray-300 dark:text-gray-600">—</span>
                    return (
                      <>
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-700">
                              <th className="text-left pb-1.5 font-medium" scope="col"><span className="sr-only">Kennzahl</span></th>
                              <th className="text-right pb-1.5 font-medium">IST</th>
                              <th className="text-right pb-1.5 font-medium">Vormonat</th>
                              <th className="text-right pb-1.5 font-medium">Vorjahr</th>
                              {glMonStats && <th className="text-right pb-1.5 font-medium">Ø {MONAT_NAMEN[selectedMonat!]}</th>}
                            </tr>
                          </thead>
                          <tbody>
                            {rows.map(row => (
                              <tr key={row.label} className="border-b border-gray-100 dark:border-gray-700/50 last:border-0">
                                <td className="py-1.5 text-gray-600 dark:text-gray-400">{row.label}</td>
                                <td className="py-1.5 text-right font-semibold text-gray-900 dark:text-white tabular-nums">
                                  {fmt(row.ist, row.unit === '%' ? 1 : 0)} {row.unit}
                                </td>
                                <td className="py-1.5 text-right tabular-nums">{cell(row.vmV, row)}</td>
                                <td className="py-1.5 text-right tabular-nums">{cell(row.vjV, row)}</td>
                                {glMonStats && <td className="py-1.5 text-right tabular-nums">{cell(row.gm, row)}</td>}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {glMonStats && (
                          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
                            Ø aus {glMonStats.count} {MONAT_NAMEN[selectedMonat!]}-Monat{glMonStats.count !== 1 ? 'en' : ''}
                          </p>
                        )}
                      </>
                    )
                  })()}
                </div>

                {/* SOLL/IST + PV-Verteilung (1/3 Breite) */}
                <div className="space-y-5">

                  {/* SOLL/IST */}
                  {d.soll_pv_kwh != null && d.pv_erzeugung_kwh != null && (() => {
                    const pct = Math.round(d.pv_erzeugung_kwh! / d.soll_pv_kwh! * 100)
                    const colorText = pct >= 100 ? 'text-green-500 dark:text-green-400' : pct >= 75 ? 'text-yellow-500 dark:text-yellow-400' : 'text-orange-500'
                    const colorBar  = pct >= 100 ? 'bg-green-500' : pct >= 75 ? 'bg-yellow-400' : 'bg-orange-400'
                    return (
                      <div>
                        <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">SOLL/IST (PVGIS)</p>
                        <div className="flex justify-end">
                          <FormelTooltip
                            formel="IST ÷ SOLL × 100"
                            berechnung={`${fmt(d.pv_erzeugung_kwh, 0)} ÷ ${fmt(d.soll_pv_kwh, 0)} kWh`}
                            ergebnis={`= ${pct} %`}
                          >
                            <span className={`text-4xl font-bold ${colorText}`}>{pct} %</span>
                          </FormelTooltip>
                        </div>
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mt-2">
                          <div className={`h-2 rounded-full ${colorBar}`} style={{ width: `${Math.min(100, pct)}%` }} />
                        </div>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5">
                          {fmt(d.pv_erzeugung_kwh, 0)} von {fmt(d.soll_pv_kwh, 0)} kWh
                        </p>
                      </div>
                    )
                  })()}

                  {/* PV-Verteilung */}
                  {d.eigenverbrauch_kwh != null && d.einspeisung_kwh != null && d.pv_erzeugung_kwh != null && d.pv_erzeugung_kwh > 0 && (() => {
                    const total = d.pv_erzeugung_kwh!
                    const evPct    = Math.round(d.eigenverbrauch_kwh! / total * 100)
                    const einspPct = Math.round(d.einspeisung_kwh!    / total * 100)
                    return (
                      <div>
                        <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">PV-Verteilung</p>
                        <div className="space-y-2.5">
                          {([
                            { label: 'Eigenverbr.',  pct: evPct,    color: 'bg-purple-500' },
                            { label: 'Einspeisung',  pct: einspPct, color: 'bg-emerald-500' },
                          ]).map(({ label, pct: p, color }) => (
                            <div key={label} className="flex items-center gap-2 text-xs">
                              <span className="w-20 text-gray-600 dark:text-gray-400 shrink-0">{label}</span>
                              <div className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                                <div className={`h-2 rounded-full ${color}`} style={{ width: `${p}%` }} />
                              </div>
                              <span className="w-8 text-right text-gray-700 dark:text-gray-300 font-medium tabular-nums">{p} %</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })()}

                </div>
              </div>
            </Section>

            {/* ════ SEKTION 2: Finanzen ══════════════════════════════════ */}
            {d.einspeise_erloes_euro != null && (
              <Section icon={Euro} color="text-green-500" title="Finanzen" defaultOpen
                summary={
                  <span className="flex items-center gap-3">
                    {nettoNachAllem != null && (
                      <span className={`font-semibold ${nettoNachAllem >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                        {fmtE(nettoNachAllem)} Monatsergebnis
                      </span>
                    )}
                    {d.netzbezug_durchschnittspreis_cent != null && (
                      <span className="text-xs text-blue-500 dark:text-blue-400">Ø {fmtCalc(d.netzbezug_durchschnittspreis_cent, 2)} ct/kWh flex</span>
                    )}
                  </span>
                }
              >
                {/* ── T-Konto ───────────────────────────────────────────── */}
                {(() => {
                  const netzPreis = d.netzbezug_durchschnittspreis_cent ?? d.netzbezug_preis_cent

                  // ── T-Konto Datenstruktur ──────────────────────────────
                  type TKontoPosten = {
                    label: string
                    wert: number
                    vjWert?: number | null
                    formel?: string
                    berechnung?: string
                    ergebnis?: string
                    color: string
                  }

                  // Farbe je Investitionstyp
                  const typColor = (typ: string) => {
                    switch (typ) {
                      case 'balkonkraftwerk': return 'text-blue-500 dark:text-blue-300'
                      case 'speicher':        return 'text-blue-600 dark:text-blue-400'
                      case 'waermepumpe':     return 'text-orange-500'
                      case 'e-auto':
                      case 'wallbox':         return 'text-purple-500'
                      case 'sonstiges':       return 'text-teal-600 dark:text-teal-400'
                      default:                return 'text-blue-600 dark:text-blue-400'
                    }
                  }

                  const fins = d.investitionen_financials ?? []
                  const hasPerInv = fins.length > 0

                  // Welche Komponenten-Ersparnisse stecken in ev_ersparnis (BKW + Speicher)
                  const evInErsparnis = hasPerInv
                    ? fins
                        .filter(inv => inv.typ === 'balkonkraftwerk' || inv.typ === 'speicher')
                        .reduce((s, inv) => s + (inv.ersparnis_euro ?? 0), 0)
                    : 0
                  const pvEvResidual = Math.max(0, (d.ev_ersparnis_euro ?? 0) - evInErsparnis)

                  const preisBez = d.netzbezug_durchschnittspreis_cent != null ? 'Ø-Preis flex' : 'Netzbezugspreis'

                  const habenPosten: TKontoPosten[] = [
                    // ── Einspeise-Erlöse (immer) ──
                    {
                      label: 'Einspeise-Erlöse',
                      wert: d.einspeise_erloes_euro ?? 0,
                      vjWert: vj?.einspeise_erloes_euro,
                      color: 'text-green-600 dark:text-green-400',
                      formel: 'Einspeisung × Einspeisevergütung',
                      berechnung: d.einspeisung_kwh != null && d.einspeise_preis_cent != null
                        ? `${fmt(d.einspeisung_kwh, 1)} kWh × ${fmtCalc(d.einspeise_preis_cent, 2)} ct/kWh`
                        : undefined,
                      ergebnis: `= ${fmtCalc(d.einspeise_erloes_euro, 2)} €`,
                    },
                    // ── PV-Eigenverbrauch ──
                    // Mit per-Inv-Daten: Residual (ohne BKW/Speicher die separat gezeigt werden)
                    // Ohne per-Inv-Daten: Gesamtwert inkl. VJ-Vergleich
                    ...(hasPerInv && pvEvResidual > 0 ? [{
                      label: 'PV-Eigenverbrauch-Ersparnis',
                      wert: pvEvResidual,
                      vjWert: undefined as number | null | undefined,
                      color: 'text-blue-600 dark:text-blue-400',
                      formel: `PV-Eigenverbrauch × ${preisBez}`,
                      berechnung: d.eigenverbrauch_kwh != null && netzPreis != null
                        ? `${fmt(d.eigenverbrauch_kwh - evInErsparnis / (netzPreis / 100), 1)} kWh × ${fmtCalc(netzPreis, 2)} ct/kWh`
                        : undefined,
                      ergebnis: `= ${fmtCalc(pvEvResidual, 2)} €`,
                    } as TKontoPosten] : !hasPerInv ? [{
                      label: 'Eigenverbrauch-Ersparnis',
                      wert: d.ev_ersparnis_euro ?? 0,
                      vjWert: vj?.ev_ersparnis_euro,
                      color: 'text-blue-600 dark:text-blue-400',
                      formel: `Eigenverbrauch × ${preisBez}`,
                      berechnung: d.eigenverbrauch_kwh != null && netzPreis != null
                        ? `${fmt(d.eigenverbrauch_kwh, 1)} kWh × ${fmtCalc(netzPreis, 2)} ct/kWh`
                        : undefined,
                      ergebnis: `= ${fmtCalc(d.ev_ersparnis_euro, 2)} €`,
                    } as TKontoPosten] : []),
                    // ── Per-Investition: BKW, Speicher, WP, eMob, Sonstiges ──
                    ...fins.flatMap((inv): TKontoPosten[] => {
                      const rows: TKontoPosten[] = []
                      if (inv.erloes_euro != null && inv.erloes_euro > 0) {
                        rows.push({
                          label: `${inv.bezeichnung} — Einspeisung`,
                          wert: inv.erloes_euro,
                          color: 'text-green-600 dark:text-green-400',
                          formel: 'Einspeisung × Einspeisevergütung',
                          ergebnis: `= ${fmtCalc(inv.erloes_euro, 2)} €`,
                        })
                      }
                      if (inv.ersparnis_euro != null) {
                        rows.push({
                          label: `${inv.bezeichnung} — ${inv.ersparnis_label || 'Ersparnis'}`,
                          wert: inv.ersparnis_euro,
                          color: typColor(inv.typ),
                          formel: inv.formel ?? undefined,
                          berechnung: inv.berechnung ?? undefined,
                          ergebnis: `= ${fmtCalc(inv.ersparnis_euro, 2)} €`,
                        })
                      }
                      return rows
                    }),
                    // ── Fallback: WP/eMob-Aggregate wenn kein per-Inv-Daten ──
                    ...(!hasPerInv && d.wp_ersparnis_euro != null ? [{
                      label: 'WP-Ersparnis vs. Gas',
                      wert: d.wp_ersparnis_euro,
                      color: 'text-orange-500',
                      formel: '(Wärme ÷ 0,9 × Gaspreis) − Strom × WP-Strompreis',
                      berechnung: d.wp_waerme_kwh != null && d.wp_strom_kwh != null
                        ? `${fmt(d.wp_waerme_kwh, 1)} kWh / 0,9 × 10 ct − ${fmt(d.wp_strom_kwh, 1)} kWh × ${fmtCalc(netzPreis, 2)} ct`
                        : undefined,
                      ergebnis: `= ${fmtCalc(d.wp_ersparnis_euro, 2)} €`,
                    } as TKontoPosten] : []),
                    ...(!hasPerInv && d.emob_ersparnis_euro != null ? [{
                      label: 'eMob-Ersparnis vs. Verbrenner',
                      wert: d.emob_ersparnis_euro,
                      color: 'text-purple-500',
                      formel: '(km × 7 L/100km × 1,80 €/L) − Netzladung × Strompreis',
                      berechnung: d.emob_km != null ? [
                        `${fmt(d.emob_km, 0)} km × 7/100 × 1,80 €`,
                        d.emob_ladung_netz_kwh != null
                          ? `− ${fmt(d.emob_ladung_netz_kwh, 1)} kWh Netz × ${fmtCalc(netzPreis, 2)} ct`
                          : `− ${fmt(d.emob_ladung_kwh, 1)} kWh × ${fmtCalc(netzPreis, 2)} ct`,
                        d.emob_ladung_pv_kwh != null ? `(PV ${fmt(d.emob_ladung_pv_kwh, 1)} kWh kostenlos)` : null,
                      ].filter(Boolean).join('\n') : undefined,
                      ergebnis: `= ${fmtCalc(d.emob_ersparnis_euro, 2)} €`,
                    } as TKontoPosten] : []),
                  ]

                  const sollPosten: TKontoPosten[] = [
                    {
                      label: 'Netzbezug-Kosten',
                      wert: d.netzbezug_kosten_euro ?? 0,
                      vjWert: vj?.netzbezug_kosten_euro,
                      color: 'text-red-500',
                      formel: 'Netzbezug × Arbeitspreis + Grundpreis',
                      berechnung: d.netzbezug_kwh != null && netzPreis != null ? [
                        `${fmt(d.netzbezug_kwh, 1)} kWh × ${fmtCalc(netzPreis, 2)} ct/kWh + Grundpreis`,
                        d.netzbezug_durchschnittspreis_cent != null ? '(flex. Tarif, Monatsdurchschnitt)' : null,
                      ].filter(Boolean).join('\n') : undefined,
                      ergebnis: `= ${fmtCalc(d.netzbezug_kosten_euro, 2)} €`,
                    },
                    // ── Betriebskosten: per Investition wenn Daten da, sonst Aggregat ──
                    ...(hasPerInv
                      ? fins
                          .filter(inv => inv.betriebskosten_monat_euro > 0)
                          .map(inv => ({
                            label: `${inv.bezeichnung} — Betriebskosten`,
                            wert: inv.betriebskosten_monat_euro,
                            color: 'text-amber-600',
                            formel: 'Betriebskosten/Jahr ÷ 12',
                            ergebnis: `= ${fmtCalc(inv.betriebskosten_monat_euro, 2)} €`,
                          } as TKontoPosten))
                      : (d.betriebskosten_anteilig_euro ?? 0) > 0 ? [{
                          label: 'Betriebskosten (anteilig)',
                          wert: d.betriebskosten_anteilig_euro!,
                          color: 'text-amber-600',
                          formel: 'Σ (Betriebskosten/Jahr ÷ 12) aller aktiven Investitionen',
                          ergebnis: `= ${fmtCalc(d.betriebskosten_anteilig_euro, 2)} €`,
                        } as TKontoPosten] : []
                    ),
                    ...((sonderkosten ?? 0) > 0 ? [{
                      label: 'Sonderkosten',
                      wert: sonderkosten!,
                      color: 'text-red-500',
                    } as TKontoPosten] : []),
                  ]

                  // Summen aus tatsächlich angezeigten Zeilen berechnen
                  const rawSoll  = sollPosten.reduce((s, p) => s + p.wert, 0)
                  const rawHaben = habenPosten.reduce((s, p) => s + p.wert, 0)
                  const nettoT   = rawHaben - rawSoll   // T-Konto-Gewinn aus Zeilen
                  const gewinnSeite = nettoT >= 0 ? 'soll' : 'haben'
                  const sumSoll  = rawSoll  + Math.max(0,  nettoT)
                  const sumHaben = rawHaben + Math.max(0, -nettoT)



                  // VJ-Summen
                  const vjSumSoll  = vj?.netzbezug_kosten_euro != null ? (vj.netzbezug_kosten_euro + Math.max(0, vj.gesamtnettoertrag_euro ?? 0)) : null
                  const vjSumHaben = vj?.einspeise_erloes_euro != null ? ((vj.einspeise_erloes_euro ?? 0) + (vj.ev_ersparnis_euro ?? 0) + Math.max(0, -(vj.gesamtnettoertrag_euro ?? 0))) : null

                  return (
                    <div className="mt-3">
                      <div className="rounded-xl border border-gray-200 dark:border-gray-700">

                        {/* Eine einzige Tabelle: 9 Spalten = 4 SOLL + 1 Trennlinie + 4 HABEN */}
                        {(() => {
                          const maxRows = Math.max(
                            sollPosten.length + 1 + (gewinnSeite === 'soll' ? 1 : 0),
                            habenPosten.length + 1 + (gewinnSeite === 'haben' ? 1 : 0),
                          )
                          // SOLL-Zeilen: Posten + Leerzeile + ggf. Gewinn
                          const sollRows: (TKontoPosten | null | 'empty' | 'ergebnis')[] = [
                            ...sollPosten,
                            'empty',
                            ...(gewinnSeite === 'soll' ? ['ergebnis' as const] : []),
                          ]
                          const habenRows: (TKontoPosten | null | 'empty' | 'ergebnis')[] = [
                            ...habenPosten,
                            'empty',
                            ...(gewinnSeite === 'haben' ? ['ergebnis' as const] : []),
                          ]
                          // Auf gleiche Länge auffüllen
                          while (sollRows.length < maxRows) sollRows.push(null)
                          while (habenRows.length < maxRows) habenRows.push(null)

                          const tdDiv = 'w-0 p-0 border-l border-gray-200 dark:border-gray-700'

                          const renderCell = (item: TKontoPosten | null | 'empty' | 'ergebnis', seite: 'soll' | 'haben') => {
                            if (item === null) return <><td /><td /><td /><td /></>
                            if (item === 'empty') return <><td className="py-1" colSpan={4} /></>
                            if (item === 'ergebnis') {
                              const isGewinn = seite === 'soll'
                              return <>
                                <td className="py-2 pl-4 pr-2 font-bold text-gray-900 dark:text-white border-b border-gray-200 dark:border-gray-600">
                                  {isGewinn ? 'Gewinn' : 'Verlust'}
                                </td>
                                <td className={`py-2 pr-3 text-right tabular-nums whitespace-nowrap font-bold border-b border-gray-200 dark:border-gray-600 ${isGewinn ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                                  {fmtCalc(Math.abs(nettoT), 2)} €
                                </td>
                                <td className="py-2 pr-2 text-right tabular-nums whitespace-nowrap text-xs text-gray-400 dark:text-gray-500 border-b border-gray-200 dark:border-gray-600">
                                  {vj?.gesamtnettoertrag_euro != null ? `VJ: ${fmtCalc(vj.gesamtnettoertrag_euro, 2)} €` : ''}
                                </td>
                                <td className="py-2 pr-4 text-right whitespace-nowrap border-b border-gray-200 dark:border-gray-600">
                                  {vj?.gesamtnettoertrag_euro != null ? <Δ a={nettoT} b={vj.gesamtnettoertrag_euro} /> : null}
                                </td>
                              </>
                            }
                            // Normaler Posten
                            return <>
                              <td className="py-2 pl-4 pr-2 text-gray-700 dark:text-gray-300 border-b border-gray-100 dark:border-gray-700/50">
                                {item.formel
                                  ? <FormelTooltip formel={item.formel} berechnung={item.berechnung} ergebnis={item.ergebnis}>{item.label}</FormelTooltip>
                                  : item.label}
                              </td>
                              <td className={`py-2 pr-3 text-right tabular-nums whitespace-nowrap font-semibold border-b border-gray-100 dark:border-gray-700/50 ${item.color}`}>
                                {fmtCalc(item.wert, 2)} €
                              </td>
                              <td className="py-2 pr-2 text-right tabular-nums whitespace-nowrap text-xs text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-700/50">
                                {item.vjWert != null ? `VJ: ${fmtCalc(item.vjWert, 2)} €` : ''}
                              </td>
                              <td className="py-2 pr-4 text-right whitespace-nowrap border-b border-gray-100 dark:border-gray-700/50">
                                {item.vjWert != null ? <Δ a={item.wert} b={item.vjWert} inv={seite === 'soll'} /> : null}
                              </td>
                            </>
                          }

                          const thSoll = "px-4 py-2 text-left text-xs font-bold text-red-700 dark:text-red-400 uppercase tracking-wider bg-red-50 dark:bg-red-900/20"
                          const thHaben = "px-4 py-2 text-left text-xs font-bold text-green-700 dark:text-green-400 uppercase tracking-wider bg-green-50 dark:bg-green-900/20"
                          const sumRow = "bg-gray-100 dark:bg-gray-700/60 border-t-2 border-gray-300 dark:border-gray-600"

                          return (
                            <>
                              {/* ── Desktop: SOLL | HABEN nebeneinander ── */}
                              <table className="hidden sm:table w-full text-sm">
                                <thead>
                                  <tr className="border-b border-gray-200 dark:border-gray-600">
                                    <th colSpan={4} className={thSoll}>SOLL — Kosten</th>
                                    <th className="w-0 p-0 border-l border-gray-200 dark:border-gray-700" aria-hidden="true" />
                                    <th colSpan={4} className={thHaben}>HABEN — Erlöse + Einsparungen</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {sollRows.map((s, i) => (
                                    <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-700/20 transition-colors">
                                      {renderCell(s, 'soll')}
                                      <td className={tdDiv} />
                                      {renderCell(habenRows[i], 'haben')}
                                    </tr>
                                  ))}
                                  <tr className={sumRow}>
                                    <td className="py-2 pl-4 pr-2 text-xs font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Σ Soll</td>
                                    <td className="py-2 pr-3 text-right tabular-nums whitespace-nowrap font-bold text-gray-900 dark:text-white">{fmtCalc(sumSoll, 2)} €</td>
                                    <td className="py-2 pr-2 text-right tabular-nums whitespace-nowrap text-xs text-gray-400 dark:text-gray-500">{vjSumSoll != null ? `VJ: ${fmtCalc(vjSumSoll, 2)} €` : ''}</td>
                                    <td className="py-2 pr-4 text-right whitespace-nowrap">{vjSumSoll != null ? <Δ a={sumSoll} b={vjSumSoll} inv /> : null}</td>
                                    <td className={tdDiv} />
                                    <td className="py-2 pl-4 pr-2 text-xs font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Σ Haben</td>
                                    <td className="py-2 pr-3 text-right tabular-nums whitespace-nowrap font-bold text-gray-900 dark:text-white">{fmtCalc(sumHaben, 2)} €</td>
                                    <td className="py-2 pr-2 text-right tabular-nums whitespace-nowrap text-xs text-gray-400 dark:text-gray-500">{vjSumHaben != null ? `VJ: ${fmtCalc(vjSumHaben, 2)} €` : ''}</td>
                                    <td className="py-2 pr-4 text-right whitespace-nowrap">{vjSumHaben != null ? <Δ a={sumHaben} b={vjSumHaben} /> : null}</td>
                                  </tr>
                                </tbody>
                              </table>

                              {/* ── Mobile: SOLL oben, HABEN unten ── */}
                              <div className="sm:hidden">
                                {/* SOLL */}
                                <table className="w-full text-sm">
                                  <thead>
                                    <tr className="border-b border-gray-200 dark:border-gray-600">
                                      <th colSpan={4} className={thSoll}>SOLL — Kosten</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {sollRows.filter(r => r !== null).map((s, i) => (
                                      <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-700/20 transition-colors">
                                        {renderCell(s, 'soll')}
                                      </tr>
                                    ))}
                                    <tr className={sumRow}>
                                      <td className="py-2 pl-4 pr-2 text-xs font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Σ Soll</td>
                                      <td className="py-2 pr-3 text-right tabular-nums whitespace-nowrap font-bold text-gray-900 dark:text-white">{fmtCalc(sumSoll, 2)} €</td>
                                      <td className="py-2 pr-2 text-right tabular-nums whitespace-nowrap text-xs text-gray-400 dark:text-gray-500">{vjSumSoll != null ? `VJ: ${fmtCalc(vjSumSoll, 2)} €` : ''}</td>
                                      <td className="py-2 pr-4 text-right whitespace-nowrap">{vjSumSoll != null ? <Δ a={sumSoll} b={vjSumSoll} inv /> : null}</td>
                                    </tr>
                                  </tbody>
                                </table>
                                {/* HABEN */}
                                <table className="w-full text-sm border-t-2 border-gray-300 dark:border-gray-600">
                                  <thead>
                                    <tr className="border-b border-gray-200 dark:border-gray-600">
                                      <th colSpan={4} className={thHaben}>HABEN — Erlöse + Einsparungen</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {habenRows.filter(r => r !== null).map((h, i) => (
                                      <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-700/20 transition-colors">
                                        {renderCell(h, 'haben')}
                                      </tr>
                                    ))}
                                    <tr className={sumRow}>
                                      <td className="py-2 pl-4 pr-2 text-xs font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Σ Haben</td>
                                      <td className="py-2 pr-3 text-right tabular-nums whitespace-nowrap font-bold text-gray-900 dark:text-white">{fmtCalc(sumHaben, 2)} €</td>
                                      <td className="py-2 pr-2 text-right tabular-nums whitespace-nowrap text-xs text-gray-400 dark:text-gray-500">{vjSumHaben != null ? `VJ: ${fmtCalc(vjSumHaben, 2)} €` : ''}</td>
                                      <td className="py-2 pr-4 text-right whitespace-nowrap">{vjSumHaben != null ? <Δ a={sumHaben} b={vjSumHaben} /> : null}</td>
                                    </tr>
                                  </tbody>
                                </table>
                              </div>
                            </>
                          )
                        })()}
                      </div>

                      {/* Tarif-Info */}
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400 dark:text-gray-500 px-1">
                        {d.netzbezug_durchschnittspreis_cent != null
                          ? <span>Netzbezug Ø <span className="text-blue-500 font-medium">{fmtCalc(d.netzbezug_durchschnittspreis_cent, 2)} ct/kWh</span> (flex)</span>
                          : d.netzbezug_preis_cent != null && <span>Netzbezug {fmtCalc(d.netzbezug_preis_cent, 2)} ct/kWh</span>
                        }
                        {d.einspeise_preis_cent != null && <span>Einspeisung {fmtCalc(d.einspeise_preis_cent, 2)} ct/kWh</span>}
                      </div>
                    </div>
                  )
                })()}
              </Section>
            )}

            {/* ════ SEKTION 2b: Community-Vergleich ═══════════════════════ */}
            {(monatsVergleich || !selectedAnlage?.community_hash) && (
              <Section icon={Users} color="text-blue-400" title="Community-Vergleich"
                summary={
                  monatsVergleich
                    ? <span className="text-xs text-gray-400">{monatsVergleich.anzahl_anlagen} Anlagen im {MONAT_NAMEN[selectedMonat!]} {selectedJahr}</span>
                    : <span className="text-xs text-gray-400">Lade…</span>
                }
              >
                {monatsVergleich ? (
                  <div className="space-y-4 mt-2">
                    {/* KPI-Vergleich */}
                    {(() => {
                      const rows: Array<{
                        label: string
                        istVal: number | null | undefined
                        kpi: typeof monatsVergleich.autarkie
                        unit: string
                        inv?: boolean
                      }> = [
                        { label: 'Autarkie',     istVal: d?.autarkie_prozent,   kpi: monatsVergleich.autarkie,     unit: '%' },
                        { label: 'Eigenverbr.',  istVal: d?.eigenverbrauch_kwh != null && d?.pv_erzeugung_kwh ? Math.round(d.eigenverbrauch_kwh / d.pv_erzeugung_kwh * 100) : null, kpi: monatsVergleich.eigenverbrauch, unit: '%' },
                        { label: 'Einspeisung',  istVal: d?.einspeisung_kwh,    kpi: monatsVergleich.einspeisung,  unit: 'kWh' },
                        { label: 'Netzbezug',    istVal: d?.netzbezug_kwh,      kpi: monatsVergleich.netzbezug,    unit: 'kWh', inv: true },
                      ]
                      return (
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-700">
                              <th className="text-left pb-1.5 font-medium"><span className="sr-only">Kennzahl</span></th>
                              <th className="text-right pb-1.5 font-medium">Dein Wert</th>
                              <th className="text-right pb-1.5 font-medium">Community-Median</th>
                              <th className="text-right pb-1.5 font-medium"></th>
                            </tr>
                          </thead>
                          <tbody>
                            {rows.filter(r => r.kpi?.median != null).map(row => {
                              const median = row.kpi!.median!
                              const d2 = row.unit === '%' ? 0 : 0
                              const better = row.inv
                                ? (row.istVal ?? Infinity) <= median
                                : (row.istVal ?? -Infinity) >= median
                              return (
                                <tr key={row.label} className="border-b border-gray-100 dark:border-gray-700/50 last:border-0">
                                  <td className="py-1.5 text-gray-600 dark:text-gray-400">{row.label}</td>
                                  <td className="py-1.5 text-right font-semibold text-gray-900 dark:text-white tabular-nums">
                                    {row.istVal != null ? `${fmt(row.istVal, d2)} ${row.unit}` : '—'}
                                  </td>
                                  <td className="py-1.5 text-right text-gray-400 dark:text-gray-500 tabular-nums">
                                    {fmt(median, d2)} {row.unit}
                                  </td>
                                  <td className="py-1.5 text-right">
                                    {row.istVal != null && (
                                      <span className={`text-xs font-medium px-1 py-0.5 rounded ${
                                        better
                                          ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                                          : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                                      }`}>
                                        {better ? '▲' : '▼'}
                                      </span>
                                    )}
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      )
                    })()}

                    {/* Teilen-CTA wenn noch nicht geteilt */}
                    {!selectedAnlage?.community_hash && (
                      <div className="rounded-xl bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border border-blue-100 dark:border-blue-800/40 p-4">
                        <div className="flex items-start gap-3">
                          <div className="h-9 w-9 rounded-lg bg-blue-600 flex items-center justify-center shrink-0">
                            <Share2 className="h-4 w-4 text-white" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-semibold text-gray-900 dark:text-white">Wie schneidest du im Ranking ab?</p>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                              Teile deine Anlage anonym und sieh deinen Platz unter {monatsVergleich.anzahl_anlagen} Anlagen.
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => navigate('/einstellungen/community')}
                            className="shrink-0 text-xs px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors font-medium"
                          >
                            Jetzt teilen →
                          </button>
                        </div>
                      </div>
                    )}

                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      Basis: {monatsVergleich.anzahl_anlagen} Anlagen · {MONAT_NAMEN[selectedMonat!]} {selectedJahr}
                    </p>
                  </div>
                ) : (
                  <div className="mt-2 rounded-xl bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border border-blue-100 dark:border-blue-800/40 p-4">
                    <div className="flex items-start gap-3">
                      <div className="h-9 w-9 rounded-lg bg-blue-600 flex items-center justify-center shrink-0">
                        <Share2 className="h-4 w-4 text-white" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-gray-900 dark:text-white">Community-Vergleich freischalten</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                          Teile deine Anlage anonym und vergleiche deine Werte mit anderen PV-Anlagen.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => navigate('/einstellungen/community')}
                        className="shrink-0 text-xs px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors font-medium"
                      >
                        Jetzt teilen →
                      </button>
                    </div>
                  </div>
                )}
              </Section>
            )}

            {/* ════ SEKTION 3: Speicher ══════════════════════════════════ */}
            {d.hat_speicher && (
              <Section icon={Battery} color="text-blue-500" title="Speicher"
                summary={
                  <span className="flex gap-3 text-sm">
                    {d.speicher_ladung_kwh != null && <span>{fmt(d.speicher_ladung_kwh, 0)} kWh geladen</span>}
                    {d.speicher_vollzyklen != null && <span className="text-gray-400">{fmtCalc(d.speicher_vollzyklen, 1)} Zyklen</span>}
                    {d.speicher_wirkungsgrad_prozent != null && <span className="text-green-600 dark:text-green-400">{fmt(d.speicher_wirkungsgrad_prozent, 0)} % η</span>}
                  </span>
                }
              >
                <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <KPICard title="Ladung" value={fmt(d.speicher_ladung_kwh, 0)} unit="kWh" icon={Battery} color="blue"
                    subtitle={vm?.speicher_ladung_kwh != null ? `VM: ${fmt(vm.speicher_ladung_kwh, 0)} kWh` : undefined} />
                  <KPICard title="Entladung" value={fmt(d.speicher_entladung_kwh, 0)} unit="kWh" icon={Battery} color="green"
                    subtitle={vm?.speicher_entladung_kwh != null ? `VM: ${fmt(vm.speicher_entladung_kwh, 0)} kWh` : undefined} />
                  <KPICard title="Wirkungsgrad" value={fmt(d.speicher_wirkungsgrad_prozent, 1)} unit="%" icon={Gauge} color="green"
                    formel="Entladung ÷ Ladung × 100"
                    berechnung={d.speicher_ladung_kwh != null && d.speicher_entladung_kwh != null
                      ? `${fmt(d.speicher_entladung_kwh, 0)} ÷ ${fmt(d.speicher_ladung_kwh, 0)} kWh`
                      : undefined}
                    ergebnis={d.speicher_wirkungsgrad_prozent != null ? `= ${fmtCalc(d.speicher_wirkungsgrad_prozent, 1)} %` : undefined} />
                  <KPICard title="Vollzyklen" value={fmt(d.speicher_vollzyklen, 2)} unit=""
                    icon={ArrowUpDown} color="blue"
                    subtitle={d.speicher_kapazitaet_kwh != null ? `Kapazität: ${fmt(d.speicher_kapazitaet_kwh, 0)} kWh` : undefined}
                    formel="Ladung ÷ Kapazität"
                    berechnung={d.speicher_kapazitaet_kwh != null && d.speicher_ladung_kwh != null
                      ? `${fmt(d.speicher_ladung_kwh, 0)} ÷ ${fmt(d.speicher_kapazitaet_kwh, 0)} kWh`
                      : undefined} />
                </div>
                <div className="mt-3">
                  <VglZeile label="Ladung"             aktuell={d.speicher_ladung_kwh}       vm={vm?.speicher_ladung_kwh}    vj={vj?.speicher_ladung_kwh}    unit="kWh" />
                  <VglZeile label="Entladung"          aktuell={d.speicher_entladung_kwh}    vm={vm?.speicher_entladung_kwh} vj={vj?.speicher_entladung_kwh} unit="kWh" />
                  {d.speicher_ladung_netz_kwh != null && (
                    <VglZeile label="Netzladung (Arbitrage)" aktuell={d.speicher_ladung_netz_kwh} unit="kWh" inv />
                  )}
                  {d.speicher_ladung_kwh != null && d.speicher_entladung_kwh != null && (
                    <div className="flex justify-between py-1.5 text-sm border-t border-gray-100 dark:border-gray-700/50 mt-1 pt-2">
                      <span className="text-gray-500 dark:text-gray-400">Bilanz (Entladung − Ladung)</span>
                      <span className={`font-semibold ${d.speicher_entladung_kwh >= d.speicher_ladung_kwh ? 'text-green-600' : 'text-amber-600'}`}>
                        {d.speicher_entladung_kwh >= d.speicher_ladung_kwh ? '+' : ''}{fmt(d.speicher_entladung_kwh - d.speicher_ladung_kwh, 1)} kWh
                      </span>
                    </div>
                  )}
                </div>
              </Section>
            )}

            {/* ════ SEKTION 4: Wärmepumpe ═══════════════════════════════ */}
            {d.hat_waermepumpe && (
              <Section icon={Flame} color="text-orange-500" title="Wärmepumpe"
                summary={
                  <span className="flex gap-3 text-sm">
                    {d.wp_strom_kwh != null && <span>{fmt(d.wp_strom_kwh, 0)} kWh Strom</span>}
                    {d.wp_strom_kwh != null && d.wp_waerme_kwh != null && d.wp_strom_kwh > 0 && (
                      <span className="text-green-600 dark:text-green-400">COP {(d.wp_waerme_kwh / d.wp_strom_kwh).toFixed(2)}</span>
                    )}
                    {d.wp_ersparnis_euro != null && <span className="text-green-500">+{fmtCalc(d.wp_ersparnis_euro, 2)} € vs. Gas</span>}
                  </span>
                }
              >
                <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <KPICard title="Stromverbrauch" value={fmt(d.wp_strom_kwh, 0)} unit="kWh" icon={Zap} color="red"
                    subtitle={vm?.wp_strom_kwh != null ? `VM: ${fmt(vm.wp_strom_kwh, 0)} kWh` : undefined} />
                  <KPICard title="Wärmeertrag" value={fmt(d.wp_waerme_kwh, 0)} unit="kWh" icon={Flame} color="orange"
                    subtitle={vm ? `VM: ${fmt(vm.wp_heizung_kwh + vm.wp_warmwasser_kwh, 0)} kWh` : undefined} />
                  <KPICard title="COP" value={d.wp_strom_kwh != null && d.wp_waerme_kwh != null && d.wp_strom_kwh > 0
                    ? fmtCalc(d.wp_waerme_kwh / d.wp_strom_kwh, 2) : '—'} unit=""
                    icon={Gauge} color="green"
                    formel="Wärmeertrag ÷ Stromverbrauch"
                    subtitle={vm && vm.wp_strom_kwh > 0 ? `VM: ${fmtCalc((vm.wp_heizung_kwh + vm.wp_warmwasser_kwh) / vm.wp_strom_kwh, 2)}` : undefined} />
                  <KPICard title="Ersparnis vs. Gas" value={d.wp_ersparnis_euro != null ? `+${fmt(d.wp_ersparnis_euro, 2)}` : '—'} unit="€"
                    icon={Euro} color="green"
                    formel="(Wärme ÷ 0,9 × Gaspreis − Strom × Strompreis)"
                    subtitle={vj?.wp_strom_kwh != null ? `VJ Strom: ${fmt(vj.wp_strom_kwh, 0)} kWh` : undefined} />
                </div>
                <div className="mt-3">
                  <VglZeile label="Stromverbrauch" aktuell={d.wp_strom_kwh}   vm={vm?.wp_strom_kwh}  vj={vj?.wp_strom_kwh}  unit="kWh" inv />
                  <VglZeile label="Wärmeertrag"    aktuell={d.wp_waerme_kwh}  vm={vm ? vm.wp_heizung_kwh + vm.wp_warmwasser_kwh : null} vj={vj?.wp_waerme_kwh} unit="kWh" />
                  {d.wp_heizung_kwh != null && (
                    <VglZeile label="  davon Heizung"    aktuell={d.wp_heizung_kwh}    unit="kWh" />
                  )}
                  {d.wp_warmwasser_kwh != null && (
                    <VglZeile label="  davon Warmwasser" aktuell={d.wp_warmwasser_kwh} unit="kWh" />
                  )}
                </div>
              </Section>
            )}

            {/* ════ SEKTION 5: E-Mobilität ═══════════════════════════════ */}
            {d.hat_emobilitaet && (
              <Section icon={Car} color="text-purple-500" title="E-Mobilität"
                summary={
                  <span className="flex gap-3 text-sm">
                    {d.emob_ladung_kwh != null && <span>{fmt(d.emob_ladung_kwh, 0)} kWh geladen</span>}
                    {d.emob_km != null && <span>{fmt(d.emob_km, 0)} km</span>}
                    {d.emob_ersparnis_euro != null && <span className="text-green-500">+{fmtCalc(d.emob_ersparnis_euro, 2)} € vs. Verbrenner</span>}
                  </span>
                }
              >
                <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <KPICard title="Ladung gesamt" value={fmt(d.emob_ladung_kwh, 0)} unit="kWh" icon={Plug} color="purple"
                    subtitle={vm ? `VM: ${fmt((vm.eauto_ladung_kwh + vm.wallbox_ladung_kwh), 0)} kWh` : undefined} />
                  <KPICard title="PV-Anteil" value={d.emob_ladung_pv_kwh != null && d.emob_ladung_kwh ? fmt(d.emob_ladung_pv_kwh / d.emob_ladung_kwh * 100, 0) : '—'} unit="%"
                    icon={Sun} color="yellow"
                    subtitle={d.emob_ladung_pv_kwh != null ? `${fmt(d.emob_ladung_pv_kwh, 0)} kWh PV` : undefined}
                    formel="PV-Ladung ÷ Gesamt-Ladung × 100" />
                  <KPICard title="Kilometer" value={fmt(d.emob_km, 0)} unit="km" icon={Car} color="blue"
                    subtitle={vm?.eauto_km != null ? `VM: ${fmt(vm.eauto_km, 0)} km` : undefined} />
                  <KPICard title="Verbrauch" value={d.emob_km && d.emob_ladung_kwh && d.emob_km > 0
                    ? fmtCalc(d.emob_ladung_kwh / d.emob_km * 100, 1) : '—'} unit="kWh/100km"
                    icon={Gauge} color="gray"
                    formel="Ladung ÷ km × 100" />
                </div>
                <div className="mt-3">
                  <VglZeile label="Ladung gesamt"    aktuell={d.emob_ladung_kwh}       vm={vm ? vm.eauto_ladung_kwh + vm.wallbox_ladung_kwh : null} vj={vj?.emob_ladung_kwh}  unit="kWh" />
                  {d.emob_ladung_pv_kwh != null && (
                    <VglZeile label="  PV-Anteil"    aktuell={d.emob_ladung_pv_kwh}    vm={vm?.wallbox_ladung_pv_kwh} unit="kWh" />
                  )}
                  {d.emob_ladung_netz_kwh != null && (
                    <VglZeile label="  Netz-Anteil"  aktuell={d.emob_ladung_netz_kwh}  unit="kWh" inv />
                  )}
                  {d.emob_ladung_extern_kwh != null && (
                    <VglZeile label="  Extern"       aktuell={d.emob_ladung_extern_kwh} unit="kWh" />
                  )}
                  {d.emob_v2h_kwh != null && (
                    <VglZeile label="V2H-Rückspeisung" aktuell={d.emob_v2h_kwh} unit="kWh" />
                  )}
                  <VglZeile label="Kilometer"        aktuell={d.emob_km}                vm={vm?.eauto_km}              vj={vj?.emob_km}             unit="km" />
                  {d.emob_ersparnis_euro != null && (
                    <VglZeile label="Ersparnis vs. Verbrenner" aktuell={d.emob_ersparnis_euro} unit="€"
                      formel="(km × 7 L/100km × 1,80 €/L) − (Netzladung × Strompreis)"
                      ergebnis={`= ${fmtCalc(d.emob_ersparnis_euro, 2)} €`} />
                  )}
                </div>
              </Section>
            )}

            {/* ════ SEKTION 6: Balkonkraftwerk ══════════════════════════ */}
            {d.hat_balkonkraftwerk && (
              <Section icon={Sun} color="text-yellow-400" title="Balkonkraftwerk"
                summary={<span className="text-sm">{fmt(d.bkw_erzeugung_kwh, 0)} kWh erzeugt · in Gesamt-PV enthalten</span>}
              >
                <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <KPICard title="Erzeugung" value={fmt(d.bkw_erzeugung_kwh, 0)} unit="kWh" icon={Sun} color="yellow" />
                  {d.bkw_eigenverbrauch_kwh != null && (
                    <KPICard title="Eigenverbrauch" value={fmt(d.bkw_eigenverbrauch_kwh, 0)} unit="kWh" icon={Home} color="purple"
                      subtitle={d.bkw_erzeugung_kwh != null && d.bkw_erzeugung_kwh > 0
                        ? `EV-Quote ${Math.round(d.bkw_eigenverbrauch_kwh / d.bkw_erzeugung_kwh * 100)} %`
                        : undefined} />
                  )}
                  {d.bkw_erzeugung_kwh != null && d.bkw_eigenverbrauch_kwh != null && (
                    <KPICard title="Einspeisung" value={fmt(d.bkw_erzeugung_kwh - d.bkw_eigenverbrauch_kwh, 0)} unit="kWh" icon={TrendingUp} color="green" />
                  )}
                </div>
              </Section>
            )}

            {/* ════ SEKTION 7: Sonstiges ═════════════════════════════════ */}
            {d.hat_sonstiges && (
              <Section icon={Wrench} color="text-gray-500" title="Sonstiges"
                summary={
                  <span className="flex gap-3 text-sm text-gray-400">
                    {d.sonstiges_erzeugung_kwh != null && <span>{fmt(d.sonstiges_erzeugung_kwh, 0)} kWh erzeugt</span>}
                    {d.sonstiges_verbrauch_kwh != null && <span>{fmt(d.sonstiges_verbrauch_kwh, 0)} kWh verbraucht</span>}
                  </span>
                }
              >
                <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {d.sonstiges_erzeugung_kwh != null && (
                    <KPICard title="Erzeugung" value={fmt(d.sonstiges_erzeugung_kwh, 0)} unit="kWh" icon={Zap} color="green" />
                  )}
                  {d.sonstiges_eigenverbrauch_kwh != null && (
                    <KPICard title="Eigenverbrauch" value={fmt(d.sonstiges_eigenverbrauch_kwh, 0)} unit="kWh" icon={Home} color="purple" />
                  )}
                  {d.sonstiges_einspeisung_kwh != null && (
                    <KPICard title="Einspeisung" value={fmt(d.sonstiges_einspeisung_kwh, 0)} unit="kWh" icon={TrendingUp} color="green" />
                  )}
                  {d.sonstiges_verbrauch_kwh != null && (
                    <KPICard title="Verbrauch" value={fmt(d.sonstiges_verbrauch_kwh, 0)} unit="kWh" icon={Zap} color="red" />
                  )}
                  {d.sonstiges_bezug_pv_kwh != null && (
                    <KPICard title="Bezug aus PV" value={fmt(d.sonstiges_bezug_pv_kwh, 0)} unit="kWh" icon={Sun} color="yellow" />
                  )}
                  {d.sonstiges_bezug_netz_kwh != null && (
                    <KPICard title="Bezug aus Netz" value={fmt(d.sonstiges_bezug_netz_kwh, 0)} unit="kWh" icon={Zap} color="red" />
                  )}
                </div>
              </Section>
            )}

            {/* Jahres-Kontext entfernt — vertikaler Zeitstrahl übernimmt die Orientierung */}

          </div>
        )}
      </main>
    </div>
  )
}
