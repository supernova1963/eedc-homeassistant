/**
 * RoiAnalyse — geteilte Element-Bausteine der ROI-Analyse (A.5 Sub 5, SoT).
 *
 * Eine Code-Wahrheit: die IST-Seite `pages/ROIDashboard.tsx` UND die v4-Sicht
 * `v4/AuswertungenRoiV4.tsx` komponieren aus diesen Teilen. Jeder Teil ist ein
 * eigenständiges Anzeige-Element (v4 umhüllt es mit `Parkbar`; IST rendert es
 * direkt über den `RoiAnalyse`-Composite). Daten-Hook `useRoiAnalyse` (ein
 * `getROIDashboard`-Call), KPI-Items `roiKpiItems`, dann Charts/Tabelle.
 *
 * Regel-SoT: R1 alle Geld-Zahlen via `fmtZahl`/`formatGeld` (kein `.toLocaleString`/
 * `.toFixed`) · R2 Geld in € ohne k€-Transform (Achsen ebenso) · R3 Geld-Rollen über
 * `GELD_TEXT_CLASS` · R4 CO₂ nur prop-gated (`zeigeCo2`; v4 = false → CO₂ raus aus
 * KPI + Detailtabelle, IST behält es per Default). Parameter (Strompreis/Einspeise-
 * vergütung/Benzinpreis/Jahr) kommen als Props — IST reicht die Slider durch, v4 die
 * Anlagen-Defaults (D3: „rebuild-lite, Slider weg"). KEIN Anlagen-Selektor (Shell).
 */
import { useState, useEffect, useMemo, Fragment } from 'react'
import {
  TrendingUp, Clock, Leaf, PiggyBank, Car, Flame, Battery, Plug,
  Settings2, Sun, LayoutGrid, ChevronDown, ChevronRight,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line,
} from 'recharts'
import { Card, Alert, LoadingSpinner, EmptyState, FormelTooltip, QuelleBadge, ChartLegende } from '../ui'
import ChartTooltip from '../ui/ChartTooltip'
import { KpiStrip, type KpiStripItem } from '../blocks'
import { investitionenApi, type ROIDashboardResponse, type ROIBerechnung, type SpeicherRoiDetail } from '../../api'
import { TYP_COLORS, GELD_COLORS, GELD_TEXT_CLASS, fmtZahl, formatGeld, formatCo2, achsenEinheit, ACHSEN_MARGIN_TOP } from '../../lib'

const typIcons: Record<string, React.ElementType> = {
  'e-auto': Car,
  'waermepumpe': Flame,
  'speicher': Battery,
  'wallbox': Plug,
  'wechselrichter': Settings2,
  'pv-module': Sun,
  'balkonkraftwerk': LayoutGrid,
  'sonstiges': Settings2,
}

const typLabels: Record<string, string> = {
  'e-auto': 'E-Auto',
  'waermepumpe': 'Wärmepumpe',
  'speicher': 'Speicher',
  'wallbox': 'Wallbox',
  'wechselrichter': 'Wechselrichter',
  'pv-module': 'PV-Module',
  'balkonkraftwerk': 'Balkonkraftwerk',
  'sonstiges': 'Sonstiges',
}

const geldTick = (v: number) => fmtZahl(v, 0)

export interface RoiAnalyseProps {
  anlageId: number
  /** Berechnungs-Parameter (Override); undefined ⇒ Backend löst Default auf. */
  strompreis?: number
  einspeiseverguetung?: number
  benzinpreis?: number
  jahr?: number | 'all'
  /** CO₂-KPI + Detailspalte zeigen (R4). IST = true (Default), v4 = false. */
  zeigeCo2?: boolean
  /** Optionaler Rückkanal der geladenen Antwort (z. B. für den Benzinpreis-Hinweis
   *  im Slider der IST-Seite). */
  onLoaded?: (data: ROIDashboardResponse) => void
}

export interface RoiAnalyseVM {
  loading: boolean
  error: string | null
  setError: (e: string | null) => void
  roiData: ROIDashboardResponse | null
  amortisationData: Array<{ jahr: number; kumulierte_einsparung: number; investition: number }>
  einsparungenByTyp: Array<{ name: string; value: number; color: string }>
  investitionenChart: Array<{
    name: string; fullName: string; kosten: number; einsparung: number
    amortisation: number; typ: string; color: string
  }>
}

