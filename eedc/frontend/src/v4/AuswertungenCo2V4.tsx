/**
 * AuswertungenCo2V4 — CO₂-Auswertung (A.5 Sub 2, SLICE-2-Neukonzept).
 *
 * Drei verschiebbare BlockShell-Blöcke (SPEC-AUSWERTUNGEN §0a):
 *   ① CO₂-Bilanz & Wirkung   — KPI-Strip (Einsparung + Äquivalente) + Monats-Bar + CSV
 *   ② CO₂-Amortisation        — graue Last (data-gated >0): kumul. Kurve + KPIs + Posten
 *   ③ Berechnungsgrundlage    — Methodik + Ø-Werte (default eingeklappt)
 *
 * Regel-SoT: R1 alle Zahlen via `fmtZahl`/`formatCo2` (kein `.toFixed`) · R2 CO₂-
 * Einheit zentral (`formatCo2`/`co2Achse`: kg→t ab ≥1.000, 2 NK; KEIN freies t/kg/g,
 * Auto-km ohne Tsd-Transform) · R6 KPIs + Charts parkbar. Daten = `useAuswertungBasis`
 * (Jahr-Filter) + `getCO2Amortisation`; CO₂-Faktor aus lib-SoT (kein lokales 0,38).
 */
import { useEffect, useMemo, useState } from 'react'
import {
  BarChart, Bar, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { Leaf, Sprout, Download } from 'lucide-react'
import { LoadingSpinner, Card, Button, fmtCalc } from '../components/ui'
import ChartTooltip from '../components/ui/ChartTooltip'
import { BlockShell, KpiStrip, type Block, type KpiStripItem } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar } from '../components/park'
import {
  CO2_FAKTOR_KG_KWH, CHART_COLORS, MARKER_WARNUNG, TYP_LABELS,
  formatCo2, fmtZahl, formatProzent, co2Achse, xAchse, yAchse,
} from '../lib'
import { exportToCSV } from '../utils/export'
import { investitionenApi, type CO2AmortisationResponse } from '../api/investitionen'
import { createMonatsZeitreihe } from '../pages/auswertung/types'
import { useSelectedAnlage, useSchmaleAchse } from '../hooks'
import { useAuswertungBasis } from './useAuswertungBasis'
import { AuswertungKopf } from './AuswertungKopf'

const SICHT_KEY = 'v4-auswertungen-co2'
// Anschauliche Äquivalenz-Faktoren (kg CO₂).
const KG_PRO_BAUM_JAHR = 12.5
const KG_PRO_AUTO_KM = 0.12
const KG_PRO_FLUG = 230

export default function AuswertungenCo2V4() {
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <Co2Inner />
    </ParkProvider>
  )
}

