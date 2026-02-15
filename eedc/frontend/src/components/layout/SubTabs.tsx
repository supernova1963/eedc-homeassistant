/**
 * SubTabs Komponente
 * Zeigt kontextabhängige Sub-Navigation unter der Hauptnavigation
 */

import { NavLink, useLocation } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
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
  Settings
} from 'lucide-react'

interface TabItem {
  name: string
  href: string
  icon: LucideIcon
  exact?: boolean
}

// Sub-Tabs für Cockpit
const cockpitTabs: TabItem[] = [
  { name: 'Übersicht', href: '/cockpit', icon: LayoutDashboard, exact: true },
  { name: 'PV-Anlage', href: '/cockpit/pv-anlage', icon: Sun },
  { name: 'E-Auto', href: '/cockpit/e-auto', icon: Car },
  { name: 'Wärmepumpe', href: '/cockpit/waermepumpe', icon: Flame },
  { name: 'Speicher', href: '/cockpit/speicher', icon: Battery },
  { name: 'Wallbox', href: '/cockpit/wallbox', icon: Plug },
  { name: 'Balkonkraftwerk', href: '/cockpit/balkonkraftwerk', icon: Sun },
  { name: 'Sonstiges', href: '/cockpit/sonstiges', icon: Wrench },
]

// Sub-Tabs für Auswertungen (leer, da Auswertung.tsx eigene Inline-Tabs hat)
const auswertungenTabs: TabItem[] = []

// Sub-Tabs für Einstellungen
// Logische Gruppierung: Stammdaten → Daten → System
const einstellungenTabs: TabItem[] = [
  // Stammdaten
  { name: 'Anlage', href: '/einstellungen/anlage', icon: Home },
  { name: 'Strompreise', href: '/einstellungen/strompreise', icon: Zap },
  { name: 'Investitionen', href: '/einstellungen/investitionen', icon: PiggyBank },
  // Daten
  { name: 'Monatsdaten', href: '/einstellungen/monatsdaten', icon: Database },
  { name: 'Import/Export', href: '/einstellungen/import', icon: Upload },
  // System
  { name: 'Solarprognose', href: '/einstellungen/solarprognose', icon: Sun },
  { name: 'Allgemein', href: '/einstellungen/allgemein', icon: Settings },
]

export default function SubTabs() {
  const location = useLocation()

  // Bestimme welche Tabs angezeigt werden sollen
  const getTabs = () => {
    if (location.pathname.startsWith('/cockpit')) return cockpitTabs
    if (location.pathname.startsWith('/auswertungen')) return auswertungenTabs
    if (location.pathname.startsWith('/einstellungen')) return einstellungenTabs
    return null
  }

  const tabs = getTabs()

  // Keine Sub-Tabs für andere Seiten
  if (!tabs) return null

  return (
    <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
      <div className="px-4 sm:px-6">
        <nav className="flex space-x-1 py-2 overflow-x-auto">
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
