/**
 * Community-Übersicht — geteilte Teile (Daten-Hook + Präsentations-Sektionen).
 *
 * EINE Code-Wahrheit für die IST-Seite (`UebersichtTab`) und die IA-V4-Sicht
 * (`CommunityUebersichtV4` als Blöcke). Reine Darstellung, kein Daten-Laden, KEINE
 * äußere Card/Block-Hülle (die wickelt der Aufrufer: IST = `<Card>`, V4 = BlockShell).
 * Zahlen de-DE (`fmtZahl`); Farben aus der Zentrale (`lib`), kein Inline-Hex.
 */
import { useMemo } from 'react'
import {
  Trophy, Battery, Home, Car, Plug, Sun, TrendingUp, TrendingDown, MapPin,
  BarChart3, Award, ThumbsUp, ThumbsDown, Zap, Medal, Flame, Target, Shield, HelpCircle,
} from 'lucide-react'
import { Card, ChartLegende } from '../../components/ui'
import { Parkbar } from '../../components/park'
import { SimpleTooltip } from '../../components/ui/FormelTooltip'
import { useChartTheme } from '../../context/ThemeContext'
import { useLegendenToggle } from '../../hooks'
import type { CommunityBenchmarkResponse, KPIVergleich } from '../../api/community'
import {
  ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Legend,
} from 'recharts'
import { REGION_NAMEN, EIGENE_SERIE_FARBEN, SERIEN_PALETTE, ACHSEN_TICK, fmtZahl } from '../../lib'
import { hatJahresfenster, jahresfensterHinweis, jahresfensterStand } from '../../lib/communityFenster'

// Element-Park (IA-V4, Element-Park-Doktrin Gernot 2026-06-27): JEDE Anzeige
// (KPI/Vergleichs-Karte, Chart, Liste, Achievement, Komponenten-Karte) ist einzeln
// parkbar. `Parkbar` ist OHNE ParkProvider inert → der IST-`UebersichtTab` (v3, kein
// Provider) bleibt optisch identisch; nur die V4-Sicht aktiviert die Geste. IDs
// view-eindeutig (Prefix `ueb-`, persistKey 'v4-community-uebersicht'); der V4-Builder
// blendet einen Block aus, wenn ALLE seine Element-IDs geparkt sind (alleGeparkt).
//
// Statische Blöcke: feste ID-Liste in UEB_PARK_IDS. Blöcke mit datenabhängiger
// Elementmenge (Achievements, Komponenten-Benchmarks) liefern ihre IDs per Funktion
// (uebAchievementParkIds / uebKomponentenParkIds) — exakt die IDs, die die Sektion
// auch rendert (gleiche Slugs/Bedingungen).
export const UEB_PARK_IDS = {
  ranking: [
    'ueb-ranking-hero',
    'ueb-ranking-community',
    'ueb-ranking-region',
    'ueb-ranking-rang-gesamt',
    'ueb-ranking-rang-region',
  ],
  profil: ['ueb-radar'],
} as const
// Performance-IDs (Stärken/Schwächen) sind datenabhängig → NICHT in UEB_PARK_IDS:
// {@link StaerkenSchwaechen} rendert `ueb-staerken` nur bei ≥1 Stärke, `ueb-schwaechen`
// nur bei ≥1 Schwäche. Die feste Liste hätte bei „3 Stärken · 0 Potenzial" ein nie
// existierendes `ueb-schwaechen` verlangt → `alleGeparkt` nie true → leerer Block blieb
// (Gernot 2026-07-09). Der Aufrufer leitet sie inline aus staerken/schwaechen ab (kein
// weiterer Nicht-Komponenten-Export in dieser .tsx → react-refresh/lint Δ0).

/** Element-IDs der Achievements-Sektion — genau die, die {@link AchievementsBlock}
 *  rendert (erreichte + bis zu 4 nicht erreichte; Slug = Achievement-ID). */
export function uebAchievementParkIds(achievements: UebersichtDaten['achievements']): string[] {
  return [
    ...achievements.erreichte.map((a) => `ueb-ach-${a.id}`),
    ...achievements.nichtErreichte.slice(0, 4).map((a) => `ueb-ach-${a.id}`),
  ]
}

const KOMP_SLUG = {
  speicher: 'speicher', balkonkraftwerk: 'bkw', waermepumpe: 'wp', wallbox: 'wallbox', eauto: 'eauto',
} as const

/** Element-IDs der Komponenten-Benchmarks — genau die Karten, die
 *  {@link KomponentenBenchmarks} unter denselben Bedingungen rendert. */
export function uebKomponentenParkIds(benchmark: CommunityBenchmarkResponse): string[] {
  const e = benchmark.benchmark_erweitert
  if (!e) return []
  const a = benchmark.anlage
  const ids: string[] = []
  if (e.speicher && a.speicher_kwh) ids.push(`ueb-komp-${KOMP_SLUG.speicher}`)
  if (e.balkonkraftwerk && a.hat_balkonkraftwerk) ids.push(`ueb-komp-${KOMP_SLUG.balkonkraftwerk}`)
  if (e.waermepumpe && a.hat_waermepumpe) ids.push(`ueb-komp-${KOMP_SLUG.waermepumpe}`)
  if (e.wallbox && a.hat_wallbox) ids.push(`ueb-komp-${KOMP_SLUG.wallbox}`)
  if (e.eauto && a.hat_eauto) ids.push(`ueb-komp-${KOMP_SLUG.eauto}`)
  return ids
}

// ─── Typen ────────────────────────────────────────────────────────────────────

