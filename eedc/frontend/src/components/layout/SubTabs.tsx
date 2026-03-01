/**
 * SubTabs Komponente
 * Zeigt kontextabhängige Sub-Navigation unter der Hauptnavigation.
 * Einstellungen: gruppen-aware – zeigt alle Tabs der aktuellen Gruppe.
 */

import { NavLink, useLocation } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import { useHAAvailable } from '../../hooks/useHAAvailable'
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
  Upload,
  Settings,
  CalendarCheck,
  BookOpen,
  FlaskConical,
  Cpu,
  Radio,
  BarChart2,
  Share2,
  MapPin,
  HardDrive,
} from 'lucide-react'

interface TabItem {
  name: string
  href: string
  icon: LucideIcon
  exact?: boolean
}

interface TabGroup {
  label: string
  tabs: TabItem[]
  /** Pfad-Präfixe, die zu dieser Gruppe gehören */
  prefixes: string[]
}

// ─── Cockpit Tabs (statisch) ─────────────────────────────────────────────────
const cockpitTabs: TabItem[] = [
  { name: 'Übersicht',       href: '/cockpit',                  icon: LayoutDashboard, exact: true },
  { name: 'PV-Anlage',       href: '/cockpit/pv-anlage',        icon: Sun },
  { name: 'E-Auto',          href: '/cockpit/e-auto',           icon: Car },
  { name: 'Wärmepumpe',      href: '/cockpit/waermepumpe',      icon: Flame },
  { name: 'Speicher',        href: '/cockpit/speicher',         icon: Battery },
  { name: 'Wallbox',         href: '/cockpit/wallbox',          icon: Plug },
  { name: 'Balkonkraftwerk', href: '/cockpit/balkonkraftwerk',  icon: Sun },
  { name: 'Sonstiges',       href: '/cockpit/sonstiges',        icon: Wrench },
]

// ─── Einstellungen-Gruppen ────────────────────────────────────────────────────
const einstellungenGruppen: TabGroup[] = [
  {
    label: 'Stammdaten',
    prefixes: [
      '/einstellungen/anlage',
      '/einstellungen/strompreise',
      '/einstellungen/investitionen',
    ],
    tabs: [
      { name: 'Anlage',        href: '/einstellungen/anlage',        icon: Home },
      { name: 'Strompreise',   href: '/einstellungen/strompreise',   icon: Zap },
      { name: 'Investitionen', href: '/einstellungen/investitionen', icon: PiggyBank },
    ],
  },
  {
    label: 'Daten',
    prefixes: [
      '/einstellungen/monatsdaten',
      '/einstellungen/monatsabschluss',
      '/einstellungen/import',
      '/einstellungen/demo',
      '/einstellungen/datenerfassung',
    ],
    tabs: [
      { name: 'Monatsdaten',     href: '/einstellungen/monatsdaten',     icon: Database },
      { name: 'Monatsabschluss', href: '/einstellungen/monatsabschluss', icon: CalendarCheck },
      { name: 'Import/Export',   href: '/einstellungen/import',          icon: Upload },
      { name: 'Demo-Daten',      href: '/einstellungen/demo',            icon: FlaskConical },
      { name: 'Datenerfassung',  href: '/einstellungen/datenerfassung',  icon: BookOpen },
    ],
  },
  {
    label: 'System',
    prefixes: [
      '/einstellungen/solarprognose',
      '/einstellungen/allgemein',
      '/einstellungen/backup',
    ],
    tabs: [
      { name: 'Solarprognose', href: '/einstellungen/solarprognose', icon: Cpu },
      { name: 'Allgemein',     href: '/einstellungen/allgemein',     icon: Settings },
      { name: 'Backup',        href: '/einstellungen/backup',        icon: HardDrive },
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

  // ── Cockpit ──────────────────────────────────────────────────────────────
  if (path.startsWith('/cockpit')) {
    return <TabBar tabs={cockpitTabs} />
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

// ─── Wiederverwendbare Tab-Leiste ─────────────────────────────────────────────
function TabBar({ tabs, groupLabel }: { tabs: TabItem[]; groupLabel?: string }) {
  if (tabs.length === 0) return null

  return (
    <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
      <div className="px-4 sm:px-6">
        <nav className="flex items-center gap-1 py-2 overflow-x-auto">
          {groupLabel && (
            <>
              <span className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide whitespace-nowrap pr-2">
                {groupLabel}
              </span>
              <span className="h-4 w-px bg-gray-300 dark:bg-gray-600 mr-2 shrink-0" />
            </>
          )}
          {tabs.map((tab) => (
            <NavLink
              key={tab.href}
              to={tab.href}
              end={tab.exact}
              className={({ isActive }) =>
                `flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
                  isActive
                    ? 'bg-white dark:bg-gray-800 text-primary-700 dark:text-primary-300 shadow-sm'
                    : 'text-gray-600 hover:bg-white/50 dark:text-gray-400 dark:hover:bg-gray-800/50'
                }`
              }
            >
              <tab.icon className="h-4 w-4" />
              {tab.name}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  )
}
