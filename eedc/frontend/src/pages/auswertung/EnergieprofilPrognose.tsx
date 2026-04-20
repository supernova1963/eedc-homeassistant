/**
 * Energieprofil Prognose — Etappe 3b Phase A
 *
 * Kombinierte Verbrauchs- + PV-Prognose für einen Tag mit Batterie-Simulation.
 * Zeigt: Stunden-Chart (PV vs. Verbrauch vs. Netto), SoC-Overlay, KPI-Cards.
 */
import { useState, useEffect, useMemo } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { Calendar, Battery, Zap, Sun, ArrowDown, ArrowUp, Info } from 'lucide-react'
import { Card, Alert } from '../../components/ui'
import { energieProfilApi, type TagesPrognose } from '../../api/energie_profil'

interface Props {
  anlageId: number
}

function morgenISO(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return d.toISOString().slice(0, 10)
}

function heuteISO(): string {
  return new Date().toISOString().slice(0, 10)
}

function fmt1(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toFixed(1)
}

function fmt0(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toFixed(0)
}

const VERBRAUCH_BASIS_LABELS: Record<string, string> = {
  gleicher_wochentag: 'Gleicher Wochentag',
  tagestyp: 'Werktag/Wochenende',
  alle: 'Alle Tage',
}

const PV_QUELLE_LABELS: Record<string, string> = {
  openmeteo: 'Open-Meteo (kalibriert)',
  solcast: 'Solcast',
}

