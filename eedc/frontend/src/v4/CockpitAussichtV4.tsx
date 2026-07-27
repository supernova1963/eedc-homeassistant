/**
 * CockpitAussichtV4 — die Projektions-/Zukunfts-Sicht der Cockpit-Zeit-Achse
 * (IA-V4 Muster A.4). SoT: `docs/drafts/SPEC-COCKPIT-AUSSICHTEN.md`.
 *
 * „Vorwärts-Teleskop" (Gernot 2026-06-22): EINE lineare Seite, deren Zoomring der
 * Horizont-Selektor ist (7 T · 14 T · 12 Monate; Mehrjahr/Degradation an 12 M
 * angehängt, AO1). Pattern-treu zu Cockpit/Monat:
 *   - Stabiler Kopf (immer da, reparametrisiert mit dem Horizont): KPI-Strip +
 *     EIN Verlauf-Hauptblock, gefüttert von den IST-Charts als Horizont-Renderer.
 *   - Darunter horizont-gescopte Detailblöcke (normale `BlockShell`).
 *
 * Read-Queries existieren (ADR-001, Shapes da): `wetterApi.getSolarPrognose`,
 * `aussichtenApi.{getPrognosenVergleich,getLangfristPrognose,getTrendAnalyse}` —
 * kein neuer Endpoint, kein Neubau der Charts. Finanz-Prognose → Auswertungen/
 * Finanzen; volles Genauigkeits-Tracking → Auswertungen/Prognose-vs-IST;
 * Trend-Historie → Cockpit/Jahr (bewusst NICHT hier).
 */
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Zap, Sun, CloudSun, TrendingUp, TrendingDown, Minus,
} from 'lucide-react'
import { Card, SegmentControl, FehlerZustand } from '../components/ui'
import { ReloadButton } from './ReloadButton'
import { AnlageLeer, OnboardingLeer } from './OnboardingLeer'
import { DatumPicker } from '../components/ui/DatumPicker'
import { BlockShell, BlockStackSkeleton, HerkunftZeile, KpiStrip, type Block, type KpiStripItem, type WertHerkunft } from '../components/blocks'
import { ParkProvider, ParkFuss, usePark, Parkbar } from '../components/park'
import {
  BLOCK_IDENTITAET, STATUS_ICONS, WT_KURZ, fmtZahl,
  pvErtragKwh, pvVormittagKwh, pvNachmittagKwh,
  prognoseSummeKwh, prognoseDurchschnittKwh, prognoseQuelleLabel,
  unvollstaendigHerkunft,
} from '../lib'
import {
  TagesPrognose, KurzfristDetails, LangfristVerlaufChart, LangfristMonatswerte,
  SaisonMuster, DegradationsPrognose, WpAussicht, AussichtFinanzTeaser, euroVz,
} from '../components/aussicht'
import { investitionenApi, type WaermepumpeDashboardResponse } from '../api/investitionen'
import { PrognoseChartKarte, PrognoseTabelle, morgenISO, heuteISO, maxPrognoseDatum } from '../pages/auswertung/EnergieprofilPrognose'
import { useApiData, useSelectedAnlage } from '../hooks'
import { wetterApi, type SolarPrognose } from '../api/wetter'
import { aussichtenApi, type FinanzPrognose, type LangfristPrognose, type TrendAnalyseResponse } from '../api/aussichten'
import { energieProfilApi, type TagesPrognose as TagesprognoseDaten } from '../api/energie_profil'

// Zwei Horizonte reichen (Gernot 2026-06-23): „7 + 14 = kurzfristig". Kurzfristig
// = 14-Tage-Solarprognose + Tages-Stundenchart; Langfristig = 12-Monats-Prognose.
type Horizont = 'kurz' | 'lang'
const HORIZONTE: { key: Horizont; label: string }[] = [
  { key: 'kurz', label: 'Kurzfristig' },
  { key: 'lang', label: 'Langfristig' },
]
const DEFAULT_HORIZONT: Horizont = 'kurz'

