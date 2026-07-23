/**
 * AuswertungenFinanzenV4 — Finanz-Auswertung (A.5 Sub 3, SLICE-2-Neukonzept).
 *
 * Drei verschiebbare BlockShell-Blöcke (SPEC-AUSWERTUNGEN §0a):
 *   ① Finanz-Übersicht (Zeitverlauf) — KPI-Strip + Sonderkosten-Hinweis + Bilanz-Bar
 *      + Kumuliert-Area + Netto-Composed + Ø-Karte (recompute via createMonatsZeitreihe
 *      + getKomponentenZeitreihe, NICHT der FinanzenTab-Verbatim-Embed)
 *   ② SOLL/HABEN-T-Konto — geteilter `TKonto`-SoT mit Monat|Jahr-Umschalter, der das
 *      Jahr vom Filter ERBT (R5: kein zweiter Jahr-`<select>`); Jahr = Σ-12.
 *   ③ Berichte & Dokumente — PDF-Finanzbericht-Teaser (G10) + CSV.
 *
 * Regel-SoT: R1 alle Zahlen via `fmtZahl`/`formatGeld` (kein `.toFixed`) · R2 Geld in €
 * ohne k€-Transform · R5 EINE Zeit-Steuerung (Dispatcher-Jahr; T-Konto erbt) · R6 KPIs +
 * Charts parkbar.
 *
 * R18-3 (Option B): `basis` (Daten + Jahr-Filter) kommt als Prop aus dem
 * Dispatcher (`AuswertungenV4`) — der Filter sitzt in dessen Steuerleiste,
 * die Auswahl überlebt den Sub-Tab-Wechsel. R18-3b: bei „Alle Jahre" zeigt das
 * T-Konto sichtbar gekennzeichnet das neueste Jahr (`ZeitraumHinweis`) statt
 * still zu verengen.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart, Bar, ComposedChart, AreaChart, Area, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { Euro, TrendingUp, Wallet, FileText } from 'lucide-react'
import { Card, buttonClasses, ChartLegende, CsvExportButton, SegmentControl, Select, eedcTooltipProps, FehlerZustand, TabellenSkeleton } from '../components/ui'
import { BlockShell, BlockStackSkeleton, KpiStrip, type Block, type KpiStripItem } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar, usePark } from '../components/park'
import { TKonto } from '../components/finanzen/TKonto'
import { COLORS, GELD_COLORS, GELD_TEXT_CLASS, MONAT_NAMEN, STATUS_ICONS, formatGeld, fmtZahl, xAchse, yAchse, achsenEinheit, ACHSEN_MARGIN_TOP } from '../lib'
import { exportToCSV } from '../utils/export'
import { createMonatsZeitreihe } from '../pages/auswertung/types'
import { aktuellerMonatApi, type AktuellerMonatResponse } from '../api/aktuellerMonat'
import { cockpitApi, type KomponentenZeitreihe } from '../api/cockpit'
import { importApi } from '../api/import'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import { baueJahrAlsMonat } from './JahrAggregat'
import { STEUER_H } from '../lib/komponentenStyle'
import { useApiData, useLegendenToggle, useSelectedAnlage, useSchmaleAchse } from '../hooks'
import type { AuswertungBasis } from './useAuswertungBasis'
import { AuswertungKopf } from './AuswertungKopf'
import { ZeitraumHinweis } from './ZeitraumHinweis'
import { AnlageLeer } from './OnboardingLeer'

const SICHT_KEY = 'v4-auswertungen-finanzen'
const MONATE_1_12 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
const euroTick = (v: number) => fmtZahl(v, 0)

export default function AuswertungenFinanzenV4({ basis }: { basis: AuswertungBasis }) {
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <FinanzenInner basis={basis} />
    </ParkProvider>
  )
}

function FinanzenInner({ basis }: { basis: AuswertungBasis }) {
  const park = usePark()
  const { anlagen, selectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()

  // Sonderkosten/Sonstige (#310) je Monat — wie FinanzenTab aus der Komponenten-Zeitreihe.
  // R18-2 (SWR): via Sicht-Cache — beim Sub-Tab-Wechsel sofort da; Soft-fail
  // (catch → null) bleibt erhalten.
  const sonderkostenQ = useApiData<KomponentenZeitreihe | null>(
    () => cockpitApi.getKomponentenZeitreihe(selectedAnlageId!).catch(() => null),
    [selectedAnlageId],
    { enabled: !!selectedAnlageId, swrKey: `v4-ausw-sonderkosten:${selectedAnlageId}` },
  )
  const sonderkostenData = selectedAnlageId ? (sonderkostenQ.data ?? null) : null

  const schmal = useSchmaleAchse()
  // B7-Legenden-Toggle; Netto-Chart: Bar+Line teilen den dataKey → Name als Toggle-Key.
  const bilanzLegende = useLegendenToggle()
  const nettoLegende = useLegendenToggle()
  const zeitreihe = useMemo(
    () => (basis.strompreis ? createMonatsZeitreihe(basis.gefiltert, undefined, basis.strompreis, basis.alleTarife) : []),
    [basis.gefiltert, basis.strompreis, basis.alleTarife],
  )

  const sonstigeByMonth = useMemo(() => {
    const map = new Map<string, { ertraege: number; ausgaben: number; netto: number }>()
    sonderkostenData?.monatswerte?.forEach((m) => {
      map.set(`${m.jahr}-${m.monat}`, {
        ertraege: m.sonstige_ertraege_euro || 0,
        ausgaben: m.sonstige_ausgaben_euro || 0,
        netto: m.sonstige_netto_euro || 0,
      })
    })
    return map
  }, [sonderkostenData])

  const chartData = useMemo(() => {
    let kumuliert = 0
    return zeitreihe.map((z) => {
      const s = sonstigeByMonth.get(`${z.jahr}-${z.monat}`)
      const nettoMitSonder = z.netto_ertrag + (s?.netto || 0)
      kumuliert += nettoMitSonder
      return { ...z, sonderkosten: s?.ausgaben || 0, netto_nach_sonderkosten: nettoMitSonder, kumuliert_ertrag: kumuliert }
    })
  }, [zeitreihe, sonstigeByMonth])

  const gesamt = useMemo(() => {
    const einspeiseErloes = chartData.reduce((s, z) => s + z.einspeise_erloes, 0)
    const netzbezugKosten = chartData.reduce((s, z) => s + z.netzbezug_kosten, 0)
    const eigenverbrauchErsparnis = chartData.reduce((s, z) => s + z.ev_ersparnis, 0)
    const sonderkosten = chartData.reduce((s, z) => s + (z.sonderkosten || 0), 0)
    const sonstigeErtraege = chartData.reduce((s, z) => s + (sonstigeByMonth.get(`${z.jahr}-${z.monat}`)?.ertraege || 0), 0)
    const nettoErtrag = einspeiseErloes + eigenverbrauchErsparnis
    const nettoNachSonderkosten = nettoErtrag + sonstigeErtraege - sonderkosten
    return { einspeiseErloes, netzbezugKosten, eigenverbrauchErsparnis, sonderkosten, sonstigeErtraege, nettoErtrag, nettoNachSonderkosten }
  }, [chartData, sonstigeByMonth])

  const monate = basis.stats.anzahlMonate || 1
  const hatMehrereTarife = (basis.alleTarife?.length || 0) > 1
  const strompreis = basis.strompreis

  const handleCsv = useCallback(() => {
    const headers = ['Monat', 'Einspeiseerlös (€)', 'EV-Ersparnis (€)', 'Netzbezug-Kosten (€)',
      'Netto-Ertrag (€)', 'Sonderkosten (€)', 'Netto nach Sonderkosten (€)', 'Kumulierter Ertrag (€)']
    const rows = chartData.map((z) => [z.name, z.einspeise_erloes, z.ev_ersparnis, z.netzbezug_kosten,
      z.netto_ertrag, z.sonderkosten, z.netto_nach_sonderkosten, z.kumuliert_ertrag])
    exportToCSV(headers, rows, 'finanzen_export.csv')
  }, [chartData])

  // T-Konto erbt das Jahr vom Filter (R5). 'alle' → neuestes Jahr, sichtbar
  // gekennzeichnet (R18-3b: vorher stille Verengung ohne Hinweis).
  const jahrFuerTKonto = basis.jahr === 'alle' ? (basis.jahre[0] ?? null) : basis.jahr

  const bloecke: Block[] = useMemo(() => {
    if (!strompreis) {
      return [{
        id: 'kein-tarif', title: 'Finanz-Übersicht', icon: Wallet, farbe: 'text-green-500', defaultOpen: true,
        render: () => (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Bitte einen Stromtarif konfigurieren, um Finanzauswertungen zu sehen.
          </p>
        ),
      }]
    }

    const kpis: KpiStripItem[] = [
      {
        title: 'Einspeiseerlös', value: formatGeld(gesamt.einspeiseErloes).wert, unit: '€', color: 'green', icon: TrendingUp,
        subtitle: hatMehrereTarife ? 'historische Tarife' : `${fmtZahl(strompreis.einspeiseverguetung_cent_kwh, 1)} ct/kWh`,
        parkId: 'kpi:einspeise', formel: hatMehrereTarife ? 'Σ (Einspeisung × Tarif) pro Monat' : 'Einspeisung × Einspeisevergütung',
        berechnung: `${fmtZahl(basis.stats.gesamtEinspeisung, 0)} kWh gesamt`, ergebnis: `= ${fmtZahl(gesamt.einspeiseErloes, 2)} €`,
      },
      {
        title: 'EV-Ersparnis', value: formatGeld(gesamt.eigenverbrauchErsparnis).wert, unit: '€', color: 'purple', icon: Euro,
        subtitle: 'vermiedener Netzbezug', parkId: 'kpi:ev-ersparnis',
        formel: hatMehrereTarife ? 'Σ (Eigenverbrauch × Tarif) pro Monat' : 'Eigenverbrauch × Netzbezugspreis',
        berechnung: `${fmtZahl(basis.stats.gesamtEigenverbrauch, 0)} kWh gesamt`, ergebnis: `= ${fmtZahl(gesamt.eigenverbrauchErsparnis, 2)} €`,
      },
      {
        title: 'Netzbezug-Kosten', value: formatGeld(gesamt.netzbezugKosten).wert, unit: '€', color: 'red', icon: Euro,
        subtitle: 'inkl. Grundpreis, historische Tarife', parkId: 'kpi:netzbezug',
        formel: 'Σ (Netzbezug × Tarif + Grundpreis) pro Monat',
        berechnung: `${fmtZahl(basis.stats.gesamtNetzbezug, 0)} kWh gesamt`, ergebnis: `= ${fmtZahl(gesamt.netzbezugKosten, 2)} €`,
      },
      {
        title: 'Netto-Ertrag', value: formatGeld(gesamt.nettoNachSonderkosten).wert, unit: '€', color: 'blue', icon: Euro,
        parkId: 'kpi:netto',
        subtitle: gesamt.sonstigeErtraege > 0 && gesamt.sonderkosten > 0
          ? `inkl. +${fmtZahl(gesamt.sonstigeErtraege, 0)} € / −${fmtZahl(gesamt.sonderkosten, 0)} € Sonstige`
          : gesamt.sonstigeErtraege > 0 ? `inkl. +${fmtZahl(gesamt.sonstigeErtraege, 0)} € Sonstige Erträge`
          : gesamt.sonderkosten > 0 ? `nach ${fmtZahl(gesamt.sonderkosten, 0)} € Sonderkosten` : 'Gesamt',
        formel: gesamt.sonstigeErtraege > 0 || gesamt.sonderkosten > 0
          ? 'Einspeiseerlös + EV-Ersparnis + Sonstige Erträge − Sonderkosten' : 'Einspeiseerlös + EV-Ersparnis',
        berechnung: `${fmtZahl(gesamt.einspeiseErloes, 2)} € + ${fmtZahl(gesamt.eigenverbrauchErsparnis, 2)} €`,
        ergebnis: `= ${fmtZahl(gesamt.nettoNachSonderkosten, 2)} €`,
      },
    ]

    const blockUebersicht: Block = {
      id: 'uebersicht', title: 'Finanz-Übersicht', icon: Wallet, farbe: 'text-green-500',
      summary: `Netto ${formatGeld(gesamt.nettoNachSonderkosten).text} · ${monate} Monate`, defaultOpen: true,
      render: () => (
        <div className="space-y-4">
          <KpiStrip kpis={kpis} />
          {gesamt.sonderkosten > 0 && (
            <Parkbar id="hinweis:sonderkosten" titel="Sonderkosten-Hinweis">
              <Card className="bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800">
                <div className="flex items-center gap-3">
                  <STATUS_ICONS.warnung className="h-5 w-5 text-amber-600 dark:text-amber-400 flex-shrink-0" />
                  <div>
                    <h4 className="font-medium text-amber-800 dark:text-amber-200">
                      Sonderkosten im Zeitraum: {fmtZahl(gesamt.sonderkosten, 2)} €
                    </h4>
                    <p className="text-sm text-amber-700 dark:text-amber-300">
                      Reparaturen, Wartung und sonstige Kosten werden vom Netto-Ertrag abgezogen.
                    </p>
                  </div>
                </div>
              </Card>
            </Parkbar>
          )}
          <Parkbar id="chart:bilanz" titel="Finanzielle Bilanz pro Monat">
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Finanzielle Bilanz pro Monat</p>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: ACHSEN_MARGIN_TOP, right: 8, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                    {/* D11-10: viele Monatslabels (bis ~37) → −45° auch auf Desktop */}
                    <XAxis dataKey="name" {...xAchse(schmal, true)} interval="preserveStartEnd" /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                    <YAxis tickFormatter={euroTick} {...yAchse(schmal)} label={achsenEinheit('€')} />
                    <Tooltip {...eedcTooltipProps({ unit: '€', decimals: 2 })} />
                    <Legend content={<ChartLegende onItemClick={bilanzLegende.onItemClick} />} />
                    <Bar dataKey="einspeise_erloes" name="Einspeiseerlös" fill={COLORS.feedin} stackId="pos" hide={bilanzLegende.istVersteckt('einspeise_erloes')} />
                    <Bar dataKey="ev_ersparnis" name="EV-Ersparnis" fill={COLORS.consumption} stackId="pos" hide={bilanzLegende.istVersteckt('ev_ersparnis')} />
                    <Bar dataKey="netzbezug_kosten" name="Netzbezug (Kosten)" fill={COLORS.grid} hide={bilanzLegende.istVersteckt('netzbezug_kosten')} />
                    {gesamt.sonderkosten > 0 && <Bar dataKey="sonderkosten" name="Sonderkosten" fill={GELD_COLORS.kosten} hide={bilanzLegende.istVersteckt('sonderkosten')} />}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </Parkbar>
          <Parkbar id="chart:kumuliert" titel="Kumulierter Netto-Ertrag">
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Kumulierter Netto-Ertrag</p>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: ACHSEN_MARGIN_TOP, right: 8, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                    <XAxis dataKey="name" {...xAchse(schmal)} interval="preserveStartEnd" /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                    <YAxis tickFormatter={euroTick} {...yAchse(schmal)} label={achsenEinheit('€')} />
                    <Tooltip {...eedcTooltipProps({ unit: '€', decimals: 0, cursor: false })} />
                    <Area type="monotone" dataKey="kumuliert_ertrag" name="Kumulierter Ertrag"
                      stroke={COLORS.feedin} fill={COLORS.feedin} fillOpacity={0.3} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-2 flex items-center justify-center gap-3 text-sm">
                <span className="text-gray-500 dark:text-gray-400">Gesamt nach {monate} Monaten:</span>
                <span className={`text-lg font-semibold ${GELD_TEXT_CLASS.netto}`}>{fmtZahl(gesamt.nettoNachSonderkosten, 0)} €</span>
              </div>
            </div>
          </Parkbar>
          <Parkbar id="chart:netto" titel="Netto-Ertrag pro Monat">
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                Netto-Ertrag pro Monat {gesamt.sonderkosten > 0 && '(nach Sonderkosten)'}
              </p>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartData} margin={{ top: ACHSEN_MARGIN_TOP, right: 8, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                    <XAxis dataKey="name" {...xAchse(schmal)} interval="preserveStartEnd" /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                    <YAxis tickFormatter={euroTick} {...yAchse(schmal)} label={achsenEinheit('€')} />
                    <Tooltip {...eedcTooltipProps({ unit: '€', decimals: 2 })} />
                    {/* D12-5: Legende fehlte (2 Serien Netto-Ertrag + Trend) — wie Chart 1. */}
                    <Legend content={<ChartLegende onItemClick={(e) => nettoLegende.toggleSerie(String(e.value))} />} />
                    <Bar dataKey="netto_nach_sonderkosten" name="Netto-Ertrag" fill={COLORS.feedin} opacity={0.7} hide={nettoLegende.istVersteckt('Netto-Ertrag')} />
                    <Line type="monotone" dataKey="netto_nach_sonderkosten" name="Trend" stroke={COLORS.solar} strokeWidth={2} dot={false} hide={nettoLegende.istVersteckt('Trend')} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          </Parkbar>
          <Parkbar id="tabelle:durchschnitt" titel="Durchschnittswerte">
          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <p className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Durchschnittswerte</p>
            <div className={`grid grid-cols-2 gap-3 text-sm ${gesamt.sonderkosten > 0 ? 'md:grid-cols-5' : 'md:grid-cols-4'}`}>
              <div><p className="text-gray-500 dark:text-gray-400">Ø Einspeiseerlös/Monat</p><p className={`font-medium ${GELD_TEXT_CLASS.ertrag}`}>{fmtZahl(gesamt.einspeiseErloes / monate, 0)} €</p></div>
              <div><p className="text-gray-500 dark:text-gray-400">Ø EV-Ersparnis/Monat</p><p className={`font-medium ${GELD_TEXT_CLASS.ersparnis}`}>{fmtZahl(gesamt.eigenverbrauchErsparnis / monate, 0)} €</p></div>
              <div><p className="text-gray-500 dark:text-gray-400">Ø Netzbezug-Kosten/Monat</p><p className={`font-medium ${GELD_TEXT_CLASS.kosten}`}>{fmtZahl(gesamt.netzbezugKosten / monate, 0)} €</p></div>
              {/* E3 (R3b, Gernot 2026-07-05): Sonderkosten bewusst Amber = Hinweis-Rolle
                  („negativ, aber kein Fehler"), NICHT Kosten-Rot — dokumentierte Ausnahme. */}
              {gesamt.sonderkosten > 0 && (
                <div><p className="text-gray-500 dark:text-gray-400">Ø Sonderkosten/Monat</p><p className="font-medium text-amber-600 dark:text-amber-400">{fmtZahl(gesamt.sonderkosten / monate, 0)} €</p></div>
              )}
              <div><p className="text-gray-500 dark:text-gray-400">Ø Netto-Ertrag/Monat</p><p className={`font-medium ${GELD_TEXT_CLASS.netto}`}>{fmtZahl(gesamt.nettoNachSonderkosten / monate, 0)} €</p></div>
            </div>
          </div>
          </Parkbar>
        </div>
      ),
    }

    const blockTKonto: Block = {
      id: 'tkonto', title: 'SOLL/HABEN-T-Konto', icon: Wallet, farbe: 'text-blue-500',
      summary: 'Kosten vs. Erlöse + Einsparungen (Monat oder Jahr)', defaultOpen: true,
      // D17-15: parkbar, damit der Block ganz weggeräumt werden kann (kein Rest).
      render: () => (
        <Parkbar id="tabelle:tkonto" titel="SOLL/HABEN-T-Konto">
          <div className="space-y-3">
            {basis.jahr === 'alle' && jahrFuerTKonto != null && (
              <ZeitraumHinweis text={`Filter „Alle Jahre“: das T-Konto bildet einen Monat oder ein Jahr ab und zeigt das Jahr ${jahrFuerTKonto}.`} />
            )}
            <TKontoPeriode anlageId={selectedAnlageId} daten={basis.daten} jahr={jahrFuerTKonto} />
          </div>
        </Parkbar>
      ),
    }

    const blockBerichte: Block = {
      id: 'berichte', title: 'Berichte & Dokumente', icon: FileText, farbe: 'text-gray-400 dark:text-gray-500',
      summary: 'Finanzbericht (PDF) · CSV-Export', defaultOpen: false,
      // D17-15: parkbar, damit der Block ganz weggeräumt werden kann (kein Rest).
      render: () => (
        <Parkbar id="doku:berichte" titel="Berichte & Dokumente">
          <div className="space-y-3">
            <FinanzberichtTeaser anlageId={selectedAnlageId} jahr={basis.jahr} />
            {/* D13-10/D14-18: Icon + Wort IMMER (CsvExportButton-SoT). */}
            <CsvExportButton onClick={handleCsv} label="CSV-Export (Monatswerte)" />
          </div>
        </Parkbar>
      ),
    }

    // Auto-Hide (Phase 3b, Gernot 2026-07-09): Block entfällt, wenn ALLE seine real
    // gerenderten Park-Elemente geparkt sind (wie Cockpit-Bilanz via bilanzParkIds).
    const uebersichtIds = ['kpi:einspeise', 'kpi:ev-ersparnis', 'kpi:netzbezug', 'kpi:netto',
      ...(gesamt.sonderkosten > 0 ? ['hinweis:sonderkosten'] : []),
      'chart:bilanz', 'chart:kumuliert', 'chart:netto', 'tabelle:durchschnitt']
    const sichtbar = (ids: string[]) => !ids.every((id) => park.istGeparkt(id))
    return [
      ...(sichtbar(uebersichtIds) ? [blockUebersicht] : []),
      ...(sichtbar(['tabelle:tkonto']) ? [blockTKonto] : []),
      ...(sichtbar(['doku:berichte']) ? [blockBerichte] : []),
    ]
    // bilanzLegende/nettoLegende in den Deps: `istVersteckt` wechselt Identität genau
    // beim Toggle → die memoisierten render-Closures sehen nie stalen Versteck-Zustand.
  }, [strompreis, gesamt, chartData, monate, hatMehrereTarife, basis.stats, basis.daten, basis.jahr, jahrFuerTKonto, selectedAnlageId, schmal, handleCsv, park, bilanzLegende, nettoLegende])

  if (basis.error) {
    // B8 (S15): Basis-Fetch-Fehler sichtbar machen — vorher 0-Wert-KPIs (stille Leere).
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <FehlerZustand text={basis.error} onRetry={basis.refresh} />
      </div>
    )
  }
  if (anlagenLoading || basis.loading) {
    // B8 (S15): Sicht-Skeleton in BlockShell-Form (3 Blöcke) statt Vollseiten-Spinner.
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <BlockStackSkeleton label="Lade Finanzdaten…" zu={2} />
      </div>
    )
  }
  if (anlagen.length === 0) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <AnlageLeer titel="Noch keine Anlage angelegt." />
      </div>
    )
  }

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      <AuswertungKopf titel="Finanzen" />
      {/* Kein `key={jahr}` → BlockShell re-rendert in-place beim Jahreswechsel
          (detLAN D7-6, 2026-06-27), statt sichtbar zu remounten. */}
      <BlockShell persistKey={SICHT_KEY} bloecke={bloecke} sortierbar />
      <ParkFuss />
    </div>
  )
}

