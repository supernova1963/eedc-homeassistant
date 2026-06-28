/**
 * PV-String-Vergleich Komponente (Gesamtlaufzeit)
 *
 * Zeigt SOLL vs IST Vergleich pro PV-Modul/String über die gesamte Laufzeit:
 * 1. Jahresübersicht: SOLL vs IST pro Jahr für jeden String
 * 2. Saisonaler Vergleich: Jan-Dez Durchschnitt vs PVGIS-Prognose
 * 3. Tabelle mit Gesamtlaufzeit-Statistik pro String
 */

import { useState, useEffect, useMemo, type ReactNode, type ComponentType } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ComposedChart, Line, Area, LabelList
} from 'recharts'
import { Sun, TrendingUp, TrendingDown, AlertTriangle, Calendar, BarChart3 } from 'lucide-react'
import { Card, LoadingSpinner, Alert, KPICard, ChartLegende } from '../ui'
import ChartTooltip from '../ui/ChartTooltip'
import { cockpitApi, type PVStringsGesamtlaufzeitResponse } from '../../api/cockpit'
import { SOLL_IST_COLORS, STRING_COLORS, CHART_HOVER_CURSOR, PROGNOSE_DASH, achsenEinheit, ACHSEN_MARGIN_TOP, fmtZahl } from '../../lib'

interface Props {
  anlageId: number
  /** Eingebettet in einen v4-Block (BlockShell): kompakte Sektions-Überschriften
   *  ohne verschachtelte Cards + komponentengerechte Diagramme (SOLL/IST je Modul,
   *  Saison-Modulauswahl). Default false = IST-Dashboard-Darstellung (unverändert). */
  embed?: boolean
}

/** Sektions-Rahmen: im Embed kompakte Überschrift (subordiniert dem Block-Titel),
 *  sonst die gewohnte Card mit großer Überschrift (IST-Seite). */
function Sektion({ embed, icon: Icon, farbe, titel, hinweis, children }: {
  embed: boolean; icon: ComponentType<{ className?: string }>; farbe: string; titel: string; hinweis?: string; children: ReactNode
}) {
  if (embed) {
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
          <Icon className={`h-4 w-4 ${farbe}`} /> {titel}
        </div>
        {hinweis && <p className="text-xs text-gray-500 dark:text-gray-400">{hinweis}</p>}
        {children}
      </div>
    )
  }
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <Icon className={`h-5 w-5 ${farbe}`} /> {titel}
      </h3>
      {hinweis && <p className="text-sm text-gray-500 mb-4">{hinweis}</p>}
      {children}
    </Card>
  )
}

