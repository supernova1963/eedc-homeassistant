/**
 * SubTabs Komponente
 * Zeigt kontextabhängige Sub-Navigation unter der Hauptnavigation
 *
 * Cockpit-Tabs werden dynamisch basierend auf vorhandenen Investitionen angezeigt.
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
import { useAnlagen, useInvestitionen } from '../../hooks'

interface TabItem {
  name: string
  href: string
  icon: LucideIcon
  exact?: boolean
}

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

/**
 * Hook für dynamische Cockpit-Tabs basierend auf vorhandenen Investitionen
 */
function useDynamicCockpitTabs(): TabItem[] {
  const { anlagen } = useAnlagen()
  const anlageId = anlagen[0]?.id
  const { investitionen } = useInvestitionen(anlageId)

  // Basis-Tabs (immer sichtbar)
  const baseTabs: TabItem[] = [
    { name: 'Übersicht', href: '/cockpit', icon: LayoutDashboard, exact: true },
  ]

  // PV-Anlage: Zeigen wenn Wechselrichter oder PV-Module vorhanden
  const hatPV = investitionen.some(i =>
    i.typ === 'wechselrichter' || i.typ === 'pv-module'
  )
  if (hatPV) {
    baseTabs.push({ name: 'PV-Anlage', href: '/cockpit/pv-anlage', icon: Sun })
  }

  // E-Auto
  const hatEAuto = investitionen.some(i => i.typ === 'e-auto')
  if (hatEAuto) {
    baseTabs.push({ name: 'E-Auto', href: '/cockpit/e-auto', icon: Car })
  }

  // Wärmepumpe
  const hatWP = investitionen.some(i => i.typ === 'waermepumpe')
  if (hatWP) {
    baseTabs.push({ name: 'Wärmepumpe', href: '/cockpit/waermepumpe', icon: Flame })
  }

  // Speicher (AC-Speicher oder DC-Speicher an Wechselrichter)
  const hatSpeicher = investitionen.some(i => i.typ === 'speicher')
  if (hatSpeicher) {
    baseTabs.push({ name: 'Speicher', href: '/cockpit/speicher', icon: Battery })
  }

  // Wallbox
  const hatWallbox = investitionen.some(i => i.typ === 'wallbox')
  if (hatWallbox) {
    baseTabs.push({ name: 'Wallbox', href: '/cockpit/wallbox', icon: Plug })
  }

  // Balkonkraftwerk
  const hatBKW = investitionen.some(i => i.typ === 'balkonkraftwerk')
  if (hatBKW) {
    baseTabs.push({ name: 'Balkonkraftwerk', href: '/cockpit/balkonkraftwerk', icon: Sun })
  }

  // Sonstiges
  const hatSonstiges = investitionen.some(i => i.typ === 'sonstiges')
  if (hatSonstiges) {
    baseTabs.push({ name: 'Sonstiges', href: '/cockpit/sonstiges', icon: Wrench })
  }

  return baseTabs
}

export default function SubTabs() {
  const location = useLocation()
  const dynamicCockpitTabs = useDynamicCockpitTabs()

  // Bestimme welche Tabs angezeigt werden sollen
  const getTabs = () => {
    if (location.pathname.startsWith('/cockpit')) return dynamicCockpitTabs
    if (location.pathname.startsWith('/auswertungen')) return auswertungenTabs
    if (location.pathname.startsWith('/einstellungen')) return einstellungenTabs
    return null
  }

  const tabs = getTabs()

  // Keine Sub-Tabs für andere Seiten
  if (!tabs || tabs.length === 0) return null

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
