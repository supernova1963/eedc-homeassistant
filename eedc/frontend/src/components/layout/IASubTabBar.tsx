/**
 * IASubTabBar — geteilte 2. Leiste der IA-v4 (Sub-Tabs, Struktur-SoT).
 *
 * EINE Quelle für die Sub-Tab-Leiste, konsumiert von Vorschau (`IASkeleton`,
 * state-getrieben) und echtem /v4 (`CockpitV4` u. a., router-getrieben) — siehe
 * {@link IATopNav}. `h-14` = Höhe der 1. Leiste; primary-getönte aktive Tabs.
 *
 * Dual-API je Eintrag wie {@link IANavItem}: `to` → NavLink, sonst `onClick`+`active`.
 */
import { NavLink } from 'react-router-dom'
import type { IANavItem } from './IATopNav'

const tabCls = (aktiv: boolean) =>
  `min-h-[44px] flex items-center px-3 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
    aktiv
      ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
      : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800/50'
  }`

export function IASubTabBar({ items }: { items: IANavItem[] }) {
  return (
    <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-3 sm:px-6">
      <nav className="flex items-center gap-1 h-14 overflow-x-auto scrollbar-none max-w-[1920px] mx-auto">
        {items.map((t) =>
          t.to ? (
            <NavLink
              key={t.key}
              to={t.to}
              className={t.active !== undefined ? () => tabCls(t.active!) : ({ isActive }) => tabCls(isActive)}
            >
              {t.label}
            </NavLink>
          ) : (
            <button key={t.key} type="button" onClick={t.onClick} className={tabCls(!!t.active)}>
              {t.label}
            </button>
          ),
        )}
      </nav>
    </div>
  )
}
