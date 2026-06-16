/**
 * CockpitV4 — erste ECHTE IA-v4-Sicht (E3 Slice 1).
 *
 * Achse „Cockpit", Zeit „Monat": aus dem promovierten {@link BlockShell}-Modell
 * zusammengesetzt, gespeist aus dem BESTEHENDEN echten Cockpit-Datenpfad
 * (`cockpitApi.getUebersicht` + `monatsdatenApi.listAggregiert` — wie
 * `pages/Dashboard.tsx`). KEINE Dummies, KEINE Mock-Schicht: in der Vorschau
 * gegen die Demo-DB der Dev-Box liefert der relative API-Pfad echte Daten.
 *
 * Slice 1 verdrahtet bewusst nur „Monat" real (KPI-Strip + EIN Monatschart);
 * die übrigen Zeit-Achsen zeigen einen Hinweis, bis ihre echten Sichten folgen.
 */
import { useEffect, useState } from 'react'
import { useParams, NavLink } from 'react-router-dom'
import {
  BarChart, Bar, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import {
  Sun, Activity, Zap, ArrowUpFromLine, Euro, LineChart,
} from 'lucide-react'
import { LoadingSpinner, Card, ChartTooltip } from '../components/ui'
import { BlockShell, KpiStrip } from '../components/blocks'
import type { Block } from '../components/blocks'
import type { KpiStripItem } from '../components/blocks/KpiStrip'
import { useSelectedAnlage } from '../hooks'
import { MONAT_KURZ, CHART_COLORS } from '../lib'
import { cockpitApi, type CockpitUebersicht } from '../api/cockpit'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'

const ZEITEN: { key: string; label: string }[] = [
  { key: 'live', label: 'Live' },
  { key: 'tag', label: 'Tag' },
  { key: 'monat', label: 'Monat' },
  { key: 'jahr', label: 'Jahr/Gesamt' },
  { key: 'aussicht', label: 'Aussicht' },
]

// KPI-Strip aus dem echten CockpitUebersicht (Hero-Kennzahlen wie Dashboard).
function cockpitKpis(d: CockpitUebersicht): KpiStripItem[] {
  return [
    { title: 'PV-Erzeugung', value: (d.pv_erzeugung_kwh / 1000).toFixed(1), unit: 'MWh', color: 'yellow', icon: Sun },
    { title: 'Autarkie', value: d.autarkie_prozent.toFixed(0), unit: '%', color: 'green', icon: Activity },
    { title: 'Eigenverbrauch', value: d.eigenverbrauch_quote_prozent.toFixed(0), unit: '%', color: 'purple', icon: Zap },
    { title: 'Einspeisung', value: (d.einspeisung_kwh / 1000).toFixed(1), unit: 'MWh', color: 'green', icon: ArrowUpFromLine },
    { title: 'Netto-Ertrag', value: d.netto_ertrag_euro.toFixed(0), unit: '€', color: 'blue', icon: Euro },
  ]
}

// EIN echter Monatschart: PV-Monatserträge aus den aggregierten Monatsdaten
// (gleiches Idiom wie components/dashboard/SparklineChart.tsx).
function MonatsChart({ monatsdaten }: { monatsdaten: AggregierteMonatsdaten[] }) {
  const sorted = [...monatsdaten].sort((a, b) => (a.jahr !== b.jahr ? a.jahr - b.jahr : a.monat - b.monat))
  if (sorted.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Monatsdaten erfasst.</p>
  }
  const firstJahr = sorted[0].jahr
  const chartData = sorted.map((m) => ({
    name: m.jahr !== firstJahr ? `${MONAT_KURZ[m.monat]} ${m.jahr}` : MONAT_KURZ[m.monat],
    kwh: Math.round(m.pv_erzeugung_kwh ?? 0),
  }))
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis dataKey="name" tick={{ fontSize: 12 }} />
          <YAxis width={48} tick={{ fontSize: 12 }} />
          <Tooltip content={<ChartTooltip unit="kWh" />} />
          <Bar dataKey="kwh" name="PV-Ertrag" fill={CHART_COLORS.erzeugung} radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function CockpitV4() {
  const { zeit = 'monat' } = useParams<{ zeit: string }>()
  const { anlagen, selectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()

  const [data, setData] = useState<CockpitUebersicht | null>(null)
  const [monatsdaten, setMonatsdaten] = useState<AggregierteMonatsdaten[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedAnlageId) return
    let abgebrochen = false
    const laden = async () => {
      setLoading(true)
      setError(null)
      try {
        const [uebersicht, monate] = await Promise.all([
          cockpitApi.getUebersicht(selectedAnlageId),
          monatsdatenApi.listAggregiert(selectedAnlageId),
        ])
        if (abgebrochen) return
        setData(uebersicht)
        setMonatsdaten(monate)
      } catch {
        if (!abgebrochen) setError('Fehler beim Laden der Daten')
      } finally {
        if (!abgebrochen) setLoading(false)
      }
    }
    laden()
    return () => {
      abgebrochen = true
    }
  }, [selectedAnlageId])

  // Zeit-Achse (Sub-Tabs, route-getrieben).
  const zeitNav = (
    <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-3 sm:px-6">
      <nav className="flex items-center gap-1 h-14 overflow-x-auto scrollbar-none max-w-[1920px] mx-auto">
        {ZEITEN.map((z) => (
          <NavLink
            key={z.key}
            to={`/v4/cockpit/${z.key}`}
            className={({ isActive }) =>
              `min-h-[44px] flex items-center px-3 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
                isActive
                  ? 'bg-white dark:bg-gray-800 text-primary-700 dark:text-primary-300 shadow-sm'
                  : 'text-gray-600 hover:bg-white/50 dark:text-gray-400 dark:hover:bg-gray-800/50'
              }`
            }
          >
            {z.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )

  let inhalt: React.ReactNode
  if (zeit !== 'monat') {
    inhalt = (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Die Zeit-Sicht „{ZEITEN.find((z) => z.key === zeit)?.label ?? zeit}" wird in einem späteren
            IA-v4-Slice mit echten Daten verdrahtet. Slice 1 zeigt „Monat".
          </p>
        </Card>
      </div>
    )
  } else if (anlagenLoading || loading) {
    inhalt = <LoadingSpinner text="Lade Cockpit…" />
  } else if (anlagen.length === 0) {
    inhalt = (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card>
          <p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage angelegt.</p>
        </Card>
      </div>
    )
  } else if (error || !data) {
    inhalt = (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card>
          <p className="text-red-500">{error || 'Keine Daten verfügbar'}</p>
        </Card>
      </div>
    )
  } else {
    const bloecke: Block[] = [
      { id: 'kpi', title: 'Kennzahlen', icon: Activity, defaultOpen: true, render: () => <KpiStrip kpis={cockpitKpis(data)} /> },
      {
        id: 'verlauf',
        title: 'PV-Monatserträge',
        icon: LineChart,
        summary: 'Verlauf über alle erfassten Monate',
        defaultOpen: true,
        render: () => <MonatsChart monatsdaten={monatsdaten} />,
      },
    ]
    inhalt = <BlockShell key="cockpit-monat" persistKey="v4-cockpit-monat" bloecke={bloecke} sortierbar />
  }

  return (
    <>
      {zeitNav}
      {inhalt}
    </>
  )
}
