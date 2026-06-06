// CO2 Tab - Monatszeitreihen für CO2-Einsparungen
import { useMemo, useState, useEffect } from 'react'
import {
  BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts'
import { Leaf, Download, Sprout } from 'lucide-react'
import { Card, Button, fmtCalc } from '../../components/ui'
import ChartTooltip from '../../components/ui/ChartTooltip'
import { exportToCSV } from '../../utils/export'
import { TYP_LABELS } from '../../lib/constants'
import { investitionenApi, type CO2AmortisationResponse } from '../../api/investitionen'
import { KPICard } from './KPICard'
import { TabProps, createMonatsZeitreihe } from './types'

const CO2_FAKTOR = 0.38 // kg CO2 pro kWh (deutscher Strommix)

interface CO2TabProps {
  data: TabProps['data']
  stats: TabProps['stats']
  zeitraumLabel?: string
  anlageId?: number | null
}

export function CO2Tab({ data, stats, zeitraumLabel, anlageId }: CO2TabProps) {
  // Monatszeitreihen erstellen
  const zeitreihe = useMemo(
    () => createMonatsZeitreihe(data),
    [data]
  )

  // Graue Herstellungs-Last (#284) — Σ über die Investitionen der Anlage
  const [co2Amort, setCo2Amort] = useState<CO2AmortisationResponse | null>(null)
  useEffect(() => {
    if (!anlageId) { setCo2Amort(null); return }
    let aktiv = true
    investitionenApi.getCO2Amortisation(anlageId)
      .then(r => { if (aktiv) setCo2Amort(r) })
      .catch(() => { if (aktiv) setCo2Amort(null) })
    return () => { aktiv = false }
  }, [anlageId])

  const graueLast = co2Amort?.graue_last_gesamt_kg ?? 0

  // Kumulierte CO2-Einsparung
  const chartDataWithKumuliert = useMemo(() => {
    let kumuliert = 0
    return zeitreihe.map(z => {
      kumuliert += z.co2_einsparung
      return {
        ...z,
        kumuliert_co2: kumuliert
      }
    })
  }, [zeitreihe])

  // Schnittpunkt „ab wann klimapositiv": erster Monat, in dem die kumulierte
  // Betriebs-Einsparung die graue Herstellungs-Last übersteigt. Ist sie im
  // Zeitraum noch nicht erreicht, wird linear über den Ø-Monatswert hochgerechnet.
  const klimapositiv = useMemo(() => {
    if (graueLast <= 0) return { status: 'keine' as const }
    const idx = chartDataWithKumuliert.findIndex(z => z.kumuliert_co2 >= graueLast)
    if (idx >= 0) {
      return { status: 'erreicht' as const, label: chartDataWithKumuliert[idx].name }
    }
    const letzte = chartDataWithKumuliert[chartDataWithKumuliert.length - 1]
    const avgPerMonth = stats.anzahlMonate > 0
      ? (stats.gesamtErzeugung * CO2_FAKTOR) / stats.anzahlMonate
      : 0
    const fehlend = graueLast - (letzte?.kumuliert_co2 ?? 0)
    const monateNoch = avgPerMonth > 0 ? Math.ceil(fehlend / avgPerMonth) : null
    return { status: 'prognose' as const, monateNoch }
  }, [graueLast, chartDataWithKumuliert, stats.anzahlMonate, stats.gesamtErzeugung])

  // Gesamt-Werte
  const gesamtCO2 = stats.gesamtErzeugung * CO2_FAKTOR
  const baeume = gesamtCO2 / 12.5 // Ein Baum bindet ca. 12.5 kg CO2/Jahr
  const autoKm = gesamtCO2 / 0.12 // ca. 120g CO2/km
  const fluege = gesamtCO2 / 230 // ca. 230 kg CO2 pro 1000 km Flug

  // CSV Export
  const handleExportCSV = () => {
    const headers = ['Monat', 'CO2-Einsparung (kg)', 'Kumuliert (kg)', 'Kumuliert (t)']
    const rows = chartDataWithKumuliert.map(z => [
      z.name, z.co2_einsparung, z.kumuliert_co2, z.kumuliert_co2 / 1000
    ])
    exportToCSV(headers, rows, `co2_export.csv`)
  }

  return (
    <div className="space-y-6">
      {/* Header mit Zeitraum und Export */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          <span className="font-medium text-gray-700 dark:text-gray-300">{zeitraumLabel}</span>
          {' '}&bull;{' '}{stats.anzahlMonate} Monate
        </p>
        <Button variant="secondary" size="sm" onClick={handleExportCSV}>
          <Download className="h-4 w-4 mr-2" />
          CSV Export
        </Button>
      </div>

      {/* CO2 KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        <KPICard
          title="CO2 eingespart"
          value={(gesamtCO2 / 1000).toFixed(2)}
          unit="t"
          subtitle={`${stats.anzahlMonate} Monate`}
          icon={Leaf}
          color="text-green-500"
          bgColor="bg-green-50 dark:bg-green-900/20"
          formel="PV-Erzeugung × CO2-Faktor"
          berechnung={`${fmtCalc(stats.gesamtErzeugung, 0)} kWh × ${CO2_FAKTOR * 1000} g/kWh`}
          ergebnis={`= ${fmtCalc(gesamtCO2, 0)} kg = ${fmtCalc(gesamtCO2 / 1000, 2)} t`}
        />
        <KPICard
          title="Bäume äquivalent"
          value={baeume.toFixed(0)}
          unit="Bäume/Jahr"
          subtitle="Bindungsleistung"
          icon={Leaf}
          color="text-emerald-500"
          bgColor="bg-emerald-50 dark:bg-emerald-900/20"
          formel="CO2-Einsparung ÷ 12,5 kg/Baum/Jahr"
          berechnung={`${fmtCalc(gesamtCO2, 0)} kg ÷ 12,5 kg/Baum`}
          ergebnis={`= ${fmtCalc(baeume, 0)} Bäume`}
        />
        <KPICard
          title="Auto-km vermieden"
          value={(autoKm / 1000).toFixed(0)}
          unit="Tsd. km"
          subtitle="bei 120g CO2/km"
          icon={Leaf}
          color="text-teal-500"
          bgColor="bg-teal-50 dark:bg-teal-900/20"
          formel="CO2-Einsparung ÷ 120 g/km"
          berechnung={`${fmtCalc(gesamtCO2 * 1000, 0)} g ÷ 120 g/km`}
          ergebnis={`= ${fmtCalc(autoKm, 0)} km`}
        />
        <KPICard
          title="Kurzstreckenflüge"
          value={fluege.toFixed(1)}
          unit="Flüge"
          subtitle="à 1000 km"
          icon={Leaf}
          color="text-cyan-500"
          bgColor="bg-cyan-50 dark:bg-cyan-900/20"
          formel="CO2-Einsparung ÷ 230 kg/Flug"
          berechnung={`${fmtCalc(gesamtCO2, 0)} kg ÷ 230 kg/Flug`}
          ergebnis={`= ${fmtCalc(fluege, 1)} Flüge vermieden`}
        />
      </div>

      {/* Chart 1: CO2-Einsparung pro Monat */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Leaf className="h-5 w-5 text-green-500" />
          CO2-Einsparung pro Monat
        </h3>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={zeitreihe} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis unit=" kg" tick={{ fontSize: 11 }} />
              <Tooltip content={<ChartTooltip unit="kg CO2" decimals={0} />} />
              <Bar dataKey="co2_einsparung" name="CO2 eingespart" fill="#10b981" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Chart 2: Kumulierte CO2-Einsparung */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Kumulierte CO2-Einsparung
        </h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartDataWithKumuliert} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis tickFormatter={(v) => `${(v/1000).toFixed(1)}`} unit=" t" tick={{ fontSize: 11 }} />
              <Tooltip content={<ChartTooltip formatter={(value) => `${(value / 1000).toFixed(2)} t CO2`} />} />
              <Area
                type="monotone"
                dataKey="kumuliert_co2"
                name="Kumulierte Einsparung"
                stroke="#10b981"
                fill="#10b981"
                fillOpacity={0.3}
              />
              {graueLast > 0 && (
                <ReferenceLine
                  y={graueLast}
                  stroke="#f59e0b"
                  strokeDasharray="6 4"
                  label={{
                    value: `Graue Last ${(graueLast / 1000).toFixed(1)} t`,
                    position: 'insideTopLeft',
                    fontSize: 11,
                    fill: '#b45309',
                  }}
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 flex items-center justify-center gap-4 text-sm">
          <span className="text-gray-500">Gesamt nach {stats.anzahlMonate} Monaten:</span>
          <span className="text-lg font-bold text-emerald-600">
            {(gesamtCO2 / 1000).toFixed(2)} t CO2
          </span>
        </div>
      </Card>

      {/* CO2-Amortisation (#284): Schnittpunkt graue Last × Betriebs-Einsparung */}
      {graueLast > 0 && (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <Sprout className="h-5 w-5 text-amber-500" />
            CO2-Amortisation
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4">
            <KPICard
              title="Graue Herstellungs-Last"
              value={(graueLast / 1000).toFixed(2)}
              unit="t CO2"
              subtitle="einmalig bei Anschaffung"
              icon={Sprout}
              color="text-amber-600"
              bgColor="bg-amber-50 dark:bg-amber-900/20"
              formel="Σ Investitionen (Override ∨ Richtwert)"
              berechnung={`${fmtCalc(graueLast, 0)} kg CO2`}
              ergebnis={`= ${fmtCalc(graueLast / 1000, 2)} t`}
            />
            <KPICard
              title="Bereits ausgeglichen"
              value={Math.min(100, (gesamtCO2 / graueLast) * 100).toFixed(0)}
              unit="%"
              subtitle={`${(gesamtCO2 / 1000).toFixed(1)} t von ${(graueLast / 1000).toFixed(1)} t`}
              icon={Leaf}
              color="text-green-600"
              bgColor="bg-green-50 dark:bg-green-900/20"
              formel="kumulierte Einsparung ÷ graue Last"
              berechnung={`${fmtCalc(gesamtCO2, 0)} kg ÷ ${fmtCalc(graueLast, 0)} kg`}
              ergebnis={`= ${fmtCalc(Math.min(100, (gesamtCO2 / graueLast) * 100), 0)} %`}
            />
            <KPICard
              title="Klimapositiv"
              value={
                klimapositiv.status === 'erreicht'
                  ? (klimapositiv.label ?? '—')
                  : klimapositiv.status === 'prognose'
                    ? (klimapositiv.monateNoch != null ? `~${klimapositiv.monateNoch}` : '—')
                    : '—'
              }
              unit={klimapositiv.status === 'prognose' && klimapositiv.monateNoch != null ? 'Monate' : ''}
              subtitle={
                klimapositiv.status === 'erreicht'
                  ? 'erreicht — graue Last gedeckt'
                  : klimapositiv.status === 'prognose'
                    ? 'hochgerechnet bis Deckung'
                    : 'keine Einsparung erfasst'
              }
              icon={Sprout}
              color="text-emerald-600"
              bgColor="bg-emerald-50 dark:bg-emerald-900/20"
            />
          </div>

          {/* Aufschlüsselung der grauen Last je Investition */}
          {co2Amort && co2Amort.posten.length > 0 && (
            <div className="mt-4 border-t border-gray-200 dark:border-gray-700 pt-4">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Graue Last je Komponente</p>
              <div className="space-y-1 text-sm">
                {co2Amort.posten.map((p) => (
                  <div key={`${p.investition_id}-${p.bezeichnung}`} className="flex items-center justify-between">
                    <span className="text-gray-600 dark:text-gray-400">
                      {p.bezeichnung}
                      <span className="text-gray-400 dark:text-gray-500"> · {TYP_LABELS[p.typ] ?? p.typ}</span>
                      {p.quelle === 'override' && <span className="ml-1 text-xs text-amber-600">(Datenblatt)</span>}
                      {p.quelle === 'fehlt' && <span className="ml-1 text-xs text-red-500">(Größe fehlt)</span>}
                    </span>
                    <span className="font-medium text-gray-700 dark:text-gray-300">{fmtCalc(p.graue_last_kg, 0)} kg</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="mt-4 text-xs text-gray-500 dark:text-gray-400">
            Die kumulierte Einsparung oben basiert auf der vermiedenen Netz-CO2 der PV-Stromerzeugung
            ({CO2_FAKTOR * 1000} g/kWh). Graue Last für PV/Speicher = voller Herstellungs-Aufwand,
            für Wärmepumpe/E-Auto = Differenz zur Alternative (Gas/Öl bzw. Verbrenner). Richtwerte,
            pro Investition per Datenblatt-Wert übersteuerbar.
          </p>
        </Card>
      )}

      {/* Info-Karte */}
      <Card>
        <h3 className="font-medium text-gray-900 dark:text-white mb-2">Berechnungsgrundlage</h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          Die CO2-Einsparung wird mit dem deutschen Strommix von <strong>{CO2_FAKTOR * 1000} g CO2/kWh</strong> berechnet.
          Jede kWh selbst erzeugter Solarstrom, die fossilen Strom ersetzt, spart entsprechend CO2 ein.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 text-sm border-t border-gray-200 dark:border-gray-700 pt-4">
          <div>
            <p className="text-gray-500">Ø pro Monat</p>
            <p className="font-medium text-green-600">{(gesamtCO2 / stats.anzahlMonate).toFixed(0)} kg</p>
          </div>
          <div>
            <p className="text-gray-500">Ø pro kWh</p>
            <p className="font-medium text-green-600">{(CO2_FAKTOR * 1000).toFixed(0)} g</p>
          </div>
          <div>
            <p className="text-gray-500">Ø pro Jahr</p>
            <p className="font-medium text-green-600">{((gesamtCO2 / stats.anzahlMonate) * 12 / 1000).toFixed(2)} t</p>
          </div>
          <div>
            <p className="text-gray-500">Hochgerechnet 20 Jahre</p>
            <p className="font-medium text-green-600">{((gesamtCO2 / stats.anzahlMonate) * 12 * 20 / 1000).toFixed(1)} t</p>
          </div>
        </div>
      </Card>
    </div>
  )
}
