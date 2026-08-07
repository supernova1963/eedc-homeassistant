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
import { Card, LoadingSpinner, Alert, KPICard, ChartLegende, Table, TableHead, TableBody, TableFoot, Select } from '../ui'
import { ZELLE, KOPF_ZELLE } from '../ui/tabelleMasse'
import ChartTooltip from '../ui/ChartTooltip'
import { useLegendenToggle } from '../../hooks'
import { Parkbar } from '../park'
import { HerkunftZeile } from '../blocks'
import { pvVerteiltHerkunft } from '../../lib/pvHerkunft'
import { cockpitApi, type PVStringsGesamtlaufzeitResponse } from '../../api/cockpit'
import { SOLL_IST_COLORS, STRING_COLORS, CHART_HOVER_CURSOR, PROGNOSE_DASH, xAchse, achsenEinheit, ACHSEN_MARGIN_TOP, fmtZahl, formatProzent } from '../../lib'

const KEINE_IDS: string[] = []

/**
 * Wortlaut zur Spalte „Performance" (R22-3, PN 89782 Rainer).
 *
 * Die Spalte misst `IST ÷ PVGIS-Prognose DES JEWEILIGEN STRINGS` — Ausrichtung
 * und Neigung stecken damit schon in der SOLL-Basis. Ohne diesen Satz liest man
 * sie als Rangliste der Dächer („das kleine Dach ist 20 % besser") und wundert
 * sich, dass der Gesamtertrag das Gegenteil sagt. Die Kennzahl für den
 * Dach-gegen-Dach-Vergleich ist kWh/kWp, der Ertragsanteil zeigt das Gewicht.
 */
const PERFORMANCE_ERKLAERUNG =
  'Performance misst jeden String gegen seine eigene Prognose — Ausrichtung und '
  + 'Neigung sind darin bereits berücksichtigt. Für den Vergleich der Dächer '
  + 'untereinander zählt kWh/kWp, für das Gewicht am Gesamtertrag die Spalte „Anteil".'

/** Ertragsanteil eines Strings am Gesamt-IST. Ohne Messwerte kein Anteil (R22-3). */
function anteilText(kwh: number, gesamt: number): string {
  return gesamt > 0 ? formatProzent((kwh / gesamt) * 100).text : '—'
}

