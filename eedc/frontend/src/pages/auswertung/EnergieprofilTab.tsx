// Energieprofil-Tab — Tagesdetail + Wochenvergleich
// Etappe 2: Auswertung persistierter Stundenwerte aus TagesEnergieProfil
import { useState, useEffect, useMemo, useRef } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { Download, ChevronUp, ChevronDown, ChevronsUpDown, Columns } from 'lucide-react'
import ChartTooltip from '../../components/ui/ChartTooltip'
import { Card, Button } from '../../components/ui'
import { exportToCSV } from '../../utils/export'
import { energieProfilApi, type StundenWert, type SerieInfo, type WochenmusterPunkt } from '../../api/energie_profil'

// Kategorien die bereits dedizierte Spalten/Felder haben → kein Extra-Tracking
const DEDIZIERTE_KATEGORIEN = new Set(['pv', 'batterie', 'netz', 'haushalt', 'waermepumpe', 'wallbox', 'eauto', 'virtual'])

// Farben für extra Sonstiges-Serien (Rotation) — hex für Recharts, Tailwind-Klassen für Tabelle
const EXTRA_FARBEN = ['#8b5cf6', '#06b6d4', '#84cc16', '#f43f5e', '#fb923c', '#a78bfa']

// ─── Konstanten ───────────────────────────────────────────────────────────────

const WOCHENTAG_KURZ = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

// Gruppierungen für Wochenvergleich
const GRUPPEN = [
  { label: 'Mo–Fr', tage: [0, 1, 2, 3, 4] },
  { label: 'Sa–So', tage: [5, 6] },
  { label: 'Mo', tage: [0] },
  { label: 'Di', tage: [1] },
  { label: 'Mi', tage: [2] },
  { label: 'Do', tage: [3] },
  { label: 'Fr', tage: [4] },
  { label: 'Sa', tage: [5] },
  { label: 'So', tage: [6] },
]

const GRUPPEN_FARBEN: Record<string, string> = {
  'Mo–Fr': '#3b82f6',
  'Sa–So': '#f97316',
  'Mo': '#6366f1',
  'Di': '#8b5cf6',
  'Mi': '#ec4899',
  'Do': '#14b8a6',
  'Fr': '#84cc16',
  'Sa': '#f59e0b',
  'So': '#ef4444',
}

// Tailwind-Klassen für aktive Wochentag-Buttons (kein inline style)
const GRUPPEN_BG_CSS: Record<string, string> = {
  'Mo–Fr': 'bg-blue-500',
  'Sa–So': 'bg-orange-500',
  'Mo':    'bg-indigo-500',
  'Di':    'bg-violet-500',
  'Mi':    'bg-pink-500',
  'Do':    'bg-teal-500',
  'Fr':    'bg-lime-500',
  'Sa':    'bg-amber-500',
  'So':    'bg-red-500',
}

