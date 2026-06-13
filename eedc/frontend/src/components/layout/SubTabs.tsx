/**
 * SubTabs Komponente
 * Zeigt kontextabhängige Sub-Navigation unter der Hauptnavigation.
 * Einstellungen: gruppen-aware – zeigt alle Tabs der aktuellen Gruppe.
 */

import { useEffect, useRef } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import { useHAAvailable } from '../../hooks/useHAAvailable'
import { useSelectedAnlage, useInvestitionen } from '../../hooks'
import { compareTyp } from '../../lib'
import type { InvestitionTyp } from '../../types'
import { SimpleTooltip } from '../ui/FormelTooltip'
import {
  LayoutDashboard,
  Car,
  Flame,
  Battery,
  Plug,
  Sun,
  Wrench,
  Home,
  Zap,
  PiggyBank,
  Database,
  Settings,
  Cpu,
  Radio,
  BarChart2,
  BarChart3,
  Share2,
  MapPin,
  HardDrive,
  ClipboardCheck,
  ScrollText,
  FileText,
  Activity,
  Euro,
  Leaf,
  Table2,
  Calendar,
  Trophy,
  TrendingUp,
} from 'lucide-react'

interface TabItem {
  name: string
  href: string
  icon: LucideIcon
  exact?: boolean
  /** Beta-Badge hinter dem Label (von PillTabs übernommen, B1). */
  beta?: boolean
  /** Tooltip-Text auf dem Tab (von PillTabs übernommen, B1). */
  tooltip?: string
}

interface TabGroup {
  label: string
  tabs: TabItem[]
  /** Pfad-Präfixe, die zu dieser Gruppe gehören */
  prefixes: string[]
}

// ─── Cockpit Tabs ────────────────────────────────────────────────────────────
// Basis-Tabs werden immer angezeigt
const cockpitBaseTabs: TabItem[] = [
  { name: 'Übersicht',       href: '/cockpit',                    icon: LayoutDashboard, exact: true },
  { name: 'Monatsberichte',  href: '/cockpit/monatsberichte',     icon: FileText },
  { name: 'PV-Anlage',       href: '/cockpit/pv-anlage',          icon: Sun },
]

// Investitions-Tabs: werden nur angezeigt wenn der Typ als Investition existiert.
// Reihenfolge folgt dem Kanon `INVESTITION_TYP_ORDER` (lib/constants.ts) — via
// compareTyp erzwungen, damit die Tab-Folge nicht von der Literal-Reihenfolge
// driften kann (Fundament P4 / F7). Im Cockpit erscheinen nur die Verbraucher-/
// Speicher-Typen als Tabs (PV-Module/Wechselrichter laufen unter „PV-Anlage").
const cockpitInvestitionTabs: (TabItem & { typen: InvestitionTyp[] })[] = [
  { name: 'Speicher',        href: '/cockpit/speicher',         icon: Battery, typen: ['speicher'] },
  { name: 'Balkonkraftwerk', href: '/cockpit/balkonkraftwerk',  icon: Sun,     typen: ['balkonkraftwerk'] },
  { name: 'Wärmepumpe',      href: '/cockpit/waermepumpe',      icon: Flame,   typen: ['waermepumpe'] },
  { name: 'Wallbox',         href: '/cockpit/wallbox',          icon: Plug,    typen: ['wallbox'] },
  { name: 'E-Auto',          href: '/cockpit/e-auto',           icon: Car,     typen: ['e-auto'] },
  { name: 'Sonstiges',       href: '/cockpit/sonstiges',        icon: Wrench,  typen: ['sonstiges'] },
]
// Kanon erzwingen (statt Literal-Reihenfolge), damit die Tab-Folge nicht driftet.
cockpitInvestitionTabs.sort((a, b) => compareTyp({ typ: a.typen[0] }, { typ: b.typen[0] }))

// ─── Auswertungen / Aussichten / Community ───────────────────────────────────
// B1 (E1-P3): Diese drei Seiten waren state-getrieben (PillTabs). Jetzt route-
// getrieben über echte URLs `/auswertungen/<tab>` etc. — die Tab-Leiste lebt
// hier in der Layout-SubTabs (eine Sub-Nav-Mechanik), die Seite rendert nur den
// Inhalt zum URL-Tab. Bestand 1:1 gehoben (gleiche Tabs/Reihenfolge/Beta/Tooltip).
const auswertungenTabs: TabItem[] = [
  { name: 'Energie',       href: '/auswertungen/energie',       icon: Zap },
  { name: 'PV-Anlage',     href: '/auswertungen/pv',            icon: Sun },
  { name: 'Komponenten',   href: '/auswertungen/komponenten',   icon: Cpu },
  { name: 'Finanzen',      href: '/auswertungen/finanzen',      icon: Euro },
  { name: 'CO2',           href: '/auswertungen/co2',           icon: Leaf },
  { name: 'Investitionen', href: '/auswertungen/investitionen', icon: PiggyBank },
  { name: 'Tabelle',       href: '/auswertungen/tabelle',       icon: Table2 },
  { name: 'Energieprofil', href: '/auswertungen/energieprofil', icon: Activity, beta: true },
]

