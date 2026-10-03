/**
 * CockpitMonatV4 — die echte Einzelmonats-Sicht (IA v4 E3 Slice 2b).
 *
 * Cockpit/Monat ist innen eine TAGES-Sicht des gewählten Monats: Hauptblock
 * {@link TagesverlaufChart} (Tagesverlauf ⇄ Monats-Fluss) + Werte-Embed in
 * Tagesgranularität (`WerteTabelle granularitaet="tag"`) als numerischer
 * Zwilling — beide gespeist aus EINER Quelle (`getTageWerte`, der Tages-Werte-
 * SoT aus Slice 2a). Der Vergleich im Embed ist der Vormonat („Vergleichsmonat",
 * B9), gematcht über den Tag-im-Monat.
 *
 * Monats-Selektor ist hier bewusst schlank (Dropdown); der volle Monats-Rail
 * (vertikal/horizontal, Mini-PV-Balken, „läuft"-Badge) folgt in Slice 2e.
 * KPI-Strip (2c), Komponenten-Sektionen (2d), Finanz-/Community-Teaser (2e)
 * docken später als weitere Blöcke an.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fmtCalc, FehlerZustand, ChartDatenTabelle } from '../components/ui'
import { AnlageLeer, DatenLeer } from './OnboardingLeer'
import { BlockShell, BlockStackSkeleton, KpiStrip, type Block } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar, usePark } from '../components/park'
import ZaehlerstaendeBlock, { useZaehlerstaende, zaehlerstaendeFuer, zaehlerParkIds } from '../components/zaehler/ZaehlerstaendeBlock'
import { useApiData, useScrollErhalt } from '../hooks'
import { MONAT_KURZ, BLOCK_IDENTITAET } from '../lib'
import { TagesverlaufChart, baueChartDaten } from './TagesverlaufChart'
import { baueMonatKpis, MonatBilanz, type GleicheMonatStats } from './MonatBilanz'
import { monatBilanzParkIds } from './bilanzParkIds'
import { MONAT_PARK_KEY } from './monatParkScope'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { punkteAusVerlaufsTagen, type WaermeVerlaufPunkt } from './waermeVerlauf'
import { baueMonatAuswertungBloecke } from './MonatAuswertungBloecke'
import { MonatsRail, type RailEintrag } from './MonatsRail'
import { MonatStepper } from './MonatStepper'
import { MonatHeader, finanzTeaserBlock } from './MonatRahmen'
import { energieProfilApi, type VerfuegbarerMonat } from '../api/energie_profil'
import { aktuellerMonatApi } from '../api/aktuellerMonat'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
import { monatRefAusQuery, verlaufTabellenSpalten } from './verlaufVergleich'
import { sollErfuellungProzent, sollFensterText } from '../lib/sollErfuellung'
import { offenerAbschlussMonat } from '../lib/monatsLuecken'

interface MonatRef { jahr: number; monat: number }

/** Zwei Monatsreferenzen, ein Monat? (Paarung, Style-Guide A3a) */
function gleicherMonat(a: MonatRef | null | undefined, b: MonatRef | null | undefined): boolean {
  return !!a && !!b && a.jahr === b.jahr && a.monat === b.monat
}

function vormonat({ jahr, monat }: MonatRef): MonatRef {
  return monat === 1 ? { jahr: jahr - 1, monat: 12 } : { jahr, monat: monat - 1 }
}

/** ISO-Spanne [erster, letzter] Tag eines Monats (UTC-stabil, kein TZ-Drift). */
function monatsSpanne({ jahr, monat }: MonatRef): { von: string; bis: string } {
  const mm = String(monat).padStart(2, '0')
  const letzter = new Date(Date.UTC(jahr, monat, 0)).getUTCDate()
  return { von: `${jahr}-${mm}-01`, bis: `${jahr}-${mm}-${String(letzter).padStart(2, '0')}` }
}

function monatLabel({ jahr, monat }: MonatRef): string {
  return `${MONAT_KURZ[monat]} ${jahr}`
}

/** Tages-Werte des Monats + Einzelmonats-KPIs in einem Zug — geteilt von
 *  Initial-Load und Reload (C1), damit es keinen zweiten Fetch-Pfad gibt. */
async function ladeMonatsdaten(anlageId: number, ref: MonatRef) {
  const akt = monatsSpanne(ref)
  const [tage, monatData] = await Promise.all([
    energieProfilApi.getTageWerte(anlageId, akt.von, akt.bis),
    aktuellerMonatApi.getData(anlageId, ref.jahr, ref.monat).catch(() => null),
  ])
  // `ref` gehört zur Nutzlast: Sie sagt selbst, zu welchem Monat sie gehört —
  // beim Monatswechsel steht die Auswahl schon auf dem neuen, während hier noch
  // die Vordaten des alten liegen (`keepPreviousData`).
  return { ref, tage, monatData }
}

