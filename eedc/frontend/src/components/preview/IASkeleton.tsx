/**
 * IASkeleton — klickbares Vorschau-Skelett der IA-v4.0.0-Struktur
 * (Etappenziel 1/2). **Guard-frei** und damit in zwei Kontexten lauffähig:
 *   1. lokal über `pages/DesignPreview.tsx` (DEV-Guard davor) auf
 *      `/dev/design-preview`;
 *   2. als eigenständiger Vorschau-Entry (`preview-main.tsx` + `preview.html`,
 *      `vite.preview.config.ts`) für das öffentliche GitHub-Pages-Hosting unter
 *      `/eedc-homeassistant/preview/` (Etappe 2) — das ist ein **Production**-
 *      Build, deshalb darf hier KEIN `import.meta.env.DEV`-Guard stehen.
 *
 * Zweck (KONZEPT-IA-V4 §„Vorab-Sichtung"): Die wiederkehrende Tester-Frage
 * „kann man vorher sehen, was sich ändert?" mit einer **klickbaren Vorschau
 * aus echten Komponenten** beantworten — kein Design-Tool, kein Wegwerf-Mock.
 * Es ist bewusst eine reine **Navigations-Schale** (keine echten Daten): die
 * neue Top-Nav (Zeit/Was/Wie-Achsen), die Cockpit-Sub-Tabs, der Komponenten-
 * Hub (Variante C) und das Einstellungs-Kachelgrid — als Dummy-Karten mit der
 * KPICard-SoT (B9). Struktur **exakt** nach KONZEPT-IA-V4/Journal, damit E2
 * die richtige Struktur testet.
 *
 * Diese Schale läuft als eigenständige In-Page-Navigation (interner State,
 * keine echten Routen — die v4-Routen entstehen erst ab E3). Mobile-Quer-
 * schnitt: `h-dvh`, Touch-Targets ≥ 44 px, Hamburger (M0).
 */