interface PerformanceMetrik {
  label: string
  abweichungProzent: number
  einheit: '%' | 'PP'  // PP = Prozentpunkte (für Metriken die selbst % sind)
  icon: React.ReactNode
  kategorie: 'pv' | 'speicher' | 'waermepumpe' | 'eauto' | 'wallbox'
}

interface Achievement {
  id: string
  name: string
  beschreibung: string
  icon: React.ReactNode
  farbe: string
  erreicht: boolean
  fortschritt?: number // 0-100 für teilweise erreichte
}

const ACHIEVEMENT_DEFINITIONEN = {
  solarprofi:       { name: 'Solarprofi',        beschreibung: 'Top 10% beim spezifischen Ertrag',        icon: <Sun className="h-5 w-5" />,    farbe: 'yellow' },
  autarkiemeister:  { name: 'Autarkiemeister',   beschreibung: 'Autarkiegrad über 80%',                   icon: <Shield className="h-5 w-5" />, farbe: 'green' },
  effizienzwunder:  { name: 'Effizienzwunder',   beschreibung: 'Speicher-Wirkungsgrad über 90%',          icon: <Battery className="h-5 w-5" />, farbe: 'emerald' },
  waermekoenig:     { name: 'Wärmekönig',        beschreibung: 'Wärmepumpe JAZ über 4.0',                 icon: <Home className="h-5 w-5" />,   farbe: 'blue' },
  gruenerfahrer:    { name: 'Grüner Fahrer',     beschreibung: 'E-Auto PV-Ladeanteil über 70%',           icon: <Car className="h-5 w-5" />,    farbe: 'purple' },
  regionalchampion: { name: 'Regionalchampion',  beschreibung: 'Top 3 in deiner Region',                  icon: <MapPin className="h-5 w-5" />, farbe: 'cyan' },
  dauerbrenner:     { name: 'Dauerbrenner',      beschreibung: '12 Monate in Folge über Durchschnitt',    icon: <Flame className="h-5 w-5" />,  farbe: 'orange' },
  perfektionist:    { name: 'Perfektionist',     beschreibung: 'Alle Komponenten über Community-Durchschnitt', icon: <Target className="h-5 w-5" />, farbe: 'indigo' },
}

// ─── Reihenfolge der Monatswerte (F-25, #375 kingcap1 2026-08-11) ────────────
// `anlage.monatswerte` kommt vom Community-Server **absteigend**
// (`benchmark.py`: `order_by(jahr.desc(), monat.desc())`) — der neueste Monat
// steht auf Position 0. Die Übersicht las ihn als `[length - 1]` und zeigte
// damit den **ältesten** Monat: Autarkie 100 % im Cockpit gegen ~5 % im Radar,
// weil der erste eingereichte Monat ein Wintermonat war.
//
// ⚠ Die Falle ist die **gleichnamige zweite Quelle**: die Teilen-Vorschau
// (`/community/preview/{id}`, eedc-eigenes Backend) liefert dieselbe Feldliste
// **aufsteigend** — `CommunityShareBlock.letzterWert` iteriert deshalb zu Recht
// von hinten. Zwei Quellen, ein Feldname, gegenläufige Reihenfolge.
//
// Deshalb hier nicht „richtig herum indizieren", sondern **sortieren**: die
// Helfer gelten für beide Reihenfolgen und überleben eine Änderung an der
// Server-Query. (`CommunityPVErtragTeile`/`CommunityTrendsTeile` machen das
// seit jeher so und waren nie betroffen.)
type MonatsZeile = { jahr: number; monat: number }

function chronologisch<T extends MonatsZeile>(monatswerte: readonly T[] | undefined): T[] {
  return [...(monatswerte ?? [])].sort((a, b) => a.jahr - b.jahr || a.monat - b.monat)
}

export function neuesterMonat<T extends MonatsZeile>(monatswerte: readonly T[] | undefined): T | undefined {
  const sortiert = chronologisch(monatswerte)
  return sortiert[sortiert.length - 1]
}

export function letzteMonate<T extends MonatsZeile>(monatswerte: readonly T[] | undefined, anzahl: number): T[] {
  return chronologisch(monatswerte).slice(-anzahl)
}

export interface UebersichtDaten {
  rankingBadge: { label: string; color: string; textColor: string } | null
  achievements: { erreichte: Achievement[]; nichtErreichte: Achievement[] }
  staerken: PerformanceMetrik[]
  schwaechen: PerformanceMetrik[]
  radarData: { kategorie: string; du: number; community: number; fullMark: number }[]
}

// ─── Daten-Hook (SoT der Übersicht-Ableitungen) ──────────────────────────────

