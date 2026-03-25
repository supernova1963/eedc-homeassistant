/**
 * Prognose vs. IST Auswertung
 *
 * Vergleicht PVGIS Ertragsprognose mit tatsächlichen Monatsdaten.
 * Zeigt Abweichungen und hilft bei der Bewertung der Anlagenperformance.
 */

import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, Sun, AlertCircle, RefreshCw, Target, Download, Brain } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, Button } from '../components/ui'
import ChartTooltip from '../components/ui/ChartTooltip'
import { useSelectedAnlage } from '../hooks'
import { pvgisApi, monatsdatenApi, cockpitApi } from '../api'
import type { PVModulPrognose } from '../api/pvgis'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import type { PrognoseVergleich } from '../api/cockpit'
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  ComposedChart, Line, ReferenceLine, Bar
} from 'recharts'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

// Gemeinsamer Typ für Prognose-Daten (gespeichert oder live)
interface PrognoseData {
  jahresertrag_kwh: number
  monatswerte: Array<{ monat: number; e_m: number }>
  isLive?: boolean
  module?: PVModulPrognose[]  // Modul-Details bei Live-Prognose
}

interface VergleichsDaten {
  monat: number
  monatName: string
  prognose: number
  ist: number
  abweichung: number
  abweichungProzent: number
}