import { useMemo, useState } from 'react'
import { KPICard } from '../ui'
import type { KomponentenColor } from '../../lib/komponentenStyle'
import {
  LayoutDashboard, Boxes, BarChart3, Users, HelpCircle, Settings, Menu, X,
  Sun, Battery, Flame, Car, Plug, Wrench, Zap, Euro, Leaf, PiggyBank, Table2,
  Activity, TrendingUp, Trophy, MapPin, ArrowRight, LineChart, Wallet,
  ArrowUp, ArrowDown, ChevronDown, Maximize2, Minimize2,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

// ─── Achsen / Tabs (Struktur-SoT: KONZEPT-IA-V4) ─────────────────────────────
type TopKey = 'cockpit' | 'komponenten' | 'auswertungen' | 'community' | 'hilfe' | 'einstellungen'

const TOP_INHALT: { key: TopKey; label: string; icon: LucideIcon }[] = [
  { key: 'cockpit',      label: 'Cockpit',      icon: LayoutDashboard },
  { key: 'komponenten',  label: 'Komponenten',  icon: Boxes },
  { key: 'auswertungen', label: 'Auswertungen', icon: BarChart3 },
  { key: 'community',    label: 'Community',    icon: Users },
]
const TOP_META: { key: TopKey; label: string; icon: LucideIcon }[] = [
  { key: 'hilfe',         label: 'Hilfe',         icon: HelpCircle },
  { key: 'einstellungen', label: 'Einstellungen', icon: Settings },
]

const COCKPIT_SUBS = ['Live', 'Tag', 'Monat', 'Jahr/Gesamt', 'Aussicht'] as const
type CockpitSub = (typeof COCKPIT_SUBS)[number]

const KOMP_TYPEN: { key: string; label: string; icon: LucideIcon }[] = [
  { key: 'pv',        label: 'PV-Anlage',   icon: Sun },
  { key: 'speicher',  label: 'Speicher',    icon: Battery },
  { key: 'waerme',    label: 'Wärme/Klima', icon: Flame },
  { key: 'eauto',     label: 'E-Auto',      icon: Car },
  { key: 'wallbox',   label: 'Wallbox',     icon: Plug },
  { key: 'bkw',       label: 'BKW',         icon: Sun },
  { key: 'sonstiges', label: 'Sonstiges',   icon: Wrench },
]

const AUSW_SUBS = ['Finanzen', 'CO₂', 'ROI', 'Tabelle', 'Prognose-vs-IST'] as const
const COMM_SUBS = ['Übersicht', 'PV-Ertrag', 'Komponenten', 'Regional', 'Trends'] as const

// ─── KPI-Dummy-Sätze (KONZEPT-IA-V4: D1-Strip + D2-Status-Kanon) ─────────────
interface KpiDummy { title: string; value: string; unit?: string; color: KomponentenColor; icon: LucideIcon }

// D1 — universeller Cockpit-Strip; ab Monat + Netto-Ertrag, Jahr + spez. Ertrag.
function cockpitStrip(sub: CockpitSub): KpiDummy[] {
  const basis: KpiDummy[] = [
    { title: 'PV-Erzeugung',   value: '412', unit: 'kWh', color: 'yellow', icon: Sun },
    { title: 'Autarkie',       value: '68',  unit: '%',   color: 'green',  icon: Activity },
    { title: 'Eigenverbrauch', value: '54',  unit: '%',   color: 'purple', icon: Zap },
    { title: 'Einspeisung',    value: '189', unit: 'kWh', color: 'green',  icon: ArrowRight },
    { title: 'Netzbezug',      value: '143', unit: 'kWh', color: 'red',    icon: Plug },
  ]
  if (sub === 'Monat') basis.push({ title: 'Netto-Ertrag', value: '128', unit: '€', color: 'blue', icon: Euro })
  if (sub === 'Jahr/Gesamt') {
    basis.push({ title: 'Netto-Ertrag', value: '1.480', unit: '€', color: 'blue', icon: Euro })
    basis.push({ title: 'Spez. Ertrag', value: '1.040', unit: 'kWh/kWp', color: 'cyan', icon: TrendingUp })
  }
  return basis
}

// D2 — Status-KPIs je Komponententyp (Kanon, KONZEPT-IA-V4 Z. 177-185).
const KOMP_STATUS: Record<string, KpiDummy[]> = {
  pv: [
    { title: 'Anlagenleistung', value: '9,8',  unit: 'kWp',     color: 'yellow', icon: Sun },
    { title: 'Gesamterzeugung', value: '38,2', unit: 'MWh',     color: 'yellow', icon: Activity },
    { title: 'Spez. Ertrag',    value: '1.040', unit: 'kWh/kWp', color: 'cyan',  icon: TrendingUp },
    { title: 'Eigenverbrauch',  value: '54',   unit: '%',       color: 'purple', icon: Zap },
  ],
  speicher: [
    { title: 'Vollzyklen',    value: '312', color: 'blue', icon: Activity },
    { title: 'Wirkungsgrad η', value: '92', unit: '%', color: 'cyan', icon: TrendingUp },
    { title: 'Durchsatz',     value: '4,1', unit: 'MWh', color: 'blue', icon: Zap },
    { title: 'Ersparnis',     value: '286', unit: '€', color: 'green', icon: Euro },
  ],
  waerme: [
    { title: 'JAZ',             value: '3,8', color: 'orange', icon: Flame },
    { title: 'Wärme erzeugt',   value: '12,4', unit: 'MWh', color: 'orange', icon: Activity },
    { title: 'Strom verbraucht', value: '3,3', unit: 'MWh', color: 'yellow', icon: Zap },
    { title: 'Ersparnis vs. Gas', value: '410', unit: '€', color: 'green', icon: Euro },
  ],
  eauto: [
    { title: 'Gefahren',  value: '14.200', unit: 'km', color: 'blue', icon: Car },
    { title: 'Verbrauch', value: '17,2', unit: 'kWh/100km', color: 'yellow', icon: Zap },
    { title: 'PV-Anteil', value: '61', unit: '%', color: 'green', icon: Sun },
    { title: 'Ersparnis vs. Benzin', value: '1.120', unit: '€', color: 'green', icon: Euro },
  ],
  wallbox: [
    { title: 'Heimladung',   value: '2,4', unit: 'MWh', color: 'blue', icon: Plug },
    { title: 'PV-Anteil',    value: '58', unit: '%', color: 'green', icon: Sun },
    { title: 'Ladevorgänge', value: '143', color: 'blue', icon: Activity },
    { title: 'Ersparnis vs. Extern', value: '640', unit: '€', color: 'green', icon: Euro },
  ],
  bkw: [
    { title: 'Erzeugung',      value: '612', unit: 'kWh', color: 'yellow', icon: Sun },
    { title: 'Eigenverbrauch', value: '94', unit: '%', color: 'purple', icon: Zap },
    { title: 'Ersparnis',      value: '184', unit: '€', color: 'green', icon: Euro },
    { title: 'Spez. Ertrag',   value: '980', unit: 'kWh/kWp', color: 'cyan', icon: TrendingUp },
  ],
  sonstiges: [
    { title: 'Erzeugung',     value: '320', unit: 'kWh', color: 'yellow', icon: Sun },
    { title: 'EV-Quote',      value: '72', unit: '%', color: 'purple', icon: Zap },
    { title: 'Ersparnis',     value: '96', unit: '€', color: 'green', icon: Euro },
    { title: 'CO₂ vermieden →', value: '0,2', unit: 't', color: 'green', icon: Leaf },
  ],
}

// ─── Bausteine ───────────────────────────────────────────────────────────────
function KpiStrip({ kpis }: { kpis: KpiDummy[] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {kpis.map((k) => (
        <KPICard key={k.title} title={k.title} value={k.value} unit={k.unit} color={k.color} icon={k.icon} />
      ))}
    </div>
  )
}

function DummyChart({ label, tall }: { label: string; tall?: boolean }) {
  return (
    <div className={`${tall ? 'h-full min-h-[300px]' : 'h-40'} rounded-lg border border-dashed border-gray-300 dark:border-gray-600 flex items-center justify-center text-gray-400 dark:text-gray-500 text-sm gap-2`}>
      <LineChart className="h-5 w-5" />
      {label}
    </div>
  )
}

function SubTabBar<T extends string>({ tabs, active, onSelect }: { tabs: readonly T[]; active: T; onSelect: (t: T) => void }) {
  return (
    <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-3 sm:px-6">
      <nav className="flex items-center gap-1 py-2 overflow-x-auto scrollbar-none">
        {tabs.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => onSelect(t)}
            className={`min-h-[44px] flex items-center px-3 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
              active === t
                ? 'bg-white dark:bg-gray-800 text-primary-700 dark:text-primary-300 shadow-sm'
                : 'text-gray-600 hover:bg-white/50 dark:text-gray-400 dark:hover:bg-gray-800/50'
            }`}
          >
            {t}
          </button>
        ))}
      </nav>
    </div>
  )
}