export function useUebersichtDaten(benchmark: CommunityBenchmarkResponse | null): UebersichtDaten {
  const rankingBadge = useMemo(() => {
    if (!benchmark) return null
    const { rang_gesamt, anzahl_anlagen_gesamt } = benchmark.benchmark
    // #387: ohne volles 12-Monats-Fenster gibt es keinen Rang — und damit auch
    // kein Abzeichen. Vorher lieferte der Server hier ersatzweise Rang 1.
    if (rang_gesamt === null || rang_gesamt === undefined || !anzahl_anlagen_gesamt) return null
    const prozent = (rang_gesamt / anzahl_anlagen_gesamt) * 100
    if (prozent <= 10) return { label: 'Top 10%', color: 'bg-yellow-500', textColor: 'text-yellow-500' }
    if (prozent <= 25) return { label: 'Top 25%', color: 'bg-gray-400', textColor: 'text-gray-500' }
    if (prozent <= 50) return { label: 'Top 50%', color: 'bg-amber-700', textColor: 'text-amber-700' }
    return null
  }, [benchmark])

  const achievements = useMemo((): { erreichte: Achievement[]; nichtErreichte: Achievement[] } => {
    if (!benchmark) return { erreichte: [], nichtErreichte: [] }
    const erreichte: Achievement[] = []
    const nichtErreichte: Achievement[] = []
    const { rang_gesamt, anzahl_anlagen_gesamt, rang_region, anzahl_anlagen_region } = benchmark.benchmark

    // #387: Beide Auszeichnungen hängen am Rang. Ohne volles Jahresfenster gibt
    // es keinen — dann wird die Auszeichnung weggelassen statt mit einem
    // erfundenen Fortschritt angezeigt.
    if (rang_gesamt !== null && rang_gesamt !== undefined && anzahl_anlagen_gesamt) {
      const perzentilGesamt = (rang_gesamt / anzahl_anlagen_gesamt) * 100
      const solarprofiErreicht = perzentilGesamt <= 10
      const solarprofi: Achievement = { id: 'solarprofi', ...ACHIEVEMENT_DEFINITIONEN.solarprofi, erreicht: solarprofiErreicht, fortschritt: solarprofiErreicht ? 100 : Math.max(0, 100 - perzentilGesamt) }
      ;(solarprofiErreicht ? erreichte : nichtErreichte).push(solarprofi)
    }

    if (rang_region !== null && rang_region !== undefined) {
      const regionalchampionErreicht = rang_region <= 3
      const regionalchampion: Achievement = { id: 'regionalchampion', ...ACHIEVEMENT_DEFINITIONEN.regionalchampion, erreicht: regionalchampionErreicht, fortschritt: regionalchampionErreicht ? 100 : Math.max(0, (1 - rang_region / Math.min(10, anzahl_anlagen_region)) * 100) }
      ;(regionalchampionErreicht ? erreichte : nichtErreichte).push(regionalchampion)
    }

    const letzterMonat = neuesterMonat(benchmark.anlage.monatswerte)
    if (letzterMonat?.autarkie_prozent !== undefined && letzterMonat.autarkie_prozent !== null) {
      const autarkieErreicht = letzterMonat.autarkie_prozent >= 80
      ;(autarkieErreicht ? erreichte : nichtErreichte).push({ id: 'autarkiemeister', ...ACHIEVEMENT_DEFINITIONEN.autarkiemeister, erreicht: autarkieErreicht, fortschritt: autarkieErreicht ? 100 : (letzterMonat.autarkie_prozent / 80) * 100 })
    }

    const speicher = benchmark.benchmark_erweitert?.speicher
    if (speicher?.wirkungsgrad) {
      const effizienzErreicht = speicher.wirkungsgrad.wert >= 90
      ;(effizienzErreicht ? erreichte : nichtErreichte).push({ id: 'effizienzwunder', ...ACHIEVEMENT_DEFINITIONEN.effizienzwunder, erreicht: effizienzErreicht, fortschritt: effizienzErreicht ? 100 : (speicher.wirkungsgrad.wert / 90) * 100 })
    }

    const wp = benchmark.benchmark_erweitert?.waermepumpe
    if (wp?.jaz) {
      const jazErreicht = wp.jaz.wert >= 4.0
      ;(jazErreicht ? erreichte : nichtErreichte).push({ id: 'waermekoenig', ...ACHIEVEMENT_DEFINITIONEN.waermekoenig, erreicht: jazErreicht, fortschritt: jazErreicht ? 100 : (wp.jaz.wert / 4.0) * 100 })
    }

    const eauto = benchmark.benchmark_erweitert?.eauto
    if (eauto?.pv_anteil) {
      const pvAnteilErreicht = eauto.pv_anteil.wert >= 70
      ;(pvAnteilErreicht ? erreichte : nichtErreichte).push({ id: 'gruenerfahrer', ...ACHIEVEMENT_DEFINITIONEN.gruenerfahrer, erreicht: pvAnteilErreicht, fortschritt: pvAnteilErreicht ? 100 : (eauto.pv_anteil.wert / 70) * 100 })
    }

    const letzteZwoelf = letzteMonate(benchmark.anlage.monatswerte, 12)
    // #387: Die Schwelle ist ein Zwölftel des Community-Jahreswerts. Fehlt der,
    // gibt es keine Schwelle — und damit auch keine Auszeichnung.
    const durchschnittMonat = (benchmark.benchmark.spez_ertrag_durchschnitt ?? 0) / 12
    if (!durchschnittMonat) return { erreichte, nichtErreichte }
    let ueberDurchschnittCount = 0
    for (const m of letzteZwoelf) if ((m.spez_ertrag_kwh_kwp || 0) > durchschnittMonat) ueberDurchschnittCount++
    const dauerbrennerErreicht = ueberDurchschnittCount === 12 && letzteZwoelf.length === 12
    const dauerbrenner: Achievement = { id: 'dauerbrenner', ...ACHIEVEMENT_DEFINITIONEN.dauerbrenner, erreicht: dauerbrennerErreicht, fortschritt: letzteZwoelf.length > 0 ? (ueberDurchschnittCount / Math.max(12, letzteZwoelf.length)) * 100 : 0 }
    if (dauerbrennerErreicht) erreichte.push(dauerbrenner)
    else if (letzteZwoelf.length >= 6) nichtErreichte.push(dauerbrenner)

    return { erreichte, nichtErreichte }
  }, [benchmark])

  const { staerken, schwaechen } = useMemo(() => {
    if (!benchmark) return { staerken: [] as PerformanceMetrik[], schwaechen: [] as PerformanceMetrik[] }
    const metriken: PerformanceMetrik[] = []

    // #387: Quotient aus zwei Jahreswerten — fehlt einer, wird er unterdrückt
    // statt geschätzt (Doktrin unvollständiger Werte).
    const eigenerJahreswert = benchmark.benchmark.spez_ertrag_anlage
    const communityJahreswert = benchmark.benchmark.spez_ertrag_durchschnitt
    if (eigenerJahreswert !== null && eigenerJahreswert !== undefined && communityJahreswert) {
      const pvAbw = ((eigenerJahreswert - communityJahreswert) / communityJahreswert) * 100
      metriken.push({ label: 'PV-Ertrag', abweichungProzent: pvAbw, einheit: '%', icon: <Sun className="h-4 w-4" />, kategorie: 'pv' })
    }

    if (benchmark.benchmark_erweitert?.speicher) {
      const sp = benchmark.benchmark_erweitert.speicher
      if (sp.wirkungsgrad?.community_avg) metriken.push({ label: 'Speicher-Effizienz', abweichungProzent: sp.wirkungsgrad.wert - sp.wirkungsgrad.community_avg, einheit: 'PP', icon: <Battery className="h-4 w-4" />, kategorie: 'speicher' })
      if (sp.netz_anteil?.community_avg) metriken.push({ label: 'PV-Ladeanteil Speicher', abweichungProzent: sp.netz_anteil.community_avg - sp.netz_anteil.wert, einheit: 'PP', icon: <Zap className="h-4 w-4" />, kategorie: 'speicher' })
    }

    {
      const wp = benchmark.benchmark_erweitert?.waermepumpe
      const vergleich = wp?.jaz_typ?.community_avg ? wp.jaz_typ : wp?.jaz?.community_avg ? wp.jaz : null
      if (wp && vergleich?.community_avg) {
        const abw = ((vergleich.wert - vergleich.community_avg) / vergleich.community_avg) * 100
        const wpArt = wp.wp_art ?? benchmark.anlage.wp_art
        const wpArtLabel = wpArt === 'luft_wasser' ? ' (Luft/Wasser)' : wpArt === 'sole_wasser' ? ' (Sole/Wasser)' : wpArt === 'grundwasser' ? ' (Grundwasser)' : wpArt === 'luft_luft' ? ' (Luft/Luft)' : ''
        metriken.push({ label: `WP JAZ${wpArtLabel}`, abweichungProzent: abw, einheit: '%', icon: <Home className="h-4 w-4" />, kategorie: 'waermepumpe' })
      }
    }

    if (benchmark.benchmark_erweitert?.wallbox?.pv_anteil?.community_avg) {
      const wb = benchmark.benchmark_erweitert.wallbox
      metriken.push({ label: 'Wallbox PV-Anteil', abweichungProzent: wb.pv_anteil!.wert - wb.pv_anteil!.community_avg!, einheit: 'PP', icon: <Plug className="h-4 w-4" />, kategorie: 'wallbox' })
    }

    if (benchmark.benchmark_erweitert?.eauto?.pv_anteil?.community_avg) {
      const ea = benchmark.benchmark_erweitert.eauto
      metriken.push({ label: 'E-Auto PV-Anteil', abweichungProzent: ea.pv_anteil!.wert - ea.pv_anteil!.community_avg!, einheit: 'PP', icon: <Car className="h-4 w-4" />, kategorie: 'eauto' })
    }

    const sortiert = [...metriken].sort((a, b) => b.abweichungProzent - a.abweichungProzent)
    return {
      staerken: sortiert.filter((m) => m.abweichungProzent > 0).slice(0, 3),
      schwaechen: sortiert.filter((m) => m.abweichungProzent < 0).slice(-3).reverse(),
    }
  }, [benchmark])

  const radarData = useMemo(() => {
    if (!benchmark) return []
    const data: { kategorie: string; du: number; community: number; fullMark: number }[] = []
    const pvEigen = benchmark.benchmark.spez_ertrag_anlage
    const pvCommunity = benchmark.benchmark.spez_ertrag_durchschnitt
    if (pvEigen !== null && pvEigen !== undefined && pvCommunity) {
      const pvMax = Math.max(pvEigen, pvCommunity) * 1.2
      data.push({ kategorie: 'PV-Ertrag', du: (pvEigen / pvMax) * 100, community: (pvCommunity / pvMax) * 100, fullMark: 100 })
    }
    const letzterMonat = neuesterMonat(benchmark.anlage.monatswerte)
    if (letzterMonat?.autarkie_prozent) data.push({ kategorie: 'Autarkie', du: letzterMonat.autarkie_prozent, community: 65, fullMark: 100 })
    if (letzterMonat?.eigenverbrauch_prozent) data.push({ kategorie: 'Eigenverbrauch', du: letzterMonat.eigenverbrauch_prozent, community: 45, fullMark: 100 })
    if (benchmark.benchmark_erweitert?.speicher?.wirkungsgrad?.community_avg) {
      const sp = benchmark.benchmark_erweitert.speicher
      data.push({ kategorie: 'Speicher', du: sp.wirkungsgrad!.wert, community: sp.wirkungsgrad!.community_avg!, fullMark: 100 })
    }
    if (benchmark.benchmark_erweitert?.waermepumpe?.jaz?.community_avg) {
      const wp = benchmark.benchmark_erweitert.waermepumpe
      const jazMax = Math.max(wp.jaz!.wert, wp.jaz!.community_avg!) * 1.2
      data.push({ kategorie: 'WP-Effizienz', du: (wp.jaz!.wert / jazMax) * 100, community: (wp.jaz!.community_avg! / jazMax) * 100, fullMark: 100 })
    }
    if (benchmark.benchmark_erweitert?.eauto?.pv_anteil?.community_avg) {
      const ea = benchmark.benchmark_erweitert.eauto
      data.push({ kategorie: 'E-Auto PV', du: ea.pv_anteil!.wert, community: ea.pv_anteil!.community_avg!, fullMark: 100 })
    }
    return data
  }, [benchmark])

  return { rankingBadge, achievements, staerken, schwaechen, radarData }
}

