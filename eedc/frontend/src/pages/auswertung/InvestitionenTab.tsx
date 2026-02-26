// Investitionen Tab - ROI Dashboard und Amortisation
import { useState, useEffect, useMemo } from 'react'
import {
  BarChart, Bar, PieChart, Pie, Cell, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import {
  PiggyBank, Wallet, TrendingUp, Calendar,
  ChevronDown, ChevronRight, AlertTriangle
} from 'lucide-react'
import { Card, LoadingSpinner, FormelTooltip, fmtCalc } from '../../components/ui'
import { useInvestitionen } from '../../hooks'
import { investitionenApi, cockpitApi, type ROIDashboardResponse, type ROIKomponente, type CockpitUebersicht } from '../../api'
import { KPICard } from './KPICard'
import { COLORS, TYP_COLORS, TYP_LABELS } from './types'
import type { useAktuellerStrompreis } from '../../hooks'

interface InvestitionenTabProps {
  anlageId: number
  strompreis?: ReturnType<typeof useAktuellerStrompreis>['strompreis']
  selectedYear?: number | 'all'
  zeitraumLabel?: string
}

export function InvestitionenTab({ anlageId, strompreis, selectedYear = 'all' }: InvestitionenTabProps) {
  const { investitionen, loading: invLoading } = useInvestitionen(anlageId)
  const [roiData, setRoiData] = useState<ROIDashboardResponse | null>(null)
  const [roiLoading, setRoiLoading] = useState(true)
  const [cockpitData, setCockpitData] = useState<CockpitUebersicht | null>(null)
  const [expandedSystems, setExpandedSystems] = useState<Set<number>>(new Set())

  useEffect(() => {
    const loadROI = async () => {
      try {
        setRoiLoading(true)
        const [roi, cockpit] = await Promise.all([
          investitionenApi.getROIDashboard(
            anlageId,
            strompreis?.netzbezug_arbeitspreis_cent_kwh,
            strompreis?.einspeiseverguetung_cent_kwh,
            undefined,
            selectedYear
          ),
          // Alle Zeiträume (kein Jahr-Filter) für realisierte Gesamtwerte
          cockpitApi.getUebersicht(anlageId),
        ])
        setRoiData(roi)
        setCockpitData(cockpit)
      } catch (e) {
        console.error('ROI-Dashboard Fehler:', e)
      } finally {
        setRoiLoading(false)
      }
    }
    loadROI()
  }, [anlageId, strompreis, selectedYear])

  // Investitionen nach Typ gruppieren
  const invByTyp = useMemo(() => {
    const grouped: Record<string, typeof investitionen> = {}
    investitionen.forEach(inv => {
      if (!grouped[inv.typ]) grouped[inv.typ] = []
      grouped[inv.typ].push(inv)
    })
    return grouped
  }, [investitionen])

  // Investitionskosten nach Typ
  const kostenByTyp = useMemo(() => {
    return Object.entries(invByTyp).map(([typ, invs]) => ({
      typ,
      label: TYP_LABELS[typ] || typ,
      kosten: invs.reduce((sum, inv) => sum + (inv.anschaffungskosten_gesamt || 0), 0),
      color: TYP_COLORS[typ] || '#6b7280',
    })).filter(t => t.kosten > 0).sort((a, b) => b.kosten - a.kosten)
  }, [invByTyp])

  // Amortisationskurve berechnen
  const amortisationData = useMemo(() => {
    if (!roiData || !roiData.gesamt_jahres_einsparung) return []

    const gesamtInvestition = roiData.gesamt_relevante_kosten
    const jahresErsparnis = roiData.gesamt_jahres_einsparung
    const result = []

    for (let jahr = 0; jahr <= 25; jahr++) {
      const kumulierteErsparnis = jahr * jahresErsparnis
      result.push({
        jahr,
        investition: gesamtInvestition,
        ersparnis: kumulierteErsparnis,
        bilanz: kumulierteErsparnis - gesamtInvestition,
      })
    }
    return result
  }, [roiData])

  if (invLoading || roiLoading) {
    return <LoadingSpinner text="Lade Investitionsdaten..." />
  }

  if (investitionen.length === 0) {
    return (
      <Card className="text-center py-8">
        <PiggyBank className="h-12 w-12 mx-auto text-gray-400 mb-4" />
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Keine Investitionen erfasst
        </h3>
        <p className="text-gray-500 dark:text-gray-400">
          Erfasse Investitionen in den Einstellungen, um die ROI-Auswertung zu sehen.
        </p>
      </Card>
    )
  }

  // Berechnungsdetails für Tooltips extrahieren
  const pvModulDetails = roiData?.berechnungen.find(b => b.investition_typ === 'pv-module')?.detail_berechnung as Record<string, unknown> | undefined
  const hochrechnungsHinweis = pvModulDetails?.hinweis as string | undefined

  return (
    <div className="space-y-6">
      {/* Gesamt-KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="Gesamtinvestition"
          value={(roiData?.gesamt_relevante_kosten || 0).toFixed(0)}
          unit="€"
          subtitle={`${investitionen.length} Komponenten`}
          icon={Wallet}
          color="text-blue-500"
          bgColor="bg-blue-50 dark:bg-blue-900/20"
          formel="Σ Anschaffungskosten − Alternativkosten"
          berechnung={roiData ? `${fmtCalc(roiData.gesamt_investition, 0)} € − ${fmtCalc(roiData.gesamt_investition - roiData.gesamt_relevante_kosten, 0)} € Alternativ` : undefined}
          ergebnis={roiData ? `= ${fmtCalc(roiData.gesamt_relevante_kosten, 0)} € relevante Kosten` : undefined}
        />
        <KPICard
          title="Jahresersparnis"
          value={(roiData?.gesamt_jahres_einsparung || 0).toFixed(0)}
          unit="€/Jahr"
          icon={TrendingUp}
          color="text-green-500"
          bgColor="bg-green-50 dark:bg-green-900/20"
          formel="Einspeiseerlös + Eigenverbrauch-Ersparnis"
          berechnung={pvModulDetails ? `${fmtCalc(pvModulDetails.einspeise_erloes_euro as number, 2)} € + ${fmtCalc(pvModulDetails.ev_ersparnis_euro as number, 2)} €` : 'Σ aller Investitions-Einsparungen'}
          ergebnis={hochrechnungsHinweis || (roiData ? `= ${fmtCalc(roiData.gesamt_jahres_einsparung, 0)} €/Jahr` : undefined)}
        />
        <KPICard
          title="ROI"
          value={roiData?.gesamt_roi_prozent?.toFixed(1) || '---'}
          unit="%"
          subtitle="pro Jahr"
          icon={TrendingUp}
          color="text-purple-500"
          bgColor="bg-purple-50 dark:bg-purple-900/20"
          formel="Jahresersparnis ÷ Relevante Kosten × 100"
          berechnung={roiData && roiData.gesamt_relevante_kosten > 0 ? `${fmtCalc(roiData.gesamt_jahres_einsparung, 0)} € ÷ ${fmtCalc(roiData.gesamt_relevante_kosten, 0)} € × 100` : undefined}
          ergebnis={roiData?.gesamt_roi_prozent ? `= ${roiData.gesamt_roi_prozent.toFixed(1)}% ROI p.a.` : undefined}
        />
        <KPICard
          title="Amortisation"
          value={roiData?.gesamt_amortisation_jahre?.toFixed(1) || '---'}
          unit="Jahre"
          icon={Calendar}
          color="text-amber-500"
          bgColor="bg-amber-50 dark:bg-amber-900/20"
          formel="Relevante Kosten ÷ Jahresersparnis"
          berechnung={roiData && roiData.gesamt_jahres_einsparung > 0 ? `${fmtCalc(roiData.gesamt_relevante_kosten, 0)} € ÷ ${fmtCalc(roiData.gesamt_jahres_einsparung, 0)} €/Jahr` : undefined}
          ergebnis={roiData?.gesamt_amortisation_jahre ? `= ${roiData.gesamt_amortisation_jahre.toFixed(1)} Jahre bis zur Kostendeckung` : undefined}
        />
      </div>

      {/* Tatsächlich realisiert – Vergleich mit konfigurierten Werten */}
      {cockpitData && cockpitData.anzahl_monate > 0 && roiData && (() => {
        const invest = roiData.gesamt_relevante_kosten
        const kumuliert = (cockpitData.netto_ertrag_euro || 0)
          + (cockpitData.wp_ersparnis_euro || 0)
          + (cockpitData.emob_ersparnis_euro || 0)
          + (cockpitData.bkw_ersparnis_euro || 0)
          + (cockpitData.sonstige_netto_euro || 0)
        const jaehrlichRealisiert = kumuliert / (cockpitData.anzahl_monate / 12)
        const roiRealisiert = invest > 0 ? (jaehrlichRealisiert / invest * 100) : 0
        const amortRealisiert = jaehrlichRealisiert > 0 ? (invest / jaehrlichRealisiert) : null
        const realisierungsquote = roiData.gesamt_jahres_einsparung > 0
          ? (jaehrlichRealisiert / roiData.gesamt_jahres_einsparung * 100)
          : null

        return (
          <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 px-4 py-3">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
                  Tatsächlich realisiert
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500">
                  Basis: {cockpitData.anzahl_monate} Monate Echtdaten
                  {cockpitData.zeitraum_von && cockpitData.zeitraum_bis
                    ? ` (${cockpitData.zeitraum_von} – ${cockpitData.zeitraum_bis})`
                    : ''}
                </p>
              </div>
              <div className="flex flex-wrap gap-6">
                <div className="text-center">
                  <p className="text-base font-bold text-gray-700 dark:text-gray-200">
                    {Math.round(jaehrlichRealisiert).toLocaleString('de')} €/Jahr
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500">Ø Jahresersparnis</p>
                </div>
                <div className="text-center">
                  <p className="text-base font-bold text-gray-700 dark:text-gray-200">
                    {roiRealisiert.toFixed(1)} %
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500">ROI p.a.</p>
                </div>
                <div className="text-center">
                  <p className="text-base font-bold text-gray-700 dark:text-gray-200">
                    {amortRealisiert ? amortRealisiert.toFixed(1) : '---'} Jahre
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500">Amortisation</p>
                </div>
                {realisierungsquote !== null && (
                  <div className="text-center">
                    <p className={`text-base font-bold ${realisierungsquote >= 90 ? 'text-green-600 dark:text-green-400' : realisierungsquote >= 70 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400'}`}>
                      {realisierungsquote.toFixed(0)} %
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">Realisierungsquote</p>
                  </div>
                )}
              </div>
            </div>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 italic">
              Die Kacheln oben zeigen Prognosen auf Basis konfigurierter Parameter und aktueller Strompreise.
              Die Realisierungsquote zeigt, wie viel des konfigurierten Potenzials tatsächlich erreicht wurde.
            </p>
          </div>
        )
      })()}

      {/* Investitionen nach Typ - Pie Chart */}
      <div className="grid md:grid-cols-2 gap-6">
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Investitionen nach Kategorie
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={kostenByTyp}
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  dataKey="kosten"
                  nameKey="label"
                  label={({ label, percent }) => `${label}: ${(percent * 100).toFixed(0)}%`}
                  labelLine={false}
                >
                  {kostenByTyp.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => [`${value.toFixed(0)} €`, '']} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Investitionen Bar Chart */}
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Kosten nach Kategorie
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={kostenByTyp} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                <XAxis type="number" unit=" €" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="label" tick={{ fontSize: 11 }} width={100} />
                <Tooltip formatter={(value: number) => [`${value.toFixed(0)} €`, '']} />
                <Bar dataKey="kosten" name="Kosten">
                  {kostenByTyp.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Amortisationskurve */}
      {amortisationData.length > 0 && (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Amortisationsverlauf
          </h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={amortisationData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                <XAxis dataKey="jahr" unit=" J." tick={{ fontSize: 11 }} />
                <YAxis unit=" €" tick={{ fontSize: 11 }} />
                <Tooltip formatter={(value: number) => [`${value.toFixed(0)} €`, '']} />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="investition"
                  name="Investition"
                  stroke={COLORS.grid}
                  fill={COLORS.grid}
                  fillOpacity={0.3}
                />
                <Area
                  type="monotone"
                  dataKey="ersparnis"
                  name="Kum. Ersparnis"
                  stroke={COLORS.feedin}
                  fill={COLORS.feedin}
                  fillOpacity={0.3}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          {roiData?.gesamt_amortisation_jahre && (
            <p className="text-sm text-gray-500 mt-2">
              Break-Even nach ca. {roiData.gesamt_amortisation_jahre.toFixed(1)} Jahren
            </p>
          )}
        </Card>
      )}

      {/* ROI pro Investition */}
      {roiData?.berechnungen && roiData.berechnungen.length > 0 && (() => {
        // Prüfe auf Konfigurationsprobleme
        const orphanModules = roiData.berechnungen.filter(b =>
          b.investition_typ === 'pv-module' &&
          typeof b.detail_berechnung?.hinweis === 'string' &&
          b.detail_berechnung.hinweis.includes('ohne Wechselrichter')
        )
        const emptyWRs = roiData.berechnungen.filter(b =>
          b.investition_typ === 'wechselrichter' &&
          typeof b.detail_berechnung?.hinweis === 'string' &&
          b.detail_berechnung.hinweis.includes('ohne zugeordnete PV-Module')
        )
        const hasConfigIssues = orphanModules.length > 0 || emptyWRs.length > 0

        return (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            ROI pro Investition
          </h3>

          {/* Konfigurationswarnungen */}
          {hasConfigIssues && (
            <div className="mb-4 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5 flex-shrink-0" />
                <div className="text-sm">
                  <p className="font-medium text-amber-800 dark:text-amber-200">Konfiguration unvollständig</p>
                  <ul className="mt-1 text-amber-700 dark:text-amber-300 list-disc list-inside">
                    {orphanModules.length > 0 && (
                      <li>
                        {orphanModules.length} PV-Modul{orphanModules.length > 1 ? 'e' : ''} ohne Wechselrichter-Zuordnung
                        → Bitte unter Einstellungen → Investitionen zuordnen
                      </li>
                    )}
                    {emptyWRs.length > 0 && (
                      <li>
                        {emptyWRs.length} Wechselrichter ohne PV-Module
                        → Bitte PV-Module zuordnen oder Wechselrichter entfernen
                      </li>
                    )}
                  </ul>
                  <p className="mt-2 text-amber-600 dark:text-amber-400 text-xs">
                    Ohne korrekte Zuordnung kann der ROI nicht korrekt auf Systemebene berechnet werden.
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead>
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Bezeichnung</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Typ</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Mehrkosten</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Ersparnis/Jahr</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">ROI</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Amortisation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {roiData.berechnungen.map((b) => {
                  // Tooltip-Inhalte für Kosten
                  const hasAlternativ = b.anschaffungskosten_alternativ > 0
                  const kostenFormel = hasAlternativ
                    ? 'Anschaffung − Alternativkosten'
                    : 'Anschaffungskosten (keine Alternative)'
                  const kostenBerechnung = hasAlternativ
                    ? `${fmtCalc(b.anschaffungskosten, 0)} € − ${fmtCalc(b.anschaffungskosten_alternativ, 0)} €`
                    : `${fmtCalc(b.anschaffungskosten, 0)} €`
                  const kostenErgebnis = `= ${fmtCalc(b.relevante_kosten, 0)} € Mehrkosten`

                  // Tooltip für Ersparnis aus detail_berechnung
                  const detail = b.detail_berechnung || {}
                  const hinweis = detail.hinweis as string | undefined

                  // Prüfen ob PV-System mit Komponenten
                  const isPVSystem = b.investition_typ === 'pv-system' && b.komponenten && b.komponenten.length > 0
                  const isExpanded = expandedSystems.has(b.investition_id)

                  // Prüfen ob PV-Modul ohne Wechselrichter-Zuordnung (Konfigurationsproblem)
                  const isOrphanPVModule = b.investition_typ === 'pv-module' &&
                    typeof hinweis === 'string' && hinweis.includes('ohne Wechselrichter')
                  // Prüfen ob Wechselrichter ohne PV-Module
                  const isEmptyWR = b.investition_typ === 'wechselrichter' &&
                    typeof hinweis === 'string' && hinweis.includes('ohne zugeordnete PV-Module')

                  const toggleExpanded = () => {
                    setExpandedSystems(prev => {
                      const next = new Set(prev)
                      if (next.has(b.investition_id)) {
                        next.delete(b.investition_id)
                      } else {
                        next.add(b.investition_id)
                      }
                      return next
                    })
                  }

                  return (
                    <>
                      <tr
                        key={b.investition_id}
                        className={`hover:bg-gray-50 dark:hover:bg-gray-800 ${isPVSystem ? 'cursor-pointer' : ''}`}
                        onClick={isPVSystem ? toggleExpanded : undefined}
                      >
                        <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">
                          <div className="flex items-center gap-2">
                            {isPVSystem && (
                              isExpanded
                                ? <ChevronDown className="h-4 w-4 text-gray-400" />
                                : <ChevronRight className="h-4 w-4 text-gray-400" />
                            )}
                            {(isOrphanPVModule || isEmptyWR) && (
                              <span title={isOrphanPVModule ? 'PV-Modul ohne Wechselrichter-Zuordnung' : 'Wechselrichter ohne PV-Module'}>
                                <AlertTriangle className="h-4 w-4 text-amber-500" />
                              </span>
                            )}
                            {b.investition_bezeichnung}
                            {isPVSystem && (
                              <span className="text-xs text-gray-400">
                                ({b.komponenten!.length} Komponenten)
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-500">
                          <span
                            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                            style={{ backgroundColor: `${TYP_COLORS[b.investition_typ] || '#6b7280'}20`, color: TYP_COLORS[b.investition_typ] || '#6b7280' }}
                          >
                            {TYP_LABELS[b.investition_typ] || b.investition_typ}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-right text-gray-900 dark:text-white">
                          <FormelTooltip
                            formel={kostenFormel}
                            berechnung={kostenBerechnung}
                            ergebnis={kostenErgebnis}
                          >
                            <span className="cursor-help border-b border-dotted border-gray-400">
                              {b.relevante_kosten.toFixed(0)} €
                            </span>
                          </FormelTooltip>
                        </td>
                        <td className="px-4 py-3 text-sm text-right text-green-600">
                          <FormelTooltip
                            formel={`Jahresersparnis ${TYP_LABELS[b.investition_typ] || b.investition_typ}`}
                            berechnung={hinweis || 'Berechnet aus Verbrauchsdaten'}
                            ergebnis={`= ${fmtCalc(b.jahres_einsparung, 0)} €/Jahr`}
                          >
                            <span className="cursor-help border-b border-dotted border-green-400">
                              {b.jahres_einsparung.toFixed(0)} €
                            </span>
                          </FormelTooltip>
                        </td>
                        <td className="px-4 py-3 text-sm text-right text-gray-900 dark:text-white">
                          <FormelTooltip
                            formel="Ersparnis ÷ Mehrkosten × 100"
                            berechnung={`${fmtCalc(b.jahres_einsparung, 0)} € ÷ ${fmtCalc(b.relevante_kosten, 0)} € × 100`}
                            ergebnis={b.roi_prozent ? `= ${b.roi_prozent.toFixed(1)}% p.a.` : 'nicht berechenbar'}
                          >
                            <span className="cursor-help border-b border-dotted border-gray-400">
                              {b.roi_prozent?.toFixed(1) || '---'}%
                            </span>
                          </FormelTooltip>
                        </td>
                        <td className="px-4 py-3 text-sm text-right text-gray-900 dark:text-white">
                          <FormelTooltip
                            formel="Mehrkosten ÷ Ersparnis"
                            berechnung={`${fmtCalc(b.relevante_kosten, 0)} € ÷ ${fmtCalc(b.jahres_einsparung, 0)} €/Jahr`}
                            ergebnis={b.amortisation_jahre ? `= ${b.amortisation_jahre.toFixed(1)} Jahre` : 'nicht berechenbar'}
                          >
                            <span className="cursor-help border-b border-dotted border-gray-400">
                              {b.amortisation_jahre?.toFixed(1) || '---'} J.
                            </span>
                          </FormelTooltip>
                        </td>
                      </tr>
                      {/* Komponenten-Zeilen für PV-Systeme */}
                      {isPVSystem && isExpanded && b.komponenten!.map((komp: ROIKomponente) => (
                        <tr
                          key={`komp-${komp.investition_id}`}
                          className="bg-gray-50 dark:bg-gray-800/50"
                        >
                          <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 pl-10">
                            <span className="flex items-center gap-2">
                              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: TYP_COLORS[komp.typ] || '#6b7280' }} />
                              {komp.bezeichnung}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500">
                            <span
                              className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                              style={{ backgroundColor: `${TYP_COLORS[komp.typ] || '#6b7280'}15`, color: TYP_COLORS[komp.typ] || '#6b7280' }}
                            >
                              {TYP_LABELS[komp.typ] || komp.typ}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-sm text-right text-gray-500">
                            {komp.relevante_kosten.toFixed(0)} €
                          </td>
                          <td className="px-4 py-2 text-sm text-right text-gray-500">
                            {komp.einsparung !== null ? (
                              <span className="text-green-500">{komp.einsparung.toFixed(0)} €</span>
                            ) : (
                              <span className="text-gray-400 italic text-xs">via Module</span>
                            )}
                          </td>
                          <td className="px-4 py-2 text-sm text-right text-gray-400" colSpan={2}>
                            {typeof komp.detail?.anteil_prozent === 'number' && (
                              <span className="text-xs">{komp.detail.anteil_prozent.toFixed(0)}% Anteil</span>
                            )}
                            {typeof komp.detail?.hinweis === 'string' && (
                              <span className="text-xs italic">{komp.detail.hinweis}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>
        )
      })()}

      {/* Investitionen-Liste */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Alle Investitionen
        </h3>
        <div className="grid gap-3">
          {Object.entries(invByTyp).map(([typ, invs]) => (
            <div key={typ} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: TYP_COLORS[typ] || '#6b7280' }}
                />
                <h4 className="font-medium text-gray-900 dark:text-white">
                  {TYP_LABELS[typ] || typ}
                </h4>
                <span className="text-sm text-gray-500">({invs.length})</span>
              </div>
              <div className="grid gap-2">
                {invs.map(inv => (
                  <div key={inv.id} className="flex justify-between items-center text-sm py-1">
                    <span className="text-gray-700 dark:text-gray-300">{inv.bezeichnung}</span>
                    <span className="text-gray-900 dark:text-white font-medium">
                      {inv.anschaffungskosten_gesamt?.toFixed(0) || '0'} €
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