// ─── Universelles Block-Modell (Gernot-Entscheid 2026-06-13) ──────────────────
// JEDER Block (KPI-Strip, Hauptblock, Werte/Tabelle, Detail-Sektion …) ist
// einklappbar (⌄) und hat einen Fokus/Vollbild-Schalter (⤢) — app-weit auf allen
// Inhalts-Achsen (Cockpit/Komponenten/Auswertungen/Community). In den Cockpit-
// Zeitsichten zusätzlich per ↑↓ verschiebbar (Monatsbericht-Muster, fester Satz).
// Fokus macht u. a. den Live-Energiefluss wieder bildschirmfüllend (Erhalt der
// beliebten Live-Seite). Persistenz pro Sicht = B6-SoT (in der echten App).
interface Block {
  id: string
  title: string
  icon?: LucideIcon
  farbe?: string
  summary?: string
  /** Default-Zustand; false = startet eingeklappt (z. B. datenreich/mobil). */
  defaultOpen?: boolean
  /** `fokus` = Vollbild-Render (Charts groß). Param mit _ wenn ungenutzt. */
  render: (fokus: boolean) => React.ReactNode
}

function BloeckeView({ bloecke, sortierbar = false }: { bloecke: Block[]; sortierbar?: boolean }) {
  const [order, setOrder] = useState<string[]>(() => bloecke.map((b) => b.id))
  const [zu, setZu] = useState<Set<string>>(() => new Set(bloecke.filter((b) => b.defaultOpen === false).map((b) => b.id)))
  const [fokus, setFokus] = useState<string | null>(null)
  const byId = useMemo(() => Object.fromEntries(bloecke.map((b) => [b.id, b] as const)), [bloecke])

  const verschieben = (i: number, r: -1 | 1) => {
    const ziel = i + r
    if (ziel < 0 || ziel >= order.length) return
    const next = [...order]
    ;[next[i], next[ziel]] = [next[ziel], next[i]]
    setOrder(next)
  }
  const toggle = (id: string) => {
    const next = new Set(zu)
    next.has(id) ? next.delete(id) : next.add(id)
    setZu(next)
  }

  // ── Fokus/Vollbild: nur dieser Block, füllt den Inhaltsbereich ──────────────
  if (fokus && byId[fokus]) {
    const b = byId[fokus]
    return (
      <div className="min-h-[85vh] flex flex-col p-3 sm:p-6 gap-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
            {b.icon && <b.icon className={`h-5 w-5 ${b.farbe ?? ''}`} />}
            {b.title}
            <span className="text-xs font-normal text-gray-400 dark:text-gray-500">Fokus / Vollbild</span>
          </h2>
          <button type="button" onClick={() => setFokus(null)}
            className="min-h-[44px] flex items-center gap-2 px-3 rounded-lg text-sm font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700">
            <Minimize2 className="h-4 w-4" /> Zurück
          </button>
        </div>
        <div className="flex-1 min-h-0">{b.render(true)}</div>
      </div>
    )
  }

  const ordered = order.map((id) => byId[id]).filter(Boolean) as Block[]
  return (
    <div className="p-3 sm:p-6 space-y-3 max-w-[1920px] mx-auto">
      <p className="text-xs text-gray-400 dark:text-gray-500">
        Jeder Block: <ChevronDown className="inline h-3 w-3" /> einklappen · <Maximize2 className="inline h-3 w-3" /> Fokus/Vollbild
        {sortierbar && <> · <ArrowUp className="inline h-3 w-3" /><ArrowDown className="inline h-3 w-3" /> verschieben</>}
      </p>
      {ordered.map((b, i) => {
        const istZu = zu.has(b.id)
        return (
          <section key={b.id} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
            <div className="flex items-center gap-2 px-3 min-h-[44px]">
              <button type="button" onClick={() => toggle(b.id)} className="flex-1 flex items-center gap-2 text-left py-2 min-w-0">
                {b.icon && <b.icon className={`h-4 w-4 flex-shrink-0 ${b.farbe ?? 'text-gray-400 dark:text-gray-500'}`} />}
                <span className="text-sm font-semibold text-gray-900 dark:text-white whitespace-nowrap">{b.title}</span>
                {b.summary && <span className="text-xs text-gray-400 dark:text-gray-500 truncate">{b.summary}</span>}
              </button>
              <div className="flex items-center gap-0.5 flex-shrink-0">
                {sortierbar && (
                  <>
                    <button type="button" onClick={() => verschieben(i, -1)} disabled={i === 0} aria-label="nach oben"
                      className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-30 disabled:cursor-default">
                      <ArrowUp className="h-4 w-4" />
                    </button>
                    <button type="button" onClick={() => verschieben(i, 1)} disabled={i === ordered.length - 1} aria-label="nach unten"
                      className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-30 disabled:cursor-default">
                      <ArrowDown className="h-4 w-4" />
                    </button>
                  </>
                )}
                <button type="button" onClick={() => setFokus(b.id)} aria-label="Fokus / Vollbild"
                  className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                  <Maximize2 className="h-4 w-4" />
                </button>
                <button type="button" onClick={() => toggle(b.id)} aria-label={istZu ? 'aufklappen' : 'einklappen'}
                  className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                  <ChevronDown className={`h-4 w-4 transition-transform ${istZu ? '-rotate-90' : ''}`} />
                </button>
              </div>
            </div>
            {!istZu && <div className="px-3 pb-3">{b.render(false)}</div>}
          </section>
        )
      })}
    </div>
  )
}

