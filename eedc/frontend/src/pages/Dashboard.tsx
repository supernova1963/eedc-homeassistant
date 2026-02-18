/**
 * Dashboard (Cockpit Übersicht)
 *
 * Zeigt aggregierte Übersicht ALLER Komponenten in strukturierten Sektionen:
 * - Energie-Bilanz
 * - Effizienz-Quoten
 * - Speicher (aggregiert)
 * - Wärmepumpe (aggregiert)
 * - E-Mobilität (aggregiert)
 * - Finanzen
 * - Umwelt (CO2)
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Sun, Zap, Battery, TrendingUp, ArrowRight, Flame, Car, Home,
  ArrowDownToLine, ArrowUpFromLine, Percent, Gauge, Euro, Leaf,
  ChevronRight, Calendar
} from 'lucide-react'
import { Card, Button, LoadingSpinner, FormelTooltip, fmtCalc } from '../components/ui'
import { useAnlagen } from '../hooks'
import { cockpitApi } from '../api'
import type { CockpitUebersicht } from '../api/cockpit'

export default function Dashboard() {
  const navigate = useNavigate()
  const { anlagen, loading: anlagenLoading } = useAnlagen()

  const [data, setData] = useState<CockpitUebersicht | null>(null)
  const [loading, setLoading] = useState(true)  // Start mit true um Race Condition zu vermeiden
  const [error, setError] = useState<string | null>(null)
  const [selectedYear, setSelectedYear] = useState<number | undefined>(undefined)
  const [availableYears, setAvailableYears] = useState<number[]>([])

  const erstesAnlageId = anlagen[0]?.id

  // Lade Cockpit-Daten
  useEffect(() => {
    if (!erstesAnlageId) return

    const loadData = async () => {
      setLoading(true)
      setError(null)
      try {
        const result = await cockpitApi.getUebersicht(erstesAnlageId, selectedYear)
        setData(result)

        // Jahre aus Zeitraum extrahieren (für Filter)
        if (result.zeitraum_von && result.zeitraum_bis) {
          const vonJahr = parseInt(result.zeitraum_von.split('-')[0])
          const bisJahr = parseInt(result.zeitraum_bis.split('-')[0])
          const years: number[] = []
          for (let y = vonJahr; y <= bisJahr; y++) {
            years.push(y)
          }
          setAvailableYears(years)
        }
      } catch (err) {
        setError('Fehler beim Laden der Daten')
        console.error(err)
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [erstesAnlageId, selectedYear])

  if (anlagenLoading || loading) {
    return <LoadingSpinner text="Lade Dashboard..." />
  }

  // Keine Anlage vorhanden
  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Übersicht</h1>
        <GettingStarted />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Übersicht</h1>
        <Card>
          <p className="text-red-500">{error || 'Keine Daten verfügbar'}</p>
          <Button onClick={() => navigate('/einstellungen/monatsdaten')} className="mt-4">
            Monatsdaten erfassen
          </Button>
        </Card>
      </div>
    )
  }

  const anlage = anlagen[0]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Home className="h-8 w-8 text-primary-500" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Übersicht</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {anlage.anlagenname} • {data.anlagenleistung_kwp.toFixed(1)} kWp
            </p>
          </div>
        </div>

        {/* Jahr-Filter */}
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-gray-400" />
          <select
            value={selectedYear || ''}
            onChange={(e) => setSelectedYear(e.target.value ? parseInt(e.target.value) : undefined)}
            className="input py-1.5 text-sm"
          >
            <option value="">Alle Jahre</option>
            {availableYears.map(y => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Zeitraum-Info */}
      {data.zeitraum_von && data.zeitraum_bis && (
        <p className="text-xs text-gray-400 dark:text-gray-500">
          Zeitraum: {data.zeitraum_von} bis {data.zeitraum_bis} ({data.anzahl_monate} Monate)
        </p>
      )}

      {/* Sektion 1: Energie-Bilanz */}
      <Section title="Energie-Bilanz" icon={Zap}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPICard
            title="PV-Erzeugung"
            value={(data.pv_erzeugung_kwh / 1000).toFixed(1)}
            unit="MWh"
            icon={Sun}
            color="text-energy-solar"
            bgColor="bg-yellow-50 dark:bg-yellow-900/20"
            onClick={() => navigate('/cockpit/pv-anlage')}
            formel="Σ PV-Erzeugung aller Monate"
            berechnung={`${fmtCalc(data.pv_erzeugung_kwh, 0)} kWh`}
            ergebnis={`= ${fmtCalc(data.pv_erzeugung_kwh / 1000, 1)} MWh`}
          />
          <KPICard
            title="Gesamtverbrauch"
            value={(data.gesamtverbrauch_kwh / 1000).toFixed(1)}
            unit="MWh"
            icon={Home}
            color="text-energy-consumption"
            bgColor="bg-purple-50 dark:bg-purple-900/20"
            formel="Eigenverbrauch + Netzbezug"
            berechnung={`${fmtCalc(data.eigenverbrauch_kwh, 0)} + ${fmtCalc(data.netzbezug_kwh, 0)} kWh`}
            ergebnis={`= ${fmtCalc(data.gesamtverbrauch_kwh / 1000, 1)} MWh`}
          />
          <KPICard
            title="Netzbezug"
            value={(data.netzbezug_kwh / 1000).toFixed(1)}
            unit="MWh"
            icon={ArrowDownToLine}
            color="text-energy-grid"
            bgColor="bg-red-50 dark:bg-red-900/20"
            formel="Σ Netzbezug aller Monate"
            berechnung={`${fmtCalc(data.netzbezug_kwh, 0)} kWh`}
            ergebnis={`= ${fmtCalc(data.netzbezug_kwh / 1000, 1)} MWh`}
          />
          <KPICard
            title="Einspeisung"
            value={(data.einspeisung_kwh / 1000).toFixed(1)}
            unit="MWh"
            icon={ArrowUpFromLine}
            color="text-green-500"
            bgColor="bg-green-50 dark:bg-green-900/20"
            formel="Σ Einspeisung aller Monate"
            berechnung={`${fmtCalc(data.einspeisung_kwh, 0)} kWh`}
            ergebnis={`= ${fmtCalc(data.einspeisung_kwh / 1000, 1)} MWh`}
          />
        </div>
      </Section>

      {/* Sektion 2: Effizienz-Quoten */}
      <Section title="Effizienz-Quoten" icon={Percent}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPICard
            title="Autarkie"
            value={data.autarkie_prozent.toFixed(1)}
            unit="%"
            subtitle="Unabhängigkeit vom Netz"
            icon={Gauge}
            color="text-blue-500"
            bgColor="bg-blue-50 dark:bg-blue-900/20"
            formel="Eigenverbrauch ÷ Gesamtverbrauch × 100"
            berechnung={`${fmtCalc(data.eigenverbrauch_kwh, 0)} ÷ ${fmtCalc(data.gesamtverbrauch_kwh, 0)} × 100`}
            ergebnis={`= ${fmtCalc(data.autarkie_prozent, 1)} %`}
          />
          <KPICard
            title="Eigenverbrauchsquote"
            value={data.eigenverbrauch_quote_prozent.toFixed(1)}
            unit="%"
            subtitle="Selbst genutzte PV"
            icon={Zap}
            color="text-purple-500"
            bgColor="bg-purple-50 dark:bg-purple-900/20"
            formel="Eigenverbrauch ÷ Erzeugung × 100"
            berechnung={`${fmtCalc(data.eigenverbrauch_kwh, 0)} ÷ ${fmtCalc(data.pv_erzeugung_kwh, 0)} × 100`}
            ergebnis={`= ${fmtCalc(data.eigenverbrauch_quote_prozent, 1)} %`}
          />
          <KPICard
            title="Direktverbrauchsquote"
            value={data.direktverbrauch_quote_prozent.toFixed(1)}
            unit="%"
            subtitle="Ohne Speicher-Umweg"
            icon={TrendingUp}
            color="text-orange-500"
            bgColor="bg-orange-50 dark:bg-orange-900/20"
            formel="Direktverbrauch ÷ Erzeugung × 100"
            berechnung={`${fmtCalc(data.direktverbrauch_kwh, 0)} ÷ ${fmtCalc(data.pv_erzeugung_kwh, 0)} × 100`}
            ergebnis={`= ${fmtCalc(data.direktverbrauch_quote_prozent, 1)} %`}
          />
          <KPICard
            title="Spez. Ertrag"
            value={data.spezifischer_ertrag_kwh_kwp?.toFixed(0) || '---'}
            unit="kWh/kWp"
            subtitle="Anlageneffizienz"
            icon={Sun}
            color="text-yellow-600"
            bgColor="bg-yellow-50 dark:bg-yellow-900/20"
            formel="Erzeugung ÷ Anlagenleistung"
            berechnung={`${fmtCalc(data.pv_erzeugung_kwh, 0)} kWh ÷ ${fmtCalc(data.anlagenleistung_kwp, 2)} kWp`}
            ergebnis={`= ${fmtCalc(data.spezifischer_ertrag_kwh_kwp || 0, 0)} kWh/kWp`}
          />
        </div>
      </Section>

      {/* Sektion 3: Speicher (wenn vorhanden) */}
      {data.hat_speicher && (
        <SectionLink
          title="Speicher"
          icon={Battery}
          onClick={() => navigate('/cockpit/speicher')}
        >
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KPICard
              title="Ladung gesamt"
              value={(data.speicher_ladung_kwh / 1000).toFixed(2)}
              unit="MWh"
              icon={ArrowDownToLine}
              color="text-green-500"
              bgColor="bg-green-50 dark:bg-green-900/20"
              formel="Σ Speicher-Ladung"
              berechnung={`${fmtCalc(data.speicher_ladung_kwh, 0)} kWh`}
              ergebnis={`= ${fmtCalc(data.speicher_ladung_kwh / 1000, 2)} MWh`}
            />
            <KPICard
              title="Entladung gesamt"
              value={(data.speicher_entladung_kwh / 1000).toFixed(2)}
              unit="MWh"
              icon={ArrowUpFromLine}
              color="text-blue-500"
              bgColor="bg-blue-50 dark:bg-blue-900/20"
              formel="Σ Speicher-Entladung"
              berechnung={`${fmtCalc(data.speicher_entladung_kwh, 0)} kWh`}
              ergebnis={`= ${fmtCalc(data.speicher_entladung_kwh / 1000, 2)} MWh`}
            />
            <KPICard
              title="Ø Effizienz"
              value={data.speicher_effizienz_prozent?.toFixed(1) || '---'}
              unit="%"
              icon={Gauge}
              color="text-teal-500"
              bgColor="bg-teal-50 dark:bg-teal-900/20"
              formel="Entladung ÷ Ladung × 100"
              berechnung={`${fmtCalc(data.speicher_entladung_kwh, 0)} ÷ ${fmtCalc(data.speicher_ladung_kwh, 0)} × 100`}
              ergebnis={`= ${fmtCalc(data.speicher_effizienz_prozent || 0, 1)} %`}
            />
            <KPICard
              title="Vollzyklen"
              value={data.speicher_vollzyklen?.toFixed(0) || '---'}
              unit=""
              subtitle={`${data.speicher_kapazitaet_kwh.toFixed(1)} kWh Kapazität`}
              icon={Battery}
              color="text-green-600"
              bgColor="bg-green-50 dark:bg-green-900/20"
              formel="Ladung ÷ Kapazität"
              berechnung={`${fmtCalc(data.speicher_ladung_kwh, 0)} kWh ÷ ${fmtCalc(data.speicher_kapazitaet_kwh, 1)} kWh`}
              ergebnis={`= ${fmtCalc(data.speicher_vollzyklen || 0, 0)} Zyklen`}
            />
          </div>
        </SectionLink>
      )}

      {/* Sektion 4: Wärmepumpe (wenn vorhanden) */}
      {data.hat_waermepumpe && (
        <SectionLink
          title="Wärmepumpe"
          icon={Flame}
          onClick={() => navigate('/cockpit/waermepumpe')}
        >
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KPICard
              title="Wärme erzeugt"
              value={(data.wp_waerme_kwh / 1000).toFixed(2)}
              unit="MWh"
              icon={Flame}
              color="text-red-500"
              bgColor="bg-red-50 dark:bg-red-900/20"
              formel="Σ Heizung + Warmwasser"
              berechnung={`${fmtCalc(data.wp_waerme_kwh, 0)} kWh`}
              ergebnis={`= ${fmtCalc(data.wp_waerme_kwh / 1000, 2)} MWh`}
            />
            <KPICard
              title="Strom verbraucht"
              value={(data.wp_strom_kwh / 1000).toFixed(2)}
              unit="MWh"
              icon={Zap}
              color="text-purple-500"
              bgColor="bg-purple-50 dark:bg-purple-900/20"
              formel="Σ WP-Stromverbrauch"
              berechnung={`${fmtCalc(data.wp_strom_kwh, 0)} kWh`}
              ergebnis={`= ${fmtCalc(data.wp_strom_kwh / 1000, 2)} MWh`}
            />
            <KPICard
              title="Ø COP"
              value={data.wp_cop?.toFixed(1) || '---'}
              unit=""
              icon={Gauge}
              color="text-orange-500"
              bgColor="bg-orange-50 dark:bg-orange-900/20"
              formel="Wärme ÷ Strom"
              berechnung={`${fmtCalc(data.wp_waerme_kwh, 0)} ÷ ${fmtCalc(data.wp_strom_kwh, 0)}`}
              ergebnis={`= ${fmtCalc(data.wp_cop || 0, 1)}`}
            />
            <KPICard
              title="Ersparnis vs. Gas"
              value={data.wp_ersparnis_euro.toFixed(0)}
              unit="€"
              icon={Euro}
              color="text-green-600"
              bgColor="bg-green-50 dark:bg-green-900/20"
              formel="Gaskosten - Stromkosten"
              berechnung={`(${fmtCalc(data.wp_waerme_kwh, 0)} kWh ÷ 0.9 × 10ct) - (${fmtCalc(data.wp_strom_kwh, 0)} kWh × Strompreis)`}
              ergebnis={`= ${fmtCalc(data.wp_ersparnis_euro, 0)} €`}
            />
          </div>
        </SectionLink>
      )}

      {/* Sektion 5: E-Mobilität (wenn vorhanden) */}
      {data.hat_emobilitaet && (
        <SectionLink
          title="E-Mobilität"
          icon={Car}
          onClick={() => navigate('/cockpit/e-auto')}
        >
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KPICard
              title="Gefahrene km"
              value={(data.emob_km / 1000).toFixed(1)}
              unit="Tkm"
              icon={Car}
              color="text-purple-500"
              bgColor="bg-purple-50 dark:bg-purple-900/20"
              formel="Σ gefahrene Kilometer"
              berechnung={`${fmtCalc(data.emob_km, 0)} km`}
              ergebnis={`= ${fmtCalc(data.emob_km / 1000, 1)} Tkm`}
            />
            <KPICard
              title="Ladung gesamt"
              value={(data.emob_ladung_kwh / 1000).toFixed(2)}
              unit="MWh"
              icon={Zap}
              color="text-blue-500"
              bgColor="bg-blue-50 dark:bg-blue-900/20"
              formel="Σ Heim + Extern Ladung"
              berechnung={`${fmtCalc(data.emob_ladung_kwh, 0)} kWh`}
              ergebnis={`= ${fmtCalc(data.emob_ladung_kwh / 1000, 2)} MWh`}
            />
            <KPICard
              title="PV-Anteil"
              value={data.emob_pv_anteil_prozent?.toFixed(0) || '---'}
              unit="%"
              icon={Sun}
              color="text-yellow-500"
              bgColor="bg-yellow-50 dark:bg-yellow-900/20"
              formel="PV-Ladung ÷ Heimladung × 100"
              berechnung="PV-geladene kWh ÷ Gesamt-Ladung"
              ergebnis={`= ${fmtCalc(data.emob_pv_anteil_prozent || 0, 0)} %`}
            />
            <KPICard
              title="Ersparnis vs. Benzin"
              value={data.emob_ersparnis_euro.toFixed(0)}
              unit="€"
              icon={Euro}
              color="text-green-600"
              bgColor="bg-green-50 dark:bg-green-900/20"
              formel="Benzinkosten - Stromkosten"
              berechnung={`Benzin (7L/100km × 1.80€) - Strom`}
              ergebnis={`= ${fmtCalc(data.emob_ersparnis_euro, 0)} €`}
            />
          </div>
        </SectionLink>
      )}

      {/* Sektion 6: Finanzen */}
      <Section title="Finanzen" icon={Euro}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPICard
            title="Einspeiseerlös"
            value={data.einspeise_erloes_euro.toFixed(0)}
            unit="€"
            icon={ArrowUpFromLine}
            color="text-green-500"
            bgColor="bg-green-50 dark:bg-green-900/20"
            formel="Einspeisung × Vergütung"
            berechnung={`${fmtCalc(data.einspeisung_kwh, 0)} kWh × 8.2 ct/kWh`}
            ergebnis={`= ${fmtCalc(data.einspeise_erloes_euro, 0)} €`}
          />
          <KPICard
            title="EV-Ersparnis"
            value={data.ev_ersparnis_euro.toFixed(0)}
            unit="€"
            icon={Zap}
            color="text-purple-500"
            bgColor="bg-purple-50 dark:bg-purple-900/20"
            formel="Eigenverbrauch × Strompreis"
            berechnung={`${fmtCalc(data.eigenverbrauch_kwh, 0)} kWh × Strompreis`}
            ergebnis={`= ${fmtCalc(data.ev_ersparnis_euro, 0)} €`}
          />
          <KPICard
            title="Netto-Ertrag"
            value={data.netto_ertrag_euro.toFixed(0)}
            unit="€"
            icon={TrendingUp}
            color="text-blue-600"
            bgColor="bg-blue-50 dark:bg-blue-900/20"
            formel="Erlös + Ersparnis"
            berechnung={`${fmtCalc(data.einspeise_erloes_euro, 0)} + ${fmtCalc(data.ev_ersparnis_euro, 0)} €`}
            ergebnis={`= ${fmtCalc(data.netto_ertrag_euro, 0)} €`}
          />
          <KPICard
            title="Jahres-Rendite"
            value={data.jahres_rendite_prozent?.toFixed(1) || '---'}
            unit="%"
            subtitle={`von ${data.investition_gesamt_euro.toFixed(0)} € Invest`}
            icon={Gauge}
            color="text-emerald-600"
            bgColor="bg-emerald-50 dark:bg-emerald-900/20"
            onClick={() => navigate('/auswertungen/roi')}
            formel="Jahres-Ertrag ÷ Investition × 100"
            berechnung={`${fmtCalc(data.netto_ertrag_euro, 0)} € ÷ ${fmtCalc(data.investition_gesamt_euro, 0)} €`}
            ergebnis={`= ${fmtCalc(data.jahres_rendite_prozent || 0, 1)} % p.a.`}
          />
        </div>
      </Section>

      {/* Sektion 7: Umwelt */}
      <Section title="CO₂-Bilanz" icon={Leaf}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPICard
            title="CO₂ PV"
            value={(data.co2_pv_kg / 1000).toFixed(1)}
            unit="t"
            subtitle="Vermiedene Emissionen"
            icon={Sun}
            color="text-green-500"
            bgColor="bg-green-50 dark:bg-green-900/20"
            formel="Eigenverbrauch × CO₂-Faktor"
            berechnung={`${fmtCalc(data.eigenverbrauch_kwh, 0)} kWh × 0.38 kg/kWh`}
            ergebnis={`= ${fmtCalc(data.co2_pv_kg, 0)} kg`}
          />
          <KPICard
            title="CO₂ Wärmepumpe"
            value={(data.co2_wp_kg / 1000).toFixed(2)}
            unit="t"
            subtitle="vs. Gas-Heizung"
            icon={Flame}
            color="text-teal-500"
            bgColor="bg-teal-50 dark:bg-teal-900/20"
            formel="CO₂ Gas - CO₂ Strom"
            berechnung="Gasverbrauch × 0.201 - WP-Strom × 0.38"
            ergebnis={`= ${fmtCalc(data.co2_wp_kg, 0)} kg`}
          />
          <KPICard
            title="CO₂ E-Mobilität"
            value={(data.co2_emob_kg / 1000).toFixed(2)}
            unit="t"
            subtitle="vs. Verbrenner"
            icon={Car}
            color="text-blue-500"
            bgColor="bg-blue-50 dark:bg-blue-900/20"
            formel="CO₂ Benzin - CO₂ Strom"
            berechnung="Benzinverbrauch × 2.37 - Stromverbrauch × 0.38"
            ergebnis={`= ${fmtCalc(data.co2_emob_kg, 0)} kg`}
          />
          <KPICard
            title="CO₂ gesamt"
            value={(data.co2_gesamt_kg / 1000).toFixed(1)}
            unit="t"
            subtitle="Gesamte Einsparung"
            icon={Leaf}
            color="text-emerald-600"
            bgColor="bg-emerald-50 dark:bg-emerald-900/20"
            formel="Σ aller CO₂-Einsparungen"
            berechnung={`${fmtCalc(data.co2_pv_kg, 0)} + ${fmtCalc(data.co2_wp_kg, 0)} + ${fmtCalc(data.co2_emob_kg, 0)} kg`}
            ergebnis={`= ${fmtCalc(data.co2_gesamt_kg / 1000, 1)} t`}
          />
        </div>
      </Section>

      {/* Quick Links */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <QuickLink
          title="Monatsdaten"
          description="Neue Daten erfassen oder CSV importieren"
          onClick={() => navigate('/einstellungen/monatsdaten')}
        />
        <QuickLink
          title="Auswertungen"
          description="Detaillierte Analysen und Zeitverläufe"
          onClick={() => navigate('/auswertungen')}
        />
        <QuickLink
          title="Investitionen"
          description="Komponenten verwalten"
          onClick={() => navigate('/einstellungen/investitionen')}
        />
      </div>
    </div>
  )
}

