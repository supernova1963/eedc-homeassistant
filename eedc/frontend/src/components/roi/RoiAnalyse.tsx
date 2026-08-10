/**
 * RoiAnalyse — geteilte Element-Bausteine der ROI-Analyse (A.5 Sub 5, SoT).
 *
 * Eine Code-Wahrheit: die IST-Seite `pages/ROIDashboard.tsx` UND die v4-Sicht
 * `v4/AuswertungenRoiV4.tsx` komponieren aus diesen Teilen. Jeder Teil ist ein
 * eigenständiges Anzeige-Element (v4 umhüllt es mit `Parkbar`; IST rendert es
 * direkt über den `RoiAnalyse`-Composite). Daten-Hook `useRoiAnalyse` (ein
 * `getROIDashboard`-Call), KPI-Items `roiKpiItems`, dann Charts/Tabelle.
 *
 * Regel-SoT: R1 alle Geld-Zahlen via `fmtZahl`/`formatGeld` (kein `.toLocaleString`/
 * `.toFixed`) · R2 Geld in € ohne k€-Transform (Achsen ebenso) · R3 Geld-Rollen über
 * `GELD_TEXT_CLASS` · R4 CO₂ nur prop-gated (`zeigeCo2`; v4 = false → CO₂ raus aus
 * KPI + Detailtabelle, IST behält es per Default). Parameter (Strompreis/Einspeise-
 * vergütung/Benzinpreis/Jahr) kommen als Props — IST reicht die Slider durch, v4 die
 * Anlagen-Defaults (D3: „rebuild-lite, Slider weg"). KEIN Anlagen-Selektor (Shell).
 */
import { useState, useEffect, useMemo, Fragment } from 'react'
import {
  TrendingUp, Clock, Leaf, PiggyBank, Car, Flame, Battery, Plug,
  Settings2, Sun, LayoutGrid, ChevronDown, ChevronRight,
} from 'lucide-react'
import {
  BarChart, Bar, Cell, LabelList, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line,
} from 'recharts'
import { Card, Alert, LoadingSpinner, EmptyState, FormelTooltip, QuelleBadge, ChartLegende, Table, TableHead, TableBody, TableFoot } from '../ui'
import { ZELLE, KOPF_ZELLE } from '../ui/tabelleMasse'
import ChartTooltip from '../ui/ChartTooltip'
import { useLegendenToggle } from '../../hooks'
import { KpiStrip, type KpiStripItem } from '../blocks'
import { investitionenApi, type ROIDashboardResponse, type ROIBerechnung, type SpeicherRoiDetail } from '../../api'
import { aussichtenApi } from '../../api/aussichten'
import { swrCachePeek, swrCacheStore } from '../../hooks/useApiData'
import { TYP_COLORS, GELD_COLORS, GELD_TEXT_CLASS, fmtZahl, formatGeld, formatCo2, xAchse, achsenEinheit, ACHSEN_MARGIN_TOP } from '../../lib'
import { TYP_LABELS } from '../../lib/constants'

const typIcons: Record<string, React.ElementType> = {
  'e-auto': Car,
  'waermepumpe': Flame,
  'speicher': Battery,
  'wallbox': Plug,
  'wechselrichter': Settings2,
  'pv-module': Sun,
  'balkonkraftwerk': LayoutGrid,
  'sonstiges': Settings2,
}

// Typ-Labels: SoT `TYP_LABELS` (lib/constants) — die frühere lokale Kopie hier
// driftete (fehlte 'pv-system' → ROI-Pie zeigte Roh-Key „pv-system", D17-5-Nebenfund).
const geldTick = (v: number) => fmtZahl(v, 0)

/**
 * Nenner der Kapitalrechnung als Text — mit dem Zwischenschritt, sobald
 * sonstige Positionen ihn von den relevanten Kosten unterscheiden (F-19).
 *
 * Der Client rechnet **nichts**: beide Zahlen kommen aus der Response
 * (`gesamt_kapitaleinsatz` ist der Wert, mit dem das Backend geteilt hat).
 * Er schreibt nur aus, woraus sie besteht — ohne das ergäbe der angezeigte
 * Rechenweg eine andere Zahl als das Ergebnis daneben (die N-212-Klasse).
 */
const nennerText = (d: { gesamt_relevante_kosten: number; gesamt_kapitaleinsatz?: number; gesamt_sonstige_ausgaben_euro?: number }): string => {
  const einsatz = d.gesamt_kapitaleinsatz ?? d.gesamt_relevante_kosten
  const ausgaben = d.gesamt_sonstige_ausgaben_euro ?? 0
  if (!ausgaben) return formatGeld(einsatz).text
  return `${formatGeld(d.gesamt_relevante_kosten).text} + ${formatGeld(ausgaben).text} sonstige Ausgaben = ${formatGeld(einsatz).text}`
}

