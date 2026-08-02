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
 *  - Voll-Aggregat (KPIs/Komponenten/Finanzen/SOLL) = Σ der kanonischen
 *    Monats-Antworten `aktuellerMonatApi.getData` (nur Monate mit Daten) via
 *    {@link baueJahrAlsMonat}. So existieren ALLE Komponenten-KPIs (anders als Tag).
 *    Welche Monate das sind, entscheidet seit P-12 (N-65) `zuLadendeMonate` +
 *    `monatHatDaten` — NICHT die Existenz einer aggregierten Zeile: die entsteht
 *    erst beim Monatsabschluss.
 *  - Verlauf-Chart + Vorjahr/Ø-Jahr-Vergleich = `monatsdatenApi.listAggregiert`
 *    (Σ der IMD je Monat), einmal je Anlage geladen.
 *  - CO₂-Bilanz = `cockpitApi.getNachhaltigkeit` (Monats-Fakten/P10), ebenfalls
 *    einmal je Anlage — der Endpoint kennt kein `?jahr=` und wird auch NICHT darum
 *    erweitert; das Jahr filtert die Sicht (s. {@link baueJahrCo2ChartDaten}).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Leaf, Sprout } from 'lucide-react'
import { fmtCalc, FehlerZustand, ChartDatenTabelle } from '../components/ui'
import { AnlageLeer, DatenLeer } from './OnboardingLeer'
import { BlockShell, BlockStackSkeleton, KpiStrip, type Block, type KpiStripItem } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar, usePark } from '../components/park'
import { useApiData, useScrollErhalt } from '../hooks'
import { BLOCK_IDENTITAET, formatCo2 } from '../lib'
import { baueJahrKpis, JahrBilanz } from './JahrBilanz'
import { monatBilanzParkIds } from './bilanzParkIds'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { finanzTeaserBlock } from './MonatRahmen'
import { JahrVerlaufChart, baueJahrChartDaten } from './JahrVerlaufChart'
import { JahrCo2Chart, baueJahrCo2ChartDaten, co2JahresSumme, CO2_TABELLEN_SPALTEN } from './JahrCo2Chart'
import { verlaufTabellenSpalten } from './verlaufVergleich'
import { JahresRail, type JahrRailEintrag } from './JahresRail'
import { JahrStepper } from './JahrStepper'
import { JahrHeader } from './JahrRahmen'
import {
  abgeschlosseneMonate, baueJahrAlsMonat, jahrVergleichAus, kennzahlenFensterAus, mittelJahre,
  monatHatDaten, monatsFenster, monatsFensterAus, zuLadendeMonate, type JahrVergleich,
} from './JahrAggregat'
import { aktuellerMonatApi, type AktuellerMonatResponse } from '../api/aktuellerMonat'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
import { cockpitApi } from '../api/cockpit'

// persistKey-SoT der Sicht — geteilt von BlockShell (Block-Ebene) und ParkProvider
// (Element-Ebene); eigene LS-Prefixe (`eedc-bloecke:` vs. `eedc-park:`).
const SICHT_KEY = 'v4-cockpit-jahr'

/**
 * Ein geladenes Jahr — zwei Aggregate über zwei Monatsmengen (P-12/N-65).
 *
 * `d` ist die Kopfzahl („das Jahr bis heute", alle Monate mit Daten), `dVgl` die
 * Vergleichs-Grundgesamtheit (nur abgeschlossene Monate). Bei einem abgeschlossenen
 * Jahr sind beide dasselbe Objekt.
 */