// Zeitraum-Optionen für Wochenvergleich
const ZEITRAUM_OPTIONEN = [
  { label: '30 Tage', tage: 30 },
  { label: '90 Tage', tage: 90 },
  { label: '180 Tage', tage: 180 },
  { label: '365 Tage', tage: 365 },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function gesternISO(): string {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  return toISODate(d)
}

function vorTagenISO(tage: number): string {
  const d = new Date()
  d.setDate(d.getDate() - tage)
  return toISODate(d)
}

function fmt1(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toFixed(1)
}

function fmt0(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toFixed(0)
}

// ─── Tagesdetail ──────────────────────────────────────────────────────────────

interface TagesdetailProps {
  anlageId: number
}

function Tagesdetail({ anlageId }: TagesdetailProps) {
  const [datum, setDatum] = useState(gesternISO())
  const [daten, setDaten] = useState<StundenWert[]>([])
  const [extraSerien, setExtraSerien] = useState<SerieInfo[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!anlageId || !datum) return
    setLoading(true)
    energieProfilApi.getStunden(anlageId, datum)
      .then(antwort => {
        setDaten(antwort.stunden)
        setExtraSerien(antwort.serien.filter(s => !DEDIZIERTE_KATEGORIEN.has(s.kategorie)))
      })
      .catch(() => { setDaten([]); setExtraSerien([]) })
      .finally(() => setLoading(false))
  }, [anlageId, datum])

  const extraErzeuger    = extraSerien.filter(s => s.seite === 'quelle')
  const extraVerbraucher = extraSerien.filter(s => s.seite === 'senke')

  // Chart-Serien analog TagesverlaufChart: bidirektionale in _pos/_neg aufgespalten
  interface ChartSerie { dataKey: string; label: string; farbe: string; stackId: 'quellen' | 'senken'; hideLabel?: boolean }
  const chartSerien = useMemo<ChartSerie[]>(() => {
    const r: ChartSerie[] = []
    r.push({ dataKey: 'pv', label: 'PV', farbe: '#eab308', stackId: 'quellen' })
    extraErzeuger.forEach((es, i) =>
      r.push({ dataKey: es.key, label: es.label, farbe: EXTRA_FARBEN[i % EXTRA_FARBEN.length], stackId: 'quellen' }))
    r.push({ dataKey: 'bat_pos', label: 'Batterie', farbe: '#3b82f6', stackId: 'quellen' })
    r.push({ dataKey: 'bat_neg', label: 'Batterie ↓', farbe: '#3b82f6', stackId: 'senken', hideLabel: true })
    r.push({ dataKey: 'netz_pos', label: 'Stromnetz', farbe: '#ef4444', stackId: 'quellen' })
    r.push({ dataKey: 'netz_neg', label: 'Stromnetz ↓', farbe: '#ef4444', stackId: 'senken', hideLabel: true })
    r.push({ dataKey: 'hausverbrauch', label: 'Hausverbrauch', farbe: '#10b981', stackId: 'senken' })
    r.push({ dataKey: 'wp', label: 'Wärmepumpe', farbe: '#f97316', stackId: 'senken' })
    r.push({ dataKey: 'wb', label: 'Wallbox', farbe: '#a855f7', stackId: 'senken' })
    extraVerbraucher.forEach((es, i) =>
      r.push({ dataKey: es.key, label: es.label, farbe: EXTRA_FARBEN[(extraErzeuger.length + i) % EXTRA_FARBEN.length], stackId: 'senken' }))
    return r
  }, [extraErzeuger, extraVerbraucher])

  const chartDaten = useMemo(() =>
    Array.from({ length: 24 }, (_, h) => {
      const s   = daten.find(d => d.stunde === h)
      const bat = s?.batterie_kw ?? 0
      const ntz = (s?.netzbezug_kw ?? 0) - (s?.einspeisung_kw ?? 0)
      const vbrSons = extraVerbraucher.reduce((a, es) => a + Math.abs(Math.min(0, s?.komponenten?.[es.key] ?? 0)), 0)
      const erzSons = extraErzeuger.reduce((a, es) => a + Math.max(0, s?.komponenten?.[es.key] ?? 0), 0)
      const punkt: Record<string, number | string> = {
        stunde:       `${h}:00`,
        pv:           s?.pv_kw ?? 0,
        bat_pos:      Math.max(0, bat),
        bat_neg:      Math.min(0, bat),
        netz_pos:     Math.max(0, ntz),
        netz_neg:     Math.min(0, ntz),
        hausverbrauch: -Math.max(0, (s?.verbrauch_kw ?? 0) - (s?.waermepumpe_kw ?? 0) - (s?.wallbox_kw ?? 0) - vbrSons),
        wp:           -(s?.waermepumpe_kw ?? 0),
        wb:           -(s?.wallbox_kw ?? 0),
        gesamterzeugung: round2((s?.pv_kw ?? 0) + Math.max(0, bat) + erzSons),
      }
      for (const es of extraErzeuger)    punkt[es.key] = Math.max(0, s?.komponenten?.[es.key] ?? 0)
      for (const es of extraVerbraucher) punkt[es.key] = Math.min(0, s?.komponenten?.[es.key] ?? 0)
      return punkt
    }), [daten, extraErzeuger, extraVerbraucher])

  // KPIs
  const kpis = useMemo(() => {
    if (!daten.length) return null
    const pvKwh        = daten.reduce((a, d) => a + (d.pv_kw ?? 0), 0)
    const batEntlKwh   = daten.reduce((a, d) => a + Math.max(0, d.batterie_kw ?? 0), 0)
    const erzSonstKwh  = extraErzeuger.reduce((a, es) =>
      a + daten.reduce((b, d) => b + Math.max(0, d.komponenten?.[es.key] ?? 0), 0), 0)
    const gesamterzKwh = pvKwh + batEntlKwh + erzSonstKwh
    const vKwh         = daten.reduce((a, d) => a + (d.verbrauch_kw ?? 0), 0)
    const netzbezugKwh = daten.reduce((a, d) => a + (d.netzbezug_kw ?? 0), 0)
    const einspeisKwh  = daten.reduce((a, d) => a + (d.einspeisung_kw ?? 0), 0)
    const autarkie     = vKwh > 0 ? Math.min(100, (1 - netzbezugKwh / vKwh) * 100) : null
    const temps        = daten.filter(d => d.temperatur_c != null).map(d => d.temperatur_c!)
    return { gesamterzKwh, pvKwh, vKwh, netzbezugKwh, einspeisKwh, autarkie,
             tempMin: temps.length ? Math.min(...temps) : null,
             tempMax: temps.length ? Math.max(...temps) : null }
  }, [daten, extraErzeuger])

  return (
    <div className="space-y-4">
      {/* Datum-Picker */}
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Tag:</label>
        <input type="date" aria-label="Tag auswählen" value={datum} max={gesternISO()}
          onChange={e => setDatum(e.target.value)} className="input w-auto text-sm" />
        {loading && <span className="text-xs text-gray-400">Lade…</span>}
      </div>

      {/* KPI-Zeile */}
      {kpis && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <KpiCard label="Gesamterzeugung" value={`${fmt1(kpis.gesamterzKwh)} kWh`} color="text-yellow-600 dark:text-yellow-400" />
          <KpiCard label="PV-Anteil"       value={`${fmt1(kpis.pvKwh)} kWh`}         color="text-amber-500 dark:text-amber-400" />
          <KpiCard label="Gesamtverbrauch" value={`${fmt1(kpis.vKwh)} kWh`}          color="text-gray-600 dark:text-gray-300" />
          <KpiCard label="Netzbezug"       value={`${fmt1(kpis.netzbezugKwh)} kWh`}  color="text-red-600 dark:text-red-400" />
          <KpiCard label="Einspeisung"     value={`${fmt1(kpis.einspeisKwh)} kWh`}   color="text-blue-600 dark:text-blue-400" />
          <KpiCard label="Autarkie"        value={kpis.autarkie != null ? `${fmt0(kpis.autarkie)} %` : '—'} color="text-primary-600 dark:text-primary-400" />
          <KpiCard label="Temperatur"      value={kpis.tempMin != null ? `${fmt1(kpis.tempMin)} / ${fmt1(kpis.tempMax)} °C` : '—'} color="text-orange-600 dark:text-orange-400" />
        </div>
      )}

      {/* Chart */}
      {daten.length === 0 && !loading ? (
        <Card className="text-center py-10 text-gray-400 dark:text-gray-500 text-sm">
          Keine Daten für diesen Tag vorhanden.
        </Card>
      ) : (
        <Card>
          <div className="text-[10px] text-gray-400 dark:text-gray-500 mb-1 flex justify-between">
            <span>▲ Quellen (Erzeugung, Bezug)</span>
            <span>Stundenmittelwerte aus Energieprofil · gestrichelt = Gesamterzeugung</span>
            <span>▼ Senken (Verbrauch, Einspeisung)</span>
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={chartDaten} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="stunde" tick={{ fontSize: 11 }} interval={2} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => v.toFixed(1)} />
              <ReferenceLine y={0} stroke="#9ca3af" strokeWidth={1.5} />
              <Tooltip content={<ChartTooltip
                unit=" kW" decimals={2}
                formatter={(v) => Math.abs(v) < 0.001 ? null : `${v > 0 ? '▲' : '▼'} ${Math.abs(v).toFixed(2)} kW`}
              />} />
              <Legend
                wrapperStyle={{ fontSize: 11 }}
                formatter={(value: string) => chartSerien.find(cs => cs.dataKey === value)?.label ?? value}
              />

              {chartSerien.map(cs => (
                <Area
                  key={cs.dataKey}
                  type="monotone"
                  dataKey={cs.dataKey}
                  name={cs.dataKey}
                  fill={cs.farbe}
                  stroke={cs.farbe}
                  fillOpacity={0.3}
                  strokeWidth={1.5}
                  stackId={cs.stackId}
                  isAnimationActive={false}
                  legendType={cs.hideLabel ? 'none' : undefined}
                />
              ))}

              <Line dataKey="gesamterzeugung" name="gesamterzeugung"
                stroke="#fbbf24" strokeWidth={2} strokeDasharray="5 3"
                dot={false} connectNulls legendType="none" />
            </ComposedChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Detailtabelle */}
      {daten.length > 0 && <TagesdetailTabelle daten={daten} extraSerien={extraSerien} datum={datum} />}
    </div>
  )
}