/** Zeilen-Variante von {@link nennerText}. */
const zeilenNenner = (b: ROIBerechnung): string =>
  formatGeld(b.kapitaleinsatz ?? b.relevante_kosten).text

export interface RoiAnalyseProps {
  anlageId: number
  /** Berechnungs-Parameter (Override); undefined ⇒ Backend löst Default auf. */
  strompreis?: number
  einspeiseverguetung?: number
  benzinpreis?: number
  jahr?: number | 'all'
  /** CO₂-KPI + Detailspalte zeigen (R4). IST = true (Default), v4 = false. */
  zeigeCo2?: boolean
  /** Optionaler Rückkanal der geladenen Antwort (z. B. für den Benzinpreis-Hinweis
   *  im Slider der IST-Seite). */
  onLoaded?: (data: ROIDashboardResponse) => void
  /** R18-2 (SWR, Opt-in der v4-Sicht): Basis des Sicht-Cache-Keys — bei Remount
   *  stehen die alten Daten sofort (kein Skeleton), still revalidiert. Die
   *  Berechnungs-Parameter werden an die Basis angehängt. IST/V3: weglassen
   *  (Verhalten unverändert). */
  swrKeyBasis?: string
}

/** Der gemessene Amortisations-Fortschritt (N-137) — geholt, nicht gerechnet. */
export interface AmortisationsFortschrittVM {
  prozent: number
  erreicht: boolean
  bisherigeErtraege: number
  relevanteKosten: number
  prognoseJahr: number | null
}

export interface RoiAnalyseVM {
  loading: boolean
  error: string | null
  setError: (e: string | null) => void
  roiData: ROIDashboardResponse | null
  amortisationData: Array<{ jahr: number; kumulierte_einsparung: number; investition: number }>
  einsparungenByTyp: Array<{ name: string; value: number; color: string }>
  investitionenChart: Array<{
    name: string; fullName: string; kosten: number; einsparung: number
    amortisation: number; typ: string; color: string
  }>
  /** null, solange die Aussichten-Prognose nicht da ist oder scheiterte. */
  fortschritt: AmortisationsFortschrittVM | null
}

/**
 * Etappe C (#264): Speicher-spezifisches C-Detail aus einer ROI-Berechnung
 * ziehen — egal ob AC-gekoppelt (eigene Berechnung) oder DC-gekoppelt
 * (Komponente eines PV-Systems). Liefert null, wenn keine belastbaren
 * C-Felder vorliegen (z. B. Prognose-Modus ohne IST-Daten).
 */
function getSpeicherCDetail(b: ROIBerechnung): SpeicherRoiDetail | null {
  if (b.investition_typ === 'speicher') {
    const d = b.detail_berechnung as SpeicherRoiDetail
    return d && d.wirkungsgrad_quelle ? d : null
  }
  const sp = b.komponenten?.find((k) => k.typ === 'speicher')
  if (sp) {
    const d = sp.detail as SpeicherRoiDetail
    return d && d.wirkungsgrad_quelle ? d : null
  }
  return null
}

/** Lädt das ROI-Dashboard (ein `getROIDashboard`-Call) und leitet Amortisations-
 *  Zeitreihe + Typ-/Investitions-Aggregate ab. Geteilt von IST + v4. */
