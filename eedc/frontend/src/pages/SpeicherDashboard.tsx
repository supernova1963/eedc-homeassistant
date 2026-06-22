/**
 * Speicher
 * Zeigt Statistiken: Zyklen, Effizienz, Ladung/Entladung, Eigenverbrauchserhöhung
 */

import { Fragment, useState, useEffect } from 'react'
import { Battery, DollarSign } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard, QuelleBadge, FormelTooltip, fmtCalc } from '../components/ui'
import { useSelectedAnlage } from '../hooks'
import type { Anlage } from '../types'
import { fmtKpi, WIRKUNGSGRAD_QUELLE_LABELS, SPEICHER_KPI } from '../lib'
import { investitionenApi } from '../api'
import type { SpeicherDashboardResponse } from '../api/investitionen'
import { SpeicherVerlaufCharts } from '../components/speicher'

export default function SpeicherDashboard() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const [dashboards, setDashboards] = useState<SpeicherDashboardResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedAnlageId) return

    const loadDashboard = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await investitionenApi.getSpeicherDashboard(selectedAnlageId)
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
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  const showSelector = anlagen.length > 1
  const selectorProps = { anlagen, selectedAnlageId, setSelectedAnlageId }

  return (
    <div className="space-y-6">
      {error && <Alert type="error">{error}</Alert>}

      {loading ? (
        <LoadingSpinner text="Lade Speicher Daten..." />
      ) : dashboards.length === 0 ? (
        <>
          <PlaceholderHeader showSelector={showSelector} {...selectorProps} />
          <Card>
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <Battery className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Kein Speicher für diese Anlage erfasst.</p>
              <p className="text-sm mt-2">Füge einen Speicher unter "Investitionen" hinzu.</p>
            </div>
          </Card>
        </>
      ) : (
        dashboards.map((dashboard, idx) => (
          <Fragment key={dashboard.investition.id}>
            {idx > 0 && <hr className="border-t border-gray-200 dark:border-gray-700" />}
            <SpeicherBlock
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
    <div className="flex items-center justify-end flex-wrap gap-4">
      <AnlageSelector {...props} />
    </div>
  )
}

function SpeicherBlock({ dashboard, ...selectorProps }: { dashboard: SpeicherDashboardResponse } & SelectorProps) {
  const { investition, monatsdaten, zusammenfassung, effizienz_verlauf } = dashboard
  const z = zusammenfassung

  // Etappe C (#264): TEP-basierte KPIs — fallen auf die bestehenden Werte
  // zurück, wenn das Backend keine belastbare Datenbasis hat.
  const istEta = z.ist_wirkungsgrad_prozent ?? null
  const etaQuelle = z.wirkungsgrad_quelle
  const etaAlarm = z.eta_degradation_alarm === true
  const ladepreisCent = z.effektiver_ladepreis_cent ?? z.arbitrage_avg_preis_cent
  const ladepreisQuelle = z.effektiver_ladepreis_cent != null ? z.effektiver_ladepreis_quelle : undefined

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <Battery className="h-8 w-8 text-green-500 flex-shrink-0" />
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white truncate">
              {investition.bezeichnung}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {z.kapazitaet_kwh} kWh Kapazität • {z.anzahl_monate} Monate Daten
            </p>
          </div>
        </div>
        <AnlageSelector {...selectorProps} />
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        <KPICard
          {...SPEICHER_KPI.vollzyklen}
          value={z.vollzyklen.toFixed(0)}
          formel="Vollzyklen = Ladung ÷ Kapazität"
          berechnung={`${z.gesamt_ladung_kwh.toFixed(0)} kWh ÷ ${z.kapazitaet_kwh} kWh`}
          ergebnis={`= ${z.vollzyklen.toFixed(1)} Zyklen`}
        />
        <KPICard
          {...SPEICHER_KPI.wirkungsgrad}
          value={fmtKpi(istEta != null ? istEta : z.effizienz_prozent, 1)}
          unit="%"
          color={etaAlarm ? 'red' : SPEICHER_KPI.wirkungsgrad.color}
          subtitle={
            istEta != null && etaQuelle
              ? `IST · ${WIRKUNGSGRAD_QUELLE_LABELS[etaQuelle] ?? etaQuelle}`
              : undefined
          }
          formel={
            istEta != null
              ? 'η (IST), SoC-korrigiert: (Entladung + ΔSoC) ÷ Ladung'
              : 'Effizienz = Entladung ÷ Ladung × 100'
          }
          berechnung={`${z.gesamt_entladung_kwh.toFixed(0)} kWh ÷ ${z.gesamt_ladung_kwh.toFixed(0)} kWh × 100`}
          ergebnis={
            istEta != null
              ? `= ${istEta.toFixed(1)} % η`
              : (z.effizienz_prozent ? `= ${z.effizienz_prozent.toFixed(1)} %` : '—')
          }
        />
        <KPICard
          {...SPEICHER_KPI.durchsatz}
          value={(z.gesamt_entladung_kwh / 1000).toFixed(1)}
          unit="MWh"
          formel="Durchsatz = Σ Entladung"
          berechnung={`${z.gesamt_entladung_kwh.toFixed(0)} kWh`}
          ergebnis={`= ${(z.gesamt_entladung_kwh / 1000).toFixed(2)} MWh`}
        />
        <KPICard
          {...SPEICHER_KPI.ersparnis}
          value={z.ersparnis_euro.toFixed(0)}
          unit="€"
          trend={z.ersparnis_euro > 0 ? 'up' : undefined}
          formel="Ersparnis = Entladung × (Strompreis − Einspeisevergütung)"
          berechnung={`${z.gesamt_entladung_kwh.toFixed(0)} kWh × Spread`}
          ergebnis={`= ${z.ersparnis_euro.toFixed(2)} €`}
        />
      </div>

      {/* Etappe C (#264): Degradations-Alarm — η-IST > 5 pp unter Parameter */}
      {etaAlarm && istEta != null && z.param_wirkungsgrad_prozent != null && (
        <Alert type="warning">
          Gemessener Wirkungsgrad ({istEta.toFixed(1)} %) liegt mehr als 5 Prozentpunkte
          unter dem Parameter-Wert ({z.param_wirkungsgrad_prozent.toFixed(1)} %) — möglicher
          Hinweis auf Speicher-Degradation. Wert prüfen, ggf. Parameter anpassen.
        </Alert>
      )}

      {/* Invariante: kumulativ kann Entladung nie die Ladung übersteigen. */}
      {z.durchsatz_inkonsistent && (
        <Alert type="warning">
          Die kumulierte Entladung übersteigt die kumulierte Ladung — über die
          gesamte Historie physikalisch unmöglich. Bitte die erfassten Lade- und
          Entlade-Werte prüfen (beim Datenübertrag leicht vertauscht).
        </Alert>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
          <p className="text-sm text-blue-600 dark:text-blue-400">Ladung gesamt</p>
          <p className="text-2xl font-bold text-blue-700 dark:text-blue-300">
            {z.gesamt_ladung_kwh.toFixed(0)} kWh
          </p>
        </div>
        <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
          <p className="text-sm text-green-600 dark:text-green-400">Entladung gesamt</p>
          <p className="text-2xl font-bold text-green-700 dark:text-green-300">
            {z.gesamt_entladung_kwh.toFixed(0)} kWh
          </p>
        </div>
        <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
          <p className="text-sm text-purple-600 dark:text-purple-400">Zyklen/Monat</p>
          <FormelTooltip
            formel="Vollzyklen ÷ Anzahl Monate"
            berechnung={`${fmtCalc(z.vollzyklen, 0)} ÷ ${fmtCalc(z.anzahl_monate, 0)} Monate`}
            ergebnis={`= ${fmtCalc(z.zyklen_pro_monat, 1)}`}
          >
            <p className="text-2xl font-bold text-purple-700 dark:text-purple-300">
              {z.zyklen_pro_monat.toFixed(1)}
            </p>
          </FormelTooltip>
        </div>
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">Verlust</p>
          <FormelTooltip
            formel="Ladung − Entladung"
            berechnung={`${fmtCalc(z.gesamt_ladung_kwh, 0)} kWh − ${fmtCalc(z.gesamt_entladung_kwh, 0)} kWh`}
            ergebnis={`= ${fmtCalc(z.gesamt_ladung_kwh - z.gesamt_entladung_kwh, 0)} kWh`}
          >
            <p className="text-2xl font-bold text-gray-700 dark:text-gray-300">
              {(z.gesamt_ladung_kwh - z.gesamt_entladung_kwh).toFixed(0)} kWh
            </p>
          </FormelTooltip>
        </div>
      </div>

      {/* Arbitrage Section (wenn aktiv) */}
      {z.arbitrage_faehig && z.arbitrage_kwh > 0 && (
        <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-4 border border-amber-200 dark:border-amber-800">
          <div className="flex items-center gap-2 mb-3">
            <DollarSign className="h-5 w-5 text-amber-600 dark:text-amber-400" />
            <h3 className="font-medium text-amber-800 dark:text-amber-200">Arbitrage (Netzladung)</h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
            <div>
              <p className="text-sm text-amber-600 dark:text-amber-400">Netzladung</p>
              <p className="text-xl font-bold text-amber-700 dark:text-amber-300">
                {z.arbitrage_kwh.toFixed(0)} kWh
              </p>
            </div>
            <div>
              <p className="text-sm text-amber-600 dark:text-amber-400">Ø Ladepreis</p>
              <p className="text-xl font-bold text-amber-700 dark:text-amber-300">
                {ladepreisCent != null ? `${ladepreisCent.toFixed(1)} ct/kWh` : '-'}
              </p>
              {ladepreisQuelle && (
                <QuelleBadge quelle={ladepreisQuelle} kind="ladepreis" className="mt-1" />
              )}
            </div>
            <div>
              <p className="text-sm text-amber-600 dark:text-amber-400">Anteil an Ladung</p>
              <FormelTooltip
                formel="Netzladung ÷ Gesamtladung × 100"
                berechnung={`${fmtCalc(z.arbitrage_kwh, 0)} kWh ÷ ${fmtCalc(z.gesamt_ladung_kwh, 0)} kWh × 100`}
                ergebnis={`= ${fmtCalc((z.arbitrage_kwh / z.gesamt_ladung_kwh) * 100, 1)} %`}
              >
                <p className="text-xl font-bold text-amber-700 dark:text-amber-300">
                  {((z.arbitrage_kwh / z.gesamt_ladung_kwh) * 100).toFixed(0)} %
                </p>
              </FormelTooltip>
            </div>
            <div>
              <p className="text-sm text-amber-600 dark:text-amber-400">Arbitrage-Gewinn</p>
              <FormelTooltip
                formel="Netzladung × (Strompreis − Ø Ladepreis)"
                ergebnis={`= +${fmtCalc(z.arbitrage_gewinn_euro, 2)} €`}
              >
                <p className="text-xl font-bold text-green-600 dark:text-green-400">
                  +{z.arbitrage_gewinn_euro.toFixed(0)} €
                </p>
              </FormelTooltip>
            </div>
          </div>
        </div>
      )}

      {/* Charts + Monatstabelle — geteilte IST-Komponente (auch im IA-v4-Hub). */}
      <SpeicherVerlaufCharts
        monatsdaten={monatsdaten}
        zusammenfassung={z}
        effizienzVerlauf={effizienz_verlauf}
      />
    </div>
  )
}
