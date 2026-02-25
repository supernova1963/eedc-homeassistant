/**
 * Dashboard (Cockpit Übersicht)
 *
 * Zeigt aggregierte Übersicht ALLER Komponenten in strukturierten Sektionen:
 * - Hero-Leiste (Top-3 KPIs mit Vorjahresvergleich)
 * - Energie-Fluss-Diagramm
 * - Energie-Bilanz + Sparkline
 * - Effizienz-Quoten (mit Ring-Gauges)
 * - Speicher, Wärmepumpe, E-Mobilität
 * - Finanzen (mit Amortisationsfortschritt)
 * - CO₂-Bilanz
 * - Community-Teaser (wenn Daten geteilt)
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Sun, Zap, Battery, TrendingUp, TrendingDown, ArrowRight, Flame, Car, Home,
  ArrowDownToLine, ArrowUpFromLine, Percent, Gauge, Euro, Leaf,
  ChevronRight, Calendar, Trophy, Minus, Receipt
} from 'lucide-react'
import { BarChart, Bar, ResponsiveContainer, Tooltip, Cell } from 'recharts'
import { Card, Button, LoadingSpinner, FormelTooltip, fmtCalc } from '../components/ui'
import { useAnlagen } from '../hooks'
import { cockpitApi } from '../api'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
import type { CockpitUebersicht } from '../api/cockpit'

const MONAT_KURZ = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

export default function Dashboard() {
  const navigate = useNavigate()
  const { anlagen, loading: anlagenLoading } = useAnlagen()

  const [data, setData] = useState<CockpitUebersicht | null>(null)
  const [prevYearData, setPrevYearData] = useState<CockpitUebersicht | null>(null)
  const [monatsdaten, setMonatsdaten] = useState<AggregierteMonatsdaten[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedYear, setSelectedYear] = useState<number | undefined>(undefined)
  const [availableYears, setAvailableYears] = useState<number[]>([])

  const erstesAnlageId = anlagen[0]?.id

  useEffect(() => {
    if (!erstesAnlageId) return

    const loadData = async () => {
      setLoading(true)
      setError(null)
      try {
        const [result, monate] = await Promise.all([
          cockpitApi.getUebersicht(erstesAnlageId, selectedYear),
          monatsdatenApi.listAggregiert(erstesAnlageId),
        ])
        setData(result)
        setMonatsdaten(monate)

        if (result.zeitraum_von && result.zeitraum_bis) {
          const vonJahr = parseInt(result.zeitraum_von.split('-')[0])
          const bisJahr = parseInt(result.zeitraum_bis.split('-')[0])
          const years: number[] = []
          for (let y = vonJahr; y <= bisJahr; y++) years.push(y)
          setAvailableYears(years)
        }

        // Vorjahr laden wenn ein Jahr gewählt ist
        if (selectedYear) {
          try {
            const prev = await cockpitApi.getUebersicht(erstesAnlageId, selectedYear - 1)
            setPrevYearData(prev.anzahl_monate > 0 ? prev : null)
          } catch {
            setPrevYearData(null)
          }
        } else {
          setPrevYearData(null)
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

  if (anlagenLoading || loading) return <LoadingSpinner text="Lade Dashboard..." />

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

      {/* Hero-Leiste */}
      <HeroLeiste data={data} prevData={prevYearData} year={selectedYear} />

      {/* Energie-Fluss */}
      <EnergyFlowDiagram data={data} />

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
        <SparklineChart monatsdaten={monatsdaten} selectedYear={selectedYear} />
      </Section>

      {/* Sektion 2: Effizienz-Quoten */}
      <Section title="Effizienz-Quoten" icon={Percent}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <RingGaugeCard
            title="Autarkie"
            value={data.autarkie_prozent}
            subtitle="Unabhängigkeit"
            color="#3b82f6"
            formel="Eigenverbrauch ÷ Gesamtverbrauch × 100"
            berechnung={`${fmtCalc(data.eigenverbrauch_kwh, 0)} ÷ ${fmtCalc(data.gesamtverbrauch_kwh, 0)} × 100`}
            ergebnis={`= ${fmtCalc(data.autarkie_prozent, 1)} %`}
          />
          <RingGaugeCard
            title="Eigenverbrauch"
            value={data.eigenverbrauch_quote_prozent}
            subtitle="Selbst genutzte PV"
            color="#a855f7"
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

      {/* Sektion 3: Speicher */}
      {data.hat_speicher && (
        <SectionLink title="Speicher" icon={Battery} onClick={() => navigate('/cockpit/speicher')}>
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

      {/* Sektion 4: Wärmepumpe */}
      {data.hat_waermepumpe && (
        <SectionLink title="Wärmepumpe" icon={Flame} onClick={() => navigate('/cockpit/waermepumpe')}>
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

      {/* Sektion 5: E-Mobilität */}
      {data.hat_emobilitaet && (
        <SectionLink title="E-Mobilität" icon={Car} onClick={() => navigate('/cockpit/e-auto')}>
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
              berechnung="Benzin (7L/100km × 1.80€) - Strom"
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
          {data.ust_eigenverbrauch_euro != null && data.ust_eigenverbrauch_euro > 0 && (
            <KPICard
              title="USt Eigenverbrauch"
              value={`-${data.ust_eigenverbrauch_euro.toFixed(0)}`}
              unit="€"
              icon={Receipt}
              color="text-orange-500"
              bgColor="bg-orange-50 dark:bg-orange-900/20"
              formel="EV × Selbstkosten × USt-Satz"
              berechnung="Regelbesteuerung: USt auf unentgeltliche Wertabgabe"
              ergebnis={`= -${fmtCalc(data.ust_eigenverbrauch_euro, 0)} €`}
            />
          )}
          <KPICard
            title="Netto-Ertrag"
            value={data.netto_ertrag_euro.toFixed(0)}
            unit="€"
            icon={TrendingUp}
            color="text-blue-600"
            bgColor="bg-blue-50 dark:bg-blue-900/20"
            formel={data.ust_eigenverbrauch_euro ? "Erlös + Ersparnis − USt" : "Erlös + Ersparnis"}
            berechnung={data.ust_eigenverbrauch_euro
              ? `${fmtCalc(data.einspeise_erloes_euro, 0)} + ${fmtCalc(data.ev_ersparnis_euro, 0)} − ${fmtCalc(data.ust_eigenverbrauch_euro, 0)} €`
              : `${fmtCalc(data.einspeise_erloes_euro, 0)} + ${fmtCalc(data.ev_ersparnis_euro, 0)} €`}
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
        {!selectedYear && data.investition_gesamt_euro > 0 && (
          <AmortisationsBar data={data} />
        )}
      </Section>

      {/* Sektion 7: CO₂-Bilanz */}
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

      {/* Community-Teaser */}
      {anlage.community_hash && <CommunityTeaser />}

      {/* Quick Links */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <QuickLink title="Monatsdaten" description="Neue Daten erfassen oder CSV importieren" onClick={() => navigate('/einstellungen/monatsdaten')} />
        <QuickLink title="Auswertungen" description="Detaillierte Analysen und Zeitverläufe" onClick={() => navigate('/auswertungen')} />
        <QuickLink title="Investitionen" description="Komponenten verwalten" onClick={() => navigate('/einstellungen/investitionen')} />
      </div>
    </div>
  )
}

// =============================================================================
// Hero-Leiste
// =============================================================================

function HeroLeiste({ data, prevData, year }: {
  data: CockpitUebersicht
  prevData: CockpitUebersicht | null
  year?: number
}) {
  const trend = (curr: number, prev?: number) => {
    if (!prev || prev === 0) return null
    return ((curr - prev) / prev) * 100
  }

  const items = [
    {
      label: 'Autarkie',
      value: `${data.autarkie_prozent.toFixed(1)} %`,
      delta: trend(data.autarkie_prozent, prevData?.autarkie_prozent),
      color: 'text-blue-600 dark:text-blue-400',
      bg: 'bg-blue-50 dark:bg-blue-900/20',
    },
    {
      label: 'Spez. Ertrag',
      value: data.spezifischer_ertrag_kwh_kwp
        ? `${data.spezifischer_ertrag_kwh_kwp.toFixed(0)} kWh/kWp`
        : '---',
      delta: trend(data.spezifischer_ertrag_kwh_kwp || 0, prevData?.spezifischer_ertrag_kwh_kwp ?? undefined),
      color: 'text-yellow-600 dark:text-yellow-400',
      bg: 'bg-yellow-50 dark:bg-yellow-900/20',
    },
    {
      label: 'Netto-Ertrag',
      value: `${data.netto_ertrag_euro.toFixed(0)} €`,
      delta: trend(data.netto_ertrag_euro, prevData?.netto_ertrag_euro),
      color: 'text-emerald-600 dark:text-emerald-400',
      bg: 'bg-emerald-50 dark:bg-emerald-900/20',
    },
  ]

  return (
    <div className="grid grid-cols-3 gap-3">
      {items.map(item => (
        <div key={item.label} className={`rounded-xl p-4 ${item.bg}`}>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{item.label}</p>
          <p className={`text-2xl font-bold ${item.color}`}>{item.value}</p>
          {item.delta !== null && year && (
            <div className={`flex items-center gap-1 mt-1 text-xs font-medium ${
              item.delta >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'
            }`}>
              {item.delta > 0.5
                ? <TrendingUp className="h-3 w-3" />
                : item.delta < -0.5
                  ? <TrendingDown className="h-3 w-3" />
                  : <Minus className="h-3 w-3" />
              }
              {item.delta > 0 ? '+' : ''}{item.delta.toFixed(1)} % vs. {year - 1}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// =============================================================================
// Energie-Fluss-Diagramm
// =============================================================================

function EnergyFlowDiagram({ data }: { data: CockpitUebersicht }) {
  const pv = data.pv_erzeugung_kwh
  if (pv <= 0) return null

  const direkt = Math.max(0, data.direktverbrauch_kwh)
  const speicherLad = data.hat_speicher ? Math.max(0, data.speicher_ladung_kwh) : 0
  const einspeis = Math.max(0, data.einspeisung_kwh)
  const pvSum = direkt + speicherLad + einspeis || pv

  const speicherEntl = data.hat_speicher ? Math.max(0, data.speicher_entladung_kwh) : 0
  const netz = Math.max(0, data.netzbezug_kwh)
  const hausSum = direkt + speicherEntl + netz || data.gesamtverbrauch_kwh

  const fmt = (v: number) => v >= 1000 ? `${(v / 1000).toFixed(1)} MWh` : `${v.toFixed(0)} kWh`
  const pct = (v: number, total: number) => total > 0 ? Math.round((v / total) * 100) : 0

  return (
    <Card className="p-4">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
        <Zap className="h-4 w-4 text-yellow-500" />
        Energie-Fluss
      </h3>
      <div className="space-y-4">

        {/* PV-Verteilung */}
        <div>
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-xs text-gray-500 flex items-center gap-1.5">
              <Sun className="h-3.5 w-3.5 text-yellow-500" />
              <span>PV erzeugt: <strong className="text-gray-700 dark:text-gray-300">{fmt(pv)}</strong></span>
            </span>
            <span className="text-xs text-gray-400">Wohin?</span>
          </div>
          <div className="flex h-7 rounded-lg overflow-hidden gap-px bg-gray-100 dark:bg-gray-700">
            {direkt > 0 && (
              <div className="bg-blue-500 flex items-center justify-center transition-all"
                style={{ width: `${pct(direkt, pvSum)}%` }}
                title={`Direktverbrauch: ${fmt(direkt)}`}>
                {pct(direkt, pvSum) >= 12 && (
                  <span className="text-xs text-white font-medium">{pct(direkt, pvSum)}%</span>
                )}
              </div>
            )}
            {speicherLad > 0 && (
              <div className="bg-green-500 flex items-center justify-center"
                style={{ width: `${pct(speicherLad, pvSum)}%` }}
                title={`Speicher: ${fmt(speicherLad)}`}>
                {pct(speicherLad, pvSum) >= 12 && (
                  <span className="text-xs text-white font-medium">{pct(speicherLad, pvSum)}%</span>
                )}
              </div>
            )}
            {einspeis > 0 && (
              <div className="bg-orange-400 flex items-center justify-center"
                style={{ width: `${pct(einspeis, pvSum)}%` }}
                title={`Einspeisung: ${fmt(einspeis)}`}>
                {pct(einspeis, pvSum) >= 12 && (
                  <span className="text-xs text-white font-medium">{pct(einspeis, pvSum)}%</span>
                )}
              </div>
            )}
          </div>
          <div className="flex gap-4 mt-1.5 flex-wrap">
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-sm bg-blue-500 inline-block flex-shrink-0" />
              Direkt {fmt(direkt)}
            </span>
            {speicherLad > 0 && (
              <span className="text-xs text-gray-500 flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-sm bg-green-500 inline-block flex-shrink-0" />
                Speicher {fmt(speicherLad)}
              </span>
            )}
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-sm bg-orange-400 inline-block flex-shrink-0" />
              Einspeis. {fmt(einspeis)}
            </span>
          </div>
        </div>

        {/* Haus-Versorgung */}
        <div>
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-xs text-gray-500 flex items-center gap-1.5">
              <Home className="h-3.5 w-3.5 text-purple-500" />
              <span>Haus verbraucht: <strong className="text-gray-700 dark:text-gray-300">{fmt(data.gesamtverbrauch_kwh)}</strong></span>
            </span>
            <span className="text-xs text-gray-400">Woher?</span>
          </div>
          <div className="flex h-7 rounded-lg overflow-hidden gap-px bg-gray-100 dark:bg-gray-700">
            {direkt > 0 && (
              <div className="bg-blue-500 flex items-center justify-center"
                style={{ width: `${pct(direkt, hausSum)}%` }}
                title={`PV direkt: ${fmt(direkt)}`}>
                {pct(direkt, hausSum) >= 12 && (
                  <span className="text-xs text-white font-medium">{pct(direkt, hausSum)}%</span>
                )}
              </div>
            )}
            {speicherEntl > 0 && (
              <div className="bg-green-500 flex items-center justify-center"
                style={{ width: `${pct(speicherEntl, hausSum)}%` }}
                title={`Speicher: ${fmt(speicherEntl)}`}>
                {pct(speicherEntl, hausSum) >= 12 && (
                  <span className="text-xs text-white font-medium">{pct(speicherEntl, hausSum)}%</span>
                )}
              </div>
            )}
            {netz > 0 && (
              <div className="bg-red-400 flex items-center justify-center"
                style={{ width: `${pct(netz, hausSum)}%` }}
                title={`Netzbezug: ${fmt(netz)}`}>
                {pct(netz, hausSum) >= 12 && (
                  <span className="text-xs text-white font-medium">{pct(netz, hausSum)}%</span>
                )}
              </div>
            )}
          </div>
          <div className="flex gap-4 mt-1.5 flex-wrap">
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-sm bg-blue-500 inline-block flex-shrink-0" />
              PV direkt {fmt(direkt)}
            </span>
            {speicherEntl > 0 && (
              <span className="text-xs text-gray-500 flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-sm bg-green-500 inline-block flex-shrink-0" />
                Speicher {fmt(speicherEntl)}
              </span>
            )}
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-sm bg-red-400 inline-block flex-shrink-0" />
              Netzbezug {fmt(netz)}
            </span>
          </div>
        </div>

      </div>
    </Card>
  )
}

// =============================================================================
// Ring-Gauge Card
// =============================================================================

function RingGaugeCard({ title, value, subtitle, color, formel, berechnung, ergebnis }: {
  title: string; value: number; subtitle?: string; color: string
  formel?: string; berechnung?: string; ergebnis?: string
}) {
  const r = 32
  const circ = 2 * Math.PI * r
  const filled = Math.min(100, Math.max(0, value)) / 100 * circ

  const gauge = (
    <svg viewBox="0 0 80 80" className="w-16 h-16 flex-shrink-0">
      <circle cx="40" cy="40" r={r} fill="none" stroke="currentColor" strokeWidth="8"
        className="text-gray-200 dark:text-gray-700" />
      <circle cx="40" cy="40" r={r} fill="none" stroke={color} strokeWidth="8"
        strokeDasharray={`${filled} ${circ}`}
        strokeLinecap="round"
        transform="rotate(-90 40 40)" />
      <text x="40" y="45" textAnchor="middle" fontSize="15" fontWeight="bold"
        fill={color}>
        {value.toFixed(0)}
      </text>
    </svg>
  )

  return (
    <Card className="p-3">
      <div className="flex items-center gap-3">
        {formel
          ? <FormelTooltip formel={formel} berechnung={berechnung} ergebnis={ergebnis}>{gauge}</FormelTooltip>
          : gauge
        }
        <div className="min-w-0">
          <p className="text-xs text-gray-500 dark:text-gray-400">{title}</p>
          <p className="text-lg font-bold text-gray-900 dark:text-white">{value.toFixed(1)} %</p>
          {subtitle && <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{subtitle}</p>}
        </div>
      </div>
    </Card>
  )
}

// =============================================================================
// Sparkline
// =============================================================================

function SparklineChart({ monatsdaten, selectedYear }: {
  monatsdaten: AggregierteMonatsdaten[]
  selectedYear?: number
}) {
  if (monatsdaten.length < 2) return null

  const sorted = [...monatsdaten].sort((a, b) =>
    a.jahr !== b.jahr ? a.jahr - b.jahr : a.monat - b.monat
  )
  const filtered = selectedYear
    ? sorted.filter(m => m.jahr === selectedYear)
    : sorted

  if (filtered.length < 2) return null

  const firstJahr = filtered[0].jahr
  const chartData = filtered.map(m => ({
    name: m.jahr !== firstJahr
      ? `${MONAT_KURZ[m.monat]} ${m.jahr}`
      : MONAT_KURZ[m.monat],
    kwh: Math.round(m.pv_erzeugung_kwh),
  }))
  const max = Math.max(...chartData.map(d => d.kwh))

  return (
    <div className="mt-4">
      <p className="text-xs text-gray-400 dark:text-gray-500 mb-2">
        PV-Monatserträge — {selectedYear ?? `${filtered[0].jahr}–${filtered[filtered.length - 1].jahr}`}
      </p>
      <div className="h-20">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            <Tooltip
              formatter={(v: number) => [`${v} kWh`, 'PV-Ertrag']}
              contentStyle={{ fontSize: 11 }}
            />
            <Bar dataKey="kwh" radius={[2, 2, 0, 0]}>
              {chartData.map((entry, i) => (
                <Cell
                  key={i}
                  fill={
                    entry.kwh >= max * 0.8 ? '#f59e0b'
                      : entry.kwh >= max * 0.5 ? '#fbbf24'
                        : '#fde68a'
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex justify-between text-xs text-gray-400 mt-0.5">
        <span>{chartData[0]?.name}</span>
        <span>{chartData[chartData.length - 1]?.name}</span>
      </div>
    </div>
  )
}

// =============================================================================
// Amortisations-Fortschritt
// =============================================================================

function AmortisationsBar({ data }: { data: CockpitUebersicht }) {
  const invest = data.investition_gesamt_euro
  const kumuliert = data.netto_ertrag_euro
  const progress = Math.min(100, Math.max(0, (kumuliert / invest) * 100))

  let amortJahr: number | null = null
  if (data.anzahl_monate > 0 && kumuliert > 0 && progress < 100) {
    const jaehrlich = kumuliert / (data.anzahl_monate / 12)
    if (jaehrlich > 0) {
      amortJahr = new Date().getFullYear() + Math.ceil((invest - kumuliert) / jaehrlich)
    }
  }

  return (
    <div className="mt-4 p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
          Amortisationsfortschritt
        </span>
        <span className="text-xs text-emerald-600 dark:text-emerald-400">
          {progress.toFixed(1)} % &nbsp;·&nbsp;
          {Math.round(kumuliert).toLocaleString('de')} € von {Math.round(invest).toLocaleString('de')} €
        </span>
      </div>
      <div className="h-3 bg-emerald-200 dark:bg-emerald-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-emerald-500 rounded-full transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>
      {progress >= 100
        ? <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 font-medium">✓ Investition vollständig amortisiert!</p>
        : amortJahr && (
          <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
            Voraussichtliche Amortisation: ca. {amortJahr}
          </p>
        )
      }
    </div>
  )
}

// =============================================================================
// Community-Teaser
// =============================================================================

function CommunityTeaser() {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate('/community')}
      className="w-full text-left card p-4 border border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-900/20 hover:shadow-md transition-shadow group"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-yellow-100 dark:bg-yellow-800/50 rounded-lg">
            <Trophy className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
          </div>
          <div>
            <p className="text-sm font-medium text-yellow-900 dark:text-yellow-100">Community-Vergleich aktiv</p>
            <p className="text-xs text-yellow-700 dark:text-yellow-300">Deine Anlage wird mit anderen verglichen → Benchmark ansehen</p>
          </div>
        </div>
        <ChevronRight className="h-4 w-4 text-yellow-500 group-hover:text-yellow-700 transition-colors flex-shrink-0" />
      </div>
    </button>
  )
}

// =============================================================================
// Section Components
// =============================================================================

function Section({ title, icon: Icon, children }: {
  title: string; icon: React.ElementType; children: React.ReactNode
}) {
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

function SectionLink({ title, icon: Icon, onClick, children }: {
  title: string; icon: React.ElementType; onClick: () => void; children: React.ReactNode
}) {
  return (
    <div className="space-y-3">
      <button onClick={onClick} className="flex items-center gap-2 group hover:opacity-80 transition-opacity">
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
  title: string; value: string; unit: string; subtitle?: string
  icon: React.ElementType; color: string; bgColor: string
  onClick?: () => void; formel?: string; berechnung?: string; ergebnis?: string
}

function KPICard({ title, value, unit, subtitle, icon: Icon, color, bgColor, onClick, formel, berechnung, ergebnis }: KPICardProps) {
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
          {formel
            ? <FormelTooltip formel={formel} berechnung={berechnung} ergebnis={ergebnis}>{valueContent}</FormelTooltip>
            : valueContent
          }
        </div>
        {subtitle && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate">{subtitle}</p>}
      </div>
      <div className={`p-2 rounded-lg ${bgColor} ml-2 flex-shrink-0`}>
        <Icon className={`h-5 w-5 ${color}`} />
      </div>
    </div>
  )

  if (onClick) {
    return <button onClick={onClick} className="card p-3 text-left hover:shadow-md transition-shadow w-full">{content}</button>
  }
  return <Card className="p-3">{content}</Card>
}

// =============================================================================
// Quick Link
// =============================================================================

function QuickLink({ title, description, onClick }: { title: string; description: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="card p-4 text-left hover:shadow-md transition-shadow group">
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