export function EnergieprofilPrognose({ anlageId }: Props) {
  const [datum, setDatum] = useState(morgenISO())
  const [daten, setDaten] = useState<TagesPrognose | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!anlageId || !datum) return
    setLoading(true)
    setError(null)
    energieProfilApi.getTagesprognose(anlageId, datum)
      .then(setDaten)
      .catch(err => {
        setDaten(null)
        const detail = err?.response?.data?.detail || err?.message || 'Fehler beim Laden'
        setError(detail)
      })
      .finally(() => setLoading(false))
  }, [anlageId, datum])

  // Chart-Daten
  const chartDaten = useMemo(() => {
    if (!daten) return []
    return daten.stunden.map(s => ({
      stunde: `${s.stunde}:00`,
      pv: s.pv_kw,
      verbrauch: -s.verbrauch_kw,  // negativ für Senken-Darstellung
      netto: s.netto_kw,
      netzbezug: s.netzbezug_kw > 0 ? -s.netzbezug_kw : null,
      einspeisung: s.einspeisung_kw > 0 ? s.einspeisung_kw : null,
      soc: s.soc_prozent,
    }))
  }, [daten])

  const hatSpeicher = daten?.speicher_kapazitaet_kwh != null

  // Max-Datum: 14 Tage in die Zukunft
  const maxDatum = useMemo(() => {
    const d = new Date()
    d.setDate(d.getDate() + 14)
    return d.toISOString().slice(0, 10)
  }, [])

  return (
    <div className="space-y-4">
      {/* Datum-Picker */}
      <div className="flex items-center gap-3 flex-wrap">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Prognose für:</label>
        <input
          type="date"
          aria-label="Prognose-Datum"
          value={datum}
          min={heuteISO()}
          max={maxDatum}
          onChange={e => setDatum(e.target.value)}
          className="input w-auto text-sm"
        />
        <button
          type="button"
          onClick={() => setDatum(morgenISO())}
          className={`px-2 py-1 text-xs rounded font-medium transition-colors ${
            datum === morgenISO()
              ? 'bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300'
              : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
          }`}
        >
          Morgen
        </button>
        {loading && <span className="text-xs text-gray-400">Lade...</span>}
      </div>

      {/* Error */}
      {error && (
        <Alert type="warning">{error}</Alert>
      )}

      {/* KPI-Cards */}
      {daten && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
            <KpiCard
              icon={<Sun className="h-4 w-4 text-yellow-500" />}
              label="PV-Prognose"
              value={`${fmt1(daten.pv_summe_kwh)} kWh`}
              color="text-yellow-600 dark:text-yellow-400"
            />
            <KpiCard
              icon={<Zap className="h-4 w-4 text-gray-500" />}
              label="Verbrauch"
              value={`${fmt1(daten.verbrauch_summe_kwh)} kWh`}
              color="text-gray-600 dark:text-gray-300"
            />
            <KpiCard
              icon={<ArrowDown className="h-4 w-4 text-red-500" />}
              label="Netzbezug"
              value={`${fmt1(daten.netzbezug_summe_kwh)} kWh`}
              color="text-red-600 dark:text-red-400"
            />
            <KpiCard
              icon={<ArrowUp className="h-4 w-4 text-cyan-500" />}
              label="Einspeisung"
              value={`${fmt1(daten.einspeisung_summe_kwh)} kWh`}
              color="text-cyan-600 dark:text-cyan-400"
            />
            <KpiCard
              icon={<Sun className="h-4 w-4 text-green-500" />}
              label="Eigenverbrauch"
              value={`${fmt1(daten.eigenverbrauch_kwh)} kWh`}
              color="text-green-600 dark:text-green-400"
            />
            <KpiCard
              icon={<Zap className="h-4 w-4 text-primary-500" />}
              label="Autarkie"
              value={`${fmt0(daten.autarkie_prozent)} %`}
              color="text-primary-600 dark:text-primary-400"
            />
            {hatSpeicher && (
              <KpiCard
                icon={<Battery className="h-4 w-4 text-blue-500" />}
                label="Speicher voll"
                value={daten.speicher_voll_um ?? 'nicht erreicht'}
                color="text-blue-600 dark:text-blue-400"
              />
            )}
          </div>

          {/* Chart */}
          <Card>
            <div className="text-[10px] text-gray-400 dark:text-gray-500 mb-1 flex justify-between">
              <span>PV-Prognose: {PV_QUELLE_LABELS[daten.pv_quelle] ?? daten.pv_quelle}</span>
              <span>
                Verbrauch: {VERBRAUCH_BASIS_LABELS[daten.verbrauch_basis] ?? daten.verbrauch_basis}
                {' '}({daten.daten_tage} Tage)
              </span>
            </div>
            <ResponsiveContainer width="100%" height={360}>
              <ComposedChart data={chartDaten} margin={{ top: 5, right: hatSpeicher ? 50 : 10, left: -10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                <XAxis dataKey="stunde" tick={{ fontSize: 11 }} interval={2} />
                <YAxis
                  yAxisId="kw"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v: number) => `${v.toFixed(1)}`}
                  label={{ value: 'kW', angle: -90, position: 'insideLeft', style: { fontSize: 10 } }}
                />
                {hatSpeicher && (
                  <YAxis
                    yAxisId="soc"
                    orientation="right"
                    domain={[0, 100]}
                    tick={{ fontSize: 10 }}
                    tickFormatter={(v: number) => `${v}%`}
                    label={{ value: 'SoC', angle: 90, position: 'insideRight', style: { fontSize: 10 } }}
                  />
                )}
                <ReferenceLine yAxisId="kw" y={0} stroke="#9ca3af" strokeWidth={1.5} />
                <Tooltip content={<PrognoseTooltip hatSpeicher={hatSpeicher} />} />
                <Legend wrapperStyle={{ fontSize: 11 }} />

                {/* PV-Erzeugung (oben, gelb) */}
                <Area
                  yAxisId="kw"
                  type="monotone"
                  dataKey="pv"
                  name="PV-Prognose"
                  fill="#eab308"
                  stroke="#eab308"
                  fillOpacity={0.3}
                  strokeWidth={2}
                  isAnimationActive={false}
                />

                {/* Einspeisung (oben, cyan) */}
                <Area
                  yAxisId="kw"
                  type="monotone"
                  dataKey="einspeisung"
                  name="Einspeisung"
                  fill="#06b6d4"
                  stroke="#06b6d4"
                  fillOpacity={0.2}
                  strokeWidth={1}
                  strokeDasharray="4 2"
                  isAnimationActive={false}
                />

                {/* Verbrauch (unten, grau-grün) */}
                <Area
                  yAxisId="kw"
                  type="monotone"
                  dataKey="verbrauch"
                  name="Verbrauch"
                  fill="#6b7280"
                  stroke="#6b7280"
                  fillOpacity={0.25}
                  strokeWidth={2}
                  isAnimationActive={false}
                />

                {/* Netzbezug (unten, rot) */}
                <Area
                  yAxisId="kw"
                  type="monotone"
                  dataKey="netzbezug"
                  name="Netzbezug"
                  fill="#ef4444"
                  stroke="#ef4444"
                  fillOpacity={0.2}
                  strokeWidth={1}
                  strokeDasharray="4 2"
                  isAnimationActive={false}
                />

                {/* SoC-Linie (sekundäre Y-Achse) */}
                {hatSpeicher && (
                  <Line
                    yAxisId="soc"
                    type="monotone"
                    dataKey="soc"
                    name="SoC"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </Card>

          {/* Stundentabelle */}
          <PrognoseTabelle daten={daten} />

          {/* Meta-Info */}
          <div className="flex items-start gap-2 text-xs text-gray-400 dark:text-gray-500">
            <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span>
              Verbrauchsprognose basiert auf dem Ø-Stundenprofil der letzten {daten.daten_tage} Tage
              ({VERBRAUCH_BASIS_LABELS[daten.verbrauch_basis] ?? daten.verbrauch_basis}).
              PV-Prognose: {PV_QUELLE_LABELS[daten.pv_quelle] ?? daten.pv_quelle}.
              {hatSpeicher && ` Batterie-Simulation: ${fmt1(daten.speicher_kapazitaet_kwh)} kWh, vereinfachtes Modell ohne Wirkungsgradverluste.`}
            </span>
          </div>
        </>
      )}

      {/* Leerzustand */}
      {!daten && !loading && !error && (
        <Card className="text-center py-10 text-gray-400 dark:text-gray-500 text-sm">
          <Calendar className="h-8 w-8 mx-auto mb-2 opacity-50" />
          Wähle ein Datum für die Tagesprognose.
        </Card>
      )}
    </div>
  )
}


