/**
 * CockpitJahrV4 — die Jahres-/Gesamt-Sicht der Cockpit-Zeit-Achse (IA-V4).
 *
 * 1:1-Muster von Cockpit/Monat, nur Granularität = Jahr/Monat:
 *  - Auswahl wie Monat: Desktop {@link JahresRail} (Zeitstrahl, Mini-PV-Balken,
 *    „läuft"-Badge) + mobil schwebender {@link JahrStepper}. Responsive identisch.
 *  - {@link JahrHeader} = Pendant zu MonatHeader (Titel Jahr + Status + Reload +
 *    Quellen-Provenance).
 *  - `BlockShell` mit DERSELBEN Block-Reihe wie Monat: Kennzahlen → Energie-Bilanz
 *    → Verlauf (12 Monatsbalken) → Komponenten (Speicher/WP/E-Mob/BKW/Sonstiges)
 *    → Finanzen — über die GETEILTEN Monat-Bauer (`baueKomponentenBloecke('jahr')`,
 *    `finanzTeaserBlock`).
 *
 * Datenpfade — kein neuer Endpoint (D3):
 *  - Voll-Aggregat (KPIs/Komponenten/Finanzen/SOLL) = Σ der 12 kanonischen
 *    Monats-Antworten `aktuellerMonatApi.getData` (nur Monate mit Daten) via
 *    {@link baueJahrAlsMonat}. So existieren ALLE Komponenten-KPIs (anders als Tag).
 *  - Verlauf-Chart + Vorjahr/Ø-Jahr-Vergleich = `monatsdatenApi.listAggregiert`
 *    (Σ der IMD je Monat), einmal je Anlage geladen.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fmtCalc, FehlerZustand, ChartDatenTabelle } from '../components/ui'
import { AnlageLeer, DatenLeer } from './OnboardingLeer'
import { BlockShell, BlockStackSkeleton, KpiStrip, type Block } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar, usePark } from '../components/park'
import { useApiData, useScrollErhalt } from '../hooks'
import { BLOCK_IDENTITAET } from '../lib'
import { baueJahrKpis, JahrBilanz } from './JahrBilanz'
import { monatBilanzParkIds } from './bilanzParkIds'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { finanzTeaserBlock } from './MonatRahmen'
import { JahrVerlaufChart, baueJahrChartDaten } from './JahrVerlaufChart'
import { verlaufTabellenSpalten } from './verlaufVergleich'
import { JahresRail, type JahrRailEintrag } from './JahresRail'
import { JahrStepper } from './JahrStepper'
import { JahrHeader } from './JahrRahmen'
import { baueJahrAlsMonat, jahrVergleichAus, mittelJahre, type JahrVergleich } from './JahrAggregat'
import { aktuellerMonatApi, type AktuellerMonatResponse } from '../api/aktuellerMonat'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'

// persistKey-SoT der Sicht — geteilt von BlockShell (Block-Ebene) und ParkProvider
// (Element-Ebene); eigene LS-Prefixe (`eedc-bloecke:` vs. `eedc-park:`).
const SICHT_KEY = 'v4-cockpit-jahr'

export default function CockpitJahrV4(props: { anlageId: number | undefined }) {
  // ParkProvider umschließt den Body (wie Cockpit/Monat, SLICE-1-Referenz).
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <CockpitJahrInner {...props} />
    </ParkProvider>
  )
}

function CockpitJahrInner({ anlageId }: { anlageId: number | undefined }) {
  const park = usePark()
  const [jahr, setJahr] = useState<number | null>(null)

  // Monatsreihe (alle Jahre) einmal je Anlage — liefert verfügbare Jahre, die
  // Verlauf-Monatsbalken und die Vorjahr/Ø-Jahr-Vergleiche. Default = neuestes
  // Jahr mit Daten. R18-2 (SWR): über den Sicht-Cache von useApiData — beim
  // Tab-Wechsel stehen die alten Daten sofort (kein Skeleton), still revalidiert.
  const monateQ = useApiData(
    () => monatsdatenApi.listAggregiert(anlageId!),
    [anlageId],
    { enabled: !!anlageId, swrKey: `v4-jahr-liste:${anlageId}` },
  )
  const alleMonate = useMemo<AggregierteMonatsdaten[]>(() => monateQ.data ?? [], [monateQ.data])
  useEffect(() => {
    if (!monateQ.data) return
    const jahre = [...new Set(monateQ.data.map((m) => m.jahr))].sort((a, b) => b - a)
    setJahr((aktuell) => aktuell ?? jahre[0] ?? null)
  }, [monateQ.data])

  // Voll-Aggregat des gewählten Jahres = Σ der Monats-Antworten (nur Monate mit Daten).
  const ladeJahr = useCallback(async (anlage: number, j: number): Promise<AktuellerMonatResponse> => {
    const heute = new Date()
    const istLaufend = j === heute.getFullYear()
    const monateMitDaten = [...new Set(alleMonate.filter((m) => m.jahr === j).map((m) => m.monat))]
    // Laufendes Jahr: auch den aktuellen Monat einschließen (evtl. noch ohne
    // abgeschlossene Aggregat-Zeile, aber mit Live-Daten).
    if (istLaufend && !monateMitDaten.includes(heute.getMonth() + 1)) monateMitDaten.push(heute.getMonth() + 1)
    const monate = (await Promise.all(
      monateMitDaten.sort((a, b) => a - b).map((m) => aktuellerMonatApi.getData(anlage, j, m).catch(() => null)),
    )).filter((m): m is AktuellerMonatResponse => m != null)
    return baueJahrAlsMonat(monate, j)
  }, [alleMonate])

  // keepPreviousData: Jahreswechsel aktualisiert den Block-Stack in-place statt
  // Skeleton (detLAN D7-2) — auch ohne Cache-Stand für das Ziel-Jahr.
  const jahrQ = useApiData(
    () => ladeJahr(anlageId!, jahr!),
    [anlageId, jahr, ladeJahr],
    {
      enabled: !!anlageId && jahr != null && alleMonate.length > 0,
      swrKey: `v4-jahr:${anlageId}:${jahr}`,
      keepPreviousData: true,
    },
  )
  const jahrData = jahrQ.data
  const loading = monateQ.loading || (jahr != null && jahrQ.loading)
  const reloading = jahrQ.reloading
  const error = monateQ.data == null && monateQ.error
    ? 'Fehler beim Laden der Jahre'
    : jahrQ.data == null && jahrQ.error ? 'Fehler beim Laden des Jahres' : null
  const reload = jahrQ.refetch

  // B1: Scroll-Position beim Jahreswechsel halten (siehe CockpitMonatV4).
  const rootRef = useRef<HTMLDivElement>(null)
  const merkeScroll = useScrollErhalt(rootRef, loading)
  const waehle = useCallback((j: number) => { merkeScroll(); setJahr(j) }, [merkeScroll])

  // Rail-/Stepper-Liste = verfügbare Jahre + PV (Mini-Balken) + laufendes Jahr.
  const railEntries = useMemo<JahrRailEintrag[]>(() => {
    const hj = new Date().getFullYear()
    const summeJe = new Map<number, number>()
    for (const m of alleMonate) summeJe.set(m.jahr, (summeJe.get(m.jahr) ?? 0) + (m.pv_erzeugung_kwh ?? 0))
    const entries: JahrRailEintrag[] = [...summeJe.entries()].map(([j, pv]) => ({ jahr: j, pv_kwh: pv, laufend: j === hj }))
    if (!entries.some((e) => e.jahr === hj)) entries.push({ jahr: hj, pv_kwh: 0, laufend: true })
    return entries
  }, [alleMonate])

  const istLaufend = jahr != null && jahr === new Date().getFullYear()

  // Verlauf-Monatsbalken + Vergleiche aus der Monatsreihe.
  const monatsZeilen = useMemo(
    () => (jahr == null ? [] : alleMonate.filter((m) => m.jahr === jahr)),
    [alleMonate, jahr],
  )
  const vorjahr = useMemo<JahrVergleich | null>(() => {
    if (jahr == null) return null
    const hatVj = alleMonate.some((m) => m.jahr === jahr - 1)
    return hatVj ? jahrVergleichAus(alleMonate, jahr - 1) : null
  }, [alleMonate, jahr])
  const oeJahr = useMemo(() => {
    if (jahr == null) return null
    const andere = [...new Set(alleMonate.map((m) => m.jahr))].filter((j) => j !== jahr)
    return mittelJahre(andere.map((j) => jahrVergleichAus(alleMonate, j)))
  }, [alleMonate, jahr])

  const bloecke = useMemo<Block[]>(() => {
    if (jahr == null) return []
    const d = jahrData
    const bilanzSummary = d
      ? `${fmtCalc(d.pv_erzeugung_kwh, 0, '—')} kWh PV · ${fmtCalc(d.autarkie_prozent, 0, '—')} % Autarkie${
          d.soll_pv_kwh != null && d.pv_erzeugung_kwh != null && d.soll_pv_kwh > 0
            ? ` · SOLL ${fmtCalc((d.pv_erzeugung_kwh / d.soll_pv_kwh) * 100, 0, '—')} %`
            : ''}`
      : 'IST / Vorjahr / Ø-Jahr'
    // Kennzahlen-Kacheln parkbar (SLICE 1): stabile parkId je Titel; geparkte im Strip
    // ausgeblendet, sind ALLE geparkt → Block-Hülle weglassen (Monat-Referenz).
    const kpiItems = d
      ? baueJahrKpis(d, vorjahr).map((k) => ({
          ...k,
          parkId: `kpi:${k.title.toLowerCase().replace(/[^a-z0-9]+/gi, '-')}`,
        }))
      : []
    const sichtbareKpi = kpiItems.filter((k) => !park.istGeparkt(k.parkId))
    const kennzahlenBlock: Block | null = d
      ? (sichtbareKpi.length > 0
          ? {
              id: 'kpi', title: 'Kennzahlen', ...BLOCK_IDENTITAET.kennzahlen,
              summary: '5 Energie-Kennzahlen + Netto-Ertrag + Jahresergebnis + Netz-Kosten',
              defaultOpen: true,
              render: () => <KpiStrip kpis={sichtbareKpi} />,
            }
          : null)
      : {
          id: 'kpi', title: 'Kennzahlen', ...BLOCK_IDENTITAET.kennzahlen,
          summary: '5 Energie-Kennzahlen + Netto-Ertrag + Jahresergebnis + Netz-Kosten',
          defaultOpen: true,
          render: () => <p className="text-sm text-gray-500 dark:text-gray-400">Keine Jahres-Kennzahlen verfügbar.</p>,
        }
    const finanzBlock = d ? finanzTeaserBlock(d, park, 'jahr') : null
    return [
      ...(kennzahlenBlock ? [kennzahlenBlock] : []),
      // Bilanz-Block: jede Teil-Anzeige einzeln parkbar (in JahrBilanz, gleiche IDs wie
      // Monat — gleicher Aggregat-Shape); Block entfällt erst, wenn ALLE geparkt sind.
      ...(d && monatBilanzParkIds(d).every((id) => park.istGeparkt(id)) ? [] : [{
        id: 'bilanz', title: 'Energie-Bilanz', ...BLOCK_IDENTITAET.energieBilanz,
        summary: bilanzSummary,
        defaultOpen: false,
        render: () => (d
          ? <JahrBilanz d={d} vj={vorjahr} oj={oeJahr} ojCount={oeJahr?.count ?? 0} />
          : <p className="text-sm text-gray-500 dark:text-gray-400">Keine Vergleichsdaten verfügbar.</p>),
      }]),
      ...(park.istGeparkt('el:verlauf') ? [] : [{
        id: 'verlauf', title: 'Verlauf', ...BLOCK_IDENTITAET.verlauf,
        summary: 'Monats-Bilanz: Erzeugung / Verbrauch / Autarkie',
        defaultOpen: false,
        render: () => <Parkbar id="el:verlauf" titel="Verlauf"><JahrVerlaufChart monate={monatsZeilen} /></Parkbar>,
        // Paket CT (Pilot): Tabellen-Ablesung im Fokus-Overlay — dieselbe Datenreihe
        // wie der Chart (baueJahrChartDaten), Spalten = Union der Chart-Serien.
        renderTabelle: () => (
          <ChartDatenTabelle
            xLabel="Monat"
            xKey="monat"
            spalten={verlaufTabellenSpalten(true)}
            daten={baueJahrChartDaten(monatsZeilen)}
            csvDateiname={`verlauf_${jahr}.csv`}
          />
        ),
      }]),
      ...(d ? baueKomponentenBloecke(d, park, 'jahr') : []),
      ...(finanzBlock ? [finanzBlock] : []),
    ]
  }, [jahr, jahrData, vorjahr, oeJahr, monatsZeilen, park])

  if (!anlageId) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <AnlageLeer titel="Noch keine Anlage gewählt." />
      </div>
    )
  }

  return (
    <div ref={rootRef} className="p-3 sm:p-6 max-w-[1920px] mx-auto">
      {/* Mobil: schwebender Player-Stepper — direktes Kind der voll-hohen Wurzel. */}
      <JahrStepper entries={railEntries} jahr={jahr ?? 0} onSelect={waehle} />

      <div className="lg:flex lg:gap-6">
        {/* Desktop: Rail-Sidebar (links) */}
        <div className="hidden lg:block lg:w-52 lg:shrink-0">
          <JahresRail entries={railEntries} jahr={jahr ?? 0} onSelect={waehle} />
        </div>

        <div className="flex-1 min-w-0 space-y-4">
          <JahrHeader jahr={jahr ?? 0} laufend={istLaufend} d={jahrData} onReload={reload} reloading={reloading} />

          {error ? (
            // B8-Fehler-Baustein (S15). Retry nur wenn reload greifen kann (Jahr gewählt);
            // beim Listen-Fetch-Fehler (jahr==null) wäre reload no-op → kein Fassade-Knopf.
            <FehlerZustand text={error} onRetry={jahr != null ? reload : undefined} />
          ) : loading && !jahrData ? (
            // Skeleton NUR beim Erst-Load (detLAN D7-2, 2026-06-27; analog Tag T2).
            // Beim Jahreswechsel bleibt der Block-Stack stehen und aktualisiert sich
            // in-place; kein `key={…}` mehr → BlockShell re-rendert statt zu remounten.
            <BlockStackSkeleton label="Lade Jahr…" />
          ) : jahr == null ? (
            <DatenLeer titel="Noch keine Jahresdaten erfasst." />
          ) : (
            <BlockShell
              persistKey={SICHT_KEY}
              bloecke={bloecke}
              sortierbar
              /* D10-2: im Vollbild läuft die Jahres-Nav oben mit (auf jeder Breite). */
              fokusKopf={
                <JahrStepper entries={railEntries} jahr={jahr ?? 0} onSelect={waehle} immerSichtbar />
              }
            />
          )}

          {/* Element-Park-Fuß (SLICE 1): Hinweiszeile + „Geparkt (n)". Inert leer,
              bis etwas geparkt ist; rendert nichts ohne ParkProvider. */}
          <ParkFuss />
        </div>
      </div>
    </div>
  )
}
