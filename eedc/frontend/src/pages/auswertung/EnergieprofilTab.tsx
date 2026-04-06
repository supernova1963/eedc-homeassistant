// Energieprofil-Tab — Tagesdetail + Wochenvergleich
// Etappe 2: Auswertung persistierter Stundenwerte aus TagesEnergieProfil
import { useState, useEffect, useMemo, useRef } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import ChartTooltip from '../../components/ui/ChartTooltip'
import { Card } from '../../components/ui'
import { energieProfilApi, type StundenWert, type SerieInfo, type WochenmusterPunkt } from '../../api/energie_profil'

// Kategorien die bereits dedizierte Spalten/Felder haben → kein Extra-Tracking
const DEDIZIERTE_KATEGORIEN = new Set(['pv', 'batterie', 'netz', 'haushalt', 'waermepumpe', 'wallbox', 'eauto', 'virtual'])

// Farben für extra Sonstiges-Serien (Rotation) — hex für Recharts, Tailwind-Klassen für Tabelle
const EXTRA_FARBEN = ['#8b5cf6', '#06b6d4', '#84cc16', '#f43f5e', '#fb923c', '#a78bfa']
const EXTRA_FARBEN_CSS = [
  'text-violet-500 dark:text-violet-400',
  'text-cyan-500 dark:text-cyan-400',
  'text-lime-500 dark:text-lime-400',
  'text-rose-500 dark:text-rose-400',
  'text-orange-400 dark:text-orange-300',
  'text-purple-400 dark:text-purple-300',
]

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
      {daten.length > 0 && <TagesdetailTabelle daten={daten} extraSerien={extraSerien} />}
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
                  ? 'border-transparent text-white'
                  : 'border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 bg-transparent'
              }`}
              style={aktiv ? { backgroundColor: GRUPPEN_FARBEN[g.label] } : {}}
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

// ── Feste Tabellenspalten (Reihenfolge: Erzeugung | Netz | Verbrauch | Bilanz | Wetter)
// Berechnete Spalten 'gesamterzeugung' und 'hausverbrauch' werden dynamisch ergänzt
const TD_COLS = [
  // Erzeugung
  { key: 'pv_kw',              label: 'PV',            unit: 'kW',   color: 'text-yellow-500 dark:text-yellow-400', sum: true },
  { key: 'batterie_kw',        label: 'Batterie',       unit: 'kW',   color: 'text-orange-500 dark:text-orange-400', sum: true },
  // Netz
  { key: 'netzbezug_kw',       label: 'Netzbezug',     unit: 'kW',   color: 'text-red-600 dark:text-red-400',    sum: true },
  { key: 'einspeisung_kw',     label: 'Einspeisung',   unit: 'kW',   color: 'text-blue-600 dark:text-blue-400',  sum: true },
  // Verbrauch
  { key: 'verbrauch_kw',       label: 'Gesamtverbr.',  unit: 'kW',   color: 'text-gray-600 dark:text-gray-300',  sum: true },
  { key: 'waermepumpe_kw',     label: 'WP',            unit: 'kW',   color: 'text-purple-600 dark:text-purple-400', sum: true },
  { key: 'wallbox_kw',         label: 'Wallbox',       unit: 'kW',   color: 'text-violet-600 dark:text-violet-400', sum: true },
  // Bilanz
  { key: 'ueberschuss_kw',     label: 'Überschuss',    unit: 'kW',   color: 'text-green-600 dark:text-green-400', sum: true },
  { key: 'defizit_kw',         label: 'Defizit',       unit: 'kW',   color: 'text-rose-600 dark:text-rose-400',  sum: true },
  // Qualität
  { key: 'soc_prozent',        label: 'SoC',           unit: '%',    color: 'text-cyan-600 dark:text-cyan-400',  sum: false },
  { key: 'temperatur_c',       label: 'Temp',          unit: '°C',   color: 'text-amber-600 dark:text-amber-400', sum: false },
  { key: 'globalstrahlung_wm2',label: 'Strahlung',     unit: 'W/m²', color: 'text-yellow-400 dark:text-yellow-300', sum: false },
] as const

type TdColKey = typeof TD_COLS[number]['key']

function TagesdetailTabelle({ daten, extraSerien }: { daten: StundenWert[], extraSerien: SerieInfo[] }) {
  const extraErzeuger    = extraSerien.filter(s => s.seite === 'quelle')
  const extraVerbraucher = extraSerien.filter(s => s.seite === 'senke')

  // Berechnete Werte pro Stunde
  function gesamterzeugung(s: StundenWert): number {
    const erzSonstige = extraErzeuger.reduce((a, es) => a + Math.max(0, s.komponenten?.[es.key] ?? 0), 0)
    return round2((s.pv_kw ?? 0) + Math.max(0, s.batterie_kw ?? 0) + erzSonstige)
  }
  function hausverbrauch(s: StundenWert): number {
    const vbrSonstige = extraVerbraucher.reduce((a, es) => a + Math.abs(Math.min(0, s.komponenten?.[es.key] ?? 0)), 0)
    return round2(Math.max(0, (s.verbrauch_kw ?? 0) - (s.waermepumpe_kw ?? 0) - (s.wallbox_kw ?? 0) - vbrSonstige))
  }

  // Summen
  const summen: Partial<Record<TdColKey, number>> = {}
  for (const col of TD_COLS) {
    if (!col.sum) continue
    const vals = daten.map(d => (d as unknown as Record<string, number | null>)[col.key]).filter(v => v != null) as number[]
    if (vals.length) summen[col.key] = vals.reduce((a, b) => a + b, 0)
  }
  const sumGesamterz  = daten.reduce((a, d) => a + gesamterzeugung(d), 0)
  const sumHausverbr  = daten.reduce((a, d) => a + hausverbrauch(d), 0)
  const extraSummen: Record<string, number> = {}
  for (const serie of extraSerien) {
    const vals = daten.map(d => d.komponenten?.[serie.key] ?? null).filter(v => v != null) as number[]
    if (vals.length) extraSummen[serie.key] = vals.reduce((a, b) => a + b, 0)
  }

  const tdCell = (v: number | null, dec = 2) => v != null
    ? v.toFixed(dec)
    : <span className="text-gray-300 dark:text-gray-600">—</span>

  return (
    <Card>
      <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-3">
        Stundenwerte in kW · Summenzeile = kWh/Tag
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b-2 border-gray-200 dark:border-gray-700">
              <th className="text-left py-2 pr-3 font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap">Std</th>

              {/* Berechnete Spalten: Gesamterzeugung + Hausverbrauch — direkt nach PV/Verbrauch */}
              <th className="text-right py-2 px-2 font-semibold whitespace-nowrap text-yellow-600 dark:text-yellow-400">
                Ges.erz.<br /><span className="font-normal opacity-70">kW</span>
              </th>
              {TD_COLS.slice(0, 2).map(c => (   /* PV + Batterie */
                <th key={c.key} className={`text-right py-2 px-2 font-medium whitespace-nowrap ${c.color}`}>
                  {c.label}<br /><span className="font-normal opacity-70">{c.unit}</span>
                </th>
              ))}
              {extraErzeuger.map((s, i) => (
                <th key={s.key} className={`text-right py-2 px-2 font-medium whitespace-nowrap ${EXTRA_FARBEN_CSS[i % EXTRA_FARBEN_CSS.length]}`}>
                  {s.label}<br /><span className="font-normal opacity-70">kW</span>
                </th>
              ))}
              {TD_COLS.slice(2, 4).map(c => (   /* Netzbezug + Einspeisung */
                <th key={c.key} className={`text-right py-2 px-2 font-medium whitespace-nowrap ${c.color}`}>
                  {c.label}<br /><span className="font-normal opacity-70">{c.unit}</span>
                </th>
              ))}
              <th className="text-right py-2 px-2 font-semibold whitespace-nowrap text-emerald-600 dark:text-emerald-400 border-l border-gray-200 dark:border-gray-700">
                Hausverbr.<br /><span className="font-normal opacity-70">kW</span>
              </th>
              {TD_COLS.slice(4).map(c => (      /* Gesamtverbr., WP, Wallbox, Bilanz, Qualität */
                <th key={c.key} className={`text-right py-2 px-2 font-medium whitespace-nowrap ${c.color}`}>
                  {c.label}<br /><span className="font-normal opacity-70">{c.unit}</span>
                </th>
              ))}
              {extraVerbraucher.map((s, i) => (
                <th key={s.key} className={`text-right py-2 px-2 font-medium whitespace-nowrap ${EXTRA_FARBEN_CSS[(extraErzeuger.length + i) % EXTRA_FARBEN_CSS.length]}`}>
                  {s.label}<br /><span className="font-normal opacity-70">kW</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 24 }, (_, h) => {
              const s = daten.find(d => d.stunde === h)
              return (
                <tr key={h} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="py-1.5 pr-3 font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap">{h}:00</td>
                  <td className="text-right py-1.5 px-2 tabular-nums text-yellow-600 dark:text-yellow-400 font-medium">
                    {s ? tdCell(gesamterzeugung(s)) : tdCell(null)}
                  </td>
                  {TD_COLS.slice(0, 2).map(c => {
                    const v = s ? (s as unknown as Record<string, number | null>)[c.key] : null
                    return <td key={c.key} className="text-right py-1.5 px-2 tabular-nums text-gray-700 dark:text-gray-300">{tdCell(v, c.unit === 'W/m²' ? 0 : 2)}</td>
                  })}
                  {extraErzeuger.map(es => (
                    <td key={es.key} className="text-right py-1.5 px-2 tabular-nums text-gray-700 dark:text-gray-300">
                      {tdCell(s?.komponenten?.[es.key] ?? null)}
                    </td>
                  ))}
                  {TD_COLS.slice(2, 4).map(c => {
                    const v = s ? (s as unknown as Record<string, number | null>)[c.key] : null
                    return <td key={c.key} className="text-right py-1.5 px-2 tabular-nums text-gray-700 dark:text-gray-300">{tdCell(v)}</td>
                  })}
                  <td className="text-right py-1.5 px-2 tabular-nums text-emerald-600 dark:text-emerald-400 font-medium border-l border-gray-100 dark:border-gray-800">
                    {s ? tdCell(hausverbrauch(s)) : tdCell(null)}
                  </td>
                  {TD_COLS.slice(4).map(c => {
                    const v = s ? (s as unknown as Record<string, number | null>)[c.key] : null
                    return <td key={c.key} className="text-right py-1.5 px-2 tabular-nums text-gray-700 dark:text-gray-300">{tdCell(v, c.unit === 'W/m²' || c.unit === '%' ? (c.unit === 'W/m²' ? 0 : 1) : 2)}</td>
                  })}
                  {extraVerbraucher.map(es => (
                    <td key={es.key} className="text-right py-1.5 px-2 tabular-nums text-gray-700 dark:text-gray-300">
                      {tdCell(s?.komponenten?.[es.key] ?? null)}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-gray-300 dark:border-gray-600 font-semibold">
              <td className="py-2 pr-3 text-gray-500 dark:text-gray-400">Σ kWh</td>
              <td className="text-right py-2 px-2 tabular-nums text-yellow-600 dark:text-yellow-400">{sumGesamterz.toFixed(2)}</td>
              {TD_COLS.slice(0, 2).map(c => (
                <td key={c.key} className={`text-right py-2 px-2 tabular-nums ${c.color}`}>
                  {c.sum && summen[c.key] != null ? summen[c.key]!.toFixed(2) : <span className="text-gray-300 dark:text-gray-600">—</span>}
                </td>
              ))}
              {extraErzeuger.map(es => (
                <td key={es.key} className="text-right py-2 px-2 tabular-nums text-violet-600 dark:text-violet-400">
                  {extraSummen[es.key] != null ? extraSummen[es.key].toFixed(2) : <span className="text-gray-300 dark:text-gray-600">—</span>}
                </td>
              ))}
              {TD_COLS.slice(2, 4).map(c => (
                <td key={c.key} className={`text-right py-2 px-2 tabular-nums ${c.color}`}>
                  {c.sum && summen[c.key] != null ? summen[c.key]!.toFixed(2) : <span className="text-gray-300 dark:text-gray-600">—</span>}
                </td>
              ))}
              <td className="text-right py-2 px-2 tabular-nums text-emerald-600 dark:text-emerald-400 border-l border-gray-200 dark:border-gray-700">{sumHausverbr.toFixed(2)}</td>
              {TD_COLS.slice(4).map(c => (
                <td key={c.key} className={`text-right py-2 px-2 tabular-nums ${c.color}`}>
                  {c.sum && summen[c.key] != null ? summen[c.key]!.toFixed(2) : <span className="text-gray-300 dark:text-gray-600">—</span>}
                </td>
              ))}
              {extraVerbraucher.map(es => (
                <td key={es.key} className="text-right py-2 px-2 tabular-nums text-violet-600 dark:text-violet-400">
                  {extraSummen[es.key] != null ? extraSummen[es.key].toFixed(2) : <span className="text-gray-300 dark:text-gray-600">—</span>}
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

export function EnergieprofilTab({ anlageId }: EnergieprofilTabProps) {
  const [subTab, setSubTab] = useState<'tagesdetail' | 'wochenvergleich'>('tagesdetail')

  const subTabs = [
    { key: 'tagesdetail' as const, label: 'Tagesdetail' },
    { key: 'wochenvergleich' as const, label: 'Wochenvergleich' },
  ]

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