/** T-Konto mit Monat|Jahr-Umschalter. Das Jahr kommt vom Sicht-Kopf (R5, Prop `jahr`),
 *  der Block wählt nur Monat-im-Jahr vs. Ganzjahr-Σ (`baueJahrAlsMonat`, kein Backend). */
function TKontoPeriode({ anlageId, daten, jahr }: {
  anlageId: number | undefined | null
  daten: AggregierteMonatsdaten[]
  jahr: number | null
}) {
  const [modus, setModus] = useState<'monat' | 'jahr'>('monat')
  const [monat, setMonat] = useState<number | null>(null)

  // Dokumentierte F10-AUSNAHME (R3b E5, Gernot 2026-07-05): das Monats-Select
  // bleibt bewusst KALENDARISCH aufsteigend (Jan→Dez, Jahres-Kontext) — die
  // Default-Auswahl ist ohnehin der neueste Monat. F10 „absteigend" gilt
  // unverändert für Datums-LISTEN außerhalb eines Jahres-Rahmens.
  const monate = useMemo(
    () => (jahr == null ? [] : [...new Set(daten.filter((r) => r.jahr === jahr).map((r) => r.monat))].sort((a, b) => a - b)),
    [daten, jahr],
  )
  // Monat default/korrigieren = letzter im (Kopf-)Jahr.
  useEffect(() => {
    if (monate.length === 0) return
    if (monat == null || !monate.includes(monat)) setMonat(monate[monate.length - 1])
  }, [monate, monat])

  // R18-2 (SWR + keepPreviousData): beim Monat/Jahr-Umschalten bleibt das
  // bestehende T-Konto stehen und der Content tauscht in-place (detLAN D7-6);
  // beim Sub-Tab-Wechsel steht der letzte Stand sofort (Sicht-Cache).
  const tkQ = useApiData<{ d: AktuellerMonatResponse | null; sonderkosten: number | null }>(
    async () => {
      if (modus === 'monat') {
        const [resp, sk] = await Promise.all([
          aktuellerMonatApi.getData(anlageId!, jahr!, monat!).catch(() => null),
          cockpitApi.getKomponentenZeitreihe(anlageId!, jahr!)
            .then((kt) => kt.monatswerte?.find((v) => v.monat === monat)?.sonstige_ausgaben_euro ?? null)
            .catch(() => null),
        ])
        return { d: resp, sonderkosten: sk }
      }
      const resps = await Promise.all(MONATE_1_12.map((m) => aktuellerMonatApi.getData(anlageId!, jahr!, m).catch(() => null)))
      const ok = resps.filter((r): r is AktuellerMonatResponse => r != null)
      return { d: ok.length ? baueJahrAlsMonat(ok, jahr!) : null, sonderkosten: null }
    },
    [anlageId, modus, jahr, monat],
    {
      enabled: !!anlageId && jahr != null && (modus === 'jahr' || monat != null),
      swrKey: `v4-ausw-tkonto:${anlageId}:${jahr}:${modus}:${monat}`,
      keepPreviousData: true,
    },
  )
  const d = tkQ.data?.d ?? null
  const sonderkosten = tkQ.data?.sonderkosten ?? null
  const laden = tkQ.loading

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <SegmentControl
          ariaLabel="Zeitraum-Modus"
          optionen={[{ key: 'monat', label: 'Monat' }, { key: 'jahr', label: `Jahr (${jahr ?? '—'})` }]}
          value={modus} onChange={setModus}
        />
        {/* D9-E: Beide Modi belegen dieselbe Toolbar-Höhe (kein Verschwinden des
            Selects → kein Vertikal-Sprung des T-Kontos beim Monat↔Jahr-Wechsel;
            Content-Swap bleibt in-place wie D7-6). */}
        {modus === 'monat' ? (
          <Select
            steuer
            value={monat != null ? String(monat) : ''}
            onChange={(e) => setMonat(e.target.value ? Number(e.target.value) : null)}
            aria-label="Monat wählen"
            options={monate.map((m) => ({ value: String(m), label: `${MONAT_NAMEN[m]} ${jahr}` }))}
          />
        ) : (
          <span className={`text-sm text-gray-500 dark:text-gray-400 px-2 inline-flex items-center ${STEUER_H}`}>Ganzes Jahr {jahr ?? '—'}</span>
        )}
      </div>
      {laden ? (
        // Spinner nur beim Erst-Load (SWR-Hook: loading nur ohne Vor-Daten);
        // beim Monat/Jahr-Umschalten bleibt das bestehende T-Konto stehen und der
        // Content tauscht in-place (detLAN D7-6, 2026-06-27).
        <TabellenSkeleton label="Lade T-Konto…" />
      ) : d ? (
        <TKonto d={d} sonderkosten={sonderkosten} />
      ) : (
        <p className="text-sm text-gray-500 dark:text-gray-400">Für den gewählten Zeitraum liegen keine Finanzdaten vor.</p>
      )}
    </div>
  )
}