interface Props {
  anlageId: number
  /** Eingebettet in einen v4-Block (BlockShell): kompakte Sektions-Überschriften
   *  ohne verschachtelte Cards + komponentengerechte Diagramme (SOLL/IST je Modul,
   *  Saison-Modulauswahl). Default false = IST-Dashboard-Darstellung (unverändert). */
  embed?: boolean
  /** v4-Hub: meldet die real gerenderten Park-IDs hoch (Block-Auto-Hide). v3/IST: undefined. */
  melde?: (ids: string[]) => void
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

export function PVStringVergleich({ anlageId, embed = false, melde }: Props) {
  // B7-Legenden-Toggle — je Chart eine Instanz (SOLL/IST-Vergleich + Saison).
  const vergleichLegende = useLegendenToggle()
  const saisonLegende = useLegendenToggle()
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

  // v4-Hub-Auto-Hide (D3, Gernot 2026-07-09): real gerenderte Park-IDs hochmelden.
  // 4 KPIs + (Badges, wenn ≥2 Strings) + (SOLL/IST-Chart) + (Saison-Chart) + Tabelle;
  // der Cross-Link wird vom Aufrufer (komponentenAnalyse) beigemischt.
  const parkIds = useMemo(() => {
    if (loading || error || !data || !data.strings || data.strings.length === 0 || !data.hat_prognose) return KEINE_IDS
    const out: string[] = []
    if (data.prognose_warnung) out.push('info:pv-warnung')
    if (data.ist_quelle === 'verteilt' || data.vergleich_hinweis) out.push('info:pv-herkunft')
    out.push('kpi:pv-soll', 'kpi:pv-ist', 'kpi:pv-abweichung', 'kpi:pv-zeitraum')
    if (data.strings.length > 1 && (data.bester_string || data.schlechtester_string)) out.push('badge:pv-best-schlecht')
    if (embed ? moduleVergleichData.length > 0 : jahresChartData.length > 0) out.push('chart:pv-soll-ist')
    if (saisonalChartData.length > 0) out.push('chart:pv-saison')
    out.push('tabelle:pv-strings')
    return out
  }, [loading, error, data, embed, moduleVergleichData, jahresChartData, saisonalChartData])
  useEffect(() => { melde?.(parkIds) }, [melde, parkIds])

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
        {/* F-10: Auch ein Balkonkraftwerk ist hier eine Zeile. Der alte Rat
            („PV-Module anlegen") führte BKW-Besitzer in den Workaround, den
            #367 verworfen hat — ein zweiter Erfassungsweg für dieselbe
            Erzeugung, mit doppelter kWp als Folge. */}
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Keine PV-Module oder Balkonkraftwerke gefunden
        </h3>
        <p className="text-gray-500 dark:text-gray-400">
          Bitte einen PV-Erzeuger unter Einstellungen → Investitionen anlegen.
        </p>
      </div>
    )
  }

  // Ohne PVGIS-Prognose bleibt der **IST** stehen (#350). Bis 2026-08-04 brach
  // die Sicht hier komplett ab — mit ihr auch die gemessenen Modul-Ertraege, die
  // gar keine Prognose brauchen. Wer nie eine abgerufen hat, sah fuer seine
  // Anlage nichts als diesen Satz. Jetzt entfaellt nur, was ohne SOLL keine
  // Aussage hat: SOLL, Abweichung, Performance.
  const hatPrognose = data.hat_prognose

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
      {/* Ohne Prognose: sagen, was fehlt — und was trotzdem dasteht (#350). */}
      {!hatPrognose && (
        <Parkbar id="info:pv-keine-prognose" titel="Keine PVGIS-Prognose">
          <Alert type="info">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span>
                Keine PVGIS-Prognose vorhanden — gezeigt werden die gemessenen Erträge.
                SOLL, Abweichung und Performance brauchen eine Prognose: Einstellungen → PVGIS.
              </span>
            </div>
          </Alert>
        </Parkbar>
      )}

      {/* Diagnose-Hinweis: stale/oversize PVGIS-Prognose (passt nicht zur kWp) */}
      {data.prognose_warnung && (
        <Parkbar id="info:pv-warnung" titel="Prognose-Warnung">
        <Alert type="warning">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            <span>{data.prognose_warnung}</span>
          </div>
        </Alert>
        </Parkbar>
      )}

      {/* Herkunft der IST-Werte (A4/b1): wer nur einen Gesamt-Sensor hat, sieht
          hier seit v4.0.1 die nach kWp verteilten Werte statt einer leeren Sicht —
          das muss dranstehen. Der Erklärsatz kommt vom Backend
          (`vergleich_hinweis`, enthält auch das Ranking-Verbot), sonst der
          Wortlaut-SoT aus `lib/pvHerkunft`. Dieselbe Zeile wie am Verlauf-Chart. */}
      {(data.ist_quelle === 'verteilt' || data.vergleich_hinweis) && (
        <Parkbar id="info:pv-herkunft" titel="Herkunft der Werte">
          <HerkunftZeile herkunft={pvVerteiltHerkunft('IST je Modul', data.vergleich_hinweis)} />
        </Parkbar>
      )}

      {/* KPI Übersicht — je Kachel einzeln parkbar (Element-Park-Doktrin). */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        {hatPrognose && <Parkbar id="kpi:pv-soll" titel="SOLL (Prognose)"><KPICard
          title="SOLL (Prognose)"
          value={fmtZahl(data.prognose_gesamt_kwh / 1000, 1)}
          unit="MWh"
          color="blue"
          icon={TrendingUp}
          subtitle={`${data.anzahl_jahre} Jahre × PVGIS`}
        /></Parkbar>}
        <Parkbar id="kpi:pv-ist" titel="IST (Erzeugt)"><KPICard
          title="IST (Erzeugt)"
          value={fmtZahl(data.ist_gesamt_kwh / 1000, 1)}
          unit="MWh"
          color="yellow"
          icon={Sun}
          subtitle={`${data.anzahl_monate} Monate erfasst`}
        /></Parkbar>
        {hatPrognose && <Parkbar id="kpi:pv-abweichung" titel="Abweichung"><KPICard
          title="Abweichung"
          value={`${(data.abweichung_gesamt_prozent ?? 0) >= 0 ? '+' : ''}${data.abweichung_gesamt_prozent != null ? fmtZahl(data.abweichung_gesamt_prozent, 1) : '0'}`}
          unit="%"
          color={(data.abweichung_gesamt_prozent ?? 0) >= 0 ? 'green' : 'red'}
          icon={(data.abweichung_gesamt_prozent ?? 0) >= 0 ? TrendingUp : TrendingDown}
        /></Parkbar>}
        <Parkbar id="kpi:pv-zeitraum" titel="Zeitraum"><KPICard
          title="Zeitraum"
          value={`${data.erstes_jahr} - ${data.letztes_jahr}`}
          color="gray"
          icon={Calendar}
          subtitle={`${fmtZahl(data.anlagen_leistung_kwp, 1)} kWp`}
        /></Parkbar>
      </div>

      {/* Beste/Schlechteste Performance */}
      {data.strings.length > 1 && (data.bester_string || data.schlechtester_string) && (
        <Parkbar id="badge:pv-best-schlecht" titel="Beste/Schwächste Performance">
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
        </Parkbar>
      )}

      {/* SOLL vs IST — Embed: je Modul nebeneinander + Delta-Label; IST-Seite: pro Jahr */}
      {(embed ? moduleVergleichData.length > 0 : jahresChartData.length > 0) && (
        <Parkbar id="chart:pv-soll-ist" titel="SOLL vs IST">
        <Sektion embed={embed} icon={Calendar} farbe="text-blue-500"
          titel={hatPrognose
            ? (embed ? 'SOLL vs IST je Modul (Gesamtlaufzeit)' : 'SOLL vs IST pro Jahr')
            : (embed ? 'Ertrag je Modul (Gesamtlaufzeit)' : 'Ertrag pro Jahr')}
          hinweis={embed
            ? (hatPrognose ? 'PVGIS-Prognose vs. erzeugt je Modul; Label = Abweichung.' : 'Gemessener Ertrag je Modul.')
            : undefined}>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              {embed ? (
                <BarChart data={moduleVergleichData} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" {...xAchse()} /* achsen-allow: Kategorie-Achse (Modul-Name) */ />
                  <YAxis tickFormatter={jahresAchse.tick} label={achsenEinheit(jahresAchse.einheit)} width={70} tick={{ fontSize: 10 }} />
                  <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit="kWh" />} />
                  <Legend content={<ChartLegende onItemClick={vergleichLegende.onItemClick} />} />
                  {/* SOLL deckend (S4: Balken nicht transparent); als Prognose nur
                      über den gestrichelten Rand markiert. */}
                  {hatPrognose && <Bar dataKey="SOLL" name="SOLL (PVGIS)" fill={SOLL_IST_COLORS.soll} stroke={SOLL_IST_COLORS.soll} strokeWidth={1} strokeDasharray={PROGNOSE_DASH} hide={vergleichLegende.istVersteckt('SOLL')} />}
                  <Bar dataKey="IST" name="IST (erzeugt)" fill={SOLL_IST_COLORS.ist} hide={vergleichLegende.istVersteckt('IST')}>
                    <LabelList dataKey="deltaLabel" position="top" fontSize={11} />
                  </Bar>
                </BarChart>
              ) : (
                <BarChart data={jahresChartData} margin={{ top: ACHSEN_MARGIN_TOP }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" {...xAchse()} /* achsen-allow: Zeit-/Kategorie-Achse (Jahr) */ />
                  <YAxis tickFormatter={jahresAchse.tick} label={achsenEinheit(jahresAchse.einheit)} width={80} tick={{ fontSize: 10 }} />
                  <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit="kWh" />} />
                  <Legend content={<ChartLegende onItemClick={vergleichLegende.onItemClick} />} />
                  {hatPrognose && data.strings.map((s, idx) => {
                    const single = data.strings.length === 1
                    const baseColor = single ? SOLL_IST_COLORS.soll : STRING_COLORS[idx % STRING_COLORS.length]
                    return (
                      <Bar key={`${s.investition_id}-soll`} dataKey={`${s.bezeichnung} SOLL`}
                        fill={baseColor} stroke={baseColor} strokeWidth={1} strokeDasharray={PROGNOSE_DASH}
                        name={`${s.bezeichnung} SOLL`} hide={vergleichLegende.istVersteckt(`${s.bezeichnung} SOLL`)} />
                    )
                  })}
                  {data.strings.map((s, idx) => {
                    const single = data.strings.length === 1
                    const baseColor = single ? SOLL_IST_COLORS.ist : STRING_COLORS[idx % STRING_COLORS.length]
                    return (
                      <Bar key={`${s.investition_id}-ist`} dataKey={`${s.bezeichnung} IST`}
                        fill={baseColor} name={`${s.bezeichnung} IST`} hide={vergleichLegende.istVersteckt(`${s.bezeichnung} IST`)} />
                    )
                  })}
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        </Sektion>
        </Parkbar>
      )}

      {/* Saisonaler Vergleich — Embed: Modulauswahl (Gesamt / einzelnes Modul) */}
      {saisonalChartData.length > 0 && (
        <Parkbar id="chart:pv-saison" titel="Saisonaler Vergleich">
        <Sektion embed={embed} icon={BarChart3} farbe="text-green-500" titel="Saisonaler Vergleich (Jan – Dez)"
          hinweis={hatPrognose
            ? 'Monatliche PVGIS-Prognose vs. Durchschnitt der tatsächlichen Erzeugung über alle Jahre.'
            : 'Durchschnitt der tatsächlichen Erzeugung über alle Jahre.'}>
          {embed && data.strings.length > 1 && (
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-500 dark:text-gray-400">Modul:</label>
              <Select
                steuer
                aria-label="Modul"
                value={saisonModul}
                onChange={(e) => setSaisonModul(e.target.value)}
                options={[
                  { value: 'gesamt', label: 'Gesamt (alle Module)' },
                  ...data.strings.map(s => ({ value: String(s.investition_id), label: s.bezeichnung })),
                ]}
              />
            </div>
          )}
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={saisonalChartData} margin={{ top: ACHSEN_MARGIN_TOP }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" {...xAchse()} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                <YAxis tickFormatter={saisonalAchse.tick} label={achsenEinheit(saisonalAchse.einheit)} width={80} tick={{ fontSize: 10 }} />
                <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit="kWh" />} />
                <Legend content={<ChartLegende onItemClick={saisonLegende.onItemClick} />} />
                {hatPrognose && <Area
                  type="monotone"
                  dataKey="SOLL"
                  fill={SOLL_IST_COLORS.soll}
                  stroke={SOLL_IST_COLORS.soll}
                  strokeDasharray={PROGNOSE_DASH}
                  fillOpacity={0.2}
                  name="PVGIS Prognose"
                  hide={saisonLegende.istVersteckt('SOLL')}
                />}
                <Line
                  type="monotone"
                  dataKey="IST Ø"
                  stroke={SOLL_IST_COLORS.ist}
                  strokeWidth={3}
                  dot={{ r: 4 }}
                  name="IST Durchschnitt"
                  hide={saisonLegende.istVersteckt('IST Ø')}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Sektion>
        </Parkbar>
      )}

      {/* String-Detail-Tabelle */}
      <Parkbar id="tabelle:pv-strings" titel="Einzelne Strings / Module">
      <Sektion embed={embed} icon={BarChart3} farbe="text-gray-500" titel="Einzelne Strings / Module (Gesamtlaufzeit)"
        hinweis={hatPrognose ? PERFORMANCE_ERKLAERUNG : 'Für den Vergleich der Dächer untereinander zählt kWh/kWp, für das Gewicht am Gesamtertrag die Spalte „Anteil".'}>
        {/* Mobil (< sm): Karten je String/Modul statt Tabelle — Muster wie
            Cockpit-Energiebilanz (eine Datenliste, zwei Render-Pfade). */}
        <div className="sm:hidden space-y-2">
          {data.strings.map((s, idx) => (
            <div key={s.investition_id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: STRING_COLORS[idx % STRING_COLORS.length] }} />
                <span className="font-medium text-gray-900 dark:text-white truncate">{s.bezeichnung}</span>
                {hatPrognose && <span className="ml-auto shrink-0"><PerformanceBadge ratio={s.performance_ratio_gesamt} /></span>}
              </div>
              {s.wechselrichter_name && <p className="text-xs text-gray-500 ml-5">→ {s.wechselrichter_name}</p>}
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-sm">
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">kWp</dt><dd className="text-gray-700 dark:text-gray-300 tabular-nums">{fmtZahl(s.leistung_kwp, 1)}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">Ausrichtung</dt><dd className="text-gray-700 dark:text-gray-300">{s.ausrichtung || '-'}{s.neigung_grad != null && ` / ${s.neigung_grad}°`}</dd></div>
                {hatPrognose && <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">SOLL</dt><dd className="text-blue-600 dark:text-blue-400 tabular-nums">{fmtZahl(s.prognose_gesamt_kwh / 1000, 1)} MWh</dd></div>}
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">IST</dt><dd className="font-medium tabular-nums" style={{ color: STRING_COLORS[idx % STRING_COLORS.length] }}>{fmtZahl(s.ist_gesamt_kwh / 1000, 1)} MWh</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">Anteil</dt><dd className="text-gray-700 dark:text-gray-300 tabular-nums">{anteilText(s.ist_gesamt_kwh, data.ist_gesamt_kwh)}</dd></div>
                {hatPrognose && <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">Abw.</dt><dd className={`tabular-nums ${(s.abweichung_gesamt_prozent ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>{(s.abweichung_gesamt_prozent ?? 0) >= 0 ? '+' : ''}{s.abweichung_gesamt_prozent != null ? fmtZahl(s.abweichung_gesamt_prozent, 1) : '0'} %</dd></div>}
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">kWh/kWp</dt><dd className="text-gray-700 dark:text-gray-300 tabular-nums">{s.spezifischer_ertrag_kwh_kwp != null ? fmtZahl(s.spezifischer_ertrag_kwh_kwp, 0) : '-'}</dd></div>
              </dl>
            </div>
          ))}
          {/* Summenkarte — dasselbe Datenpaar wie der Tabellenfuß (R22-3). */}
          {data.strings.length > 1 && (
            <div className="rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/60 p-3">
              <span className="font-medium text-gray-900 dark:text-white">Gesamt</span>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-sm">
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">kWp</dt><dd className="text-gray-700 dark:text-gray-300 tabular-nums">{fmtZahl(data.anlagen_leistung_kwp, 1)}</dd></div>
                {hatPrognose && <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">SOLL</dt><dd className="text-blue-600 dark:text-blue-400 tabular-nums">{fmtZahl(data.prognose_gesamt_kwh / 1000, 1)} MWh</dd></div>}
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">IST</dt><dd className="font-medium text-gray-900 dark:text-white tabular-nums">{fmtZahl(data.ist_gesamt_kwh / 1000, 1)} MWh</dd></div>
                {hatPrognose && <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">Abw.</dt><dd className={`tabular-nums ${(data.abweichung_gesamt_prozent ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>{(data.abweichung_gesamt_prozent ?? 0) >= 0 ? '+' : ''}{data.abweichung_gesamt_prozent != null ? fmtZahl(data.abweichung_gesamt_prozent, 1) : '0'} %</dd></div>}
                <div className="flex justify-between gap-2"><dt className="text-gray-500 dark:text-gray-400">kWh/kWp</dt><dd className="text-gray-700 dark:text-gray-300 tabular-nums">{data.anlagen_leistung_kwp > 0 ? fmtZahl(data.ist_gesamt_kwh / data.anlagen_leistung_kwp, 0) : '—'}</dd></div>
              </dl>
            </div>
          )}
        </div>

        {/* Desktop (≥ sm): Tabelle */}
        <Table aussenClassName="hidden sm:block">
          <TableHead>
            <tr>
              <th className={`${KOPF_ZELLE} text-left text-gray-500`}>String / Modul</th>
              <th className={`${KOPF_ZELLE} text-right text-gray-500`}>kWp</th>
              <th className={`${KOPF_ZELLE} text-left text-gray-500`}>Ausrichtung</th>
              {hatPrognose && <th className={`${KOPF_ZELLE} text-right text-gray-500`}>SOLL</th>}
              <th className={`${KOPF_ZELLE} text-right text-gray-500`}>IST</th>
              <th className={`${KOPF_ZELLE} text-right text-gray-500`}>Anteil</th>
              {hatPrognose && <th className={`${KOPF_ZELLE} text-right text-gray-500`}>Abw.</th>}
              {hatPrognose && <th className={`${KOPF_ZELLE} text-right text-gray-500`}>Performance</th>}
              <th className={`${KOPF_ZELLE} text-right text-gray-500`}>kWh/kWp</th>
            </tr>
          </TableHead>
          <TableBody>
            {data.strings.map((s, idx) => (
              <tr key={s.investition_id} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                <td className={ZELLE}>
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
                <td className={`${ZELLE} text-right text-gray-600 dark:text-gray-400`}>
                  {fmtZahl(s.leistung_kwp, 1)}
                </td>
                <td className={`${ZELLE} text-gray-600 dark:text-gray-400`}>
                  {s.ausrichtung || '-'}
                  {s.neigung_grad != null && ` / ${s.neigung_grad}°`}
                </td>
                {hatPrognose && <td className={`${ZELLE} text-right text-blue-600 dark:text-blue-400`}>
                  {fmtZahl(s.prognose_gesamt_kwh / 1000, 1)} MWh
                </td>}
                <td className={`${ZELLE} text-right font-medium`} style={{ color: STRING_COLORS[idx % STRING_COLORS.length] }}>
                  {fmtZahl(s.ist_gesamt_kwh / 1000, 1)} MWh
                </td>
                <td className={`${ZELLE} text-right text-gray-600 dark:text-gray-400`}>
                  {anteilText(s.ist_gesamt_kwh, data.ist_gesamt_kwh)}
                </td>
                {hatPrognose && <td className={`${ZELLE} text-right ${
                  (s.abweichung_gesamt_prozent ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
                }`}>
                  {(s.abweichung_gesamt_prozent ?? 0) >= 0 ? '+' : ''}
                  {s.abweichung_gesamt_prozent != null ? fmtZahl(s.abweichung_gesamt_prozent, 1) : '0'} %
                </td>}
                {hatPrognose && <td className={`${ZELLE} text-right`}>
                  <PerformanceBadge ratio={s.performance_ratio_gesamt} />
                </td>}
                <td className={`${ZELLE} text-right text-gray-600 dark:text-gray-400`}>
                  {s.spezifischer_ertrag_kwh_kwp != null ? fmtZahl(s.spezifischer_ertrag_kwh_kwp, 0) : '-'}
                </td>
              </tr>
            ))}
          </TableBody>
          {/* Σ-Zeile (R22-3): erledigt zugleich Rainers „Summe der Modul-Leistung".
              Die kWp-Summe ist `anlagen_leistung_kwp` aus derselben Response —
              nicht clientseitig nachaddiert (eine Zahl, eine Quelle). */}
          {data.strings.length > 1 && (
            <TableFoot>
              <tr>
                <td className={`${ZELLE} font-medium text-gray-900 dark:text-white`}>Gesamt</td>
                <td className={`${ZELLE} text-right text-gray-600 dark:text-gray-400`}>{fmtZahl(data.anlagen_leistung_kwp, 1)}</td>
                <td className={`${ZELLE} text-gray-600 dark:text-gray-400`}>-</td>
                {hatPrognose && <td className={`${ZELLE} text-right text-blue-600 dark:text-blue-400`}>{fmtZahl(data.prognose_gesamt_kwh / 1000, 1)} MWh</td>}
                <td className={`${ZELLE} text-right font-medium text-gray-900 dark:text-white`}>{fmtZahl(data.ist_gesamt_kwh / 1000, 1)} MWh</td>
                <td className={`${ZELLE} text-right text-gray-600 dark:text-gray-400`}>{data.ist_gesamt_kwh > 0 ? formatProzent(100).text : '—'}</td>
                {hatPrognose && <td className={`${ZELLE} text-right ${(data.abweichung_gesamt_prozent ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {(data.abweichung_gesamt_prozent ?? 0) >= 0 ? '+' : ''}
                  {data.abweichung_gesamt_prozent != null ? fmtZahl(data.abweichung_gesamt_prozent, 1) : '0'} %
                </td>}
                {/* Kein Gesamt-Performance-Badge: die SOLL-Basen der Strings sind
                    verschieden gewichtet — ein Mittelwert daraus wäre erfunden. */}
                {hatPrognose && <td className={`${ZELLE} text-right text-gray-400 dark:text-gray-500`}>—</td>}
                <td className={`${ZELLE} text-right text-gray-600 dark:text-gray-400`}>
                  {data.anlagen_leistung_kwp > 0 ? fmtZahl(data.ist_gesamt_kwh / data.anlagen_leistung_kwp, 0) : '—'}
                </td>
              </tr>
            </TableFoot>
          )}
        </Table>
      </Sektion>
      </Parkbar>
    </div>
  )
}
