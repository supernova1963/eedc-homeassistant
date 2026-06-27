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
import { LoadingSpinner, Card, fmtCalc } from '../components/ui'
import { BlockShell, KpiStrip, type Block } from '../components/blocks'
import { ParkProvider, ParkFuss, usePark } from '../components/park'
import { useScrollErhalt } from '../hooks'
import { MONAT_KURZ, BLOCK_IDENTITAET } from '../lib'
import { TagesverlaufChart } from './TagesverlaufChart'
import { baueMonatKpis, MonatBilanz, type GleicheMonatStats } from './MonatBilanz'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { MonatsRail, type RailEintrag } from './MonatsRail'
import { MonatStepper } from './MonatStepper'
import { MonatHeader, finanzTeaserBlock } from './MonatRahmen'
import { energieProfilApi, type TagWerte, type VerfuegbarerMonat } from '../api/energie_profil'
import { aktuellerMonatApi, type AktuellerMonatResponse } from '../api/aktuellerMonat'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'

interface MonatRef { jahr: number; monat: number }

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
function ladeMonatsdaten(anlageId: number, ref: MonatRef) {
  const akt = monatsSpanne(ref)
  return Promise.all([
    energieProfilApi.getTageWerte(anlageId, akt.von, akt.bis),
    aktuellerMonatApi.getData(anlageId, ref.jahr, ref.monat).catch(() => null),
  ])
}