function Co2Inner() {
  const { anlagen, selectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const basis = useAuswertungBasis(selectedAnlageId)

  // Graue Last lädt asynchron → erst rendern, wenn sie gesettled ist. Sonst mountet
  // BlockShell mit nur [①③] und nimmt den später ergänzten ②-Block (data-gated)
  // nicht mehr auf (Order wird nur beim Mount initialisiert).
  const [co2Amort, setCo2Amort] = useState<CO2AmortisationResponse | null>(null)
  const [amortGeladen, setAmortGeladen] = useState(false)
  useEffect(() => {
    if (!selectedAnlageId) { setCo2Amort(null); setAmortGeladen(true); return }
    let aktiv = true
    setAmortGeladen(false)
    investitionenApi.getCO2Amortisation(selectedAnlageId)
      .then((r) => { if (aktiv) setCo2Amort(r) })
      .catch(() => { if (aktiv) setCo2Amort(null) })
      .finally(() => { if (aktiv) setAmortGeladen(true) })
    return () => { aktiv = false }
  }, [selectedAnlageId])

  const schmal = useSchmaleAchse()
  const zeitreihe = useMemo(() => createMonatsZeitreihe(basis.gefiltert), [basis.gefiltert])
  const kumuliert = useMemo(() => {
    let summe = 0
    return zeitreihe.map((z) => { summe += z.co2_einsparung; return { ...z, kumuliert_co2: summe } })
  }, [zeitreihe])

  const anzahlMonate = basis.stats.anzahlMonate
  const gesamtCo2 = basis.stats.gesamtErzeugung * CO2_FAKTOR_KG_KWH
  const graueLast = co2Amort?.graue_last_gesamt_kg ?? 0

  const klimapositiv = useMemo(() => {
    if (graueLast <= 0) return { status: 'keine' as const }
    const idx = kumuliert.findIndex((z) => z.kumuliert_co2 >= graueLast)
    if (idx >= 0) return { status: 'erreicht' as const, label: kumuliert[idx].name }
    const avgProMonat = anzahlMonate > 0 ? gesamtCo2 / anzahlMonate : 0
    const fehlend = graueLast - (kumuliert[kumuliert.length - 1]?.kumuliert_co2 ?? 0)
    const monateNoch = avgProMonat > 0 ? Math.ceil(fehlend / avgProMonat) : null
    return { status: 'prognose' as const, monateNoch }
  }, [graueLast, kumuliert, anzahlMonate, gesamtCo2])

  const handleCsv = () => {
    const headers = ['Monat', 'CO₂-Einsparung (kg)', 'Kumuliert (kg)']
    const rows = kumuliert.map((z) => [z.name, z.co2_einsparung, z.kumuliert_co2])
    exportToCSV(headers, rows, 'co2_export.csv')
  }

  const bloecke: Block[] = useMemo(() => {
    const fc = formatCo2(gesamtCo2)
    const baeume = gesamtCo2 / KG_PRO_BAUM_JAHR
    const autoKm = gesamtCo2 / KG_PRO_AUTO_KM
    const fluege = gesamtCo2 / KG_PRO_FLUG

    // ① Bilanz-KPIs (R2: CO₂ via formatCo2; Äquivalente in Basiseinheit, kein Tsd-Transform).
    const bilanzKpis: KpiStripItem[] = [
      {
        title: 'CO₂ eingespart', value: fc.wert, unit: fc.einheit, color: 'green', icon: Leaf,
        subtitle: `${anzahlMonate} Monate`, parkId: 'kpi:co2-eingespart',
        formel: 'PV-Erzeugung × CO₂-Faktor',
        berechnung: `${fmtCalc(basis.stats.gesamtErzeugung, 0)} kWh × ${fmtZahl(CO2_FAKTOR_KG_KWH * 1000, 0)} g/kWh`,
        ergebnis: `= ${formatCo2(gesamtCo2).text}`,
      },
      {
        title: 'Bäume äquivalent', value: fmtZahl(baeume, 0), unit: 'Bäume/Jahr', color: 'green', icon: Leaf,
        subtitle: 'Bindungsleistung', parkId: 'kpi:baeume',
        formel: 'CO₂-Einsparung ÷ 12,5 kg/Baum/Jahr',
        berechnung: `${fmtZahl(gesamtCo2, 0)} kg ÷ 12,5 kg`, ergebnis: `= ${fmtZahl(baeume, 0)} Bäume`,
      },
      {
        title: 'Auto-km vermieden', value: fmtZahl(autoKm, 0), unit: 'km', color: 'cyan', icon: Leaf,
        subtitle: 'bei 120 g CO₂/km', parkId: 'kpi:autokm',
        formel: 'CO₂-Einsparung ÷ 120 g/km',
        berechnung: `${fmtZahl(gesamtCo2 * 1000, 0)} g ÷ 120 g/km`, ergebnis: `= ${fmtZahl(autoKm, 0)} km`,
      },
      {
        title: 'Kurzstreckenflüge', value: fmtZahl(fluege, 1), unit: 'Flüge', color: 'cyan', icon: Leaf,
        subtitle: 'à 1000 km', parkId: 'kpi:fluege',
        formel: 'CO₂-Einsparung ÷ 230 kg/Flug',
        berechnung: `${fmtZahl(gesamtCo2, 0)} kg ÷ 230 kg`, ergebnis: `= ${fmtZahl(fluege, 1)} Flüge`,
      },
    ]

    // Achsen-Einheit je Chart (R2: ganze Achse = eine Einheit vom Max).
    const monMax = Math.max(0, ...zeitreihe.map((z) => z.co2_einsparung))
    const monAchse = co2Achse(monMax)
    const kumMax = Math.max(0, graueLast, ...kumuliert.map((z) => z.kumuliert_co2))
    const kumAchse = co2Achse(kumMax)

    const blockBilanz: Block = {
      id: 'bilanz', title: 'CO₂-Bilanz & Wirkung', icon: Leaf, farbe: 'text-green-500',
      summary: `${fc.text} eingespart`, defaultOpen: true,
      badge: (
        <Button variant="secondary" size="sm" onClick={handleCsv}>
          <Download className="h-4 w-4 mr-1" /> CSV-Export
        </Button>
      ),
      render: () => (
        <div className="space-y-4">
          <KpiStrip kpis={bilanzKpis} />
          <Parkbar id="chart:co2-monat" titel="CO₂ pro Monat">
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white mb-2">CO₂-Einsparung pro Monat</p>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={zeitreihe} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                    <XAxis dataKey="name" {...xAchse(schmal)} interval="preserveStartEnd" />
                    <YAxis tickFormatter={monAchse.tick} unit={` ${monAchse.einheit}`} {...yAchse(schmal)} />
                    <Tooltip content={<ChartTooltip formatter={(v) => `${monAchse.tick(v)} ${monAchse.einheit}`} />} />
                    <Bar dataKey="co2_einsparung" name="CO₂ eingespart" fill={CHART_COLORS.co2Pv} radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </Parkbar>
        </div>
      ),
    }

    // ② Amortisation (nur wenn graue Last erfasst).
    const amortKpis: KpiStripItem[] = graueLast > 0 ? [
      {
        title: 'Graue Herstellungs-Last', value: formatCo2(graueLast).wert, unit: formatCo2(graueLast).einheit,
        color: 'yellow', icon: Sprout, subtitle: 'einmalig bei Anschaffung', parkId: 'kpi:graue-last',
        formel: 'Σ Investitionen (Datenblatt ∨ Richtwert)', berechnung: `${fmtZahl(graueLast, 0)} kg`,
        ergebnis: `= ${formatCo2(graueLast).text}`,
      },
      {
        title: 'Bereits ausgeglichen', value: formatProzent(Math.min(100, (gesamtCo2 / graueLast) * 100)).wert, unit: '%',
        color: 'green', icon: Leaf, subtitle: `${formatCo2(gesamtCo2).text} von ${formatCo2(graueLast).text}`,
        parkId: 'kpi:ausgeglichen', formel: 'kumulierte Einsparung ÷ graue Last',
        berechnung: `${fmtZahl(gesamtCo2, 0)} kg ÷ ${fmtZahl(graueLast, 0)} kg`,
        ergebnis: `= ${formatProzent(Math.min(100, (gesamtCo2 / graueLast) * 100)).text}`,
      },
      {
        title: 'Klimapositiv', color: 'green', icon: Sprout, parkId: 'kpi:klimapositiv',
        value: klimapositiv.status === 'erreicht' ? (klimapositiv.label ?? '—')
          : klimapositiv.status === 'prognose' ? (klimapositiv.monateNoch != null ? `~${fmtZahl(klimapositiv.monateNoch, 0)}` : '—')
          : '—',
        unit: klimapositiv.status === 'prognose' && klimapositiv.monateNoch != null ? 'Monate' : '',
        subtitle: klimapositiv.status === 'erreicht' ? 'erreicht — graue Last gedeckt'
          : klimapositiv.status === 'prognose' ? 'hochgerechnet bis Deckung' : 'keine Einsparung erfasst',
      },
    ] : []

    const posten = co2Amort?.posten ?? []
    const postenMax = Math.max(0, ...posten.map((p) => p.graue_last_kg))
    const postenAchse = co2Achse(postenMax)

    const blockAmort: Block | null = graueLast > 0 ? {
      id: 'amort', title: 'CO₂-Amortisation', icon: Sprout, farbe: 'text-amber-500',
      summary: `graue Last ${formatCo2(graueLast).text}`, defaultOpen: false,
      render: () => (
        <div className="space-y-4">
          <KpiStrip kpis={amortKpis} />
          <Parkbar id="chart:co2-kumuliert" titel="Kumulierte CO₂-Einsparung">
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Kumulierte CO₂-Einsparung</p>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={kumuliert} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                    <XAxis dataKey="name" {...xAchse(schmal)} interval="preserveStartEnd" />
                    <YAxis tickFormatter={kumAchse.tick} unit={` ${kumAchse.einheit}`} {...yAchse(schmal)} />
                    <Tooltip content={<ChartTooltip formatter={(v) => `${kumAchse.tick(v)} ${kumAchse.einheit}`} />} />
                    <Area type="monotone" dataKey="kumuliert_co2" name="Kumulierte Einsparung"
                      stroke={CHART_COLORS.co2Pv} fill={CHART_COLORS.co2Pv} fillOpacity={0.3} />
                    <ReferenceLine y={graueLast} stroke={MARKER_WARNUNG.linie} strokeDasharray="6 4"
                      label={{ value: `Graue Last ${kumAchse.tick(graueLast)} ${kumAchse.einheit}`,
                        position: 'insideTopLeft', fontSize: 11, fill: MARKER_WARNUNG.text }} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </Parkbar>
          {posten.length > 0 && (
            <Parkbar id="tabelle:graue-last" titel="Graue Last je Komponente">
              <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Graue Last je Komponente</p>
                <div className="space-y-1 text-sm">
                  {posten.map((p) => (
                    <div key={`${p.investition_id}-${p.bezeichnung}`} className="flex items-center justify-between">
                      <span className="text-gray-600 dark:text-gray-400">
                        {p.bezeichnung}
                        <span className="text-gray-400 dark:text-gray-500"> · {TYP_LABELS[p.typ] ?? p.typ}</span>
                        {p.quelle === 'override' && <span className="ml-1 text-xs text-amber-600">(Datenblatt)</span>}
                        {p.quelle === 'fehlt' && <span className="ml-1 text-xs text-red-500">(Größe fehlt)</span>}
                      </span>
                      <span className="font-medium text-gray-700 dark:text-gray-300 tabular-nums">
                        {postenAchse.tick(p.graue_last_kg)} {postenAchse.einheit}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </Parkbar>
          )}
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Kumulierte Einsparung = vermiedene Netz-CO₂ der PV-Erzeugung ({fmtZahl(CO2_FAKTOR_KG_KWH * 1000, 0)} g/kWh).
            Graue Last für PV/Speicher = voller Herstellungs-Aufwand, für Wärmepumpe/E-Auto = Differenz zur Alternative.
            Richtwerte, pro Investition per Datenblatt übersteuerbar.
          </p>
        </div>
      ),
    } : null

    // ③ Berechnungsgrundlage (Methodik + Ø-Werte).
    const oProMonat = anzahlMonate > 0 ? gesamtCo2 / anzahlMonate : 0
    const blockBasis: Block = {
      id: 'basis', title: 'Berechnungsgrundlage', icon: Leaf, farbe: 'text-gray-400',
      summary: `Strommix ${fmtZahl(CO2_FAKTOR_KG_KWH * 1000, 0)} g/kWh`, defaultOpen: false,
      render: () => (
        <div className="space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Die CO₂-Einsparung rechnet mit dem deutschen Strommix von{' '}
            <strong>{fmtZahl(CO2_FAKTOR_KG_KWH * 1000, 0)} g CO₂/kWh</strong>. Jede selbst erzeugte kWh,
            die fossilen Strom ersetzt, spart entsprechend CO₂.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm border-t border-gray-200 dark:border-gray-700 pt-4">
            <div><p className="text-gray-500">Ø pro Monat</p><p className="font-medium text-green-600 dark:text-green-400">{formatCo2(oProMonat).text}</p></div>
            <div><p className="text-gray-500">Ø pro kWh</p><p className="font-medium text-green-600 dark:text-green-400">{fmtZahl(CO2_FAKTOR_KG_KWH * 1000, 0)} g</p></div>
            <div><p className="text-gray-500">Ø pro Jahr</p><p className="font-medium text-green-600 dark:text-green-400">{formatCo2(oProMonat * 12).text}</p></div>
            <div><p className="text-gray-500">Hochgerechnet 20 J.</p><p className="font-medium text-green-600 dark:text-green-400">{formatCo2(oProMonat * 12 * 20).text}</p></div>
          </div>
        </div>
      ),
    }

    return [blockBilanz, ...(blockAmort ? [blockAmort] : []), blockBasis]
  }, [zeitreihe, kumuliert, gesamtCo2, graueLast, anzahlMonate, klimapositiv, co2Amort, basis.stats.gesamtErzeugung])

  if (anlagenLoading || basis.loading || !amortGeladen) return <LoadingSpinner text="Lade CO₂-Daten…" />
  if (anlagen.length === 0) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage angelegt.</p></Card>
      </div>
    )
  }

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      <AuswertungKopf titel="CO₂-Bilanz" jahr={basis.jahr} setJahr={basis.setJahr} jahre={basis.jahre} />
      <BlockShell key={`co2-${basis.jahr}`} persistKey={SICHT_KEY} bloecke={bloecke} sortierbar />
      <ParkFuss />
    </div>
  )
}
