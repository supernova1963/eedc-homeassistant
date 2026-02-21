/**
 * TopNavigation Komponente
 * Hauptnavigation oben mit Logo, Tabs und Einstellungen-Dropdown
 */

import { useState, useRef, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Moon, Sun as SunIcon, Monitor, Settings, ChevronDown, LayoutDashboard, BarChart3, TrendingUp, Users } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useTheme } from '../../context/ThemeContext'
import eedcIcon from '../../assets/eedc-icon.svg'

// Haupttabs mit Icons
const mainTabs: { name: string; basePath: string; icon: LucideIcon }[] = [
  { name: 'Cockpit', basePath: '/cockpit', icon: LayoutDashboard },
  { name: 'Auswertungen', basePath: '/auswertungen', icon: BarChart3 },
  { name: 'Aussichten', basePath: '/aussichten', icon: TrendingUp },
  { name: 'Community', basePath: '/community', icon: Users },
]

// Einstellungen-Menü Struktur
const settingsMenu = [
  {
    category: 'Stammdaten',
    items: [
      { name: 'Anlage', href: '/einstellungen/anlage' },
      { name: 'Strompreise', href: '/einstellungen/strompreise' },
      { name: 'Investitionen', href: '/einstellungen/investitionen' },
    ],
  },
  {
    category: 'Daten',
    items: [
      { name: 'Monatsdaten', href: '/einstellungen/monatsdaten' },
      { name: 'Monatsabschluss', href: '/einstellungen/monatsabschluss' },
      { name: 'Import', href: '/einstellungen/import' },
      { name: 'Datenerfassung', href: '/einstellungen/datenerfassung' },
      { name: 'Demo-Daten', href: '/einstellungen/demo' },
    ],
  },
  {
    category: 'System',
    items: [
      { name: 'Solarprognose', href: '/einstellungen/solarprognose' },
      { name: 'Allgemein', href: '/einstellungen/allgemein' },
    ],
  },
  {
    category: 'Home Assistant',
    items: [
      { name: 'Sensor-Zuordnung', href: '/einstellungen/sensor-mapping' },
      { name: 'Statistik-Import', href: '/einstellungen/ha-statistik-import' },
      { name: 'MQTT-Export', href: '/einstellungen/ha-export' },
    ],
  },
  {
    category: 'Community',
    items: [
      { name: 'Daten teilen', href: '/einstellungen/community' },
    ],
  },
]

export default function TopNavigation() {
  const { theme, setTheme } = useTheme()
  const location = useLocation()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Bestimme aktiven Haupttab
  const getActiveMainTab = () => {
    if (location.pathname.startsWith('/cockpit')) return 'Cockpit'
    if (location.pathname.startsWith('/auswertungen')) return 'Auswertungen'
    if (location.pathname.startsWith('/aussichten')) return 'Aussichten'
    if (location.pathname.startsWith('/community')) return 'Community'
    if (location.pathname.startsWith('/einstellungen')) return null
    // Default: Cockpit
    return 'Cockpit'
  }

  const activeMainTab = getActiveMainTab()

  // Schließe Dropdown bei Klick außerhalb
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setSettingsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const cycleTheme = () => {
    if (theme === 'light') setTheme('dark')
    else if (theme === 'dark') setTheme('system')
    else setTheme('light')
  }

  // Prüfe ob ein Einstellungs-Item aktiv ist
  const isSettingsItemActive = (href: string) => location.pathname === href

  return (
    <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
      <div className="px-4 sm:px-6">
        <div className="flex items-center justify-between h-14">
          {/* Logo */}
          <div className="flex items-center">
            <img src={eedcIcon} alt="eedc" className="h-10 w-10" />
            <span className="ml-2 text-xl font-bold text-gray-900 dark:text-white">eedc</span>

            {/* Haupttabs */}
            <nav className="ml-8 flex space-x-1">
              {mainTabs.map((tab) => {
                const Icon = tab.icon
                return (
                  <NavLink
                    key={tab.name}
                    to={tab.basePath}
                    className={() =>
                      `flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                        activeMainTab === tab.name
                          ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                          : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                      }`
                    }
                  >
                    <Icon className="h-4 w-4" />
                    {tab.name}
                  </NavLink>
                )
              })}
            </nav>
          </div>

          {/* Rechte Seite: Theme + Einstellungen */}
          <div className="flex items-center gap-2">
            {/* Theme Toggle */}
            <button
              onClick={cycleTheme}
              className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700 transition-colors"
              title={`Theme: ${theme}`}
            >
              {theme === 'light' && <SunIcon className="h-5 w-5" />}
              {theme === 'dark' && <Moon className="h-5 w-5" />}
              {theme === 'system' && <Monitor className="h-5 w-5" />}
            </button>

            {/* Einstellungen Dropdown */}
            <div className="relative" ref={dropdownRef}>
              <button
                onClick={() => setSettingsOpen(!settingsOpen)}
                className={`flex items-center gap-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  location.pathname.startsWith('/einstellungen')
                    ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                    : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                }`}
              >
                <Settings className="h-4 w-4" />
                <span>Einstellungen</span>
                <ChevronDown className={`h-4 w-4 transition-transform ${settingsOpen ? 'rotate-180' : ''}`} />
              </button>

              {/* Dropdown Menu */}
              {settingsOpen && (
                <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-2 z-50">
                  {settingsMenu.map((section, idx) => (
                    <div key={section.category}>
                      {idx > 0 && <div className="my-2 border-t border-gray-200 dark:border-gray-700" />}
                      <div className="px-3 py-1">
                        <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                          {section.category}
                        </p>
                      </div>
                      {section.items.map((item) => (
                        <NavLink
                          key={item.href}
                          to={item.href}
                          onClick={() => setSettingsOpen(false)}
                          className={`block px-4 py-2 text-sm transition-colors ${
                            isSettingsItemActive(item.href)
                              ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                              : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                          }`}
                        >
                          {item.name}
                        </NavLink>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  )
}