// ── Tooltip ──────────────────────────────────────────────────────────────────

function PrognoseTooltip({ active, payload, label }: {
  active?: boolean; payload?: Array<{ name: string; value: number; color: string }>; label?: string; hatSpeicher?: boolean
}) {
  if (!active || !payload) return null

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg px-3 py-2 text-xs">
      <p className="font-medium text-gray-900 dark:text-white mb-1">{label}</p>
      {payload.filter(p => p.value != null).map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-gray-600 dark:text-gray-400">{p.name}:</span>
          <span className="font-medium text-gray-900 dark:text-white">
            {p.name === 'SoC' ? `${p.value.toFixed(1)}%` : `${Math.abs(p.value).toFixed(2)} kW`}
          </span>
        </div>
      ))}
    </div>
  )
}


// ── KPI-Card ─────────────────────────────────────────────────────────────────

function KpiCard({ icon, label, value, color }: {
  icon: React.ReactNode; label: string; value: string; color?: string
}) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2">
      <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 mb-0.5">
        {icon}
        {label}
      </div>
      <div className={`text-sm font-semibold ${color ?? 'text-gray-900 dark:text-white'}`}>{value}</div>
    </div>
  )
}


// ── Stundentabelle ───────────────────────────────────────────────────────────

function PrognoseTabelle({ daten }: { daten: TagesPrognose }) {
  const hatSpeicher = daten.speicher_kapazitaet_kwh != null

  return (
    <Card padding="none" className="overflow-hidden">
      <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700">
        <span className="text-xs text-gray-500 dark:text-gray-400">
          Stundenprognose in kW · Summenzeile = kWh/Tag
        </span>
      </div>
      <div className="overflow-auto max-h-[500px]">
        <table className="w-full text-xs">
          <thead className="sticky top-0 z-10 bg-gray-50 dark:bg-gray-800">
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-400">Std</th>
              <th className="px-2 py-2 text-right font-medium text-yellow-600 dark:text-yellow-400">PV</th>
              <th className="px-2 py-2 text-right font-medium text-gray-600 dark:text-gray-300">Verbr.</th>
              <th className="px-2 py-2 text-right font-medium text-green-600 dark:text-green-400">Netto</th>
              <th className="px-2 py-2 text-right font-medium text-red-600 dark:text-red-400">Bezug</th>
              <th className="px-2 py-2 text-right font-medium text-cyan-600 dark:text-cyan-400">Einsp.</th>
              {hatSpeicher && (
                <th className="px-2 py-2 text-right font-medium text-blue-600 dark:text-blue-400">SoC %</th>
              )}
            </tr>
          </thead>
          <tbody>
            {daten.stunden.map(s => (
              <tr key={s.stunde} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/40">
                <td className="px-3 py-1.5 font-medium text-gray-600 dark:text-gray-300 tabular-nums">{s.stunde}:00</td>
                <td className="px-2 py-1.5 text-right tabular-nums text-yellow-700 dark:text-yellow-300">{s.pv_kw.toFixed(2)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums text-gray-700 dark:text-gray-300">{s.verbrauch_kw.toFixed(2)}</td>
                <td className={`px-2 py-1.5 text-right tabular-nums font-medium ${
                  s.netto_kw >= 0
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-red-600 dark:text-red-400'
                }`}>
                  {s.netto_kw >= 0 ? '+' : ''}{s.netto_kw.toFixed(2)}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-red-600 dark:text-red-400">
                  {s.netzbezug_kw > 0.005 ? s.netzbezug_kw.toFixed(2) : <Dash />}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums text-cyan-600 dark:text-cyan-400">
                  {s.einspeisung_kw > 0.005 ? s.einspeisung_kw.toFixed(2) : <Dash />}
                </td>
                {hatSpeicher && (
                  <td className="px-2 py-1.5 text-right tabular-nums text-blue-600 dark:text-blue-400">
                    {s.soc_prozent != null ? s.soc_prozent.toFixed(1) : <Dash />}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 font-semibold sticky bottom-0">
              <td className="px-3 py-2 text-gray-500 dark:text-gray-400">kWh</td>
              <td className="px-2 py-2 text-right tabular-nums text-yellow-700 dark:text-yellow-300">{daten.pv_summe_kwh.toFixed(1)}</td>
              <td className="px-2 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{daten.verbrauch_summe_kwh.toFixed(1)}</td>
              <td className={`px-2 py-2 text-right tabular-nums ${
                daten.pv_summe_kwh - daten.verbrauch_summe_kwh >= 0
                  ? 'text-green-600 dark:text-green-400'
                  : 'text-red-600 dark:text-red-400'
              }`}>
                {(daten.pv_summe_kwh - daten.verbrauch_summe_kwh).toFixed(1)}
              </td>
              <td className="px-2 py-2 text-right tabular-nums text-red-600 dark:text-red-400">{daten.netzbezug_summe_kwh.toFixed(1)}</td>
              <td className="px-2 py-2 text-right tabular-nums text-cyan-600 dark:text-cyan-400">{daten.einspeisung_summe_kwh.toFixed(1)}</td>
              {hatSpeicher && <td />}
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  )
}

function Dash() {
  return <span className="text-gray-300 dark:text-gray-600">—</span>
}
