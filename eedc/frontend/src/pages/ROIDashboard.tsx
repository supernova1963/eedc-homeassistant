/**
 * ROI-Dashboard - Wirtschaftlichkeitsanalyse aller Investitionen
 */

import { useState, useEffect, useMemo, Fragment } from 'react'
import {
  TrendingUp,
  Clock,
  Leaf,
  PiggyBank,
  Car,
  Flame,
  Battery,
  Plug,
  Settings2,
  Sun,
  LayoutGrid,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
} from 'recharts'
import { Card, Alert, LoadingSpinner, EmptyState, FormelTooltip, fmtCalc, QuelleBadge, KPICard } from '../components/ui'
import ChartTooltip from '../components/ui/ChartTooltip'
import { useSelectedAnlage, useAktuellerStrompreis } from '../hooks'
import { investitionenApi, type ROIDashboardResponse, type ROIBerechnung, type SpeicherRoiDetail } from '../api'
import { TYP_COLORS, GELD_COLORS } from '../lib'

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
            {lp != null ? `${lp.toFixed(2)} ct/kWh` : '—'}
          </span>
          {detail.ladepreis_quelle && (
            <QuelleBadge quelle={detail.ladepreis_quelle} kind="ladepreis" />
          )}
          {detail.ladepreis_abdeckung_prozent != null && (
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {detail.ladepreis_abdeckung_prozent.toFixed(0)} % Abdeckung
            </span>
          )}
        </span>
        <span className="flex items-center gap-2">
          <span className="text-gray-500 dark:text-gray-400">Verwendeter Wirkungsgrad:</span>
          <span className="font-medium text-gray-900 dark:text-white">
            {eta != null ? `${eta.toFixed(1)} %` : '—'}
          </span>
          {detail.wirkungsgrad_quelle && (
            <QuelleBadge quelle={detail.wirkungsgrad_quelle} kind="wirkungsgrad" />
          )}
        </span>
      </div>
      {detail.eta_degradation_alarm && detail.param_wirkungsgrad_prozent != null && (
        <p className="text-xs text-amber-700 dark:text-amber-300">
          ⚠ Gemessener Wirkungsgrad liegt mehr als 5 Prozentpunkte unter dem
          Parameter-Wert ({detail.param_wirkungsgrad_prozent.toFixed(1)} %) —
          möglicher Hinweis auf Speicher-Degradation.
        </p>
      )}
    </div>
  )
}

