/**
 * CockpitTagV4 — die Einzeltag-Sicht der Cockpit-Zeit-Achse (IA-V4).
 *
 * 1:1-Muster von Cockpit/Monat, nur Granularität = Tag/Stunde:
 *  - Auswahl wie Monat: Desktop {@link TagesRail} (Zeitstrahl, Mini-PV-Balken,
 *    „heute"-Badge) + mobil schwebender {@link TagStepper} (Player). Responsive
 *    `hidden lg:block` / `lg:hidden` identisch zu Monat.
 *  - {@link TagHeader} = Pendant zu MonatHeader (Titel + Status-Badge + Reload +
 *    Quellen-Provenance).
 *  - `BlockShell` mit derselben Block-Reihe wie Monat: Kennzahlen → Energie-Bilanz
 *    → Stundenverlauf → Stundenwerte → Komponenten (Speicher/WP/E-Mob/BKW/Sonstiges)
 *    → Finanzen (über die GETEILTEN Monat-Bauer, period='tag').
 *
 * Datenpfade — kein neuer Endpoint:
 *  - KPI/Bilanz aus dem Tages-Werte-SoT `getTageWerte` (`TagWerte`, wie Monat-SoT,
 *    NICHT aus Stunden summiert). 90-Tage-Fenster liefert Tag + Vortag + Ø-Wochentag.
 *  - Stundenverlauf/Stundenwerte + Komponenten-Energie/WP-Counter aus `getStunden`.
 *  - Rail-/Stepper-Liste = letzte 90 Tage (Schnellauswahl); ALLE verfügbaren Tage
 *    erreicht man über die Datumsauswahl im Stepper (Date-Input ab dem ältesten Tag)
 *    + „Zurücksetzen" auf den neuesten Tag. Das 90-Tage-`FENSTER` dient zugleich dem
 *    Ø-gleicher-Wochentag-Rückblick ab dem gewählten Tag.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Card, FehlerZustand } from '../components/ui'
import { AnlageLeer } from './OnboardingLeer'
import { BlockShell, BlockStackSkeleton, KpiStrip, type Block } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar, usePark } from '../components/park'
import { useScrollErhalt } from '../hooks'
import { BLOCK_IDENTITAET, DEDIZIERTE_KATEGORIEN, fmtZahl, WT_LANG } from '../lib'
import { TagVerlaufChart, TagWerteTabelle } from '../components/tag'
import { baueTagKpis, TagBilanz, type GleicheWochentagStats } from './TagBilanz'
import { baueTagKomponentenUndFinanz } from './TagKomponenten'
import { TagesRail, type TagRailEintrag } from './TagesRail'
import { TagStepper } from './TagStepper'
import { TagHeader } from './TagRahmen'
import {
  energieProfilApi, type StundenWert, type SerieInfo, type TagWerte, type TagDetail,
} from '../api/energie_profil'

// ─── Datums-Helfer (TZ-stabil über Mittag) ───────────────────────────────────
function toISODate(d: Date): string { return d.toISOString().slice(0, 10) }
function heuteISO(): string { return toISODate(new Date()) }
function gesternISO(): string { const d = new Date(); d.setDate(d.getDate() - 1); return toISODate(d) }
function tagVerschieben(iso: string, tage: number): string {
  const d = new Date(iso + 'T12:00:00'); d.setDate(d.getDate() + tage); return toISODate(d)
}
function vorTagen(iso: string, tage: number): string {
  const d = new Date(iso + 'T12:00:00'); d.setDate(d.getDate() - tage); return toISODate(d)
}
function wochentagOf(iso: string): number { return new Date(iso + 'T12:00:00').getDay() }

// (a) Gernot 2026-06-26: Picker/Liste (Rail) = letzte 90 Tage; ALLE verfügbaren
// Tage erreicht man über die Datumsauswahl (Date-Input, ältester Tag aus
// `verfuegbare-monate`) + „Zurücksetzen". Dasselbe 90-Fenster dient dem Ø-gleicher-
// Wochentag-Rückblick ab dem gewählten Tag (das `tage-werte`-Backend deckelt 366 T).
const FENSTER_TAGE = 90

/** Ø über die gleichen Wochentage im Fenster — client-seitiges Mittel vorab-
 *  aggregierter Tageswerte (wie Monat `glMonStats`). */