/** „So., 26.07." — beide Prognose-Blöcke tragen damit sichtbar IHREN Tag.
 *  Der Datumswähler sitzt nur im Stunden-Block; wer den Stundenwerte-Block
 *  allein aufklappt, sah sonst nicht, dass er standardmäßig MORGEN zeigt
 *  (Rainer-PN „Nachtrag" 2026-07-25). */
const tagLabel = (iso: string) => {
  const d = new Date(iso + 'T12:00:00')
  return `${WT_KURZ[d.getDay()]}., ${d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })}`
}
const KURZ_TAGE = 14

function istHorizont(v: string | null): v is Horizont {
  return v === 'kurz' || v === 'lang'
}

// ─── KPI-Builder (Kopf, reparametrisiert pro Horizont) ────────────────────────

// Alle Tageswerte kommen über den Anzeige-SoT (`pvErtragKwh` & Co.): eedc-
// korrigiert, sonst OpenMeteo roh. `eedcHeute` = derselbe Wert aus dem
// Prognosen-Vergleich (`days=4`-Snapshot, identisch zu Live/MQTT) und bleibt
// deshalb für „Heute" vorne — die 14-Tage-Antwort ruft OpenMeteo mit anderem
// `days` ab und kann minimal abweichen (R8-4). Keine dritte Mechanik: der
// Kanon-Wert der Solar-Prognose ist jetzt der Fallback derselben Kette.
function kurzKpis(p: SolarPrognose, eedcHeute?: number | null): KpiStripItem[] {
  const heute = p.tage[0]
  const morgen = p.tage[1]
  const vmNm = (t?: typeof heute) =>
    t && pvVormittagKwh(t) != null
      ? `VM ${fmtZahl(pvVormittagKwh(t)!, 1)} · NM ${fmtZahl(pvNachmittagKwh(t) ?? 0, 1)}`
      : undefined
  // R13-4c (Rainer #77): Reihenfolge Heute · Morgen · Summe · Durchschnitt.
  return [
    { title: 'Heute', value: fmtZahl(eedcHeute ?? (heute ? pvErtragKwh(heute) : 0), 1), unit: 'kWh', color: 'gray', icon: CloudSun, subtitle: vmNm(heute) },
    { title: 'Morgen', value: fmtZahl(morgen ? pvErtragKwh(morgen) : 0, 1), unit: 'kWh', color: 'gray', icon: CloudSun, subtitle: vmNm(morgen) },
    { title: `Summe ${p.tage.length} Tage`, value: fmtZahl(prognoseSummeKwh(p), 0), unit: 'kWh', color: 'yellow', icon: Zap },
    { title: `Ø/Tag (${p.tage.length} T)`, value: fmtZahl(prognoseDurchschnittKwh(p), 1), unit: 'kWh', color: 'blue', icon: Sun },
  ]
}

function langKpis(p: LangfristPrognose): KpiStripItem[] {
  const t = p.trend_analyse
  const spez = p.anlagenleistung_kwp > 0 ? p.jahresprognose_kwh / p.anlagenleistung_kwp : 0
  return [
    { title: 'Jahresprognose', value: p.jahresprognose_kwh.toLocaleString('de-DE'), unit: 'kWh', color: 'yellow', icon: Zap },
    { title: 'Spez. Ertrag (Prognose)', value: fmtZahl(spez, 0), unit: 'kWh/kWp', color: 'blue', icon: Sun },
    {
      title: 'Performance-Ratio (Trend)',
      value: fmtZahl(t.durchschnittliche_performance_ratio * 100, 0), unit: '%',
      color: t.trend_richtung === 'positiv' ? 'green' : t.trend_richtung === 'negativ' ? 'red' : 'gray',
      icon: t.trend_richtung === 'negativ' ? TrendingDown : t.trend_richtung === 'positiv' ? TrendingUp : Minus,
      trend: t.trend_richtung === 'positiv' ? 'up' : t.trend_richtung === 'negativ' ? 'down' : undefined,
    },
    { title: 'Datenbasis', value: `${t.datenbasis_monate} Monate`, color: 'gray', icon: STATUS_ICONS.info },
  ]
}

