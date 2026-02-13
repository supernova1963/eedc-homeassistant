// CO2 Tab - Monatszeitreihen für CO2-Einsparungen
import { useMemo } from 'react'
import {
  BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'
import { Leaf, Download } from 'lucide-react'
import { Card, Button, fmtCalc } from '../../components/ui'
import { exportToCSV } from '../../utils/export'
import { KPICard } from './KPICard'
import { TabProps, createMonatsZeitreihe } from './types'

const CO2_FAKTOR = 0.38 // kg CO2 pro kWh (deutscher Strommix)

interface CO2TabProps {
  data: TabProps['data']
  stats: TabProps['stats']
  zeitraumLabel?: string
}

export function CO2Tab({ data, stats, zeitraumLabel }: CO2TabProps) {
  // Monatszeitreihen erstellen
  const zeitreihe = useMemo(
    () => createMonatsZeitreihe(data),
    [data]
  )

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
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
              <Tooltip
                formatter={(value: number) => [`${value.toFixed(0)} kg CO2`, 'Einsparung']}
                contentStyle={{ backgroundColor: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb' }}
              />
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
              <Tooltip
                formatter={(value: number) => [`${(value/1000).toFixed(2)} t CO2`, 'Kumuliert']}
                contentStyle={{ backgroundColor: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb' }}
              />
              <Area
                type="monotone"
                dataKey="kumuliert_co2"
                name="Kumulierte Einsparung"
                stroke="#10b981"
                fill="#10b981"
                fillOpacity={0.3}
              />
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

      {/* Info-Karte */}
      <Card>
        <h3 className="font-medium text-gray-900 dark:text-white mb-2">Berechnungsgrundlage</h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          Die CO2-Einsparung wird mit dem deutschen Strommix von <strong>{CO2_FAKTOR * 1000} g CO2/kWh</strong> berechnet.
          Jede kWh selbst erzeugter Solarstrom, die fossilen Strom ersetzt, spart entsprechend CO2 ein.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm border-t border-gray-200 dark:border-gray-700 pt-4">
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
