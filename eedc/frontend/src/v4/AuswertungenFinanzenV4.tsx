/**
 * AuswertungenFinanzenV4 — Finanz-Auswertung (A.5 Sub 3, SLICE-2-Neukonzept).
 *
 * Drei verschiebbare BlockShell-Blöcke (SPEC-AUSWERTUNGEN §0a):
 *   ① Finanz-Übersicht (Zeitverlauf) — KPI-Strip + Sonderkosten-Hinweis + Bilanz-Bar
 *      + Kumuliert-Area + Netto-Composed + Ø-Karte (recompute via createMonatsZeitreihe
 *      + getKomponentenZeitreihe, NICHT der FinanzenTab-Verbatim-Embed)
 *   ② SOLL/HABEN-T-Konto — geteilter `TKonto`-SoT mit Monat|Jahr-Umschalter, der das
 *      Jahr vom Sicht-Kopf ERBT (R5: kein zweiter Jahr-`<select>`); Jahr = Σ-12.
 *   ③ Berichte & Dokumente — PDF-Finanzbericht-Teaser (G10) + CSV.
 *
 * Regel-SoT: R1 alle Zahlen via `fmtZahl`/`formatGeld` (kein `.toFixed`) · R2 Geld in €
 * ohne k€-Transform · R5 EINE Zeit-Steuerung (Kopf-Jahr; T-Konto erbt) · R6 KPIs +
 * Charts parkbar.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  BarChart, Bar, ComposedChart, AreaChart, Area, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { Euro, TrendingUp, Wallet, FileText, Download, Wrench } from 'lucide-react'
import { LoadingSpinner, Card, Button, buttonClasses, ChartLegende } from '../components/ui'
import ChartTooltip from '../components/ui/ChartTooltip'
import { BlockShell, KpiStrip, type Block, type KpiStripItem } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar } from '../components/park'
import { TKonto } from '../components/finanzen/TKonto'
import { COLORS, GELD_COLORS, MONAT_NAMEN, formatGeld, fmtZahl, xAchse, yAchse, achsenEinheit, ACHSEN_MARGIN_TOP } from '../lib'
import { exportToCSV } from '../utils/export'
import { createMonatsZeitreihe } from '../pages/auswertung/types'
import { aktuellerMonatApi, type AktuellerMonatResponse } from '../api/aktuellerMonat'
import { cockpitApi, type KomponentenZeitreihe } from '../api/cockpit'
import { importApi } from '../api/import'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import { baueJahrAlsMonat } from './JahrAggregat'
import { STEUER_H } from './WerkbankZeitraum'
import { useSelectedAnlage, useSchmaleAchse } from '../hooks'
import { useAuswertungBasis } from './useAuswertungBasis'
import { AuswertungKopf } from './AuswertungKopf'

const SICHT_KEY = 'v4-auswertungen-finanzen'
const MONATE_1_12 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
const euroTick = (v: number) => fmtZahl(v, 0)

export default function AuswertungenFinanzenV4() {
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <FinanzenInner />
    </ParkProvider>
  )
}

function FinanzenInner() {
  const { anlagen, selectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const basis = useAuswertungBasis(selectedAnlageId)

  // Sonderkosten/Sonstige (#310) je Monat — wie FinanzenTab aus der Komponenten-Zeitreihe.
  const [sonderkostenData, setSonderkostenData] = useState<KomponentenZeitreihe | null>(null)
  useEffect(() => {
    if (!selectedAnlageId) { setSonderkostenData(null); return }
    let aktiv = true
    cockpitApi.getKomponentenZeitreihe(selectedAnlageId)
      .then((r) => { if (aktiv) setSonderkostenData(r) })
      .catch(() => { if (aktiv) setSonderkostenData(null) })
    return () => { aktiv = false }
  }, [selectedAnlageId])

  const schmal = useSchmaleAchse()
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

  const handleCsv = () => {
    const headers = ['Monat', 'Einspeiseerlös (€)', 'EV-Ersparnis (€)', 'Netzbezug-Kosten (€)',
      'Netto-Ertrag (€)', 'Sonderkosten (€)', 'Netto nach Sonderkosten (€)', 'Kumulierter Ertrag (€)']
    const rows = chartData.map((z) => [z.name, z.einspeise_erloes, z.ev_ersparnis, z.netzbezug_kosten,
      z.netto_ertrag, z.sonderkosten, z.netto_nach_sonderkosten, z.kumuliert_ertrag])
    exportToCSV(headers, rows, 'finanzen_export.csv')
  }

  // T-Konto erbt das Jahr vom Kopf (R5). 'alle' → neuestes Jahr.
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
                  <Wrench className="h-5 w-5 text-amber-600 dark:text-amber-400 flex-shrink-0" />
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
                  <BarChart data={chartData} margin={{ top: ACHSEN_MARGIN_TOP, right: 30, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                    <XAxis dataKey="name" {...xAchse(schmal)} interval="preserveStartEnd" /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                    <YAxis tickFormatter={euroTick} {...yAchse(schmal)} label={achsenEinheit('€')} />
                    <Tooltip content={<ChartTooltip unit="€" decimals={2} />} />
                    <Legend content={<ChartLegende />} />
                    <Bar dataKey="einspeise_erloes" name="Einspeiseerlös" fill={COLORS.feedin} stackId="pos" />
                    <Bar dataKey="ev_ersparnis" name="EV-Ersparnis" fill={COLORS.consumption} stackId="pos" />
                    <Bar dataKey="netzbezug_kosten" name="Netzbezug (negativ)" fill={COLORS.grid} />
                    {gesamt.sonderkosten > 0 && <Bar dataKey="sonderkosten" name="Sonderkosten" fill={GELD_COLORS.kosten} />}
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
                  <AreaChart data={chartData} margin={{ top: ACHSEN_MARGIN_TOP, right: 30, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                    <XAxis dataKey="name" {...xAchse(schmal)} interval="preserveStartEnd" /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                    <YAxis tickFormatter={euroTick} {...yAchse(schmal)} label={achsenEinheit('€')} />
                    <Tooltip content={<ChartTooltip unit="€" decimals={0} />} />
                    <Area type="monotone" dataKey="kumuliert_ertrag" name="Kumulierter Ertrag"
                      stroke={COLORS.feedin} fill={COLORS.feedin} fillOpacity={0.3} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-2 flex items-center justify-center gap-3 text-sm">
                <span className="text-gray-500">Gesamt nach {monate} Monaten:</span>
                <span className="text-lg font-bold text-green-600 dark:text-green-400">{fmtZahl(gesamt.nettoNachSonderkosten, 0)} €</span>
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
                  <ComposedChart data={chartData} margin={{ top: ACHSEN_MARGIN_TOP, right: 30, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                    <XAxis dataKey="name" {...xAchse(schmal)} interval="preserveStartEnd" /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                    <YAxis tickFormatter={euroTick} {...yAchse(schmal)} label={achsenEinheit('€')} />
                    <Tooltip content={<ChartTooltip unit="€" decimals={2} />} />
                    <Bar dataKey="netto_nach_sonderkosten" name="Netto-Ertrag" fill={COLORS.feedin} opacity={0.7} />
                    <Line type="monotone" dataKey="netto_nach_sonderkosten" name="Trend" stroke={COLORS.solar} strokeWidth={2} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          </Parkbar>
          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <p className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Durchschnittswerte</p>
            <div className={`grid grid-cols-2 gap-3 text-sm ${gesamt.sonderkosten > 0 ? 'md:grid-cols-5' : 'md:grid-cols-4'}`}>
              <div><p className="text-gray-500">Ø Einspeiseerlös/Monat</p><p className="font-medium text-green-600 dark:text-green-400">{fmtZahl(gesamt.einspeiseErloes / monate, 0)} €</p></div>
              <div><p className="text-gray-500">Ø EV-Ersparnis/Monat</p><p className="font-medium text-purple-600 dark:text-purple-400">{fmtZahl(gesamt.eigenverbrauchErsparnis / monate, 0)} €</p></div>
              <div><p className="text-gray-500">Ø Netzbezug-Kosten/Monat</p><p className="font-medium text-red-600 dark:text-red-400">{fmtZahl(gesamt.netzbezugKosten / monate, 0)} €</p></div>
              {gesamt.sonderkosten > 0 && (
                <div><p className="text-gray-500">Ø Sonderkosten/Monat</p><p className="font-medium text-amber-600 dark:text-amber-400">{fmtZahl(gesamt.sonderkosten / monate, 0)} €</p></div>
              )}
              <div><p className="text-gray-500">Ø Netto-Ertrag/Monat</p><p className="font-medium text-blue-600 dark:text-blue-400">{fmtZahl(gesamt.nettoNachSonderkosten / monate, 0)} €</p></div>
            </div>
          </div>
        </div>
      ),
    }

    const blockTKonto: Block = {
      id: 'tkonto', title: 'SOLL/HABEN-T-Konto', icon: Wallet, farbe: 'text-blue-500',
      summary: 'Kosten vs. Erlöse + Einsparungen (Monat oder Jahr)', defaultOpen: true,
      render: () => <TKontoPeriode anlageId={selectedAnlageId} daten={basis.daten} jahr={jahrFuerTKonto} />,
    }

    const blockBerichte: Block = {
      id: 'berichte', title: 'Berichte & Dokumente', icon: FileText, farbe: 'text-gray-400',
      summary: 'Finanzbericht (PDF) · CSV-Export', defaultOpen: false,
      render: () => (
        <div className="space-y-3">
          <FinanzberichtTeaser anlageId={selectedAnlageId} jahr={basis.jahr} />
          <Button variant="secondary" size="sm" onClick={handleCsv}>
            <Download className="h-4 w-4 mr-1" /> CSV-Export (Monatswerte)
          </Button>
        </div>
      ),
    }

    return [blockUebersicht, blockTKonto, blockBerichte]
  }, [strompreis, gesamt, chartData, monate, hatMehrereTarife, basis.stats, basis.daten, basis.jahr, jahrFuerTKonto, selectedAnlageId])

  if (anlagenLoading || basis.loading) return <LoadingSpinner text="Lade Finanzdaten…" />
  if (anlagen.length === 0) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage angelegt.</p></Card>
      </div>
    )
  }

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      <AuswertungKopf titel="Finanzen" jahr={basis.jahr} setJahr={basis.setJahr} jahre={basis.jahre} />
      {/* Kein `key={jahr}` → BlockShell re-rendert in-place beim Jahreswechsel
          (detLAN D7-6, 2026-06-27), statt sichtbar zu remounten. */}
      <BlockShell persistKey={SICHT_KEY} bloecke={bloecke} sortierbar />
      <ParkFuss />
    </div>
  )
}