// Detail-Sektionen der Cockpit-Zeitsichten (Summary-Zeilen wie im Monatsbericht).
const COCKPIT_DETAIL: { id: string; icon: LucideIcon; title: string; summary: string; farbe: string }[] = [
  { id: 'd-energie',   icon: Sun,     title: 'Energie-Bilanz',      summary: '618 kWh PV · 96 % Autarkie', farbe: 'text-yellow-500' },
  { id: 'd-finanzen',  icon: Euro,    title: 'Finanzen',            summary: '+90,25 € Monatsergebnis',    farbe: 'text-blue-500' },
  { id: 'd-community', icon: Users,   title: 'Community-Vergleich',  summary: '2 Anlagen im Juni 2026',     farbe: 'text-blue-500' },
  { id: 'd-speicher',  icon: Battery, title: 'Speicher',            summary: '99 kWh geladen · 7,7 Zyklen · 73 % η', farbe: 'text-green-500' },
  { id: 'd-emob',      icon: Car,     title: 'E-Mobilität',         summary: '62 kWh geladen · 221 km · +7,82 € vs. Verbrenner', farbe: 'text-purple-500' },
]

// ─── Inhalts-Sichten ──────────────────────────────────────────────────────────
function CockpitView() {
  const [sub, setSub] = useState<CockpitSub>('Live')
  const istLive = sub === 'Live'

  const bloecke: Block[] =
    sub === 'Aussicht'
      ? [
          { id: 'kpi', title: 'Kennzahlen', icon: Activity, defaultOpen: true, render: (_f) => <KpiStrip kpis={cockpitStrip(sub)} /> },
          { id: 'wetter', title: 'Wetter + PV-Ertragsprognose', icon: Sun, render: (f) => <DummyChart label="Prognose-Verlauf (7/14 Tage · 12 Monate · Mehrjahr)" tall={f} /> },
          { id: 'quellen', title: 'Forward-Quellenvergleich', icon: BarChart3, summary: 'OpenMeteo · eedc · Solcast', render: (f) => <DummyChart label="Quellenvergleich" tall={f} /> },
        ]
      : [
          { id: 'kpi', title: 'Kennzahlen', icon: Activity, defaultOpen: true, render: (_f) => <KpiStrip kpis={cockpitStrip(sub)} /> },
          { id: 'haupt', title: 'Hauptblock', icon: LineChart, summary: 'Verlauf ⇄ Fluss', defaultOpen: true, render: (f) => <DummyChart label={istLive ? 'Energiefluss (Default Live) — ⤢ für Vollbild' : 'Verlauf'} tall={f} /> },
          { id: 'werte', title: 'Werte/Tabelle', icon: Table2, summary: 'numerischer Zwilling', defaultOpen: !istLive, render: (f) => <DummyChart label="Werte-Embed" tall={f} /> },
          ...COCKPIT_DETAIL.map((d): Block => ({
            id: d.id, title: d.title, icon: d.icon, farbe: d.farbe, summary: d.summary, defaultOpen: false,
            render: (f) => <DummyChart label={`${d.title} — Detail`} tall={f} />,
          })),
        ]

  return (
    <>
      <SubTabBar tabs={COCKPIT_SUBS} active={sub} onSelect={setSub} />
      {/* Cockpit-Zeitsichten: alle Blöcke klapp-/fokussierbar UND sortierbar */}
      <BloeckeView key={`cockpit-${sub}`} bloecke={bloecke} sortierbar />
    </>
  )
}

