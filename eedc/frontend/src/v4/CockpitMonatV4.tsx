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
import { useCallback, useEffect, useMemo, useState } from 'react'
import { LoadingSpinner, Card, fmtCalc } from '../components/ui'
import { BlockShell, KpiStrip, type Block } from '../components/blocks'
import { WerteTabelle } from '../components/werte'
import { tagesZeile } from '../lib/werte'
import { MONAT_KURZ, BLOCK_IDENTITAET } from '../lib'
import { TagesverlaufChart } from './TagesverlaufChart'
import { baueMonatKpis, MonatBilanz, type GleicheMonatStats } from './MonatBilanz'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { MonatsRail, type RailEintrag } from './MonatsRail'
import { MonatHeader, finanzTeaserBlock, communityBlock } from './MonatRahmen'
import { energieProfilApi, type TagWerte, type VerfuegbarerMonat } from '../api/energie_profil'
import { aktuellerMonatApi, type AktuellerMonatResponse } from '../api/aktuellerMonat'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
import { communityApi, type MonatsVergleich } from '../api/community'

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

/** Tages-Werte (Monat + Vormonat) + Einzelmonats-KPIs in einem Zug — geteilt von
 *  Initial-Load und Reload (C1), damit es keinen zweiten Fetch-Pfad gibt. */
function ladeMonatsdaten(anlageId: number, ref: MonatRef) {
  const akt = monatsSpanne(ref)
  const vm = monatsSpanne(vormonat(ref))
  return Promise.all([
    energieProfilApi.getTageWerte(anlageId, akt.von, akt.bis),
    energieProfilApi.getTageWerte(anlageId, vm.von, vm.bis).catch(() => [] as TagWerte[]),
    aktuellerMonatApi.getData(anlageId, ref.jahr, ref.monat).catch(() => null),
  ])
}