export default function PrognoseVsIst() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const [selectedJahr, setSelectedJahr] = useState<number>(new Date().getFullYear())
  const [prognose, setPrognose] = useState<PrognoseData | null>(null)
  const [monatsdaten, setMonatsdaten] = useState<AggregierteMonatsdaten[]>([])
  const [loading, setLoading] = useState(false)
  const [savingPrognose, setSavingPrognose] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [vergleich, setVergleich] = useState<PrognoseVergleich | null>(null)

  // Daten laden
  useEffect(() => {
    if (selectedAnlageId) {
      loadData()
    }
  }, [selectedAnlageId, selectedJahr])

  const loadData = async () => {
    if (!selectedAnlageId) return

    setLoading(true)
    setError(null)

    try {
      // Aggregierte Monatsdaten laden (korrekte PV-Erzeugung aus InvestitionMonatsdaten)
      const monatsdatenData = await monatsdatenApi.listAggregiert(selectedAnlageId)
      setMonatsdaten(monatsdatenData)

      // Prognose-Vergleich (EEDC vs. ML vs. IST) laden
      try {
        const vergleichData = await cockpitApi.getPrognoseVergleich(selectedAnlageId, selectedJahr)
        setVergleich(vergleichData)
      } catch {
        setVergleich(null)
      }

      // Versuche gespeicherte Prognose zu laden
      const gespeichertePrognose = await pvgisApi.getAktivePrognose(selectedAnlageId)

      if (gespeichertePrognose) {
        // Gespeicherte Prognose verwenden
        setPrognose({
          jahresertrag_kwh: gespeichertePrognose.jahresertrag_kwh,
          monatswerte: gespeichertePrognose.monatswerte,
          isLive: false
        })
      } else {
        // Keine gespeicherte Prognose -> Live-Prognose abrufen
        try {
          const livePrognose = await pvgisApi.getPrognose(selectedAnlageId)
          setPrognose({
            jahresertrag_kwh: livePrognose.jahresertrag_kwh,
            monatswerte: livePrognose.monatsdaten.map(m => ({
              monat: m.monat,
              e_m: m.e_m
            })),
            isLive: true,
            module: livePrognose.module  // Modul-Details speichern
          })
        } catch (pvgisError) {
          // PVGIS-Abruf fehlgeschlagen (z.B. keine PV-Module definiert)
          setPrognose(null)
          if (pvgisError instanceof Error && pvgisError.message.includes('PV-Module')) {
            setError('Keine PV-Module für diese Anlage definiert. Bitte unter Einstellungen → Investitionen anlegen.')
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden')
    } finally {
      setLoading(false)
    }
  }

  // Prognose speichern
  const handleSavePrognose = async () => {
    if (!selectedAnlageId) return

    setSavingPrognose(true)
    try {
      await pvgisApi.speicherePrognose(selectedAnlageId)
      // Modul-Daten vom aktuellen State behalten (werden nicht in DB gespeichert)
      const currentModule = prognose?.module
      // Neu laden um gespeicherte Prognose zu verwenden
      await loadData()
      // Modul-Daten wieder hinzufügen falls vorhanden
      if (currentModule && currentModule.length > 0) {
        setPrognose(prev => prev ? { ...prev, module: currentModule } : null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    } finally {
      setSavingPrognose(false)
    }
  }

  // Verfügbare Jahre aus Monatsdaten extrahieren
  const verfuegbareJahre = [...new Set(monatsdaten.map(m => m.jahr))].sort((a, b) => b - a)

  // Jahr automatisch auf das neueste mit Daten setzen
  useEffect(() => {
    if (verfuegbareJahre.length > 0 && !verfuegbareJahre.includes(selectedJahr)) {
      setSelectedJahr(verfuegbareJahre[0])
    }
  }, [verfuegbareJahre, selectedJahr])

  // Vergleichsdaten berechnen
  const vergleichsDaten: VergleichsDaten[] = []
  if (prognose?.monatswerte) {
    for (let monat = 1; monat <= 12; monat++) {
      const prognoseWert = prognose.monatswerte.find(m => m.monat === monat)?.e_m || 0
      const istWert = monatsdaten
        .filter(m => m.jahr === selectedJahr && m.monat === monat)
        .reduce((sum, m) => sum + (m.pv_erzeugung_kwh || 0), 0)

      const abweichung = istWert - prognoseWert
      const abweichungProzent = prognoseWert > 0 ? (abweichung / prognoseWert) * 100 : 0

      vergleichsDaten.push({
        monat,
        monatName: monatNamen[monat],
        prognose: prognoseWert,
        ist: istWert,
        abweichung,
        abweichungProzent
      })
    }
  }

  // Jahresübersicht
  const jahresPrognose = vergleichsDaten.reduce((sum, d) => sum + d.prognose, 0)
  const jahresIst = vergleichsDaten.reduce((sum, d) => sum + d.ist, 0)
  const jahresAbweichung = jahresIst - jahresPrognose
  const jahresAbweichungProzent = jahresPrognose > 0 ? (jahresAbweichung / jahresPrognose) * 100 : 0

  // Monate mit Daten zählen
  const monateOhneDaten = vergleichsDaten.filter(d => d.ist === 0).length
  const monateMitDaten = 12 - monateOhneDaten

  // Hochrechnung auf Jahresbasis wenn nicht alle Monate vorhanden
  const hochgerechneterJahresIst = monateMitDaten > 0
    ? (jahresIst / monateMitDaten) * 12
    : 0

  if (anlagenLoading) return <LoadingSpinner text="Lade..." />

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Prognose vs. IST</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Target className="h-8 w-8 text-purple-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Prognose vs. IST</h1>
        </div>
        <div className="flex items-center gap-3">
          {anlagen.length > 1 && (
            <Select
              value={selectedAnlageId?.toString() || ''}
              onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
              options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
            />
          )}
          {verfuegbareJahre.length > 0 && (
            <Select
              value={selectedJahr.toString()}
              onChange={(e) => setSelectedJahr(parseInt(e.target.value))}
              options={verfuegbareJahre.map(j => ({ value: j.toString(), label: j.toString() }))}
            />
          )}
          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            title="Aktualisieren"
          >
            <RefreshCw className={`h-5 w-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {error && <Alert type="error">{error}</Alert>}

      {loading ? (
        <LoadingSpinner text="Lade Vergleichsdaten..." />
      ) : !prognose ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <Sun className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Keine PVGIS Prognose verfügbar.</p>
            <p className="text-sm mt-2">
              Bitte definiere PV-Module unter "Einstellungen → Investitionen".
            </p>
          </div>
        </Card>
      ) : monatsdaten.length === 0 ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Keine Monatsdaten für diese Anlage vorhanden.</p>
            <p className="text-sm mt-2">
              Erfasse Monatsdaten unter "Einstellungen → Monatsdaten".
            </p>
          </div>
        </Card>
      ) : (
        <>
          {/* Hinweis bei Live-Prognose */}
          {prognose.isLive && (
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 flex items-center justify-between gap-4">
              <div className="text-blue-700 dark:text-blue-300">
                <strong>Live-Prognose:</strong> Diese Prognose wurde gerade von PVGIS abgerufen und ist noch nicht gespeichert.
              </div>
              <Button
                size="sm"
                onClick={handleSavePrognose}
                disabled={savingPrognose}
              >
                <Download className="h-4 w-4 mr-1" />
                {savingPrognose ? 'Speichern...' : 'Speichern'}
              </Button>
            </div>
          )}

          {/* Jahresübersicht KPIs */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
            <Card className="p-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">PVGIS Prognose</p>
              <p className="text-2xl font-bold text-yellow-600 dark:text-yellow-400">
                {jahresPrognose.toLocaleString('de-DE', { maximumFractionDigits: 0 })} kWh
              </p>
              <p className="text-xs text-gray-400">Jahr {selectedJahr}</p>
            </Card>

            <Card className="p-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">IST-Erzeugung</p>
              <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                {jahresIst.toLocaleString('de-DE', { maximumFractionDigits: 0 })} kWh
              </p>
              <p className="text-xs text-gray-400">{monateMitDaten} von 12 Monaten</p>
            </Card>

            <Card className="p-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">Abweichung</p>
              <div className="flex items-center gap-2">
                {jahresAbweichung >= 0 ? (
                  <TrendingUp className="h-6 w-6 text-green-500" />
                ) : (
                  <TrendingDown className="h-6 w-6 text-red-500" />
                )}
                <p className={`text-2xl font-bold ${jahresAbweichung >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {jahresAbweichung >= 0 ? '+' : ''}{jahresAbweichung.toLocaleString('de-DE', { maximumFractionDigits: 0 })} kWh
                </p>
              </div>
              <p className={`text-xs ${jahresAbweichung >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {jahresAbweichung >= 0 ? '+' : ''}{jahresAbweichungProzent.toFixed(1)}%
              </p>
            </Card>

            {monateMitDaten < 12 && monateMitDaten > 0 && (
              <Card className="p-4">
                <p className="text-sm text-gray-500 dark:text-gray-400">Hochrechnung Jahr</p>
                <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                  {hochgerechneterJahresIst.toLocaleString('de-DE', { maximumFractionDigits: 0 })} kWh
                </p>
                <p className="text-xs text-gray-400">
                  ({((hochgerechneterJahresIst / jahresPrognose - 1) * 100).toFixed(1)}% vs. Prognose)
                </p>
              </Card>
            )}
          </div>

          {/* Monatlicher Vergleich Chart */}
          <Card className="space-y-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Monatlicher Vergleich {selectedJahr}
            </h2>

            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={vergleichsDaten}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="monatName" />
                  <YAxis yAxisId="left" tickFormatter={(v) => `${v} kWh`} />
                  <YAxis yAxisId="right" orientation="right" tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    content={
                      <ChartTooltip
                        formatter={(value: number, name: string) => {
                          if (name === 'Abweichung %') return `${value.toFixed(1)}%`
                          return `${value.toFixed(0)} kWh`
                        }}
                      />
                    }
                  />
                  <Legend />
                  <ReferenceLine yAxisId="right" y={0} stroke="#666" strokeDasharray="3 3" />
                  <Bar yAxisId="left" dataKey="prognose" fill="#f59e0b" name="PVGIS Prognose" />
                  <Bar yAxisId="left" dataKey="ist" fill="#22c55e" name="IST-Erzeugung" />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="abweichungProzent"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    name="Abweichung %"
                    dot={{ fill: '#8b5cf6' }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Prognose-Vergleich: EEDC vs. ML vs. IST */}
          {vergleich?.hat_sfml_daten && (
            <Card className="space-y-4">
              <div className="flex items-center gap-2">
                <Brain className="h-5 w-5 text-purple-500" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Prognose-Vergleich: EEDC vs. ML vs. IST
                </h2>
              </div>

              <p className="text-sm text-gray-500 dark:text-gray-400">
                Vergleich der täglichen GTI-Prognose (EEDC) mit Solar Forecast ML auf Monatsbasis.
                {vergleich.tage_mit_sfml < 30 && (
                  <span className="text-amber-600 dark:text-amber-400 ml-1">
                    Hinweis: Erst {vergleich.tage_mit_sfml} Tage mit ML-Daten — Genauigkeit steigt mit mehr Trainingsdaten.
                  </span>
                )}
              </p>

              {/* Jahres-KPIs */}
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-3 bg-orange-50 dark:bg-orange-900/20 rounded-lg">
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">EEDC-Forecast</p>
                  <p className="text-lg font-bold text-orange-600 dark:text-orange-400">
                    {vergleich.eedc_jahres_kwh.toLocaleString('de-DE', { maximumFractionDigits: 0 })} kWh
                  </p>
                  {vergleich.eedc_abweichung_pct !== null && (
                    <p className={`text-xs ${vergleich.eedc_abweichung_pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {vergleich.eedc_abweichung_pct >= 0 ? '+' : ''}{vergleich.eedc_abweichung_pct}% vs. IST
                    </p>
                  )}
                </div>
                <div className="text-center p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">ML-Forecast</p>
                  <p className="text-lg font-bold text-purple-600 dark:text-purple-400">
                    {vergleich.sfml_jahres_kwh.toLocaleString('de-DE', { maximumFractionDigits: 0 })} kWh
                  </p>
                  {vergleich.sfml_abweichung_pct !== null && (
                    <p className={`text-xs ${vergleich.sfml_abweichung_pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {vergleich.sfml_abweichung_pct >= 0 ? '+' : ''}{vergleich.sfml_abweichung_pct}% vs. IST
                    </p>
                  )}
                </div>
                <div className="text-center p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">IST-Erzeugung</p>
                  <p className="text-lg font-bold text-green-600 dark:text-green-400">
                    {vergleich.ist_jahres_kwh.toLocaleString('de-DE', { maximumFractionDigits: 0 })} kWh
                  </p>
                  <p className="text-xs text-gray-500">
                    {vergleich.tage_mit_eedc} Tage EEDC / {vergleich.tage_mit_sfml} Tage ML
                  </p>
                </div>
              </div>

              {/* Monatlicher Vergleich Chart */}
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={vergleich.monatswerte.filter(m => m.eedc_kwh > 0 || m.sfml_kwh > 0 || m.ist_kwh > 0)}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="monat_name" />
                    <YAxis tickFormatter={(v) => `${v}%`} domain={['auto', 'auto']} />
                    <Tooltip
                      content={
                        <ChartTooltip
                          formatter={(value: number, name: string) => {
                            if (name.includes('%')) return `${value.toFixed(1)}%`
                            return `${value.toFixed(0)} kWh`
                          }}
                        />
                      }
                    />
                    <Legend />
                    <ReferenceLine y={0} stroke="#666" strokeDasharray="3 3" />
                    <Bar dataKey="eedc_abweichung_pct" fill="#f97316" name="EEDC Abw. %" />
                    <Bar dataKey="sfml_abweichung_pct" fill="#a855f7" name="ML Abw. %" />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>

              {/* Monatstabelle */}
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-700">
                      <th className="text-left py-2 px-2">Monat</th>
                      <th className="text-right py-2 px-2 text-orange-600">EEDC</th>
                      <th className="text-right py-2 px-2 text-purple-600">ML</th>
                      <th className="text-right py-2 px-2 text-green-600">IST</th>
                      <th className="text-right py-2 px-2">EEDC Abw.</th>
                      <th className="text-right py-2 px-2">ML Abw.</th>
                      <th className="text-center py-2 px-2">Bessere Prognose</th>
                    </tr>
                  </thead>
                  <tbody>
                    {vergleich.monatswerte
                      .filter(m => m.eedc_kwh > 0 || m.sfml_kwh > 0 || m.ist_kwh > 0)
                      .map((m) => {
                        const eedcAbw = m.eedc_abweichung_pct !== null ? Math.abs(m.eedc_abweichung_pct) : null
                        const sfmlAbw = m.sfml_abweichung_pct !== null ? Math.abs(m.sfml_abweichung_pct) : null
                        const besser = eedcAbw !== null && sfmlAbw !== null
                          ? sfmlAbw < eedcAbw ? 'ML' : eedcAbw < sfmlAbw ? 'EEDC' : 'Gleich'
                          : null

                        return (
                          <tr key={m.monat} className="border-b border-gray-100 dark:border-gray-800">
                            <td className="py-2 px-2 font-medium">{m.monat_name}</td>
                            <td className="text-right py-2 px-2 text-orange-600">{m.eedc_kwh > 0 ? `${m.eedc_kwh.toFixed(0)} kWh` : '-'}</td>
                            <td className="text-right py-2 px-2 text-purple-600">{m.sfml_kwh > 0 ? `${m.sfml_kwh.toFixed(0)} kWh` : '-'}</td>
                            <td className="text-right py-2 px-2 text-green-600">{m.ist_kwh > 0 ? `${m.ist_kwh.toFixed(0)} kWh` : '-'}</td>
                            <td className={`text-right py-2 px-2 ${m.eedc_abweichung_pct !== null ? (m.eedc_abweichung_pct >= 0 ? 'text-green-600' : 'text-red-600') : ''}`}>
                              {m.eedc_abweichung_pct !== null ? `${m.eedc_abweichung_pct >= 0 ? '+' : ''}${m.eedc_abweichung_pct.toFixed(1)}%` : '-'}
                            </td>
                            <td className={`text-right py-2 px-2 ${m.sfml_abweichung_pct !== null ? (m.sfml_abweichung_pct >= 0 ? 'text-green-600' : 'text-red-600') : ''}`}>
                              {m.sfml_abweichung_pct !== null ? `${m.sfml_abweichung_pct >= 0 ? '+' : ''}${m.sfml_abweichung_pct.toFixed(1)}%` : '-'}
                            </td>
                            <td className="text-center py-2 px-2">
                              {besser === 'ML' ? (
                                <span className="inline-flex items-center gap-1 text-purple-600 font-medium">
                                  <Brain className="h-3 w-3" /> ML
                                </span>
                              ) : besser === 'EEDC' ? (
                                <span className="text-orange-600 font-medium">EEDC</span>
                              ) : besser === 'Gleich' ? (
                                <span className="text-gray-500">Gleich</span>
                              ) : (
                                <span className="text-gray-400">-</span>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* Detailtabelle */}
          <Card className="space-y-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Monatliche Details
            </h2>

            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-2 px-2">Monat</th>
                    <th className="text-right py-2 px-2">PVGIS Prognose</th>
                    <th className="text-right py-2 px-2">IST-Erzeugung</th>
                    <th className="text-right py-2 px-2">Abweichung</th>
                    <th className="text-right py-2 px-2">%</th>
                    <th className="text-center py-2 px-2">Bewertung</th>
                  </tr>
                </thead>
                <tbody>
                  {vergleichsDaten.map((d) => (
                    <tr key={d.monat} className="border-b border-gray-100 dark:border-gray-800">
                      <td className="py-2 px-2 font-medium">{d.monatName}</td>
                      <td className="text-right py-2 px-2 text-yellow-600">
                        {d.prognose.toFixed(0)} kWh
                      </td>
                      <td className="text-right py-2 px-2">
                        {d.ist > 0 ? (
                          <span className="text-green-600">{d.ist.toFixed(0)} kWh</span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td className={`text-right py-2 px-2 ${d.abweichung >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {d.ist > 0 ? `${d.abweichung >= 0 ? '+' : ''}${d.abweichung.toFixed(0)} kWh` : '-'}
                      </td>
                      <td className={`text-right py-2 px-2 ${d.abweichungProzent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {d.ist > 0 ? `${d.abweichungProzent >= 0 ? '+' : ''}${d.abweichungProzent.toFixed(1)}%` : '-'}
                      </td>
                      <td className="text-center py-2 px-2">
                        {d.ist === 0 ? (
                          <span className="text-gray-400">Keine Daten</span>
                        ) : d.abweichungProzent >= 5 ? (
                          <span className="inline-flex items-center gap-1 text-green-600">
                            <TrendingUp className="h-4 w-4" />
                            Übertroffen
                          </span>
                        ) : d.abweichungProzent >= -5 ? (
                          <span className="text-blue-600">Im Plan</span>
                        ) : d.abweichungProzent >= -15 ? (
                          <span className="text-yellow-600">Leicht unter Plan</span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-red-600">
                            <TrendingDown className="h-4 w-4" />
                            Unter Plan
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 border-gray-300 dark:border-gray-600 font-bold">
                    <td className="py-2 px-2">Gesamt</td>
                    <td className="text-right py-2 px-2 text-yellow-600">
                      {jahresPrognose.toFixed(0)} kWh
                    </td>
                    <td className="text-right py-2 px-2 text-green-600">
                      {jahresIst.toFixed(0)} kWh
                    </td>
                    <td className={`text-right py-2 px-2 ${jahresAbweichung >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {jahresAbweichung >= 0 ? '+' : ''}{jahresAbweichung.toFixed(0)} kWh
                    </td>
                    <td className={`text-right py-2 px-2 ${jahresAbweichungProzent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {jahresAbweichungProzent >= 0 ? '+' : ''}{jahresAbweichungProzent.toFixed(1)}%
                    </td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Card>

          {/* Erklärung */}
          <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
            <h3 className="font-medium text-purple-700 dark:text-purple-300 mb-2">
              Interpretation der Abweichungen
            </h3>
            <ul className="text-sm text-purple-600 dark:text-purple-400 space-y-1 list-disc list-inside">
              <li><strong>Übertroffen (&gt;5%):</strong> Die Anlage produziert mehr als erwartet - sehr gut!</li>
              <li><strong>Im Plan (±5%):</strong> Die Anlage entspricht den Erwartungen von PVGIS.</li>
              <li><strong>Leicht unter Plan (-5% bis -15%):</strong> Kleinere Abweichungen, z.B. durch lokale Wetterbedingungen.</li>
              <li><strong>Unter Plan (&lt;-15%):</strong> Deutliche Minderleistung - Verschattung, Verschmutzung oder technische Probleme prüfen.</li>
            </ul>
            <p className="text-xs text-purple-500 dark:text-purple-400 mt-3">
              Hinweis: PVGIS basiert auf langjährigen Mittelwerten. Einzelne Monate können stark abweichen.
            </p>
          </div>

        </>
      )}
    </div>
  )
}