/**
 * Etappe C (#264): Speicher-spezifisches C-Detail aus einer ROI-Berechnung
 * ziehen — egal ob AC-gekoppelt (eigene Berechnung) oder DC-gekoppelt
 * (Komponente eines PV-Systems). Liefert null, wenn keine belastbaren
 * C-Felder vorliegen (z. B. Prognose-Modus ohne IST-Daten).
 */
function getSpeicherCDetail(b: ROIBerechnung): SpeicherRoiDetail | null {
  if (b.investition_typ === 'speicher') {
    const d = b.detail_berechnung as SpeicherRoiDetail
    return d && d.wirkungsgrad_quelle ? d : null
  }
  const sp = b.komponenten?.find((k) => k.typ === 'speicher')
  if (sp) {
    const d = sp.detail as SpeicherRoiDetail
    return d && d.wirkungsgrad_quelle ? d : null
  }
  return null
}

/** Lädt das ROI-Dashboard (ein `getROIDashboard`-Call) und leitet Amortisations-
 *  Zeitreihe + Typ-/Investitions-Aggregate ab. Geteilt von IST + v4. */
export function useRoiAnalyse({ anlageId, strompreis, einspeiseverguetung, benzinpreis, jahr, onLoaded }: RoiAnalyseProps): RoiAnalyseVM {
  const [roiData, setRoiData] = useState<ROIDashboardResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!anlageId) return
    let ab = false
    const loadROI = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await investitionenApi.getROIDashboard(anlageId, strompreis, einspeiseverguetung, benzinpreis, jahr)
        if (!ab) { setRoiData(data); onLoaded?.(data) }
      } catch (e) {
        if (!ab) setError(e instanceof Error ? e.message : 'Fehler beim Laden der ROI-Daten')
      } finally {
        if (!ab) setLoading(false)
      }
    }
    loadROI()
    return () => { ab = true }
    // onLoaded bewusst nicht in den Deps (Eltern reicht inline-Callback durch).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anlageId, strompreis, einspeiseverguetung, benzinpreis, jahr])

  const amortisationData = useMemo(() => {
    if (!roiData || roiData.gesamt_relevante_kosten <= 0) return []
    const data = []
    let kumulierteEinsparung = 0
    const maxJahre = Math.min(Math.ceil((roiData.gesamt_amortisation_jahre ?? 20) * 1.5), 30)
    for (let j = 0; j <= maxJahre; j++) {
      data.push({
        jahr: j,
        kumulierte_einsparung: Math.round(kumulierteEinsparung),
        investition: roiData.gesamt_relevante_kosten,
      })
      kumulierteEinsparung += roiData.gesamt_jahres_einsparung
    }
    return data
  }, [roiData])

  const einsparungenByTyp = useMemo(() => {
    if (!roiData) return []
    const grouped: Record<string, number> = {}
    roiData.berechnungen.forEach((b) => {
      grouped[b.investition_typ] = (grouped[b.investition_typ] || 0) + b.jahres_einsparung
    })
    return Object.entries(grouped)
      .map(([typ, value]) => ({
        name: typLabels[typ] || typ,
        value: Math.round(value),
        color: TYP_COLORS[typ] || TYP_COLORS['sonstiges'],
      }))
      .filter((d) => d.value > 0)
  }, [roiData])

  const investitionenChart = useMemo(() => {
    if (!roiData) return []
    return roiData.berechnungen.map((b) => ({
      name: b.investition_bezeichnung.length > 15 ? b.investition_bezeichnung.substring(0, 15) + '...' : b.investition_bezeichnung,
      fullName: b.investition_bezeichnung,
      kosten: b.relevante_kosten,
      einsparung: b.jahres_einsparung,
      amortisation: b.amortisation_jahre ?? 0,
      typ: b.investition_typ,
      color: TYP_COLORS[b.investition_typ] || TYP_COLORS['sonstiges'],
    }))
  }, [roiData])

  return { loading, error, setError, roiData, amortisationData, einsparungenByTyp, investitionenChart }
}

/** Block ① — KPIs Investition · Einsparung · Amortisation. CO₂-KPI nur bei
 *  `zeigeCo2` (R4: v4 = aus → 3 KPIs, IST = an → 4 KPIs). */
