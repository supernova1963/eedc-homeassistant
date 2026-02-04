/**
 * Layout Komponente
 * Neues Layout mit TopNavigation und SubTabs (ohne Sidebar)
 */

import { Outlet } from 'react-router-dom'
import TopNavigation from './TopNavigation'
import SubTabs from './SubTabs'

export default function Layout() {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col">
      {/* Top Navigation */}
      <TopNavigation />

      {/* Sub-Tabs (kontextabhängig) */}
      <SubTabs />

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="py-2 px-6 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <p className="text-xs text-gray-500 dark:text-gray-400 text-center">
          EEDC v0.1.0 – Energie Effizienz Data Center
        </p>
      </footer>
    </div>
  )
}