/** Segment-Button für den Monat/Jahr-Umschalter. */
function SegBtn({ aktiv, onClick, children }: { aktiv: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick}
      className={`px-3 ${STEUER_H} inline-flex items-center text-sm font-medium transition-colors ${
        aktiv ? 'bg-primary-600 text-white'
              : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'}`}>
      {children}
    </button>
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
  const [d, setD] = useState<AktuellerMonatResponse | null>(null)
  const [sonderkosten, setSonderkosten] = useState<number | null>(null)
  const [laden, setLaden] = useState(false)

  const monate = useMemo(
    () => (jahr == null ? [] : [...new Set(daten.filter((r) => r.jahr === jahr).map((r) => r.monat))].sort((a, b) => a - b)),
    [daten, jahr],
  )
  // Monat default/korrigieren = letzter im (Kopf-)Jahr.
  useEffect(() => {
    if (monate.length === 0) return
    if (monat == null || !monate.includes(monat)) setMonat(monate[monate.length - 1])
  }, [monate, monat])

  useEffect(() => {
    if (!anlageId || jahr == null) return
    let ab = false
    setLaden(true)
    if (modus === 'monat') {
      if (monat == null) { setLaden(false); return }
      Promise.all([
        aktuellerMonatApi.getData(anlageId, jahr, monat),
        cockpitApi.getKomponentenZeitreihe(anlageId, jahr)
          .then((kt) => kt.monatswerte?.find((v) => v.monat === monat)?.sonstige_ausgaben_euro ?? null)
          .catch(() => null),
      ])
        .then(([resp, sk]) => { if (!ab) { setD(resp); setSonderkosten(sk) } })
        .catch(() => { if (!ab) setD(null) })
        .finally(() => { if (!ab) setLaden(false) })
    } else {
      Promise.all(MONATE_1_12.map((m) => aktuellerMonatApi.getData(anlageId, jahr, m).catch(() => null)))
        .then((resps) => {
          if (ab) return
          const ok = resps.filter((r): r is AktuellerMonatResponse => r != null)
          setD(ok.length ? baueJahrAlsMonat(ok, jahr) : null)
          setSonderkosten(null)
        })
        .finally(() => { if (!ab) setLaden(false) })
    }
    return () => { ab = true }
  }, [anlageId, modus, jahr, monat])

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <SegBtn aktiv={modus === 'monat'} onClick={() => setModus('monat')}>Monat</SegBtn>
          <SegBtn aktiv={modus === 'jahr'} onClick={() => setModus('jahr')}>Jahr ({jahr ?? '—'})</SegBtn>
        </div>
        {/* D9-E: Beide Modi belegen dieselbe Toolbar-Höhe (kein Verschwinden des
            Selects → kein Vertikal-Sprung des T-Kontos beim Monat↔Jahr-Wechsel;
            Content-Swap bleibt in-place wie D7-6). */}
        {modus === 'monat' ? (
          <select value={monat ?? ''} onChange={(e) => setMonat(e.target.value ? Number(e.target.value) : null)}
            aria-label="Monat wählen" className={`input w-auto ${STEUER_H} py-0`}>
            {monate.map((m) => <option key={m} value={m}>{MONAT_NAMEN[m]} {jahr}</option>)}
          </select>
        ) : (
          <span className={`text-sm text-gray-500 dark:text-gray-400 px-2 inline-flex items-center ${STEUER_H}`}>Ganzes Jahr {jahr ?? '—'}</span>
        )}
      </div>
      {laden && !d ? (
        // Spinner nur beim Erst-Load; beim Monat/Jahr-Umschalten bleibt das
        // bestehende T-Konto stehen und der Content tauscht in-place (detLAN D7-6,
        // 2026-06-27 — „ausschließlich den Content neu schreiben").
        <LoadingSpinner text="Lade T-Konto…" />
      ) : d ? (
        <TKonto d={d} sonderkosten={sonderkosten} />
      ) : (
        <p className="text-sm text-gray-500 dark:text-gray-400">Für den gewählten Zeitraum liegen keine Finanzdaten vor.</p>
      )}
    </div>
  )
}

/** G10 — Cross-Link-Teaser auf den PDF-Finanzbericht. */
function FinanzberichtTeaser({ anlageId, jahr }: { anlageId: number | undefined | null; jahr: number | 'alle' }) {
  if (!anlageId) return null
  const url = importApi.getPdfZipExportUrl(anlageId, ['finanzbericht'], jahr === 'alle' ? null : jahr)
  return (
    <div className="space-y-2">
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Finanzbericht als PDF{jahr !== 'alle' ? ` (Jahr ${jahr})` : ' (Gesamtzeitraum)'} — die zentrale
        Berichts-/Dokumentenverwaltung folgt in den Einstellungen.
      </p>
      <a href={url} className={buttonClasses({ variant: 'primary', className: 'gap-2 no-underline' })}>
        <FileText className="h-4 w-4" /> Finanzbericht (PDF)
      </a>
    </div>
  )
}