// persistKey-SoT der Sicht — geteilt von BlockShell (Block-Ebene) und ParkProvider
// (Element-Ebene); eigene LS-Prefixe (`eedc-bloecke:` vs. `eedc-park:`).
const SICHT_KEY = 'v4-cockpit-monat'

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
  const [monate, setMonate] = useState<VerfuegbarerMonat[]>([])
  const [gewaehlt, setGewaehlt] = useState<MonatRef | null>(null)
  const [tage, setTage] = useState<TagWerte[]>([])
  const [monatData, setMonatData] = useState<AktuellerMonatResponse | null>(null)
  const [alleMonate, setAlleMonate] = useState<AggregierteMonatsdaten[]>([])
  const [loading, setLoading] = useState(true)
  const [reloading, setReloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // B1: Scroll-Position beim Monatswechsel halten (Container vom Wurzel-Element
  // aus gefunden — mobil `main`, Desktop ViewShell). `merkeScroll` vor jedem
  // setGewaehlt; Wiederherstellung nach dem Reload (Signal = loading-Flip).
  const rootRef = useRef<HTMLDivElement>(null)
  const merkeScroll = useScrollErhalt(rootRef, loading)
  const waehle = useCallback((j: number, m: number) => { merkeScroll(); setGewaehlt({ jahr: j, monat: m }) }, [merkeScroll])

  // Verfügbare Monate + Monatsreihe (für Vormonat/Ø-Monat) laden → Default vorwählen.
  // Beide Quellen parallel, damit die Default-Wahl die Monatsdaten kennt.
  useEffect(() => {
    if (!anlageId) return
    let ab = false
    Promise.all([
      monatsdatenApi.listAggregiert(anlageId),
      energieProfilApi.getVerfuegbareMonate(anlageId),
    ])
      .then(([agg, ms]) => {
        if (ab) return
        setAlleMonate(agg)
        setMonate(ms)
        // Default = neuester Monat MIT Monatsdaten — NICHT bloß die neueste TEP/TZ-
        // Zeile: ein laufender Monat ohne Abschluss (oder eine Snapshot-Streuzeile)
        // würde sonst leer vorgewählt. Fallback: neuester verfügbarer Monat.
        const desc = <T extends { jahr: number; monat: number }>(xs: T[]) =>
          [...xs].sort((a, b) => (a.jahr !== b.jahr ? b.jahr - a.jahr : b.monat - a.monat))
        const wahl = desc(agg)[0] ?? desc(ms)[0]
        if (wahl) {
          setGewaehlt({ jahr: wahl.jahr, monat: wahl.monat })
        } else {
          setLoading(false)
        }
      })
      .catch(() => { if (!ab) { setError('Fehler beim Laden der Monate'); setLoading(false) } })
    return () => { ab = true }
  }, [anlageId])

  // Tages-Werte (Monat + Vormonat) + Einzelmonats-KPIs (IST/Vorjahr/SOLL) laden.
  useEffect(() => {
    if (!anlageId || !gewaehlt) return
    let ab = false
    setLoading(true)
    setError(null)
    ladeMonatsdaten(anlageId, gewaehlt)
      .then(([t, m]) => { if (!ab) { setTage(t); setMonatData(m) } })
      .catch(() => { if (!ab) setError('Fehler beim Laden der Tageswerte') })
      .finally(() => { if (!ab) setLoading(false) })
    return () => { ab = true }
  }, [anlageId, gewaehlt])

  // C1: Aktualisieren (nur laufender Monat) — refetcht dieselben Quellen wie der
  // Initial-Load, ohne den Voll-Spinner (nur das Reload-Icon dreht).
  const reload = useCallback(() => {
    if (!anlageId || !gewaehlt) return
    setReloading(true)
    ladeMonatsdaten(anlageId, gewaehlt)
      .then(([t, m]) => { setTage(t); setMonatData(m) })
      .catch(() => {})
      .finally(() => setReloading(false))
  }, [anlageId, gewaehlt])

  // C2: „Abschluss starten" nur wenn Vergangenheits-Monate noch offen sind
  // (verhaltensgleich zu MonatsabschlussView.hatOffeneAbschluesse).
  const hatOffeneAbschluesse = useMemo(() => {
    const heute = new Date()
    const hj = heute.getFullYear()
    const hm = heute.getMonth() + 1
    const vm = hm === 1 ? { jahr: hj - 1, monat: 12 } : { jahr: hj, monat: hm - 1 }
    if (alleMonate.length === 0) return true
    const letzter = [...alleMonate].sort((a, b) => (b.jahr !== a.jahr ? b.jahr - a.jahr : b.monat - a.monat))[0]
    return letzter.jahr < vm.jahr || (letzter.jahr === vm.jahr && letzter.monat < vm.monat)
  }, [alleMonate])

  // Vormonat-Aggregat + Ø gleicher Monat (andere Jahre) aus der Monatsreihe.
  const vormonatAgg = useMemo<AggregierteMonatsdaten | null>(() => {
    if (!gewaehlt) return null
    const vm = vormonat(gewaehlt)
    return alleMonate.find((m) => m.jahr === vm.jahr && m.monat === vm.monat) ?? null
  }, [alleMonate, gewaehlt])

  const glMonStats = useMemo<GleicheMonatStats | null>(() => {
    if (!gewaehlt) return null
    const ms = alleMonate.filter((m) => m.monat === gewaehlt.monat && m.jahr !== gewaehlt.jahr)
    if (ms.length === 0) return null
    const avg = (vals: number[]) => (vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : null)
    const pick = (f: (m: AggregierteMonatsdaten) => number | null | undefined) =>
      avg(ms.map(f).filter((v): v is number => v != null && v > 0))
    return {
      pv: pick((m) => m.pv_erzeugung_kwh),
      ev: pick((m) => m.eigenverbrauch_kwh),
      direkt: pick((m) => m.direktverbrauch_kwh),
      einsp: pick((m) => m.einspeisung_kwh),
      netz: pick((m) => m.netzbezug_kwh),
      gesamt: pick((m) => m.gesamtverbrauch_kwh),
      autarkie: pick((m) => m.autarkie_prozent),
      count: ms.length,
    }
  }, [alleMonate, gewaehlt])

  // Rail-Einträge: verfügbare Monate + PV (Mini-Balken) + laufender Monat.
  const railEntries = useMemo<RailEintrag[]>(() => {
    const heute = new Date()
    const hj = heute.getFullYear()
    const hm = heute.getMonth() + 1
    const entries: RailEintrag[] = monate.map((m) => ({
      jahr: m.jahr, monat: m.monat,
      pv_kwh: alleMonate.find((a) => a.jahr === m.jahr && a.monat === m.monat)?.pv_erzeugung_kwh ?? 0,
      laufend: m.jahr === hj && m.monat === hm,
    }))
    if (!entries.some((e) => e.jahr === hj && e.monat === hm)) {
      entries.push({ jahr: hj, monat: hm, pv_kwh: 0, laufend: true })
    }
    return entries
  }, [monate, alleMonate])

  const istLaufend = useMemo(() => {
    if (!gewaehlt) return false
    const heute = new Date()
    return gewaehlt.jahr === heute.getFullYear() && gewaehlt.monat === heute.getMonth() + 1
  }, [gewaehlt])

  const bloecke: Block[] = useMemo(() => {
    if (!gewaehlt) return []
    // Energie-Bilanz Block-Summary = Kernwerte auf einen Blick (wie IST), nicht
    // die Struktur-Beschreibung — im eingeklappten Zustand direkt ablesbar (A1).
    const bilanzSummary = monatData
      ? `${fmtCalc(monatData.pv_erzeugung_kwh, 0, '—')} kWh PV · ${fmtCalc(monatData.autarkie_prozent, 0, '—')} % Autarkie${
          monatData.soll_pv_kwh != null && monatData.pv_erzeugung_kwh != null && monatData.soll_pv_kwh > 0
            ? ` · SOLL ${Math.round((monatData.pv_erzeugung_kwh / monatData.soll_pv_kwh) * 100)} %`
            : ''}`
      : 'IST / Vormonat / Vorjahr / Ø-Monat'
    // Kennzahlen-Kacheln parkbar machen (SLICE 1): stabile parkId je Titel; geparkte
    // werden im Strip ausgeblendet. Sind ALLE geparkt → Block-Hülle ausblenden
    // (Gernot-Abnahme 2026-06-25, Entscheidung 2).
    const kpiItems = monatData
      ? baueMonatKpis(monatData, vormonatAgg).map((k) => ({
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
              summary: '5 Energie-Kennzahlen + Netto-Ertrag + Monatsergebnis',
              defaultOpen: true,
              render: () => <KpiStrip kpis={sichtbareKpi} />,
            }
          : null)
      : {
          id: 'kpi',
          title: 'Kennzahlen',
          ...BLOCK_IDENTITAET.kennzahlen,
          summary: '5 Energie-Kennzahlen + Netto-Ertrag + Monatsergebnis',
          defaultOpen: true,
          render: () => <p className="text-sm text-gray-500 dark:text-gray-400">Keine Monats-Kennzahlen verfügbar.</p>,
        }
    // Default-Klappregel (Gernot 2026-06-19, revidiert): NUR der erste Block
    // (Kennzahlen) offen — alle übrigen eingeklappt, ihre Summary trägt den Kern.
    return [
      ...(kennzahlenBlock ? [kennzahlenBlock] : []),
      {
        id: 'bilanz',
        title: 'Energie-Bilanz',
        ...BLOCK_IDENTITAET.energieBilanz,
        summary: bilanzSummary,
        defaultOpen: false,
        render: () => (monatData
          ? <MonatBilanz d={monatData} vm={vormonatAgg} glMonStats={glMonStats} monatName={MONAT_KURZ[gewaehlt.monat]} />
          : <p className="text-sm text-gray-500 dark:text-gray-400">Keine Vergleichsdaten verfügbar.</p>),
      },
      {
        id: 'tagesverlauf',
        title: 'Verlauf',
        ...BLOCK_IDENTITAET.verlauf,
        summary: 'Tages-Bilanz: Erzeugung / Verbrauch / Autarkie',
        defaultOpen: false,
        render: () => <TagesverlaufChart tage={tage} />,
      },
      // Komponenten-Detailblöcke (aktiv-gegatet, B6/B7).
      ...(monatData ? baueKomponentenBloecke(monatData) : []),
      // Finanz-Teaser (B5) — bewusst GANZ UNTEN: Netto-Ertrag/Monatsergebnis stehen
      // bereits in den Kennzahlen (D), hier nur Aufschlüsselung + Tarif + Cross-Link.
      ...(monatData ? [finanzTeaserBlock(monatData)] : []),
    ]
  }, [gewaehlt, tage, monatData, vormonatAgg, glMonStats, park])

  if (!anlageId) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage gewählt.</p></Card>
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
            titel={gewaehlt ? monatLabel(gewaehlt) : '…'}
            laufend={istLaufend}
            d={monatData}
            onReload={reload}
            reloading={reloading}
            zeigeAbschlussLink={hatOffeneAbschluesse}
          />

          {error ? (
            <Card><p className="text-red-500">{error}</p></Card>
          ) : loading && !monatData ? (
            // Voll-Spinner NUR beim Erst-Load (noch keine Daten). Beim Monatswechsel
            // bleibt der bestehende Block-Stack stehen und aktualisiert sich in-place
            // → kein „Aufblitzen" (detLAN D7-2, 2026-06-27; analog Tag T2). Kein
            // `key={…}` mehr → BlockShell re-rendert statt zu remounten.
            <LoadingSpinner text="Lade Monat…" />
          ) : monate.length === 0 ? (
            <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Monatsdaten erfasst.</p></Card>
          ) : (
            <BlockShell persistKey={SICHT_KEY} bloecke={bloecke} sortierbar />
          )}

          {/* Element-Park-Fuß (SLICE 1): Hinweiszeile + „Geparkt (n)". Inert leer,
              bis etwas geparkt ist; rendert nichts ohne ParkProvider. */}
          <ParkFuss />
        </div>
      </div>
    </div>
  )
}
