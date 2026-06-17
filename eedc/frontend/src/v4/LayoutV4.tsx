/**
 * LayoutV4 — eigene Schale für den IA-v4-Vorschau-Routenbaum (`/v4/…`).
 *
 * Bewusst PARALLEL zum Produktiv-`components/layout/Layout`: kein Eingriff in
 * den Bestandsbaum. Nur hinter dem Build-Flag `VITE_IA_V4` gemountet
 * ([[flags.ts]] + `App.tsx`). Slice 1 = schlanke Top-Achse (Inhalts-Tabs) +
 * `<Outlet/>`; die volle Drei-Achsen-Nav folgt in späteren Slices, sobald die
 * #243-Achsen-Zuordnung steht.
 *
 * Mobile-Querschnitt wie im Skelett: `h-dvh`, Touch-Targets ≥ 44 px.
 */
import { NavLink, Outlet } from 'react-router-dom'
import { LayoutDashboard, BarChart3 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

// Inhalts-Achse (Struktur-SoT: KONZEPT-IA-V4). Real verdrahtet: Cockpit +
// Auswertungen/Werte-Tabelle; weitere Achsen folgen in späteren Slices.
const TOP: { key: string; label: string; to: string; icon: LucideIcon }[] = [
  { key: 'cockpit',      label: 'Cockpit',      to: '/v4/cockpit/monat',         icon: LayoutDashboard },
  { key: 'auswertungen', label: 'Auswertungen', to: '/v4/auswertungen/tabelle',  icon: BarChart3 },
]

export default function LayoutV4() {
  return (
    <div className="h-dvh bg-gray-50 dark:bg-gray-900 flex flex-col overflow-hidden">
      <header className="flex-shrink-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-[1920px] mx-auto px-3 sm:px-6 h-14 flex items-center gap-3">
          <span className="text-sm font-bold text-gray-900 dark:text-white">eedc</span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-primary-100 dark:bg-primary-900/50 text-primary-700 dark:text-primary-300 font-medium">
            IA v4 · Vorschau
          </span>
          <nav className="flex items-center gap-1 ml-2 overflow-x-auto scrollbar-none">
            {TOP.map((t) => (
              <NavLink
                key={t.key}
                to={t.to}
                className={({ isActive }) =>
                  `min-h-[44px] flex items-center gap-2 px-3 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
                    isActive
                      ? 'bg-gray-100 dark:bg-gray-700 text-primary-700 dark:text-primary-300'
                      : 'text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-700/50'
                  }`
                }
              >
                <t.icon className="h-4 w-4" />
                {t.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {/* Ab lg gibt main keine eigene Scroll-Leiste mehr her, sondern wird flex-
          Container für die ViewShell (fixe 2. Leiste). Mobile: alles scrollt. */}
      <main className="flex-1 overflow-auto lg:overflow-hidden lg:flex lg:flex-col lg:min-h-0">
        <Outlet />
      </main>
    </div>
  )
}