/** G10 — Cross-Link-Teaser auf den PDF-Finanzbericht.
 *  R18-8 (rapahl #208, Gernot-Entscheid): KEIN neuer Menüpunkt, kein zweiter
 *  Berichts-Ort — hier nur der EINE Wegweiser zur vollständigen Berichtsübersicht
 *  (seit jeher Einstellungen · Stammdaten · Anlage). */
function FinanzberichtTeaser({ anlageId, jahr }: { anlageId: number | undefined | null; jahr: number | 'alle' }) {
  if (!anlageId) return null
  const url = importApi.getPdfZipExportUrl(anlageId, ['finanzbericht'], jahr === 'alle' ? null : jahr)
  return (
    <div className="space-y-2">
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Finanzbericht als PDF{jahr !== 'alle' ? ` (Jahr ${jahr})` : ' (Gesamtzeitraum)'}.
      </p>
      <a href={url} className={buttonClasses({ variant: 'primary', className: 'gap-2 no-underline' })}>
        <FileText className="h-4 w-4" /> Finanzbericht (PDF)
      </a>
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Alle Berichte:{' '}
        <Link to="/einstellungen/stammdaten" className="text-primary-600 dark:text-primary-400 hover:underline">
          Einstellungen · Stammdaten · Anlage
        </Link>
      </p>
    </div>
  )
}
