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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Zap, Sun, CloudSun, TrendingUp, TrendingDown, Minus,
} from 'lucide-react'
import { Card, SegmentControl, FehlerZustand } from '../components/ui'
import { ReloadButton } from './ReloadButton'
import { AnlageLeer, OnboardingLeer } from './OnboardingLeer'
import { DatumPicker } from '../components/ui/DatumPicker'
import { BlockShell, BlockStackSkeleton, KpiStrip, type Block, type KpiStripItem } from '../components/blocks'
import { ParkProvider, ParkFuss, usePark, Parkbar } from '../components/park'
import { BLOCK_IDENTITAET, STATUS_ICONS, fmtZahl } from '../lib'
import {
  TagesPrognose, KurzfristDetails, LangfristVerlaufChart, LangfristMonatswerte,
  SaisonMuster, DegradationsPrognose, WpAussicht, AussichtFinanzTeaser, euroVz,
} from '../components/aussicht'
import { investitionenApi, type WaermepumpeDashboardResponse } from '../api/investitionen'
import { PrognoseChartKarte, PrognoseTabelle, morgenISO, heuteISO, maxPrognoseDatum } from '../pages/auswertung/EnergieprofilPrognose'
import { useSelectedAnlage } from '../hooks'
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
const KURZ_TAGE = 14

function istHorizont(v: string | null): v is Horizont {
  return v === 'kurz' || v === 'lang'
}

// ─── KPI-Builder (Kopf, reparametrisiert pro Horizont) ────────────────────────