export function useRoiAnalyse({ anlageId, strompreis, einspeiseverguetung, benzinpreis, jahr, onLoaded, swrKeyBasis }: RoiAnalyseProps): RoiAnalyseVM {
  // Voller Cache-Key inkl. Berechnungs-Parameter (jede Variante = eigener Stand).
  const swrKey = swrKeyBasis
    ? `${swrKeyBasis}:${anlageId}:${strompreis}:${einspeiseverguetung}:${benzinpreis}:${jahr}`
    : undefined
  const [roiData, setRoiData] = useState<ROIDashboardResponse | null>(
    () => (swrKey ? swrCachePeek<ROIDashboardResponse>(swrKey) : undefined) ?? null,
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // N-137: Der Amortisations-FORTSCHRITT ist die einzige Amortisations-Aussage,
  // die aus GEMESSENEN Erträgen kommt — und die kumulierten Erträge entstehen
  // nur an einer Stelle im Baum (Aussichten-Finanzprognose: Monats-Fakten →
  // Finanz-Zeilen → Aggregat − Betriebskosten − USt, rund 220 Zeilen). Diese
  // Sicht HOLT die fertige Zahl deshalb, statt sie ein zweites Mal zu rechnen;
  // dieselbe Zahl noch einmal aufzubauen wäre die Drift-Klasse, die dieses
  // Paket gerade beseitigt. Eigener State: die Kachel erscheint, wenn sie da
  // ist — der Rest der Sicht wartet nicht auf den schwereren Endpoint.
  const [fortschritt, setFortschritt] = useState<AmortisationsFortschrittVM | null>(null)

  useEffect(() => {
    if (!anlageId) return
    let ab = false
    aussichtenApi.getFinanzPrognose(anlageId)
      .then((p) => {
        if (ab) return
        setFortschritt({
          prozent: p.amortisations_fortschritt_prozent,
          erreicht: p.amortisation_erreicht,
          bisherigeErtraege: p.bisherige_ertraege_euro,
          relevanteKosten: p.investition_gesamt_euro,
          prognoseJahr: p.amortisation_prognose_jahr,
        })
      })
      // Still: die Fortschritts-Kachel entfällt dann, der Rest der Sicht steht.
      .catch(() => { if (!ab) setFortschritt(null) })
    return () => { ab = true }
  }, [anlageId])

  useEffect(() => {
    if (!anlageId) return
    let ab = false
    // R18-2 (SWR, Opt-in v4): Cache-Stand sofort zeigen + still revalidieren —
    // Skeleton nur ohne Cache-Stand (echter Erst-Load).
    const cached = swrKey ? swrCachePeek<ROIDashboardResponse>(swrKey) : undefined
    if (cached !== undefined) setRoiData(cached)
    const loadROI = async () => {
      try {
        if (cached === undefined) setLoading(true)
        setError(null)
        const data = await investitionenApi.getROIDashboard(anlageId, strompreis, einspeiseverguetung, benzinpreis, jahr)
        if (!ab) {
          setRoiData(data)
          if (swrKey) swrCacheStore(swrKey, data)
          onLoaded?.(data)
        }
      } catch (e) {
        if (!ab) setError(e instanceof Error ? e.message : 'Fehler beim Laden der ROI-Daten')
      } finally {
        if (!ab) setLoading(false)
      }
    }
    loadROI()
    return () => { ab = true }
    // onLoaded bewusst nicht in den Deps (Eltern reicht inline-Callback durch).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anlageId, strompreis, einspeiseverguetung, benzinpreis, jahr, swrKey])

  const amortisationData = useMemo(() => {
    if (!roiData || roiData.gesamt_relevante_kosten <= 0) return []
    const data = []
    let kumulierteEinsparung = 0
    // F-19: die Break-Even-Linie liegt auf dem **Kapitaleinsatz** — dem Wert,
    // durch den das Backend teilt. Auf den relevanten Kosten würde die Kurve
    // die Nulllinie an einem anderen Jahr schneiden als die Amortisations-
    // Kachel darüber nennt.
    const nenner = roiData.gesamt_kapitaleinsatz ?? roiData.gesamt_relevante_kosten
    const maxJahre = Math.min(Math.ceil((roiData.gesamt_amortisation_jahre ?? 20) * 1.5), 30)
    for (let j = 0; j <= maxJahre; j++) {
      data.push({
        jahr: j,
        kumulierte_einsparung: Math.round(kumulierteEinsparung),
        investition: nenner,
      })
      kumulierteEinsparung += roiData.gesamt_jahres_einsparung
    }
    return data
  }, [roiData])

  const einsparungenByTyp = useMemo(() => {
    if (!roiData) return []
    const grouped: Record<string, number> = {}
    roiData.berechnungen.forEach((b) => {
      grouped[b.investition_typ] = (grouped[b.investition_typ] || 0) + b.jahres_einsparung
    })
    return Object.entries(grouped)
      .map(([typ, value]) => ({
        name: TYP_LABELS[typ] || typ,
        value: Math.round(value),
        color: TYP_COLORS[typ] || TYP_COLORS['sonstiges'],
      }))
      .filter((d) => d.value > 0)
  }, [roiData])

  const investitionenChart = useMemo(() => {
    if (!roiData) return []
    return roiData.berechnungen.map((b) => ({
      name: b.investition_bezeichnung.length > 15 ? b.investition_bezeichnung.substring(0, 15) + '...' : b.investition_bezeichnung,
      fullName: b.investition_bezeichnung,
      kosten: b.relevante_kosten,
      einsparung: b.jahres_einsparung,
      amortisation: b.amortisation_jahre ?? 0,
      typ: b.investition_typ,
      color: TYP_COLORS[b.investition_typ] || TYP_COLORS['sonstiges'],
    }))
  }, [roiData])

  return { loading, error, setError, roiData, amortisationData, einsparungenByTyp, investitionenChart, fortschritt }
}

/** Block ① — KPIs Investition · Einsparung · Amortisation. CO₂-KPI nur bei
 *  `zeigeCo2` (R4: v4 = aus → 3 KPIs, IST = an → 4 KPIs). */
export function roiKpiItems(
  roiData: ROIDashboardResponse,
  zeigeCo2 = false,
  fortschritt: AmortisationsFortschrittVM | null = null,
): KpiStripItem[] {
  const items: KpiStripItem[] = [
    {
      title: 'Gesamtinvestition', value: formatGeld(roiData.gesamt_investition).wert, unit: '€',
      color: 'blue', icon: PiggyBank, parkId: 'kpi:investition',
      subtitle: `Relevant: ${formatGeld(roiData.gesamt_relevante_kosten).text}`,
      sicht: 'Gesamt-Anlage · Vollkosten + Mehrkosten-Ansatz im Untertitel',
      formel: 'Σ Anschaffungskosten aller Investitionen',
      berechnung: 'Relevant = Gesamt − Alternativkosten',
      ergebnis: `= ${formatGeld(roiData.gesamt_relevante_kosten).text}`,
    },
    {
      title: 'Jährliche Einsparung', value: formatGeld(roiData.gesamt_jahres_einsparung).wert, unit: '€',
      color: 'green', icon: TrendingUp, parkId: 'kpi:einsparung',
      subtitle: roiData.gesamt_roi_prozent ? `ROI: ${roiData.gesamt_roi_prozent} %` : 'ROI: -',
      sicht: 'Gesamt-Anlage · Jahres-Prognose · Mehrkosten-Ansatz',
      formel: 'Σ Einsparungen aller Investitionen',
      berechnung: roiData.gesamt_relevante_kosten > 0 ? 'ROI = Einsparung ÷ Kapitaleinsatz × 100' : undefined,
      ergebnis: roiData.gesamt_roi_prozent ? `= ${roiData.gesamt_roi_prozent} % ROI` : undefined,
    },
    {
      title: 'Amortisation', value: roiData.gesamt_amortisation_jahre ? `${roiData.gesamt_amortisation_jahre}` : '—',
      unit: roiData.gesamt_amortisation_jahre ? 'Jahre' : undefined,
      color: 'orange', icon: Clock, parkId: 'kpi:amortisation',
      // Radiocarbonat (Forum v4.0.0): „Ich fand es schöner mit der voraussichtlichen
      // Jahreszahl der Amortisierung." Dauer bleibt der Hauptwert, das Jahr steht dabei.
      subtitle: roiData.gesamt_amortisation_jahr
        ? `Kostendeckung voraussichtlich ${roiData.gesamt_amortisation_jahr}`
        : 'Bis zur Kostendeckung',
      sicht: 'Gesamt-Anlage · Mehrkosten-Ansatz · MODELL (hochgerechnet, ohne bisherige Erträge) — die gemessene Sicht steht daneben als „Amortisations-Fortschritt“',
      formel: 'Kapitaleinsatz ÷ Jährliche Einsparung',
      // F-19: Nenner ist der Kapitaleinsatz — relevante Kosten plus die
      // sonstigen Netto-Kosten (Reparatur, Ersatzteil …). Der Zwischenschritt
      // steht ausgeschrieben, sonst ergäbe der Rechenweg eine andere Zahl als
      // das Ergebnis daneben.
      berechnung: roiData.gesamt_jahres_einsparung > 0 ? nennerText(roiData) + ` ÷ ${formatGeld(roiData.gesamt_jahres_einsparung).text}/Jahr` : undefined,
      ergebnis: roiData.gesamt_amortisation_jahre ? `= ${roiData.gesamt_amortisation_jahre} Jahre` : undefined,
    },
  ]
  // N-137: Die Gegen-Kachel zur Amortisation. Sie beantwortet dieselbe Frage,
  // aber aus der GEMESSENEN Historie statt aus einer hochgerechneten
  // Jahres-Einsparung — „4.800 € von 12.000 € sind drin" neben „laut Rechnung
  // in 9,2 Jahren". Beide teilen denselben Nenner (relevante Kosten =
  // Mehrkosten), sonst stünden sie sich in einer Sicht widersprechend
  // gegenüber. Fehlt die Zahl (Endpoint nicht da), entfällt die Kachel — kein
  // Platzhalter, der eine Aussage vortäuscht.
  if (fortschritt) {
    const rest = Math.max(0, fortschritt.relevanteKosten - fortschritt.bisherigeErtraege)
    items.push({
      title: 'Amortisations-Fortschritt',
      value: fmtZahl(fortschritt.prozent, 1), unit: '%',
      color: 'purple', icon: PiggyBank, parkId: 'kpi:amortisation-fortschritt',
      subtitle: fortschritt.erreicht
        ? 'Kosten gedeckt'
        : `noch ${formatGeld(rest).text}${fortschritt.prognoseJahr ? ` · voraussichtlich ${fortschritt.prognoseJahr}` : ''}`,
      sicht: 'Gesamt-Anlage · Mehrkosten-Ansatz · GEMESSEN (bisherige Erträge, kein Modell)',
      formel: 'Bisherige Netto-Erträge ÷ Relevante Kosten × 100',
      berechnung: `${formatGeld(fortschritt.bisherigeErtraege).text} ÷ ${formatGeld(fortschritt.relevanteKosten).text}`,
      ergebnis: `= ${fmtZahl(fortschritt.prozent, 1)} % gedeckt`,
    })
  }
  if (zeigeCo2) {
    items.push({
      title: 'CO2-Einsparung', value: formatCo2(roiData.gesamt_co2_einsparung_kg).wert, unit: formatCo2(roiData.gesamt_co2_einsparung_kg).einheit,
      color: 'green', icon: Leaf, parkId: 'kpi:co2', subtitle: 'pro Jahr',
      sicht: 'Gesamt-Anlage · Jahres-Prognose',
      formel: 'Σ CO2-Einsparungen aller Investitionen',
      berechnung: 'Je nach Investitionstyp unterschiedlich',
      ergebnis: `= ${formatCo2(roiData.gesamt_co2_einsparung_kg).text}/Jahr`,
    })
  }
  return items
}

/** Block ② — Amortisationsverlauf (Break-Even-Kurve, 25–30 Jahre). */
export function RoiAmortisationChart({ vm }: { vm: RoiAnalyseVM }) {
  const legende = useLegendenToggle()
  const roiData = vm.roiData
  if (!roiData) return null
  const basisJahr = roiData.basis_jahr
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Amortisationsverlauf</h3>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={vm.amortisationData} margin={{ top: ACHSEN_MARGIN_TOP }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            {/* Mit gepflegtem Anschaffungsdatum zeigen die Ticks Kalenderjahre
                (Radiocarbonat), sonst wie bisher den Jahres-Index ab 0. */}
            <XAxis
              dataKey="jahr"
              tickFormatter={(j: number) => (basisJahr != null ? `${basisJahr + j}` : `${j}`)}
              {...xAchse()} /* achsen-allow: Jahres-Index bzw. Kalenderjahr; Einheit steht im Break-Even-Text + KPI, Achsen-Label kollidierte mit Legende (#29-15) */
            />
            <YAxis tickFormatter={geldTick} tick={{ fontSize: 10 }} width={70} label={achsenEinheit('€')} />
            <Tooltip content={<ChartTooltip labelFormatter={(label) => (basisJahr != null ? `${basisJahr + Number(label)}` : `Jahr ${label}`)} unit="€" />} />
            <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
            <Line type="monotone" dataKey="kumulierte_einsparung" name="Kumulierte Einsparung" stroke={GELD_COLORS.ersparnis} strokeWidth={2} dot={false} hide={legende.istVersteckt('kumulierte_einsparung')} />
            <Line type="monotone" dataKey="investition" name="Investition" stroke={GELD_COLORS.kosten} strokeWidth={2} strokeDasharray="5 5" dot={false} hide={legende.istVersteckt('investition')} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {roiData.gesamt_amortisation_jahre && (
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 text-center">
          Break-Even nach ca. {fmtZahl(roiData.gesamt_amortisation_jahre, 1)} Jahren
          {roiData.gesamt_amortisation_jahr ? ` — voraussichtlich ${roiData.gesamt_amortisation_jahr}` : ''}
          {/* Ehrlichkeit zum Nullpunkt: die Kurve rechnet ab dem FRÜHESTEN
              Anschaffungsjahr mit der heutigen Jahres-Einsparung. Wer über
              mehrere Jahre erweitert hat, liest damit ein optimistisches Jahr. */}
          {basisJahr != null && (
            <span className="block text-xs mt-0.5">
              Startjahr {basisJahr} (früheste Anschaffung); bei über mehrere Jahre verteilten
              Anschaffungen ist das Jahr eher optimistisch.
            </span>
          )}
        </p>
      )}
    </Card>
  )
}

/** Block ③a — Einsparungen nach Investitionstyp: horizontale Balken mit Werten
 * (R18-5, rapahl #208 + Gernot-Entscheid 2026-07-10). Kriterium (B7-Schärfung):
 * absolute Werte + Rangfolge → horizontale Balken · reiner Anteil am Ganzen →
 * AnteilDonut. Hier sind es absolute €/Jahr mit Rangfolge — daher Balken nach
 * der Mechanik der Nachbar-Kachel „Investitionen im Vergleich" (keine dritte
 * Komponente). Sortierung bewusst nach Wert absteigend (Rangfolge IST die
 * Aussage) — nicht INVESTITION_TYP_ORDER (die gilt für Typ-LISTEN). */
export function RoiTypBalken({ vm }: { vm: RoiAnalyseVM }) {
  const daten = [...vm.einsparungenByTyp].sort((a, b) => b.value - a.value)
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Einsparungen nach Typ</h3>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={daten} layout="vertical" margin={{ right: 56 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis type="number" domain={[0, 'auto']} tickFormatter={(v) => `${fmtZahl(v, 0)} €`} tick={{ fontSize: 10 }} /* achsen-allow: Wert-Achse waagerecht, Einheit/Format pro Tick (de-DE) */ />
            <YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 10 }} /* achsen-allow: Kategorie-Namen (Typen) */ />
            <Tooltip content={<ChartTooltip formatter={(value: number) => `${fmtZahl(value, 0)} €/Jahr`} />} />
            <Bar dataKey="value" name="Jährliche Einsparung" radius={[0, 2, 2, 0]}>
              {daten.map((d) => <Cell key={d.name} fill={d.color} />)}
              {/* Rainers Kern: „Balken MIT Werten" — Wert am Balkenende. */}
              <LabelList dataKey="value" position="right" formatter={(v: number) => `${fmtZahl(v, 0)} €`} className="fill-gray-500 dark:fill-gray-400" fontSize={10} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

/** Block ③b — Investitionen im Vergleich (Kosten vs. Einsparung, horizontale Bars). */
export function RoiVergleichBar({ vm }: { vm: RoiAnalyseVM }) {
  const legende = useLegendenToggle()
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Investitionen im Vergleich</h3>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={vm.investitionenChart} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            {/* D9-F: Domain an Daten klemmen (Werte ≥ 0 → kein leerer Negativbereich) + € als Einheit. */}
            <XAxis type="number" domain={[0, 'auto']} tickFormatter={(v) => `${fmtZahl(v, 0)} €`} tick={{ fontSize: 10 }} /* achsen-allow: Wert-Achse waagerecht, Einheit/Format pro Tick (de-DE) */ />
            <YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 10 }} /* achsen-allow: Kategorie-Namen (Investitionen) */ />
            <Tooltip content={<ChartTooltip formatter={(value: number, name: string) => name === 'Relevante Kosten' ? `${fmtZahl(value, 0)} €` : `${fmtZahl(value, 0)} €/Jahr`} />} />
            <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
            <Bar dataKey="kosten" fill={GELD_COLORS.kosten} name="Relevante Kosten" hide={legende.istVersteckt('kosten')} />
            <Bar dataKey="einsparung" fill={GELD_COLORS.ersparnis} name="Jährliche Einsparung" hide={legende.istVersteckt('einsparung')} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

/** Aufklappbares C-Detail einer Speicher-ROI-Zeile (Etappe C, #264). */
function SpeicherDetailPanel({ detail }: { detail: SpeicherRoiDetail }) {
  const lp = detail.effektiver_ladepreis_cent
  const eta = detail.verwendetes_wirkungsgrad_prozent
  return (
    <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800/50 space-y-2">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
        <span className="flex items-center gap-2">
          <span className="text-gray-500 dark:text-gray-400">Effektiver Ladepreis:</span>
          <span className="font-medium text-gray-900 dark:text-white">
            {lp != null ? `${fmtZahl(lp, 2)} ct/kWh` : '—'}
          </span>
          {detail.ladepreis_quelle && (
            <QuelleBadge quelle={detail.ladepreis_quelle} kind="ladepreis" />
          )}
          {detail.ladepreis_abdeckung_prozent != null && (
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {fmtZahl(detail.ladepreis_abdeckung_prozent, 0)} % Abdeckung
            </span>
          )}
        </span>
        <span className="flex items-center gap-2">
          <span className="text-gray-500 dark:text-gray-400">Verwendeter Wirkungsgrad:</span>
          <span className="font-medium text-gray-900 dark:text-white">
            {eta != null ? `${fmtZahl(eta, 1)} %` : '—'}
          </span>
          {detail.wirkungsgrad_quelle && (
            <QuelleBadge quelle={detail.wirkungsgrad_quelle} kind="wirkungsgrad" />
          )}
        </span>
      </div>
      {detail.eta_degradation_alarm && detail.param_wirkungsgrad_prozent != null && (
        <p className="text-xs text-amber-700 dark:text-amber-300">
          ⚠ Gemessener Wirkungsgrad liegt mehr als 5 Prozentpunkte unter dem
          Parameter-Wert ({fmtZahl(detail.param_wirkungsgrad_prozent, 1)} %) —
          möglicher Hinweis auf Speicher-Degradation.
        </p>
      )}
    </div>
  )
}

/** Block ④ — Detailübersicht je Investition (+ Speicher-C-Panel #264, Formel-Tooltips).
 *  CO₂-Spalte nur bei `zeigeCo2` (R4: v4 = aus, IST = an). */
export function RoiDetailTabelle({ vm, zeigeCo2 = true }: { vm: RoiAnalyseVM; zeigeCo2?: boolean }) {
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())
  const roiData = vm.roiData
  if (!roiData) return null
  const cols = zeigeCo2 ? 6 : 5
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Detailübersicht</h3>
      <Table mitFuss flaeche="karte">
          <TableHead>
            <tr>
              <th className={`${KOPF_ZELLE} text-left text-gray-500 dark:text-gray-400`}>Investition</th>
              <th className={`${KOPF_ZELLE} text-right text-gray-500 dark:text-gray-400`}>Kosten</th>
              <th className={`${KOPF_ZELLE} text-right text-gray-500 dark:text-gray-400`}>Einsparung/Jahr</th>
              <th className={`${KOPF_ZELLE} text-right text-gray-500 dark:text-gray-400`}>ROI</th>
              <th className={`${KOPF_ZELLE} text-right text-gray-500 dark:text-gray-400`}>Amortisation</th>
              {zeigeCo2 && <th className={`${KOPF_ZELLE} text-right text-gray-500 dark:text-gray-400`}>CO2</th>}
            </tr>
          </TableHead>
          <TableBody>
            {roiData.berechnungen.map((b) => {
              const Icon = typIcons[b.investition_typ] || Settings2
              const cDetail = getSpeicherCDetail(b)
              const isExpanded = expandedRows.has(b.investition_id)
              // N-87: Komponenten, für die eedc bewusst KEINE Wirtschaftlichkeit
              // konstruiert (heute: Split-Klimaanlage), zeigen den Leerwert `—`
              // statt einer 0 — eine 0 wäre die Behauptung „spart nichts", hier
              // fehlt der Wert aber. Gleiche Haltung wie `unbewertet()` im
              // Komponenten-Hub. Der Grund steht im `hinweis` als Tooltip.
              const unbewertet = (b.detail_berechnung as { nicht_bewertet?: boolean } | undefined)?.nicht_bewertet === true
              const unbewertetGrund = unbewertet
                ? String((b.detail_berechnung as { hinweis?: unknown } | undefined)?.hinweis ?? '')
                : undefined
              const leerwert = (
                <span className="text-gray-400 dark:text-gray-500" title={unbewertetGrund}>—</span>
              )
              return (
                <Fragment key={b.investition_id}>
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-800">
                    <td className={ZELLE}>
                      <div className="flex items-center gap-2">
                        {cDetail ? (
                          <button
                            type="button"
                            onClick={() => setExpandedRows((prev) => {
                              const next = new Set(prev)
                              if (next.has(b.investition_id)) next.delete(b.investition_id)
                              else next.add(b.investition_id)
                              return next
                            })}
                            className="text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 flex-shrink-0"
                            aria-label="Speicher-Details ein-/ausklappen"
                          >
                            {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                          </button>
                        ) : (
                          <span className="w-4 flex-shrink-0" />
                        )}
                        <Icon className="h-4 w-4 flex-shrink-0" style={{ color: TYP_COLORS[b.investition_typ] }} />
                        <div>
                          <p className="text-sm font-medium text-gray-900 dark:text-white">{b.investition_bezeichnung}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            {TYP_LABELS[b.investition_typ] ?? b.investition_typ}
                            {/* R15-4: DC-Speicher hat KEINE eigene Zeile (System-Ansatz) —
                                sein Enthaltensein hier kenntlich machen. */}
                            {(() => {
                              const sp = b.komponenten?.filter((k) => k.typ === 'speicher') ?? []
                              return sp.length > 0 ? ` · inkl. Speicher ${sp.map((k) => k.bezeichnung).join(', ')}` : ''
                            })()}
                            {/* N-87: der Leerwert in den Wert-Spalten braucht einen sichtbaren
                                Grund — sonst liest er sich als fehlende Datenpflege. */}
                            {unbewertet && (
                              <span title={unbewertetGrund} className="cursor-help"> · nicht bewertet</span>
                            )}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className={`${ZELLE} text-right`}>
                      <p className="text-sm text-gray-900 dark:text-white">{formatGeld(b.relevante_kosten).text}</p>
                      {b.anschaffungskosten_alternativ > 0 && (
                        <p className="text-xs text-gray-500 dark:text-gray-400">({formatGeld(b.anschaffungskosten).text} gesamt)</p>
                      )}
                    </td>
                    <td className={`${ZELLE} text-right font-medium ${unbewertet ? '' : GELD_TEXT_CLASS.ersparnis}`}>
                      {unbewertet ? leerwert : formatGeld(b.jahres_einsparung).text}
                    </td>
                    <td className={`${ZELLE} text-right`}>
                      {unbewertet ? leerwert : b.roi_prozent ? (
                        <FormelTooltip
                          sicht="Pro Investition · Jahres-ROI · Mehrkosten-Ansatz · Prognose"
                          formel="Jahresersparnis ÷ Kapitaleinsatz × 100"
                          berechnung={`${formatGeld(b.jahres_einsparung).text} ÷ ${zeilenNenner(b)} × 100`}
                          ergebnis={`= ${b.roi_prozent} % p.a.`}
                        >
                          <span className={b.roi_prozent >= 10 ? `${GELD_TEXT_CLASS.ersparnis} cursor-help border-b border-dotted border-green-400` : 'text-gray-900 dark:text-white cursor-help border-b border-dotted border-gray-400'}>
                            {b.roi_prozent} %
                          </span>
                        </FormelTooltip>
                      ) : (
                        <span className="text-gray-400 dark:text-gray-500">—</span>
                      )}
                    </td>
                    <td className={`${ZELLE} text-right`}>
                      {unbewertet ? leerwert : b.amortisation_jahre ? (
                        <FormelTooltip
                          sicht="Pro Investition · Mehrkosten-Ansatz · Prognose (rechnerisch, ohne bisherige Erträge)"
                          formel="Kapitaleinsatz ÷ Jahresersparnis"
                          berechnung={`${zeilenNenner(b)} ÷ ${formatGeld(b.jahres_einsparung).text}/Jahr`}
                          ergebnis={`= ${b.amortisation_jahre} Jahre`}
                        >
                          <span className={b.amortisation_jahre <= 10 ? `${GELD_TEXT_CLASS.ersparnis} cursor-help border-b border-dotted border-green-400` : 'text-orange-500 cursor-help border-b border-dotted border-orange-400'}>
                            {b.amortisation_jahre} J.
                          </span>
                        </FormelTooltip>
                      ) : (
                        <span className="text-gray-400 dark:text-gray-500">—</span>
                      )}
                    </td>
                    {zeigeCo2 && (
                      <td className={`${ZELLE} text-right text-emerald-600 dark:text-emerald-400`}>
                        {unbewertet ? leerwert : b.co2_einsparung_kg ? `${fmtZahl(b.co2_einsparung_kg, 0)} kg` : '—'}
                      </td>
                    )}
                  </tr>
                  {cDetail && isExpanded && (
                    <tr>
                      <td colSpan={cols} className="p-0"><SpeicherDetailPanel detail={cDetail} /></td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </TableBody>
          <TableFoot>
            <tr className="bg-gray-50 dark:bg-gray-800 font-semibold">
              <td className={`${ZELLE} text-gray-900 dark:text-white`}>Gesamt</td>
              <td className={`${ZELLE} text-right text-gray-900 dark:text-white`}>{formatGeld(roiData.gesamt_relevante_kosten).text}</td>
              <td className={`${ZELLE} text-right ${GELD_TEXT_CLASS.ersparnis}`}>{formatGeld(roiData.gesamt_jahres_einsparung).text}</td>
              <td className={`${ZELLE} text-right text-gray-900 dark:text-white`}>{roiData.gesamt_roi_prozent ? `${roiData.gesamt_roi_prozent} %` : '—'}</td>
              <td className={`${ZELLE} text-right text-gray-900 dark:text-white`}>{roiData.gesamt_amortisation_jahre ? `${roiData.gesamt_amortisation_jahre} J.` : '—'}</td>
              {zeigeCo2 && (
                <td className={`${ZELLE} text-right text-emerald-600 dark:text-emerald-400`}>{fmtZahl(roiData.gesamt_co2_einsparung_kg, 0)} kg</td>
              )}
            </tr>
          </TableFoot>
        </Table>
    </Card>
  )
}

/** Prognose-Disclaimer (Block ④-Fuß). */
export function RoiHinweis() {
  return (
    <Alert type="info">
      <strong>Hinweis:</strong> Die Berechnungen sind Prognosen basierend auf den eingegebenen Parametern.
      Die tatsächlichen Einsparungen können je nach Nutzungsverhalten und Energiepreisen abweichen.
    </Alert>
  )
}

/**
 * RoiAnalyse — Composite für die IST-Seite (`pages/ROIDashboard.tsx`): lädt + rendert
 * alle Teile in der bisherigen Reihenfolge (KPIs · Amortisation+Pie · Vergleich ·
 * Tabelle · Hinweis). v4 komponiert dieselben Teile selbst in BlockShell-Blöcke.
 */
export function RoiAnalyse(props: RoiAnalyseProps) {
  const vm = useRoiAnalyse(props)

  if (vm.error) {
    return <Alert type="error" onClose={() => vm.setError(null)}>{vm.error}</Alert>
  }
  if (vm.loading) {
    return <LoadingSpinner text="Berechne ROI..." />
  }
  if (vm.roiData && vm.roiData.berechnungen.length === 0) {
    return (
      <EmptyState
        icon={PiggyBank}
        title="Keine aktiven Investitionen"
        description="Erfasse Investitionen auf der Investitionen-Seite, um deren Wirtschaftlichkeit zu analysieren."
      />
    )
  }
  if (!vm.roiData) return null

  const zeigeCo2 = props.zeigeCo2 ?? true
  return (
    <div className="space-y-6">
      <KpiStrip kpis={roiKpiItems(vm.roiData, zeigeCo2, vm.fortschritt)} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <RoiAmortisationChart vm={vm} />
        <RoiTypBalken vm={vm} />
      </div>
      <RoiVergleichBar vm={vm} />
      <RoiDetailTabelle vm={vm} zeigeCo2={zeigeCo2} />
      <RoiHinweis />
    </div>
  )
}