// persistKey-SoT der Sicht — geteilt von BlockShell (Block-Ebene) und ParkProvider
// (Element-Ebene); eigene LS-Prefixe (`eedc-bloecke:` vs. `eedc-park:`).
// Seit dem Monatsbericht (#395 Punkt 4) hat der Park-Scope einen zweiten Leser
// außerhalb dieses Baums (`components/DokumentationsDialog`) — deshalb steht die
// Zeichenkette in `v4/monatParkScope.ts` und nicht mehr hier.
const SICHT_KEY = MONAT_PARK_KEY

/** Neueste Monatsreferenz zuerst. */
function neuesteZuerst<T extends MonatRef>(xs: T[]): T[] {
  return [...xs].sort((a, b) => (a.jahr !== b.jahr ? b.jahr - a.jahr : b.monat - a.monat))
}

/**
 * Gibt es Vergangenheits-Monate ohne Abschluss?
 *
 * Rein und exportiert, weil zwei Stellen sie brauchen — der „Abschluss
 * starten"-Link und seit N-99 die Default-Vorauswahl. `heute` wird
 * hereingereicht statt gelesen: eine Probe, die die echte Uhr nimmt, ist nicht
 * hermetisch (N-167).
 *
 * ⚠ Die Ableitung kommt aus dem SoT `lib/monatsLuecken` — **nicht** aus einer
 * eigenen Regel. Bis 06.08. stand hier „ist der jüngste Monat mit Daten älter
 * als der Vormonat?", also genau das naive „letzter Monat + 1", das der SoT
 * ausdrücklich ablöst: eine **Binnen-Lücke** (Januar fehlt, Februar–Juli
 * gepflegt) galt damit als „nichts offen", während die Status-Fußzeile
 * daneben „nächster offener: Jan" meldete. Solange nur der Knopf daran hing,
 * blieb das unauffällig; mit N-99 hängt die Vorauswahl daran.
 *
 * Als Bereichs-Start dient der **früheste vorhandene Monat** — der dritte
 * Fallback von `ermittleStartAnker`. Lücken *vor* der ersten Datenzeile
 * bleiben damit unerkannt; dafür bräuchte es das Anschaffungsdatum der
 * Investitionen und einen zusätzlichen Fetch beim Öffnen der Sicht.
 */
export function hatOffeneAbschluesse(mitMonatsdaten: MonatRef[], heute: Date): boolean {
  if (mitMonatsdaten.length === 0) return true
  // Seit N-368 liegt die Ableitung im SoT `lib/monatsLuecken`, weil eine ZWEITE
  // Sicht dieselbe Frage stellt (Auswertungen → Tabelle, Hinweis über den
  // Tageswerten). Das Verhalten ist unveraendert — nur der Ort ist jetzt einer.
  return offenerAbschlussMonat(mitMonatsdaten, heute) !== null
}

/**
 * Default-Vorauswahl der Monats-Sicht (N-99, Meldung coolxmad #353).
 *
 * Zwei Lagen, weil die Sicht zwei Aufgaben hat:
 * - **Abschlüsse offen** → neuester Monat MIT Monatsdaten. Er ist der Anfang
 *   des Weges zum offenen Abschluss; auf den laufenden Monat zu springen
 *   würde daran vorbeiführen.
 * - **Keine offenen Abschlüsse** → neuester Monat, für den es überhaupt Werte
 *   gibt (`voll` = inkl. Monate ohne Abschluss und ohne Zählerzeile). Das ist
 *   in aller Regel der laufende — und damit dieselbe Doktrin, der
 *   Cockpit → Tag („neuester Tag mit Daten") und Cockpit → Jahr schon folgen.
 *
 * Die Auflage stammt von Gernot (03.08.); die volle Liste lag seit F-1
 * (`ce3d316a`) bereits in der Komponente, die Vorauswahl las sie nur nicht.
 *
 * Monate **nach** dem laufenden werden nie vorgewählt: die volle Liste kennt
 * auch Monate, deren einzige Spur eine Tagesebene-Zeile ist — eine
 * Snapshot-Streuzeile in der Zukunft würde sonst eine leere Sicht öffnen.
 */
export function waehleDefaultMonat(
  mitMonatsdaten: MonatRef[],
  verfuegbar: MonatRef[],
  voll: MonatRef[],
  heute: Date,
): MonatRef | null {
  const streng = neuesteZuerst(mitMonatsdaten)[0] ?? neuesteZuerst(verfuegbar)[0] ?? null
  if (hatOffeneAbschluesse(mitMonatsdaten, heute)) return alsMonatRef(streng)
  const hj = heute.getFullYear()
  const hm = heute.getMonth() + 1
  const bisHeute = voll.filter((m) => m.jahr < hj || (m.jahr === hj && m.monat <= hm))
  const neuester = neuesteZuerst(bisHeute)[0] ?? null
  return alsMonatRef(neuester ?? streng)
}

