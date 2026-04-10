/**
 * Aktueller Monat Dashboard
 *
 * Zeigt den laufenden Monat mit Daten aus allen verfügbaren Quellen
 * (HA-Sensoren, Connectors, gespeicherte Monatsdaten).
 * Manueller Aktualisieren-Button (kein Auto-Refresh).
 */

import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Sun, Battery, Flame, Car, Euro,
  ArrowDownToLine, RefreshCw, Clock,
  Home, TrendingUp, AlertCircle, CalendarClock,
  FileSpreadsheet, Plug, Cloud, Upload,
} from 'lucide-react'
import { Card, Button, Select, KPICard, FormelTooltip, fmtCalc } from '../components/ui'
import { MONAT_NAMEN } from '../lib/constants'
import ChartTooltip from '../components/ui/ChartTooltip'
import { DataLoadingState } from '../components/common'
import { useSelectedAnlage, useApiData } from '../hooks'
import { aktuellerMonatApi } from '../api/aktuellerMonat'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'

// ─── Colors ──────────────────────────────────────────────────────────────────

const COLORS = {
  erzeugung: '#f59e0b',
  einspeisung: '#10b981',
  eigenverbrauch: '#8b5cf6',
  netzbezug: '#ef4444',
  speicher: '#3b82f6',
  wp: '#f97316',
  emob: '#a855f7',
  bkw: '#eab308',
  erloese: '#10b981',
  kosten: '#ef4444',
  ersparnis: '#3b82f6',
  netto: '#8b5cf6',
  soll: '#9ca3af',
  vorjahr: '#94a3b8',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const fmt = (val: number | null | undefined, decimals = 1) => fmtCalc(val, decimals, '—')

function fmtEuro(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—'
  const prefix = val >= 0 ? '+' : ''
  return `${prefix}${fmtCalc(val, 2, '—')}`
}

function quelleLabel(quelle: string): string {
  switch (quelle) {
    case 'ha_statistics': return 'HA-Statistik'
    case 'ha_sensor': return 'HA-Sensor'
    case 'local_connector': return 'Connector'
    case 'gespeichert': return 'Gespeichert'
    default: return quelle
  }
}

function quelleColor(quelle: string): string {
  switch (quelle) {
    case 'ha_statistics': return 'bg-green-500'
    case 'ha_sensor': return 'bg-green-500'
    case 'local_connector': return 'bg-blue-500'
    case 'gespeichert': return 'bg-gray-400'
    default: return 'bg-gray-300'
  }
}

function QuelleBadge({ quelle, aktiv }: { quelle: string; aktiv: boolean }) {
  if (!aktiv) return null
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
      <span className={`w-2 h-2 rounded-full ${quelleColor(quelle)}`} />
      {quelleLabel(quelle)}
    </span>
  )
}


// ─── Main Component ──────────────────────────────────────────────────────────