export function roiKpiItems(roiData: ROIDashboardResponse, zeigeCo2 = false): KpiStripItem[] {
  const items: KpiStripItem[] = [
    {
      title: 'Gesamtinvestition', value: formatGeld(roiData.gesamt_investition).wert, unit: '€',
      color: 'blue', icon: PiggyBank, parkId: 'kpi:investition',
      subtitle: `Relevant: ${formatGeld(roiData.gesamt_relevante_kosten).text}`,
      sicht: 'Gesamt-Anlage · Vollkosten + Mehrkosten-Ansatz im Untertitel',
      formel: 'Σ Anschaffungskosten aller Investitionen',
      berechnung: 'Relevant = Gesamt − Alternativkosten',
      ergebnis: `= ${formatGeld(roiData.gesamt_relevante_kosten).text}`,
    },
    {
      title: 'Jährliche Einsparung', value: formatGeld(roiData.gesamt_jahres_einsparung).wert, unit: '€',
      color: 'green', icon: TrendingUp, parkId: 'kpi:einsparung',
      subtitle: roiData.gesamt_roi_prozent ? `ROI: ${roiData.gesamt_roi_prozent} %` : 'ROI: -',
      sicht: 'Gesamt-Anlage · Jahres-Prognose · Mehrkosten-Ansatz',
      formel: 'Σ Einsparungen aller Investitionen',
      berechnung: roiData.gesamt_relevante_kosten > 0 ? 'ROI = Einsparung ÷ Kosten × 100' : undefined,
      ergebnis: roiData.gesamt_roi_prozent ? `= ${roiData.gesamt_roi_prozent} % ROI` : undefined,
    },
    {
      title: 'Amortisation', value: roiData.gesamt_amortisation_jahre ? `${roiData.gesamt_amortisation_jahre}` : '-',
      unit: roiData.gesamt_amortisation_jahre ? 'Jahre' : undefined,
      color: 'orange', icon: Clock, parkId: 'kpi:amortisation',
      subtitle: 'Bis zur Kostendeckung',
      sicht: 'Gesamt-Anlage · Mehrkosten-Ansatz · Prognose (rechnerisch, ohne bisherige Erträge)',
      formel: 'Relevante Kosten ÷ Jährliche Einsparung',
      berechnung: roiData.gesamt_jahres_einsparung > 0 ? `${formatGeld(roiData.gesamt_relevante_kosten).text} ÷ ${formatGeld(roiData.gesamt_jahres_einsparung).text}/Jahr` : undefined,
      ergebnis: roiData.gesamt_amortisation_jahre ? `= ${roiData.gesamt_amortisation_jahre} Jahre` : undefined,
    },
  ]
  if (zeigeCo2) {
    items.push({
      title: 'CO2-Einsparung', value: formatCo2(roiData.gesamt_co2_einsparung_kg).wert, unit: formatCo2(roiData.gesamt_co2_einsparung_kg).einheit,
      color: 'green', icon: Leaf, parkId: 'kpi:co2', subtitle: 'pro Jahr',
      sicht: 'Gesamt-Anlage · Jahres-Prognose',
      formel: 'Σ CO2-Einsparungen aller Investitionen',
      berechnung: 'Je nach Investitionstyp unterschiedlich',
      ergebnis: `= ${formatCo2(roiData.gesamt_co2_einsparung_kg).text}/Jahr`,
    })
  }
  return items
}

/** Block ② — Amortisationsverlauf (Break-Even-Kurve, 25–30 Jahre). */
export function RoiAmortisationChart({ vm }: { vm: RoiAnalyseVM }) {
  const roiData = vm.roiData
  if (!roiData) return null
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Amortisationsverlauf</h3>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={vm.amortisationData} margin={{ top: ACHSEN_MARGIN_TOP }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis dataKey="jahr" tickFormatter={geldTick} tick={{ fontSize: 10 }} /* achsen-allow: Jahres-Index (0–30), Einheit „Jahre" steht im Break-Even-Text + KPI; Achsen-Label kollidierte mit Legende (#29-15) */ />
            <YAxis tickFormatter={geldTick} tick={{ fontSize: 10 }} width={70} label={achsenEinheit('€')} />
            <Tooltip content={<ChartTooltip labelFormatter={(label) => `Jahr ${label}`} unit="€" />} />
            <Legend content={<ChartLegende />} />
            <Line type="monotone" dataKey="kumulierte_einsparung" name="Kumulierte Einsparung" stroke={GELD_COLORS.ersparnis} strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="investition" name="Investition" stroke={GELD_COLORS.kosten} strokeWidth={2} strokeDasharray="5 5" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {roiData.gesamt_amortisation_jahre && (
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 text-center">
          Break-Even nach ca. {fmtZahl(roiData.gesamt_amortisation_jahre, 1)} Jahren
        </p>
      )}
    </Card>
  )
}

