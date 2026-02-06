import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Building2,
  CalendarDays,
  Zap,
  PiggyBank,
  BarChart3,
  TrendingUp,
  Upload,
  Settings,
  Sun,
  Car,
  Flame,
  Battery,
  Plug
} from 'lucide-react'
import { VERSION_STRING } from '../../config/version'

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Anlagen', href: '/anlagen', icon: Building2 },
  { name: 'Monatsdaten', href: '/monatsdaten', icon: CalendarDays },
  { name: 'Strompreise', href: '/strompreise', icon: Zap },
  { name: 'Investitionen', href: '/investitionen', icon: PiggyBank },
  { name: 'ROI-Dashboard', href: '/roi', icon: TrendingUp },
  { name: 'Auswertung', href: '/auswertung', icon: BarChart3 },
]

const investitionsDashboards = [
  { name: 'E-Auto', href: '/e-auto', icon: Car },
  { name: 'Wärmepumpe', href: '/waermepumpe', icon: Flame },
  { name: 'Speicher', href: '/speicher', icon: Battery },
  { name: 'Wallbox', href: '/wallbox', icon: Plug },
]

const secondaryNavigation = [
  { name: 'Import', href: '/import', icon: Upload },
  { name: 'Einstellungen', href: '/settings', icon: Settings },
]

export default function Sidebar() {
  return (
    <aside className="w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex flex-col">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-gray-200 dark:border-gray-700">
        <Sun className="h-8 w-8 text-energy-solar" />
        <span className="ml-3 text-xl font-bold text-gray-900 dark:text-white">
          eedc
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navigation.map((item) => (
          <NavLink
            key={item.name}
            to={item.href}
            className={({ isActive }) =>
              `flex items-center px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                  : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
              }`
            }
          >
            <item.icon className="h-5 w-5 mr-3" />
            {item.name}
          </NavLink>
        ))}

        {/* Investitions-Dashboards */}
        <div className="pt-4 mt-4 border-t border-gray-200 dark:border-gray-700">
          <p className="px-3 mb-2 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
            Investitionen
          </p>
          {investitionsDashboards.map((item) => (
            <NavLink
              key={item.name}
              to={item.href}
              className={({ isActive }) =>
                `flex items-center px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                    : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                }`
              }
            >
              <item.icon className="h-5 w-5 mr-3" />
              {item.name}
            </NavLink>
          ))}
        </div>

        {/* Secondary Navigation */}
        <div className="pt-4 mt-4 border-t border-gray-200 dark:border-gray-700">
          {secondaryNavigation.map((item) => (
            <NavLink
              key={item.name}
              to={item.href}
              className={({ isActive }) =>
                `flex items-center px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                    : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                }`
              }
            >
              <item.icon className="h-5 w-5 mr-3" />
              {item.name}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-gray-200 dark:border-gray-700">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {VERSION_STRING}
        </p>
      </div>
    </aside>
  )
}