export function PVStringVergleich({ anlageId, embed = false }: Props) {
  const [data, setData] = useState<PVStringsGesamtlaufzeitResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saisonModul, setSaisonModul] = useState<string>('gesamt')

  useEffect(() => {
    let cancelled = false

    const loadData = async () => {
      setLoading(true)
      setError(null)

      try {
        const result = await cockpitApi.getPVStringsGesamtlaufzeit(anlageId)
        if (!cancelled) {
          setData(result)
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const errorMsg = err && typeof err === 'object' && 'detail' in err
            ? String((err as { detail: string }).detail)
            : 'Fehler beim Laden der String-Daten'
          setError(errorMsg)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    loadData()
    return () => { cancelled = true }
  }, [anlageId])

  // Chart-Daten: Jahresübersicht pro String
  const jahresChartData = useMemo(() => {
    if (!data?.strings || data.strings.length === 0) return []

    // Gruppiere nach Jahr
    const byYear: Record<number, Record<string, { soll: number; ist: number }>> = {}

    for (const s of data.strings) {
      for (const jw of s.jahreswerte) {
        if (!byYear[jw.jahr]) byYear[jw.jahr] = {}
        byYear[jw.jahr][s.bezeichnung] = {
          soll: jw.prognose_kwh,
          ist: jw.ist_kwh,
        }
      }
    }

    return Object.entries(byYear)
      .sort(([a], [b]) => Number(a) - Number(b))
      .map(([jahr, strings]) => {
        const row: Record<string, number | string> = { name: jahr }
        for (const s of data.strings) {
          const vals = strings[s.bezeichnung]
          if (vals) {
            row[`${s.bezeichnung} SOLL`] = Math.round(vals.soll)
            row[`${s.bezeichnung} IST`] = Math.round(vals.ist)
          }
        }
        return row
      })
  }, [data])

  // Chart-Daten: SOLL/IST je Modul nebeneinander (Gesamtlaufzeit) + Delta-Label (Embed).
  const moduleVergleichData = useMemo(() => {
    if (!data?.strings) return []
    return data.strings.map(s => ({
      name: s.bezeichnung,
      SOLL: Math.round(s.prognose_gesamt_kwh),
      IST: Math.round(s.ist_gesamt_kwh),
      deltaLabel: s.abweichung_gesamt_prozent != null
        ? `${s.abweichung_gesamt_prozent >= 0 ? '+' : ''}${fmtZahl(s.abweichung_gesamt_prozent, 0)} %`
        : '',
    }))
  }, [data])

  // Chart-Daten: Saisonaler Vergleich (Jan-Dez) — Quelle nach Modulauswahl (Gesamt / einzelnes Modul).
  const saisonalChartData = useMemo(() => {
    const quelle = saisonModul === 'gesamt'
      ? data?.saisonal_aggregiert
      : data?.strings.find(s => String(s.investition_id) === saisonModul)?.saisonalwerte
    if (!quelle) return []
    return quelle.map(s => ({
      name: s.monat_name.slice(0, 3),
      SOLL: Math.round(s.prognose_kwh),
      'IST Ø': Math.round(s.ist_durchschnitt_kwh),
      'IST Summe': Math.round(s.ist_summe_kwh),
    }))
  }, [data, saisonModul])

  // Achsen-Einheit + Tick getrennt: Einheit gehört an den Achsen-Titel (R9),
  // Tick liefert nur die Zahl (de-DE). Schwelle bei 5000: ab dort MWh, damit
  // "10.000 kWh" nicht abgeschnitten wird.
  const jahresAchse = useMemo(() => {
    if (jahresChartData.length === 0) return { einheit: 'kWh', tick: (val: number) => `${val}` }
    const maxVal = Math.max(...jahresChartData.flatMap(row =>
      Object.entries(row).filter(([k]) => k !== 'name').map(([, v]) => Number(v) || 0)
    ))
    const mwh = maxVal >= 5000
    return {
      einheit: mwh ? 'MWh' : 'kWh',
      tick: (val: number) => mwh
        ? (val / 1000).toLocaleString('de-DE', { maximumFractionDigits: 1 })
        : val.toLocaleString('de-DE'),
    }
  }, [jahresChartData])

  const saisonalAchse = useMemo(() => {
    const maxVal = saisonalChartData.length > 0
      ? Math.max(...saisonalChartData.flatMap(d => [d.SOLL, d['IST Ø']]))
      : 0
    const mwh = maxVal >= 5000
    return {
      einheit: mwh ? 'MWh' : 'kWh',
      tick: (val: number) => mwh
        ? (val / 1000).toLocaleString('de-DE', { maximumFractionDigits: 1 })
        : val.toLocaleString('de-DE'),
    }
  }, [saisonalChartData])

  // Loading State
  if (loading) {
    return <LoadingSpinner text="Lade String-Vergleich..." />
  }

  // Error State
  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  // No Data State
  if (!data || !data.strings || data.strings.length === 0) {
    return (
      <div className="text-center py-8">
        <Sun className="h-12 w-12 mx-auto text-gray-400 dark:text-gray-500 mb-4" />
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Keine PV-Module gefunden
        </h3>
        <p className="text-gray-500 dark:text-gray-400">
          Bitte PV-Module unter Einstellungen → Investitionen anlegen.
        </p>
      </div>
    )
  }

  // No Prognosis State
  if (!data.hat_prognose) {
    return (
      <Alert type="warning">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          <span>
            Keine PVGIS-Prognose vorhanden. Bitte unter Einstellungen → PVGIS eine Prognose abrufen.
          </span>
        </div>
      </Alert>
    )
  }

  // Performance Badge
  const PerformanceBadge = ({ ratio }: { ratio: number | null | undefined }) => {
    if (ratio == null) return <span className="text-gray-400 dark:text-gray-500">-</span>
    const pct = ratio * 100
    const colorClass = pct >= 95 ? 'text-green-600' : pct < 85 ? 'text-red-600' : 'text-amber-600'
    const Icon = pct >= 95 ? TrendingUp : pct < 85 ? TrendingDown : null
    return (
      <span className={`flex items-center justify-end gap-1 ${colorClass}`}>
        {Icon && <Icon className="h-3 w-3" />}
        {fmtZahl(pct, 0)} %
      </span>
    )
  }

  return (
    <div className="space-y-6">
      {/* Diagnose-Hinweis: stale/oversize PVGIS-Prognose (passt nicht zur kWp) */}
      {data.prognose_warnung && (
        <Alert type="warning">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            <span>{data.prognose_warnung}</span>
          </div>
        </Alert>
      )}

      {/* KPI Übersicht */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        <KPICard
          title="SOLL (Prognose)"
          value={fmtZahl(data.prognose_gesamt_kwh / 1000, 1)}
          unit="MWh"
          color="blue"
          icon={TrendingUp}
          subtitle={`${data.anzahl_jahre} Jahre × PVGIS`}
        />
        <KPICard
          title="IST (Erzeugt)"
          value={fmtZahl(data.ist_gesamt_kwh / 1000, 1)}
          unit="MWh"
          color="yellow"
          icon={Sun}
          subtitle={`${data.anzahl_monate} Monate erfasst`}
        />
        <KPICard
          title="Abweichung"
          value={`${(data.abweichung_gesamt_prozent ?? 0) >= 0 ? '+' : ''}${data.abweichung_gesamt_prozent != null ? fmtZahl(data.abweichung_gesamt_prozent, 1) : '0'}`}
          unit="%"
          color={(data.abweichung_gesamt_prozent ?? 0) >= 0 ? 'green' : 'red'}
          icon={(data.abweichung_gesamt_prozent ?? 0) >= 0 ? TrendingUp : TrendingDown}
        />
        <KPICard
          title="Zeitraum"
          value={`${data.erstes_jahr} - ${data.letztes_jahr}`}
          color="gray"
          icon={Calendar}
          subtitle={`${fmtZahl(data.anlagen_leistung_kwp, 1)} kWp`}
        />
      </div>

      {/* Beste/Schlechteste Performance */}
      {data.strings.length > 1 && (data.bester_string || data.schlechtester_string) && (
        <div className="flex flex-wrap gap-4 text-sm">
          {data.bester_string && (
            <div className="flex items-center gap-2 bg-green-50 dark:bg-green-900/20 px-3 py-1 rounded-full">
              <TrendingUp className="h-4 w-4 text-green-600" />
              <span className="text-green-700 dark:text-green-300">
                Beste Performance: <strong>{data.bester_string}</strong>
              </span>
            </div>
          )}
          {data.schlechtester_string && data.schlechtester_string !== data.bester_string && (
            <div className="flex items-center gap-2 bg-red-50 dark:bg-red-900/20 px-3 py-1 rounded-full">
              <TrendingDown className="h-4 w-4 text-red-600" />
              <span className="text-red-700 dark:text-red-300">
                Schwächster: <strong>{data.schlechtester_string}</strong>
              </span>
            </div>
          )}
        </div>
      )}

      {/* SOLL vs IST — Embed: je Modul nebeneinander + Delta-Label; IST-Seite: pro Jahr */}
      {(embed ? moduleVergleichData.length > 0 : jahresChartData.length > 0) && (
        <Sektion embed={embed} icon={Calendar} farbe="text-blue-500"
          titel={embed ? 'SOLL vs IST je Modul (Gesamtlaufzeit)' : 'SOLL vs IST pro Jahr'}
          hinweis={embed ? 'PVGIS-Prognose vs. erzeugt je Modul; Label = Abweichung.' : undefined}>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              {embed ? (
                <BarChart data={moduleVergleichData} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} /* achsen-allow: Kategorie-Achse (Modul-Name) */ />
                  <YAxis tickFormatter={jahresAchse.tick} label={achsenEinheit(jahresAchse.einheit)} width={70} tick={{ fontSize: 10 }} />
                  <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit="kWh" />} />
                  <Legend content={<ChartLegende />} />
                  {/* SOLL deckend (S4: Balken nicht transparent); als Prognose nur
                      über den gestrichelten Rand markiert. */}
                  <Bar dataKey="SOLL" name="SOLL (PVGIS)" fill={SOLL_IST_COLORS.soll} stroke={SOLL_IST_COLORS.soll} strokeWidth={1} strokeDasharray={PROGNOSE_DASH} />
                  <Bar dataKey="IST" name="IST (erzeugt)" fill={SOLL_IST_COLORS.ist}>
                    <LabelList dataKey="deltaLabel" position="top" fontSize={11} />
                  </Bar>
                </BarChart>
              ) : (
                <BarChart data={jahresChartData} margin={{ top: ACHSEN_MARGIN_TOP }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} /* achsen-allow: Zeit-/Kategorie-Achse (Jahr) */ />
                  <YAxis tickFormatter={jahresAchse.tick} label={achsenEinheit(jahresAchse.einheit)} width={80} tick={{ fontSize: 10 }} />
                  <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit="kWh" />} />
                  <Legend content={<ChartLegende />} />
                  {data.strings.map((s, idx) => {
                    const single = data.strings.length === 1
                    const baseColor = single ? SOLL_IST_COLORS.soll : STRING_COLORS[idx % STRING_COLORS.length]
                    return (
                      <Bar key={`${s.investition_id}-soll`} dataKey={`${s.bezeichnung} SOLL`}
                        fill={baseColor} stroke={baseColor} strokeWidth={1} strokeDasharray={PROGNOSE_DASH}
                        name={`${s.bezeichnung} SOLL`} />
                    )
                  })}
                  {data.strings.map((s, idx) => {
                    const single = data.strings.length === 1
                    const baseColor = single ? SOLL_IST_COLORS.ist : STRING_COLORS[idx % STRING_COLORS.length]
                    return (
                      <Bar key={`${s.investition_id}-ist`} dataKey={`${s.bezeichnung} IST`}
                        fill={baseColor} name={`${s.bezeichnung} IST`} />
                    )
                  })}
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        </Sektion>
      )}

      {/* Saisonaler Vergleich — Embed: Modulauswahl (Gesamt / einzelnes Modul) */}
      {saisonalChartData.length > 0 && (
        <Sektion embed={embed} icon={BarChart3} farbe="text-green-500" titel="Saisonaler Vergleich (Jan – Dez)"
          hinweis="Monatliche PVGIS-Prognose vs. Durchschnitt der tatsächlichen Erzeugung über alle Jahre.">
          {embed && data.strings.length > 1 && (
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-500 dark:text-gray-400">Modul:</label>
              <select
                value={saisonModul}
                onChange={(e) => setSaisonModul(e.target.value)}
                className="min-h-[36px] rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm px-2 text-gray-700 dark:text-gray-300"
              >
                <option value="gesamt">Gesamt (alle Module)</option>
                {data.strings.map(s => <option key={s.investition_id} value={String(s.investition_id)}>{s.bezeichnung}</option>)}
              </select>
            </div>
          )}
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={saisonalChartData} margin={{ top: ACHSEN_MARGIN_TOP }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                <YAxis tickFormatter={saisonalAchse.tick} label={achsenEinheit(saisonalAchse.einheit)} width={80} tick={{ fontSize: 10 }} />
                <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit="kWh" />} />
                <Legend content={<ChartLegende />} />
                <Area
                  type="monotone"
                  dataKey="SOLL"
                  fill={SOLL_IST_COLORS.soll}
                  stroke={SOLL_IST_COLORS.soll}
                  strokeDasharray={PROGNOSE_DASH}
                  fillOpacity={0.2}
                  name="PVGIS Prognose"
                />
                <Line
                  type="monotone"
                  dataKey="IST Ø"
                  stroke={SOLL_IST_COLORS.ist}
                  strokeWidth={3}
                  dot={{ r: 4 }}
                  name="IST Durchschnitt"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Sektion>
      )}

      {/* String-Detail-Tabelle */}
      <Sektion embed={embed} icon={BarChart3} farbe="text-gray-500" titel="Einzelne Strings / Module (Gesamtlaufzeit)">
        {/* Mobil (< sm): Karten je String/Modul statt Tabelle — Muster wie
            Cockpit-Energiebilanz (eine Datenliste, zwei Render-Pfade). */}
        <div className="sm:hidden space-y-2">
          {data.strings.map((s, idx) => (
            <div key={s.investition_id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: STRING_COLORS[idx % STRING_COLORS.length] }} />
                <span className="font-medium text-gray-900 dark:text-white truncate">{s.bezeichnung}</span>
                <span className="ml-auto shrink-0"><PerformanceBadge ratio={s.performance_ratio_gesamt} /></span>
              </div>
              {s.wechselrichter_name && <p className="text-xs text-gray-500 ml-5">→ {s.wechselrichter_name}</p>}
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-sm">
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">kWp</dt><dd className="text-gray-700 dark:text-gray-300 tabular-nums">{fmtZahl(s.leistung_kwp, 1)}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">Ausrichtung</dt><dd className="text-gray-700 dark:text-gray-300">{s.ausrichtung || '-'}{s.neigung_grad != null && ` / ${s.neigung_grad}°`}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">SOLL</dt><dd className="text-blue-600 dark:text-blue-400 tabular-nums">{fmtZahl(s.prognose_gesamt_kwh / 1000, 1)} MWh</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">IST</dt><dd className="font-medium tabular-nums" style={{ color: STRING_COLORS[idx % STRING_COLORS.length] }}>{fmtZahl(s.ist_gesamt_kwh / 1000, 1)} MWh</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">Abw.</dt><dd className={`tabular-nums ${(s.abweichung_gesamt_prozent ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>{(s.abweichung_gesamt_prozent ?? 0) >= 0 ? '+' : ''}{s.abweichung_gesamt_prozent != null ? fmtZahl(s.abweichung_gesamt_prozent, 1) : '0'} %</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">kWh/kWp</dt><dd className="text-gray-700 dark:text-gray-300 tabular-nums">{s.spezifischer_ertrag_kwh_kwp != null ? fmtZahl(s.spezifischer_ertrag_kwh_kwp, 0) : '-'}</dd></div>
              </dl>
            </div>
          ))}
        </div>

        {/* Desktop (≥ sm): Tabelle */}
        <div className="hidden sm:block overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-gray-500">String / Modul</th>
                <th className="px-3 py-2 text-right font-medium text-gray-500">kWp</th>
                <th className="px-3 py-2 text-left font-medium text-gray-500">Ausrichtung</th>
                <th className="px-3 py-2 text-right font-medium text-gray-500">SOLL</th>
                <th className="px-3 py-2 text-right font-medium text-gray-500">IST</th>
                <th className="px-3 py-2 text-right font-medium text-gray-500">Abw.</th>
                <th className="px-3 py-2 text-right font-medium text-gray-500">Performance</th>
                <th className="px-3 py-2 text-right font-medium text-gray-500">kWh/kWp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {data.strings.map((s, idx) => (
                <tr key={s.investition_id} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: STRING_COLORS[idx % STRING_COLORS.length] }}
                      />
                      <span className="font-medium text-gray-900 dark:text-white">
                        {s.bezeichnung}
                      </span>
                    </div>
                    {s.wechselrichter_name && (
                      <p className="text-xs text-gray-500 ml-5">→ {s.wechselrichter_name}</p>
                    )}
                  </td>
                  <td className="px-3 py-3 text-right text-gray-600 dark:text-gray-400">
                    {fmtZahl(s.leistung_kwp, 1)}
                  </td>
                  <td className="px-3 py-3 text-gray-600 dark:text-gray-400">
                    {s.ausrichtung || '-'}
                    {s.neigung_grad != null && ` / ${s.neigung_grad}°`}
                  </td>
                  <td className="px-3 py-3 text-right text-blue-600 dark:text-blue-400">
                    {fmtZahl(s.prognose_gesamt_kwh / 1000, 1)} MWh
                  </td>
                  <td className="px-3 py-3 text-right font-medium" style={{ color: STRING_COLORS[idx % STRING_COLORS.length] }}>
                    {fmtZahl(s.ist_gesamt_kwh / 1000, 1)} MWh
                  </td>
                  <td className={`px-3 py-3 text-right ${
                    (s.abweichung_gesamt_prozent ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {(s.abweichung_gesamt_prozent ?? 0) >= 0 ? '+' : ''}
                    {s.abweichung_gesamt_prozent != null ? fmtZahl(s.abweichung_gesamt_prozent, 1) : '0'} %
                  </td>
                  <td className="px-3 py-3 text-right">
                    <PerformanceBadge ratio={s.performance_ratio_gesamt} />
                  </td>
                  <td className="px-3 py-3 text-right text-gray-600 dark:text-gray-400">
                    {s.spezifischer_ertrag_kwh_kwp != null ? fmtZahl(s.spezifischer_ertrag_kwh_kwp, 0) : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Sektion>
    </div>
  )
}
