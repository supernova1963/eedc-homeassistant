/**
 * AuswertungenPrognoseV4 — Prognose-Auswertung (A.5 Sub 4, Element-Rebuild).
 *
 * Fünf verschiebbare BlockShell-Blöcke, jeder aus EINZELN parkbaren Elementen
 * (Gernot-Abnahme 2026-06-26: feiner Park wie Sub 2/3, volle Extraktion). Die
 * Render-Bausteine + Daten-Hooks liegen geteilt in `components/prognose/*` (eine
 * Code-Wahrheit mit den IST-Sichten); hier nur Komposition + Park-Hüllen.
 *   ① Jahres-SOLL/IST gegen PVGIS · ② SOLL/IST pro PV-String · ③ Mehrjahres-
 *   Performance (data-gated „Alle Jahre") · ④ Quellen-Genauigkeit · ⑤ Tages-/Stundenprofil.
 *
 * R5: EINE Jahr-Steuerung im Kopf speist ①②③ (bei „Alle Jahre" → ① neuestes Jahr).
 * R6: jede KPI/Chart/Tabelle parkbar (`Parkbar`/KpiStrip-`parkId`). Datenladung je
 * Block lazy (BlockShell rendert eingeklappte Blöcke nicht). Feld-Sperren (SFML
 * draußen, Solcast-Spalte) + Format (R1/R2/R3) stecken in den geteilten Teilen.
 */
import { Target, Sun, TrendingUp, GitCompareArrows, Clock } from 'lucide-react'
import { LoadingSpinner, Card, Alert } from '../components/ui'
import { BlockShell, KpiStrip, type Block } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar } from '../components/park'
import {
  usePrognoseVsIst, pvgisKpiItems,
  PvgisSpeichern, PvgisMonatsChart, PvgisDetailTabelle, PvgisErklaerung,
} from '../components/prognose/PrognoseVsIstTeile'
import {
  usePvStrings, pvStringsKpiItems, exportPvStringsCsv,
  PvStringHeaderZeile, PvStringBestSchlecht, PvStringSollIstBar,
  PvStringMonatsverlauf, PvStringTabelle, PvStringMehrjahr,
} from '../components/prognose/PvStringsTeile'
import {
  usePrognoseVergleich, hatLernfaktorO12, hatStratifizierung, hatTracking,
  PvgKpiMatrix, PvgStatusHinweise, PvgLernfaktorO12, PvgStratifizierung, PvgHeatmap,
  PvgStundenprofil, Pvg24hTabelle, Pvg7TageTabelle, PvgGenauigkeitsTracking,
} from '../components/prognose/PrognoseVergleichTeile'
import { useSelectedAnlage } from '../hooks'
import { useAuswertungBasis } from './useAuswertungBasis'
import { AuswertungKopf } from './AuswertungKopf'

const SICHT_KEY = 'v4-auswertungen-prognose'

// ① Jahres-SOLL/IST gegen PVGIS ────────────────────────────────────────────────
function BlockPvgis({ anlageId, jahr }: { anlageId: number; jahr: number | undefined }) {
  const vm = usePrognoseVsIst(anlageId, jahr)
  if (vm.loading) return <LoadingSpinner text="Lade Prognose…" />
  if (vm.error) return <Alert type="error">{vm.error}</Alert>
  if (!vm.prognose) return <p className="text-sm text-gray-500 dark:text-gray-400">Keine PVGIS-Prognose verfügbar — bitte PV-Module unter Einstellungen → Investitionen anlegen.</p>
  if (vm.monatsdaten.length === 0) return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Monatsdaten für diese Anlage vorhanden.</p>
  return (
    <div className="space-y-4">
      <PvgisSpeichern vm={vm} />
      <KpiStrip kpis={pvgisKpiItems(vm, jahr)} />
      <Parkbar id="chart:pvgis-monat" titel="Monatlicher Vergleich"><PvgisMonatsChart vm={vm} jahr={jahr} /></Parkbar>
      <Parkbar id="tabelle:pvgis-detail" titel="Monatliche Details"><PvgisDetailTabelle vm={vm} /></Parkbar>
      <Parkbar id="info:pvgis-erklaerung" titel="Interpretation der Abweichungen"><PvgisErklaerung /></Parkbar>
    </div>
  )
}