// Datum-Picker für die Tages-Stundenprognose (Heute/Morgen-Shortcuts + bis +14 T).
function StundenDatumPicker({ datum, setDatum }: { datum: string; setDatum: (d: string) => void }) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Prognose für:</label>
      {/* D13-4/12: Custom-DatumPicker (SoT) statt nativem Tagesfeld — Icon/Stil app-weit. */}
      <DatumPicker
        modus="tag" ariaLabel="Prognose-Datum" value={datum}
        min={heuteISO()} max={maxPrognoseDatum()}
        onChange={setDatum} className="w-auto text-sm"
      />
      {/* B15/S4: Shortcut-Paar als SegmentControl-SoT; steht der Picker auf +2..+14,
          entspricht `datum` keiner Option → beide inaktiv (von der SoT erlaubt). */}
      <SegmentControl
        ariaLabel="Prognose-Tag-Shortcut" size="sm"
        optionen={[{ key: heuteISO(), label: 'Heute' }, { key: morgenISO(), label: 'Morgen' }]}
        value={datum} onChange={setDatum}
      />
    </div>
  )
}


// ─── Orchestrator ─────────────────────────────────────────────────────────────

// persistKey-SoT der Sicht — geteilt von BlockShell (Block-Ebene) und ParkProvider
// (Element-Ebene; eigener LS-Prefix). SLICE-1-Park, analog Cockpit/Monat.
const SICHT_KEY = 'v4-cockpit-aussicht'

export default function CockpitAussichtV4(props: { anlageId: number | undefined }) {
  // ParkProvider umschließt den Body, damit `usePark` (Kennzahlen-Filter, ParkFuss)
  // im selben Baum greift. Ohne Provider blieben die Park-Hooks inert (Produktion).
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <CockpitAussichtInner {...props} />
    </ParkProvider>
  )
}

