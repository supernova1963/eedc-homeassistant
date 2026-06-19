/**
 * TagesverlaufChart — Hauptblock der Cockpit/Monat-Sicht (IA v4 E3, B4).
 *
 * Zeigt den gewählten Monat als TAGES-Verlauf (eine Säule je Tag) und schaltet
 * per Linsen-Toggle auf den aggregierten MONATS-FLUSS um. In beiden Linsen ist
 * die PV-Verteilung Eigenverbrauch/Einspeisung im Chart gesplittet: die
 * Erzeugungs-Säule ist EV (unten) + Einspeisung (oben). Hinweis (O3-Revision
 * 2026-06-18): das ersetzt NICHT die vertrauten Verteilungs-Balken in der
 * Energie-Bilanz (die bleiben wie im IST) — der Chart-Split ist zusätzlich.
 *
 * Datenquelle: `TagWerte[]` aus dem Tages-Werte-Endpoint (numerischer Zwilling
 * des Werte-Embeds, B9) — dieselbe SoT wie die Tabelle, damit Chart und Zahlen
 * nie auseinanderlaufen.
 */
import { useMemo, useState } from 'react'
import {
  ComposedChart, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { BarChart3, Workflow } from 'lucide-react'
import { ChartTooltip } from '../components/ui'
import { CHART_COLORS } from '../lib'
import type { TagWerte } from '../api/energie_profil'

export type Linse = 'verlauf' | 'fluss'

interface VerlaufPunkt {
  tag: number
  eigenverbrauch: number
  einspeisung: number
  netzbezug: number  // negativ (Senke)
}

/** Pro Tag: Erzeugung (EV+Einspeisung) nach oben, Netzbezug nach unten. */
export function baueVerlaufDaten(tage: TagWerte[]): VerlaufPunkt[] {
  return [...tage]
    .sort((a, b) => a.datum.localeCompare(b.datum))
    .map((t) => ({
      tag: Number(t.datum.slice(8, 10)),
      eigenverbrauch: round1(t.eigenverbrauch),
      einspeisung: round1(t.einspeisung),
      netzbezug: round1(-t.netzbezug),
    }))
}

interface FlussBalken {
  name: string
  eigenverbrauch: number
  einspeisung: number
  netzbezug: number
}

/** Monats-Σ: „Erzeugung" = EV+Einspeisung, „Verbrauch" = EV+Netzbezug. */
export function baueFlussDaten(tage: TagWerte[]): FlussBalken[] {
  const ev = sum(tage, (t) => t.eigenverbrauch)
  const einsp = sum(tage, (t) => t.einspeisung)
  const netz = sum(tage, (t) => t.netzbezug)
  return [
    { name: 'Erzeugung', eigenverbrauch: round1(ev), einspeisung: round1(einsp), netzbezug: 0 },
    { name: 'Verbrauch', eigenverbrauch: round1(ev), einspeisung: 0, netzbezug: round1(netz) },
  ]
}

const LINSEN: { key: Linse; label: string; icon: typeof BarChart3 }[] = [
  { key: 'verlauf', label: 'Tagesverlauf', icon: BarChart3 },
  { key: 'fluss', label: 'Monats-Fluss', icon: Workflow },
]

export function TagesverlaufChart({ tage }: { tage: TagWerte[] }) {
  const [linse, setLinse] = useState<Linse>('verlauf')
  const verlauf = useMemo(() => baueVerlaufDaten(tage), [tage])
  const fluss = useMemo(() => baueFlussDaten(tage), [tage])

  if (tage.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Tagesdaten im Monat.</p>
  }

  return (
    <div className="space-y-3">
      {/* Linsen-Toggle */}
      <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 w-fit">
        {LINSEN.map((l) => {
          const Icon = l.icon
          const aktiv = linse === l.key
          return (
            <button
              key={l.key}
              type="button"
              onClick={() => setLinse(l.key)}
              className={`min-h-[36px] flex items-center gap-1.5 px-3 rounded-md text-sm font-medium transition-colors ${
                aktiv
                  ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
              }`}
            >
              <Icon className="h-4 w-4" /> {l.label}
            </button>
          )
        })}
      </div>

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          {linse === 'verlauf' ? (
            <ComposedChart data={verlauf} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} stackOffset="sign">
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="tag" tick={{ fontSize: 12 }} />
              <YAxis width={48} tick={{ fontSize: 12 }} />
              <ReferenceLine y={0} className="stroke-gray-400 dark:stroke-gray-500" />
              <Tooltip content={<ChartTooltip unit=" kWh" decimals={1} />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="eigenverbrauch" name="Eigenverbrauch" stackId="pv" fill={CHART_COLORS.eigenverbrauch} />
              <Bar dataKey="einspeisung" name="Einspeisung" stackId="pv" fill={CHART_COLORS.einspeisung} />
              <Bar dataKey="netzbezug" name="Netzbezug" stackId="netz" fill={CHART_COLORS.netzbezug} />
            </ComposedChart>
          ) : (
            <BarChart data={fluss} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis width={48} tick={{ fontSize: 12 }} />
              <Tooltip content={<ChartTooltip unit=" kWh" decimals={1} />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="eigenverbrauch" name="Eigenverbrauch" stackId="f" fill={CHART_COLORS.eigenverbrauch} />
              <Bar dataKey="einspeisung" name="Einspeisung" stackId="f" fill={CHART_COLORS.einspeisung} />
              <Bar dataKey="netzbezug" name="Netzbezug" stackId="f" fill={CHART_COLORS.netzbezug} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function round1(v: number): number {
  return Math.round(v * 10) / 10
}

function sum(tage: TagWerte[], f: (t: TagWerte) => number): number {
  return tage.reduce((s, t) => s + (f(t) || 0), 0)
}
