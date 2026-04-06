// Energieprofil-Tab — Tagesdetail + Wochenvergleich
// Etappe 2: Auswertung persistierter Stundenwerte aus TagesEnergieProfil
import { useState, useEffect, useMemo } from 'react'
import {
  ComposedChart, Area, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import ChartTooltip from '../../components/ui/ChartTooltip'
import { Card } from '../../components/ui'
import { energieProfilApi, type StundenWert, type WochenmusterPunkt } from '../../api/energie_profil'

// ─── Konstanten ───────────────────────────────────────────────────────────────

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
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!anlageId || !datum) return
    setLoading(true)
    energieProfilApi.getStunden(anlageId, datum)
      .then(setDaten)
      .catch(() => setDaten([]))
      .finally(() => setLoading(false))
  }, [anlageId, datum])

  const chartDaten = useMemo(() =>
    Array.from({ length: 24 }, (_, h) => {
      const s = daten.find(d => d.stunde === h)
      return {
        stunde: `${h}:00`,
        pv: s?.pv_kw ?? null,
        verbrauch: s?.verbrauch_kw != null ? -s.verbrauch_kw : null,
        netzbezug: s?.netzbezug_kw ?? null,
        einspeisung: s?.einspeisung_kw != null ? -s.einspeisung_kw : null,
        batterie: s?.batterie_kw ?? null,
        soc: s?.soc_prozent ?? null,
        temp: s?.temperatur_c ?? null,
      }
    }), [daten])

  // KPIs aus Stundenwerten
  const kpis = useMemo(() => {
    if (!daten.length) return null
    const pvKwh = daten.reduce((s, d) => s + (d.pv_kw ?? 0), 0)
    const vKwh = daten.reduce((s, d) => s + (d.verbrauch_kw ?? 0), 0)
    const netzbezugKwh = daten.reduce((s, d) => s + (d.netzbezug_kw ?? 0), 0)
    const einspeisungKwh = daten.reduce((s, d) => s + (d.einspeisung_kw ?? 0), 0)
    const ueberschussKwh = daten.reduce((s, d) => s + (d.ueberschuss_kw ?? 0), 0)
    const autarkie = vKwh > 0 ? Math.min(100, (1 - netzbezugKwh / vKwh) * 100) : null
    const tempMin = Math.min(...daten.filter(d => d.temperatur_c != null).map(d => d.temperatur_c!))
    const tempMax = Math.max(...daten.filter(d => d.temperatur_c != null).map(d => d.temperatur_c!))
    return { pvKwh, vKwh, netzbezugKwh, einspeisungKwh, ueberschussKwh, autarkie, tempMin, tempMax }
  }, [daten])

  return (
    <div className="space-y-4">
      {/* Datum-Picker */}
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Tag:</label>
        <input
          type="date"
          aria-label="Tag auswählen"
          value={datum}
          max={gesternISO()}
          onChange={e => setDatum(e.target.value)}
          className="input w-auto text-sm"
        />
        {loading && <span className="text-xs text-gray-400">Lade…</span>}
      </div>

      {/* KPI-Zeile */}
      {kpis && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <KpiCard label="PV-Ertrag" value={`${fmt1(kpis.pvKwh)} kWh`} color="text-yellow-600 dark:text-yellow-400" />
          <KpiCard label="Verbrauch" value={`${fmt1(kpis.vKwh)} kWh`} color="text-gray-600 dark:text-gray-300" />
          <KpiCard label="Netzbezug" value={`${fmt1(kpis.netzbezugKwh)} kWh`} color="text-red-600 dark:text-red-400" />
          <KpiCard label="Einspeisung" value={`${fmt1(kpis.einspeisungKwh)} kWh`} color="text-blue-600 dark:text-blue-400" />
          <KpiCard label="Überschuss" value={`${fmt1(kpis.ueberschussKwh)} kWh`} color="text-green-600 dark:text-green-400" />
          <KpiCard label="Autarkie" value={kpis.autarkie != null ? `${fmt0(kpis.autarkie)} %` : '—'} color="text-primary-600 dark:text-primary-400" />
          <KpiCard label="Temperatur" value={kpis.tempMin !== Infinity ? `${fmt1(kpis.tempMin)} / ${fmt1(kpis.tempMax)} °C` : '—'} color="text-orange-600 dark:text-orange-400" />
        </div>
      )}

      {/* Chart */}
      {daten.length === 0 && !loading ? (
        <Card className="text-center py-10 text-gray-400 dark:text-gray-500 text-sm">
          Keine Daten für diesen Tag vorhanden.
        </Card>
      ) : (
        <Card>
          <div className="text-xs text-gray-500 dark:text-gray-400 mb-3">
            Leistung in kW · positiv = Erzeugung/Bezug · negativ = Verbrauch/Einspeisung
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={chartDaten} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.15)" />
              <XAxis dataKey="stunde" tick={{ fontSize: 11 }} interval={2} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${v}`} />
              <ReferenceLine y={0} stroke="rgba(128,128,128,0.4)" />
              <Tooltip content={<ChartTooltip unit=" kW" decimals={2} />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area dataKey="pv" name="PV" fill="#fef08a" stroke="#eab308" fillOpacity={0.5} dot={false} connectNulls />
              <Bar dataKey="netzbezug" name="Netzbezug" fill="#ef4444" fillOpacity={0.7} />
              <Bar dataKey="einspeisung" name="Einspeisung" fill="#3b82f6" fillOpacity={0.7} />
              <Bar dataKey="batterie" name="Batterie" fill="#f97316" fillOpacity={0.7} />
              <Line dataKey="verbrauch" name="Verbrauch" stroke="#6b7280" strokeWidth={2} dot={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </Card>
      )}
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
    </div>
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
