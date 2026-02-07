/**
 * SubTabs Komponente
 * Zeigt kontextabhängige Sub-Navigation unter der Hauptnavigation
 */

import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Car,
  Flame,
  Battery,
  Plug,
  Sun,
  Wrench,
  BarChart3,
  TrendingUp,
  FileText
} from 'lucide-react'

// Sub-Tabs für Cockpit
const cockpitTabs = [
  { name: 'Übersicht', href: '/cockpit', icon: LayoutDashboard, exact: true },
  { name: 'E-Auto', href: '/cockpit/e-auto', icon: Car },
  { name: 'Wärmepumpe', href: '/cockpit/waermepumpe', icon: Flame },
  { name: 'Speicher', href: '/cockpit/speicher', icon: Battery },
  { name: 'Wallbox', href: '/cockpit/wallbox', icon: Plug },
  { name: 'Balkonkraftwerk', href: '/cockpit/balkonkraftwerk', icon: Sun },
  { name: 'Sonstiges', href: '/cockpit/sonstiges', icon: Wrench },
]

// Sub-Tabs für Auswertungen
const auswertungenTabs = [
  { name: 'Jahresvergleich', href: '/auswertungen', icon: BarChart3, exact: true },
  { name: 'ROI-Analyse', href: '/auswertungen/roi', icon: TrendingUp },
  { name: 'Prognose vs. IST', href: '/auswertungen/prognose', icon: TrendingUp },
  { name: 'PDF-Export', href: '/auswertungen/export', icon: FileText },
]

export default function SubTabs() {
  const location = useLocation()

  // Bestimme welche Tabs angezeigt werden sollen
  const getTabs = () => {
    if (location.pathname.startsWith('/cockpit')) return cockpitTabs
    if (location.pathname.startsWith('/auswertungen')) return auswertungenTabs
    return null
  }

  const tabs = getTabs()

  // Keine Sub-Tabs für Einstellungen
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