function alsMonatRef(m: MonatRef | null): MonatRef | null {
  return m ? { jahr: m.jahr, monat: m.monat } : null
}

/**
 * „Ø gleicher Monat" (andere Jahre) für die Vergleichsspalte von Cockpit → Monat (N-604, 03.10.2026).
 *
 * Als reine Funktion herausgezogen, damit die Regel eine Probe hat (`CockpitMonatV4.glMonStats.test.ts`): eine gemessene
 * 0 zählt mit, die Ø-Autarkie ist eine Quote über die Jahre, die BEIDE Größen tragen.
 */
export function gleicheMonatStats(
  alleMonate: readonly AggregierteMonatsdaten[],
  angezeigterMonat: { jahr: number; monat: number } | null | undefined,
): GleicheMonatStats | null {
  if (!angezeigterMonat) return null
  const ms = alleMonate.filter((m) => m.monat === angezeigterMonat.monat && m.jahr !== angezeigterMonat.jahr)
  if (ms.length === 0) return null
  const avg = (vals: number[]) => (vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : null)
  // N-604 (03.10.2026): eine gemessene 0 ist ein Wert — bis dahin warf `v > 0` eine 0-kWh-Einspeisung (Schnee,
  // Volleinspeiser ohne Bezug) aus dem Mittel (CLAUDE.md „0-Werte prüfen").
  const pick = (f: (m: AggregierteMonatsdaten) => number | null | undefined) =>
    avg(ms.map(f).filter((v): v is number => v != null))
  // Die Ø-Autarkie ist eine Quote aus Summen über die Jahre, die BEIDE Größen tragen (R-Q, dieselbe Regel wie
  // das Jahr im Backend) — nicht das Mittel der Monats-Prozente. ⚠ Klassifizierte Ausnahme von
  // `check:ergebnis-roh`, bis die Monatsreihe eine Backend-Vergleichsroute hat (Register N-604).
  const paar = ms.filter((m) => m.eigenverbrauch_kwh != null && m.gesamtverbrauch_kwh != null)
  const evPaar = paar.reduce((s, m) => s + (m.eigenverbrauch_kwh ?? 0), 0)
  const gvPaar = paar.reduce((s, m) => s + (m.gesamtverbrauch_kwh ?? 0), 0)
  return {
    pv: pick((m) => m.pv_erzeugung_kwh),
    ev: pick((m) => m.eigenverbrauch_kwh),
    direkt: pick((m) => m.direktverbrauch_kwh),
    einsp: pick((m) => m.einspeisung_kwh),
    netz: pick((m) => m.netzbezug_kwh),
    gesamt: pick((m) => m.gesamtverbrauch_kwh),
    autarkie: gvPaar > 0 ? (evPaar / gvPaar) * 100 : null,
    count: ms.length,
  }
}

export default function CockpitMonatV4(props: { anlageId: number | undefined }) {
  // ParkProvider muss den Body umschließen, damit `usePark` (Kennzahlen-Filter,
  // ParkFuss) im selben Baum greift. SLICE 1 — Referenz-Sicht.
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <CockpitMonatInner {...props} />
    </ParkProvider>
  )
}