export default function AktuellerMonat() {
  const navigate = useNavigate()
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const [refreshing, setRefreshing] = useState(false)

  const now = new Date()
  const [selectedJahr, setSelectedJahr] = useState(now.getFullYear())
  const [selectedMonat, setSelectedMonat] = useState(now.getMonth() + 1)
  const istAktuellerMonat = selectedJahr === now.getFullYear() && selectedMonat === now.getMonth() + 1

  const { data, loading, error, refetch } = useApiData(
    () => aktuellerMonatApi.getData(selectedAnlageId!, selectedJahr, selectedMonat),
    [selectedAnlageId, selectedJahr, selectedMonat],
    { enabled: selectedAnlageId != null },
  )

  const handleRefresh = async () => {
    setRefreshing(true)
    await refetch()
    setRefreshing(false)
  }

  // ── Chart Data ──

  const energieBilanzData = useMemo(() => {
    if (!data) return []
    return [
      { name: 'Erzeugung', value: data.pv_erzeugung_kwh || 0, quellefeld: 'pv_erzeugung_kwh', fill: '#f59e0b' },
      { name: 'Einspeisung', value: data.einspeisung_kwh || 0, quellefeld: 'einspeisung_kwh', fill: '#10b981' },
      { name: 'Eigenverbr.', value: data.eigenverbrauch_kwh || 0, quellefeld: null, fill: '#8b5cf6' },
      { name: 'Netzbezug', value: data.netzbezug_kwh || 0, quellefeld: 'netzbezug_kwh', fill: '#ef4444' },
    ].filter(d => d.value > 0)
  }, [data])

  const verteilungData = useMemo(() => {
    if (!data || !data.pv_erzeugung_kwh) return []
    return [
      { name: 'Eigenverbrauch', value: data.eigenverbrauch_kwh || 0, color: COLORS.eigenverbrauch },
      { name: 'Einspeisung', value: data.einspeisung_kwh || 0, color: COLORS.einspeisung },
    ].filter(d => d.value > 0)
  }, [data])

  const vorjahrData = useMemo(() => {
    if (!data?.vorjahr) return []
    const items: Array<{ name: string; Aktuell: number; Vorjahr: number }> = []
    if (data.pv_erzeugung_kwh !== null && data.vorjahr.pv_erzeugung_kwh !== undefined) {
      items.push({ name: 'PV-Erzeugung', Aktuell: data.pv_erzeugung_kwh, Vorjahr: data.vorjahr.pv_erzeugung_kwh })
    }
    if (data.einspeisung_kwh !== null && data.vorjahr.einspeisung_kwh !== undefined) {
      items.push({ name: 'Einspeisung', Aktuell: data.einspeisung_kwh, Vorjahr: data.vorjahr.einspeisung_kwh })
    }
    if (data.eigenverbrauch_kwh !== null && data.vorjahr.eigenverbrauch_kwh !== undefined) {
      items.push({ name: 'Eigenverbr.', Aktuell: data.eigenverbrauch_kwh, Vorjahr: data.vorjahr.eigenverbrauch_kwh })
    }
    if (data.netzbezug_kwh !== null && data.vorjahr.netzbezug_kwh !== undefined) {
      items.push({ name: 'Netzbezug', Aktuell: data.netzbezug_kwh, Vorjahr: data.vorjahr.netzbezug_kwh })
    }
    return items
  }, [data])

  const sollIstData = useMemo(() => {
    if (!data || data.soll_pv_kwh === null || data.pv_erzeugung_kwh === null) return []
    return [
      { name: 'PV-Erzeugung', IST: Math.round(data.pv_erzeugung_kwh), SOLL: Math.round(data.soll_pv_kwh) },
    ]
  }, [data])

  const vorjahrFormatter = useMemo(() => {
    const maxVal = vorjahrData.length > 0 ? Math.max(...vorjahrData.flatMap(d => [d.Aktuell, d.Vorjahr])) : 0
    const mwh = maxVal > 10000
    return (val: number) => mwh ? `${(val / 1000).toFixed(1)} MWh` : `${val} kWh`
  }, [vorjahrData])

  const sollIstFormatter = useMemo(() => {
    const maxVal = sollIstData.length > 0 ? Math.max(...sollIstData.flatMap(d => [d.IST, d.SOLL])) : 0
    const mwh = maxVal > 10000
    return (val: number) => mwh ? `${(val / 1000).toFixed(1)} MWh` : `${val} kWh`
  }, [sollIstData])

  const finanzData = useMemo(() => {
    if (!data) return []
    const items: Array<{ name: string; Betrag: number; fill: string }> = []
    if (data.einspeise_erloes_euro !== null) items.push({ name: 'Einspeise-Erlöse', Betrag: data.einspeise_erloes_euro, fill: COLORS.erloese })
    if (data.ev_ersparnis_euro !== null) items.push({ name: 'EV-Ersparnis', Betrag: data.ev_ersparnis_euro, fill: COLORS.ersparnis })
    if (data.wp_ersparnis_euro !== null) items.push({ name: 'WP-Ersparnis', Betrag: data.wp_ersparnis_euro, fill: COLORS.wp })
    if (data.emob_ersparnis_euro !== null) items.push({ name: 'eMob-Ersparnis', Betrag: data.emob_ersparnis_euro, fill: COLORS.emob })
    if (data.netzbezug_kosten_euro !== null) items.push({ name: 'Netzbezug-Kosten', Betrag: -data.netzbezug_kosten_euro, fill: COLORS.kosten })
    return items
  }, [data])

  const energieSaldo = useMemo(() => {
    if (!data || data.einspeise_erloes_euro === null || data.ev_ersparnis_euro === null || data.netzbezug_kosten_euro === null) return null
    let saldo = data.einspeise_erloes_euro + data.ev_ersparnis_euro - data.netzbezug_kosten_euro
    if (data.wp_ersparnis_euro !== null) saldo += data.wp_ersparnis_euro
    if (data.emob_ersparnis_euro !== null) saldo += data.emob_ersparnis_euro
    return Math.round(saldo * 100) / 100
  }, [data])

  // ── Loading / Error States ──

  if (anlagenLoading || loading) {
    return <DataLoadingState loading={true} error={null}><div /></DataLoadingState>
  }

  if (!selectedAnlageId || anlagen.length === 0) {
    return <DataLoadingState loading={false} error={null} isEmpty={true} emptyMessage="Keine Anlage angelegt."><div /></DataLoadingState>
  }

  if (error) {
    return <DataLoadingState loading={false} error={error} onRetry={refetch}><div /></DataLoadingState>
  }

  if (!data) return null

  const q = data.feld_quellen
  const vj = data.vorjahr

  const keineQuellen = !data.quellen.ha_statistics && !data.quellen.ha_sensor && !data.quellen.connector && !data.quellen.gespeichert
  const keineDaten = data.pv_erzeugung_kwh === null && data.einspeisung_kwh === null && data.netzbezug_kwh === null
  const hasChartData = energieBilanzData.length > 0

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <CalendarClock className="h-8 w-8 text-blue-500" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              {istAktuellerMonat ? 'Aktueller Monat: ' : ''}{data.monat_name} {data.jahr}
            </h1>
            <div className="flex items-center gap-2 mt-1">
              <QuelleBadge quelle="ha_statistics" aktiv={data.quellen.ha_statistics} />
              <QuelleBadge quelle="local_connector" aktiv={data.quellen.connector} />
              <QuelleBadge quelle="gespeichert" aktiv={data.quellen.gespeichert} />
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Select
            compact
            value={selectedMonat.toString()}
            onChange={(e) => setSelectedMonat(parseInt(e.target.value))}
            options={MONAT_NAMEN.slice(1).map((name, i) => ({ value: String(i + 1), label: name }))}
          />
          <Select
            compact
            value={selectedJahr.toString()}
            onChange={(e) => setSelectedJahr(parseInt(e.target.value))}
            options={Array.from({ length: 6 }, (_, i) => now.getFullYear() - i).map(y => ({ value: String(y), label: String(y) }))}
          />
          {anlagen.length > 1 && (
            <Select
              compact
              value={selectedAnlageId?.toString() || ''}
              onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
              options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
            />
          )}
          <Button
            variant="secondary"
            onClick={handleRefresh}
            loading={refreshing}
            disabled={!istAktuellerMonat}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Aktualisieren
          </Button>
          {data?.aktualisiert_um && (
            <span className="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500">
              <Clock className="h-3 w-3" />
              {new Date(data.aktualisiert_um).toLocaleString('de-DE', {
                day: '2-digit', month: '2-digit', year: 'numeric',
                hour: '2-digit', minute: '2-digit',
              })}
            </span>
          )}
        </div>
      </div>

      {/* ── Keine Daten Hinweis mit Aktionen ── */}
      {(keineQuellen || keineDaten) && (
        <Card>
          <div className="p-6">
            <div className="flex items-start gap-4 mb-6">
              <AlertCircle className="h-8 w-8 text-gray-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-lg font-medium text-gray-900 dark:text-white">
                  Keine Daten für {data.monat_name} {data.jahr}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  {istAktuellerMonat
                    ? 'Wählen Sie eine der folgenden Möglichkeiten, um Daten für den aktuellen Monat einzulesen:'
                    : 'Für diesen Monat sind keine gespeicherten Daten vorhanden. Sie können den Monatsabschluss durchführen, um Daten einzutragen.'}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <button
                onClick={() => navigate(`/monatsabschluss/${selectedAnlageId}`)}
                className="flex items-start gap-3 p-4 rounded-xl border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left"
              >
                <div className="p-2 rounded-lg bg-blue-50 dark:bg-blue-900/20">
                  <FileSpreadsheet className="h-5 w-5 text-blue-500" />
                </div>
                <div>
                  <p className="font-medium text-gray-900 dark:text-white">Monatsabschluss</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    Werte manuell erfassen oder aus Quellen zusammenführen
                  </p>
                </div>
              </button>
              <button
                onClick={() => navigate('/einstellungen/connector')}
                className="flex items-start gap-3 p-4 rounded-xl border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left"
              >
                <div className="p-2 rounded-lg bg-green-50 dark:bg-green-900/20">
                  <Plug className="h-5 w-5 text-green-500" />
                </div>
                <div>
                  <p className="font-medium text-gray-900 dark:text-white">Geräte-Connector</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    SMA, Fronius, Shelly, OpenDTU u.a. im lokalen Netzwerk
                  </p>
                </div>
              </button>
              <button
                onClick={() => navigate('/einstellungen/cloud-import')}
                className="flex items-start gap-3 p-4 rounded-xl border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left"
              >
                <div className="p-2 rounded-lg bg-purple-50 dark:bg-purple-900/20">
                  <Cloud className="h-5 w-5 text-purple-500" />
                </div>
                <div>
                  <p className="font-medium text-gray-900 dark:text-white">Cloud-Import</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    SolarEdge, Fronius SolarWeb, Huawei, Growatt, Deye
                  </p>
                </div>
              </button>
              <button
                onClick={() => navigate('/einstellungen/portal-import')}
                className="flex items-start gap-3 p-4 rounded-xl border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left"
              >
                <div className="p-2 rounded-lg bg-orange-50 dark:bg-orange-900/20">
                  <Upload className="h-5 w-5 text-orange-500" />
                </div>
                <div>
                  <p className="font-medium text-gray-900 dark:text-white">Portal-Import (CSV)</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    CSV-Upload von SMA Sunny Portal, EVCC, Fronius u.a.
                  </p>
                </div>
              </button>
            </div>
          </div>
        </Card>
      )}

      {/* ── Hero KPIs ── */}
      {!keineDaten && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KPICard
            title="PV-Erzeugung"
            value={data.pv_erzeugung_kwh !== null ? fmt(data.pv_erzeugung_kwh) : '—'}
            unit="kWh"
            icon={Sun}
            color="yellow"
            subtitle={data.soll_pv_kwh !== null
              ? `SOLL: ${fmt(data.soll_pv_kwh)} kWh`
              : vj?.pv_erzeugung_kwh !== undefined
                ? `VJ: ${fmt(vj.pv_erzeugung_kwh)} kWh`
                : undefined}
          />
          <KPICard
            title="Autarkie"
            value={data.autarkie_prozent !== null ? fmt(data.autarkie_prozent, 0) : '—'}
            unit="%"
            icon={Home}
            color="green"
            subtitle={vj?.autarkie_prozent !== undefined
              ? `VJ: ${fmt(vj.autarkie_prozent, 0)}%`
              : undefined}
            formel="Eigenverbrauch ÷ Gesamtverbrauch × 100"
            berechnung={data.eigenverbrauch_kwh !== null && data.gesamtverbrauch_kwh !== null
              ? `${fmtCalc(data.eigenverbrauch_kwh, 0)} kWh ÷ ${fmtCalc(data.gesamtverbrauch_kwh, 0)} kWh × 100`
              : undefined}
            ergebnis={data.autarkie_prozent !== null ? `= ${fmtCalc(data.autarkie_prozent, 1)} %` : undefined}
          />
          <KPICard
            title="Netto-Ertrag PV"
            value={data.netto_ertrag_euro !== null ? fmtEuro(data.netto_ertrag_euro) : '—'}
            unit="€"
            icon={Euro}
            color={data.netto_ertrag_euro !== null && data.netto_ertrag_euro >= 0 ? 'green' : 'red'}
            formel="Einspeise-Erlöse + EV-Ersparnis (Ertrag der PV-Anlage, ohne Netzbezug-Abzug)"
            berechnung={data.einspeise_erloes_euro !== null && data.ev_ersparnis_euro !== null
              ? `${fmtCalc(data.einspeise_erloes_euro, 2)} + ${fmtCalc(data.ev_ersparnis_euro, 2)} €`
              : undefined}
            ergebnis={data.netto_ertrag_euro !== null ? `= ${fmtCalc(data.netto_ertrag_euro, 2)} €` : undefined}
          />
        </div>
      )}

      {/* ── Energie-Bilanz Chart + Verteilung Donut ── */}
      {hasChartData && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-2">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Energie-Bilanz
            </h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={energieBilanzData} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" unit=" kWh" />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={110}
                    tick={(props: { x: number; y: number; payload: { value: string; index: number } }) => {
                      const entry = energieBilanzData[props.payload.index]
                      const info = entry?.quellefeld ? q[entry.quellefeld] : null
                      return (
                        <g transform={`translate(${props.x},${props.y})`}>
                          <text x={-8} y={0} dy={4} textAnchor="end" className="text-xs fill-gray-700 dark:fill-gray-300" fontSize={12}>
                            {props.payload.value}
                          </text>
                          {info && (
                            <circle cx={-2} cy={1} r={3.5} className={quelleColor(info.quelle).replace('bg-', 'fill-')}
                              fill={info.quelle === 'ha_statistics' || info.quelle === 'ha_sensor' ? '#22c55e' : info.quelle === 'local_connector' ? '#3b82f6' : '#9ca3af'}
                            >
                              <title>{quelleLabel(info.quelle)}</title>
                            </circle>
                          )}
                        </g>
                      )
                    }}
                  />
                  <Tooltip content={<ChartTooltip unit="kWh" />} />
                  <Bar dataKey="value" name="kWh" radius={[0, 4, 4, 0]}>
                    {energieBilanzData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Energieverteilung
            </h2>
            {verteilungData.length > 0 ? (
              <>
                <div className="h-52">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={verteilungData}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={45}
                        outerRadius={75}
                        label={({ percent }) => `${(percent * 100).toFixed(0)}%`}
                        labelLine={false}
                      >
                        {verteilungData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip content={<ChartTooltip unit="kWh" />} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-2 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS.eigenverbrauch }} />
                      <span className="text-gray-500">Eigenverbrauch:</span>
                    </span>
                    <span className="font-medium">{fmt(data.eigenverbrauch_kwh)} kWh</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS.einspeisung }} />
                      <span className="text-gray-500">Einspeisung:</span>
                    </span>
                    <span className="font-medium">{fmt(data.einspeisung_kwh)} kWh</span>
                  </div>
                  {data.eigenverbrauch_quote_prozent !== null && (
                    <div className="flex justify-between pt-1 border-t border-gray-100 dark:border-gray-700">
                      <span className="text-gray-500">EV-Quote:</span>
                      <FormelTooltip
                        formel="Eigenverbrauch ÷ PV-Erzeugung × 100"
                        berechnung={data.eigenverbrauch_kwh !== null && data.pv_erzeugung_kwh !== null
                          ? `${fmtCalc(data.eigenverbrauch_kwh, 0)} kWh ÷ ${fmtCalc(data.pv_erzeugung_kwh, 0)} kWh × 100`
                          : undefined}
                        ergebnis={`= ${fmtCalc(data.eigenverbrauch_quote_prozent, 1)} %`}
                      >
                        <span className="font-medium">{fmt(data.eigenverbrauch_quote_prozent, 0)}%</span>
                      </FormelTooltip>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <p className="text-gray-400 text-sm text-center py-8">Keine Verteilungsdaten</p>
            )}
          </Card>
        </div>
      )}

      {/* ── Vorjahresvergleich Chart ── */}
      {vorjahrData.length > 0 && (
        <Card>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Vorjahresvergleich: {data.monat_name} {data.jahr} vs. {data.jahr - 1}
          </h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={vorjahrData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis tickFormatter={vorjahrFormatter} width={90} />
                <Tooltip content={<ChartTooltip unit="kWh" />} />
                <Legend />
                <Bar dataKey="Aktuell" fill={COLORS.erzeugung} radius={[4, 4, 0, 0]} />
                <Bar dataKey="Vorjahr" fill={COLORS.vorjahr} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* ── Komponenten (Speicher, WP, E-Auto, BKW) ── */}
      {(data.hat_speicher || data.hat_waermepumpe || data.hat_emobilitaet || data.hat_balkonkraftwerk) && (
        <Card>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Komponenten
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {data.hat_speicher && (
              <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Battery className="h-5 w-5 text-blue-500" />
                  <span className="font-medium text-gray-900 dark:text-white">Speicher</span>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Ladung:</span>
                    <span className="font-medium">{fmt(data.speicher_ladung_kwh)} kWh</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Entladung:</span>
                    <span className="font-medium">{fmt(data.speicher_entladung_kwh)} kWh</span>
                  </div>
                  {data.speicher_ladung_kwh !== null && data.speicher_entladung_kwh !== null && (
                    <div className="flex justify-between pt-1 border-t border-blue-100 dark:border-blue-800">
                      <span className="text-gray-500">Effizienz:</span>
                      <FormelTooltip
                        formel="Entladung ÷ Ladung × 100"
                        berechnung={`${fmtCalc(data.speicher_entladung_kwh, 0)} kWh ÷ ${fmtCalc(data.speicher_ladung_kwh, 0)} kWh × 100`}
                        ergebnis={`= ${fmtCalc(data.speicher_entladung_kwh / data.speicher_ladung_kwh * 100, 1)} %`}
                      >
                        <span className="font-medium">{fmt(data.speicher_entladung_kwh / data.speicher_ladung_kwh * 100, 0)}%</span>
                      </FormelTooltip>
                    </div>
                  )}
                </div>
              </div>
            )}

            {data.hat_waermepumpe && (
              <div className="bg-orange-50 dark:bg-orange-900/20 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Flame className="h-5 w-5 text-orange-500" />
                  <span className="font-medium text-gray-900 dark:text-white">Wärmepumpe Summe</span>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Strom:</span>
                    <span className="font-medium">{fmt(data.wp_strom_kwh)} kWh</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Wärme:</span>
                    <span className="font-medium">{fmt(data.wp_waerme_kwh)} kWh</span>
                  </div>
                  {(data.wp_heizung_kwh ?? 0) > 0 && (
                    <div className="flex justify-between pl-3 text-gray-400">
                      <span>Heizung:</span>
                      <span>{fmt(data.wp_heizung_kwh)} kWh</span>
                    </div>
                  )}
                  {(data.wp_warmwasser_kwh ?? 0) > 0 && (
                    <div className="flex justify-between pl-3 text-gray-400">
                      <span>Warmwasser:</span>
                      <span>{fmt(data.wp_warmwasser_kwh)} kWh</span>
                    </div>
                  )}
                  {data.wp_strom_kwh && data.wp_waerme_kwh && (
                    <div className="flex justify-between pt-1 border-t border-orange-100 dark:border-orange-800">
                      <span className="text-gray-500">COP:</span>
                      <FormelTooltip
                        formel="Wärme ÷ Strom"
                        berechnung={`${fmtCalc(data.wp_waerme_kwh, 0)} kWh ÷ ${fmtCalc(data.wp_strom_kwh, 0)} kWh`}
                        ergebnis={`= ${fmtCalc(data.wp_waerme_kwh / data.wp_strom_kwh, 2)}`}
                      >
                        <span className="font-medium">{fmt(data.wp_waerme_kwh / data.wp_strom_kwh)}</span>
                      </FormelTooltip>
                    </div>
                  )}
                </div>
              </div>
            )}

            {data.hat_emobilitaet && (
              <div className="bg-purple-50 dark:bg-purple-900/20 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Car className="h-5 w-5 text-purple-500" />
                  <span className="font-medium text-gray-900 dark:text-white">E-Mobilität</span>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Ladung:</span>
                    <span className="font-medium">{fmt(data.emob_ladung_kwh)} kWh</span>
                  </div>
                  {(data.emob_km ?? 0) > 0 && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Gefahren:</span>
                      <span className="font-medium">{fmt(data.emob_km)} km</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {data.hat_balkonkraftwerk && (
              <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Sun className="h-5 w-5 text-yellow-500" />
                  <span className="font-medium text-gray-900 dark:text-white">Balkonkraftwerk</span>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Erzeugung:</span>
                    <span className="font-medium">{fmt(data.bkw_erzeugung_kwh)} kWh</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* ── Finanzen Chart ── */}
      {finanzData.length > 0 && (
        <Card>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Finanzen
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={finanzData} layout="vertical" margin={{ left: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" unit=" €" />
                  <YAxis type="category" dataKey="name" width={120} />
                  <Tooltip content={<ChartTooltip unit="€" decimals={2} />} />
                  <Bar dataKey="Betrag" name="Betrag" radius={[0, 4, 4, 0]}>
                    {finanzData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="flex flex-col gap-3">
              {/* KPI-Grid: 3 Basis + optionale Komponenten, grid-cols passt sich an */}
              {(() => {
                const hasWP = data.wp_ersparnis_euro !== null
                const hasEmob = data.emob_ersparnis_euro !== null
                const total = 3 + (hasWP ? 1 : 0) + (hasEmob ? 1 : 0)
                // 3 → 3-col | 4 → 2×2 | 5 → 3-col (3+2)
                const gridCols = total === 4 ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-1 sm:grid-cols-3'
                return (
                  <div className={`grid ${gridCols} gap-3`}>
                    <KPICard
                      title="Einspeise-Erlöse"
                      value={data.einspeise_erloes_euro !== null ? fmtEuro(data.einspeise_erloes_euro) : '—'}
                      unit="€" icon={TrendingUp} color="green"
                      formel="Einspeisung × Einspeisevergütung"
                      berechnung={data.einspeisung_kwh !== null ? `${fmtCalc(data.einspeisung_kwh, 1)} kWh` : undefined}
                      ergebnis={data.einspeise_erloes_euro !== null ? `= ${fmtCalc(data.einspeise_erloes_euro, 2)} €` : undefined}
                    />
                    <KPICard
                      title="EV-Ersparnis"
                      value={data.ev_ersparnis_euro !== null ? fmtEuro(data.ev_ersparnis_euro) : '—'}
                      unit="€" icon={Home} color="blue"
                      formel="Eigenverbrauch × Netzbezugspreis"
                      berechnung={data.eigenverbrauch_kwh !== null ? `${fmtCalc(data.eigenverbrauch_kwh, 1)} kWh` : undefined}
                      ergebnis={data.ev_ersparnis_euro !== null ? `= ${fmtCalc(data.ev_ersparnis_euro, 2)} €` : undefined}
                    />
                    <KPICard
                      title="Netzbezug-Kosten"
                      value={data.netzbezug_kosten_euro !== null ? `−${fmt(data.netzbezug_kosten_euro)}` : '—'}
                      unit="€" icon={ArrowDownToLine} color="red"
                      formel="Netzbezug × Netzbezugspreis + Grundpreis"
                      berechnung={data.netzbezug_kwh !== null ? `${fmtCalc(data.netzbezug_kwh, 1)} kWh` : undefined}
                      ergebnis={data.netzbezug_kosten_euro !== null ? `= −${fmtCalc(data.netzbezug_kosten_euro, 2)} €` : undefined}
                    />
                    {hasWP && (
                      <KPICard
                        title="WP-Ersparnis"
                        value={fmtEuro(data.wp_ersparnis_euro)}
                        unit="€" icon={Flame} color="orange"
                        formel="Wärme ÷ 0,9 × Gaspreis − WP-Strom × WP-Strompreis"
                        berechnung={data.wp_waerme_kwh !== null && data.wp_strom_kwh !== null
                          ? `${fmtCalc(data.wp_waerme_kwh, 1)} kWh Wärme, ${fmtCalc(data.wp_strom_kwh, 1)} kWh Strom`
                          : undefined}
                        ergebnis={`= ${fmtCalc(data.wp_ersparnis_euro, 2)} €`}
                      />
                    )}
                    {hasEmob && (
                      <KPICard
                        title="eMob-Ersparnis"
                        value={fmtEuro(data.emob_ersparnis_euro)}
                        unit="€" icon={Car} color="purple"
                        formel="Benzinkosten − Stromkosten (vs. Verbrenner)"
                        berechnung={data.emob_ladung_kwh !== null ? `${fmtCalc(data.emob_ladung_kwh, 1)} kWh geladen` : undefined}
                        ergebnis={`= ${fmtCalc(data.emob_ersparnis_euro, 2)} €`}
                      />
                    )}
                  </div>
                )
              })()}
              {/* Energie-Saldo */}
              {energieSaldo !== null && (() => {
                const formelTeile = ['Einspeise-Erlöse', 'EV-Ersparnis']
                const berechnungTeile = [fmtCalc(data.einspeise_erloes_euro, 2), fmtCalc(data.ev_ersparnis_euro, 2)]
                if (data.wp_ersparnis_euro !== null) { formelTeile.push('WP-Ersparnis'); berechnungTeile.push(fmtCalc(data.wp_ersparnis_euro, 2)) }
                if (data.emob_ersparnis_euro !== null) { formelTeile.push('eMob-Ersparnis'); berechnungTeile.push(fmtCalc(data.emob_ersparnis_euro, 2)) }
                const formel = formelTeile.join(' + ') + ' − Netzbezug-Kosten'
                const berechnung = berechnungTeile.join(' + ') + ` − ${fmtCalc(data.netzbezug_kosten_euro, 2)} €`
                return (
                  <Card>
                    <div className="flex flex-col items-center justify-center py-2">
                      <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">Energie-Saldo</p>
                      <FormelTooltip formel={formel} berechnung={berechnung} ergebnis={`= ${fmtCalc(energieSaldo, 2)} €`}>
                        <span className={`text-4xl font-bold ${energieSaldo >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                          {fmtEuro(energieSaldo)}
                        </span>
                      </FormelTooltip>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 text-center">
                        {formelTeile.join(' + ')} − Netzbezug
                      </p>
                    </div>
                  </Card>
                )
              })()}
            </div>
          </div>
        </Card>
      )}

      {/* ── SOLL/IST-Vergleich ── */}
      {sollIstData.length > 0 && (
        <Card>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            SOLL/IST-Vergleich (PVGIS)
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sollIstData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis tickFormatter={sollIstFormatter} width={90} />
                  <Tooltip content={<ChartTooltip unit="kWh" />} />
                  <Legend />
                  <Bar dataKey="IST" fill={COLORS.erzeugung} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="SOLL" fill={COLORS.soll} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="flex items-center justify-center">
              <div className="text-center">
                <p className="text-sm text-gray-500 mb-2">Erfüllungsgrad</p>
                <FormelTooltip
                  formel="IST ÷ SOLL × 100"
                  berechnung={`${fmtCalc(data.pv_erzeugung_kwh, 0)} kWh ÷ ${fmtCalc(data.soll_pv_kwh, 0)} kWh × 100`}
                  ergebnis={`= ${fmtCalc(data.pv_erzeugung_kwh! / data.soll_pv_kwh! * 100, 1)} %`}
                >
                  <p className={`text-5xl font-bold ${data.pv_erzeugung_kwh! >= data.soll_pv_kwh! ? 'text-green-500' : 'text-orange-500'}`}>
                    {fmt(data.pv_erzeugung_kwh! / data.soll_pv_kwh! * 100, 0)}%
                  </p>
                </FormelTooltip>
                <p className="text-sm text-gray-400 mt-2">
                  {fmt(data.pv_erzeugung_kwh)} von {fmt(data.soll_pv_kwh)} kWh
                </p>
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}
