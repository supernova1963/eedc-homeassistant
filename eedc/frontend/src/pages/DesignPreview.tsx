/**
 * DesignPreview — klickbares Vorschau-Skelett der IA-v4.0.0-Struktur
 * (Etappenziel 1, E1-P3). Sichtbar nur im DEV-Modus (`import.meta.env.DEV`);
 * in Production-Builds rendert die Page nichts.
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

import { useState } from 'react'
import { KPICard } from '../components/ui'
import type { KomponentenColor } from '../lib/komponentenStyle'
import {
  LayoutDashboard, Boxes, BarChart3, Users, HelpCircle, Settings, Menu, X,
  Sun, Battery, Flame, Car, Plug, Wrench, Zap, Euro, Leaf, PiggyBank, Table2,
  Activity, TrendingUp, Trophy, MapPin, ArrowRight, LineChart, Wallet,
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

function Sektion({ title, children, hint }: { title: string; children?: React.ReactNode; hint?: string }) {
  return (
    <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
        {title}
        {hint && <span className="text-xs font-normal text-gray-400 dark:text-gray-500">{hint}</span>}
      </h3>
      {children}
    </section>
  )
}

function DummyChart({ label }: { label: string }) {
  return (
    <div className="h-40 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 flex items-center justify-center text-gray-400 dark:text-gray-500 text-sm gap-2">
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

// ─── Inhalts-Sichten ──────────────────────────────────────────────────────────
function CockpitView() {
  const [sub, setSub] = useState<CockpitSub>('Live')
  return (
    <>
      <SubTabBar tabs={COCKPIT_SUBS} active={sub} onSelect={setSub} />
      <div className="p-3 sm:p-6 space-y-4 max-w-[1920px] mx-auto">
        <KpiStrip kpis={cockpitStrip(sub)} />
        {sub === 'Aussicht' ? (
          <>
            <div className="flex flex-wrap gap-2">
              {['7 Tage', '14 Tage', '12 Monate', 'Mehrjahr'].map((h) => (
                <span key={h} className="min-h-[44px] flex items-center px-3 rounded-lg text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300">{h}</span>
              ))}
            </div>
            <Sektion title="Wetter + PV-Ertragsprognose"><DummyChart label="Prognose-Verlauf" /></Sektion>
            <Sektion title="Forward-Quellenvergleich (OpenMeteo · eedc · Solcast)"><DummyChart label="Quellenvergleich" /></Sektion>
          </>
        ) : (
          <>
            <Sektion title="Hauptblock" hint="Verlauf ⇄ Fluss (Linsen-Toggle)">
              <DummyChart label={sub === 'Live' ? 'Energiefluss (Default Live)' : 'Verlauf'} />
            </Sektion>
            <Sektion title="Werte/Tabelle" hint="numerischer Zwilling, eingebettet"><DummyChart label="Werte-Embed" /></Sektion>
            <Sektion title="Komponenten-Sektionen" hint="klapp- und sortierbar">
              <p className="text-sm text-gray-500 dark:text-gray-400">Speicher · Wärme · E-Mobilität — je mit Cross-Link → Komponenten/&lt;typ&gt;.</p>
            </Sektion>
          </>
        )}
      </div>
    </>
  )
}

function KomponentenView() {
  const [typ, setTyp] = useState(KOMP_TYPEN[0].key)
  const aktiv = KOMP_TYPEN.find((t) => t.key === typ)!
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
      <div className="p-3 sm:p-6 space-y-4 max-w-[1920px] mx-auto">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">{aktiv.label}</h2>
          <span className="min-h-[44px] flex items-center px-3 rounded-lg text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300">Mai 2026 ▾</span>
        </div>
        {/* Variante C — fixe lineare Sektion-Folge: Status → Verlauf → Vergleich → Aussicht */}
        <Sektion title="Aktueller Status"><KpiStrip kpis={KOMP_STATUS[typ]} /></Sektion>
        <Sektion title="Verlauf im Zeitraum"><DummyChart label="Tages-/Monatschart" /></Sektion>
        <Sektion title="Vergleich" hint="Diagramm ⇄ Tabelle · Saison-Toggle"><DummyChart label="Vorjahr/Vormonat · wetternormalisiert" /></Sektion>
        <Sektion title="Aussicht" hint="komponentenspezifische Prognose">
          <p className="text-sm text-gray-500 dark:text-gray-400">z. B. „wann voll/leer" (Speicher) — entfällt bei Typen ohne sinnvolle Prognose.</p>
        </Sektion>
      </div>
    </>
  )
}

function AuswertungenView() {
  const [sub, setSub] = useState<(typeof AUSW_SUBS)[number]>('Finanzen')
  return (
    <>
      <SubTabBar tabs={AUSW_SUBS} active={sub} onSelect={setSub} />
      <div className="p-3 sm:p-6 space-y-4 max-w-[1920px] mx-auto">
        <Sektion title={sub} hint="analytischer Schnitt über die ganze Anlage">
          <DummyChart label={sub === 'Tabelle' ? 'Volle Werkbank (Spalten-Picker, CSV)' : `${sub}-Auswertung`} />
        </Sektion>
        {sub === 'Finanzen' && (
          <Sektion title="SOLL/HABEN-T-Konto" hint="aus dem Monatsbericht hierher verlagert (F2-a), zeitraum-parametrisiert">
            <p className="text-sm text-gray-500 dark:text-gray-400">Tag/Monat/Jahr-Selektor + sonstige Positionen (#310).</p>
          </Sektion>
        )}
      </div>
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
  return (
    <>
      <SubTabBar tabs={COMM_SUBS} active={sub} onSelect={setSub} />
      <div className="p-3 sm:p-6 space-y-4 max-w-[1920px] mx-auto">
        <KpiStrip kpis={kpis} />
        <Sektion title={sub}><DummyChart label={`Community: ${sub}`} /></Sektion>
      </div>
    </>
  )
}

function HilfeView() {
  return (
    <div className="p-3 sm:p-6 space-y-4 max-w-3xl mx-auto">
      <Sektion title="Hilfe" hint="In-App-Handbuch">
        <p className="text-sm text-gray-500 dark:text-gray-400">Inkl. „Wo ist X hin?" beim v4-Flip (Aussichten → Cockpit/Aussicht, T-Konto → Auswertungen/Finanzen …).</p>
      </Sektion>
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
export default function DesignPreview() {
  if (!import.meta.env.DEV) return null

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
    <div className="h-dvh flex flex-col overflow-hidden bg-gray-50 dark:bg-gray-900 -mx-3 sm:-mx-6 -mt-4 sm:-mt-4">
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