function KomponentenView() {
  const [typ, setTyp] = useState(KOMP_TYPEN[0].key)
  const aktiv = KOMP_TYPEN.find((t) => t.key === typ)!
  // Variante C — fixe lineare Folge (Stabilität über Typen): nicht sortierbar,
  // aber klapp- und fokussierbar.
  const bloecke: Block[] = [
    { id: 'status', title: 'Aktueller Status', icon: Activity, defaultOpen: true, render: (_f) => <KpiStrip kpis={KOMP_STATUS[typ]} /> },
    { id: 'verlauf', title: 'Verlauf im Zeitraum', icon: LineChart, defaultOpen: true, render: (f) => <DummyChart label="Tages-/Monatschart" tall={f} /> },
    { id: 'vergleich', title: 'Vergleich', icon: BarChart3, summary: 'Diagramm ⇄ Tabelle · Saison-Toggle', defaultOpen: false, render: (f) => <DummyChart label="Vorjahr/Vormonat · wetternormalisiert" tall={f} /> },
    { id: 'aussicht', title: 'Aussicht', icon: TrendingUp, summary: 'komponentenspezifische Prognose', defaultOpen: false, render: (_f) => <p className="text-sm text-gray-500 dark:text-gray-400">z. B. „wann voll/leer" (Speicher) — entfällt bei Typen ohne sinnvolle Prognose.</p> },
  ]
  return (
    <>
      <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-3 sm:px-6">
        <nav className="flex items-center gap-1 py-2 overflow-x-auto scrollbar-none">
          {KOMP_TYPEN.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTyp(t.key)}
              className={`min-h-[44px] flex items-center gap-2 px-3 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
                typ === t.key
                  ? 'bg-white dark:bg-gray-800 text-primary-700 dark:text-primary-300 shadow-sm'
                  : 'text-gray-600 hover:bg-white/50 dark:text-gray-400 dark:hover:bg-gray-800/50'
              }`}
            >
              <t.icon className="h-4 w-4" />
              {t.label}
            </button>
          ))}
        </nav>
      </div>
      <div className="px-3 sm:px-6 pt-4 flex items-center justify-between max-w-[1920px] mx-auto">
        <h2 className="text-lg font-bold text-gray-900 dark:text-white">{aktiv.label}</h2>
        <span className="min-h-[44px] flex items-center px-3 rounded-lg text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300">Mai 2026 ▾</span>
      </div>
      <BloeckeView key={`komp-${typ}`} bloecke={bloecke} />
    </>
  )
}