export default function CockpitMonatV4({ anlageId }: { anlageId: number | undefined }) {
  const [monate, setMonate] = useState<VerfuegbarerMonat[]>([])
  const [gewaehlt, setGewaehlt] = useState<MonatRef | null>(null)
  const [tage, setTage] = useState<TagWerte[]>([])
  const [vormonatTage, setVormonatTage] = useState<TagWerte[]>([])
  const [monatData, setMonatData] = useState<AktuellerMonatResponse | null>(null)
  const [alleMonate, setAlleMonate] = useState<AggregierteMonatsdaten[]>([])
  const [monatsVergleich, setMonatsVergleich] = useState<MonatsVergleich | null>(null)
  const [loading, setLoading] = useState(true)
  const [reloading, setReloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Verfügbare Monate + Monatsreihe (für Vormonat/Ø-Monat) laden → neuesten vorwählen.
  useEffect(() => {
    if (!anlageId) return
    let ab = false
    monatsdatenApi.listAggregiert(anlageId).then((m) => { if (!ab) setAlleMonate(m) }).catch(() => {})
    energieProfilApi.getVerfuegbareMonate(anlageId)
      .then((ms) => {
        if (ab) return
        setMonate(ms)
        if (ms.length > 0) {
          const neueste = [...ms].sort((a, b) => (a.jahr !== b.jahr ? b.jahr - a.jahr : b.monat - a.monat))[0]
          setGewaehlt({ jahr: neueste.jahr, monat: neueste.monat })
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
      .then(([t, v, m]) => { if (!ab) { setTage(t); setVormonatTage(v); setMonatData(m) } })
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
      .then(([t, v, m]) => { setTage(t); setVormonatTage(v); setMonatData(m) })
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
      einsp: pick((m) => m.einspeisung_kwh),
      netz: pick((m) => m.netzbezug_kwh),
      gesamt: pick((m) => m.gesamtverbrauch_kwh),
      autarkie: pick((m) => m.autarkie_prozent),
      count: ms.length,
    }
  }, [alleMonate, gewaehlt])

  // Community-Monats-Benchmark (data-gated; Fehler still schlucken, O4).
  useEffect(() => {
    if (!gewaehlt) return
    let ab = false
    setMonatsVergleich(null)
    communityApi.getMonatsBenchmark(gewaehlt.jahr, gewaehlt.monat)
      .then((v) => { if (!ab) setMonatsVergleich(v) })
      .catch(() => {})
    return () => { ab = true }
  }, [gewaehlt])

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
    const vmRef = vormonat(gewaehlt)
    // Energie-Bilanz Block-Summary = Kernwerte auf einen Blick (wie IST), nicht
    // die Struktur-Beschreibung — im eingeklappten Zustand direkt ablesbar (A1).
    const bilanzSummary = monatData
      ? `${fmtCalc(monatData.pv_erzeugung_kwh, 0, '—')} kWh PV · ${fmtCalc(monatData.autarkie_prozent, 0, '—')} % Autarkie${
          monatData.soll_pv_kwh != null && monatData.pv_erzeugung_kwh != null && monatData.soll_pv_kwh > 0
            ? ` · SOLL ${Math.round((monatData.pv_erzeugung_kwh / monatData.soll_pv_kwh) * 100)} %`
            : ''}`
      : 'IST / Vormonat / Vorjahr / Ø-Monat'
    return [
      {
        id: 'kpi',
        title: 'Kennzahlen',
        ...BLOCK_IDENTITAET.kennzahlen,
        summary: '5 Energie-Kennzahlen + Netto-Ertrag + Monatsergebnis',
        defaultOpen: true,
        render: () => (monatData
          ? <KpiStrip kpis={baueMonatKpis(monatData, vormonatAgg)} />
          : <p className="text-sm text-gray-500 dark:text-gray-400">Keine Monats-Kennzahlen verfügbar.</p>),
      },
      {
        id: 'bilanz',
        title: 'Energie-Bilanz',
        ...BLOCK_IDENTITAET.energieBilanz,
        summary: bilanzSummary,
        defaultOpen: true,
        render: () => (monatData
          ? <MonatBilanz d={monatData} vm={vormonatAgg} glMonStats={glMonStats} monatName={MONAT_KURZ[gewaehlt.monat]} />
          : <p className="text-sm text-gray-500 dark:text-gray-400">Keine Vergleichsdaten verfügbar.</p>),
      },
      {
        id: 'tagesverlauf',
        title: 'Tagesverlauf',
        ...BLOCK_IDENTITAET.verlauf,
        summary: 'Tageswerte des Monats ⇄ Monats-Fluss',
        // Default-Klappregel (Gernot 2026-06-19): nur Kennzahlen + Energie-Bilanz
        // offen, alle anderen Blöcke eingeklappt.
        defaultOpen: false,
        render: () => <TagesverlaufChart tage={tage} />,
      },
      {
        id: 'werte',
        title: 'Werte/Tabelle (Tagesebene)',
        ...BLOCK_IDENTITAET.werte,
        summary: 'numerischer Zwilling des Tagesverlaufs',
        defaultOpen: false,
        render: () => (
          <WerteTabelle
            rows={tage.map(tagesZeile)}
            vorjahrRows={vormonatTage.length > 0 ? vormonatTage.map(tagesZeile) : null}
            granularitaet="tag"
            jahrLabel={monatLabel(gewaehlt)}
            vergleichLabel={monatLabel(vmRef)}
            alleWerteHref="#/v4/auswertungen/tabelle"
            csvDateiname={`werte_tag_${gewaehlt.jahr}-${String(gewaehlt.monat).padStart(2, '0')}.csv`}
          />
        ),
      },
      // Finanz-Teaser (B5) + Community (O4, data-gated) — vor den Komponenten.
      ...(monatData ? [finanzTeaserBlock(monatData)] : []),
      ...(monatData && monatsVergleich
        ? [communityBlock(monatsVergleich, monatData, MONAT_KURZ[gewaehlt.monat], gewaehlt.jahr)].filter((b): b is NonNullable<typeof b> => b != null)
        : []),
      // Komponenten-Detailblöcke (aktiv-gegatet, B6/B7).
      ...(monatData ? baueKomponentenBloecke(monatData) : []),
    ]
  }, [gewaehlt, tage, vormonatTage, monatData, vormonatAgg, glMonStats, monatsVergleich])

  if (!anlageId) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage gewählt.</p></Card>
      </div>
    )
  }

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto lg:flex lg:gap-6">
      {/* Monats-Rail: links Desktop / oben Mobile (B2) */}
      <div className="lg:w-52 lg:shrink-0 mb-4 lg:mb-0">
        <MonatsRail
          entries={railEntries}
          jahr={gewaehlt?.jahr ?? 0}
          monat={gewaehlt?.monat ?? 0}
          onSelect={(j, m) => setGewaehlt({ jahr: j, monat: m })}
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
        ) : loading ? (
          <LoadingSpinner text="Lade Monat…" />
        ) : monate.length === 0 ? (
          <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Monatsdaten erfasst.</p></Card>
        ) : (
          <BlockShell key={`monat-${gewaehlt?.jahr}-${gewaehlt?.monat}`} persistKey="v4-cockpit-monat" bloecke={bloecke} sortierbar />
        )}
      </div>
    </div>
  )
}