// ─── Wochenvergleich ──────────────────────────────────────────────────────────

interface WochenvergleichProps {
  anlageId: number
}

function Wochenvergleich({ anlageId }: WochenvergleichProps) {
  const [zeitraumTage, setZeitraumTage] = useState(90)
  const [aktivGruppen, setAktivGruppen] = useState<string[]>(['Mo–Fr', 'Sa–So'])
  const [feld, setFeld] = useState<'verbrauch_kw' | 'pv_kw' | 'netzbezug_kw'>('verbrauch_kw')
  const [daten, setDaten] = useState<WochenmusterPunkt[]>([])
  const [loading, setLoading] = useState(false)

  const bis = toISODate(new Date())
  const von = vorTagenISO(zeitraumTage)

  useEffect(() => {
    if (!anlageId) return
    setLoading(true)
    energieProfilApi.getWochenmuster(anlageId, von, bis)
      .then(setDaten)
      .catch(() => setDaten([]))
      .finally(() => setLoading(false))
  }, [anlageId, zeitraumTage])

  // Chart-Daten: eine Zeile pro Stunde, eine Spalte pro aktiver Gruppe
  const chartDaten = useMemo(() => {
    return Array.from({ length: 24 }, (_, h) => {
      const punkt: Record<string, number | string | null> = { stunde: `${h}:00` }
      for (const gruppe of GRUPPEN.filter(g => aktivGruppen.includes(g.label))) {
        const relevant = daten.filter(d => gruppe.tage.includes(d.wochentag) && d.stunde === h)
        if (relevant.length === 0) {
          punkt[gruppe.label] = null
          continue
        }
        const werte = relevant.map(d => d[feld]).filter(v => v != null) as number[]
        punkt[gruppe.label] = werte.length ? round2(werte.reduce((a, b) => a + b, 0) / werte.length) : null
      }
      return punkt
    })
  }, [daten, aktivGruppen, feld])

  function toggleGruppe(label: string) {
    setAktivGruppen(prev =>
      prev.includes(label) ? prev.filter(g => g !== label) : [...prev, label]
    )
  }

  const feldOptionen: { value: typeof feld; label: string }[] = [
    { value: 'verbrauch_kw', label: 'Verbrauch' },
    { value: 'pv_kw', label: 'PV-Erzeugung' },
    { value: 'netzbezug_kw', label: 'Netzbezug' },
  ]

  const anzahlHinweis = useMemo(() => {
    if (!daten.length) return null
    const map = new Map<number, number>()
    for (const d of daten) {
      const prev = map.get(d.wochentag) || 0
      map.set(d.wochentag, Math.max(prev, d.anzahl_tage))
    }
    return map
  }, [daten])

  return (
    <div className="space-y-4">
      {/* Filter-Zeile */}
      <div className="flex flex-wrap items-center gap-4">
        {/* Zeitraum */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Zeitraum:</span>
          <div className="flex gap-1">
            {ZEITRAUM_OPTIONEN.map(o => (
              <button
                type="button"
                key={o.tage}
                onClick={() => setZeitraumTage(o.tage)}
                className={`px-2 py-1 text-xs rounded font-medium transition-colors ${
                  zeitraumTage === o.tage
                    ? 'bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300'
                    : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        {/* Kennzahl */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Zeige:</span>
          <div className="flex gap-1">
            {feldOptionen.map(o => (
              <button
                type="button"
                key={o.value}
                onClick={() => setFeld(o.value)}
                className={`px-2 py-1 text-xs rounded font-medium transition-colors ${
                  feld === o.value
                    ? 'bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300'
                    : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        {loading && <span className="text-xs text-gray-400">Lade…</span>}
      </div>

      {/* Wochentag-Toggles */}
      <div className="flex flex-wrap gap-2">
        {GRUPPEN.map(g => {
          const aktiv = aktivGruppen.includes(g.label)
          const anzahl = g.tage.length === 1 ? anzahlHinweis?.get(g.tage[0]) : null
          return (
            <button
              type="button"
              key={g.label}
              onClick={() => toggleGruppe(g.label)}
              title={anzahl ? `${anzahl} Tage im Zeitraum` : undefined}
              className={`px-3 py-1 text-xs rounded-full font-medium border transition-colors ${
                aktiv
                  ? `border-transparent text-white ${GRUPPEN_BG_CSS[g.label] ?? 'bg-primary-500'}`
                  : 'border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 bg-transparent'
              }`}
            >
              {g.label}
              {anzahl != null && <span className="ml-1 opacity-70">({anzahl})</span>}
            </button>
          )
        })}
      </div>

      {/* Chart */}
      {daten.length === 0 && !loading ? (
        <Card className="text-center py-10 text-gray-400 dark:text-gray-500 text-sm">
          Keine Daten im gewählten Zeitraum.
        </Card>
      ) : (
        <Card>
          <div className="text-xs text-gray-500 dark:text-gray-400 mb-3">
            Ø-{feldOptionen.find(f => f.value === feld)?.label} in kW je Stunde
            {' '}· Zeitraum: {von} – {bis}
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={chartDaten} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.15)" />
              <XAxis dataKey="stunde" tick={{ fontSize: 11 }} interval={2} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${v}`} />
              <Tooltip content={<ChartTooltip unit=" kW" decimals={2} />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {GRUPPEN.filter(g => aktivGruppen.includes(g.label)).map(g => (
                <Line
                  key={g.label}
                  dataKey={g.label}
                  name={g.label}
                  stroke={GRUPPEN_FARBEN[g.label]}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Detailtabelle alle Wochentage × Felder */}
      {daten.length > 0 && <WochenmusterTabelle daten={daten} />}
    </div>
  )
}

// ─── Tabellen ─────────────────────────────────────────────────────────────────

// ── Tabellenspalten-Definitionen (analog TabelleTab) ─────────────────────────

type TdGroup = 'erzeugung' | 'netz' | 'verbrauch' | 'bilanz' | 'qualitaet'

interface TdColDef {
  key: string
  label: string
  unit: string
  group: TdGroup
  decimals: number
  isSum: boolean        // kW × 1h = kWh in Summenzeile
  defaultVisible: boolean
  calc?: boolean        // berechnete Spalte (kein direktes StundenWert-Feld)
}

const TD_COLUMNS: TdColDef[] = [
  // Erzeugung
  { key: 'gesamterzeugung', label: 'Gesamterzeugung', unit: 'kW', group: 'erzeugung', decimals: 2, isSum: true,  defaultVisible: true,  calc: true  },
  { key: 'pv_kw',           label: 'PV',              unit: 'kW', group: 'erzeugung', decimals: 2, isSum: true,  defaultVisible: true                },
  { key: 'batterie_kw',     label: 'Batterie',        unit: 'kW', group: 'erzeugung', decimals: 2, isSum: true,  defaultVisible: true                },
  // Netz
  { key: 'netzbezug_kw',   label: 'Netzbezug',       unit: 'kW', group: 'netz',      decimals: 2, isSum: true,  defaultVisible: true                },
  { key: 'einspeisung_kw', label: 'Einspeisung',     unit: 'kW', group: 'netz',      decimals: 2, isSum: true,  defaultVisible: false               },
  // Verbrauch
  { key: 'verbrauch_kw',   label: 'Gesamtverbrauch', unit: 'kW', group: 'verbrauch', decimals: 2, isSum: true,  defaultVisible: true                },
  { key: 'hausverbrauch',  label: 'Hausverbrauch',   unit: 'kW', group: 'verbrauch', decimals: 2, isSum: true,  defaultVisible: true,  calc: true   },
  { key: 'waermepumpe_kw', label: 'Wärmepumpe',      unit: 'kW', group: 'verbrauch', decimals: 2, isSum: true,  defaultVisible: true                },
  { key: 'wallbox_kw',     label: 'Wallbox',         unit: 'kW', group: 'verbrauch', decimals: 2, isSum: true,  defaultVisible: true                },
  // Bilanz
  { key: 'ueberschuss_kw', label: 'Überschuss',      unit: 'kW', group: 'bilanz',    decimals: 2, isSum: true,  defaultVisible: false               },
  { key: 'defizit_kw',     label: 'Defizit',         unit: 'kW', group: 'bilanz',    decimals: 2, isSum: true,  defaultVisible: false               },
  // Qualität
  { key: 'soc_prozent',        label: 'SoC',         unit: '%',    group: 'qualitaet', decimals: 1, isSum: false, defaultVisible: false             },
  { key: 'temperatur_c',       label: 'Temperatur',  unit: '°C',   group: 'qualitaet', decimals: 1, isSum: false, defaultVisible: false             },
  { key: 'globalstrahlung_wm2',label: 'Strahlung',   unit: 'W/m²', group: 'qualitaet', decimals: 0, isSum: false, defaultVisible: false             },
]

const TD_GROUP_LABELS: Record<TdGroup, string> = {
  erzeugung: 'Erzeugung',
  netz:      'Netz',
  verbrauch: 'Verbrauch',
  bilanz:    'Bilanz',
  qualitaet: 'Qualität',
}
const TD_GROUPS: TdGroup[] = ['erzeugung', 'netz', 'verbrauch', 'bilanz', 'qualitaet']
const TD_STORAGE_KEY = 'eedc_tagesprofil_visible_cols'

function TagesdetailTabelle({ daten, extraSerien, datum }: { daten: StundenWert[], extraSerien: SerieInfo[], datum: string }) {
  const extraErzeuger    = extraSerien.filter(s => s.seite === 'quelle')
  const extraVerbraucher = extraSerien.filter(s => s.seite === 'senke')

  // Berechnete Werte pro Stunde
  function calcGesamterzeugung(s: StundenWert): number {
    const erzS = extraErzeuger.reduce((a, es) => a + Math.max(0, s.komponenten?.[es.key] ?? 0), 0)
    return round2((s.pv_kw ?? 0) + Math.max(0, s.batterie_kw ?? 0) + erzS)
  }
  function calcHausverbrauch(s: StundenWert): number {
    const vbrS = extraVerbraucher.reduce((a, es) => a + Math.abs(Math.min(0, s.komponenten?.[es.key] ?? 0)), 0)
    return round2(Math.max(0, (s.verbrauch_kw ?? 0) - (s.waermepumpe_kw ?? 0) - (s.wallbox_kw ?? 0) - vbrS))
  }

  // Sichtbare Spalten aus localStorage
  const [visibleCols, setVisibleCols] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem(TD_STORAGE_KEY)
      if (stored) {
        const keys = JSON.parse(stored) as string[]
        return new Set(keys)
      }
    } catch { /* ignore */ }
    const defaults = new Set(TD_COLUMNS.filter(c => c.defaultVisible).map(c => c.key))
    extraSerien.forEach(es => defaults.add(es.key))
    return defaults
  })
  useEffect(() => {
    // Neue extra Serien immer als sichtbar hinzufügen
    setVisibleCols(prev => {
      const next = new Set(prev)
      extraSerien.forEach(es => { if (!next.has(es.key)) next.add(es.key) })
      return next
    })
  }, [extraSerien])
  useEffect(() => {
    try { localStorage.setItem(TD_STORAGE_KEY, JSON.stringify([...visibleCols])) } catch { /* ignore */ }
  }, [visibleCols])

  function toggleCol(key: string) {
    setVisibleCols(prev => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n })
  }

  // Spaltenauswahl-Picker
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function onOut(e: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) setPickerOpen(false)
    }
    if (pickerOpen) document.addEventListener('mousedown', onOut)
    return () => document.removeEventListener('mousedown', onOut)
  }, [pickerOpen])

  // Sortierung
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  function handleSort(key: string) {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  // Stunden-Daten (0-23, mit berechneten Feldern)
  const rows = useMemo(() => {
    const all = Array.from({ length: 24 }, (_, h) => {
      const s = daten.find(d => d.stunde === h)
      const raw = s ? (s as unknown as Record<string, number | null>) : {}
      return {
        h,
        s,
        vals: {
          ...raw,
          gesamterzeugung: s ? calcGesamterzeugung(s) : null,
          hausverbrauch:   s ? calcHausverbrauch(s)   : null,
          ...Object.fromEntries(extraSerien.map(es => [es.key, s?.komponenten?.[es.key] ?? null])),
        } as Record<string, number | null>,
      }
    })
    if (!sortKey) return all
    return [...all].sort((a, b) => {
      const av = a.vals[sortKey] ?? (sortDir === 'desc' ? -Infinity : Infinity)
      const bv = b.vals[sortKey] ?? (sortDir === 'desc' ? -Infinity : Infinity)
      return sortDir === 'asc' ? av - bv : bv - av
    })
  }, [daten, sortKey, sortDir, extraSerien])

  // Aktive Spalten in Reihenfolge: TD_COLUMNS + extra Serien (eingebettet in Gruppe)
  const allCols = useMemo(() => {
    const cols: (TdColDef | (SerieInfo & { unit: string; decimals: number; isSum: boolean; group: TdGroup }))[] = []
    for (const c of TD_COLUMNS) {
      cols.push(c)
      if (c.key === 'batterie_kw') extraErzeuger.forEach(es => cols.push({ ...es, unit: 'kW', decimals: 2, isSum: true, group: 'erzeugung' }))
      if (c.key === 'wallbox_kw') extraVerbraucher.forEach(es => cols.push({ ...es, unit: 'kW', decimals: 2, isSum: true, group: 'verbrauch' }))
    }
    return cols.filter(c => visibleCols.has(c.key))
  }, [visibleCols, extraErzeuger, extraVerbraucher])

  // Summenzeile
  const summen = useMemo(() => {
    const r: Record<string, number | null> = {}
    for (const col of allCols) {
      if (!col.isSum) { r[col.key] = null; continue }
      const vals = rows.map(row => row.vals[col.key]).filter(v => v != null) as number[]
      r[col.key] = vals.length ? vals.reduce((a, b) => a + b, 0) : null
    }
    return r
  }, [rows, allCols])

  // CSV Export
  function handleExport() {
    const headers = ['Stunde', ...allCols.map(c => c.unit ? `${c.label} (${c.unit})` : c.label)]
    const csvRows = rows.map(row => [
      `${row.h}:00`,
      ...allCols.map(c => {
        const v = row.vals[c.key]
        return v != null ? v.toFixed(c.decimals) : ''
      }),
    ])
    // Summenzeile
    csvRows.push(['Σ/kWh', ...allCols.map(c => {
      const v = summen[c.key]
      return v != null ? v.toFixed(c.decimals) : '—'
    })])
    exportToCSV(headers, csvRows, `energieprofil_${datum}.csv`)
  }

  function SortIcon({ colKey }: { colKey: string }) {
    if (sortKey !== colKey) return <ChevronsUpDown className="h-3 w-3 opacity-30 shrink-0" />
    return sortDir === 'asc'
      ? <ChevronUp className="h-3 w-3 text-primary-500 shrink-0" />
      : <ChevronDown className="h-3 w-3 text-primary-500 shrink-0" />
  }

  const dash = <span className="text-gray-300 dark:text-gray-600">—</span>
  function cell(v: number | null, dec: number) {
    return v != null ? v.toLocaleString('de-DE', { minimumFractionDigits: dec, maximumFractionDigits: dec }) : dash
  }

  return (
    <Card padding="none" className="overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-gray-200 dark:border-gray-700 flex-wrap">
        <span className="text-xs text-gray-500 dark:text-gray-400">
          Stundenwerte in kW · Σ-Zeile = kWh/Tag
        </span>
        <div className="flex items-center gap-2">
          {/* Spaltenauswahl */}
          <div className="relative" ref={pickerRef}>
            <Button variant="secondary" size="sm" onClick={() => setPickerOpen(o => !o)}>
              <Columns className="h-4 w-4 mr-1.5" />
              Spalten ({visibleCols.size})
            </Button>
            {pickerOpen && (
              <div className="absolute right-0 top-full mt-1 z-20 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3 w-56 max-h-96 overflow-y-auto">
                {TD_GROUPS.map(group => {
                  const fixedInGroup = TD_COLUMNS.filter(c => c.group === group)
                  const extraInGroup = group === 'erzeugung' ? extraErzeuger
                    : group === 'verbrauch' ? extraVerbraucher : []
                  const allInGroup = [...fixedInGroup, ...extraInGroup.map(es => ({ key: es.key, label: es.label }))]
                  return (
                    <div key={group} className="mb-3 last:mb-0">
                      <p className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide mb-1">
                        {TD_GROUP_LABELS[group]}
                      </p>
                      {allInGroup.map(c => (
                        <label key={c.key} className="flex items-center gap-2 py-0.5 cursor-pointer">
                          <input type="checkbox" className="rounded shrink-0"
                            checked={visibleCols.has(c.key)}
                            onChange={() => toggleCol(c.key)} />
                          <span className="text-xs text-gray-700 dark:text-gray-300 truncate">{c.label}</span>
                        </label>
                      ))}
                    </div>
                  )
                })}
                <button type="button"
                  onClick={() => setVisibleCols(new Set(TD_COLUMNS.filter(c => c.defaultVisible).map(c => c.key)))}
                  className="mt-1 w-full text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-center py-1">
                  Standard wiederherstellen
                </button>
              </div>
            )}
          </div>
          <Button variant="secondary" size="sm" onClick={handleExport}>
            <Download className="h-4 w-4 mr-1.5" />
            CSV
          </Button>
        </div>
      </div>

      {/* Tabelle */}
      <div className="overflow-auto max-h-[560px]">
        <table className="w-full text-xs">
          <thead className="sticky top-0 z-10 bg-gray-50 dark:bg-gray-800">
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th
                className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap cursor-pointer select-none"
                onClick={() => { setSortKey(null); setSortDir('asc') }}
              >
                <span className="flex items-center gap-1">Std {!sortKey && <ChevronUp className="h-3 w-3 text-primary-500" />}</span>
              </th>
              {allCols.map(c => (
                <th key={c.key}
                  className="px-2 py-2 text-right font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200"
                  onClick={() => handleSort(c.key)}
                >
                  <span className="flex items-center justify-end gap-1">
                    <SortIcon colKey={c.key} />
                    <span>{c.label}</span>
                  </span>
                  <span className="font-normal text-[10px] opacity-60">{c.unit}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ h, vals }) => (
              <tr key={h} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/40">
                <td className="px-3 py-1.5 font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap tabular-nums">{h}:00</td>
                {allCols.map(c => (
                  <td key={c.key} className="px-2 py-1.5 text-right tabular-nums text-gray-700 dark:text-gray-300">
                    {cell(vals[c.key], c.decimals)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 font-semibold sticky bottom-0">
              <td className="px-3 py-2 text-gray-500 dark:text-gray-400">Σ kWh</td>
              {allCols.map(c => (
                <td key={c.key} className="px-2 py-2 text-right tabular-nums text-gray-700 dark:text-gray-200">
                  {cell(summen[c.key], c.decimals)}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  )
}

const WM_FELDER = [
  { key: 'pv_kw' as const,          label: 'PV kW',      color: 'text-yellow-600 dark:text-yellow-400' },
  { key: 'verbrauch_kw' as const,    label: 'Verbr. kW',  color: 'text-gray-600 dark:text-gray-300' },
  { key: 'netzbezug_kw' as const,    label: 'Bezug kW',   color: 'text-red-600 dark:text-red-400' },
  { key: 'einspeisung_kw' as const,  label: 'Einsp. kW',  color: 'text-blue-600 dark:text-blue-400' },
  { key: 'batterie_kw' as const,     label: 'Batt. kW',   color: 'text-orange-500 dark:text-orange-400' },
]

function WochenmusterTabelle({ daten }: { daten: WochenmusterPunkt[] }) {
  // Lookup: {wochentag: {stunde: WochenmusterPunkt}}
  const lookup = new Map<number, Map<number, WochenmusterPunkt>>()
  for (const d of daten) {
    if (!lookup.has(d.wochentag)) lookup.set(d.wochentag, new Map())
    lookup.get(d.wochentag)!.set(d.stunde, d)
  }
  const verfuegbareWT = [0,1,2,3,4,5,6].filter(wt => lookup.has(wt))

  return (
    <Card>
      <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-3">
        Ø-Stundenwerte je Wochentag · alle Felder
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="text-left py-2 pr-2 font-medium text-gray-500 dark:text-gray-400 sticky left-0 bg-white dark:bg-gray-900">Std</th>
              {verfuegbareWT.map(wt => (
                <th key={wt} colSpan={WM_FELDER.length}
                  className="text-center py-2 px-2 font-medium text-gray-700 dark:text-gray-300 border-l border-gray-200 dark:border-gray-700">
                  {WOCHENTAG_KURZ[wt]}
                </th>
              ))}
            </tr>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th scope="col" className="sticky left-0 bg-white dark:bg-gray-900">Feld</th>
              {verfuegbareWT.map(wt => (
                WM_FELDER.map(f => (
                  <th key={`${wt}-${f.key}`}
                    className={`text-right py-1 px-1.5 font-normal whitespace-nowrap ${f.color} border-l first:border-l border-gray-100 dark:border-gray-800`}>
                    {f.label.split(' ')[0]}
                  </th>
                ))
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 24 }, (_, h) => (
              <tr key={h} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="py-1.5 pr-2 font-medium text-gray-600 dark:text-gray-300 sticky left-0 bg-white dark:bg-gray-900">{h}:00</td>
                {verfuegbareWT.map(wt => {
                  const p = lookup.get(wt)?.get(h)
                  return WM_FELDER.map(f => {
                    const v = p ? p[f.key] : null
                    return (
                      <td key={`${wt}-${f.key}`}
                        className="text-right py-1.5 px-1.5 tabular-nums text-gray-700 dark:text-gray-300 border-l border-gray-100 dark:border-gray-800">
                        {v != null ? v.toFixed(2) : <span className="text-gray-300 dark:text-gray-600">—</span>}
                      </td>
                    )
                  })
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

// ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

function round2(v: number): number {
  return Math.round(v * 100) / 100
}

function KpiCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2">
      <div className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">{label}</div>
      <div className={`text-sm font-semibold ${color ?? 'text-gray-900 dark:text-white'}`}>{value}</div>
    </div>
  )
}

// ─── Info-Panel ───────────────────────────────────────────────────────────────

function InfoPanel() {
  const [offen, setOffen] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)

  return (
    <div className="rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/40">
      <button
        type="button"
        onClick={() => setOffen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-blue-800 dark:text-blue-300"
      >
        <span className="flex items-center gap-2">
          <span className="text-base">ℹ</span>
          Wie werden die Daten erhoben und verdichtet?
        </span>
        <span className="text-xs opacity-60">{offen ? '▲ schließen' : '▼ anzeigen'}</span>
      </button>

      {offen && (
        <div ref={contentRef} className="px-4 pb-4 text-sm text-blue-900 dark:text-blue-200 space-y-4 border-t border-blue-200 dark:border-blue-800 pt-4">

          <div className="grid sm:grid-cols-2 gap-4">
            <section>
              <h4 className="font-semibold mb-1">Datenquellen</h4>
              <p className="text-xs leading-relaxed opacity-90">
                <strong>HA Add-on:</strong> Stündliche Mittelwerte aus der Home Assistant Sensor-History.
                HA speichert diese nur ~10 Tage — deshalb werden die Daten täglich persistent in der
                EEDC-Datenbank gespeichert.
              </p>
              <p className="text-xs leading-relaxed opacity-90 mt-1">
                <strong>Docker Standalone:</strong> MQTT Live-Snapshots werden alle 5 Minuten in der DB
                gesichert und daraus stündliche Mittelwerte berechnet. Retention: 15 Tage.
              </p>
            </section>

            <section>
              <h4 className="font-semibold mb-1">Aggregations-Zeitplan</h4>
              <ul className="text-xs leading-relaxed opacity-90 space-y-0.5">
                <li><strong>00:15 Uhr täglich</strong> — Vortag wird finalisiert (alle Stunden 0–23)</li>
                <li><strong>alle 15 Min</strong> — laufender Tag rollierend (abgeschlossene Stunden)</li>
                <li><strong>Monatsabschluss</strong> — rückwirkende Nachberechnung falls Lücken</li>
              </ul>
            </section>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <section>
              <h4 className="font-semibold mb-1">Felder erklärt</h4>
              <ul className="text-xs leading-relaxed opacity-90 space-y-0.5">
                <li><strong>PV kW</strong> — Summe aller lokalen Erzeuger (PV-Module, BKW)</li>
                <li><strong>Verbrauch kW</strong> — Gesamtverbrauch (Haushalt + WP + Wallbox + …)</li>
                <li><strong>Bezug / Einspeisung</strong> — Netto-Austausch mit dem Stromnetz</li>
                <li><strong>Batterie kW</strong> — <span className="text-orange-600 dark:text-orange-400 font-medium">positiv = Entladung</span> (Quelle), <span className="text-blue-600 dark:text-blue-400 font-medium">negativ = Ladung</span> (Senke)</li>
                <li><strong>WP / Wallbox kW</strong> — Absolut-Wert des jeweiligen Verbrauchers</li>
                <li><strong>Überschuss kW</strong> — max(0, PV − Verbrauch) je Stunde</li>
                <li><strong>Defizit kW</strong> — max(0, Verbrauch − PV) je Stunde</li>
                <li><strong>SoC %</strong> — Batterie-Ladestand (Stundenmittel)</li>
                <li><strong>Strahlung W/m²</strong> — Globalstrahlung (Open-Meteo Historical)</li>
              </ul>
            </section>

            <section>
              <h4 className="font-semibold mb-1">Wochenvergleich</h4>
              <p className="text-xs leading-relaxed opacity-90">
                Für jeden Wochentag (Mo–So) und jede Stunde wird der <strong>arithmetische
                Mittelwert</strong> aller verfügbaren Tage im gewählten Zeitraum berechnet.
                Die Zahl in Klammern hinter jedem Wochentag-Button zeigt, wie viele Tage
                in die Berechnung einfließen.
              </p>
              <p className="text-xs leading-relaxed opacity-90 mt-1">
                <strong>Empfehlung:</strong> Mindestens 4 Wochen Daten für aussagekräftige Muster.
                Ab 8 Wochen sind saisonale Einflüsse erkennbar.
              </p>
            </section>
          </div>

          <div className="text-xs opacity-70 border-t border-blue-200 dark:border-blue-700 pt-2">
            Summenzeile in der Tagesdetail-Tabelle: kW-Felder aufsummiert ergeben kWh/Tag
            (1 Stundenwert × 1h = kWh). SoC, Temperatur und Strahlung werden nicht summiert.
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Haupt-Tab ────────────────────────────────────────────────────────────────

interface EnergieprofilTabProps {
  anlageId: number
}

const MIN_TAGE = 8  // 1 Woche + 1 Tag

export function EnergieprofilTab({ anlageId }: EnergieprofilTabProps) {
  const [subTab, setSubTab] = useState<'tagesdetail' | 'wochenvergleich'>('tagesdetail')
  const [tageMitDaten, setTageMitDaten] = useState<number | null>(null)

  // Datenbestand prüfen: letzte 90 Tage abfragen und zählen
  useEffect(() => {
    if (!anlageId) return
    const bis = toISODate(new Date())
    const von = vorTagenISO(90)
    energieProfilApi.getTage(anlageId, von, bis)
      .then(tage => setTageMitDaten(tage.filter(t => t.stunden_verfuegbar > 0).length))
      .catch(() => setTageMitDaten(0))
  }, [anlageId])

  const subTabs = [
    { key: 'tagesdetail' as const, label: 'Tagesdetail' },
    { key: 'wochenvergleich' as const, label: 'Wochenvergleich' },
  ]

  // Noch nicht genug Daten → Sammelscreen
  // Fortschrittsbalken: 8 mögliche Werte (0–8 Tage), statische Tailwind-Klassen
  const PROGRESS_W = ['w-0','w-[12.5%]','w-1/4','w-[37.5%]','w-1/2','w-[62.5%]','w-3/4','w-[87.5%]','w-full']

  if (tageMitDaten !== null && tageMitDaten < MIN_TAGE) {
    const progressClass = PROGRESS_W[Math.min(tageMitDaten, MIN_TAGE)]
    return (
      <div className="space-y-4">
        <InfoPanel />
        <Card>
          <div className="py-6 text-center space-y-4 max-w-md mx-auto">
            <div className="text-4xl">📊</div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white">
              Energieprofil sammelt Daten
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Für aussagekräftige Tagesprofile und den Wochenvergleich werden mindestens{' '}
              <strong>{MIN_TAGE} Tage</strong> mit vollständigen Stundenwerten benötigt.
            </p>
            {/* Fortschrittsbalken */}
            <div className="space-y-1">
              <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
                <span>{tageMitDaten} von {MIN_TAGE} Tagen</span>
                <span>{Math.round(tageMitDaten / MIN_TAGE * 100)} %</span>
              </div>
              <div className="h-2.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div className={`h-full bg-primary-500 rounded-full transition-all ${progressClass}`} />
              </div>
            </div>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              Stundenwerte werden täglich um 00:15 Uhr für den Vortag gespeichert
              und alle 15 Minuten für den laufenden Tag aktualisiert.
            </p>
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Info-Panel */}
      <InfoPanel />

      {/* Sub-Tab-Navigation */}
      <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 w-fit">
        {subTabs.map(t => (
          <button
            type="button"
            key={t.key}
            onClick={() => setSubTab(t.key)}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
              subTab === t.key
                ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {subTab === 'tagesdetail' && <Tagesdetail anlageId={anlageId} />}
      {subTab === 'wochenvergleich' && <Wochenvergleich anlageId={anlageId} />}
    </div>
  )
}