interface JahrLadung {
  d: AktuellerMonatResponse
  dVgl: AktuellerMonatResponse
  monate: number[]
  vergleichsMonate: number[]
}

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
  //
  // N-65: welche Monate das sind, entscheidet NICHT mehr die Existenz einer
  // aggregierten Zeile — die entsteht erst beim Monatsabschluss, und ein längst
  // gelaufener Monat ohne Abschluss fiel damit komplett aus der Jahreszahl (an der
  // Box: Juli 2026, 1.843 kWh = ein Viertel der angezeigten Ernte). Gefragt wird
  // jetzt das Intervall (`zuLadendeMonate`), geantwortet hat, wer Mengen trägt
  // (`monatHatDaten` — der Endpoint beantwortet auch Monate vor der Inbetriebnahme,
  // dann aber nur mit Stammdaten-Ableitungen wie SOLL und Tarif).
  const ladeJahr = useCallback(async (anlage: number, j: number): Promise<JahrLadung> => {
    const heute = new Date()
    const antworten = (await Promise.all(
      zuLadendeMonate(alleMonate, j, heute).map((m) => aktuellerMonatApi.getData(anlage, j, m).catch(() => null)),
    )).filter((m): m is AktuellerMonatResponse => m != null && monatHatDaten(m))
    const monate = antworten.map((m) => m.monat)
    const vergleichsMonate = abgeschlosseneMonate(monate, j, heute)
    const d = baueJahrAlsMonat(antworten, j)
    const dVgl = vergleichsMonate.length === monate.length
      ? d
      : baueJahrAlsMonat(antworten.filter((m) => vergleichsMonate.includes(m.monat)), j)
    return { d, dVgl, monate, vergleichsMonate }
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
  // CO₂-Zeitreihe (Monats-Fakten/P10) — EIN Abruf je Anlage im selben useApiData-
  // Verbund wie `monateQ`/`jahrQ` (kein loser useEffect daneben, eigener swrKey).
  // Der Endpoint liefert die GANZE Historie und wird bewusst nicht um `?jahr=`
  // erweitert; ein Jahreswechsel löst deshalb auch keinen neuen Abruf aus.
  const co2Q = useApiData(
    () => cockpitApi.getNachhaltigkeit(anlageId!),
    [anlageId],
    { enabled: !!anlageId, swrKey: `v4-jahr-co2:${anlageId}` },
  )
  const co2Monate = useMemo(() => co2Q.data?.monatswerte ?? [], [co2Q.data])
  // JAHRESGEBUNDEN: die Chart-Zeilen — der Filter greift auf die ganze Zeile, nicht
  // auf einzelne Serien (die halb greifende Variante war der Befund N-10).
  const co2Punkte = useMemo(
    () => (jahr == null ? [] : baueJahrCo2ChartDaten(co2Monate, jahr)),
    [co2Monate, jahr],
  )
  // NICHT JAHRESGEBUNDEN: `co2_kumuliert_kg` ist eine Lebensdauer-Zahl. Deshalb der
  // letzte Wert der GESAMTEN Historie (Backend liefert nach (jahr, monat) aufsteigend),
  // ausdrücklich nicht der letzte des gewählten Jahres.
  const co2Kumuliert = co2Monate.length > 0 ? co2Monate[co2Monate.length - 1].co2_kumuliert_kg : 0
  const co2Fehler = co2Q.data == null && co2Q.error != null
  const co2Reload = co2Q.refetch

  const jahrData = jahrQ.data?.d ?? null
  const jahrVglData = jahrQ.data?.dVgl ?? null
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
  // Grundgesamtheit des Jahresvergleichs (Fund N-37): die Monate, für die das
  // ANGEZEIGTE Jahr Daten hat — ohne den laufenden. Ohne sie standen im laufenden
  // Jahr die gelaufenen Monate gegen ein volles Vorjahr. Eine Lücke mitten im Jahr
  // beschneidet damit genauso: die Regel ist „gleiche Monate", nicht „erste N".
  //
  // N-65: die Quelle ist jetzt die WIRKLICH geladene Monatsmenge, nicht mehr
  // `monatsZeilen` (= die aggregierten Zeilen). Sonst wüchse der Widerspruch, den
  // P-12 auflöst: die Kopfzahl zählte einen Monat, den der Vergleich nicht kennt.
  const kopfMonate = useMemo(() => jahrQ.data?.monate ?? [], [jahrQ.data])
  const vergleichsMonate = useMemo(() => jahrQ.data?.vergleichsMonate ?? [], [jahrQ.data])
  // Fenster der Kacheln — nur gesetzt, wenn sie mehr Monate zählen als der Vergleich.
  const kennzahlenFenster = useMemo(
    () => kennzahlenFensterAus(kopfMonate, vergleichsMonate),
    [kopfMonate, vergleichsMonate],
  )
  // Fenster der IST-Spalte der Vergleichstabelle = die Grundgesamtheit selbst.
  const istFenster = useMemo(() => monatsFensterAus(vergleichsMonate), [vergleichsMonate])
  const vorjahr = useMemo<JahrVergleich | null>(() => {
    if (jahr == null) return null
    const vj = jahrVergleichAus(alleMonate, jahr - 1, vergleichsMonate)
    // Keine Überschneidung (Anlage erst im angezeigten Jahr in Betrieb) ⇒ KEIN
    // Vergleich, nicht eine Spalte aus lauter 0.
    return vj.monate.length > 0 ? vj : null
  }, [alleMonate, jahr, vergleichsMonate])
  const oeJahr = useMemo(() => {
    if (jahr == null) return null
    const andere = [...new Set(alleMonate.map((m) => m.jahr))].filter((j) => j !== jahr)
    // In den Ø geht nur ein Jahr ein, das die Grundgesamtheit GANZ abdeckt —
    // sonst mischte sich eine Ein-Monats-Summe (Anlage lief 2023 erst ab Juni) in
    // einen Sechs-Monats-Ø. `count` fällt entsprechend.
    return mittelJahre(andere.map((j) => jahrVergleichAus(alleMonate, j, vergleichsMonate)), vergleichsMonate)
  }, [alleMonate, jahr, vergleichsMonate])
  // Das Fenster, auf das sich die Vergleichszahl bezieht — `null` bei einem vollen
  // Jahr (dann ist nichts zu beschriften).
  const vjFenster = useMemo(() => monatsFenster(vorjahr), [vorjahr])
  const ojFenster = useMemo(() => monatsFenster(oeJahr), [oeJahr])

  const bloecke = useMemo<Block[]>(() => {
    if (jahr == null) return []
    const d = jahrData
    // P-12/N-65: die Kopfzeile eines Blocks trägt sein Zeitfenster, sobald das
    // Jahr nicht deckungsgleich ist. Sie ist der einzige Ort über den Kacheln, der
    // ungekürzt rendert — die Kachel-Zweitzeile ist `truncate` und schnitt ein
    // Präfix genau dort ab, wo die Vorjahres-Angabe steht (an der Box gemessen).
    const mitFenster = (fenster: string | null, text: string) => (fenster ? `${fenster} · ${text}` : text)
    // Der Bilanz-Block fasst die TABELLE zusammen — also die abgeschlossenen Monate,
    // nicht die Kopfzahl. Sonst nennte die eingeklappte Zeile eine andere PV-Zahl als
    // die Tabelle darin.
    const b = jahrVglData ?? d
    // Die SOLL-Erfüllung steht NUR an der PV-Kachel. Über die abgeschlossenen Monate
    // gerechnet ergäbe sie hier eine zweite, andere Prozentzahl für dieselbe Größe
    // (an der Box 119 % gegen 103 % an der Kachel) — der Unterschied ist echt, aber
    // er gehört an EINE Stelle. Ursache ist, dass der laufende Monat sein VOLLES
    // PVGIS-SOLL mitbringt und nur ein paar Tage Ertrag; das ist ein eigener Fund und
    // bestand schon vor P-12 (damals 98,7 % aus Jan–Jun + vollem August).
    // Bei abgeschlossenem Jahr fallen beide Fenster zusammen ⇒ Anzeige wie bisher.
    const bilanzSummary = b
      ? mitFenster(istFenster, `${fmtCalc(b.pv_erzeugung_kwh, 0, '—')} kWh PV · ${fmtCalc(b.autarkie_prozent, 0, '—')} % Autarkie${
          istFenster == null && b.soll_pv_kwh != null && b.pv_erzeugung_kwh != null && b.soll_pv_kwh > 0
            ? ` · SOLL ${fmtCalc((b.pv_erzeugung_kwh / b.soll_pv_kwh) * 100, 0, '—')} %`
            : ''}`)
      : 'IST / Vorjahr / Ø-Jahr'
    const kennzahlenSummary = mitFenster(
      kennzahlenFenster, '5 Energie-Kennzahlen + Netto-Ertrag + Jahresergebnis + Netz-Kosten',
    )
    // Kennzahlen-Kacheln parkbar (SLICE 1): stabile parkId je Titel; geparkte im Strip
    // ausgeblendet, sind ALLE geparkt → Block-Hülle weglassen (Monat-Referenz).
    const kpiItems = d
      ? baueJahrKpis(d, vorjahr, vjFenster).map((k) => ({
          ...k,
          parkId: `kpi:${k.title.toLowerCase().replace(/[^a-z0-9]+/gi, '-')}`,
        }))
      : []
    const sichtbareKpi = kpiItems.filter((k) => !park.istGeparkt(k.parkId))
    const kennzahlenBlock: Block | null = d
      ? (sichtbareKpi.length > 0
          ? {
              id: 'kpi', title: 'Kennzahlen', ...BLOCK_IDENTITAET.kennzahlen,
              summary: kennzahlenSummary,
              defaultOpen: true,
              render: () => <KpiStrip kpis={sichtbareKpi} />,
            }
          : null)
      : {
          id: 'kpi', title: 'Kennzahlen', ...BLOCK_IDENTITAET.kennzahlen,
          summary: kennzahlenSummary,
          defaultOpen: true,
          render: () => <p className="text-sm text-gray-500 dark:text-gray-400">Keine Jahres-Kennzahlen verfügbar.</p>,
        }
    const finanzBlock = d ? finanzTeaserBlock(d, park, 'jahr') : null

    // ── CO₂-Bilanz (Nebenfunde-Paket B') ────────────────────────────────────────
    // Zwei Kennwerte + der gestapelte Monats-Chart. Jede Anzeige ist einzeln
    // parkbar (KpiStrip parkt je Kachel, der Chart über EINE Parkbar = EINE
    // atomare Anzeige); der Block entfällt erst, wenn ALLE drei geparkt sind —
    // dasselbe Auto-Hide-Muster wie der Bilanz-Block darüber.
    // Abgrenzung: das ist die ZEITBEZOGENE Sicht. Die CO₂-**Amortisation** je
    // Komponente (Lebensdauer-Frage „wann ist die graue Last eingespielt")
    // bleibt unter Auswertungen → CO₂; hier bewusst keine Dublette davon.
    const co2ParkIds = ['kpi:co2-jahr', 'kpi:co2-kumuliert', 'el:co2']
    const fcJahr = formatCo2(co2JahresSumme(co2Punkte))
    const fcKum = formatCo2(co2Kumuliert)
    const co2Kpis: KpiStripItem[] = [
      {
        title: 'CO₂ eingespart', value: fcJahr.wert, unit: fcJahr.einheit,
        color: 'green', icon: Leaf, parkId: 'kpi:co2-jahr',
        subtitle: `${jahr} · PV + Wärmepumpe + E-Mobilität`,
        formel: 'Σ der Monatswerte des gewählten Jahres',
        berechnung: `${co2Punkte.length} Monate mit Daten`, ergebnis: `= ${fcJahr.text}`,
        sicht: `Jahr ${jahr}`,
      },
      {
        title: 'CO₂ kumuliert', value: fcKum.wert, unit: fcKum.einheit,
        color: 'green', icon: Sprout, parkId: 'kpi:co2-kumuliert',
        subtitle: 'gesamte Historie — nicht jahresgebunden',
        formel: 'Σ aller erfassten Monate',
        berechnung: `${co2Monate.length} Monate mit Daten`, ergebnis: `= ${fcKum.text}`,
        sicht: 'Gesamte Historie',
      },
    ]
    const co2Block: Block | null = co2Fehler
      // B8: der Fehler des Zweit-Abrufs wird sichtbar statt still ausgelassen —
      // ein fehlender Block wäre von „diese Anlage hat keine CO₂-Daten" nicht zu
      // unterscheiden.
      ? {
          id: 'co2', title: 'CO₂-Bilanz', ...BLOCK_IDENTITAET.co2,
          summary: 'vermiedenes CO₂ je Monat', defaultOpen: false,
          render: () => <FehlerZustand text="Fehler beim Laden der CO₂-Bilanz" onRetry={co2Reload} />,
        }
      : co2Punkte.length === 0 || co2ParkIds.every((id) => park.istGeparkt(id))
        ? null
        : {
            id: 'co2', title: 'CO₂-Bilanz', ...BLOCK_IDENTITAET.co2,
            summary: `${fcJahr.text} eingespart · kumuliert ${fcKum.text}`,
            defaultOpen: false,
            render: () => (
              <div className="space-y-4">
                <KpiStrip kpis={co2Kpis} />
                <Parkbar id="el:co2" titel="CO₂-Verlauf">
                  <JahrCo2Chart daten={co2Punkte} />
                </Parkbar>
              </div>
            ),
            // Paket CT: dieselbe Datenreihe wie der Chart, Spalten = Union der Serien
            // (+ die Stapel-Höhe, die der Balken ohnehin zeigt).
            renderTabelle: () => (
              <ChartDatenTabelle
                xLabel="Monat"
                xKey="monat"
                spalten={CO2_TABELLEN_SPALTEN}
                daten={co2Punkte}
                csvDateiname={`co2_${jahr}.csv`}
              />
            ),
          }

    return [
      ...(kennzahlenBlock ? [kennzahlenBlock] : []),
      // Bilanz-Block: jede Teil-Anzeige einzeln parkbar (in JahrBilanz, gleiche IDs wie
      // Monat — gleicher Aggregat-Shape); Block entfällt erst, wenn ALLE geparkt sind.
      ...(d && monatBilanzParkIds(d).every((id) => park.istGeparkt(id)) ? [] : [{
        id: 'bilanz', title: 'Energie-Bilanz', ...BLOCK_IDENTITAET.energieBilanz,
        summary: bilanzSummary,
        defaultOpen: false,
        render: () => (d
          ? <JahrBilanz
              d={d} dVgl={jahrVglData ?? d}
              vj={vorjahr} oj={oeJahr} ojCount={oeJahr?.count ?? 0}
              vjFenster={vjFenster} ojFenster={ojFenster}
              istFenster={istFenster} kennzahlenFenster={kennzahlenFenster}
            />
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
      ...(co2Block ? [co2Block] : []),
      ...(d ? baueKomponentenBloecke(d, park, 'jahr') : []),
      ...(finanzBlock ? [finanzBlock] : []),
    ]
  }, [jahr, jahrData, jahrVglData, vorjahr, oeJahr, vjFenster, ojFenster, istFenster,
      kennzahlenFenster, monatsZeilen, park,
      co2Punkte, co2Monate.length, co2Kumuliert, co2Fehler, co2Reload])

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
