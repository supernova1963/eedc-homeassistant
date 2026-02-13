/**
 * Finanzen-Tab: Finanzprognose mit ROI und Amortisation
 */
import { useState, useEffect } from 'react'
import { Euro, TrendingUp, PiggyBank, CheckCircle, Clock, Battery, Car, Flame } from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import { aussichtenApi, FinanzPrognose } from '../../api/aussichten'
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  PieChart,
  Pie,
  Cell,
} from 'recharts'

interface Props {
  anlageId: number
}

const COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ec4899']

// Icons für Komponenten-Typen
const KOMPONENTEN_ICONS: Record<string, typeof Battery> = {
  'speicher': Battery,
  'e-auto-v2h': Car,
  'e-auto-ladung': Car,
  'waermepumpe': Flame,
}

export default function FinanzenTab({ anlageId }: Props) {
  const [prognose, setPrognose] = useState<FinanzPrognose | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [monate, setMonate] = useState(12)

  useEffect(() => {
    loadPrognose()
  }, [anlageId, monate])

  async function loadPrognose() {
    setLoading(true)
    setError(null)
    try {
      const data = await aussichtenApi.getFinanzPrognose(anlageId, monate)
      setPrognose(data)
    } catch (err: any) {
      setError(err.message || 'Fehler beim Laden der Finanzprognose')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <LoadingSpinner text="Lade Finanzprognose..." />
  }

  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  if (!prognose) {
    return <Alert type="warning">Keine Prognose verfügbar</Alert>
  }

  // Chart-Daten
  const chartData = prognose.monatswerte.map(m => ({
    name: `${m.monat_name.substring(0, 3)} ${m.jahr}`,
    einspeise_erloes: m.einspeise_erloes_euro,
    ev_ersparnis: m.ev_ersparnis_euro,
    netto_ertrag: m.netto_ertrag_euro,
  }))

  // Pie-Chart für Ertrags-Zusammensetzung
  const pieData = [
    { name: 'EV-Ersparnis', value: prognose.jahres_ev_ersparnis_euro },
    { name: 'Einspeise-Erlös', value: prognose.jahres_einspeise_erloes_euro },
  ]

  // Amortisations-Fortschritt (kumuliert)
  const amortFortschritt = Math.min(prognose.amortisations_fortschritt_prozent, 100)

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
              <Euro className="h-5 w-5 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Jahres-Ertrag</p>
              <p className="text-xl font-bold text-green-600">
                {prognose.jahres_netto_ertrag_euro.toLocaleString('de-DE', { minimumFractionDigits: 0, maximumFractionDigits: 0 })} €
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <TrendingUp className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Amortisation</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {prognose.amortisations_fortschritt_prozent.toFixed(1)}%
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            {prognose.amortisation_erreicht ? (
              <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
              </div>
            ) : (
              <div className="p-2 bg-orange-100 dark:bg-orange-900/30 rounded-lg">
                <Clock className="h-5 w-5 text-orange-600 dark:text-orange-400" />
              </div>
            )}
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Amortisation</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {prognose.amortisation_erreicht ? (
                  <span className="text-green-600">Erreicht</span>
                ) : prognose.amortisation_prognose_jahr ? (
                  <span>{prognose.amortisation_prognose_jahr}</span>
                ) : (
                  <span className="text-gray-400">-</span>
                )}
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
              <PiggyBank className="h-5 w-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Bisherige Erträge</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {prognose.bisherige_ertraege_euro.toLocaleString('de-DE', { minimumFractionDigits: 0, maximumFractionDigits: 0 })} €
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* ROI-Fortschrittsbalken */}
      <Card className="p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-semibold text-gray-900 dark:text-white">Amortisations-Fortschritt</h3>
          <span className="text-sm text-gray-500">
            {prognose.bisherige_ertraege_euro.toLocaleString('de-DE')} € von {prognose.investition_gesamt_euro.toLocaleString('de-DE')} €
          </span>
        </div>
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4">
          <div
            className={`h-4 rounded-full transition-all ${
              prognose.amortisation_erreicht
                ? 'bg-green-500'
                : amortFortschritt > 75
                ? 'bg-blue-500'
                : amortFortschritt > 50
                ? 'bg-yellow-500'
                : 'bg-orange-500'
            }`}
            style={{ width: `${amortFortschritt}%` }}
          />
        </div>
        {!prognose.amortisation_erreicht && prognose.restlaufzeit_bis_amortisation_monate && (
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
            Noch ca. {prognose.restlaufzeit_bis_amortisation_monate} Monate bis zur Amortisation
            (voraussichtlich {prognose.amortisation_prognose_jahr})
          </p>
        )}
      </Card>

      {/* Controls */}
      <Card className="p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900 dark:text-white">Monatliche Ertrags-Prognose</h3>
          <select
            value={monate}
            onChange={(e) => setMonate(Number(e.target.value))}
            className="input w-auto text-sm"
          >
            <option value={6}>6 Monate</option>
            <option value={12}>12 Monate</option>
            <option value={24}>24 Monate</option>
          </select>
        </div>
      </Card>

      {/* Charts nebeneinander */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Bar-Chart */}
        <Card className="p-4 lg:col-span-2">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Monatliche Erträge</h3>
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 11 }}
                  angle={-45}
                  textAnchor="end"
                  height={60}
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  label={{ value: '€', angle: -90, position: 'insideLeft' }}
                />
                <Tooltip
                  formatter={(value: number, name: string) => {
                    const labels: Record<string, string> = {
                      einspeise_erloes: 'Einspeise-Erlös',
                      ev_ersparnis: 'EV-Ersparnis',
                      netto_ertrag: 'Netto-Ertrag',
                    }
                    return [`${value.toFixed(2)} €`, labels[name] || name]
                  }}
                />
                <Legend
                  formatter={(value) => {
                    const labels: Record<string, string> = {
                      einspeise_erloes: 'Einspeise-Erlös',
                      ev_ersparnis: 'EV-Ersparnis',
                      netto_ertrag: 'Netto-Ertrag',
                    }
                    return labels[value] || value
                  }}
                />
                <Bar dataKey="einspeise_erloes" stackId="a" fill="#3b82f6" name="einspeise_erloes" />
                <Bar dataKey="ev_ersparnis" stackId="a" fill="#10b981" name="ev_ersparnis" />
                <Line
                  type="monotone"
                  dataKey="netto_ertrag"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  name="netto_ertrag"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Pie-Chart */}
        <Card className="p-4">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Ertrags-Zusammensetzung</h3>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                  label={({ percent }) => `${(percent * 100).toFixed(0)}%`}
                >
                  {pieData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => `${value.toFixed(2)} €`} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">EV-Quote:</span>
              <span className="font-medium">{prognose.eigenverbrauchsquote_prozent.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Eigenverbrauch:</span>
              <span className="font-medium">{prognose.jahres_eigenverbrauch_kwh.toLocaleString('de-DE')} kWh</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Einspeisung:</span>
              <span className="font-medium">{prognose.jahres_einspeisung_kwh.toLocaleString('de-DE')} kWh</span>
            </div>
          </div>
        </Card>
      </div>

      {/* Komponenten-Beiträge (nur wenn vorhanden) */}
      {prognose.komponenten_beitraege && prognose.komponenten_beitraege.length > 0 && (
        <Card className="p-4">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Komponenten-Beiträge zur Finanzierung</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {prognose.komponenten_beitraege.map((k, idx) => {
              const Icon = KOMPONENTEN_ICONS[k.typ] || Battery
              return (
                <div key={idx} className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                      <Icon className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                    </div>
                    <div>
                      <p className="font-medium text-gray-900 dark:text-white">{k.bezeichnung}</p>
                      <p className="text-xs text-gray-500">{k.beschreibung}</p>
                    </div>
                  </div>
                  <div className="mt-3 flex justify-between text-sm">
                    <span className="text-gray-500">{k.beitrag_kwh_jahr.toLocaleString('de-DE')} kWh/Jahr</span>
                    <span className="font-semibold text-green-600">+{k.beitrag_euro_jahr.toFixed(0)} €/Jahr</span>
                  </div>
                </div>
              )
            })}
          </div>
          {/* Zusammenfassung */}
          {(prognose.speicher_ev_erhoehung_kwh > 0 || prognose.v2h_rueckspeisung_kwh > 0 || prognose.wp_pv_anteil_kwh > 0) && (
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                {prognose.speicher_ev_erhoehung_kwh > 0 && (
                  <div>
                    <p className="text-gray-500">Speicher EV+</p>
                    <p className="font-semibold">{prognose.speicher_ev_erhoehung_kwh.toLocaleString('de-DE')} kWh</p>
                    <p className="text-green-600">+{prognose.speicher_ev_erhoehung_euro.toFixed(0)} €</p>
                  </div>
                )}
                {prognose.v2h_rueckspeisung_kwh > 0 && (
                  <div>
                    <p className="text-gray-500">V2H-Rückspeisung</p>
                    <p className="font-semibold">{prognose.v2h_rueckspeisung_kwh.toLocaleString('de-DE')} kWh</p>
                    <p className="text-green-600">+{prognose.v2h_ersparnis_euro.toFixed(0)} €</p>
                  </div>
                )}
                {prognose.eauto_ladung_pv_kwh > 0 && (
                  <div>
                    <p className="text-gray-500">E-Auto PV-Ladung</p>
                    <p className="font-semibold">{prognose.eauto_ladung_pv_kwh.toLocaleString('de-DE')} kWh</p>
                    <p className="text-green-600">+{prognose.eauto_ersparnis_euro.toFixed(0)} €</p>
                  </div>
                )}
                {prognose.wp_pv_anteil_kwh > 0 && (
                  <div>
                    <p className="text-gray-500">WP PV-Direkt</p>
                    <p className="font-semibold">{prognose.wp_pv_anteil_kwh.toLocaleString('de-DE')} kWh</p>
                    <p className="text-green-600">+{prognose.wp_pv_ersparnis_euro.toFixed(0)} €</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Strompreise & Investition */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="p-4">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Strompreise</h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
              <span className="text-gray-600 dark:text-gray-400">Einspeisevergütung</span>
              <span className="font-semibold text-blue-600">
                {prognose.einspeiseverguetung_cent_kwh.toFixed(2)} ct/kWh
              </span>
            </div>
            <div className="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
              <span className="text-gray-600 dark:text-gray-400">Netzbezugspreis</span>
              <span className="font-semibold text-orange-600">
                {prognose.netzbezug_preis_cent_kwh.toFixed(2)} ct/kWh
              </span>
            </div>
            <div className="flex justify-between items-center p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
              <span className="text-gray-600 dark:text-gray-400">Ersparnis durch EV</span>
              <span className="font-semibold text-green-600">
                {(prognose.netzbezug_preis_cent_kwh - prognose.einspeiseverguetung_cent_kwh).toFixed(2)} ct/kWh
              </span>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Investition & ROI</h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
              <span className="text-gray-600 dark:text-gray-400">Investition gesamt</span>
              <span className="font-semibold">
                {prognose.investition_gesamt_euro.toLocaleString('de-DE')} €
              </span>
            </div>
            <div className="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
              <span className="text-gray-600 dark:text-gray-400">Bisherige Erträge</span>
              <span className="font-semibold text-green-600">
                {prognose.bisherige_ertraege_euro.toLocaleString('de-DE')} €
              </span>
            </div>
            <div className="flex justify-between items-center p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
              <span className="text-gray-600 dark:text-gray-400">Prognose Jahres-Ertrag</span>
              <span className="font-semibold text-blue-600">
                {prognose.jahres_netto_ertrag_euro.toLocaleString('de-DE')} €/Jahr
              </span>
            </div>
          </div>
        </Card>
      </div>

      {/* Detail-Tabelle */}
      <Card className="p-4">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Monatswerte</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-2 px-3">Monat</th>
                <th className="text-right py-2 px-3">PV-Erzeugung</th>
                <th className="text-right py-2 px-3">Eigenverbrauch</th>
                <th className="text-right py-2 px-3">Einspeisung</th>
                <th className="text-right py-2 px-3">Einspeise-Erlös</th>
                <th className="text-right py-2 px-3">EV-Ersparnis</th>
                <th className="text-right py-2 px-3 font-semibold">Netto-Ertrag</th>
              </tr>
            </thead>
            <tbody>
              {prognose.monatswerte.map((m) => (
                <tr key={`${m.jahr}-${m.monat}`} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-2 px-3 font-medium">{m.monat_name} {m.jahr}</td>
                  <td className="py-2 px-3 text-right">{m.pv_erzeugung_kwh.toFixed(0)} kWh</td>
                  <td className="py-2 px-3 text-right">{m.eigenverbrauch_kwh.toFixed(0)} kWh</td>
                  <td className="py-2 px-3 text-right">{m.einspeisung_kwh.toFixed(0)} kWh</td>
                  <td className="py-2 px-3 text-right text-blue-600">{m.einspeise_erloes_euro.toFixed(2)} €</td>
                  <td className="py-2 px-3 text-right text-green-600">{m.ev_ersparnis_euro.toFixed(2)} €</td>
                  <td className="py-2 px-3 text-right font-semibold text-yellow-600">{m.netto_ertrag_euro.toFixed(2)} €</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-gray-300 dark:border-gray-600 font-semibold">
                <td className="py-2 px-3">Gesamt</td>
                <td className="py-2 px-3 text-right">{prognose.jahres_erzeugung_kwh.toLocaleString('de-DE')} kWh</td>
                <td className="py-2 px-3 text-right">{prognose.jahres_eigenverbrauch_kwh.toLocaleString('de-DE')} kWh</td>
                <td className="py-2 px-3 text-right">{prognose.jahres_einspeisung_kwh.toLocaleString('de-DE')} kWh</td>
                <td className="py-2 px-3 text-right text-blue-600">{prognose.jahres_einspeise_erloes_euro.toFixed(2)} €</td>
                <td className="py-2 px-3 text-right text-green-600">{prognose.jahres_ev_ersparnis_euro.toFixed(2)} €</td>
                <td className="py-2 px-3 text-right text-yellow-600">{prognose.jahres_netto_ertrag_euro.toFixed(2)} €</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </Card>

      {/* Meta-Info */}
      <Card className="p-4 bg-gray-50 dark:bg-gray-800">
        <div className="flex flex-wrap gap-4 text-sm text-gray-500 dark:text-gray-400">
          <span>Datenquellen: {prognose.datenquellen.join(', ')}</span>
          <span>Zeitraum: {prognose.prognose_zeitraum.von} bis {prognose.prognose_zeitraum.bis}</span>
        </div>
      </Card>
    </div>
  )
}
