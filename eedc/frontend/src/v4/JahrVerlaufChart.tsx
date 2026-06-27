/**
 * JahrVerlaufChart — „Verlauf"-Hauptblock der Cockpit/Jahr-Sicht.
 *
 * Granularitäts-agnostisches Pendant zu {@link TagesverlaufChart}: derselbe
 * gestapelte Bilanz-Balken-Chart, hier auf die MONATE des gewählten Jahres
 * angewandt (Monat→Tage, Tag→Stunden, Jahr→Monate). Toggles identisch:
 *   • Erzeugung  — Eigenverbrauch + Einspeisung = PV · Netzbezug separat
 *   • Verbrauch  — Direktverbrauch + Speicher-Entladung + Netzbezug = Gesamtverbrauch
 *   • Autarkie % — optionale Linie auf zweiter (%)-Achse
 *
 * Quelle: `AggregierteMonatsdaten[]` (Σ der IMD je Monat) — dieselbe SoT wie die
 * Bilanz-Vergleichsspalten, damit Chart und Zahlen nie auseinanderlaufen.
 */
import { useMemo, useState } from 'react'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { ChartTooltip, ChartLegende } from '../components/ui'
import { CHART_COLORS, MONAT_KURZ, CHART_HOVER_CURSOR, xAchse, yAchse } from '../lib'
import { useSchmaleAchse } from '../hooks'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'

type BilanzView = 'erzeugung' | 'verbrauch'

interface ChartPunkt {
  monat: string
  eigenverbrauch: number
  einspeisung: number
  netzbezug: number
  direktverbrauch: number
  speicherEntladung: number
  autarkie: number | null
}

const round1 = (v: number | null | undefined): number => (v == null ? 0 : Math.round(v * 10) / 10)

/** Pro Monat des Jahres die Bilanz-Werte (aufsteigend nach Monat). */
export function baueJahrChartDaten(monate: AggregierteMonatsdaten[]): ChartPunkt[] {
  return [...monate]
    .sort((a, b) => a.monat - b.monat)
    .map((m) => ({
      monat: MONAT_KURZ[m.monat],
      eigenverbrauch: round1(m.eigenverbrauch_kwh),
      einspeisung: round1(m.einspeisung_kwh),
      netzbezug: round1(m.netzbezug_kwh),
      direktverbrauch: round1(m.direktverbrauch_kwh),
      speicherEntladung: round1(m.speicher_entladung_kwh),
      autarkie: m.autarkie_prozent != null ? round1(m.autarkie_prozent) : null,
    }))
}

export function JahrVerlaufChart({ monate }: { monate: AggregierteMonatsdaten[] }) {
  const schmal = useSchmaleAchse()
  const [view, setView] = useState<BilanzView>('erzeugung')
  const [showAutarkie, setShowAutarkie] = useState(false)
  const daten = useMemo(() => baueJahrChartDaten(monate), [monate])

  if (monate.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Monatsdaten im Jahr.</p>
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          {(['erzeugung', 'verbrauch'] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              className={`min-h-[36px] px-3 text-sm font-medium transition-colors ${
                view === v
                  ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                  : 'text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800'
              }`}
            >
              {v === 'erzeugung' ? 'Erzeugung' : 'Verbrauch'}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setShowAutarkie((s) => !s)}
          className={`min-h-[36px] px-3 text-sm font-medium rounded-lg border transition-colors ${
            showAutarkie
              ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
              : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800'
          }`}
        >
          Autarkie %
        </button>
      </div>

      <p className="text-xs text-gray-400 dark:text-gray-500">
        {view === 'erzeugung'
          ? 'Gestapelt: Eigenverbrauch + Einspeisung = PV-Erzeugung'
          : 'Gestapelt: Direktverbrauch + Speicher-Entladung + Netzbezug = Gesamtverbrauch'}
      </p>

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={daten} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            <XAxis dataKey="monat" {...xAchse(schmal)} />
            <YAxis yAxisId="kwh" {...yAchse(schmal, 48)} unit=" kWh" />
            {showAutarkie && (
              <YAxis yAxisId="pct" orientation="right" domain={[0, 100]} {...yAchse(schmal, 40)} unit=" %" />
            )}
            <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip formatter={(value: number, name: string) =>
              name === 'Autarkie' ? `${value.toFixed(1)} %` : `${value.toFixed(1)} kWh`} />} />
            <Legend wrapperStyle={{ fontSize: 12 }} content={<ChartLegende />} />

            {view === 'erzeugung' ? (
              <>
                <Bar yAxisId="kwh" dataKey="eigenverbrauch" name="Eigenverbrauch" stackId="pv" fill={CHART_COLORS.eigenverbrauch} />
                <Bar yAxisId="kwh" dataKey="einspeisung" name="Einspeisung" stackId="pv" fill={CHART_COLORS.einspeisung} />
                <Bar yAxisId="kwh" dataKey="netzbezug" name="Netzbezug" fill={CHART_COLORS.netzbezug} />
              </>
            ) : (
              <>
                <Bar yAxisId="kwh" dataKey="direktverbrauch" name="Direktverbrauch" stackId="vb" fill={CHART_COLORS.direktverbrauch} />
                <Bar yAxisId="kwh" dataKey="speicherEntladung" name="Speicher-Entladung" stackId="vb" fill={CHART_COLORS.speicherEntladung} />
                <Bar yAxisId="kwh" dataKey="netzbezug" name="Netzbezug" stackId="vb" fill={CHART_COLORS.netzbezug} />
                <Bar yAxisId="kwh" dataKey="einspeisung" name="Einspeisung" fill={CHART_COLORS.einspeisung} />
              </>
            )}

            {showAutarkie && (
              <Line yAxisId="pct" type="monotone" dataKey="autarkie" name="Autarkie" stroke={CHART_COLORS.autarkie} strokeWidth={2} dot={false} connectNulls />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