function AuswertungenView() {
  const [sub, setSub] = useState<(typeof AUSW_SUBS)[number]>('Finanzen')
  const bloecke: Block[] = [
    { id: 'main', title: sub, icon: BarChart3, summary: 'analytischer Schnitt über die ganze Anlage', defaultOpen: true, render: (f) => <DummyChart label={sub === 'Tabelle' ? 'Volle Werkbank (Spalten-Picker, CSV)' : `${sub}-Auswertung`} tall={f} /> },
    ...(sub === 'Finanzen'
      ? [{ id: 'tkonto', title: 'SOLL/HABEN-T-Konto', icon: Wallet, summary: 'aus dem Monatsbericht hierher verlagert (F2-a)', defaultOpen: true, render: (_f: boolean) => <p className="text-sm text-gray-500 dark:text-gray-400">zeitraum-parametrisiert (Tag/Monat/Jahr) + sonstige Positionen (#310).</p> } as Block]
      : []),
  ]
  return (
    <>
      <SubTabBar tabs={AUSW_SUBS} active={sub} onSelect={setSub} />
      <BloeckeView key={`ausw-${sub}`} bloecke={bloecke} />
    </>
  )
}

function CommunityView() {
  const [sub, setSub] = useState<(typeof COMM_SUBS)[number]>('Übersicht')
  const kpis: KpiDummy[] = [
    { title: 'Dein Rang',    value: '#12', color: 'blue', icon: Trophy },
    { title: 'Spez. Ertrag', value: '1.040', unit: 'kWh/kWp', color: 'cyan', icon: TrendingUp },
    { title: 'Region',       value: 'Bayern', color: 'green', icon: MapPin },
  ]
  const bloecke: Block[] = [
    { id: 'kpi', title: 'Kennzahlen', icon: Trophy, defaultOpen: true, render: (_f) => <KpiStrip kpis={kpis} /> },
    { id: 'inhalt', title: sub, icon: BarChart3, defaultOpen: true, render: (f) => <DummyChart label={`Community: ${sub}`} tall={f} /> },
  ]
  return (
    <>
      <SubTabBar tabs={COMM_SUBS} active={sub} onSelect={setSub} />
      <BloeckeView key={`comm-${sub}`} bloecke={bloecke} />
    </>
  )
}

function HilfeView() {
  return (
    <div className="p-3 sm:p-6 space-y-4 max-w-3xl mx-auto">
      <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Hilfe <span className="text-xs font-normal text-gray-400 dark:text-gray-500">In-App-Handbuch</span></h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">Inkl. „Wo ist X hin?" beim v4-Flip (Aussichten → Cockpit/Aussicht, T-Konto → Auswertungen/Finanzen …).</p>
      </section>
    </div>
  )
}

const EINSTELLUNGEN_GRUPPEN: { gruppe: string; kacheln: { name: string; status: '✓' | '⚠' | '🆕'; icon: LucideIcon }[] }[] = [
  { gruppe: 'Anlage', kacheln: [
    { name: 'Anlage', status: '✓', icon: Settings }, { name: 'Strompreise', status: '✓', icon: Zap },
    { name: 'Investitionen', status: '✓', icon: PiggyBank }, { name: 'Solarprognose', status: '⚠', icon: Sun },
  ] },
  { gruppe: 'Daten', kacheln: [
    { name: 'Monatsdaten', status: '✓', icon: Table2 }, { name: 'Energieprofil-Pflege', status: '✓', icon: Activity },
    { name: 'Daten-Checker', status: '⚠', icon: Wallet }, { name: 'Einrichtung', status: '✓', icon: Settings },
  ] },
  { gruppe: 'Integration', kacheln: [
    { name: 'Sensor-Zuordnung', status: '✓', icon: MapPin }, { name: 'Statistik-Import', status: '🆕', icon: BarChart3 },
    { name: 'MQTT-Export', status: '✓', icon: ArrowRight }, { name: 'Import-Wizards', status: '🆕', icon: Boxes },
  ] },
  { gruppe: 'System', kacheln: [
    { name: 'Allgemein', status: '✓', icon: Settings }, { name: 'Backup', status: '⚠', icon: Battery }, { name: 'Protokolle', status: '✓', icon: LineChart },
  ] },
  { gruppe: 'Daten teilen', kacheln: [{ name: 'Community-Share', status: '🆕', icon: Users }] },
]

function EinstellungenView() {
  return (
    <div className="p-3 sm:p-6 space-y-6 max-w-5xl mx-auto">
      <input
        type="search"
        placeholder="🔍 Suchen in Einstellungen …"
        className="w-full min-h-[44px] rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 text-sm text-gray-900 dark:text-white"
      />
      {EINSTELLUNGEN_GRUPPEN.map((g) => (
        <div key={g.gruppe}>
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-2">{g.gruppe}</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {g.kacheln.map((k) => (
              <button key={k.name} type="button" className="min-h-[44px] text-left rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-3 hover:shadow-md transition-shadow flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 text-sm text-gray-900 dark:text-white">
                  <k.icon className="h-4 w-4 text-gray-400 dark:text-gray-500" />
                  {k.name}
                </span>
                <span className="text-sm">{k.status}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Schale ───────────────────────────────────────────────────────────────────
export default function IASkeleton() {
  const [top, setTop] = useState<TopKey>('cockpit')
  const [mobileOpen, setMobileOpen] = useState(false)

  const alleEintraege = [...TOP_INHALT, ...TOP_META]
  const navBtn = (key: TopKey, label: string, Icon: LucideIcon, aktiv: boolean) => (
    <button
      key={key}
      type="button"
      onClick={() => { setTop(key); setMobileOpen(false) }}
      className={`min-h-[44px] flex items-center gap-2 px-3 rounded-lg text-sm font-medium transition-colors ${
        aktiv
          ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
          : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
      }`}
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  )

  return (
    <div className="h-dvh flex flex-col overflow-hidden bg-gray-50 dark:bg-gray-900">
      {/* Top-Nav-Schale */}
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="px-4 sm:px-6 flex items-center justify-between h-14">
          <div className="flex items-center gap-3">
            <span className="text-xl font-bold text-gray-900 dark:text-white">eedc</span>
            <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200">IA-v4 VORSCHAU</span>
            <nav aria-label="Hauptnavigation" className="ml-4 hidden lg:flex items-center gap-1">
              {TOP_INHALT.map((t) => navBtn(t.key, t.label, t.icon, top === t.key))}
            </nav>
          </div>
          <div className="hidden lg:flex items-center gap-1">
            <span className="h-5 w-px bg-gray-300 dark:bg-gray-600 mx-1" />
            {TOP_META.map((t) => navBtn(t.key, t.label, t.icon, top === t.key))}
          </div>
          <button
            type="button"
            onClick={() => setMobileOpen(!mobileOpen)}
            className="lg:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
            aria-label="Menü"
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
        {/* Mobile-Menü (M0 Hamburger) */}
        {mobileOpen && (
          <nav aria-label="Hauptnavigation mobil" className="lg:hidden border-t border-gray-200 dark:border-gray-700 px-4 py-3 space-y-1">
            {alleEintraege.map((t) => navBtn(t.key, t.label, t.icon, top === t.key))}
          </nav>
        )}
      </header>

      {/* Inhalt je Achse */}
      <main className="flex-1 overflow-auto">
        {top === 'cockpit' && <CockpitView />}
        {top === 'komponenten' && <KomponentenView />}
        {top === 'auswertungen' && <AuswertungenView />}
        {top === 'community' && <CommunityView />}
        {top === 'hilfe' && <HilfeView />}
        {top === 'einstellungen' && <EinstellungenView />}
      </main>
    </div>
  )
}