function berechneWochentagStats(fenster: TagWerte[], datum: string): GleicheWochentagStats | null {
  const wt = wochentagOf(datum)
  const tage = fenster.filter((r) => r.datum !== datum && wochentagOf(r.datum) === wt)
  if (tage.length === 0) return null
  const avg = (vals: number[]) => (vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : null)
  const pick = (f: (r: TagWerte) => number | null | undefined) =>
    avg(tage.map(f).filter((v): v is number => v != null && v > 0))
  return {
    pv: pick((r) => r.erzeugung),
    ev: pick((r) => r.eigenverbrauch),
    direkt: pick((r) => r.direktverbrauch),
    einsp: pick((r) => r.einspeisung),
    netz: pick((r) => r.netzbezug),
    gesamt: pick((r) => r.gesamtverbrauch),
    autarkie: pick((r) => r.autarkie),
    count: tage.length,
  }
}

// persistKey-SoT der Sicht — geteilt von BlockShell (Block-Ebene) und ParkProvider
// (Element-Ebene); eigene LS-Prefixe (`eedc-bloecke:` vs. `eedc-park:`).
const SICHT_KEY = 'v4-cockpit-tag'

export default function CockpitTagV4(props: { anlageId: number | undefined }) {
  // ParkProvider umschließt den Body, damit `usePark` (Kennzahlen-Filter, ParkFuss)
  // im selben Baum greift — wie Cockpit/Monat (SLICE-1-Referenz).
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <CockpitTagInner {...props} />
    </ParkProvider>
  )
}

