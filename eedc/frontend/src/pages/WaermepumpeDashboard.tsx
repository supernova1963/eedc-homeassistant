/**
 * Wärmepumpe
 * Zeigt Statistiken: COP, Stromverbrauch, Heizenergie, Ersparnis vs. Gas/Öl
 */

import { Fragment, useState, useEffect } from 'react'
import { Flame, Leaf, TrendingUp, Power, PieChart as PieChartIcon, BarChart3, Calendar, Table, Timer } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard, SortableSection, OrderedSections } from '../components/ui'
import ChartTooltip from '../components/ui/ChartTooltip'
import { useSelectedAnlage, useSectionOrder } from '../hooks'
import type { Anlage } from '../types'
import { fmtKpi, WP_KPI, CHART_COLORS } from '../lib'
import { investitionenApi } from '../api'
import type { WaermepumpeDashboardResponse } from '../api/investitionen'
import { WaermepumpeVergleich, WaermepumpeMonatsverlauf, WaermepumpeKostenvergleich, WaermepumpeMonatsTabelle } from '../components/waermepumpe'
import { Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'

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

  const waermePieData = [
    { name: 'Heizung', value: z.gesamt_heizenergie_kwh },
    { name: 'Warmwasser', value: z.gesamt_warmwasser_kwh },
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
          {...WP_KPI.jaz}
          value={fmtKpi(z.durchschnitt_cop, 2)}
          formel="JAZ = Wärme ÷ Strom (Gesamtlaufzeit)"
          berechnung={`${z.gesamt_waerme_kwh.toFixed(0)} kWh ÷ ${z.gesamt_stromverbrauch_kwh.toFixed(0)} kWh`}
          ergebnis={z.durchschnitt_cop ? `= ${z.durchschnitt_cop.toFixed(2)}` : '—'}
        />
        <KPICard
          {...WP_KPI.waerme}
          value={fmtKpi(z.gesamt_waerme_kwh / 1000, 1)}
          unit="MWh"
          formel="Wärme = Heizung + Warmwasser"
          berechnung={`${z.gesamt_heizenergie_kwh.toFixed(0)} + ${z.gesamt_warmwasser_kwh.toFixed(0)} kWh`}
          ergebnis={`= ${z.gesamt_waerme_kwh.toFixed(0)} kWh`}
        />
        <KPICard
          {...WP_KPI.strom}
          value={fmtKpi(z.gesamt_stromverbrauch_kwh / 1000, 1)}
          unit="MWh"
          formel="Σ Stromverbrauch WP"
          berechnung={`${z.gesamt_stromverbrauch_kwh.toFixed(0)} kWh`}
          ergebnis={`= ${(z.gesamt_stromverbrauch_kwh / 1000).toFixed(2)} MWh`}
        />
        <KPICard
          {...WP_KPI.ersparnis}
          value={fmtKpi(z.ersparnis_euro, 0)}
          unit="€"
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
            {...WP_KPI.jaz}
            title="JAZ Heizen"
            value={fmtKpi(z.cop_heizen, 2)}
            formel="JAZ Heizen = Heizwärme ÷ Strom Heizen"
            berechnung={`${z.gesamt_heizung_getrennt_kwh?.toFixed(0)} kWh ÷ ${z.gesamt_strom_heizen_kwh?.toFixed(0)} kWh`}
            ergebnis={z.cop_heizen ? `= ${z.cop_heizen.toFixed(2)}` : '—'}
          />
          <KPICard
            {...WP_KPI.jaz}
            title="JAZ Warmwasser"
            value={fmtKpi(z.cop_warmwasser, 2)}
            formel="JAZ WW = Warmwasser ÷ Strom WW"
            berechnung={`${z.gesamt_warmwasser_getrennt_kwh?.toFixed(0)} kWh ÷ ${z.gesamt_strom_warmwasser_kwh?.toFixed(0)} kWh`}
            ergebnis={(z.cop_warmwasser && z.cop_warmwasser > 0) ? `= ${z.cop_warmwasser.toFixed(2)}` : '—'}
          />
          <KPICard
            {...WP_KPI.strom}
            title="Strom Heizen"
            value={fmtKpi(z.gesamt_strom_heizen_kwh ? z.gesamt_strom_heizen_kwh / 1000 : null, 1)}
            unit="MWh"
          />
          <KPICard
            {...WP_KPI.strom}
            title="Strom Warmwasser"
            value={fmtKpi(z.gesamt_strom_warmwasser_kwh ? z.gesamt_strom_warmwasser_kwh / 1000 : null, 1)}
            unit="MWh"
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
                label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)} %`}
              >
                <Cell fill={CHART_COLORS.wpWaerme} />
                <Cell fill={CHART_COLORS.wpWarmwasser} />
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
        <WaermepumpeKostenvergleich zusammenfassung={z} />
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
        <WaermepumpeMonatsverlauf monatsdaten={monatsdaten} />
      </SortableSection>

      {/* Monatsvergleich über Jahre – mit Toggle */}
      <SortableSection
        sectionId="monatsvergleich"
        storageKeyPrefix={wpStoragePrefix}
        icon={Calendar}
        color="text-purple-500"
        title="Monats- / Saisonvergleich"
        summary="Strom ⇄ JAZ · Monate ⇄ Saison"
        defaultOpen
      >
        <WaermepumpeVergleich monatsdaten={monatsdaten} hatGetrennteStrom={hatGetrennteStrom} />
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
        <WaermepumpeMonatsTabelle monatsdaten={monatsdaten} />
      </SortableSection>

      </OrderedSections>
    </div>
  )
}
