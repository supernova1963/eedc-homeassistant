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
 * R5: EINE Jahr-Steuerung speist ①②③ — seit R18-3 (Option B) sitzt sie in der
 * Dispatcher-Steuerleiste (`AuswertungenV4`), `basis` kommt als Prop. R18-3a:
 * bei „Alle Jahre" zeigt ① sichtbar gekennzeichnet das neueste Jahr
 * (`ZeitraumHinweis`) statt still zu verengen; ④/⑤ folgen dem Filter nicht
 * (eigene Tage-Fenster) und kennzeichnen das ebenso.
 * R6: jede KPI/Chart/Tabelle parkbar (`Parkbar`/KpiStrip-`parkId`). Datenladung je
 * Block lazy (BlockShell rendert eingeklappte Blöcke nicht). Feld-Sperren (SFML
 * draußen, Solcast-Spalte) + Format (R1/R2/R3) stecken in den geteilten Teilen.
 *
 * Auto-Hide (Phase 3b, Gernot 2026-07-09): weil die Block-DATEN hier lazy in den
 * Kind-Komponenten liegen (nicht auf View-Ebene wie CO₂/Finanzen/ROI), MELDET jedes
 * Kind seine real gerenderten Park-IDs hoch (`melde`). Der Parent behält die letzte
 * Meldung je Block (überlebt das Unmounten des versteckten Blocks → kein Oszillieren)
 * und lässt einen Block weg, sobald ALLE gemeldeten IDs geparkt sind.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Target, Sun, TrendingUp, GitCompareArrows, Clock } from 'lucide-react'
import { Alert, FehlerZustand, KpiStripSkeleton, ChartSkeleton, TabellenSkeleton } from '../components/ui'
import { BlockShell, BlockStackSkeleton, KpiStrip, type Block } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar, usePark } from '../components/park'
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
import type { AuswertungBasis } from './useAuswertungBasis'
import { AuswertungKopf } from './AuswertungKopf'
import { ZeitraumHinweis } from './ZeitraumHinweis'
import { AnlageLeer } from './OnboardingLeer'

const SICHT_KEY = 'v4-auswertungen-prognose'

/** Reporter: ein Kind meldet dem Parent die IDs, die es GERADE parkbar rendert. */
type MeldeFn = (block: string, ids: string[]) => void
const nurStrings = (xs: (string | undefined)[]): string[] => xs.filter((x): x is string => !!x)