function CockpitTagInner({ anlageId }: { anlageId: number | undefined }) {
  const park = usePark()
  const [datum, setDatum] = useState(gesternISO())
  const [railEntries, setRailEntries] = useState<TagRailEintrag[]>([])
  const [stunden, setStunden] = useState<StundenWert[]>([])
  const [serien, setSerien] = useState<SerieInfo[]>([]) // volle Serien (Komponenten-Klassifikation)
  const [tag, setTag] = useState<TagWerte | null>(null)
  const [tagDetail, setTagDetail] = useState<TagDetail | null>(null)
  const [vortag, setVortag] = useState<TagWerte | null>(null)
  const [wtStats, setWtStats] = useState<GleicheWochentagStats | null>(null)
  const [loading, setLoading] = useState(true)
  // D12-1: „je geladen?" statt `!tag` als Voll-Spinner-Gate — sonst flasht der
  // Spinner beim Wechsel Lücken-Tag → Lücken-Tag (tag bleibt null) und reißt das
  // Vollbild weg. Erst-Load zeigt Spinner, danach nie wieder (in-place reload).
  const [jeGeladen, setJeGeladen] = useState(false)
  const [reloading, setReloading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [aeltesterTag, setAeltesterTag] = useState<string>()  // (a) Date-Input-Untergrenze = ältester verfügbarer Tag

  // B1: Scroll-Position beim Tageswechsel halten (siehe CockpitMonatV4).
  const rootRef = useRef<HTMLDivElement>(null)
  const merkeScroll = useScrollErhalt(rootRef, loading)
  const initialisiert = useRef(false)  // R5-1: Default einmalig auf „neuester Tag mit Daten"
  const waehle = useCallback((d: string) => {
    initialisiert.current = true  // ab erster User-Wahl nicht mehr automatisch umspringen
    merkeScroll(); setDatum(d)
  }, [merkeScroll])

  // Rail-/Stepper-Liste = verfügbare Tage (letzte 90 Tage), einmal je Anlage —
  // wie Monat seine verfügbaren Monate lädt (selektion-unabhängig).
  useEffect(() => {
    if (!anlageId) return
    let ab = false
    const heute = heuteISO()
    energieProfilApi.getTageWerte(anlageId, vorTagen(heute, FENSTER_TAGE), heute)
      .then((tw) => {
        if (ab) return
        const entries: TagRailEintrag[] = tw.map((r) => ({ datum: r.datum, pv_kwh: r.erzeugung ?? 0, heute: r.datum === heute }))
        if (!entries.some((e) => e.datum === heute)) entries.push({ datum: heute, pv_kwh: 0, heute: true })
        setRailEntries(entries)
        // R5-1 (Rainer): Default = neuester Tag MIT Daten (einheitlich mit Cockpit/
        // Monat+Jahr), NICHT fix „gestern" — sonst landet man auf einem leeren
        // Kalendertag, wenn die jüngsten Tagesdaten älter sind (Demo bis 23.06.;
        // bzw. verzögerte HA-Aggregation). Nur beim Erst-Load, nie über eine
        // bereits getroffene User-Wahl hinweg.
        if (!initialisiert.current) {
          const neuesterMitDaten = tw.reduce<string | null>((m, r) => (m && m >= r.datum ? m : r.datum), null)
          if (neuesterMitDaten) { initialisiert.current = true; setDatum(neuesterMitDaten) }
        }
      })
      .catch(() => { if (!ab) setRailEntries([]) })
    return () => { ab = true }
  }, [anlageId])

  // (a) Ältester verfügbarer Tag für die Datumsauswahl-Untergrenze — aus den
  // verfügbaren Monaten (uncapped, leichtgewichtig); erster Tag des frühesten Monats.
  useEffect(() => {
    if (!anlageId) return
    let ab = false
    energieProfilApi.getVerfuegbareMonate(anlageId)
      .then((ms) => {
        if (ab || ms.length === 0) return
        const frueh = [...ms].sort((a, b) => (a.jahr !== b.jahr ? a.jahr - b.jahr : a.monat - b.monat))[0]
        setAeltesterTag(`${frueh.jahr}-${String(frueh.monat).padStart(2, '0')}-01`)
      })
      .catch(() => {})
    return () => { ab = true }
  }, [anlageId])

  const laden = useCallback(async (silent = false) => {
    if (!anlageId) return
    const reqId = anlageId
    silent ? setReloading(true) : setLoading(true)
    setError(null)
    try {
      // tag-detail (snapshot-teuer) nur für den GEWÄHLTEN Tag; soft-fail, damit der
      // Rest auch ohne die Zusatzwerte lädt (Bauer lassen fehlende Felder weg).
      const [stundenAntwort, fenster, detail] = await Promise.all([
        energieProfilApi.getStunden(reqId, datum),
        energieProfilApi.getTageWerte(reqId, vorTagen(datum, FENSTER_TAGE), datum),
        energieProfilApi.getTagDetail(reqId, datum).catch(() => null),
      ])
      setStunden(stundenAntwort.stunden)
      setSerien(stundenAntwort.serien)
      setTagDetail(detail)
      const vortagISO = tagVerschieben(datum, -1)
      setTag(fenster.find((r) => r.datum === datum) ?? null)
      setVortag(fenster.find((r) => r.datum === vortagISO) ?? null)
      setWtStats(berechneWochentagStats(fenster, datum))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Laden des Tages')
    } finally {
      silent ? setReloading(false) : setLoading(false)
      setJeGeladen(true)  // D12-1: ab jetzt nur noch in-place aktualisieren, kein Voll-Spinner
    }
  }, [anlageId, datum])

  useEffect(() => {
    if (!anlageId) { setLoading(false); return }
    laden(false)
  }, [anlageId, laden])

  const bloecke = useMemo<Block[]>(() => {
    const list: Block[] = []
    // Extra-Serien (nicht-dedizierte) für Chart/Tabelle — wie IST-„Tagesdetail".
    const extraSerien = serien.filter((s) => !DEDIZIERTE_KATEGORIEN.has(s.kategorie))
    const wochentag = WT_LANG[wochentagOf(datum)]
    if (tag) {
      // Kennzahlen-Kacheln parkbar (SLICE 1): stabile parkId je Titel; geparkte
      // werden im Strip ausgeblendet, sind ALLE geparkt → Block-Hülle weglassen
      // (Monat-Referenz, Gernot-Abnahme 2026-06-25).
      const kpiItems = baueTagKpis(tag, vortag, tagDetail?.soll_pv_kwh, {
        kwh: tagDetail?.speicher_ladung_netz_kwh,
        preis_cent: tagDetail?.speicher_effektiver_ladepreis_cent,
      }).map((k) => ({
        ...k,
        parkId: `kpi:${k.title.toLowerCase().replace(/[^a-z0-9]+/gi, '-')}`,
      }))
      const sichtbareKpi = kpiItems.filter((k) => !park.istGeparkt(k.parkId))
      if (sichtbareKpi.length > 0) {
        list.push({
          id: 'kpi', title: 'Kennzahlen', ...BLOCK_IDENTITAET.kennzahlen,
          summary: `${fmtZahl(tag.erzeugung, 0)} kWh PV · ${tag.autarkie != null ? fmtZahl(tag.autarkie, 0) : '—'} % Autarkie`,
          defaultOpen: true,
          render: () => <KpiStrip kpis={sichtbareKpi} />,
        })
      }
      // Bilanz-Panel als parkbares Element; geparkt → ganzer Block weg.
      if (!park.istGeparkt('el:bilanz')) list.push({
        id: 'bilanz', title: 'Energie-Bilanz', ...BLOCK_IDENTITAET.energieBilanz,
        summary: `IST / Vortag${wtStats ? ` / Ø ${wochentag}` : ''}`,
        defaultOpen: false,
        render: () => <Parkbar id="el:bilanz" titel="Energie-Bilanz"><TagBilanz t={tag} vt={vortag} wtStats={wtStats} wochentagName={wochentag} /></Parkbar>,
      })
    } else {
      // D11-2: Tag ohne Daten (z. B. Lücken-Tag) — denselben `kpi`-Block mit Hinweis
      // rendern statt die Block-Liste leeren. So bleibt im Vollbild der Block (gleiche
      // ID) stehen, statt dass BlockShell unmountet und das Vollbild abrupt wegbricht.
      list.push({
        id: 'kpi', title: 'Kennzahlen', ...BLOCK_IDENTITAET.kennzahlen,
        summary: 'keine Daten für diesen Tag', defaultOpen: true,
        render: () => (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Für diesen Tag liegen keine Daten vor. Wähle einen Tag mit Messwerten.
          </p>
        ),
      })
    }
    if (stunden.length > 0) {
      if (!park.istGeparkt('el:stundenverlauf')) list.push({
        id: 'verlauf', title: 'Stundenverlauf', ...BLOCK_IDENTITAET.verlauf,
        summary: 'Stundenmittel: Quellen ▲ / Senken ▼',
        defaultOpen: false,
        render: () => <Parkbar id="el:stundenverlauf" titel="Stundenverlauf"><TagVerlaufChart daten={stunden} extraSerien={extraSerien} /></Parkbar>,
      })
      if (!park.istGeparkt('el:stundenwerte')) list.push({
        id: 'stundenwerte', title: 'Stundenwerte', ...BLOCK_IDENTITAET.werte,
        summary: 'Stundenwerte in kW · Σ-Zeile = kWh/Tag',
        defaultOpen: false,
        render: () => <Parkbar id="el:stundenwerte" titel="Stundenwerte"><TagWerteTabelle daten={stunden} extraSerien={extraSerien} datum={datum} /></Parkbar>,
      })
    }
    // Komponenten-Detailblöcke (aktiv-gegated) + Finanz-Teaser — dieselben Bauer
    // wie Cockpit/Monat (period='tag'). `tagDetail` füttert die tagesgenauen
    // Zusatzwerte (WP-Strom-Split, Speicher-Netzladung/Ladepreis).
    if (tag) list.push(...baueTagKomponentenUndFinanz(tag, stunden, serien, park, tagDetail))
    return list
  }, [tag, vortag, wtStats, stunden, serien, datum, tagDetail, park])

  if (!anlageId) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <AnlageLeer titel="Noch keine Anlage gewählt." />
      </div>
    )
  }

  const istHeute = datum >= heuteISO()

  return (
    <div ref={rootRef} className="p-3 sm:p-6 max-w-[1920px] mx-auto">
      {/* Mobil: schwebender Player-Stepper — direktes Kind der voll-hohen Wurzel
          (NICHT in der kurzen Rail-Spalte), damit `sticky` beim Scrollen hält. */}
      <TagStepper entries={railEntries} datum={datum} onSelect={waehle} aeltesterTag={aeltesterTag} />

      <div className="lg:flex lg:gap-6">
        {/* Desktop: Rail-Sidebar (links) */}
        <div className="hidden lg:block lg:w-52 lg:shrink-0">
          <TagesRail entries={railEntries} datum={datum} onSelect={waehle} aeltesterTag={aeltesterTag} />
        </div>

        <div className="flex-1 min-w-0 space-y-4">
          <TagHeader datum={datum} laufend={istHeute} tag={tag} onReload={() => laden(true)} reloading={reloading} />

          {error ? (
            // B8-Fehler-Baustein (S15): laden(false) setzt setError(null) + refetcht alle Quellen.
            <FehlerZustand text={error} onRetry={() => laden(false)} />
          ) : loading && !jeGeladen ? (
            // Skeleton NUR beim allerersten Load (noch nie geladen). Beim
            // Tageswechsel bleibt der Block-Stack stehen und aktualisiert sich
            // in-place → kein Hochspringen, kein „Aufblitzen" (detLAN T2). D12-1:
            // `!jeGeladen` statt `!tag` — bei Lücke→Lücke ist tag null, würde sonst
            // den Lade-Zustand flashen und das Vollbild wegreißen. Kein `key={datum}`.
            <BlockStackSkeleton label="Lade Tag…" />
          ) : bloecke.length === 0 ? (
            <Card><p className="text-sm text-gray-500 dark:text-gray-400">Keine Daten für diesen Tag vorhanden.</p></Card>
          ) : (
            <BlockShell
              persistKey={SICHT_KEY}
              bloecke={bloecke}
              sortierbar
              /* D10-2: im Vollbild läuft die Tages-Nav oben mit (auf jeder Breite). */
              fokusKopf={
                <TagStepper entries={railEntries} datum={datum} onSelect={waehle} aeltesterTag={aeltesterTag} immerSichtbar />
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