// `eedcHeute` = kanonischer eedc-Tageswert (Prognose-Kanon, v3.45.6). Die „Heute"-KPI
// MUSS ihn zeigen — sonst stünde hier der pure `/solar-prognose`-Wert und wiche von
// allen anderen Anzeigen ab (R8-4). Spiegelt `KurzfristTab` (`eedc ?? pur`).
function kurzKpis(p: SolarPrognose, eedcHeute?: number | null): KpiStripItem[] {
  const heute = p.tage[0]
  const morgen = p.tage[1]
  const vmNm = (t?: typeof heute) =>
    t?.pv_ertrag_morgens_kwh != null
      ? `VM ${fmtZahl(t.pv_ertrag_morgens_kwh, 1)} · NM ${fmtZahl(t.pv_ertrag_nachmittags_kwh ?? 0, 1)}`
      : undefined
  // R13-4c (Rainer #77): Reihenfolge Heute · Morgen · Summe · Durchschnitt.
  return [
    { title: 'Heute', value: fmtZahl(eedcHeute ?? heute?.pv_ertrag_kwh ?? 0, 1), unit: 'kWh', color: 'gray', icon: CloudSun, subtitle: vmNm(heute) },
    { title: 'Morgen', value: fmtZahl(morgen?.pv_ertrag_kwh ?? 0, 1), unit: 'kWh', color: 'gray', icon: CloudSun, subtitle: vmNm(morgen) },
    { title: `Summe ${p.tage.length} Tage`, value: fmtZahl(p.summe_kwh, 0), unit: 'kWh', color: 'yellow', icon: Zap },
    { title: `Ø/Tag (${p.tage.length} T)`, value: fmtZahl(p.durchschnitt_kwh_tag, 1), unit: 'kWh', color: 'blue', icon: Sun },
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

  const [kurz, setKurz] = useState<SolarPrognose | null>(null)
  const [eedcHeute, setEedcHeute] = useState<number | null>(null) // kanonischer eedc-„Heute"-Wert (R8-4), parallel zur SolarPrognose
  const [lang, setLang] = useState<LangfristPrognose | null>(null)
  // Tagesprognose (Stunden-Chart + Stundenwerte teilen Datum + Daten — getrennte
  // Blöcke, eine Quelle, Gernot 2026-06-23).
  const [pDatum, setPDatum] = useState(morgenISO())
  const [pDaten, setPDaten] = useState<TagesprognoseDaten | null>(null)
  const [pError, setPError] = useState<string | null>(null)
  const [trend, setTrend] = useState<TrendAnalyseResponse | null>(null)
  const [wp, setWp] = useState<WaermepumpeDashboardResponse[] | null>(null) // data-gated WP-Aussicht (langfristig)
  const [finanz, setFinanz] = useState<FinanzPrognose | null>(null) // Vorwärts-€-Teaser (D2), horizont-unabhängig
  const [loading, setLoading] = useState(true)
  const [reloading, setReloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const setHorizont = (h: Horizont) => {
    const next = new URLSearchParams(searchParams)
    next.set('h', h)
    setSearchParams(next, { replace: true })
  }

  const hatKoordinaten = !!(selectedAnlage?.latitude && selectedAnlage?.longitude)

  const laden = useCallback(async (silent = false) => {
    if (!anlageId) return
    const reqId = anlageId
    silent ? setReloading(true) : setLoading(true)
    setError(null)
    try {
      // Vorwärts-Finanz-Teaser (D2) — horizont-unabhängig (Jahresprognose),
      // Backend-Aggregat (ADR-001). Soft-fail: kein Teaser statt Sicht-Fehler.
      const finanzP = aussichtenApi.getFinanzPrognose(reqId, 12).catch(() => null)
      if (horizont === 'lang') {
        const [l, t, w, f] = await Promise.all([
          aussichtenApi.getLangfristPrognose(reqId, 12),
          aussichtenApi.getTrendAnalyse(reqId, 5).catch(() => null),
          investitionenApi.getWaermepumpeDashboard(reqId).catch(() => []),
          finanzP,
        ])
        setLang(l); setTrend(t); setWp(w); setFinanz(f)
      } else {
        // Stunden-Prognose-Block lädt seine Daten selbst (EnergieprofilPrognose).
        // `getPrognosenVergleich` liefert den kanonischen eedc-„Heute"-Wert (R8-4);
        // Soft-fail → Fallback auf den puren SolarPrognose-Wert, kein Sicht-Fehler.
        const [k, v, f] = await Promise.all([
          wetterApi.getSolarPrognose(reqId, KURZ_TAGE, false),
          aussichtenApi.getPrognosenVergleich(reqId).catch(() => null),
          finanzP,
        ])
        setKurz(k); setEedcHeute(v?.eedc_heute_kwh ?? null); setFinanz(f)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Laden der Aussicht')
    } finally {
      silent ? setReloading(false) : setLoading(false)
    }
  }, [anlageId, horizont])

  // D11-9: Horizont-Wechsel (kurz↔lang) soll NICHT den Voll-Spinner zeigen — sonst
  // flackert die ganze Sicht. Nur beim echten Anlagenwechsel/Erstladen voll laden;
  // bei reinem Horizont-Wechsel still nachladen (Kopf bleibt, Daten tauschen).
  const geladenFuer = useRef<number | null>(null)
  useEffect(() => {
    if (!anlageId || !hatKoordinaten) { setLoading(false); return }
    const silent = geladenFuer.current === anlageId
    geladenFuer.current = anlageId
    laden(silent)
  }, [anlageId, hatKoordinaten, laden])

  // Tagesprognose laden (nur Kurzfristig; Stunden-Chart + Stundenwerte teilen sie).
  useEffect(() => {
    if (!anlageId || !hatKoordinaten || !istKurz) return
    let ab = false
    setPError(null)
    energieProfilApi.getTagesprognose(anlageId, pDatum)
      .then((d) => { if (!ab) { setPDaten(d); setPError(null) } })
      .catch((err) => { if (!ab) { setPDaten(null); setPError(err?.response?.data?.detail || err?.message || 'Fehler beim Laden der Tagesprognose') } })
    return () => { ab = true }
  }, [anlageId, hatKoordinaten, istKurz, pDatum])

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
    const kennzahlenBlock = (items: KpiStripItem[], summary: string): Block | null => {
      const mit = items.map((k) => ({ ...k, parkId: `kpi:${k.title.toLowerCase().replace(/[^a-z0-9]+/gi, '-')}` }))
      const sichtbar = mit.filter((k) => !park.istGeparkt(k.parkId!))
      if (!sichtbar.length) return null
      return {
        id: 'kpi', title: 'Kennzahlen', ...BLOCK_IDENTITAET.kennzahlen,
        summary, defaultOpen: true, render: () => <KpiStrip kpis={sichtbar} />,
      }
    }
    if (istKurz) {
      if (!kurz) return []
      const kpi = kennzahlenBlock(kurzKpis(kurz, eedcHeute), `${fmtZahl(kurz.summe_kwh, 0)} kWh in ${kurz.tage.length} Tagen · Ø ${fmtZahl(kurz.durchschnitt_kwh_tag, 1)} kWh/Tag`)
      // Aussicht-Anzeigen sind einzeln parkbar (Doktrin): render in `Parkbar`, und ist
      // die Anzeige geparkt → ganzer Block weg (wie Cockpit/Monat-Verlauf).
      const list: Block[] = [
        ...(kpi ? [kpi] : []),
        ...(park.istGeparkt('el:aussicht-tages') ? [] : [{
          id: 'verlauf', title: 'Tages-Prognose', ...BLOCK_IDENTITAET.wetter,
          summary: `${kurz.tage.length} Tage: Wetter, Temperatur & PV-Ertrag je Tag`,
          defaultOpen: true,
          render: () => <Parkbar id="el:aussicht-tages" titel="Tages-Prognose"><TagesPrognose tage={kurz.tage} /></Parkbar>,
        }]),
        ...(park.istGeparkt('el:aussicht-tage-tabelle') ? [] : [{
          id: 'details', title: `${kurz.tage.length}-Tage-Tabelle`, ...BLOCK_IDENTITAET.werte,
          summary: 'VM/NM · GTI · Bewölkung · Temp · Niederschlag · Quelle',
          defaultOpen: false,
          render: () => <Parkbar id="el:aussicht-tage-tabelle" titel={`${kurz.tage.length}-Tage-Tabelle`}><KurzfristDetails tage={kurz.tage} /></Parkbar>,
        }]),
        // Stunden-Ebene (1 Tag): Chart + Tabelle als GETRENNTE Blöcke, eine Quelle.
        // Datum-Picker = Chrome (bleibt), nur der Chart ist die parkbare Anzeige →
        // geparkt entfällt der ganze Stunden-Block (Picker ohne Chart sinnlos).
        ...(park.istGeparkt('el:aussicht-stunden') ? [] : [{
          id: 'stunden', title: 'Stunden-Prognose', ...BLOCK_IDENTITAET.verlauf,
          summary: 'PV + Verbrauch + Speicher je Stunde (wählbarer Tag)',
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
          id: 'stundenwerte', title: 'Stundenwerte', ...BLOCK_IDENTITAET.werte,
          summary: 'Stundenprognose in kW · Summenzeile = kWh/Tag',
          defaultOpen: false,
          render: () => (pDaten
            ? <Parkbar id="el:aussicht-stundenwerte" titel="Stundenwerte"><PrognoseTabelle daten={pDaten} ohneCaption /></Parkbar>
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
  }, [istKurz, kurz, eedcHeute, lang, trend, wp, finanz, pDatum, pDaten, pError, park])

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
          <ReloadButton onClick={() => laden(true)} loading={reloading} disabled={loading} />
        </div>
      </div>

      {!hatKoordinaten ? (
        // B8 (S15): handgerollter EmptyState-Zwilling → SoT (Texte + CTA unverändert).
        <OnboardingLeer
          icon={Sun}
          titel="Standort nicht konfiguriert"
          beschreibung="Für Prognosen werden die Koordinaten der Anlage benötigt. Bitte konfiguriere den Standort in den Anlagen-Einstellungen."
          ctaHref="#/v4/einstellungen/stammdaten"
          ctaLabel="Anlage konfigurieren"
        />
      ) : error ? (
        // B8-Fehler-Baustein (S15): laden(false) = nicht-silent → Lade-Zustand statt
        // Leer-Flash während des Retrys (laden setzt setError(null) selbst).
        <FehlerZustand text={error} onRetry={() => laden(false)} />
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
