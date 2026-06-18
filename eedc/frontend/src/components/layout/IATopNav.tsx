/**
 * IATopNav — geteilte IA-v4-Top-Nav-Schale (Struktur-SoT).
 *
 * EINE Quelle für die obere Leiste der IA-v4: konsumiert von der öffentlichen
 * Vorschau (`components/preview/IASkeleton`, state-getrieben) UND vom echten
 * /v4-Routenbaum (`v4/LayoutV4`, router-getrieben). Damit gibt es keine zwei
 * driftenden Nav-Kopien mehr (Konvergenz-Leitprinzip). Die Produktiv-
 * `components/layout/TopNavigation` bleibt mit ihren Produktiv-Spezifika
 * (Settings-Dropdown, Monatsabschluss-Badge, HA-Verfügbarkeit) bis zum Flip 3.8
 * separat.
 *
 * Enthält fest: Produktiv-Marke (`eedc-icon.svg` + Wortmarke), Hell/Dunkel/
 * System-Theme-Cycle (Bestands-Muster aus `TopNavigation`/`Header`), Hamburger +
 * `lg`-Responsive, primary-getönte aktive Tabs. `h-14` = Höhe der 2. Leiste.
 *
 * Dual-API je Eintrag: `to` → `NavLink` (Routen, v4) · sonst `onClick`+`active`
 * (State, Vorschau). `active` darf bei `to`-Einträgen die NavLink-Auto-Erkennung
 * übersteuern (Achsen-Aktivität via `pathname.startsWith`).
 */
import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Moon, Sun, Monitor, Menu, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useTheme } from '../../context/ThemeContext'
import eedcIcon from '../../assets/eedc-icon.svg'

export interface IANavItem {
  key: string
  label: string
  /** Optionales Icon (Top-Nav-Achsen tragen eines; Sub-Tabs nicht). */
  icon?: LucideIcon
  /** Routen-Ziel (v4). Wenn gesetzt → NavLink, sonst Button. */
  to?: string
  /** State-Handler (Vorschau) bzw. zusätzliche Aktion. */
  onClick?: () => void
  /** Explizite Aktivität (übersteuert NavLink-Auto-Erkennung; Achsen-Level). */
  active?: boolean
}

const navCls = (aktiv: boolean) =>
  `min-h-[44px] flex items-center gap-2 px-3 rounded-lg text-sm font-medium transition-colors ${
    aktiv
      ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
      : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
  }`

function NavEntry({ item, onNavigate }: { item: IANavItem; onNavigate?: () => void }) {
  const Icon = item.icon
  const inhalt = (
    <>
      {Icon && <Icon className="h-4 w-4" />}
      {item.label}
    </>
  )
  if (item.to) {
    return (
      <NavLink
        to={item.to}
        onClick={onNavigate}
        className={item.active !== undefined ? () => navCls(item.active!) : ({ isActive }) => navCls(isActive)}
      >
        {inhalt}
      </NavLink>
    )
  }
  return (
    <button
      type="button"
      onClick={() => { item.onClick?.(); onNavigate?.() }}
      className={navCls(!!item.active)}
    >
      {inhalt}
    </button>
  )
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const cycle = () => setTheme(theme === 'light' ? 'dark' : theme === 'dark' ? 'system' : 'light')
  return (
    <button
      type="button"
      onClick={cycle}
      className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700 transition-colors"
      aria-label={`Theme: ${theme}`}
      title={`Theme: ${theme === 'light' ? 'Hell' : theme === 'dark' ? 'Dunkel' : 'System'}`}
    >
      {theme === 'light' && <Sun className="h-5 w-5" />}
      {theme === 'dark' && <Moon className="h-5 w-5" />}
      {theme === 'system' && <Monitor className="h-5 w-5" />}
    </button>
  )
}

export function IATopNav({
  inhalt,
  meta,
  modusBadge,
}: {
  inhalt: IANavItem[]
  meta: IANavItem[]
  /** Optionale Modus-Kennung (z. B. „Vorschau") — reine Markierung, kein Design-Ziel. */
  modusBadge?: React.ReactNode
}) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const alle = [...inhalt, ...meta]
  const closeMobile = () => setMobileOpen(false)

  return (
    <header className="flex-shrink-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
      <div className="max-w-[1920px] mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-3">
        {/* Produktiv-Marke (Bestand) + Achsen */}
        <div className="flex items-center min-w-0">
          <img src={eedcIcon} alt="eedc" className="h-10 w-10 shrink-0" />
          <span className="ml-2 text-xl font-bold text-gray-900 dark:text-white">eedc</span>
          {modusBadge}
          <nav aria-label="Hauptnavigation" className="ml-6 hidden lg:flex items-center gap-1">
            {inhalt.map((t) => <NavEntry key={t.key} item={t} onNavigate={closeMobile} />)}
          </nav>
        </div>

        {/* Rechts: Meta-Gruppe (Trenner) + Theme (Desktop) */}
        <div className="hidden lg:flex items-center gap-1">
          {meta.map((t) => <NavEntry key={t.key} item={t} onNavigate={closeMobile} />)}
          <span className="h-5 w-px bg-gray-300 dark:bg-gray-600 mx-1" />
          <ThemeToggle />
        </div>

        {/* Hamburger (Mobile) */}
        <button
          type="button"
          onClick={() => setMobileOpen(!mobileOpen)}
          className="lg:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
          aria-label="Menü"
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {/* Mobile-Menü (M0 Hamburger) — alle Achsen + Meta + Theme */}
      {mobileOpen && (
        <nav aria-label="Hauptnavigation mobil" className="lg:hidden border-t border-gray-200 dark:border-gray-700 px-4 py-3 space-y-1">
          {alle.map((t) => <NavEntry key={t.key} item={t} onNavigate={closeMobile} />)}
          <div className="pt-1"><ThemeToggle /></div>
        </nav>
      )}
    </header>
  )
}