const aussichtenTabs: TabItem[] = [
  { name: 'Kurzfristig', href: '/aussichten/kurzfristig', icon: Sun,        tooltip: '7-14 Tage Wetterprognose mit PV-Ertragsprognose' },
  { name: 'Prognosen',   href: '/aussichten/prognosen',   icon: BarChart3,  tooltip: 'PV-Prognosen vergleichen (OpenMeteo, eedc-kalibriert, Solcast)' },
  { name: 'Langfristig', href: '/aussichten/langfristig', icon: Calendar,   tooltip: '12-Monats-Prognose basierend auf PVGIS-Daten' },
  { name: 'Trend',       href: '/aussichten/trend',       icon: TrendingUp, tooltip: 'Historische Trends und Degradationsanalyse' },
  { name: 'Finanzen',    href: '/aussichten/finanzen',    icon: Euro,       tooltip: 'Finanzielle Prognosen und Amortisation' },
]

const communityTabs: TabItem[] = [
  { name: 'Übersicht',   href: '/community/uebersicht',   icon: Trophy },
  { name: 'PV-Ertrag',   href: '/community/pv-ertrag',    icon: Sun },
  { name: 'Komponenten', href: '/community/komponenten',  icon: Battery },
  { name: 'Regional',    href: '/community/regional',     icon: MapPin },
  { name: 'Trends',      href: '/community/trends',       icon: TrendingUp },
  { name: 'Statistiken', href: '/community/statistiken',  icon: BarChart3 },
]

// ─── Einstellungen-Gruppen ────────────────────────────────────────────────────
const einstellungenGruppen: TabGroup[] = [
  {
    label: 'Stammdaten',
    prefixes: [
      '/einstellungen/anlage',
      '/einstellungen/strompreise',
      '/einstellungen/investitionen',
      '/einstellungen/solarprognose',
    ],
    tabs: [
      { name: 'Anlagen',       href: '/einstellungen/anlage',        icon: Home },
      { name: 'Strompreise',   href: '/einstellungen/strompreise',   icon: Zap },
      { name: 'Investitionen', href: '/einstellungen/investitionen', icon: PiggyBank },
      { name: 'Solarprognose', href: '/einstellungen/solarprognose', icon: Sun },
    ],
  },
  {
    label: 'Daten',
    prefixes: [
      '/einstellungen/monatsdaten',
      '/einstellungen/monatsabschluss',
      '/einstellungen/energieprofil',
      '/einstellungen/einrichtung',
      // Sub-Wizards erreichbar via Einrichtung-Hub
      '/einstellungen/import',
      '/einstellungen/portal-import',
      '/einstellungen/cloud-import',
      '/einstellungen/custom-import',
      '/einstellungen/connector',
      '/einstellungen/mqtt-inbound',
      '/einstellungen/daten-checker',
    ],
    tabs: [
      { name: 'Monatsdaten',   href: '/einstellungen/monatsdaten',   icon: Database },
      { name: 'Energieprofil', href: '/einstellungen/energieprofil', icon: Activity },
      { name: 'Daten-Checker', href: '/einstellungen/daten-checker', icon: ClipboardCheck },
      { name: 'Einrichtung',   href: '/einstellungen/einrichtung',   icon: Cpu },
    ],
  },
  {
    label: 'Home Assistant',
    prefixes: [
      '/einstellungen/sensor-mapping',
      '/einstellungen/ha-statistik-import',
      '/einstellungen/ha-export',
    ],
    tabs: [
      { name: 'Sensor-Zuordnung',  href: '/einstellungen/sensor-mapping',        icon: MapPin },
      { name: 'Statistik-Import',  href: '/einstellungen/ha-statistik-import',   icon: BarChart2 },
      { name: 'MQTT-Export',       href: '/einstellungen/ha-export',             icon: Radio },
    ],
  },
  {
    label: 'System',
    prefixes: [
      '/einstellungen/allgemein',
      '/einstellungen/backup',
      '/einstellungen/protokolle',
    ],
    tabs: [
      { name: 'Allgemein',   href: '/einstellungen/allgemein',   icon: Settings },
      { name: 'Backup',      href: '/einstellungen/backup',      icon: HardDrive },
      { name: 'Protokolle',  href: '/einstellungen/protokolle',  icon: ScrollText },
    ],
  },
  {
    label: 'Community',
    prefixes: [
      '/einstellungen/community',
    ],
    tabs: [
      { name: 'Daten teilen', href: '/einstellungen/community', icon: Share2 },
    ],
  },
]

