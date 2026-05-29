/**
 * Wärmepumpe
 * Zeigt Statistiken: COP, Stromverbrauch, Heizenergie, Ersparnis vs. Gas/Öl
 */

import { Fragment, useState, useEffect } from 'react'
import { Flame, Zap, Leaf, TrendingUp, Thermometer, Power, PieChart as PieChartIcon, BarChart3, Calendar, Table, Timer } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard, SortableSection, OrderedSections } from '../components/ui'
import ChartTooltip from '../components/ui/ChartTooltip'
import { useSelectedAnlage, useSectionOrder } from '../hooks'
import type { Anlage } from '../types'
import { MONAT_KURZ, fmtKpi, SAISON_FENSTER } from '../lib'
import { investitionenApi } from '../api'
import type { WaermepumpeDashboardResponse } from '../api/investitionen'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area, LabelList
} from 'recharts'

export default function WaermepumpeDashboard() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const [dashboards, setDashboards] = useState<WaermepumpeDashboardResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedAnlageId) return

    const loadDashboard = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await investitionenApi.getWaermepumpeDashboard(selectedAnlageId)
        setDashboards(data)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden')
      } finally {
        setLoading(false)
      }
    }

    loadDashboard()
  }, [selectedAnlageId])

  if (anlagenLoading) return <LoadingSpinner text="Lade..." />

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Wärmepumpe</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  const showSelector = anlagen.length > 1
  const selectorProps = {
    anlagen,
    selectedAnlageId,
    setSelectedAnlageId,
  }

  return (
    <div className="space-y-6">
      {error && <Alert type="error">{error}</Alert>}

      {loading ? (
        <LoadingSpinner text="Lade Wärmepumpe Daten..." />
      ) : dashboards.length === 0 ? (
        <>
          <PlaceholderHeader showSelector={showSelector} {...selectorProps} />
          <Card>
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <Flame className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Keine Wärmepumpe für diese Anlage erfasst.</p>
              <p className="text-sm mt-2">Füge eine Wärmepumpe unter "Investitionen" hinzu.</p>
            </div>
          </Card>
        </>
      ) : (
        dashboards.map((dashboard, idx) => (
          <Fragment key={dashboard.investition.id}>
            {idx > 0 && <hr className="border-t border-gray-200 dark:border-gray-700" />}
            <WaermepumpeBlock
              dashboard={dashboard}
              showSelector={idx === 0 && showSelector}
              {...selectorProps}
            />
          </Fragment>
        ))
      )}
    </div>
  )
}

interface SelectorProps {
  anlagen: Anlage[]
  selectedAnlageId: number | undefined
  setSelectedAnlageId: (id: number) => void
  showSelector: boolean
}

function AnlageSelector({ anlagen, selectedAnlageId, setSelectedAnlageId, showSelector }: SelectorProps) {
  if (!showSelector) return null
  return (
    <Select
      compact
      value={selectedAnlageId?.toString() || ''}
      onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
      options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
    />
  )
}

function PlaceholderHeader(props: SelectorProps) {
  return (
    <div className="flex items-center justify-between flex-wrap gap-4">
      <div className="flex items-center gap-3 min-w-0">
        <Flame className="h-8 w-8 text-orange-500 flex-shrink-0" />
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white truncate">Wärmepumpe</h1>
      </div>
      <AnlageSelector {...props} />
    </div>
  )
}

const DEFAULT_WP_SECTION_ORDER = [
  'waermeverteilung', 'kostenvergleich', 'monatsverlauf', 'monatsvergleich', 'co2', 'details',
] as const

