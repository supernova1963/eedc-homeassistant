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
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Zap, Sun, CloudSun, TrendingUp, TrendingDown, Minus, Info, RefreshCw, ArrowRight,
} from 'lucide-react'
import { Card, LoadingSpinner, buttonClasses } from '../components/ui'
import { BlockShell, KpiStrip, type Block, type KpiStripItem } from '../components/blocks'
import { ParkProvider, ParkFuss, usePark } from '../components/park'
import { BLOCK_IDENTITAET, fmtZahl } from '../lib'
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
  return [
    { title: `Summe ${p.tage.length} Tage`, value: fmtZahl(p.summe_kwh, 0), unit: 'kWh', color: 'yellow', icon: Zap },
    { title: 'Durchschnitt/Tag', value: fmtZahl(p.durchschnitt_kwh_tag, 1), unit: 'kWh', color: 'blue', icon: Sun },
    { title: 'Heute', value: fmtZahl(eedcHeute ?? heute?.pv_ertrag_kwh ?? 0, 1), unit: 'kWh', color: 'gray', icon: CloudSun, subtitle: vmNm(heute) },
    { title: 'Morgen', value: fmtZahl(morgen?.pv_ertrag_kwh ?? 0, 1), unit: 'kWh', color: 'gray', icon: CloudSun, subtitle: vmNm(morgen) },
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
    { title: 'Datenbasis', value: `${t.datenbasis_monate} Monate`, color: 'gray', icon: Info },
  ]
}