// =============================================================================
// Section Components
// =============================================================================

interface SectionProps {
  title: string
  icon: React.ElementType
  children: React.ReactNode
}

function Section({ title, icon: Icon, children }: SectionProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Icon className="h-5 w-5 text-gray-500" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
      </div>
      {children}
    </div>
  )
}

interface SectionLinkProps extends SectionProps {
  onClick: () => void
}

function SectionLink({ title, icon: Icon, onClick, children }: SectionLinkProps) {
  return (
    <div className="space-y-3">
      <button
        onClick={onClick}
        className="flex items-center gap-2 group hover:opacity-80 transition-opacity"
      >
        <Icon className="h-5 w-5 text-gray-500" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
        <ChevronRight className="h-4 w-4 text-gray-400 group-hover:text-primary-500 transition-colors" />
      </button>
      {children}
    </div>
  )
}

// =============================================================================
// KPI Card
// =============================================================================

interface KPICardProps {
  title: string
  value: string
  unit: string
  subtitle?: string
  icon: React.ElementType
  color: string
  bgColor: string
  onClick?: () => void
  formel?: string
  berechnung?: string
  ergebnis?: string
}

function KPICard({
  title,
  value,
  unit,
  subtitle,
  icon: Icon,
  color,
  bgColor,
  onClick,
  formel,
  berechnung,
  ergebnis
}: KPICardProps) {
  const valueContent = (
    <span className="text-xl font-bold text-gray-900 dark:text-white">
      {value} <span className="text-sm font-normal text-gray-500">{unit}</span>
    </span>
  )

  const content = (
    <div className="flex items-start justify-between">
      <div className="flex-1 min-w-0">
        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{title}</p>
        <div className="mt-0.5">
          {formel ? (
            <FormelTooltip formel={formel} berechnung={berechnung} ergebnis={ergebnis}>
              {valueContent}
            </FormelTooltip>
          ) : (
            valueContent
          )}
        </div>
        {subtitle && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate">{subtitle}</p>
        )}
      </div>
      <div className={`p-2 rounded-lg ${bgColor} ml-2 flex-shrink-0`}>
        <Icon className={`h-5 w-5 ${color}`} />
      </div>
    </div>
  )

  if (onClick) {
    return (
      <button onClick={onClick} className="card p-3 text-left hover:shadow-md transition-shadow w-full">
        {content}
      </button>
    )
  }

  return <Card className="p-3">{content}</Card>
}