function WaermepumpeBlock({ dashboard, ...selectorProps }: { dashboard: WaermepumpeDashboardResponse } & SelectorProps) {
  const { investition, monatsdaten, zusammenfassung } = dashboard
  const z = zusammenfassung
  const { order: sectionOrder, moveSection } = useSectionOrder(
    `cockpit-wp-${investition.id}_section_order`,
    DEFAULT_WP_SECTION_ORDER,
  )
  const wpStoragePrefix = `cockpit-wp-${investition.id}`

  const hatGetrennteStrom = z.cop_heizen !== undefined

  const monthlyData = monatsdaten.map(md => {
    const d = md.verbrauch_daten
    const strom = d.stromverbrauch_kwh || 0
    const heizung = d.heizenergie_kwh || 0
    const warmwasser = d.warmwasser_kwh || 0
    const stromHeizen = d.strom_heizen_kwh || 0
    const stromWarmwasser = d.strom_warmwasser_kwh || 0
    return {
      name: `${MONAT_KURZ[md.monat]} ${md.jahr.toString().slice(2)}`,
      strom,
      strom_heizen: stromHeizen,
      strom_warmwasser: stromWarmwasser,
      heizung,
      warmwasser,
      cop: (heizung + warmwasser) / (strom || 1),
      cop_heizen: stromHeizen > 0 ? heizung / stromHeizen : null,
      cop_warmwasser: stromWarmwasser > 0 ? warmwasser / stromWarmwasser : null,
    }
  })

  // Monatsvergleich über Jahre: Jan/Feb/...Dez als Gruppen, je ein Balken pro Jahr
  const [vergleichModus, setVergleichModus] = useState<'jaz' | 'strom'>('strom')
  const vergleichJahre = [...new Set(monatsdaten.map(md => md.jahr))].sort()
  const vergleichJahreColors = ['#f59e0b', '#22c55e', '#3b82f6', '#ef4444', '#8b5cf6']
  const vergleichData = Array.from({ length: 12 }, (_, i) => {
    const monat = i + 1
    const entry: Record<string, string | number | null> = { name: MONAT_KURZ[monat] }
    for (const jahr of vergleichJahre) {
      const md = monatsdaten.find(m => m.monat === monat && m.jahr === jahr)
      if (md) {
        const waerme = (md.verbrauch_daten.heizenergie_kwh || 0) + (md.verbrauch_daten.warmwasser_kwh || 0)
        const strom = md.verbrauch_daten.stromverbrauch_kwh || 0
        if (vergleichModus === 'jaz') {
          entry[`val_${jahr}`] = strom > 0 ? Math.round(waerme / strom * 100) / 100 : null
        } else {
          entry[`val_${jahr}`] = strom > 0 ? Math.round(strom) : null
        }
      } else {
        entry[`val_${jahr}`] = null
      }
    }
    return entry
  })

  // Saison-Modus: Fokus-Fenster (Winter/Heizperiode/Sommer) über die gesamte
  // Lebensdauer zu Saison-Instanzen aggregiert. Kein Jahresfilter (#195:
  // Cockpit-vs-Auswertung-Grenze) — der Achsen-Toggle wechselt nur die Sicht.
  const [vergleichAchse, setVergleichAchse] = useState<'monate' | 'saison'>('monate')
  const [saisonFenster, setSaisonFenster] = useState<keyof typeof SAISON_FENSTER>('winter')
  const saisonCfg = SAISON_FENSTER[saisonFenster]
  const saisonSpanntJahr = saisonCfg.monate.some(m => m < saisonCfg.startMonat)
  const saisonData = (() => {
    if (vergleichJahre.length === 0) return []
    const minJ = vergleichJahre[0]
    const maxJ = vergleichJahre[vergleichJahre.length - 1]
    const rows: { name: string; value: number | null; label: string; vollstaendig: boolean }[] = []
    for (let startJahr = minJ - 1; startJahr <= maxJ; startJahr++) {
      let sumStrom = 0
      let sumWaerme = 0
      let monateMitDaten = 0
      for (const m of saisonCfg.monate) {
        const kalenderJahr = m >= saisonCfg.startMonat ? startJahr : startJahr + 1
        const md = monatsdaten.find(x => x.monat === m && x.jahr === kalenderJahr)
        if (md) {
          monateMitDaten++
          // #195 / rapahl-PN: bei getrennter Strommessung saisonbereinigt
          // rechnen — nur Heizung. Warmwasser läuft ganzjährig ~konstant
          // und würde den Saison-Vergleich verwässern.
          if (hatGetrennteStrom) {
            sumStrom += md.verbrauch_daten.strom_heizen_kwh || 0
            sumWaerme += md.verbrauch_daten.heizenergie_kwh || 0
          } else {
            sumStrom += md.verbrauch_daten.stromverbrauch_kwh || 0
            sumWaerme += (md.verbrauch_daten.heizenergie_kwh || 0) + (md.verbrauch_daten.warmwasser_kwh || 0)
          }
        }
      }
      if (monateMitDaten === 0) continue
      const vollstaendig = monateMitDaten === saisonCfg.monate.length
      const basisName = saisonSpanntJahr
        ? `${String(startJahr % 100).padStart(2, '0')}/${String((startJahr + 1) % 100).padStart(2, '0')}`
        : `${startJahr}`
      const wert = vergleichModus === 'jaz'
        ? (sumStrom > 0 ? Math.round((sumWaerme / sumStrom) * 100) / 100 : null)
        : Math.round(sumStrom)
      rows.push({
        name: vollstaendig ? basisName : `${basisName} (${monateMitDaten}/${saisonCfg.monate.length})`,
        value: wert,
        label: wert == null ? '' : (vergleichModus === 'jaz' ? wert.toFixed(2) : wert.toLocaleString('de-DE')),
        vollstaendig,
      })
    }
    return rows
  })()

  const waermePieData = [
    { name: 'Heizung', value: z.gesamt_heizenergie_kwh },
    { name: 'Warmwasser', value: z.gesamt_warmwasser_kwh },
  ]

  const kostenVergleichData = [
    { name: 'Wärmepumpe', value: z.wp_kosten_euro, fill: '#22c55e' },
    { name: 'Gas/Öl', value: z.alte_heizung_kosten_euro, fill: '#ef4444' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <Flame className="h-8 w-8 text-orange-500 flex-shrink-0" />
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white truncate">
              {investition.bezeichnung}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {z.anzahl_monate} Monate Daten
            </p>
          </div>
        </div>
        <AnlageSelector {...selectorProps} />
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        <KPICard
          title="JAZ"
          value={fmtKpi(z.durchschnitt_cop, 2)}
          icon={Thermometer}
          color="orange"
          formel="JAZ = Wärme ÷ Strom (Gesamtlaufzeit)"
          berechnung={`${z.gesamt_waerme_kwh.toFixed(0)} kWh ÷ ${z.gesamt_stromverbrauch_kwh.toFixed(0)} kWh`}
          ergebnis={z.durchschnitt_cop ? `= ${z.durchschnitt_cop.toFixed(2)}` : '—'}
        />
        <KPICard
          title="Wärme erzeugt"
          value={fmtKpi(z.gesamt_waerme_kwh / 1000, 1)}
          unit="MWh"
          icon={Flame}
          color="red"
          formel="Wärme = Heizung + Warmwasser"
          berechnung={`${z.gesamt_heizenergie_kwh.toFixed(0)} + ${z.gesamt_warmwasser_kwh.toFixed(0)} kWh`}
          ergebnis={`= ${z.gesamt_waerme_kwh.toFixed(0)} kWh`}
        />
        <KPICard
          title="Strom verbraucht"
          value={fmtKpi(z.gesamt_stromverbrauch_kwh / 1000, 1)}
          unit="MWh"
          icon={Zap}
          color="yellow"
          formel="Σ Stromverbrauch WP"
          berechnung={`${z.gesamt_stromverbrauch_kwh.toFixed(0)} kWh`}
          ergebnis={`= ${(z.gesamt_stromverbrauch_kwh / 1000).toFixed(2)} MWh`}
        />
        <KPICard
          title="Ersparnis vs. Gas"
          value={fmtKpi(z.ersparnis_euro, 0)}
          unit="€"
          icon={TrendingUp}
          color="green"
          trend={z.ersparnis_euro > 0 ? 'up' : undefined}
          formel="Ersparnis = Gas/Öl-Kosten − WP-Kosten"
          berechnung={`${z.alte_heizung_kosten_euro.toFixed(0)} € − ${z.wp_kosten_euro.toFixed(0)} €`}
          ergebnis={`= ${z.ersparnis_euro.toFixed(2)} €`}
        />
      </div>
      {/* Getrennte JAZ-Anzeige (wenn separate Strommessung) */}
      {hatGetrennteStrom && (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
          <KPICard
            title="JAZ Heizen"
            value={fmtKpi(z.cop_heizen, 2)}
            icon={Thermometer}
            color="orange"
            formel="JAZ Heizen = Heizwärme ÷ Strom Heizen"
            berechnung={`${z.gesamt_heizung_getrennt_kwh?.toFixed(0)} kWh ÷ ${z.gesamt_strom_heizen_kwh?.toFixed(0)} kWh`}
            ergebnis={z.cop_heizen ? `= ${z.cop_heizen.toFixed(2)}` : '—'}
          />
          <KPICard
            title="JAZ Warmwasser"
            value={fmtKpi(z.cop_warmwasser, 2)}
            icon={Thermometer}
            color="orange"
            formel="JAZ WW = Warmwasser ÷ Strom WW"
            berechnung={`${z.gesamt_warmwasser_getrennt_kwh?.toFixed(0)} kWh ÷ ${z.gesamt_strom_warmwasser_kwh?.toFixed(0)} kWh`}
            ergebnis={(z.cop_warmwasser && z.cop_warmwasser > 0) ? `= ${z.cop_warmwasser.toFixed(2)}` : '—'}
          />
          <KPICard
            title="Strom Heizen"
            value={fmtKpi(z.gesamt_strom_heizen_kwh ? z.gesamt_strom_heizen_kwh / 1000 : null, 1)}
            unit="MWh"
            icon={Zap}
            color="yellow"
          />
          <KPICard
            title="Strom Warmwasser"
            value={fmtKpi(z.gesamt_strom_warmwasser_kwh ? z.gesamt_strom_warmwasser_kwh / 1000 : null, 1)}
            unit="MWh"
            icon={Zap}
            color="yellow"
          />
        </div>
      )}
      <p className="text-xs text-gray-400 dark:text-gray-500 italic -mt-2">
        JAZ = Jahresarbeitszahl über die gesamte Laufzeit ({z.anzahl_monate} Monate). Jahresweise Auswertung unter Auswertungen → Komponenten.
      </p>

      {/* Kompressor-Starts + Betriebsstunden (nur wenn Counter-Sensoren
          zugeordnet sind). #238/#290 (detLAN-Kompromiss): Hauptwert = seit
          Anschaffung von eedc erfasst (Anzeige ab Anschaffungsdatum limitiert);
          der rohe Lebensdauer-Zählerstand des Hersteller-Counters steht der
          Vollständigkeit halber im Tooltip. Drift wird im Daten-Checker
          ausgewiesen. Die zwei abgeleiteten KPIs „Ø Laufzeit pro Start" und
          „Starts pro Betriebsstunde" sind nur sichtbar, wenn beide Sensoren
          gepflegt sind und rechnen mit den seit-Anschaffung erfassten Summen. */}
      {((z.kompressor_starts_gesamt != null && z.kompressor_starts_gesamt > 0) ||
        (z.betriebsstunden_gesamt != null && z.betriebsstunden_gesamt > 0)) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
          {z.kompressor_starts_gesamt != null && z.kompressor_starts_gesamt > 0 && (
            <KPICard
              title="Kompressor-Starts"
              value={(z.kompressor_starts_summe_erfasst ?? 0).toLocaleString('de-DE')}
              icon={Power}
              color="gray"
              subtitle={z.kompressor_starts_max_tag != null ? `Max/Tag: ${z.kompressor_starts_max_tag}` : undefined}
              formel="Von eedc erfasst seit Anschaffung (Σ Tagesinkremente)"
              berechnung={`Zählerstand (Lebensdauer): ${z.kompressor_starts_gesamt.toLocaleString('de-DE')} · Max/Tag: ${z.kompressor_starts_max_tag ?? '—'}`}
              ergebnis={`= ${(z.kompressor_starts_summe_erfasst ?? 0).toLocaleString('de-DE')} Starts seit Anschaffung`}
            />
          )}
          {z.betriebsstunden_gesamt != null && z.betriebsstunden_gesamt > 0 && (
            <KPICard
              title="Betriebsstunden"
              value={(z.betriebsstunden_summe_erfasst ?? 0).toLocaleString('de-DE', { maximumFractionDigits: 0 })}
              unit="h"
              icon={Timer}
              color="gray"
              subtitle={z.betriebsstunden_max_tag != null ? `Max/Tag: ${z.betriebsstunden_max_tag} h` : undefined}
              formel="Von eedc erfasst seit Anschaffung (Σ Tagesinkremente)"
              berechnung={`Zählerstand (Lebensdauer): ${z.betriebsstunden_gesamt.toLocaleString('de-DE', { maximumFractionDigits: 0 })} h · Max/Tag: ${z.betriebsstunden_max_tag ?? '—'} h`}
              ergebnis={`= ${(z.betriebsstunden_summe_erfasst ?? 0).toLocaleString('de-DE', { maximumFractionDigits: 0 })} h seit Anschaffung`}
            />
          )}
          {z.oe_laufzeit_pro_start_h != null && (
            <KPICard
              title="Ø Laufzeit pro Start"
              value={z.oe_laufzeit_pro_start_h.toLocaleString('de-DE', { maximumFractionDigits: 2 })}
              unit="h"
              icon={Timer}
              color="blue"
              formel="Betriebsstunden ÷ Kompressor-Starts (seit Anschaffung)"
              berechnung={`${z.betriebsstunden_summe_erfasst?.toLocaleString('de-DE', { maximumFractionDigits: 0 })} h ÷ ${z.kompressor_starts_summe_erfasst?.toLocaleString('de-DE')}`}
              ergebnis={`= ${z.oe_laufzeit_pro_start_h.toLocaleString('de-DE', { maximumFractionDigits: 2 })} h/Start`}
            />
          )}
          {z.starts_pro_betriebsstunde != null && (
            <KPICard
              title="Starts pro Betriebsstunde"
              value={z.starts_pro_betriebsstunde.toLocaleString('de-DE', { maximumFractionDigits: 3 })}
              icon={Power}
              color="blue"
              formel="Kompressor-Starts ÷ Betriebsstunden (seit Anschaffung)"
              berechnung={`${z.kompressor_starts_summe_erfasst?.toLocaleString('de-DE')} ÷ ${z.betriebsstunden_summe_erfasst?.toLocaleString('de-DE', { maximumFractionDigits: 0 })} h`}
              ergebnis={`= ${z.starts_pro_betriebsstunde.toLocaleString('de-DE', { maximumFractionDigits: 3 })} / h`}
            />
          )}
        </div>
      )}

      <OrderedSections order={sectionOrder} onMove={moveSection} className="space-y-3">

      {/* Wärme-Verteilung */}
      <SortableSection
        sectionId="waermeverteilung"
        storageKeyPrefix={wpStoragePrefix}
        icon={PieChartIcon}
        color="text-red-500"
        title="Wärme-Verteilung"
        summary={`Heizung ${z.gesamt_heizenergie_kwh.toFixed(0)} kWh · Warmwasser ${z.gesamt_warmwasser_kwh.toFixed(0)} kWh`}
        defaultOpen
      >
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={waermePieData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={80}
                paddingAngle={5}
                dataKey="value"
                label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
              >
                <Cell fill="#ef4444" />
                <Cell fill="#3b82f6" />
              </Pie>
              <Tooltip content={<ChartTooltip unit="kWh" />} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex justify-center gap-6 text-sm">
          <span className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-red-500"></span>
            Heizung: {z.gesamt_heizenergie_kwh.toFixed(0)} kWh
          </span>
          <span className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-blue-500"></span>
            Warmwasser: {z.gesamt_warmwasser_kwh.toFixed(0)} kWh
          </span>
        </div>
      </SortableSection>

      {/* Kostenvergleich */}
      <SortableSection
        sectionId="kostenvergleich"
        storageKeyPrefix={wpStoragePrefix}
        icon={TrendingUp}
        color="text-green-500"
        title="Kostenvergleich WP vs. Gas/Öl"
        summary={`Ersparnis ${z.ersparnis_euro.toFixed(0)} €`}
        defaultOpen
      >
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={kostenVergleichData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" tickFormatter={(v) => `${v}€`} />
              <YAxis type="category" dataKey="name" width={110} />
              <Tooltip content={<ChartTooltip unit="€" decimals={2} />} />
              <Bar dataKey="value" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="text-center mt-2">
          <span className="text-lg font-semibold text-green-600 dark:text-green-400">
            Ersparnis: {z.ersparnis_euro.toFixed(2)} €
          </span>
        </div>
      </SortableSection>

      {/* Wärme pro Monat */}
      <SortableSection
        sectionId="monatsverlauf"
        storageKeyPrefix={wpStoragePrefix}
        icon={BarChart3}
        color="text-orange-500"
        title="Wärmeerzeugung pro Monat"
        summary={`${monatsdaten.length} Monate`}
        defaultOpen
      >
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={monthlyData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" fontSize={10} />
              <YAxis label={{ value: 'kWh', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' } }} />
              <Tooltip content={<ChartTooltip unit="kWh" />} />
              <Legend />
              <Area type="monotone" dataKey="heizung" stackId="1" fill="#ef4444" stroke="#dc2626" name="Heizung" />
              <Area type="monotone" dataKey="warmwasser" stackId="1" fill="#3b82f6" stroke="#2563eb" name="Warmwasser" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </SortableSection>

      {/* Monatsvergleich über Jahre – mit Toggle */}
      <SortableSection
        sectionId="monatsvergleich"
        storageKeyPrefix={wpStoragePrefix}
        icon={Calendar}
        color="text-purple-500"
        title={`${vergleichModus === 'jaz' ? 'JAZ' : 'Stromverbrauch'} ${vergleichAchse === 'saison' ? 'Saisonvergleich' : 'Monatsvergleich'}`}
        summary={vergleichJahre.length > 1 ? `${vergleichJahre[0]}–${vergleichJahre[vergleichJahre.length - 1]}` : `${vergleichJahre[0] ?? ''}`}
        defaultOpen
      >
        <div className="flex items-center justify-end flex-wrap gap-2 mb-4">
          {/* Metrik: Strom / JAZ */}
          <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 text-sm overflow-hidden">
            <button
              onClick={() => setVergleichModus('strom')}
              className={`px-3 py-1 transition-colors ${vergleichModus === 'strom' ? 'bg-yellow-500 text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
            >
              Strom (kWh)
            </button>
            <button
              onClick={() => setVergleichModus('jaz')}
              className={`px-3 py-1 transition-colors ${vergleichModus === 'jaz' ? 'bg-orange-500 text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
            >
              JAZ
            </button>
          </div>
          {/* Achse: Monate / Saison */}
          <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 text-sm overflow-hidden">
            <button
              onClick={() => setVergleichAchse('monate')}
              className={`px-3 py-1 transition-colors ${vergleichAchse === 'monate' ? 'bg-purple-500 text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
            >
              Monate
            </button>
            <button
              onClick={() => setVergleichAchse('saison')}
              className={`px-3 py-1 transition-colors ${vergleichAchse === 'saison' ? 'bg-purple-500 text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
            >
              Saison
            </button>
          </div>
          {/* Saison-Fenster — nur im Saison-Modus */}
          {vergleichAchse === 'saison' && (
            <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 text-sm overflow-hidden">
              {(Object.keys(SAISON_FENSTER) as (keyof typeof SAISON_FENSTER)[]).map(key => (
                <button
                  key={key}
                  onClick={() => setSaisonFenster(key)}
                  title={`${SAISON_FENSTER[key].label} (${SAISON_FENSTER[key].bereich})`}
                  className={`px-3 py-1 transition-colors ${saisonFenster === key ? 'bg-purple-500 text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
                >
                  {SAISON_FENSTER[key].label}
                </button>
              ))}
            </div>
          )}
        </div>
        {vergleichAchse === 'saison' && saisonData.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-16">
            Keine Daten im Fenster {saisonCfg.label} ({saisonCfg.bereich}).
          </p>
        ) : (
          <div className="h-72 text-gray-700 dark:text-gray-200">
            <ResponsiveContainer width="100%" height="100%">
              {vergleichAchse === 'monate' ? (
                <BarChart data={vergleichData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" fontSize={12} />
                  <YAxis domain={vergleichModus === 'jaz' ? [0, 6] : undefined} />
                  <Tooltip content={<ChartTooltip formatter={(v) => vergleichModus === 'jaz' ? v?.toFixed(2) : `${v} kWh`} />} />
                  <Legend />
                  {vergleichJahre.map((jahr, i) => (
                    <Bar
                      key={jahr}
                      dataKey={`val_${jahr}`}
                      name={`${jahr}`}
                      fill={vergleichJahreColors[i % vergleichJahreColors.length]}
                    />
                  ))}
                </BarChart>
              ) : (
                <BarChart data={saisonData} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" fontSize={12} />
                  <YAxis domain={vergleichModus === 'jaz' ? [0, 6] : undefined} />
                  <Tooltip content={<ChartTooltip formatter={(v) => vergleichModus === 'jaz' ? v?.toFixed(2) : `${v} kWh`} />} />
                  <Bar dataKey="value" name={vergleichModus === 'jaz' ? 'JAZ' : 'Strom'}>
                    {saisonData.map((s, i) => (
                      <Cell
                        key={i}
                        fill={vergleichJahreColors[i % vergleichJahreColors.length]}
                        fillOpacity={s.vollstaendig ? 1 : 0.4}
                      />
                    ))}
                    <LabelList dataKey="label" position="top" fill="currentColor" fontSize={13} fontWeight={600} />
                  </Bar>
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        )}
        {vergleichAchse === 'saison' && saisonData.length > 0 && (
          <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
            {saisonCfg.label}: {saisonCfg.bereich} ({saisonCfg.monate.length} Monate).{' '}
            {hatGetrennteStrom
              ? 'Saison-Strom = nur Heizung (Warmwasser ausgeklammert, getrennte Strommessung).'
              : 'Saison-Strom inkl. Warmwasser — keine getrennte Strommessung erfasst.'}{' '}
            Blasse Balken kennzeichnen eine unvollständige Saison.
          </p>
        )}
      </SortableSection>

      {/* CO2 Info */}
      <SortableSection
        sectionId="co2"
        storageKeyPrefix={wpStoragePrefix}
        icon={Leaf}
        color="text-green-500"
        title="CO₂-Ersparnis"
        summary={`${z.co2_ersparnis_kg.toFixed(0)} kg vs. fossile Heizung`}
        defaultOpen
      >
        <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4 flex items-center gap-4">
          <Leaf className="h-8 w-8 text-green-500" />
          <div>
            <p className="text-sm text-green-600 dark:text-green-400">CO₂ Ersparnis gegenüber fossiler Heizung</p>
            <p className="text-2xl font-bold text-green-700 dark:text-green-300">
              {z.co2_ersparnis_kg.toFixed(0)} kg
            </p>
          </div>
        </div>
      </SortableSection>

      {/* Detail-Tabelle */}
      <SortableSection
        sectionId="details"
        storageKeyPrefix={wpStoragePrefix}
        icon={Table}
        color="text-gray-500"
        title="Monatsdaten"
        summary={`${monatsdaten.length} Einträge`}
      >
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-2 px-2">Monat</th>
                <th className="text-right py-2 px-2">Strom (kWh)</th>
                <th className="text-right py-2 px-2">Heizung (kWh)</th>
                <th className="text-right py-2 px-2">Warmwasser (kWh)</th>
                <th className="text-right py-2 px-2">JAZ</th>
              </tr>
            </thead>
            <tbody>
              {monatsdaten.map((md) => {
                const strom = md.verbrauch_daten.stromverbrauch_kwh || 0
                const heiz = md.verbrauch_daten.heizenergie_kwh || 0
                const ww = md.verbrauch_daten.warmwasser_kwh || 0
                const cop = strom > 0 ? (heiz + ww) / strom : 0
                return (
                  <tr key={md.id} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="py-2 px-2">{MONAT_KURZ[md.monat]} {md.jahr}</td>
                    <td className="text-right py-2 px-2">{strom.toFixed(0)}</td>
                    <td className="text-right py-2 px-2 text-red-600">{heiz.toFixed(0)}</td>
                    <td className="text-right py-2 px-2 text-blue-600">{ww.toFixed(0)}</td>
                    <td className="text-right py-2 px-2 text-orange-600">{cop.toFixed(2)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </SortableSection>

      </OrderedSections>
    </div>
  )
}
