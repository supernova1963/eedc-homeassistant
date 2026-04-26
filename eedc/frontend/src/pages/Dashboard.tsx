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
  Sun, Zap, Battery, TrendingUp, Flame, Car, Home,
  ArrowDownToLine, ArrowUpFromLine, Percent, Gauge, Euro, Leaf,
  Calendar, Receipt, Share2, Activity, Thermometer
} from 'lucide-react'
import { Card, Button, LoadingSpinner, Select, fmtCalc } from '../components/ui'
import { fmtKpi } from '../lib'
import {
  HeroLeiste, EnergyFlowDiagram, RingGaugeCard, SparklineChart,
  AmortisationsBar, CommunityTeaser, CommunityNudge, Section, SectionLink, KPICard,
  QuickLink, ShareTextModal, GettingStarted
} from '../components/dashboard'
import { useSelectedAnlage } from '../hooks'
import { cockpitApi } from '../api'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
import type { CockpitUebersicht } from '../api/cockpit'

export default function Dashboard() {
  const navigate = useNavigate()
  const { anlagen, selectedAnlageId, setSelectedAnlageId, selectedAnlage: anlage, loading: anlagenLoading } = useSelectedAnlage()

  const [data, setData] = useState<CockpitUebersicht | null>(null)
  const [prevYearData, setPrevYearData] = useState<CockpitUebersicht | null>(null)
  const [monatsdaten, setMonatsdaten] = useState<AggregierteMonatsdaten[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedYear, setSelectedYear] = useState<number | undefined>(undefined)
  const [availableYears, setAvailableYears] = useState<number[]>([])
  const [showShareModal, setShowShareModal] = useState(false)

  useEffect(() => {
    if (!selectedAnlageId) return

    const loadData = async () => {
      setLoading(true)
      setError(null)
      try {
        const [result, monate] = await Promise.all([
          cockpitApi.getUebersicht(selectedAnlageId, selectedYear),
          monatsdatenApi.listAggregiert(selectedAnlageId),
        ])
        setData(result)
        setMonatsdaten(monate)

        // availableYears aus ungefilterten Monatsdaten — nicht aus result.zeitraum_von/bis,
        // da result bei gesetztem selectedYear nur den gefilterten Zeitraum zurückgibt
        if (monate.length > 0) {
          const years = [...new Set(monate.map(m => m.jahr))].sort((a, b) => b - a)
          setAvailableYears(years)
        }

        // Vorjahr laden wenn ein Jahr gewählt ist
        if (selectedYear) {
          try {
            const prev = await cockpitApi.getUebersicht(selectedAnlageId, selectedYear - 1)
            setPrevYearData(prev.anzahl_monate > 0 ? prev : null)
          } catch {
            setPrevYearData(null)
          }
        } else {
          setPrevYearData(null)
        }
      } catch (err) {
        setError('Fehler beim Laden der Daten')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [selectedAnlageId, selectedYear])

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


  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Home className="h-8 w-8 text-primary-500" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Übersicht</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {anlage?.anlagenname} • {data.anlagenleistung_kwp.toFixed(1)} kWp
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {anlagen.length > 1 && (
            <Select
              compact
              value={selectedAnlageId?.toString() || ''}
              onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
              options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
            />
          )}
          <button
            onClick={() => setShowShareModal(true)}
            className="p-2 rounded-lg text-gray-400 hover:text-primary-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            aria-label="Monatstext für Social Media"
          >
            <Share2 className="h-4 w-4" />
          </button>
          <Calendar className="h-4 w-4 text-gray-400" />
          <select
            value={selectedYear || ''}
            onChange={(e) => setSelectedYear(e.target.value ? parseInt(e.target.value) : undefined)}
            aria-label="Jahr filtern"
            className="input w-auto"
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
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
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
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
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
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
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
              title="Effizienz"
              value={fmtKpi(data.speicher_effizienz_prozent, 1)}
              unit="%"
              icon={Activity}
              color="text-cyan-500"
              bgColor="bg-cyan-50 dark:bg-cyan-900/20"
              formel="Entladung ÷ Ladung × 100"
              berechnung={`${fmtCalc(data.speicher_entladung_kwh, 0)} ÷ ${fmtCalc(data.speicher_ladung_kwh, 0)} × 100`}
              ergebnis={data.speicher_effizienz_prozent ? `= ${fmtCalc(data.speicher_effizienz_prozent, 1)} %` : '---'}
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
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
            <KPICard
              title="JAZ"
              value={fmtKpi(data.wp_cop, 2)}
              unit=""
              icon={Thermometer}
              color="text-orange-500"
              bgColor="bg-orange-50 dark:bg-orange-900/20"
              formel="JAZ = Wärme ÷ Strom"
              berechnung={`${fmtCalc(data.wp_waerme_kwh, 0)} ÷ ${fmtCalc(data.wp_strom_kwh, 0)}`}
              ergebnis={data.wp_cop ? `= ${fmtCalc(data.wp_cop, 2)}` : '---'}
            />
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
              color="text-yellow-500"
              bgColor="bg-yellow-50 dark:bg-yellow-900/20"
              formel="Σ WP-Stromverbrauch"
              berechnung={`${fmtCalc(data.wp_strom_kwh, 0)} kWh`}
              ergebnis={`= ${fmtCalc(data.wp_strom_kwh / 1000, 2)} MWh`}
            />
            <KPICard
              title="Ersparnis vs. Gas"
              value={data.wp_ersparnis_euro.toFixed(0)}
              unit="€"
              icon={TrendingUp}
              color="text-green-500"
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
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
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
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
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
          {data.netzbezug_kosten_euro > 0 && (
            <KPICard
              title="Netzbezugskosten"
              value={data.netzbezug_kosten_euro.toFixed(0)}
              unit="€"
              icon={ArrowDownToLine}
              color="text-red-500"
              bgColor="bg-red-50 dark:bg-red-900/20"
              formel="Σ (Netzbezug × Strompreis + Grundpreis)"
              berechnung={`${fmtCalc(data.netzbezug_kwh, 0)} kWh × Strompreis + Grundpreis`}
              ergebnis={`= ${fmtCalc(data.netzbezug_kosten_euro, 0)} €`}
            />
          )}
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
            sicht="Gesamt-Anlage · Jahres-ROI · IST-Werte · Vollkosten"
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
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
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

      {/* Community-Teaser / Nudge */}
      {anlage?.community_hash ? <CommunityTeaser /> : monatsdaten.length >= 3 && <CommunityNudge />}

      {/* Quick Links */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <QuickLink title="Monatsdaten" description="Neue Daten erfassen oder CSV importieren" onClick={() => navigate('/einstellungen/monatsdaten')} />
        <QuickLink title="Auswertungen" description="Detaillierte Analysen und Zeitverläufe" onClick={() => navigate('/auswertungen')} />
        <QuickLink title="Investitionen" description="Komponenten verwalten" onClick={() => navigate('/einstellungen/investitionen')} />
      </div>

      {/* Share-Text Modal */}
      {showShareModal && selectedAnlageId && (
        <ShareTextModal
          anlageId={selectedAnlageId}
          availableYears={availableYears}
          monatsdaten={monatsdaten}
          onClose={() => setShowShareModal(false)}
        />
      )}
    </div>
  )
}