export default function SubTabs() {
  const location = useLocation()
  const path = location.pathname
  const haAvailable = useHAAvailable()

  // ── Live (keine Sub-Tabs) ────────────────────────────────────────────────
  if (path.startsWith('/live')) return null

  // ── Cockpit ──────────────────────────────────────────────────────────────
  if (path.startsWith('/cockpit')) {
    return <CockpitTabBar />
  }

  // ── Auswertungen / Aussichten / Community (B1, route-getrieben) ──────────
  if (path.startsWith('/auswertungen')) {
    return <TabBar tabs={auswertungenTabs} ariaLabel="Auswertungen-Tabs" />
  }
  if (path.startsWith('/aussichten')) {
    return <TabBar tabs={aussichtenTabs} ariaLabel="Aussichten-Tabs" />
  }
  if (path.startsWith('/community')) {
    return <TabBar tabs={communityTabs} ariaLabel="Community-Tabs" />
  }

  // ── Einstellungen – gruppen-aware ────────────────────────────────────────
  if (path.startsWith('/einstellungen')) {
    // HA-Gruppe nur anzeigen wenn HA verfügbar
    const filteredGruppen = haAvailable
      ? einstellungenGruppen
      : einstellungenGruppen.filter(g => g.label !== 'Home Assistant')
    const gruppe = filteredGruppen.find(g =>
      g.prefixes.some(p => path.startsWith(p))
    ) ?? null
    if (!gruppe) return null
    return <TabBar tabs={gruppe.tabs} groupLabel={gruppe.label} />
  }

  return null
}

// ─── Cockpit Tab-Leiste (dynamisch nach Investitionen) ───────────────────────
function CockpitTabBar() {
  const { selectedAnlageId } = useSelectedAnlage()
  const { investitionen, loading } = useInvestitionen(selectedAnlageId)

  const vorhandeneTypen = new Set(investitionen.map(i => i.typ))

  const tabs = [
    ...cockpitBaseTabs,
    ...cockpitInvestitionTabs.filter(tab =>
      tab.typen.some(typ => vorhandeneTypen.has(typ))
    ),
  ]

  // Während dem Laden nur Basis-Tabs zeigen (kein Flicker)
  return <TabBar tabs={loading ? cockpitBaseTabs : tabs} />
}

// ─── Wiederverwendbare Tab-Leiste ─────────────────────────────────────────────
function TabBar({ tabs, groupLabel, ariaLabel }: { tabs: TabItem[]; groupLabel?: string; ariaLabel?: string }) {
  const navRef = useRef<HTMLElement>(null)
  const location = useLocation()

  // Aktiven Tab in den sichtbaren Bereich scrollen — wichtig auf Mobile,
  // damit z.B. "PV-Anlage" oder "Daten-Cleanup" nicht hinter dem rechten Rand bleiben.
  useEffect(() => {
    const active = navRef.current?.querySelector('a[aria-current="page"]') as HTMLElement | null
    if (active) {
      active.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'auto' })
    }
  }, [location.pathname, tabs.length])

  if (tabs.length === 0) return null

  return (
    <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
      <div className="px-4 sm:px-6">
        <nav ref={navRef} aria-label={ariaLabel ?? (groupLabel ? `${groupLabel}-Tabs` : 'Cockpit-Tabs')} className="flex items-center gap-1 py-2 overflow-x-auto snap-x snap-proximity scrollbar-none">
          {groupLabel && (
            <>
              <span className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide whitespace-nowrap pr-2">
                {groupLabel}
              </span>
              <span className="h-4 w-px bg-gray-300 dark:bg-gray-600 mr-2 shrink-0" />
            </>
          )}
          {tabs.map((tab) => {
            const link = (
              <NavLink
                key={tab.href}
                to={tab.href}
                end={tab.exact}
                className={({ isActive }) =>
                  `flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors snap-start ${
                    isActive
                      ? 'bg-white dark:bg-gray-800 text-primary-700 dark:text-primary-300 shadow-sm'
                      : 'text-gray-600 hover:bg-white/50 dark:text-gray-400 dark:hover:bg-gray-800/50'
                  }`
                }
              >
                <tab.icon className="h-4 w-4" />
                {tab.name}
                {tab.beta && (
                  <span className="rounded px-1 py-0.5 text-[10px] font-semibold leading-none bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">
                    Beta
                  </span>
                )}
              </NavLink>
            )
            return tab.tooltip ? (
              <SimpleTooltip key={tab.href} text={tab.tooltip}>
                {link}
              </SimpleTooltip>
            ) : (
              link
            )
          })}
        </nav>
      </div>
    </div>
  )
}