// ─── Sektion: Ranking + Haupt-KPI ────────────────────────────────────────────

export function RankingHauptKpi({ benchmark, rankingBadge }: { benchmark: CommunityBenchmarkResponse; rankingBadge: UebersichtDaten['rankingBadge'] }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-6">
        {rankingBadge && (
          <span className={`px-3 py-1 rounded-full text-white text-sm font-medium ${rankingBadge.color}`}>
            <Award className="h-4 w-4 inline mr-1" />{rankingBadge.label}
          </span>
        )}
        <span className="ml-auto text-sm text-gray-500 dark:text-gray-400">{benchmark.zeitraum_label}</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Parkbar id="ueb-ranking-hero" titel="Dein spez. Ertrag" className="text-center md:col-span-1">
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Dein spez. Ertrag</p>
          <p className="text-4xl font-bold text-primary-500">{fmtZahl(benchmark.benchmark.spez_ertrag_anlage, 0)}</p>
          <p className="text-gray-500 dark:text-gray-400">kWh/kWp</p>
          <AbweichungBadge wert={benchmark.benchmark.spez_ertrag_anlage} durchschnitt={benchmark.benchmark.spez_ertrag_durchschnitt} />
          {hatJahresfenster(benchmark.benchmark) && jahresfensterStand(benchmark.benchmark) && (
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{jahresfensterStand(benchmark.benchmark)}</p>
          )}
          {jahresfensterHinweis(benchmark.benchmark) && (
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">{jahresfensterHinweis(benchmark.benchmark)}</p>
          )}
        </Parkbar>
        <div className="md:col-span-2">
          <div className="grid grid-cols-2 gap-4">
            <Parkbar id="ueb-ranking-community" titel="Community Durchschnitt">
              <VergleichsBox label="Community Durchschnitt" wert={benchmark.benchmark.spez_ertrag_durchschnitt} einheit="kWh/kWp" icon={<BarChart3 className="h-5 w-5 text-gray-400 dark:text-gray-500" />} />
            </Parkbar>
            <Parkbar id="ueb-ranking-region" titel={REGION_NAMEN[benchmark.anlage.region] || benchmark.anlage.region}>
              <VergleichsBox label={REGION_NAMEN[benchmark.anlage.region] || benchmark.anlage.region} wert={benchmark.benchmark.spez_ertrag_region} einheit="kWh/kWp" icon={<MapPin className="h-5 w-5 text-blue-400" />} />
            </Parkbar>
            <Parkbar id="ueb-ranking-rang-gesamt" titel="Rang gesamt">
              <VergleichsBox label="Rang gesamt" wert={benchmark.benchmark.rang_gesamt} zusatz={`von ${benchmark.benchmark.anzahl_anlagen_gesamt}`} icon={<Trophy className="h-5 w-5 text-yellow-500" />} isRank />
            </Parkbar>
            <Parkbar id="ueb-ranking-rang-region" titel="Rang Region">
              <VergleichsBox label="Rang Region" wert={benchmark.benchmark.rang_region} zusatz={`von ${benchmark.benchmark.anzahl_anlagen_region}`} icon={<Trophy className="h-5 w-5 text-blue-500" />} isRank />
            </Parkbar>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Sektion: Stärken & Schwächen ────────────────────────────────────────────

export function StaerkenSchwaechen({ staerken, schwaechen }: { staerken: PerformanceMetrik[]; schwaechen: PerformanceMetrik[] }) {
  const zeile = (s: PerformanceMetrik, positiv: boolean) => (
    <div className={`flex items-center justify-between rounded-lg px-3 py-2 ${positiv ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'}`}>
      <div className="flex items-center gap-2">{s.icon}<span className="text-gray-700 dark:text-gray-300">{s.label}</span></div>
      <span className={`font-semibold ${positiv ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
        {positiv ? '+' : ''}{fmtZahl(s.abweichungProzent, 1)}{s.einheit === 'PP' ? ' PP' : ' %'}
      </span>
    </div>
  )
  return (
    <div>
      {staerken.length > 0 && (
        <Parkbar id="ueb-staerken" titel="Stärken" className="block mb-4">
          <div className="flex items-center gap-2 mb-2"><ThumbsUp className="h-5 w-5 text-green-500" /><span className="font-medium text-gray-700 dark:text-gray-300">Stärken</span></div>
          <div className="space-y-2">{staerken.map((s, idx) => <div key={idx}>{zeile(s, true)}</div>)}</div>
        </Parkbar>
      )}
      {schwaechen.length > 0 && (
        <Parkbar id="ueb-schwaechen" titel="Verbesserungspotenzial">
          <div className="flex items-center gap-2 mb-2"><ThumbsDown className="h-5 w-5 text-red-500" /><span className="font-medium text-gray-700 dark:text-gray-300">Verbesserungspotenzial</span></div>
          <div className="space-y-2">{schwaechen.map((s, idx) => <div key={idx}>{zeile(s, false)}</div>)}</div>
        </Parkbar>
      )}
    </div>
  )
}

// ─── Sektion: Performance-Profil (Radar) ─────────────────────────────────────

export function PerformanceProfil({ radarData }: { radarData: UebersichtDaten['radarData'] }) {
  const achsen = useChartTheme()
  const legende = useLegendenToggle()
  return (
    <Parkbar id="ueb-radar" titel="Performance-Profil">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={radarData}>
            <PolarGrid stroke={achsen.grid} />
            <PolarAngleAxis dataKey="kategorie" tick={ACHSEN_TICK} />
            <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fill: achsen.referenz, fontSize: 10 }} />
            <Radar name="Du" dataKey="du" stroke={EIGENE_SERIE_FARBEN.du} fill={EIGENE_SERIE_FARBEN.du} fillOpacity={0.3} hide={legende.istVersteckt('du')} />
            <Radar name="Community" dataKey="community" stroke={SERIEN_PALETTE[0]} fill={SERIEN_PALETTE[0]} fillOpacity={0.15} hide={legende.istVersteckt('community')} />
            <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </Parkbar>
  )
}

// ─── Sektion: Achievements ───────────────────────────────────────────────────

export function AchievementsBlock({ achievements }: { achievements: UebersichtDaten['achievements'] }) {
  return (
    <div>
      {achievements.erreichte.length > 0 && (
        <div className="mb-4">
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
            Erreicht: {fmtZahl(achievements.erreichte.length, 0)} von {fmtZahl(achievements.erreichte.length + achievements.nichtErreichte.length, 0)}
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{achievements.erreichte.map((a) => (
            <Parkbar key={a.id} id={`ueb-ach-${a.id}`} titel={a.name}><AchievementBadge achievement={a} /></Parkbar>
          ))}</div>
        </div>
      )}
      {achievements.nichtErreichte.length > 0 && (
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">In Reichweite</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{achievements.nichtErreichte.slice(0, 4).map((a) => (
            <Parkbar key={a.id} id={`ueb-ach-${a.id}`} titel={a.name}><AchievementBadge achievement={a} /></Parkbar>
          ))}</div>
        </div>
      )}
    </div>
  )
}

// ─── Sektion: Komponenten-Benchmarks ─────────────────────────────────────────

export function KomponentenBenchmarks({ benchmark }: { benchmark: CommunityBenchmarkResponse }) {
  const e = benchmark.benchmark_erweitert
  if (!e) return null
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {e.speicher && benchmark.anlage.speicher_kwh && (
        <Parkbar id={`ueb-komp-${KOMP_SLUG.speicher}`} titel="Speicher">
          <KomponentenCard title="Speicher" icon={<Battery className="h-6 w-6 text-green-500" />} kapazitaet={`${fmtZahl(benchmark.anlage.speicher_kwh, 1)} kWh`}>
            <KPIRow label="Zyklen/Jahr" kpi={e.speicher.zyklen_jahr} einheit="" />
            <KPIRow label="Wirkungsgrad" kpi={e.speicher.wirkungsgrad} einheit="%" />
            <KPIRow label="Netzladung" kpi={e.speicher.netz_anteil} einheit="%" invertColors />
          </KomponentenCard>
        </Parkbar>
      )}
      {e.balkonkraftwerk && benchmark.anlage.hat_balkonkraftwerk && (
        <Parkbar id={`ueb-komp-${KOMP_SLUG.balkonkraftwerk}`} titel="Balkonkraftwerk">
          <KomponentenCard title="Balkonkraftwerk" icon={<Sun className="h-6 w-6 text-amber-500" />} kapazitaet={benchmark.anlage.bkw_wp ? `${fmtZahl(benchmark.anlage.bkw_wp, 0)} Wp` : undefined}>
            <KPIRow label="Spez. Ertrag" kpi={e.balkonkraftwerk.spez_ertrag} einheit="kWh/kWp" />
            <KPIRow label="Erzeugung" kpi={e.balkonkraftwerk.erzeugung} einheit="kWh" hideComparison />
            <KPIRow label="Eigenverbrauchsquote" kpi={e.balkonkraftwerk.eigenverbrauch} einheit="%" hideComparison />
          </KomponentenCard>
        </Parkbar>
      )}
      {e.waermepumpe && benchmark.anlage.hat_waermepumpe && (() => {
        const wp = e.waermepumpe
        const jazVergleich = wp.jaz_typ?.community_avg ? wp.jaz_typ : wp.jaz
        const wpArt = wp.wp_art ?? benchmark.anlage.wp_art
        const wpArtLabel = wpArt === 'luft_wasser' ? ' · Luft/Wasser' : wpArt === 'sole_wasser' ? ' · Sole/Wasser' : wpArt === 'grundwasser' ? ' · Grundwasser' : wpArt === 'luft_luft' ? ' · Luft/Luft' : ''
        return (
          <Parkbar id={`ueb-komp-${KOMP_SLUG.waermepumpe}`} titel="Wärmepumpe">
            <KomponentenCard title="Wärmepumpe" icon={<Home className="h-6 w-6 text-blue-500" />}>
              <KPIRow label={`JAZ${wpArtLabel}`} kpi={jazVergleich} einheit="" />
              <KPIRow label="Stromverbrauch" kpi={wp.stromverbrauch} einheit="kWh" hideComparison />
              <KPIRow label="Wärmeerzeugung" kpi={wp.waermeerzeugung} einheit="kWh" hideComparison />
            </KomponentenCard>
          </Parkbar>
        )
      })()}
      {e.wallbox && benchmark.anlage.hat_wallbox && (
        <Parkbar id={`ueb-komp-${KOMP_SLUG.wallbox}`} titel="Wallbox">
          <KomponentenCard title="Wallbox" icon={<Plug className="h-6 w-6 text-cyan-500" />} kapazitaet={benchmark.anlage.wallbox_kw ? `${fmtZahl(benchmark.anlage.wallbox_kw, 1)} kW` : undefined}>
            <KPIRow label="PV-Anteil Ladung" kpi={e.wallbox.pv_anteil} einheit="%" />
            <KPIRow label="Ladung gesamt" kpi={e.wallbox.ladung} einheit="kWh" hideComparison />
            <KPIRow label="Ladevorgänge" kpi={e.wallbox.ladevorgaenge} einheit="" hideComparison />
          </KomponentenCard>
        </Parkbar>
      )}
      {e.eauto && benchmark.anlage.hat_eauto && (
        <Parkbar id={`ueb-komp-${KOMP_SLUG.eauto}`} titel="E-Auto">
          <KomponentenCard title="E-Auto" icon={<Car className="h-6 w-6 text-purple-500" />}>
            <KPIRow label="PV-Anteil" kpi={e.eauto.pv_anteil} einheit="%" />
            <KPIRow label="Ladung gesamt" kpi={e.eauto.ladung_gesamt} einheit="kWh" hideComparison />
            <KPIRow label="Verbrauch" kpi={e.eauto.verbrauch_100km} einheit="kWh/100km" invertColors />
            {e.eauto.v2h && <KPIRow label="V2H Entladung" kpi={e.eauto.v2h} einheit="kWh" hideComparison />}
          </KomponentenCard>
        </Parkbar>
      )}
    </div>
  )
}

// ─── Helfer-Komponenten ──────────────────────────────────────────────────────

function AbweichungBadge({ wert, durchschnitt }: { wert: number | null; durchschnitt: number | null }) {
  // #387: ein Quotient ohne Zähler oder Nenner ist keine Abweichung von 0.
  if (wert === null || wert === undefined || !durchschnitt) return null
  const abweichung = ((wert - durchschnitt) / durchschnitt) * 100
  const isPositive = abweichung >= 0
  return (
    <span className={`inline-flex items-center gap-1 mt-2 px-2 py-1 rounded text-sm font-medium ${isPositive ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'}`}>
      {isPositive ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
      {isPositive ? '+' : ''}{fmtZahl(abweichung, 1)} % vs. Durchschnitt
    </span>
  )
}

const VERGLEICH_TOOLTIPS: Record<string, string> = {
  'Rang gesamt': 'Deine Position im Vergleich zu allen teilnehmenden Anlagen',
  'Rang Region': 'Deine Position im Vergleich zu Anlagen in deiner Region',
  'Spez. Ertrag': 'Dein normierter Ertrag (kWh/kWp) im Vergleichszeitraum',
}

function VergleichsBox({ label, wert, einheit, zusatz, icon, isRank, tooltip }: { label: string; wert: number | null; einheit?: string; zusatz?: string; icon?: React.ReactNode; isRank?: boolean; tooltip?: string }) {
  const tooltipText = tooltip || VERGLEICH_TOOLTIPS[label]
  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-1">
          {label}
          {tooltipText && <SimpleTooltip text={tooltipText}><HelpCircle className="h-3 w-3 text-gray-400 dark:text-gray-500 opacity-60" /></SimpleTooltip>}
        </span>
      </div>
      <p className="text-xl font-semibold text-gray-900 dark:text-white">
        {isRank && wert !== null && wert !== undefined ? '#' : ''}{fmtZahl(wert, 0)}
        {einheit && <span className="text-sm font-normal text-gray-500 dark:text-gray-400 ml-1">{einheit}</span>}
        {zusatz && <span className="text-sm font-normal text-gray-400 dark:text-gray-500 ml-2">{zusatz}</span>}
      </p>
    </div>
  )
}

function KomponentenCard({ title, icon, kapazitaet, children }: { title: string; icon: React.ReactNode; kapazitaet?: string; children: React.ReactNode }) {
  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">{icon}<h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3></div>
        {kapazitaet && <span className="text-sm text-gray-500 dark:text-gray-400">{kapazitaet}</span>}
      </div>
      <div className="space-y-3">{children}</div>
    </Card>
  )
}

const KPI_TOOLTIPS: Record<string, string> = {
  'Spez. Ertrag': 'Ertrag normiert auf installierte Leistung (kWh pro kWp)',
  'Autarkie': 'Anteil des Eigenverbrauchs am Gesamtverbrauch',
  'Eigenverbrauch': 'Anteil der selbst genutzten PV-Erzeugung',
  'Eigenverbrauchsquote': 'Anteil der selbst genutzten PV-Erzeugung',
  'Zyklen/Jahr': 'Vollständige Lade-/Entladezyklen pro Jahr',
  'Wirkungsgrad': 'Verhältnis von Entladung zu Ladung (Effizienz)',
  'Netzlade-Anteil': 'Anteil der Speicherladung aus dem Netz statt PV',
  'JAZ': 'Jahresarbeitszahl: Wärmeenergie geteilt durch Stromverbrauch',
  'Stromverbrauch': 'Gesamter Stromverbrauch der Wärmepumpe',
  'Wärmeerzeugung': 'Erzeugte Wärme für Heizung und Warmwasser',
  'PV-Anteil': 'Anteil der Ladung aus PV-Überschuss',
  'Ladung': 'Gesamte Lademenge im Zeitraum',
  'Verbrauch': 'Durchschnittlicher Energieverbrauch',
  'Erzeugung': 'Gesamte PV-Erzeugung im Zeitraum',
}

function KPIRow({ label, kpi, einheit, hideComparison, invertColors, tooltip }: { label: string; kpi?: KPIVergleich | null; einheit: string; hideComparison?: boolean; invertColors?: boolean; tooltip?: string }) {
  if (!kpi) return null
  const hasComparison = !hideComparison && kpi.community_avg !== undefined && kpi.community_avg !== null
  const abweichung = hasComparison ? ((kpi.wert - kpi.community_avg!) / kpi.community_avg!) * 100 : null
  const isPositive = abweichung !== null ? (invertColors ? abweichung < 0 : abweichung > 0) : null
  const tooltipText = tooltip || KPI_TOOLTIPS[label]
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <span className="text-gray-600 dark:text-gray-400 flex items-center gap-1">
        {label}
        {tooltipText && <SimpleTooltip text={tooltipText}><HelpCircle className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500 opacity-60" /></SimpleTooltip>}
      </span>
      <div className="flex items-center gap-3">
        <span className="font-semibold text-gray-900 dark:text-white">{fmtZahl(kpi.wert, einheit === '%' || einheit === '' ? 1 : 0)} {einheit}</span>
        {hasComparison && abweichung !== null && (
          <span className={`text-sm ${isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
            ({abweichung >= 0 ? '+' : ''}{fmtZahl(abweichung, 1)} %)
          </span>
        )}
      </div>
    </div>
  )
}

const ACHIEVEMENT_FARBEN: Record<string, { bg: string; border: string; icon: string; text: string; bar: string }> = {
  yellow:  { bg: 'bg-yellow-100 dark:bg-yellow-900/30',  border: 'border-yellow-300 dark:border-yellow-700',  icon: 'text-yellow-500',  text: 'text-yellow-700 dark:text-yellow-300',  bar: 'bg-yellow-400' },
  green:   { bg: 'bg-green-100 dark:bg-green-900/30',    border: 'border-green-300 dark:border-green-700',    icon: 'text-green-500',   text: 'text-green-700 dark:text-green-300',    bar: 'bg-green-400' },
  emerald: { bg: 'bg-emerald-100 dark:bg-emerald-900/30',border: 'border-emerald-300 dark:border-emerald-700',icon: 'text-emerald-500', text: 'text-emerald-700 dark:text-emerald-300',bar: 'bg-emerald-400' },
  blue:    { bg: 'bg-blue-100 dark:bg-blue-900/30',      border: 'border-blue-300 dark:border-blue-700',      icon: 'text-blue-500',    text: 'text-blue-700 dark:text-blue-300',      bar: 'bg-blue-400' },
  purple:  { bg: 'bg-purple-100 dark:bg-purple-900/30',  border: 'border-purple-300 dark:border-purple-700',  icon: 'text-purple-500',  text: 'text-purple-700 dark:text-purple-300',  bar: 'bg-purple-400' },
  cyan:    { bg: 'bg-cyan-100 dark:bg-cyan-900/30',      border: 'border-cyan-300 dark:border-cyan-700',      icon: 'text-cyan-500',    text: 'text-cyan-700 dark:text-cyan-300',      bar: 'bg-cyan-400' },
  orange:  { bg: 'bg-orange-100 dark:bg-orange-900/30',  border: 'border-orange-300 dark:border-orange-700',  icon: 'text-orange-500',  text: 'text-orange-700 dark:text-orange-300',  bar: 'bg-orange-400' },
  indigo:  { bg: 'bg-indigo-100 dark:bg-indigo-900/30',  border: 'border-indigo-300 dark:border-indigo-700',  icon: 'text-indigo-500',  text: 'text-indigo-700 dark:text-indigo-300',  bar: 'bg-indigo-400' },
}
const ACHIEVEMENT_FARBEN_OFF = { bg: 'bg-gray-100 dark:bg-gray-800', border: 'border-gray-200 dark:border-gray-700', icon: 'text-gray-400 dark:text-gray-500', text: 'text-gray-500' }

function AchievementBadge({ achievement }: { achievement: Achievement }) {
  const palette = ACHIEVEMENT_FARBEN[achievement.farbe] || ACHIEVEMENT_FARBEN.yellow
  const c = achievement.erreicht ? palette : { ...ACHIEVEMENT_FARBEN_OFF, bar: 'bg-gray-400' }
  return (
    <div className={`relative rounded-xl p-3 border ${c.bg} ${c.border} ${achievement.erreicht ? '' : 'opacity-70'}`} title={achievement.beschreibung}>
      <div className="flex items-center gap-2 mb-1 min-w-0 pr-5">
        <div className={`flex-shrink-0 ${c.icon}`}>{achievement.icon}</div>
        <span className={`text-sm font-medium truncate ${c.text}`} title={achievement.name}>{achievement.name}</span>
      </div>
      <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2">{achievement.beschreibung}</p>
      {!achievement.erreicht && achievement.fortschritt !== undefined && (
        <div className="mt-2">
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-sm h-1.5">
            <div className={`h-1.5 rounded-sm ${palette.bar}`} style={{ width: `${Math.min(100, Math.max(0, achievement.fortschritt))}%` }} />
          </div>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{fmtZahl(achievement.fortschritt, 0)} %</p>
        </div>
      )}
      {achievement.erreicht && <div className="absolute top-2 right-2"><Medal className={`h-4 w-4 ${c.icon}`} /></div>}
    </div>
  )
}