// ② SOLL/IST pro PV-String ──────────────────────────────────────────────────────
function BlockStrings({ anlageId, selectedYear, jahre, zeitraumLabel }: {
  anlageId: number; selectedYear: number | 'all'; jahre: number[]; zeitraumLabel: string
}) {
  const { data, loading, error } = usePvStrings(anlageId, selectedYear, jahre)
  if (loading) return <LoadingSpinner text="Lade PV-String-Daten…" />
  if (error) return <Alert type="error">{error}</Alert>
  if (!data || data.strings.length === 0) return <p className="text-sm text-gray-500 dark:text-gray-400">Keine PV-Module gefunden.</p>
  if (!data.hat_prognose) return <Alert type="warning">Keine PVGIS-Prognose vorhanden — bitte unter Einstellungen → PVGIS abrufen.</Alert>
  return (
    <div className="space-y-4">
      <PvStringHeaderZeile data={data} zeitraumLabel={zeitraumLabel} onCsv={() => exportPvStringsCsv(data, selectedYear)} />
      <KpiStrip kpis={pvStringsKpiItems(data, zeitraumLabel)} />
      {data.strings.length > 1 && (
        <Parkbar id="badge:best-schlecht" titel="Beste/Schwächste Performance"><PvStringBestSchlecht data={data} /></Parkbar>
      )}
      <Parkbar id="chart:soll-ist-bar" titel="SOLL vs IST pro String"><PvStringSollIstBar data={data} /></Parkbar>
      <Parkbar id="chart:string-monatsverlauf" titel="Monatsverlauf SOLL vs IST"><PvStringMonatsverlauf data={data} selectedYear={selectedYear} /></Parkbar>
      <Parkbar id="tabelle:string-details" titel="String-Details"><PvStringTabelle data={data} /></Parkbar>
    </div>
  )
}

// ③ Mehrjahres-Performance — fester 3. Block (year-dependent Trio ①②③); zeigt den
//    Mehrjahres-Chart nur bei Kopf-Jahr = „Alle Jahre", sonst einen Hinweis.
function BlockMehrjahr({ anlageId, jahre, aktiv }: { anlageId: number; jahre: number[]; aktiv: boolean }) {
  if (!aktiv) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Die Mehrjahres-Performance erscheint bei Jahr = „Alle Jahre" (und mindestens zwei Jahren mit Daten).</p>
  }
  return <BlockMehrjahrInner anlageId={anlageId} jahre={jahre} />
}
function BlockMehrjahrInner({ anlageId, jahre }: { anlageId: number; jahre: number[] }) {
  const { data, loading, error, jahresvergleichData } = usePvStrings(anlageId, 'all', jahre)
  if (loading) return <LoadingSpinner text="Lade Mehrjahres-Daten…" />
  if (error) return <Alert type="error">{error}</Alert>
  if (!data || jahresvergleichData.length <= 1) return <p className="text-sm text-gray-500 dark:text-gray-400">Mehrjahres-Vergleich braucht mindestens zwei Jahre mit Daten.</p>
  return (
    <Parkbar id="chart:mehrjahr" titel="Performance-Entwicklung über Jahre">
      <PvStringMehrjahr data={data} jahresvergleichData={jahresvergleichData} />
    </Parkbar>
  )
}

// ④ Quellen-Genauigkeit OM · eedc · Solcast ─────────────────────────────────────
function BlockGenauigkeit({ anlageId }: { anlageId: number }) {
  const vm = usePrognoseVergleich(anlageId)
  if (vm.loading) return <LoadingSpinner text="Lade Genauigkeits-Daten…" />
  if (vm.error) return <Alert type="error">{vm.error}</Alert>
  if (!vm.data) return null
  return (
    <div className="space-y-4">
      <Parkbar id="matrix:genauigkeit" titel="KPI-Matrix (Quellen × Zeiträume)"><PvgKpiMatrix vm={vm} /></Parkbar>
      <PvgStatusHinweise vm={vm} />
      {hatLernfaktorO12(vm) && <Parkbar id="card:lernfaktor-o12" titel="Lernfaktor O1+O2"><PvgLernfaktorO12 vm={vm} /></Parkbar>}
      {hatStratifizierung(vm) && <Parkbar id="card:stratifizierung" titel="Wetter-Stratifizierung"><PvgStratifizierung vm={vm} /></Parkbar>}
      <Parkbar id="card:heatmap" titel="Korrekturprofil-Heatmap"><PvgHeatmap vm={vm} /></Parkbar>
      {hatTracking(vm) && <Parkbar id="card:genauigkeits-tracking" titel="Genauigkeits-Tracking"><PvgGenauigkeitsTracking vm={vm} /></Parkbar>}
    </div>
  )
}