// ① Jahres-SOLL/IST gegen PVGIS ────────────────────────────────────────────────
function BlockPvgis({ anlageId, jahr, melde }: { anlageId: number; jahr: number | undefined; melde: MeldeFn }) {
  const vm = usePrognoseVsIst(anlageId, jahr)
  const leer = vm.loading || !!vm.error || !vm.prognose || vm.monatsdaten.length === 0
  const ids = useMemo(
    () => (leer ? [] : nurStrings([
      ...pvgisKpiItems(vm, jahr).map((k) => k.parkId),
      'chart:pvgis-monat', 'tabelle:pvgis-detail', 'info:pvgis-erklaerung',
    ])),
    [leer, vm, jahr],
  )
  useEffect(() => melde('pvgis', ids), [melde, ids])
  // B8 (S15): Block-Skeleton in Zielform (KPI-Strip + Chart) statt Sektions-Spinner.
  if (vm.loading) return <div className="space-y-4"><KpiStripSkeleton label="Lade Prognose…" /><ChartSkeleton /></div>
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
function BlockStrings({ anlageId, selectedYear, jahre, zeitraumLabel, melde }: {
  anlageId: number; selectedYear: number | 'all'; jahre: number[]; zeitraumLabel: string; melde: MeldeFn
}) {
  const { data, loading, error } = usePvStrings(anlageId, selectedYear, jahre)
  const leer = loading || !!error || !data || data.strings.length === 0 || !data.hat_prognose
  const ids = useMemo(
    () => (leer || !data ? [] : nurStrings([
      ...pvStringsKpiItems(data, zeitraumLabel).map((k) => k.parkId),
      ...(data.strings.length > 1 ? ['badge:best-schlecht'] : []),
      'chart:soll-ist-bar', 'chart:string-monatsverlauf', 'tabelle:string-details',
    ])),
    [leer, data, zeitraumLabel],
  )
  useEffect(() => melde('pvstrings', ids), [melde, ids])
  if (loading) return <div className="space-y-4"><KpiStripSkeleton label="Lade PV-String-Daten…" /><ChartSkeleton /></div>
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
function BlockMehrjahr({ anlageId, jahre, aktiv, melde }: { anlageId: number; jahre: number[]; aktiv: boolean; melde: MeldeFn }) {
  useEffect(() => { if (!aktiv) melde('mehrjahr', []) }, [aktiv, melde])
  if (!aktiv) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Die Mehrjahres-Performance erscheint bei Jahr = „Alle Jahre" (und mindestens zwei Jahren mit Daten).</p>
  }
  return <BlockMehrjahrInner anlageId={anlageId} jahre={jahre} melde={melde} />
}
function BlockMehrjahrInner({ anlageId, jahre, melde }: { anlageId: number; jahre: number[]; melde: MeldeFn }) {
  const { data, loading, error, jahresvergleichData } = usePvStrings(anlageId, 'all', jahre)
  const zeigt = !loading && !error && !!data && jahresvergleichData.length > 1
  const ids = useMemo(() => (zeigt ? ['chart:mehrjahr'] : []), [zeigt])
  useEffect(() => melde('mehrjahr', ids), [melde, ids])
  if (loading) return <ChartSkeleton label="Lade Mehrjahres-Daten…" />
  if (error) return <Alert type="error">{error}</Alert>
  if (!data || jahresvergleichData.length <= 1) return <p className="text-sm text-gray-500 dark:text-gray-400">Mehrjahres-Vergleich braucht mindestens zwei Jahre mit Daten.</p>
  return (
    <Parkbar id="chart:mehrjahr" titel="Performance-Entwicklung über Jahre">
      <PvStringMehrjahr data={data} jahresvergleichData={jahresvergleichData} />
    </Parkbar>
  )
}

// ④ Quellen-Genauigkeit OM · eedc · Solcast ─────────────────────────────────────
function BlockGenauigkeit({ anlageId, melde }: { anlageId: number; melde: MeldeFn }) {
  const vm = usePrognoseVergleich(anlageId)
  const ids = useMemo(() => {
    const d = vm.data
    if (vm.loading || vm.error || !d) return []
    // Spiegelt exakt die Null-Bedingung von PvgStatusHinweise (self-wrap) — die ID
    // nur melden, wenn der Hinweis wirklich rendert, sonst hinge der Auto-Hide an
    // einer nie parkbaren ID fest.
    const hasEedc = d.eedc_lernfaktor !== null || d.eedc_heute_kwh !== null
    const zeigeStatus = !!(d.solcast_status && d.solcast_status !== 'ok' && d.solcast_hinweis) || !hasEedc
    return nurStrings([
      'matrix:genauigkeit',
      zeigeStatus ? 'hinweis:quellen-status' : undefined,
      hatLernfaktorO12(vm) ? 'card:lernfaktor-o12' : undefined,
      hatStratifizierung(vm) ? 'card:stratifizierung' : undefined,
      'card:heatmap',
      hatTracking(vm) ? 'card:genauigkeits-tracking' : undefined,
    ])
  }, [vm])
  useEffect(() => melde('genauigkeit', ids), [melde, ids])
  if (vm.loading) return <TabellenSkeleton label="Lade Genauigkeits-Daten…" />
  if (vm.error) return <Alert type="error">{vm.error}</Alert>
  if (!vm.data) return null
  return (
    <div className="space-y-4">
      <Parkbar id="matrix:genauigkeit" titel="KPI-Matrix (Quellen × Zeiträume)"><PvgKpiMatrix vm={vm} /></Parkbar>
      {/* D17-15: Status-/Leerzustand-Hinweise parkbar (self-wrap; rendert null bei
          keinem Inhalt → kein leerer Rahmen, R17-5-konform). */}
      <PvgStatusHinweise vm={vm} parkbar={{ id: 'hinweis:quellen-status', titel: 'Status-Hinweise' }} />
      {hatLernfaktorO12(vm) && <Parkbar id="card:lernfaktor-o12" titel="Lernfaktor O1+O2"><PvgLernfaktorO12 vm={vm} /></Parkbar>}
      {hatStratifizierung(vm) && <Parkbar id="card:stratifizierung" titel="Wetter-Stratifizierung"><PvgStratifizierung vm={vm} /></Parkbar>}
      <Parkbar id="card:heatmap" titel="Korrekturprofil-Heatmap"><PvgHeatmap vm={vm} /></Parkbar>
      {hatTracking(vm) && <Parkbar id="card:genauigkeits-tracking" titel="Genauigkeits-Tracking"><PvgGenauigkeitsTracking vm={vm} /></Parkbar>}
    </div>
  )
}

// ⑤ Tages-/Stundenprofil & Solcast-Roadmap ──────────────────────────────────────
function BlockProfil({ anlageId, melde }: { anlageId: number; melde: MeldeFn }) {
  const vm = usePrognoseVergleich(anlageId)
  const ids = useMemo(
    () => (vm.loading || vm.error || !vm.data ? [] : ['chart:stundenprofil', 'tabelle:24h', 'tabelle:7-tage']),
    [vm],
  )
  useEffect(() => melde('profil', ids), [melde, ids])
  if (vm.loading) return <ChartSkeleton label="Lade Profil-Daten…" />
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

export default function AuswertungenPrognoseV4({ basis }: { basis: AuswertungBasis }) {
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <PrognoseInner basis={basis} />
    </ParkProvider>
  )
}

function PrognoseInner({ basis }: { basis: AuswertungBasis }) {
  const park = usePark()
  const { anlagen, selectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()

  // Auto-Hide: letzte je-Block gemeldete Park-IDs (überlebt Unmount des versteckten
  // Blocks → kein Oszillieren). Gleichheits-geschützt gegen Render-Schleifen.
  const [blockIds, setBlockIds] = useState<Record<string, string[]>>({})
  const melde = useCallback<MeldeFn>((block, ids) => {
    setBlockIds((s) => {
      const cur = s[block]
      if (cur && cur.length === ids.length && cur.every((v, i) => v === ids[i])) return s
      return { ...s, [block]: ids }
    })
  }, [])
  const sichtbar = useCallback((block: string) => {
    const ids = blockIds[block]
    // Kein Parkbares gemeldet (Lade-/Leerzustand oder noch nie geöffnet) → Block bleibt
    // (zeigt Chrome/Message). Sonst: verstecken, sobald ALLE gemeldeten IDs geparkt sind.
    return !ids || ids.length === 0 || !ids.every((id) => park.istGeparkt(id))
  }, [blockIds, park])

  if (basis.error) {
    // B8 (S15): Basis-Fetch-Fehler sichtbar machen — vorher stille Leere.
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <FehlerZustand text={basis.error} onRetry={basis.refresh} />
      </div>
    )
  }
  if (anlagenLoading || basis.loading) {
    // B8 (S15): Sicht-Skeleton in BlockShell-Form (5 Blöcke: ① offen + 4 zu) statt
    // Vollseiten-Spinner — kein Komplett-Sprung beim Erscheinen des Inhalts.
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <BlockStackSkeleton label="Lade Prognose-Daten…" zu={4} />
      </div>
    )
  }
  if (anlagen.length === 0 || !selectedAnlageId) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <AnlageLeer titel="Noch keine Anlage angelegt." />
      </div>
    )
  }

  // R5: das Filter-Jahr (Dispatcher-Steuerleiste) speist ①②③.
  const anlageId = selectedAnlageId
  const selectedYear: number | 'all' = basis.jahr === 'alle' ? 'all' : basis.jahr
  // R18-3a: ① ist ein Einzeljahr-Vergleich — bei „Alle Jahre" neuestes Jahr,
  // aber sichtbar gekennzeichnet (ZeitraumHinweis) statt still.
  const jahrFuerBlock = basis.jahr === 'alle' ? basis.jahre[0] : basis.jahr
  const zeigeMehrjahr = basis.jahr === 'alle' && basis.jahre.length > 1

  const bloecke: Block[] = [
    ...(sichtbar('pvgis') ? [{
      id: 'pvgis', title: 'Jahres-SOLL/IST gegen PVGIS', icon: Target, farbe: 'text-purple-500', defaultOpen: true,
      summary: 'PVGIS-Jahresprognose vs. IST + Monats-Detail · „Prognose speichern"',
      render: () => (
        <div className="space-y-4">
          {basis.jahr === 'alle' && jahrFuerBlock != null && (
            <ZeitraumHinweis text={`Filter „Alle Jahre“: der SOLL/IST-Vergleich gegen PVGIS ist ein Einzeljahr-Vergleich und zeigt das Jahr ${jahrFuerBlock}.`} />
          )}
          <BlockPvgis anlageId={anlageId} jahr={jahrFuerBlock} melde={melde} />
        </div>
      ),
    }] : []),
    ...(sichtbar('pvstrings') ? [{
      id: 'pvstrings', title: 'SOLL/IST pro PV-String', icon: Sun, farbe: 'text-amber-500', defaultOpen: false,
      summary: 'String-Performance gegen PVGIS (KPIs · SOLL-IST · Monatsverlauf · Tabelle)',
      render: () => <BlockStrings anlageId={anlageId} selectedYear={selectedYear} jahre={basis.jahre} zeitraumLabel={basis.zeitraumLabel} melde={melde} />,
    }] : []),
    ...(sichtbar('mehrjahr') ? [{
      id: 'mehrjahr', title: 'Mehrjahres-Performance', icon: TrendingUp, farbe: 'text-blue-500', defaultOpen: false,
      summary: 'Performance-Ratio pro String über die Jahre (bei „Alle Jahre")',
      render: () => <BlockMehrjahr anlageId={anlageId} jahre={basis.jahre} aktiv={zeigeMehrjahr} melde={melde} />,
    }] : []),
    ...(sichtbar('genauigkeit') ? [{
      id: 'genauigkeit', title: 'Quellen-Genauigkeit (OM · eedc · Solcast)', icon: GitCompareArrows, farbe: 'text-orange-500', defaultOpen: false,
      summary: 'Multi-Quellen-Genauigkeit (MAPE/Bias), wetter-stratifiziert · Tage-Fenster 7/10/30',
      render: () => (
        <div className="space-y-4">
          {basis.jahr !== 'alle' && (
            <ZeitraumHinweis text="Der Jahr-Filter wirkt hier nicht — die Genauigkeits-Fenster (7/10/30 Tage) beziehen sich immer auf die jüngste Zeit." />
          )}
          <BlockGenauigkeit anlageId={anlageId} melde={melde} />
        </div>
      ),
    }] : []),
    ...(sichtbar('profil') ? [{
      id: 'profil', title: 'Tages-/Stundenprofil', icon: Clock, farbe: 'text-blue-400', defaultOpen: false,
      summary: 'Stundenprofil-Chart · 24h-Vergleich · 7-Tage-Vergleich',
      render: () => (
        <div className="space-y-4">
          {basis.jahr !== 'alle' && (
            <ZeitraumHinweis text="Der Jahr-Filter wirkt hier nicht — Tages-/Stundenprofil zeigt immer die aktuellen Tage." />
          )}
          <BlockProfil anlageId={anlageId} melde={melde} />
        </div>
      ),
    }] : []),
  ]

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      <AuswertungKopf titel="Prognose" />
      <BlockShell key={`prog-${basis.jahr}`} persistKey={SICHT_KEY} bloecke={bloecke} sortierbar />
      <ParkFuss />
    </div>
  )
}