function CockpitMonatInner({ anlageId }: { anlageId: number | undefined }) {
  const park = usePark()
  // B3-Drill-in: Verlauf-Balken der Jahr-Sicht landet mit `?jahr=&monat=` hier. Beim
  // Erst-Load dem Default (neuester Monat mit Daten) vorziehen; nur am Mount gelesen (Ref).
  const [searchParams] = useSearchParams()
  const initialGewaehltRef = useRef<MonatRef | null>(monatRefAusQuery(searchParams))
  const [gewaehlt, setGewaehlt] = useState<MonatRef | null>(initialGewaehltRef.current)

  // Verfügbare Monate + Monatsreihe (für Vormonat/Ø-Monat) laden → Default vorwählen.
  // Beide Quellen parallel, damit die Default-Wahl die Monatsdaten kennt.
  // R18-2 (SWR): über den Sicht-Cache von useApiData — beim Tab-Wechsel stehen die
  // alten Daten sofort (kein Skeleton), still revalidiert.
  //
  // DREI Quellen, und die dritte ist der Grund für dieses Paket (Melder
  // kaba-kakao, Forum T89667/98): die **Rail** hing allein an
  // `getVerfuegbareMonate` — das ist ein `GROUP BY` über `TagesZusammenfassung`,
  // also die reine **Tagesebene**. Wer eedc über Monatsabschlüsse oder Import
  // pflegt (der Standalone-Kernfall), hat dort nichts stehen; die Rail zeigte
  // dann als einzigen Eintrag den laufenden Monat, den der Client unten
  // bedingungslos nachschiebt — während die Sicht daneben einen Monat mit
  // vollen Werten darstellte, der in seiner eigenen Auswahlliste fehlte.
  // Cockpit → Jahr wurde von genau dieser Klasse mit N-68 + N-121 geheilt und
  // zieht seither `listAggregiert` mit beiden Flags; die Monats-Rail ist bei
  // der alten Quelle geblieben.
  //
  // Die **volle** Liste steht bewusst NEBEN der strengen, statt sie zu
  // ersetzen: die beiden beantworten verschiedene Fragen (Datensatz-Liste vs.
  // Zeitreihe, siehe Route-Docstring), und `inkl_nur_tageswerte` füllt in der
  // Schicht auch **Lücken bestehender** Monate (PV/BKW aus der Tagesebene).
  // Die strenge Liste hier zu ersetzen würde daher Vormonats- und Ø-Vergleiche
  // bewegen — eine Zahlenänderung, die dieses Paket nicht beauftragt hat.
  const monateQ = useApiData(
    () => Promise.all([
      monatsdatenApi.listAggregiert(anlageId!),
      energieProfilApi.getVerfuegbareMonate(anlageId!),
      monatsdatenApi.listAggregiert(anlageId!, undefined, {
        inklOhneZaehlerzeile: true,
        inklNurTageswerte: true,
      }),
    ]),
    [anlageId],
    { enabled: !!anlageId, swrKey: `v4-monat-liste:${anlageId}` },
  )
  const alleMonate = useMemo<AggregierteMonatsdaten[]>(() => monateQ.data?.[0] ?? [], [monateQ.data])
  const monate = useMemo<VerfuegbarerMonat[]>(() => monateQ.data?.[1] ?? [], [monateQ.data])
  /** Obermenge für die Rail: inkl. Monate ohne Abschluss und ohne DB-Spur. */
  const alleMonateVoll = useMemo<AggregierteMonatsdaten[]>(() => monateQ.data?.[2] ?? [], [monateQ.data])

  // Default vorwählen, sobald die Listen da sind.
  useEffect(() => {
    if (!monateQ.data) return
    // B3: Drill-in-`?jahr=&monat=` hat schon vorgewählt → Default nicht überschreiben
    // (Ref ist mount-stabil, keine exhaustive-deps-Pflicht).
    const [agg, ms, voll] = monateQ.data
    setGewaehlt((aktuell) => aktuell ?? waehleDefaultMonat(agg, ms, voll, new Date()))
  }, [monateQ.data])

  // Tages-Werte (Monat + Vormonat) + Einzelmonats-KPIs (IST/Vorjahr/SOLL) laden.
  // keepPreviousData: Monatswechsel aktualisiert den Block-Stack in-place statt
  // Skeleton (detLAN D7-2) — auch ohne Cache-Stand für den Ziel-Monat.
  const tageQ = useApiData(
    () => ladeMonatsdaten(anlageId!, gewaehlt!),
    [anlageId, gewaehlt?.jahr, gewaehlt?.monat],
    {
      enabled: !!anlageId && !!gewaehlt,
      swrKey: `v4-monat:${anlageId}:${gewaehlt?.jahr}-${gewaehlt?.monat}`,
      keepPreviousData: true,
    },
  )
  const tage = useMemo(() => tageQ.data?.tage ?? [], [tageQ.data])
  const monatData = tageQ.data?.monatData ?? null
  // ── Die Sicht zeigt EINE Periode ────────────────────────────────────────────
  // `gewaehlt` ist die **Auswahl** (Rail/Stepper, wirkt sofort), `angezeigterMonat`
  // der Monat, zu dem die **Zahlen im Bild** gehören. Alles, was diese Zahlen
  // beschriftet oder ergänzt, hängt am angezeigten Monat; die Auswahl steht im
  // Kopf als Lade-Marker daneben (Style-Guide A3a, gebaut zuerst in Cockpit → Tag).
  const angezeigterMonat: MonatRef | null = tageQ.data?.ref ?? gewaehlt
  const laedtMonat = gewaehlt && !gleicherMonat(angezeigterMonat, gewaehlt) ? gewaehlt : null

  // Monats-Auswertung (getMonat) — fertig berechnete Analyse-Werte für die vor dem
  // Flip wiederhergestellten Energieprofil-Blöcke (Peaks/Tagesprofil/Kategorien/§51 +
  // PR Ø). EIGENER Fetch/swrKey, an `gewaehlt` gebunden (kein Doppel-Fetch); getMonat
  // respektiert das Installationsdatum backend-seitig. Fehlt die Antwort (Fehler/
  // laden), bleiben die Blöcke einfach aus — sie sind additiv zur Monatsbilanz.
  const auswQ = useApiData(
    async () => ({ ref: gewaehlt!, ausw: await energieProfilApi.getMonat(anlageId!, gewaehlt!.jahr, gewaehlt!.monat) }),
    [anlageId, gewaehlt?.jahr, gewaehlt?.monat],
    {
      enabled: !!anlageId && !!gewaehlt,
      swrKey: `v4-monat-auswertung:${anlageId}:${gewaehlt?.jahr}-${gewaehlt?.monat}`,
      keepPreviousData: true,
    },
  )
  // Paarung: die Auswertungs-Blöcke und die PR-Ø-Kachel gehören zu DIESEN Kacheln
  // oder sie erscheinen nicht — sonst stünde die Analyse des einen Monats über den
  // Mengen eines anderen, je nachdem welche der beiden Abfragen zuerst antwortet.
  const monatAusw = gleicherMonat(auswQ.data?.ref, angezeigterMonat) ? auswQ.data!.ausw : null

  // ── Wärme/Klima-Verlauf (Konzept §8, Bauschnitt 4): x = Tage des Monats ──
  //
  // ⚠ **Eigener Abruf, und das ist die Entscheidung.** Die Tageszeilen von
  // `getTageWerte` liegen oben schon geladen — sie tragen die Größen aber
  // nicht: `wp_strom` ist dort die Σ der Stundenleistungen (Leistungspfad),
  // während Kachel und Aufteilung mit dem Zählerpfad rechnen. Zwei Zahlen für
  // dieselbe Größe in EINEM Bild wären W-17b ein zweites Mal (dietmar1968 sah
  // 30 kWh Balken unter einer 284-kWh-Kachel). Betriebsart-Aufteilung und
  // gemessene Wärme je Tag fehlen dort ohnehin.
  //
  // Er lädt **neben** der Sicht: Bleibt er aus, fehlt der Verlauf-Block und
  // sonst nichts — wie die Auswertungs-Blöcke darunter.
  const verlaufQ = useApiData(
    async () => {
      const spanne = monatsSpanne(gewaehlt!)
      return { ref: gewaehlt!, tage: await energieProfilApi.getWaermeVerlauf(anlageId!, spanne.von, spanne.bis) }
    },
    [anlageId, gewaehlt?.jahr, gewaehlt?.monat],
    {
      enabled: !!anlageId && !!gewaehlt,
      swrKey: `v4-monat-waermeverlauf:${anlageId}:${gewaehlt?.jahr}-${gewaehlt?.monat}`,
      keepPreviousData: true,
    },
  )
  // Die Punkte baut eine reine Funktion (`waermeVerlauf.ts`) — dort ist eine
  // vergessene Durchreichung prüfbar, hier im `useMemo` war sie unsichtbar.
  // WK-16c: Verteilung & Verlauf — **dieselbe Bauform wie der Verlauf darüber**,
  // inklusive Paarung über `ref` (A3a: eine Sicht zeigt EINE Periode).
  const verteilungQ = useApiData(
    async () => ({
      ref: gewaehlt!,
      v: await energieProfilApi.getWaermeVerteilung(anlageId!, {
        sicht: 'monat', jahr: gewaehlt!.jahr, monat: gewaehlt!.monat,
      }),
    }),
    [anlageId, gewaehlt?.jahr, gewaehlt?.monat],
    {
      enabled: !!anlageId && !!gewaehlt,
      swrKey: `v4-monat-waermeverteilung:${anlageId}:${gewaehlt?.jahr}-${gewaehlt?.monat}`, /* de-de-allow: Cache-Key, keine Anzeige */
      keepPreviousData: true,
    },
  )
  const wpVerteilung = gleicherMonat(verteilungQ.data?.ref, angezeigterMonat)
    ? verteilungQ.data!.v : null
  const wpVerlaufTage = gleicherMonat(verlaufQ.data?.ref, angezeigterMonat) ? verlaufQ.data!.tage : null
  const wpVerlauf = useMemo<WaermeVerlaufPunkt[]>(
    () => punkteAusVerlaufsTagen(wpVerlaufTage ?? []),
    [wpVerlaufTage],
  )
  const loading = monateQ.loading || (!!gewaehlt && tageQ.loading)
  const reloading = tageQ.reloading
  const error = monateQ.data == null && monateQ.error
    ? 'Fehler beim Laden der Monate'
    : tageQ.data == null && tageQ.error ? 'Fehler beim Laden der Tageswerte' : null
  // C1: Aktualisieren (nur laufender Monat) — refetcht dieselben Quellen wie der
  // Initial-Load, ohne den Voll-Spinner (refetch ist bei Cache-Stand still).
  const reload = tageQ.refetch

  // B1: Scroll-Position beim Monatswechsel halten (Container vom Wurzel-Element
  // aus gefunden — mobil `main`, Desktop ViewShell). `merkeScroll` vor jedem
  // setGewaehlt; Wiederherstellung nach dem Reload (Signal = loading-Flip; mit
  // SWR-In-Place-Update flippt loading beim Monatswechsel nicht mehr → der
  // Scroll bleibt ohnehin natürlich stehen, der Hook greift nur im Skeleton-Fall).
  const rootRef = useRef<HTMLDivElement>(null)
  const merkeScroll = useScrollErhalt(rootRef, loading)
  const waehle = useCallback((j: number, m: number) => { merkeScroll(); setGewaehlt({ jahr: j, monat: m }) }, [merkeScroll])

  // C2: „Abschluss starten" nur wenn Vergangenheits-Monate noch offen sind —
  // dieselbe reine Funktion, die auch die Vorauswahl steuert (N-99).
  const offeneAbschluesse = useMemo(() => hatOffeneAbschluesse(alleMonate, new Date()), [alleMonate])

  // Vormonat-Aggregat + Ø gleicher Monat (andere Jahre) aus der Monatsreihe.
  const vormonatAgg = useMemo<AggregierteMonatsdaten | null>(() => {
    if (!angezeigterMonat) return null
    const vm = vormonat(angezeigterMonat)
    return alleMonate.find((m) => m.jahr === vm.jahr && m.monat === vm.monat) ?? null
  }, [alleMonate, angezeigterMonat])

  const glMonStats = useMemo(() => gleicheMonatStats(alleMonate, angezeigterMonat), [alleMonate, angezeigterMonat])

  // Rail-Einträge = **Vereinigung** beider Grundgesamtheiten + laufender Monat:
  // die Monats-Fakten (Abschlüsse, Import, Komponenten-Zeilen) UND die lokale
  // Tagesebene. Keine der beiden allein reicht — die Tagesebene kennt keinen
  // importierten Monat, die Monats-Fakten keinen Monat, der ausschließlich aus
  // Tageswerten besteht (dafür brauchte Cockpit → Jahr seinerzeit N-121).
  const railEntries = useMemo<RailEintrag[]>(() => {
    const heute = new Date()
    const hj = heute.getFullYear()
    const hm = heute.getMonth() + 1
    const key = (jahr: number, monat: number) => `${jahr}-${monat}`
    const pvJeMonat = new Map<string, number>()
    const schluessel = new Map<string, { jahr: number; monat: number }>()
    const merke = (jahr: number, monat: number) => {
      const k = key(jahr, monat)
      if (!schluessel.has(k)) schluessel.set(k, { jahr, monat })
    }
    alleMonateVoll.forEach((m) => {
      pvJeMonat.set(key(m.jahr, m.monat), m.pv_erzeugung_kwh ?? 0)
      merke(m.jahr, m.monat)
    })
    monate.forEach((m) => merke(m.jahr, m.monat))
    const entries: RailEintrag[] = [...schluessel.values()].map(({ jahr: j, monat: m }) => ({
      jahr: j, monat: m,
      pv_kwh: pvJeMonat.get(key(j, m)) ?? 0,
      laufend: j === hj && m === hm,
    }))
    if (!entries.some((e) => e.jahr === hj && e.monat === hm)) {
      entries.push({ jahr: hj, monat: hm, pv_kwh: 0, laufend: true })
    }
    return entries
  }, [monate, alleMonateVoll])

  // „läuft/abgeschlossen" beschreibt die Zahlen im Bild, nicht die Auswahl.
  const istLaufend = useMemo(() => {
    if (!angezeigterMonat) return false
    const heute = new Date()
    return angezeigterMonat.jahr === heute.getFullYear() && angezeigterMonat.monat === heute.getMonth() + 1
  }, [angezeigterMonat])

  // #377 — Verbrauchszähler dieses Monats. Geholt wird für die **Auswahl** (der
  // Abruf soll nicht auf die Kacheln warten), gezeigt wird nur, was zum
  // **angezeigten** Monat gehört: sonst stünden die Stände des einen Monats unter
  // den Mengen eines anderen (Style-Guide A3a).
  const zaehlerQ = useZaehlerstaende(anlageId, 'monat', {
    jahr: gewaehlt?.jahr, monat: gewaehlt?.monat,
  })
  const zaehlerstaende = zaehlerstaendeFuer(zaehlerQ, {
    zeitraum: 'monat', jahr: angezeigterMonat?.jahr, monat: angezeigterMonat?.monat,
  })

  const bloecke: Block[] = useMemo(() => {
    if (!angezeigterMonat) return []
    // Energie-Bilanz Block-Summary = Kernwerte auf einen Blick (wie IST), nicht
    // die Struktur-Beschreibung — im eingeklappten Zustand direkt ablesbar (A1).
    // Die Kopfzeile rendert ungekürzt — sie ist deshalb der Ort für die
    // Fensterangabe des SOLL (N-69; die Kachel-Zweitzeile darunter ist
    // `truncate`). Im laufenden Monat steht dort „SOLL 148 % (anteilig · 4 von
    // 31 Tagen)", im abgeschlossenen wie bisher nur die Prozentzahl.
    const monatSollPct = monatData ? sollErfuellungProzent(monatData) : null
    const monatSollFenster = monatData ? sollFensterText(monatData) : null
    const bilanzSummary = monatData
      ? `${fmtCalc(monatData.pv_erzeugung_kwh, 0, '—')} kWh PV · ${fmtCalc(monatData.autarkie_prozent, 0, '—')} % Autarkie${
          monatSollPct != null
            ? ` · SOLL ${fmtCalc(monatSollPct, 0, '—')} %${monatSollFenster ? ` (${monatSollFenster})` : ''}`
            : ''}`
      : 'IST / Vormonat / Vorjahr / Ø-Monat'
    // Kennzahlen-Kacheln parkbar machen (SLICE 1): stabile parkId je Titel; geparkte
    // werden im Strip ausgeblendet. Sind ALLE geparkt → Block-Hülle ausblenden
    // (Gernot-Abnahme 2026-06-25, Entscheidung 2).
    const kpiItems = monatData
      ? baueMonatKpis(monatData, vormonatAgg, monatAusw?.performance_ratio_avg, monatAusw?.performance_ratio_tage).map((k) => ({
          ...k,
          parkId: `kpi:${k.title.toLowerCase().replace(/[^a-z0-9]+/gi, '-')}`,
        }))
      : []
    const sichtbareKpi = kpiItems.filter((k) => !park.istGeparkt(k.parkId))
    const kennzahlenBlock: Block | null = monatData
      ? (sichtbareKpi.length > 0
          ? {
              id: 'kpi',
              title: 'Kennzahlen',
              ...BLOCK_IDENTITAET.kennzahlen,
              summary: '5 Energie-Kennzahlen + Netto-Ertrag + Monatsergebnis + Netz-Kosten',
              defaultOpen: true,
              render: () => <KpiStrip kpis={sichtbareKpi} />,
            }
          : null)
      : {
          id: 'kpi',
          title: 'Kennzahlen',
          ...BLOCK_IDENTITAET.kennzahlen,
          summary: '5 Energie-Kennzahlen + Netto-Ertrag + Monatsergebnis + Netz-Kosten',
          defaultOpen: true,
          render: () => <p className="text-sm text-gray-500 dark:text-gray-400">Keine Monats-Kennzahlen verfügbar.</p>,
        }
    // Default-Klappregel (Gernot 2026-06-19, revidiert): NUR der erste Block
    // (Kennzahlen) offen — alle übrigen eingeklappt, ihre Summary trägt den Kern.
    // Finanz-Teaser kann komplett geparkt sein → null (kein Block).
    const finanzBlock = monatData ? finanzTeaserBlock(monatData, park) : null
    return [
      ...(kennzahlenBlock ? [kennzahlenBlock] : []),
      // Bilanz-/Verlauf-Blöcke: ihr eines Element ist parkbar; ist es geparkt,
      // entfällt der ganze Block (Element-Park-Doktrin, Gernot 2026-06-27).
      // Bilanz-Block: jede Teil-Anzeige (Vergleich/Grundlast/Verteilung/Geräte) ist
      // einzeln parkbar (in MonatBilanz); der Block entfällt erst, wenn ALLE geparkt
      // sind (Speicher-Muster `alleGeparkt`).
      ...(monatData && monatBilanzParkIds(monatData).every((id) => park.istGeparkt(id)) ? [] : [{
        id: 'bilanz',
        title: 'Energie-Bilanz',
        ...BLOCK_IDENTITAET.energieBilanz,
        summary: bilanzSummary,
        defaultOpen: false,
        render: () => (monatData
          ? <MonatBilanz d={monatData} vm={vormonatAgg} glMonStats={glMonStats} monatName={MONAT_KURZ[angezeigterMonat.monat]} />
          : <p className="text-sm text-gray-500 dark:text-gray-400">Keine Vergleichsdaten verfügbar.</p>),
      }]),
      ...(park.istGeparkt('el:verlauf') ? [] : [{
        id: 'tagesverlauf',
        title: 'Verlauf',
        ...BLOCK_IDENTITAET.verlauf,
        summary: 'Tages-Bilanz: Erzeugung / Verbrauch / Autarkie',
        defaultOpen: false,
        render: () => <Parkbar id="el:verlauf" titel="Verlauf"><TagesverlaufChart tage={tage} /></Parkbar>,
        // Paket CT (Pilot): Tabellen-Ablesung im Fokus-Overlay — dieselbe Datenreihe
        // wie der Chart (baueChartDaten), Spalten = Union der Chart-Serien.
        renderTabelle: () => (
          <ChartDatenTabelle
            xLabel="Tag"
            xKey="tag"
            spalten={verlaufTabellenSpalten(false)}
            daten={baueChartDaten(tage)}
            zeilen={31}
            csvDateiname={`verlauf_${angezeigterMonat.jahr}-${String(angezeigterMonat.monat).padStart(2, '0')}.csv`} /* de-de-allow: Dateiname (ISO sortierbar) */
          />
        ),
      }]),
      // Wiederhergestellte Energieprofil-Analysen (M4/M8/M9/M3, ante-flip) — fertig
      // aus getMonat berechnet; jeder Block versteckt sich selbst bei leerer Daten-
      // /Park-Lage (Element-Park-Doktrin).
      ...(monatAusw ? baueMonatAuswertungBloecke(monatAusw, park, monatData?.nicht_vergueteter_erloes_euro) : []),
      // Komponenten-Detailblöcke (aktiv-gegatet, B6/B7).
      ...(monatData ? baueKomponentenBloecke(monatData, park, 'monat', null, wpVerlauf, null, wpVerteilung) : []),
      // Finanz-Teaser (B5) — bewusst GANZ UNTEN: Netto-Ertrag/Monatsergebnis stehen
      // bereits in den Kennzahlen (D), hier nur Aufschlüsselung + Tarif + Cross-Link.
      // #377 — Verbrauchszähler: nur wenn wirklich einer gepflegt ist.
      ...(zaehlerstaende && zaehlerstaende.length > 0 && !zaehlerParkIds(zaehlerstaende).every((id) => park.istGeparkt(id)) ? [{
        id: 'zaehlerstaende', title: 'Zählerstände', ...BLOCK_IDENTITAET.zaehlerstaende,
        summary: 'erfasst, nicht bewertet',
        defaultOpen: false,
        render: () => (
          <ZaehlerstaendeBlock staende={zaehlerstaende} zeitraum="monat" />
        ),
      }] : []),
      ...(finanzBlock ? [finanzBlock] : []),
    ]
  }, [angezeigterMonat, tage, monatData, monatAusw, vormonatAgg, glMonStats, park, zaehlerstaende, wpVerlauf, wpVerteilung])

  if (!anlageId) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <AnlageLeer titel="Noch keine Anlage gewählt." />
      </div>
    )
  }

  return (
    <div ref={rootRef} className="p-3 sm:p-6 max-w-[1920px] mx-auto">
      {/* Mobil: schwebender Player-Stepper. Bewusst direktes Kind der voll-hohen
          Wurzel (NICHT in der kurzen Rail-Spalte) — sonst klebt `sticky` nur
          innerhalb seines kurzen Eltern-Containers und verschwindet beim Scrollen. */}
      <MonatStepper
        entries={railEntries}
        jahr={gewaehlt?.jahr ?? 0}
        monat={gewaehlt?.monat ?? 0}
        onSelect={waehle}
      />

      <div className="lg:flex lg:gap-6">
        {/* Desktop: Rail-Sidebar (links) */}
        <div className="hidden lg:block lg:w-52 lg:shrink-0">
          <MonatsRail
            entries={railEntries}
            jahr={gewaehlt?.jahr ?? 0}
            monat={gewaehlt?.monat ?? 0}
            onSelect={waehle}
          />
        </div>

        <div className="flex-1 min-w-0 space-y-4">
          <MonatHeader
            titel={angezeigterMonat ? monatLabel(angezeigterMonat) : '…'}
            laedtTitel={laedtMonat ? monatLabel(laedtMonat) : null}
            laufend={istLaufend}
            d={monatData}
            onReload={reload}
            reloading={reloading}
            zeigeAbschlussLink={offeneAbschluesse}
          />

          {error ? (
            // B8-Fehler-Baustein (S15). Retry nur wenn reload greifen kann (Monat gewählt);
            // beim Listen-Fetch-Fehler (gewaehlt==null) wäre reload no-op → kein Fassade-Knopf.
            <FehlerZustand text={error} onRetry={gewaehlt ? reload : undefined} />
          ) : loading && !monatData ? (
            // Skeleton NUR beim Erst-Load (noch keine Daten). Beim Monatswechsel
            // bleibt der bestehende Block-Stack stehen und aktualisiert sich in-place
            // → kein „Aufblitzen" (detLAN D7-2, 2026-06-27; analog Tag T2). Kein
            // `key={…}` mehr → BlockShell re-rendert statt zu remounten.
            <BlockStackSkeleton label="Lade Monat…" />
          ) : monate.length === 0 ? (
            <DatenLeer titel="Noch keine Monatsdaten erfasst." />
          ) : (
            <BlockShell
              persistKey={SICHT_KEY}
              bloecke={bloecke}
              sortierbar
              /* D10-2: im Vollbild läuft die Monats-Nav oben mit (auf jeder Breite). */
              fokusKopf={
                <MonatStepper
                  entries={railEntries}
                  jahr={gewaehlt?.jahr ?? 0}
                  monat={gewaehlt?.monat ?? 0}
                  onSelect={waehle}
                  immerSichtbar
                />
              }
            />
          )}

          {/* Element-Park-Fuß (SLICE 1): Hinweiszeile + „Geparkt (n)". Inert leer,
              bis etwas geparkt ist; rendert nichts ohne ParkProvider. */}
          <ParkFuss bereit={!(loading && !monatData)} />
        </div>
      </div>
    </div>
  )
}