export default function ROIDashboard() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const [roiData, setRoiData] = useState<ROIDashboardResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Etappe C (#264): aufgeklappte Speicher-Detail-Zeilen (per investition_id).
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())

  // Anpassbare Parameter
  const [strompreis, setStrompreis] = useState<number>(30)
  const [einspeiseverguetung, setEinspeiseverguetung] = useState<number>(8.2)
  // Slider als reines Override: leer = Backend löst pro Investition auf
  // (per-Inv `benzinpreis_euro` → letzter Monatsdaten-Preis → Default).
  // Hardcoded 1.85 hätte den per-Inv-Wert stillschweigend überschrieben.
  const [benzinpreis, setBenzinpreis] = useState<number | undefined>(undefined)

  const anlageId = selectedAnlageId
  const { strompreis: aktuellerStrompreis } = useAktuellerStrompreis(anlageId ?? null)

  // Strompreis aus DB übernehmen wenn verfügbar
  useEffect(() => {
    if (aktuellerStrompreis) {
      setStrompreis(aktuellerStrompreis.netzbezug_arbeitspreis_cent_kwh)
      setEinspeiseverguetung(aktuellerStrompreis.einspeiseverguetung_cent_kwh)
    }
  }, [aktuellerStrompreis])

  // ROI-Daten laden
  useEffect(() => {
    if (!anlageId) return

    const loadROI = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await investitionenApi.getROIDashboard(
          anlageId,
          strompreis,
          einspeiseverguetung,
          benzinpreis
        )
        setRoiData(data)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden der ROI-Daten')
      } finally {
        setLoading(false)
      }
    }

    loadROI()
  }, [anlageId, strompreis, einspeiseverguetung, benzinpreis])

  // Amortisations-Zeitreihe berechnen
  const amortisationData = useMemo(() => {
    if (!roiData || roiData.gesamt_relevante_kosten <= 0) return []

    const data = []
    let kumulierteEinsparung = 0
    const maxJahre = Math.min(
      Math.ceil((roiData.gesamt_amortisation_jahre ?? 20) * 1.5),
      30
    )

    for (let jahr = 0; jahr <= maxJahre; jahr++) {
      data.push({
        jahr,
        kumulierte_einsparung: Math.round(kumulierteEinsparung),
        investition: roiData.gesamt_relevante_kosten,
      })
      kumulierteEinsparung += roiData.gesamt_jahres_einsparung
    }

    return data
  }, [roiData])

  // Einsparungen nach Typ
  const einsparungenByTyp = useMemo(() => {
    if (!roiData) return []

    const grouped: Record<string, number> = {}
    roiData.berechnungen.forEach(b => {
      const typ = b.investition_typ
      grouped[typ] = (grouped[typ] || 0) + b.jahres_einsparung
    })

    return Object.entries(grouped)
      .map(([typ, value]) => ({
        name: typLabels[typ] || typ,
        value: Math.round(value),
        color: TYP_COLORS[typ] || TYP_COLORS['sonstiges'],
      }))
      .filter(d => d.value > 0)
  }, [roiData])

  // Einzelne Investitionen für Balkendiagramm
  const investitionenChart = useMemo(() => {
    if (!roiData) return []

    return roiData.berechnungen.map(b => ({
      name: b.investition_bezeichnung.length > 15
        ? b.investition_bezeichnung.substring(0, 15) + '...'
        : b.investition_bezeichnung,
      fullName: b.investition_bezeichnung,
      kosten: b.relevante_kosten,
      einsparung: b.jahres_einsparung,
      amortisation: b.amortisation_jahre ?? 0,
      typ: b.investition_typ,
      color: TYP_COLORS[b.investition_typ] || TYP_COLORS['sonstiges'],
    }))
  }, [roiData])

  if (anlagenLoading) {
    return <LoadingSpinner text="Lade Daten..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          ROI-Dashboard
        </h1>
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an.
        </Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            ROI-Dashboard
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Wirtschaftlichkeitsanalyse deiner Investitionen
          </p>
        </div>
        <div className="flex items-center gap-3">
          {anlagen.length > 1 && (
            <select
              value={anlageId ?? ''}
              onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
              className="input w-auto"
            >
              {anlagen.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.anlagenname}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {error && (
        <Alert type="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Parameter-Eingabe */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Settings2 className="h-5 w-5 text-gray-500" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Berechnungsparameter
          </h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Strompreis (Cent/kWh)
            </label>
            <input
              type="number"
              step="0.1"
              value={strompreis}
              onChange={(e) => setStrompreis(Number(e.target.value))}
              className="input"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Einspeisevergütung (Cent/kWh)
            </label>
            <input
              type="number"
              step="0.1"
              value={einspeiseverguetung}
              onChange={(e) => setEinspeiseverguetung(Number(e.target.value))}
              className="input"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Benzinpreis (Euro/Liter)
            </label>
            <input
              type="number"
              step="0.01"
              value={benzinpreis ?? ''}
              placeholder={roiData?.benzinpreis_hinweis_euro?.toFixed(2) ?? '1.65'}
              onChange={(e) => {
                const v = e.target.value
                setBenzinpreis(v === '' ? undefined : Number(v))
              }}
              className="input"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Leer lassen → pro E-Auto wird der gepflegte Wert bzw. der aktuelle
              Marktpreis aus den Monatsdaten verwendet.
            </p>
          </div>
        </div>
      </Card>

      {loading && <LoadingSpinner text="Berechne ROI..." />}

      {!loading && roiData && roiData.berechnungen.length === 0 && (
        <EmptyState
          icon={PiggyBank}
          title="Keine aktiven Investitionen"
          description="Erfasse Investitionen auf der Investitionen-Seite, um deren Wirtschaftlichkeit zu analysieren."
        />
      )}

      {!loading && roiData && roiData.berechnungen.length > 0 && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard
              icon={PiggyBank}
              title="Gesamtinvestition"
              value={`${roiData.gesamt_investition.toLocaleString('de-DE')} €`}
              subtitle={`Relevant: ${roiData.gesamt_relevante_kosten.toLocaleString('de-DE')} €`}
              color="blue"
              sicht="Gesamt-Anlage · Vollkosten + Mehrkosten-Ansatz im Untertitel"
              formel="Σ Anschaffungskosten aller Investitionen"
              berechnung={`Relevant = Gesamt − Alternativkosten`}
              ergebnis={`= ${fmtCalc(roiData.gesamt_relevante_kosten, 0)} €`}
            />
            <KPICard
              icon={TrendingUp}
              title="Jährliche Einsparung"
              value={`${roiData.gesamt_jahres_einsparung.toLocaleString('de-DE')} €`}
              subtitle={roiData.gesamt_roi_prozent ? `ROI: ${roiData.gesamt_roi_prozent} %` : 'ROI: -'}
              color="green"
              sicht="Gesamt-Anlage · Jahres-Prognose · Mehrkosten-Ansatz"
              formel="Σ Einsparungen aller Investitionen"
              berechnung={roiData.gesamt_relevante_kosten > 0 ? `ROI = Einsparung ÷ Kosten × 100` : undefined}
              ergebnis={roiData.gesamt_roi_prozent ? `= ${roiData.gesamt_roi_prozent} % ROI` : undefined}
            />
            <KPICard
              icon={Clock}
              title="Amortisation"
              value={roiData.gesamt_amortisation_jahre ? `${roiData.gesamt_amortisation_jahre} Jahre` : '-'}
              subtitle="Bis zur Kostendeckung"
              color="orange"
              sicht="Gesamt-Anlage · Mehrkosten-Ansatz · Prognose (rechnerisch, ohne bisherige Erträge)"
              formel="Relevante Kosten ÷ Jährliche Einsparung"
              berechnung={roiData.gesamt_jahres_einsparung > 0 ? `${fmtCalc(roiData.gesamt_relevante_kosten, 0)} € ÷ ${fmtCalc(roiData.gesamt_jahres_einsparung, 0)} €/Jahr` : undefined}
              ergebnis={roiData.gesamt_amortisation_jahre ? `= ${roiData.gesamt_amortisation_jahre} Jahre` : undefined}
            />
            <KPICard
              icon={Leaf}
              title="CO2-Einsparung"
              value={`${roiData.gesamt_co2_einsparung_kg.toLocaleString('de-DE')} kg`}
              subtitle="pro Jahr"
              color="green"
              sicht="Gesamt-Anlage · Jahres-Prognose"
              formel="Σ CO2-Einsparungen aller Investitionen"
              berechnung="Je nach Investitionstyp unterschiedlich"
              ergebnis={`= ${fmtCalc(roiData.gesamt_co2_einsparung_kg / 1000, 2)} t CO2/Jahr`}
            />
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Amortisations-Chart */}
            <Card>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Amortisationsverlauf
              </h3>
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={amortisationData}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                    <XAxis
                      dataKey="jahr"
                      label={{ value: 'Jahre', position: 'bottom' }}
                      tick={{ fontSize: 12 }}
                    />
                    <YAxis
                      tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                      tick={{ fontSize: 12 }}
                    />
                    <Tooltip content={<ChartTooltip
                      labelFormatter={(label) => `Jahr ${label}`}
                      unit="€"
                    />} />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="kumulierte_einsparung"
                      name="Kumulierte Einsparung"
                      stroke={GELD_COLORS.ersparnis}
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="investition"
                      name="Investition"
                      stroke={GELD_COLORS.kosten}
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              {roiData.gesamt_amortisation_jahre && (
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 text-center">
                  Break-Even nach ca. {roiData.gesamt_amortisation_jahre} Jahren
                </p>
              )}
            </Card>

            {/* Einsparungen nach Typ */}
            <Card>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Einsparungen nach Typ
              </h3>
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={einsparungenByTyp}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={100}
                      label={({ name, percent }) =>
                        `${name}: ${(percent * 100).toFixed(0)} %`
                      }
                      labelLine={true}
                    >
                      {einsparungenByTyp.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip content={<ChartTooltip unit="€/Jahr" />} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          {/* Investitionen im Vergleich */}
          <Card>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Investitionen im Vergleich
            </h3>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={investitionenChart} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis type="number" tickFormatter={(v) => `${v.toLocaleString('de-DE')}`} />
                  <YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 11 }} />
                  <Tooltip content={<ChartTooltip
                    formatter={(value, name) =>
                      name === 'Relevante Kosten'
                        ? `${value.toLocaleString('de-DE')} €`
                        : `${value.toLocaleString('de-DE')} €/Jahr`
                    }
                  />} />
                  <Legend />
                  <Bar dataKey="kosten" fill={GELD_COLORS.kosten} name="Relevante Kosten" />
                  <Bar dataKey="einsparung" fill={GELD_COLORS.ersparnis} name="Jährliche Einsparung" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Detail-Tabelle */}
          <Card>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Detailübersicht
            </h3>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead>
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Investition
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Kosten
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Einsparung/Jahr
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      ROI
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Amortisation
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      CO2
                    </th>
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
                                {isExpanded
                                  ? <ChevronDown className="h-4 w-4" />
                                  : <ChevronRight className="h-4 w-4" />}
                              </button>
                            ) : (
                              <span className="w-4 flex-shrink-0" />
                            )}
                            <Icon
                              className="h-4 w-4 flex-shrink-0"
                              style={{ color: TYP_COLORS[b.investition_typ] }}
                            />
                            <div>
                              <p className="text-sm font-medium text-gray-900 dark:text-white">
                                {b.investition_bezeichnung}
                              </p>
                              <p className="text-xs text-gray-500 dark:text-gray-400">
                                {typLabels[b.investition_typ]}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right">
                          <p className="text-sm text-gray-900 dark:text-white">
                            {b.relevante_kosten.toLocaleString('de-DE')} €
                          </p>
                          {b.anschaffungskosten_alternativ > 0 && (
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                              ({b.anschaffungskosten.toLocaleString('de-DE')} € gesamt)
                            </p>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right text-sm text-green-600 dark:text-green-400 font-medium">
                          {b.jahres_einsparung.toLocaleString('de-DE')} €
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right text-sm">
                          {b.roi_prozent ? (
                            <FormelTooltip
                              sicht="Pro Investition · Jahres-ROI · Mehrkosten-Ansatz · Prognose"
                              formel="Jahresersparnis ÷ Relevante Kosten × 100"
                              berechnung={`${fmtCalc(b.jahres_einsparung, 0)} € ÷ ${fmtCalc(b.relevante_kosten, 0)} € × 100`}
                              ergebnis={`= ${b.roi_prozent} % p.a.`}
                            >
                              <span className={b.roi_prozent >= 10 ? 'text-green-600 dark:text-green-400 cursor-help border-b border-dotted border-green-400' : 'text-gray-900 dark:text-white cursor-help border-b border-dotted border-gray-400'}>
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
                              berechnung={`${fmtCalc(b.relevante_kosten, 0)} € ÷ ${fmtCalc(b.jahres_einsparung, 0)} €/Jahr`}
                              ergebnis={`= ${b.amortisation_jahre} Jahre`}
                            >
                              <span className={b.amortisation_jahre <= 10 ? 'text-green-600 dark:text-green-400 cursor-help border-b border-dotted border-green-400' : 'text-orange-500 cursor-help border-b border-dotted border-orange-400'}>
                                {b.amortisation_jahre} J.
                              </span>
                            </FormelTooltip>
                          ) : (
                            <span className="text-gray-400 dark:text-gray-500">-</span>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right text-sm text-emerald-600 dark:text-emerald-400">
                          {b.co2_einsparung_kg ? `${b.co2_einsparung_kg.toLocaleString('de-DE')} kg` : '-'}
                        </td>
                      </tr>
                      {cDetail && isExpanded && (
                        <tr>
                          <td colSpan={6} className="p-0">
                            <SpeicherDetailPanel detail={cDetail} />
                          </td>
                        </tr>
                      )}
                      </Fragment>
                    )
                  })}
                </tbody>
                <tfoot>
                  <tr className="bg-gray-50 dark:bg-gray-800 font-semibold">
                    <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                      Gesamt
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-gray-900 dark:text-white">
                      {roiData.gesamt_relevante_kosten.toLocaleString('de-DE')} €
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-green-600 dark:text-green-400">
                      {roiData.gesamt_jahres_einsparung.toLocaleString('de-DE')} €
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-gray-900 dark:text-white">
                      {roiData.gesamt_roi_prozent ? `${roiData.gesamt_roi_prozent} %` : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-gray-900 dark:text-white">
                      {roiData.gesamt_amortisation_jahre ? `${roiData.gesamt_amortisation_jahre} J.` : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-emerald-600 dark:text-emerald-400">
                      {roiData.gesamt_co2_einsparung_kg.toLocaleString('de-DE')} kg
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Card>

          {/* Hinweis */}
          <Alert type="info">
            <strong>Hinweis:</strong> Die Berechnungen sind Prognosen basierend auf den eingegebenen Parametern.
            Die tatsächlichen Einsparungen können je nach Nutzungsverhalten und Energiepreisen abweichen.
          </Alert>
        </>
      )}
    </div>
  )
}