function CockpitAussichtInner({ anlageId }: { anlageId: number | undefined }) {
  const park = usePark()
  const { selectedAnlage } = useSelectedAnlage()
  const [searchParams, setSearchParams] = useSearchParams()
  const horizont: Horizont = istHorizont(searchParams.get('h')) ? (searchParams.get('h') as Horizont) : DEFAULT_HORIZONT
  const istKurz = horizont === 'kurz'

  // Tagesprognose-Datum (Stunden-Chart + Stundenwerte teilen Datum + Daten —
  // getrennte Blöcke, eine Quelle, Gernot 2026-06-23).
  const [pDatum, setPDatum] = useState(morgenISO())

  const setHorizont = (h: Horizont) => {
    const next = new URLSearchParams(searchParams)
    next.set('h', h)
    setSearchParams(next, { replace: true })
  }

  const hatKoordinaten = !!(selectedAnlage?.latitude && selectedAnlage?.longitude)

  // R18-2 (SWR): Daten je Horizont über den Sicht-Cache von useApiData — beim
  // Remount (Tab-Wechsel) stehen die alten Daten sofort, still revalidiert.
  // Skeleton nur beim echten Erst-Load; das ersetzt die frühere geladenFuer-Ref
  // (D11-9): Horizont-Wechsel mit Cache-Stand ist jetzt sofort, ohne Cache zeigt
  // er den ehrlichen Skeleton statt des irreführenden „Keine Prognose verfügbar".
  // Vorwärts-Finanz-Teaser (D2) — horizont-unabhängig (Jahresprognose),
  // Backend-Aggregat (ADR-001). Soft-fail: kein Teaser statt Sicht-Fehler.
  const finanzQ = useApiData<FinanzPrognose | null>(
    () => aussichtenApi.getFinanzPrognose(anlageId!, 12).catch(() => null),
    [anlageId],
    { enabled: !!anlageId && hatKoordinaten, swrKey: `v4-aussicht-finanz:${anlageId}` },
  )
  // Kurzfristig: Solar-Prognose + kanonischer eedc-„Heute"-Wert (R8-4, Soft-fail →
  // Fallback auf den puren SolarPrognose-Wert, kein Sicht-Fehler).
  // R22-6: `ist_stundenprofil` + `aktuelle_stunde` kommen aus DERSELBEN Antwort,
  // die hier ohnehin schon für `eedc_heute_kwh` geholt wird — die IST-Spalte der
  // Stundenwerte kostet keinen zweiten Fetch (Doppel-Fetch-Doktrin).
  const kurzQ = useApiData<{
    kurz: SolarPrognose
    eedcHeute: number | null
    istStunden: { stunde: number; kw: number | null }[] | null
    aktuelleStunde: number | null
  }>(
    async () => {
      const [k, v] = await Promise.all([
        wetterApi.getSolarPrognose(anlageId!, KURZ_TAGE, false),
        aussichtenApi.getPrognosenVergleich(anlageId!).catch(() => null),
      ])
      return {
        kurz: k,
        eedcHeute: v?.eedc_heute_kwh ?? null,
        istStunden: v?.ist_stundenprofil ?? null,
        aktuelleStunde: v?.aktuelle_stunde ?? null,
      }
    },
    [anlageId],
    { enabled: !!anlageId && hatKoordinaten && istKurz, swrKey: `v4-aussicht-kurz:${anlageId}` },
  )
  const langQ = useApiData<{ lang: LangfristPrognose; trend: TrendAnalyseResponse | null; wp: WaermepumpeDashboardResponse[] }>(
    async () => {
      const [l, t, w] = await Promise.all([
        aussichtenApi.getLangfristPrognose(anlageId!, 12),
        aussichtenApi.getTrendAnalyse(anlageId!, 5).catch(() => null),
        investitionenApi.getWaermepumpeDashboard(anlageId!).catch(() => [] as WaermepumpeDashboardResponse[]),
      ])
      return { lang: l, trend: t, wp: w }
    },
    [anlageId],
    { enabled: !!anlageId && hatKoordinaten && !istKurz, swrKey: `v4-aussicht-lang:${anlageId}` },
  )
  const kurz = kurzQ.data?.kurz ?? null
  const eedcHeute = kurzQ.data?.eedcHeute ?? null
  // IST nur für heute — für morgen gibt es keine gemessenen Stunden (R22-6).
  const istHeute = pDatum === heuteISO() ? kurzQ.data?.istStunden ?? null : null
  const lang = langQ.data?.lang ?? null
  const trend = langQ.data?.trend ?? null
  const wp = langQ.data?.wp ?? null
  const finanz = finanzQ.data ?? null
  const aktivQ = istKurz ? kurzQ : langQ
  // Fehler nur ohne Daten als Sicht-Fehler zeigen; mit Cache-Stand bleiben die
  // alten Daten stehen (SWR-Semantik, KONZEPT-LADEZEIT-CACHE-SWR §3).
  const loading = hatKoordinaten && aktivQ.loading
  const reloading = aktivQ.reloading || finanzQ.reloading
  const error = aktivQ.data == null ? aktivQ.error : null
  const laden = () => { aktivQ.refetch(); finanzQ.refetch() }

  // Tagesprognose laden (nur Kurzfristig; Stunden-Chart + Stundenwerte teilen sie).
  const tagesQ = useApiData<TagesprognoseDaten>(
    () => energieProfilApi.getTagesprognose(anlageId!, pDatum),
    [anlageId, pDatum],
    { enabled: !!anlageId && hatKoordinaten && istKurz, swrKey: `v4-aussicht-stunden:${anlageId}:${pDatum}` }, /* de-de-allow: Cache-Key, keine Anzeige */
  )
  const pDaten = tagesQ.data
  const pError = tagesQ.data == null ? tagesQ.error : null

  const bloecke = useMemo<Block[]>(() => {
    // Vorwärts-Finanz-Teaser (D2) — in BEIDEN Horizonten ganz unten (analog
    // Cockpit/Monat); dezent, default eingeklappt. Jahresprognose, horizont-unabhängig.
    // Finanz-Teaser: Bilanz(+Tarif) und Cross-Link je eigene Parkbar (in AussichtFinanzTeaser);
    // Block entfällt erst, wenn BEIDE geparkt sind.
    const finanzTeaserGeparkt = park.istGeparkt('el:aussicht-finanz-bilanz') && park.istGeparkt('el:aussicht-finanz-link')
    const finanzTeaser: Block | null = finanz && !finanzTeaserGeparkt ? {
      id: 'finanzen', title: 'Finanzen', ...BLOCK_IDENTITAET.finanzen,
      summary: `${euroVz(finanz.jahres_netto_ertrag_euro)} Netto-Ertrag (Jahresprognose)`,
      defaultOpen: false,
      render: () => <AussichtFinanzTeaser finanz={finanz} />,
    } : null
    // R5-5a (Rainer): Kennzahlen-Kacheln parkbar (SLICE 1) — stabile parkId je
    // Titel, geparkte raus; sind ALLE geparkt → Block ganz weg (wie Cockpit/Monat).
    const kennzahlenBlock = (
      items: KpiStripItem[], summary: string, herkunft?: WertHerkunft,
    ): Block | null => {
      const mit = items.map((k) => ({ ...k, parkId: `kpi:${k.title.toLowerCase().replace(/[^a-z0-9]+/gi, '-')}` }))
      const sichtbar = mit.filter((k) => !park.istGeparkt(k.parkId!))
      if (!sichtbar.length) return null
      return {
        id: 'kpi', title: 'Kennzahlen', ...BLOCK_IDENTITAET.kennzahlen,
        summary, defaultOpen: true, render: () => (
          <div className="space-y-2">
            <HerkunftZeile herkunft={herkunft} />
            <KpiStrip kpis={sichtbar} />
          </div>
        ),
      }
    }
    if (istKurz) {
      if (!kurz) return []
      // Summenzeile == Σ der Balken: dieselben Aggregate wie die KPIs (SoT),
      // sonst widerspräche sich die Seite an anderer Stelle erneut.
      const quelleLabel = prognoseQuelleLabel(kurz)
      // P4 (N77): war der Multi-String-Fan-out unvollständig, sind Summe, Ø/Tag und
      // alle Tagesbalken eine Teilsumme. Das Backend sagt es in `hinweise`; hier
      // steht es an beiden Stellen, wo die betroffenen Zahlen stehen.
      const kurzHerkunft = unvollstaendigHerkunft(kurz.hinweise, 'PV-Prognose')
      const kpi = kennzahlenBlock(kurzKpis(kurz, eedcHeute), `${fmtZahl(prognoseSummeKwh(kurz), 0)} kWh in ${kurz.tage.length} Tagen · Ø ${fmtZahl(prognoseDurchschnittKwh(kurz), 1)} kWh/Tag`, kurzHerkunft)
      // Aussicht-Anzeigen sind einzeln parkbar (Doktrin): render in `Parkbar`, und ist
      // die Anzeige geparkt → ganzer Block weg (wie Cockpit/Monat-Verlauf).
      const list: Block[] = [
        ...(kpi ? [kpi] : []),
        ...(park.istGeparkt('el:aussicht-tages') ? [] : [{
          id: 'verlauf', title: 'Tages-Prognose', ...BLOCK_IDENTITAET.wetter,
          summary: `${kurz.tage.length} Tage: Wetter, Temperatur & PV-Ertrag je Tag · Quelle ${quelleLabel}`,
          defaultOpen: true,
          render: () => (
            <Parkbar id="el:aussicht-tages" titel="Tages-Prognose">
              <div className="space-y-2">
                <HerkunftZeile herkunft={kurzHerkunft} />
                <TagesPrognose tage={kurz.tage} quelleLabel={quelleLabel} />
              </div>
            </Parkbar>
          ),
        }]),
        ...(park.istGeparkt('el:aussicht-tage-tabelle') ? [] : [{
          id: 'details', title: `${kurz.tage.length}-Tage-Tabelle`, ...BLOCK_IDENTITAET.werte,
          summary: `VM/NM · GTI · Bewölkung · Temp · Niederschlag · Wettermodell · Quelle ${quelleLabel}`,
          defaultOpen: false,
          render: () => <Parkbar id="el:aussicht-tage-tabelle" titel={`${kurz.tage.length}-Tage-Tabelle`}><KurzfristDetails tage={kurz.tage} /></Parkbar>,
        }]),
        // Stunden-Ebene (1 Tag): Chart + Tabelle als GETRENNTE Blöcke, eine Quelle.
        // Datum-Picker = Chrome (bleibt), nur der Chart ist die parkbare Anzeige →
        // geparkt entfällt der ganze Stunden-Block (Picker ohne Chart sinnlos).
        ...(park.istGeparkt('el:aussicht-stunden') ? [] : [{
          id: 'stunden', title: `Stunden-Prognose · ${tagLabel(pDatum)}`, ...BLOCK_IDENTITAET.verlauf,
          summary: `PV + Verbrauch + Speicher je Stunde${pDaten?.pv_quelle ? ` · Quelle ${pDaten.pv_quelle}` : ''} (wählbarer Tag)`,
          defaultOpen: false,
          render: () => (
            <div className="space-y-4">
              <StundenDatumPicker datum={pDatum} setDatum={setPDatum} />
              {pError
                ? <p className="text-sm text-amber-600 dark:text-amber-400">{pError}</p>
                : pDaten ? <Parkbar id="el:aussicht-stunden" titel="Stunden-Prognose"><PrognoseChartKarte daten={pDaten} /></Parkbar>
                : <p className="text-sm text-gray-500 dark:text-gray-400">Lade Tagesprognose…</p>}
            </div>
          ),
        }]),
        ...(park.istGeparkt('el:aussicht-stundenwerte') ? [] : [{
          id: 'stundenwerte', title: `Stundenwerte · ${tagLabel(pDatum)}`, ...BLOCK_IDENTITAET.werte,
          summary: `Stundenprognose in kW${istHeute ? ' + gemessenes IST' : ''} · Summenzeile = kWh/Tag${pDaten?.pv_quelle ? ` · Quelle ${pDaten.pv_quelle}` : ''}`,
          defaultOpen: false,
          render: () => (pDaten
            ? <Parkbar id="el:aussicht-stundenwerte" titel="Stundenwerte">
                <PrognoseTabelle
                  daten={pDaten}
                  ohneCaption
                  istStunden={istHeute ?? undefined}
                  aktuelleStunde={kurzQ.data?.aktuelleStunde ?? null}
                />
              </Parkbar>
            : <p className="text-sm text-gray-500 dark:text-gray-400">{pError ?? 'Lade Tagesprognose…'}</p>),
        }]),
      ]
      if (finanzTeaser) list.push(finanzTeaser)
      return list
    }
    // 12 Monate
    if (!lang) return []
    const kpiLang = kennzahlenBlock(langKpis(lang), `${lang.jahresprognose_kwh.toLocaleString('de-DE')} kWh Jahresprognose`)
    // Aussicht-Anzeigen einzeln parkbar (Doktrin): render in `Parkbar`, geparkt → Block weg.
    const list: Block[] = [
      ...(kpiLang ? [kpiLang] : []),
      ...(park.istGeparkt('el:aussicht-monats') ? [] : [{
        id: 'verlauf', title: 'Monats-Prognose', ...BLOCK_IDENTITAET.verlauf,
        summary: 'PVGIS vs. Trend-korrigiert + Konfidenzband',
        defaultOpen: true,
        render: () => <Parkbar id="el:aussicht-monats" titel="Monats-Prognose"><LangfristVerlaufChart prognose={lang} /></Parkbar>,
      }]),
      ...(park.istGeparkt('el:aussicht-monatswerte') ? [] : [{
        id: 'monatswerte', title: 'Monatswerte', ...BLOCK_IDENTITAET.werte,
        summary: 'PVGIS · Trend-korrigiert · Min/Max · Hist. PR + Gesamt',
        defaultOpen: false,
        render: () => <Parkbar id="el:aussicht-monatswerte" titel="Monatswerte"><LangfristMonatswerte prognose={lang} /></Parkbar>,
      }]),
      ...(park.istGeparkt('el:aussicht-saison') ? [] : [{
        id: 'saison', title: 'Saisonale Muster', ...BLOCK_IDENTITAET.saison,
        summary: trend ? `Beste: ${trend.saisonale_muster.beste_monate.slice(0, 2).join(', ')}` : 'Beste / schwächste Monate',
        defaultOpen: false,
        render: () => (trend
          ? <Parkbar id="el:aussicht-saison" titel="Saisonale Muster"><SaisonMuster muster={trend.saisonale_muster} /></Parkbar>
          : <p className="text-sm text-gray-500 dark:text-gray-400">Noch keine saisonalen Muster verfügbar.</p>),
      }]),
    ]
    if (trend && !park.istGeparkt('el:aussicht-degradation')) {
      const grad = trend.degradation.geschaetzt_prozent_jahr
      list.push({
        id: 'degradation', title: 'Degradations-Prognose', ...BLOCK_IDENTITAET.degradation,
        // C3/S19: Degradation = 2 NK (typisch 0,3–0,5 %/Jahr — 1 NK verlöre Information).
        summary: grad == null ? 'noch nicht bewertbar' : grad === 0 ? 'keine messbar' : `${fmtZahl(grad, 2)} % / Jahr`,
        defaultOpen: false,
        render: () => <Parkbar id="el:aussicht-degradation" titel="Degradations-Prognose"><DegradationsPrognose trend={trend} /></Parkbar>,
      })
    }
    // WP-Aussicht — data-gated (nur wenn die Anlage eine WP hat); Komponenten-
    // Temporales lebt in Cockpit/Aussicht (21.06.-Regel), nicht im Hub.
    if (wp && wp.length > 0 && !park.istGeparkt('el:aussicht-wp')) {
      list.push({
        id: 'wp-aussicht', title: 'Wärmepumpe — Ausblick', ...BLOCK_IDENTITAET.wpAussicht,
        summary: 'Effizienz-Trend (JAZ) + erwartete Heizsaison',
        defaultOpen: false,
        render: () => <Parkbar id="el:aussicht-wp" titel="Wärmepumpe — Ausblick"><WpAussicht wpDashboards={wp} /></Parkbar>,
      })
    }
    if (finanzTeaser) list.push(finanzTeaser)
    return list
  }, [istKurz, kurz, eedcHeute, istHeute, kurzQ.data?.aktuelleStunde, lang, trend, wp, finanz, pDatum, pDaten, pError, park])

  if (!anlageId) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <AnlageLeer titel="Noch keine Anlage gewählt." />
      </div>
    )
  }

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      {/* L-Header: Titel · Horizont-Selektor · Datenquelle · Reload */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-lg font-bold text-gray-900 dark:text-white">Aussicht</h1>
          {/* Horizont-Selektor (SegmentControl-SoT, URL-linkbar ?h=) */}
          <SegmentControl
            ariaLabel="Prognose-Horizont" size="sm"
            optionen={HORIZONTE.map((h) => ({ key: h.key, label: h.label }))}
            value={horizont} onChange={setHorizont}
          />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <ReloadButton onClick={laden} loading={reloading} disabled={loading} />
        </div>
      </div>

      {!hatKoordinaten ? (
        // B8 (S15): handgerollter EmptyState-Zwilling → SoT (Texte + CTA unverändert).
        <OnboardingLeer
          icon={Sun}
          titel="Standort nicht konfiguriert"
          beschreibung="Für Prognosen werden die Koordinaten der Anlage benötigt. Bitte konfiguriere den Standort in den Anlagen-Einstellungen."
          ctaHref="#/einstellungen/stammdaten"
          ctaLabel="Anlage konfigurieren"
        />
      ) : error ? (
        // B8-Fehler-Baustein (S15): refetch ohne Cache-Stand = nicht-silent →
        // Lade-Zustand statt Leer-Flash während des Retrys.
        <FehlerZustand text={error} onRetry={laden} />
      ) : loading ? (
        // B8-Skeleton (S15): faktisch Erst-Load/Anlagenwechsel-only (geladenFuer-Ref,
        // D11-9); Chart-Form — der kurz-Default öffnet KPI- + Verlaufs-Block.
        <BlockStackSkeleton label="Lade Aussicht…" offen="chart" />
      ) : bloecke.length === 0 ? (
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Keine Prognose verfügbar.</p></Card>
      ) : (
        <BlockShell key={horizont} persistKey={`v4-cockpit-aussicht-${horizont}`} bloecke={bloecke} sortierbar />
      )}

      {/* Element-Park-Fuß (SLICE 1): Hinweiszeile + „Geparkt (n)". Inert, bis etwas
          geparkt ist. */}
      <ParkFuss />
    </div>
  )
}
