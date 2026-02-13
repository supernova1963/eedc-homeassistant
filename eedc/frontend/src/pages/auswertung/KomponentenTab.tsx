// Komponenten Tab - Speicher, Wärmepumpe, E-Mobilität, Balkonkraftwerk, Sonstiges
import { useMemo, useEffect, useState } from 'react'
import {
  Bar, ComposedChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import { Battery, Flame, Car, Download, AlertCircle, Sun, Zap, RefreshCw } from 'lucide-react'
import { Card, Button, fmtCalc } from '../../components/ui'
import { exportToCSV } from '../../utils/export'
import { KPICard } from './KPICard'
import { TabProps, CHART_COLORS, monatNamen } from './types'
import { cockpitApi, KomponentenZeitreihe } from '../../api/cockpit'

interface KomponentenTabProps extends Pick<TabProps, 'anlage' | 'strompreis' | 'zeitraumLabel'> {
  selectedYear?: number | 'all' | null
}

export function KomponentenTab({ anlage, strompreis, selectedYear, zeitraumLabel }: KomponentenTabProps) {
  const [komponenten, setKomponenten] = useState<KomponentenZeitreihe | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Lade Komponenten-Zeitreihe vom Backend (mit Jahr-Filter)
  useEffect(() => {
    if (!anlage?.id) return

    const loadData = async () => {
      setLoading(true)
      setError(null)
      try {
        // Jahr übergeben: null/undefined/'all' = alle Jahre, sonst spezifisches Jahr
        const jahrParam = (selectedYear && selectedYear !== 'all') ? selectedYear : undefined
        const result = await cockpitApi.getKomponentenZeitreihe(anlage.id, jahrParam)
        setKomponenten(result)
      } catch (err) {
        setError('Fehler beim Laden der Komponentendaten')
        console.error(err)
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [anlage?.id, selectedYear])

  // Chart-Daten mit Namen für X-Achse
  const chartData = useMemo(() => {
    if (!komponenten?.monatswerte) return []
    return komponenten.monatswerte.map(m => ({
      ...m,
      name: `${monatNamen[m.monat]} ${m.jahr.toString().slice(-2)}`
    }))
  }, [komponenten])

  // Aggregierte Werte berechnen
  const speicherSummen = useMemo(() => {
    if (!chartData.length) return { ladung: 0, entladung: 0, effizienz: null, arbitrage: 0 }
    const ladung = chartData.reduce((sum, z) => sum + z.speicher_ladung_kwh, 0)
    const entladung = chartData.reduce((sum, z) => sum + z.speicher_entladung_kwh, 0)
    const arbitrage = chartData.reduce((sum, z) => sum + z.speicher_arbitrage_kwh, 0)
    return {
      ladung,
      entladung,
      effizienz: ladung > 0 ? (entladung / ladung) * 100 : null,
      arbitrage
    }
  }, [chartData])

  const wpSummen = useMemo(() => {
    if (!chartData.length) return { waerme: 0, strom: 0, cop: null, heizung: 0, warmwasser: 0 }
    const waerme = chartData.reduce((sum, z) => sum + z.wp_waerme_kwh, 0)
    const strom = chartData.reduce((sum, z) => sum + z.wp_strom_kwh, 0)
    const heizung = chartData.reduce((sum, z) => sum + z.wp_heizung_kwh, 0)
    const warmwasser = chartData.reduce((sum, z) => sum + z.wp_warmwasser_kwh, 0)
    return {
      waerme,
      strom,
      cop: strom > 0 ? waerme / strom : null,
      heizung,
      warmwasser
    }
  }, [chartData])

  const emobSummen = useMemo(() => {
    if (!chartData.length) return {
      km: 0, ladung: 0, pvAnteil: null,
      pvLadung: 0, netzLadung: 0, externLadung: 0, externEuro: 0, v2h: 0
    }
    const km = chartData.reduce((sum, z) => sum + z.emob_km, 0)
    const ladung = chartData.reduce((sum, z) => sum + z.emob_ladung_kwh, 0)
    const pvLadung = chartData.reduce((sum, z) => sum + z.emob_ladung_pv_kwh, 0)
    const netzLadung = chartData.reduce((sum, z) => sum + z.emob_ladung_netz_kwh, 0)
    const externLadung = chartData.reduce((sum, z) => sum + z.emob_ladung_extern_kwh, 0)
    const externEuro = chartData.reduce((sum, z) => sum + z.emob_ladung_extern_euro, 0)
    const v2h = chartData.reduce((sum, z) => sum + z.emob_v2h_kwh, 0)
    const pvAnteil = ladung > 0 ? (pvLadung / ladung) * 100 : null
    return { km, ladung, pvAnteil, pvLadung, netzLadung, externLadung, externEuro, v2h }
  }, [chartData])

  const bkwSummen = useMemo(() => {
    if (!chartData.length) return { erzeugung: 0, eigenverbrauch: 0, speicherLadung: 0, speicherEntladung: 0 }
    return {
      erzeugung: chartData.reduce((sum, z) => sum + z.bkw_erzeugung_kwh, 0),
      eigenverbrauch: chartData.reduce((sum, z) => sum + z.bkw_eigenverbrauch_kwh, 0),
      speicherLadung: chartData.reduce((sum, z) => sum + z.bkw_speicher_ladung_kwh, 0),
      speicherEntladung: chartData.reduce((sum, z) => sum + z.bkw_speicher_entladung_kwh, 0)
    }
  }, [chartData])

  const sonstigesSummen = useMemo(() => {
    if (!chartData.length) return { erzeugung: 0, verbrauch: 0 }
    return {
      erzeugung: chartData.reduce((sum, z) => sum + z.sonstiges_erzeugung_kwh, 0),
      verbrauch: chartData.reduce((sum, z) => sum + z.sonstiges_verbrauch_kwh, 0)
    }
  }, [chartData])

  // Sonderkosten - für zukünftige Nutzung in Finanzen-Tab vorbereitet
  const _sonderkostenGesamt = useMemo(() => {
    if (!chartData.length) return 0
    return chartData.reduce((sum, z) => sum + z.sonderkosten_euro, 0)
  }, [chartData])
  void _sonderkostenGesamt // Prepared for Finanzen-Tab integration

  // CSV Export
  const handleExportCSV = () => {
    if (!chartData.length) return

    const headers = ['Monat']
    if (komponenten?.hat_speicher) headers.push('Speicher Ladung (kWh)', 'Speicher Entladung (kWh)', 'Speicher Effizienz (%)')
    if (komponenten?.hat_waermepumpe) headers.push('WP Wärme (kWh)', 'WP Strom (kWh)', 'WP COP')
    if (komponenten?.hat_emobilitaet) headers.push('E-Auto km', 'E-Auto Ladung (kWh)', 'E-Auto PV-Anteil (%)')
    if (komponenten?.hat_balkonkraftwerk) headers.push('BKW Erzeugung (kWh)', 'BKW Eigenverbrauch (kWh)')
    if (komponenten?.hat_sonstiges) headers.push('Sonstiges Erzeugung (kWh)', 'Sonstiges Verbrauch (kWh)')

    const rows = chartData.map(z => {
      const row: (string | number)[] = [z.name]
      if (komponenten?.hat_speicher) row.push(z.speicher_ladung_kwh, z.speicher_entladung_kwh, z.speicher_effizienz_prozent ?? '')
      if (komponenten?.hat_waermepumpe) row.push(z.wp_waerme_kwh, z.wp_strom_kwh, z.wp_cop ?? '')
      if (komponenten?.hat_emobilitaet) row.push(z.emob_km, z.emob_ladung_kwh, z.emob_pv_anteil_prozent ?? '')
      if (komponenten?.hat_balkonkraftwerk) row.push(z.bkw_erzeugung_kwh, z.bkw_eigenverbrauch_kwh)
      if (komponenten?.hat_sonstiges) row.push(z.sonstiges_erzeugung_kwh, z.sonstiges_verbrauch_kwh)
      return row
    })
    exportToCSV(headers, rows, `komponenten_${anlage?.anlagenname || 'export'}.csv`)
  }

  // Loading State
  if (loading) {
    return (
      <Card className="text-center py-12">
        <RefreshCw className="h-12 w-12 mx-auto text-gray-400 mb-4 animate-spin" />
        <p className="text-gray-500 dark:text-gray-400">Lade Komponentendaten...</p>
      </Card>
    )
  }

  // Error State
  if (error) {
    return (
      <Card className="text-center py-12">
        <AlertCircle className="h-12 w-12 mx-auto text-red-400 mb-4" />
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">Fehler</h3>
        <p className="text-gray-500 dark:text-gray-400">{error}</p>
      </Card>
    )
  }

  // Keine Daten vorhanden
  const hatKomponenten = komponenten && (
    komponenten.hat_speicher ||
    komponenten.hat_waermepumpe ||
    komponenten.hat_emobilitaet ||
    komponenten.hat_balkonkraftwerk ||
    komponenten.hat_sonstiges
  )

  if (!hatKomponenten) {
    return (
      <Card className="text-center py-12">
        <AlertCircle className="h-12 w-12 mx-auto text-gray-400 mb-4" />
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Keine Komponentendaten vorhanden
        </h3>
        <p className="text-gray-500 dark:text-gray-400 max-w-md mx-auto">
          Erfasse Daten für Speicher, Wärmepumpe, E-Auto, Balkonkraftwerk oder Sonstiges
          unter <strong>Einstellungen → Investitionen</strong> und füge Monatsdaten hinzu.
        </p>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header mit Zeitraum und Export */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          <span className="font-medium text-gray-700 dark:text-gray-300">{zeitraumLabel}</span>
          {' '}&bull;{' '}{komponenten?.anzahl_monate || 0} Monate
        </p>
        <Button variant="secondary" size="sm" onClick={handleExportCSV}>
          <Download className="h-4 w-4 mr-2" />
          CSV Export
        </Button>
      </div>

      {/* ========== SPEICHER ========== */}
      {komponenten?.hat_speicher && speicherSummen.ladung > 0 && (
        <>
          <div className="border-b border-gray-200 dark:border-gray-700 pb-2">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <Battery className="h-6 w-6 text-green-500" />
              Speicher
              {komponenten.hat_arbitrage && (
                <span className="text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 px-2 py-0.5 rounded">
                  Arbitrage
                </span>
              )}
            </h2>
          </div>

          {/* Speicher KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KPICard
              title="Ladung gesamt"
              value={(speicherSummen.ladung / 1000).toFixed(2)}
              unit="MWh"
              icon={Battery}
              color="text-green-500"
              bgColor="bg-green-50 dark:bg-green-900/20"
              formel="Σ Speicher-Ladung aller Monate"
              berechnung={`${fmtCalc(speicherSummen.ladung, 0)} kWh`}
              ergebnis={`= ${fmtCalc(speicherSummen.ladung / 1000, 2)} MWh`}
            />
            <KPICard
              title="Entladung gesamt"
              value={(speicherSummen.entladung / 1000).toFixed(2)}
              unit="MWh"
              icon={Battery}
              color="text-blue-500"
              bgColor="bg-blue-50 dark:bg-blue-900/20"
              formel="Σ Speicher-Entladung aller Monate"
              berechnung={`${fmtCalc(speicherSummen.entladung, 0)} kWh`}
              ergebnis={`= ${fmtCalc(speicherSummen.entladung / 1000, 2)} MWh`}
            />
            <KPICard
              title="Ø Effizienz"
              value={speicherSummen.effizienz?.toFixed(1) || '---'}
              unit="%"
              icon={Battery}
              color="text-cyan-500"
              bgColor="bg-cyan-50 dark:bg-cyan-900/20"
              formel="Entladung ÷ Ladung × 100"
              berechnung={`${fmtCalc(speicherSummen.entladung, 0)} kWh ÷ ${fmtCalc(speicherSummen.ladung, 0)} kWh × 100`}
              ergebnis={speicherSummen.effizienz ? `= ${fmtCalc(speicherSummen.effizienz, 1)}%` : '---'}
            />
            {komponenten.hat_arbitrage && speicherSummen.arbitrage > 0 ? (
              <KPICard
                title="Arbitrage"
                value={speicherSummen.arbitrage.toFixed(0)}
                unit="kWh"
                subtitle="Netzladung"
                icon={Battery}
                color="text-purple-500"
                bgColor="bg-purple-50 dark:bg-purple-900/20"
                formel="Σ Netzladung für Arbitrage"
              />
            ) : (
              <KPICard
                title="Verlust"
                value={(speicherSummen.ladung - speicherSummen.entladung).toFixed(0)}
                unit="kWh"
                subtitle={speicherSummen.effizienz ? `${(100 - speicherSummen.effizienz).toFixed(1)}%` : undefined}
                icon={Battery}
                color="text-gray-500"
                bgColor="bg-gray-50 dark:bg-gray-900/20"
              />
            )}
          </div>

          {/* Speicher Chart */}
          <Card>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Speicher pro Monat
            </h3>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData.filter(z => z.speicher_ladung_kwh > 0 || z.speicher_entladung_kwh > 0)} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis yAxisId="left" tickFormatter={(v) => `${v.toFixed(0)}`} unit=" kWh" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="right" orientation="right" domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(value: number, name: string) => {
                      if (name.includes('Effizienz')) return [`${value?.toFixed(1) || '---'}%`, name]
                      return [`${value.toFixed(0)} kWh`, name]
                    }}
                    contentStyle={{ backgroundColor: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb' }}
                  />
                  <Legend />
                  <Bar yAxisId="left" dataKey="speicher_ladung_kwh" name="Ladung" fill={CHART_COLORS.speicherLadung} />
                  <Bar yAxisId="left" dataKey="speicher_entladung_kwh" name="Entladung" fill={CHART_COLORS.speicherEntladung} />
                  {komponenten.hat_arbitrage && (
                    <Bar yAxisId="left" dataKey="speicher_arbitrage_kwh" name="Arbitrage (Netz)" fill="#8b5cf6" />
                  )}
                  <Line yAxisId="right" type="monotone" dataKey="speicher_effizienz_prozent" name="Effizienz (%)" stroke={CHART_COLORS.speicherEffizienz} strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </>
      )}

      {/* ========== WÄRMEPUMPE ========== */}
      {komponenten?.hat_waermepumpe && wpSummen.strom > 0 && (
        <>
          <div className="border-b border-gray-200 dark:border-gray-700 pb-2 mt-8">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <Flame className="h-6 w-6 text-red-500" />
              Wärmepumpe
            </h2>
          </div>

          {/* WP KPIs - Erste Zeile */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KPICard
              title="Wärme erzeugt"
              value={(wpSummen.waerme / 1000).toFixed(2)}
              unit="MWh"
              icon={Flame}
              color="text-red-500"
              bgColor="bg-red-50 dark:bg-red-900/20"
              formel="Σ Wärme aller Monate"
              berechnung={`${fmtCalc(wpSummen.waerme, 0)} kWh`}
              ergebnis={`= ${fmtCalc(wpSummen.waerme / 1000, 2)} MWh`}
            />
            <KPICard
              title="Strom verbraucht"
              value={(wpSummen.strom / 1000).toFixed(2)}
              unit="MWh"
              icon={Flame}
              color="text-purple-500"
              bgColor="bg-purple-50 dark:bg-purple-900/20"
              formel="Σ WP-Strom aller Monate"
              berechnung={`${fmtCalc(wpSummen.strom, 0)} kWh`}
              ergebnis={`= ${fmtCalc(wpSummen.strom / 1000, 2)} MWh`}
            />
            <KPICard
              title="Ø COP"
              value={wpSummen.cop?.toFixed(2) || '---'}
              unit=""
              subtitle="Jahresarbeitszahl"
              icon={Flame}
              color="text-orange-500"
              bgColor="bg-orange-50 dark:bg-orange-900/20"
              formel="Wärme ÷ Strom"
              berechnung={`${fmtCalc(wpSummen.waerme, 0)} kWh ÷ ${fmtCalc(wpSummen.strom, 0)} kWh`}
              ergebnis={wpSummen.cop ? `= ${fmtCalc(wpSummen.cop, 2)} COP` : '---'}
            />
            <KPICard
              title="Ersparnis vs. Gas"
              value={strompreis ? ((wpSummen.waerme * 0.08) - (wpSummen.strom * strompreis.netzbezug_arbeitspreis_cent_kwh / 100)).toFixed(0) : '---'}
              unit="€"
              subtitle="ca. 8 ct/kWh Gas"
              icon={Flame}
              color="text-green-500"
              bgColor="bg-green-50 dark:bg-green-900/20"
            />
          </div>

          {/* WP KPIs - Zweite Zeile: Heizung vs. Warmwasser (nur wenn beide > 0) */}
          {(wpSummen.heizung > 0 || wpSummen.warmwasser > 0) && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <KPICard
                title="Heizung"
                value={(wpSummen.heizung / 1000).toFixed(2)}
                unit="MWh"
                subtitle={wpSummen.waerme > 0 ? `${((wpSummen.heizung / wpSummen.waerme) * 100).toFixed(0)}% der Wärme` : undefined}
                icon={Flame}
                color="text-red-400"
                bgColor="bg-red-50 dark:bg-red-900/20"
                formel="Σ Heizenergie aller Monate"
              />
              <KPICard
                title="Warmwasser"
                value={(wpSummen.warmwasser / 1000).toFixed(2)}
                unit="MWh"
                subtitle={wpSummen.waerme > 0 ? `${((wpSummen.warmwasser / wpSummen.waerme) * 100).toFixed(0)}% der Wärme` : undefined}
                icon={Flame}
                color="text-blue-500"
                bgColor="bg-blue-50 dark:bg-blue-900/20"
                formel="Σ Warmwasser-Energie aller Monate"
              />
            </div>
          )}

          {/* WP Chart */}
          <Card>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Wärmepumpe pro Monat
            </h3>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData.filter(z => z.wp_waerme_kwh > 0 || z.wp_strom_kwh > 0)} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis yAxisId="left" tickFormatter={(v) => `${v.toFixed(0)}`} unit=" kWh" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="right" orientation="right" domain={[0, 'auto']} tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(value: number, name: string) => {
                      if (name === 'COP') return [`${value?.toFixed(2) || '---'}`, name]
                      return [`${value.toFixed(0)} kWh`, name]
                    }}
                    contentStyle={{ backgroundColor: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb' }}
                  />
                  <Legend />
                  {(wpSummen.heizung > 0 || wpSummen.warmwasser > 0) ? (
                    <>
                      <Bar yAxisId="left" dataKey="wp_heizung_kwh" name="Heizung" stackId="waerme" fill="#f87171" />
                      <Bar yAxisId="left" dataKey="wp_warmwasser_kwh" name="Warmwasser" stackId="waerme" fill="#60a5fa" />
                    </>
                  ) : (
                    <Bar yAxisId="left" dataKey="wp_waerme_kwh" name="Wärme" fill={CHART_COLORS.wpWaerme} />
                  )}
                  <Bar yAxisId="left" dataKey="wp_strom_kwh" name="Strom" fill={CHART_COLORS.wpStrom} />
                  <Line yAxisId="right" type="monotone" dataKey="wp_cop" name="COP" stroke={CHART_COLORS.wpCop} strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </>
      )}

      {/* ========== E-MOBILITÄT ========== */}
      {komponenten?.hat_emobilitaet && emobSummen.ladung > 0 && (
        <>
          <div className="border-b border-gray-200 dark:border-gray-700 pb-2 mt-8">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <Car className="h-6 w-6 text-purple-500" />
              E-Mobilität
              {komponenten.hat_v2h && (
                <span className="text-xs bg-cyan-100 dark:bg-cyan-900/30 text-cyan-700 dark:text-cyan-300 px-2 py-0.5 rounded">
                  V2H
                </span>
              )}
            </h2>
          </div>

          {/* E-Auto KPIs - Erste Zeile */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KPICard
              title="Gefahrene km"
              value={(emobSummen.km / 1000).toFixed(1)}
              unit="Tkm"
              icon={Car}
              color="text-purple-500"
              bgColor="bg-purple-50 dark:bg-purple-900/20"
              formel="Σ gefahrene km aller Monate"
              berechnung={`${fmtCalc(emobSummen.km, 0)} km`}
              ergebnis={`= ${fmtCalc(emobSummen.km / 1000, 1)} Tausend km`}
            />
            <KPICard
              title="Ladung gesamt"
              value={(emobSummen.ladung / 1000).toFixed(2)}
              unit="MWh"
              icon={Car}
              color="text-blue-500"
              bgColor="bg-blue-50 dark:bg-blue-900/20"
              formel="Σ E-Auto-Ladung aller Monate"
              berechnung={`${fmtCalc(emobSummen.ladung, 0)} kWh`}
              ergebnis={`= ${fmtCalc(emobSummen.ladung / 1000, 2)} MWh`}
            />
            <KPICard
              title="Ø PV-Anteil"
              value={emobSummen.pvAnteil?.toFixed(0) || '---'}
              unit="%"
              icon={Car}
              color="text-green-500"
              bgColor="bg-green-50 dark:bg-green-900/20"
              formel="PV-Ladung ÷ Gesamtladung × 100"
              berechnung={`${fmtCalc(emobSummen.pvLadung, 0)} kWh ÷ ${fmtCalc(emobSummen.ladung, 0)} kWh × 100`}
              ergebnis={emobSummen.pvAnteil ? `= ${fmtCalc(emobSummen.pvAnteil, 0)}%` : '---'}
            />
            <KPICard
              title="Verbrauch"
              value={emobSummen.km > 0 ? (emobSummen.ladung / emobSummen.km * 100).toFixed(1) : '---'}
              unit="kWh/100km"
              icon={Car}
              color="text-amber-500"
              bgColor="bg-amber-50 dark:bg-amber-900/20"
              formel="Ladung ÷ km × 100"
              berechnung={`${fmtCalc(emobSummen.ladung, 0)} kWh ÷ ${fmtCalc(emobSummen.km, 0)} km × 100`}
              ergebnis={emobSummen.km > 0 ? `= ${fmtCalc(emobSummen.ladung / emobSummen.km * 100, 1)} kWh/100km` : '---'}
            />
          </div>

          {/* E-Auto KPIs - Zweite Zeile: Ladequellen + V2H */}
          {(emobSummen.pvLadung > 0 || emobSummen.netzLadung > 0 || emobSummen.externLadung > 0 || emobSummen.v2h > 0) && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <KPICard
                title="PV-Ladung"
                value={emobSummen.pvLadung.toFixed(0)}
                unit="kWh"
                subtitle={emobSummen.ladung > 0 ? `${((emobSummen.pvLadung / emobSummen.ladung) * 100).toFixed(0)}% der Ladung` : undefined}
                icon={Sun}
                color="text-yellow-500"
                bgColor="bg-yellow-50 dark:bg-yellow-900/20"
                formel="Σ Ladung aus eigener PV"
              />
              <KPICard
                title="Netz-Ladung"
                value={emobSummen.netzLadung.toFixed(0)}
                unit="kWh"
                subtitle={emobSummen.ladung > 0 ? `${((emobSummen.netzLadung / emobSummen.ladung) * 100).toFixed(0)}% der Ladung` : undefined}
                icon={Zap}
                color="text-red-500"
                bgColor="bg-red-50 dark:bg-red-900/20"
                formel="Σ Ladung aus Netzstrom"
              />
              {emobSummen.externLadung > 0 && (
                <KPICard
                  title="Extern geladen"
                  value={emobSummen.externLadung.toFixed(0)}
                  unit="kWh"
                  subtitle={emobSummen.externEuro > 0 ? `${fmtCalc(emobSummen.externEuro, 2)} €` : undefined}
                  icon={Car}
                  color="text-orange-500"
                  bgColor="bg-orange-50 dark:bg-orange-900/20"
                  formel="Σ Ladung an öffentlichen Säulen"
                />
              )}
              {komponenten.hat_v2h && emobSummen.v2h > 0 && (
                <KPICard
                  title="V2H Entladung"
                  value={emobSummen.v2h.toFixed(0)}
                  unit="kWh"
                  subtitle={strompreis ? `≈ ${fmtCalc(emobSummen.v2h * strompreis.netzbezug_arbeitspreis_cent_kwh / 100, 0)} € Ersparnis` : undefined}
                  icon={Battery}
                  color="text-cyan-500"
                  bgColor="bg-cyan-50 dark:bg-cyan-900/20"
                  formel="Σ Rückspeisung ins Haus (Vehicle-to-Home)"
                />
              )}
            </div>
          )}

          {/* E-Auto Chart */}
          <Card>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              E-Mobilität pro Monat
            </h3>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData.filter(z => z.emob_km > 0 || z.emob_ladung_kwh > 0)} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="right" orientation="right" domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(value: number, name: string) => {
                      if (name.includes('PV-Anteil')) return [`${value?.toFixed(0) || '---'}%`, name]
                      if (name.includes('km')) return [`${value.toFixed(0)} km`, name]
                      if (name.includes('€')) return [`${value.toFixed(2)} €`, name]
                      return [`${value.toFixed(0)} kWh`, name]
                    }}
                    contentStyle={{ backgroundColor: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb' }}
                  />
                  <Legend />
                  <Bar yAxisId="left" dataKey="emob_ladung_pv_kwh" name="PV-Ladung" stackId="ladung" fill="#f59e0b" />
                  <Bar yAxisId="left" dataKey="emob_ladung_netz_kwh" name="Netz-Ladung" stackId="ladung" fill="#ef4444" />
                  {emobSummen.externLadung > 0 && (
                    <Bar yAxisId="left" dataKey="emob_ladung_extern_kwh" name="Extern" stackId="ladung" fill="#f97316" />
                  )}
                  {komponenten.hat_v2h && (
                    <Bar yAxisId="left" dataKey="emob_v2h_kwh" name="V2H" fill="#06b6d4" />
                  )}
                  <Line yAxisId="right" type="monotone" dataKey="emob_pv_anteil_prozent" name="PV-Anteil (%)" stroke={CHART_COLORS.emobPvAnteil} strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </>
      )}

      {/* ========== BALKONKRAFTWERK ========== */}
      {komponenten?.hat_balkonkraftwerk && bkwSummen.erzeugung > 0 && (
        <>
          <div className="border-b border-gray-200 dark:border-gray-700 pb-2 mt-8">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <Sun className="h-6 w-6 text-yellow-500" />
              Balkonkraftwerk
              {bkwSummen.speicherLadung > 0 && (
                <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 px-2 py-0.5 rounded">
                  mit Speicher
                </span>
              )}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Die BKW-Erzeugung ist in der PV-Gesamterzeugung enthalten, wird hier aber separat ausgewiesen.
            </p>
          </div>

          {/* BKW KPIs - Erste Zeile */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KPICard
              title="Erzeugung gesamt"
              value={bkwSummen.erzeugung.toFixed(0)}
              unit="kWh"
              icon={Sun}
              color="text-yellow-500"
              bgColor="bg-yellow-50 dark:bg-yellow-900/20"
              formel="Σ BKW-Erzeugung aller Monate"
              berechnung={`${fmtCalc(bkwSummen.erzeugung, 0)} kWh`}
              ergebnis={`= ${fmtCalc(bkwSummen.erzeugung, 0)} kWh`}
            />
            <KPICard
              title="Eigenverbrauch"
              value={bkwSummen.eigenverbrauch.toFixed(0)}
              unit="kWh"
              icon={Sun}
              color="text-green-500"
              bgColor="bg-green-50 dark:bg-green-900/20"
              formel="Σ BKW-Eigenverbrauch aller Monate"
              berechnung={`${fmtCalc(bkwSummen.eigenverbrauch, 0)} kWh`}
              ergebnis={`= ${fmtCalc(bkwSummen.eigenverbrauch, 0)} kWh`}
            />
            <KPICard
              title="EV-Quote"
              value={bkwSummen.erzeugung > 0 ? ((bkwSummen.eigenverbrauch / bkwSummen.erzeugung) * 100).toFixed(0) : '---'}
              unit="%"
              icon={Sun}
              color="text-purple-500"
              bgColor="bg-purple-50 dark:bg-purple-900/20"
              formel="Eigenverbrauch ÷ Erzeugung × 100"
              berechnung={`${fmtCalc(bkwSummen.eigenverbrauch, 0)} kWh ÷ ${fmtCalc(bkwSummen.erzeugung, 0)} kWh × 100`}
              ergebnis={bkwSummen.erzeugung > 0 ? `= ${fmtCalc((bkwSummen.eigenverbrauch / bkwSummen.erzeugung) * 100, 0)}%` : '---'}
            />
            <KPICard
              title="Einspeisung"
              value={(bkwSummen.erzeugung - bkwSummen.eigenverbrauch).toFixed(0)}
              unit="kWh"
              subtitle="geschätzt"
              icon={Sun}
              color="text-blue-500"
              bgColor="bg-blue-50 dark:bg-blue-900/20"
            />
          </div>

          {/* BKW KPIs - Zweite Zeile: Speicher (nur wenn vorhanden) */}
          {bkwSummen.speicherLadung > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <KPICard
                title="Speicher Ladung"
                value={bkwSummen.speicherLadung.toFixed(0)}
                unit="kWh"
                icon={Battery}
                color="text-green-500"
                bgColor="bg-green-50 dark:bg-green-900/20"
                formel="Σ BKW-Speicher Ladung"
              />
              <KPICard
                title="Speicher Entladung"
                value={bkwSummen.speicherEntladung.toFixed(0)}
                unit="kWh"
                icon={Battery}
                color="text-blue-500"
                bgColor="bg-blue-50 dark:bg-blue-900/20"
                formel="Σ BKW-Speicher Entladung"
              />
              <KPICard
                title="Speicher Effizienz"
                value={bkwSummen.speicherLadung > 0 ? ((bkwSummen.speicherEntladung / bkwSummen.speicherLadung) * 100).toFixed(0) : '---'}
                unit="%"
                icon={Battery}
                color="text-cyan-500"
                bgColor="bg-cyan-50 dark:bg-cyan-900/20"
                formel="Entladung ÷ Ladung × 100"
              />
            </div>
          )}

          {/* BKW Chart */}
          <Card>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Balkonkraftwerk pro Monat
            </h3>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData.filter(z => z.bkw_erzeugung_kwh > 0)} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis unit=" kWh" tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(value: number, name: string) => [`${value.toFixed(0)} kWh`, name]}
                    contentStyle={{ backgroundColor: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb' }}
                  />
                  <Legend />
                  <Bar dataKey="bkw_erzeugung_kwh" name="Erzeugung" fill="#f59e0b" />
                  <Bar dataKey="bkw_eigenverbrauch_kwh" name="Eigenverbrauch" fill="#10b981" />
                  {bkwSummen.speicherLadung > 0 && (
                    <>
                      <Bar dataKey="bkw_speicher_ladung_kwh" name="Speicher Ladung" fill="#22c55e" />
                      <Bar dataKey="bkw_speicher_entladung_kwh" name="Speicher Entladung" fill="#3b82f6" />
                    </>
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </>
      )}

      {/* ========== SONSTIGES ========== */}
      {komponenten?.hat_sonstiges && (sonstigesSummen.erzeugung > 0 || sonstigesSummen.verbrauch > 0) && (
        <>
          <div className="border-b border-gray-200 dark:border-gray-700 pb-2 mt-8">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <Zap className="h-6 w-6 text-gray-500" />
              Sonstige Komponenten
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Aggregiert alle Investitionen vom Typ "Sonstiges" (z.B. Mini-BHKW, Pool-Pumpe).
            </p>
          </div>

          {/* Sonstiges KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {sonstigesSummen.erzeugung > 0 && (
              <KPICard
                title="Erzeugung gesamt"
                value={sonstigesSummen.erzeugung.toFixed(0)}
                unit="kWh"
                icon={Zap}
                color="text-green-500"
                bgColor="bg-green-50 dark:bg-green-900/20"
              />
            )}
            {sonstigesSummen.verbrauch > 0 && (
              <KPICard
                title="Verbrauch gesamt"
                value={sonstigesSummen.verbrauch.toFixed(0)}
                unit="kWh"
                icon={Zap}
                color="text-red-500"
                bgColor="bg-red-50 dark:bg-red-900/20"
              />
            )}
            {sonstigesSummen.erzeugung > 0 && sonstigesSummen.verbrauch > 0 && (
              <KPICard
                title="Netto"
                value={(sonstigesSummen.erzeugung - sonstigesSummen.verbrauch).toFixed(0)}
                unit="kWh"
                icon={Zap}
                color={(sonstigesSummen.erzeugung - sonstigesSummen.verbrauch) >= 0 ? "text-green-500" : "text-red-500"}
                bgColor={(sonstigesSummen.erzeugung - sonstigesSummen.verbrauch) >= 0 ? "bg-green-50 dark:bg-green-900/20" : "bg-red-50 dark:bg-red-900/20"}
              />
            )}
          </div>

          {/* Sonstiges Chart */}
          <Card>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Sonstige Komponenten pro Monat
            </h3>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData.filter(z => z.sonstiges_erzeugung_kwh > 0 || z.sonstiges_verbrauch_kwh > 0)} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis unit=" kWh" tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(value: number, name: string) => [`${value.toFixed(0)} kWh`, name]}
                    contentStyle={{ backgroundColor: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb' }}
                  />
                  <Legend />
                  {sonstigesSummen.erzeugung > 0 && (
                    <Bar dataKey="sonstiges_erzeugung_kwh" name="Erzeugung" fill="#10b981" />
                  )}
                  {sonstigesSummen.verbrauch > 0 && (
                    <Bar dataKey="sonstiges_verbrauch_kwh" name="Verbrauch" fill="#ef4444" />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </>
      )}

      {/* Hinweis wenn Komponenten vorhanden aber keine Monatsdaten */}
      {komponenten && (
        (komponenten.hat_waermepumpe && wpSummen.strom === 0) ||
        (komponenten.hat_emobilitaet && emobSummen.ladung === 0) ||
        (komponenten.hat_balkonkraftwerk && bkwSummen.erzeugung === 0) ||
        (komponenten.hat_sonstiges && sonstigesSummen.erzeugung === 0 && sonstigesSummen.verbrauch === 0)
      ) && (
        <Card className="bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-medium text-amber-800 dark:text-amber-200">
                Komponenten ohne Monatsdaten
              </h4>
              <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                Einige Investitionen sind angelegt, haben aber noch keine Monatsdaten.
                Erfasse monatliche Verbrauchsdaten unter <strong>Einstellungen → Investitionen</strong>.
              </p>
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}