// =============================================================================
// Quick Link
// =============================================================================

function QuickLink({ title, description, onClick }: { title: string; description: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="card p-4 text-left hover:shadow-md transition-shadow group"
    >
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-gray-900 dark:text-white">{title}</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">{description}</p>
        </div>
        <ArrowRight className="h-5 w-5 text-gray-400 group-hover:text-primary-600 transition-colors" />
      </div>
    </button>
  )
}

// =============================================================================
// Getting Started
// =============================================================================

function GettingStarted() {
  const navigate = useNavigate()

  return (
    <Card className="bg-primary-50 dark:bg-primary-900/20 border-primary-200 dark:border-primary-800">
      <h2 className="text-lg font-semibold text-primary-900 dark:text-primary-100 mb-4">
        Willkommen bei eedc!
      </h2>
      <p className="text-primary-700 dark:text-primary-300 mb-4">
        Starte mit diesen Schritten, um deine PV-Anlage zu analysieren:
      </p>
      <ol className="list-decimal list-inside text-primary-700 dark:text-primary-300 space-y-2 mb-6">
        <li>Lege deine PV-Anlage unter "Anlagen" an</li>
        <li>Konfiguriere deine Strompreise</li>
        <li>Erfasse Monatsdaten oder importiere eine CSV</li>
        <li>Analysiere deine Ergebnisse in den Auswertungen</li>
      </ol>
      <Button onClick={() => navigate('/einstellungen/anlage')}>
        Jetzt starten
        <ArrowRight className="h-4 w-4 ml-2" />
      </Button>
    </Card>
  )
}