// ⑤ Tages-/Stundenprofil & Solcast-Roadmap ──────────────────────────────────────
function BlockProfil({ anlageId }: { anlageId: number }) {
  const vm = usePrognoseVergleich(anlageId)
  if (vm.loading) return <LoadingSpinner text="Lade Profil-Daten…" />
  if (vm.error) return <Alert type="error">{vm.error}</Alert>
  if (!vm.data) return null
  return (
    <div className="space-y-4">
      <Parkbar id="chart:stundenprofil" titel="Tagesverlauf — Stundenprofil"><PvgStundenprofil vm={vm} /></Parkbar>
      <Parkbar id="tabelle:24h" titel="Stundenvergleich heute"><Pvg24hTabelle vm={vm} /></Parkbar>
      <Parkbar id="tabelle:7-tage" titel="7-Tage-Vergleich"><Pvg7TageTabelle vm={vm} /></Parkbar>
    </div>
  )
}

export default function AuswertungenPrognoseV4() {
  const { anlagen, selectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const basis = useAuswertungBasis(selectedAnlageId)

  if (anlagenLoading || basis.loading) return <LoadingSpinner text="Lade Prognose-Daten…" />
  if (anlagen.length === 0 || !selectedAnlageId) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage angelegt.</p></Card>
      </div>
    )
  }

  // R5: das Kopf-Jahr speist ①②③.
  const anlageId = selectedAnlageId
  const selectedYear: number | 'all' = basis.jahr === 'alle' ? 'all' : basis.jahr
  const jahrFuerBlock = basis.jahr === 'alle' ? basis.jahre[0] : basis.jahr
  const zeigeMehrjahr = basis.jahr === 'alle' && basis.jahre.length > 1

  const bloecke: Block[] = [
    {
      id: 'pvgis', title: 'Jahres-SOLL/IST gegen PVGIS', icon: Target, farbe: 'text-purple-500', defaultOpen: true,
      summary: 'PVGIS-Jahresprognose vs. IST + Monats-Detail · „Prognose speichern"',
      render: () => <BlockPvgis anlageId={anlageId} jahr={jahrFuerBlock} />,
    },
    {
      id: 'pvstrings', title: 'SOLL/IST pro PV-String', icon: Sun, farbe: 'text-amber-500', defaultOpen: false,
      summary: 'String-Performance gegen PVGIS (KPIs · SOLL-IST · Monatsverlauf · Tabelle)',
      render: () => <BlockStrings anlageId={anlageId} selectedYear={selectedYear} jahre={basis.jahre} zeitraumLabel={basis.zeitraumLabel} />,
    },
    {
      id: 'mehrjahr', title: 'Mehrjahres-Performance', icon: TrendingUp, farbe: 'text-blue-500', defaultOpen: false,
      summary: 'Performance-Ratio pro String über die Jahre (bei „Alle Jahre")',
      render: () => <BlockMehrjahr anlageId={anlageId} jahre={basis.jahre} aktiv={zeigeMehrjahr} />,
    },
    {
      id: 'genauigkeit', title: 'Quellen-Genauigkeit (OM · eedc · Solcast)', icon: GitCompareArrows, farbe: 'text-orange-500', defaultOpen: false,
      summary: 'Multi-Quellen-Genauigkeit (MAPE/Bias), wetter-stratifiziert · Tage-Fenster 7/10/30',
      render: () => <BlockGenauigkeit anlageId={anlageId} />,
    },
    {
      id: 'profil', title: 'Tages-/Stundenprofil', icon: Clock, farbe: 'text-blue-400', defaultOpen: false,
      summary: 'Stundenprofil-Chart · 24h-Vergleich · 7-Tage-Vergleich',
      render: () => <BlockProfil anlageId={anlageId} />,
    },
  ]

  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
        <AuswertungKopf titel="Prognose" jahr={basis.jahr} setJahr={basis.setJahr} jahre={basis.jahre} />
        <BlockShell key={`prog-${basis.jahr}`} persistKey={SICHT_KEY} bloecke={bloecke} sortierbar />
        <ParkFuss />
      </div>
    </ParkProvider>
  )
}