/** Block ③a — Einsparungen nach Investitionstyp (Pie). */
export function RoiTypPie({ vm }: { vm: RoiAnalyseVM }) {
  const daten = vm.einsparungenByTyp
  const summe = daten.reduce((s, d) => s + d.value, 0)
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Einsparungen nach Typ</h3>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            {/* Keine Pie-Außenlabels: die ragten mit `labelLine` über den Container
                und wurden auf schmalen Screens abgeschnitten (detLAN 2026-06-28).
                Name + % stehen jetzt in der umbruchfähigen Legende darunter — auf
                jeder Breite vollständig sichtbar. */}
            <Pie
              data={daten}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={100}
            >
              {daten.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip content={<ChartTooltip unit="€/Jahr" />} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1">
        {daten.map((d) => (
          <li key={d.name} className="flex items-center gap-1.5 text-sm">
            <span className="inline-block w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: d.color }} />
            <span className="text-gray-700 dark:text-gray-300">{d.name}</span>
            <span className="text-gray-400 dark:text-gray-500 tabular-nums">{fmtZahl(summe > 0 ? (d.value / summe) * 100 : 0, 0)} %</span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

/** Block ③b — Investitionen im Vergleich (Kosten vs. Einsparung, horizontale Bars). */
export function RoiVergleichBar({ vm }: { vm: RoiAnalyseVM }) {
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Investitionen im Vergleich</h3>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={vm.investitionenChart} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            {/* D9-F: Domain an Daten klemmen (Werte ≥ 0 → kein leerer Negativbereich) + € als Einheit. */}
            <XAxis type="number" domain={[0, 'auto']} tickFormatter={(v) => `${fmtZahl(v, 0)} €`} tick={{ fontSize: 10 }} /* achsen-allow: Wert-Achse waagerecht, Einheit/Format pro Tick (de-DE) */ />
            <YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 10 }} /* achsen-allow: Kategorie-Namen (Investitionen) */ />
            <Tooltip content={<ChartTooltip formatter={(value: number, name: string) => name === 'Relevante Kosten' ? `${fmtZahl(value, 0)} €` : `${fmtZahl(value, 0)} €/Jahr`} />} />
            <Legend content={<ChartLegende />} />
            <Bar dataKey="kosten" fill={GELD_COLORS.kosten} name="Relevante Kosten" />
            <Bar dataKey="einsparung" fill={GELD_COLORS.ersparnis} name="Jährliche Einsparung" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

/** Aufklappbares C-Detail einer Speicher-ROI-Zeile (Etappe C, #264). */
function SpeicherDetailPanel({ detail }: { detail: SpeicherRoiDetail }) {
  const lp = detail.effektiver_ladepreis_cent
  const eta = detail.verwendetes_wirkungsgrad_prozent
  return (
    <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800/50 space-y-2">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
        <span className="flex items-center gap-2">
          <span className="text-gray-500 dark:text-gray-400">Effektiver Ladepreis:</span>
          <span className="font-medium text-gray-900 dark:text-white">
            {lp != null ? `${fmtZahl(lp, 2)} ct/kWh` : '—'}
          </span>
          {detail.ladepreis_quelle && (
            <QuelleBadge quelle={detail.ladepreis_quelle} kind="ladepreis" />
          )}
          {detail.ladepreis_abdeckung_prozent != null && (
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {fmtZahl(detail.ladepreis_abdeckung_prozent, 0)} % Abdeckung
            </span>
          )}
        </span>
        <span className="flex items-center gap-2">
          <span className="text-gray-500 dark:text-gray-400">Verwendeter Wirkungsgrad:</span>
          <span className="font-medium text-gray-900 dark:text-white">
            {eta != null ? `${fmtZahl(eta, 1)} %` : '—'}
          </span>
          {detail.wirkungsgrad_quelle && (
            <QuelleBadge quelle={detail.wirkungsgrad_quelle} kind="wirkungsgrad" />
          )}
        </span>
      </div>
      {detail.eta_degradation_alarm && detail.param_wirkungsgrad_prozent != null && (
        <p className="text-xs text-amber-700 dark:text-amber-300">
          ⚠ Gemessener Wirkungsgrad liegt mehr als 5 Prozentpunkte unter dem
          Parameter-Wert ({fmtZahl(detail.param_wirkungsgrad_prozent, 1)} %) —
          möglicher Hinweis auf Speicher-Degradation.
        </p>
      )}
    </div>
  )
}

/** Block ④ — Detailübersicht je Investition (+ Speicher-C-Panel #264, Formel-Tooltips).
 *  CO₂-Spalte nur bei `zeigeCo2` (R4: v4 = aus, IST = an). */
export function RoiDetailTabelle({ vm, zeigeCo2 = true }: { vm: RoiAnalyseVM; zeigeCo2?: boolean }) {
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())
  const roiData = vm.roiData
  if (!roiData) return null
  const cols = zeigeCo2 ? 6 : 5
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Detailübersicht</h3>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead>
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Investition</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Kosten</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Einsparung/Jahr</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">ROI</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Amortisation</th>
              {zeigeCo2 && <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">CO2</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
            {roiData.berechnungen.map((b) => {
              const Icon = typIcons[b.investition_typ] || Settings2
              const cDetail = getSpeicherCDetail(b)
              const isExpanded = expandedRows.has(b.investition_id)
              return (
                <Fragment key={b.investition_id}>
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-800">
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        {cDetail ? (
                          <button
                            type="button"
                            onClick={() => setExpandedRows((prev) => {
                              const next = new Set(prev)
                              if (next.has(b.investition_id)) next.delete(b.investition_id)
                              else next.add(b.investition_id)
                              return next
                            })}
                            className="text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 flex-shrink-0"
                            aria-label="Speicher-Details ein-/ausklappen"
                          >
                            {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                          </button>
                        ) : (
                          <span className="w-4 flex-shrink-0" />
                        )}
                        <Icon className="h-4 w-4 flex-shrink-0" style={{ color: TYP_COLORS[b.investition_typ] }} />
                        <div>
                          <p className="text-sm font-medium text-gray-900 dark:text-white">{b.investition_bezeichnung}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">{typLabels[b.investition_typ]}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-right">
                      <p className="text-sm text-gray-900 dark:text-white">{formatGeld(b.relevante_kosten).text}</p>
                      {b.anschaffungskosten_alternativ > 0 && (
                        <p className="text-xs text-gray-500 dark:text-gray-400">({formatGeld(b.anschaffungskosten).text} gesamt)</p>
                      )}
                    </td>
                    <td className={`px-4 py-3 whitespace-nowrap text-right text-sm font-medium ${GELD_TEXT_CLASS.ersparnis}`}>
                      {formatGeld(b.jahres_einsparung).text}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-right text-sm">
                      {b.roi_prozent ? (
                        <FormelTooltip
                          sicht="Pro Investition · Jahres-ROI · Mehrkosten-Ansatz · Prognose"
                          formel="Jahresersparnis ÷ Relevante Kosten × 100"
                          berechnung={`${formatGeld(b.jahres_einsparung).text} ÷ ${formatGeld(b.relevante_kosten).text} × 100`}
                          ergebnis={`= ${b.roi_prozent} % p.a.`}
                        >
                          <span className={b.roi_prozent >= 10 ? `${GELD_TEXT_CLASS.ersparnis} cursor-help border-b border-dotted border-green-400` : 'text-gray-900 dark:text-white cursor-help border-b border-dotted border-gray-400'}>
                            {b.roi_prozent} %
                          </span>
                        </FormelTooltip>
                      ) : (
                        <span className="text-gray-400 dark:text-gray-500">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-right text-sm">
                      {b.amortisation_jahre ? (
                        <FormelTooltip
                          sicht="Pro Investition · Mehrkosten-Ansatz · Prognose (rechnerisch, ohne bisherige Erträge)"
                          formel="Relevante Kosten ÷ Jahresersparnis"
                          berechnung={`${formatGeld(b.relevante_kosten).text} ÷ ${formatGeld(b.jahres_einsparung).text}/Jahr`}
                          ergebnis={`= ${b.amortisation_jahre} Jahre`}
                        >
                          <span className={b.amortisation_jahre <= 10 ? `${GELD_TEXT_CLASS.ersparnis} cursor-help border-b border-dotted border-green-400` : 'text-orange-500 cursor-help border-b border-dotted border-orange-400'}>
                            {b.amortisation_jahre} J.
                          </span>
                        </FormelTooltip>
                      ) : (
                        <span className="text-gray-400 dark:text-gray-500">-</span>
                      )}
                    </td>
                    {zeigeCo2 && (
                      <td className="px-4 py-3 whitespace-nowrap text-right text-sm text-emerald-600 dark:text-emerald-400">
                        {b.co2_einsparung_kg ? `${fmtZahl(b.co2_einsparung_kg, 0)} kg` : '-'}
                      </td>
                    )}
                  </tr>
                  {cDetail && isExpanded && (
                    <tr>
                      <td colSpan={cols} className="p-0"><SpeicherDetailPanel detail={cDetail} /></td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
          <tfoot>
            <tr className="bg-gray-50 dark:bg-gray-800 font-semibold">
              <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">Gesamt</td>
              <td className="px-4 py-3 text-right text-sm text-gray-900 dark:text-white">{formatGeld(roiData.gesamt_relevante_kosten).text}</td>
              <td className={`px-4 py-3 text-right text-sm ${GELD_TEXT_CLASS.ersparnis}`}>{formatGeld(roiData.gesamt_jahres_einsparung).text}</td>
              <td className="px-4 py-3 text-right text-sm text-gray-900 dark:text-white">{roiData.gesamt_roi_prozent ? `${roiData.gesamt_roi_prozent} %` : '-'}</td>
              <td className="px-4 py-3 text-right text-sm text-gray-900 dark:text-white">{roiData.gesamt_amortisation_jahre ? `${roiData.gesamt_amortisation_jahre} J.` : '-'}</td>
              {zeigeCo2 && (
                <td className="px-4 py-3 text-right text-sm text-emerald-600 dark:text-emerald-400">{fmtZahl(roiData.gesamt_co2_einsparung_kg, 0)} kg</td>
              )}
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  )
}

/** Prognose-Disclaimer (Block ④-Fuß). */
export function RoiHinweis() {
  return (
    <Alert type="info">
      <strong>Hinweis:</strong> Die Berechnungen sind Prognosen basierend auf den eingegebenen Parametern.
      Die tatsächlichen Einsparungen können je nach Nutzungsverhalten und Energiepreisen abweichen.
    </Alert>
  )
}

/**
 * RoiAnalyse — Composite für die IST-Seite (`pages/ROIDashboard.tsx`): lädt + rendert
 * alle Teile in der bisherigen Reihenfolge (KPIs · Amortisation+Pie · Vergleich ·
 * Tabelle · Hinweis). v4 komponiert dieselben Teile selbst in BlockShell-Blöcke.
 */
export function RoiAnalyse(props: RoiAnalyseProps) {
  const vm = useRoiAnalyse(props)

  if (vm.error) {
    return <Alert type="error" onClose={() => vm.setError(null)}>{vm.error}</Alert>
  }
  if (vm.loading) {
    return <LoadingSpinner text="Berechne ROI..." />
  }
  if (vm.roiData && vm.roiData.berechnungen.length === 0) {
    return (
      <EmptyState
        icon={PiggyBank}
        title="Keine aktiven Investitionen"
        description="Erfasse Investitionen auf der Investitionen-Seite, um deren Wirtschaftlichkeit zu analysieren."
      />
    )
  }
  if (!vm.roiData) return null

  const zeigeCo2 = props.zeigeCo2 ?? true
  return (
    <div className="space-y-6">
      <KpiStrip kpis={roiKpiItems(vm.roiData, zeigeCo2)} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <RoiAmortisationChart vm={vm} />
        <RoiTypPie vm={vm} />
      </div>
      <RoiVergleichBar vm={vm} />
      <RoiDetailTabelle vm={vm} zeigeCo2={zeigeCo2} />
      <RoiHinweis />
    </div>
  )
}