// Datum-Picker für die Tages-Stundenprognose (Heute/Morgen-Shortcuts + bis +14 T).
function StundenDatumPicker({ datum, setDatum }: { datum: string; setDatum: (d: string) => void }) {
  const btn = (aktiv: boolean) =>
    `px-2 py-1 text-xs rounded font-medium transition-colors ${
      aktiv ? 'bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300'
        : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
    }`
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Prognose für:</label>
      <input
        type="date" aria-label="Prognose-Datum" value={datum}
        min={heuteISO()} max={maxPrognoseDatum()}
        onChange={(e) => setDatum(e.target.value)}
        className="input w-auto text-sm"
      />
      <button type="button" onClick={() => setDatum(heuteISO())} className={btn(datum === heuteISO())}>Heute</button>
      <button type="button" onClick={() => setDatum(morgenISO())} className={btn(datum === morgenISO())}>Morgen</button>
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

  useEffect(() => {
    if (!anlageId || !hatKoordinaten) { setLoading(false); return }
    laden(false)
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
    const finanzTeaser: Block | null = finanz ? {
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
      const list: Block[] = [
        ...(kpi ? [kpi] : []),
        {
          id: 'verlauf', title: 'Tages-Prognose', ...BLOCK_IDENTITAET.wetter,
          summary: `${kurz.tage.length} Tage: Wetter, Temperatur & PV-Ertrag je Tag`,
          defaultOpen: true,
          render: () => <TagesPrognose tage={kurz.tage} />,
        },
        {
          id: 'details', title: `${kurz.tage.length}-Tage-Tabelle`, ...BLOCK_IDENTITAET.werte,
          summary: 'VM/NM · GTI · Bewölkung · Temp · Niederschlag · Quelle',
          defaultOpen: false,
          render: () => <KurzfristDetails tage={kurz.tage} />,
        },
        // Stunden-Ebene (1 Tag): Chart + Tabelle als GETRENNTE Blöcke, eine Quelle.
        {
          id: 'stunden', title: 'Stunden-Prognose', ...BLOCK_IDENTITAET.verlauf,
          summary: 'PV + Verbrauch + Speicher je Stunde (wählbarer Tag)',
          defaultOpen: false,
          render: () => (
            <div className="space-y-4">
              <StundenDatumPicker datum={pDatum} setDatum={setPDatum} />
              {pError
                ? <p className="text-sm text-amber-600 dark:text-amber-400">{pError}</p>
                : pDaten ? <PrognoseChartKarte daten={pDaten} />
                : <p className="text-sm text-gray-500 dark:text-gray-400">Lade Tagesprognose…</p>}
            </div>
          ),
        },
        {
          id: 'stundenwerte', title: 'Stundenwerte', ...BLOCK_IDENTITAET.werte,
          summary: 'Stundenprognose in kW · Summenzeile = kWh/Tag',
          defaultOpen: false,
          render: () => (pDaten
            ? <PrognoseTabelle daten={pDaten} />
            : <p className="text-sm text-gray-500 dark:text-gray-400">{pError ?? 'Lade Tagesprognose…'}</p>),
        },
      ]
      if (finanzTeaser) list.push(finanzTeaser)
      return list
    }
    // 12 Monate
    if (!lang) return []
    const kpiLang = kennzahlenBlock(langKpis(lang), `${lang.jahresprognose_kwh.toLocaleString('de-DE')} kWh Jahresprognose`)
    const list: Block[] = [
      ...(kpiLang ? [kpiLang] : []),
      {
        id: 'verlauf', title: 'Monats-Prognose', ...BLOCK_IDENTITAET.verlauf,
        summary: 'PVGIS vs. Trend-korrigiert + Konfidenzband',
        defaultOpen: true,
        render: () => <LangfristVerlaufChart prognose={lang} />,
      },
      {
        id: 'monatswerte', title: 'Monatswerte', ...BLOCK_IDENTITAET.werte,
        summary: 'PVGIS · Trend-korrigiert · Min/Max · Hist. PR + Gesamt',
        defaultOpen: false,
        render: () => <LangfristMonatswerte prognose={lang} />,
      },
      {
        id: 'saison', title: 'Saisonale Muster', ...BLOCK_IDENTITAET.saison,
        summary: trend ? `Beste: ${trend.saisonale_muster.beste_monate.slice(0, 2).join(', ')}` : 'Beste / schwächste Monate',
        defaultOpen: false,
        render: () => (trend
          ? <SaisonMuster muster={trend.saisonale_muster} />
          : <p className="text-sm text-gray-500 dark:text-gray-400">Noch keine saisonalen Muster verfügbar.</p>),
      },
    ]
    if (trend) {
      const grad = trend.degradation.geschaetzt_prozent_jahr
      list.push({
        id: 'degradation', title: 'Degradations-Prognose', ...BLOCK_IDENTITAET.degradation,
        summary: grad == null ? 'noch nicht bewertbar' : grad === 0 ? 'keine messbar' : `${fmtZahl(grad, 1)} % / Jahr`,
        defaultOpen: false,
        render: () => <DegradationsPrognose trend={trend} />,
      })
    }
    // WP-Aussicht — data-gated (nur wenn die Anlage eine WP hat); Komponenten-
    // Temporales lebt in Cockpit/Aussicht (21.06.-Regel), nicht im Hub.
    if (wp && wp.length > 0) {
      list.push({
        id: 'wp-aussicht', title: 'Wärmepumpe — Ausblick', ...BLOCK_IDENTITAET.wpAussicht,
        summary: 'Effizienz-Trend (JAZ) + erwartete Heizsaison',
        defaultOpen: false,
        render: () => <WpAussicht wpDashboards={wp} />,
      })
    }
    if (finanzTeaser) list.push(finanzTeaser)
    return list
  }, [istKurz, kurz, eedcHeute, lang, trend, wp, finanz, anlageId, pDatum, pDaten, pError, park])

  if (!anlageId) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage gewählt.</p></Card>
      </div>
    )
  }

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      {/* L-Header: Titel · Horizont-Selektor · Datenquelle · Reload */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-lg font-bold text-gray-900 dark:text-white">Aussicht</h1>
          {/* Horizont-Selektor (segmented control, URL-linkbar ?h=) */}
          <div className="inline-flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
            {HORIZONTE.map((h) => (
              <button
                key={h.key}
                type="button"
                onClick={() => setHorizont(h.key)}
                aria-pressed={horizont === h.key}
                className={`text-xs px-3 py-1.5 font-medium transition-colors ${
                  horizont === h.key
                    ? 'bg-primary-600 text-white'
                    : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                {h.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => laden(true)}
            disabled={reloading || loading}
            className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${reloading ? 'animate-spin' : ''}`} />
            Aktualisieren
          </button>
        </div>
      </div>

      {!hatKoordinaten ? (
        <Card className="text-center py-12">
          <Sun className="h-12 w-12 mx-auto text-yellow-500 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">Standort nicht konfiguriert</h3>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Für Prognosen werden die Koordinaten der Anlage benötigt. Bitte konfiguriere den Standort in den Anlagen-Einstellungen.
          </p>
          <a href="#/einstellungen/anlage" className={buttonClasses({ variant: 'primary', size: 'sm', className: 'gap-1.5' })}>
            Anlage konfigurieren <ArrowRight className="h-4 w-4" />
          </a>
        </Card>
      ) : error ? (
        <Card><p className="text-red-500">{error}</p></Card>
      ) : loading ? (
        <LoadingSpinner text="Lade Aussicht…" />
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
