/**
 * Layout Komponente
 * Neues Layout mit TopNavigation und SubTabs (ohne Sidebar)
 */

import { useState, useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { ArrowUpCircle, X } from 'lucide-react'
import TopNavigation from './TopNavigation'
import SubTabs from './SubTabs'
import { FULL_VERSION_STRING } from '../../config/version'
import { systemApi, type UpdateCheckResponse } from '../../api'

const DISMISSED_KEY = 'eedc_update_dismissed_version'

export default function Layout() {
  const [update, setUpdate] = useState<UpdateCheckResponse | null>(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    systemApi.checkUpdate().then((data) => {
      if (data.update_verfuegbar && data.neueste_version) {
        const dismissedVersion = localStorage.getItem(DISMISSED_KEY)
        if (dismissedVersion === data.neueste_version) {
          setDismissed(true)
        }
        setUpdate(data)
      }
    }).catch(() => {
      // Silently ignore — kein Update-Check möglich
    })
  }, [])

  const handleDismiss = () => {
    if (update?.neueste_version) {
      localStorage.setItem(DISMISSED_KEY, update.neueste_version)
    }
    setDismissed(true)
  }

  const showBanner = update?.update_verfuegbar && !dismissed

  return (
    <div className="h-screen bg-gray-50 dark:bg-gray-900 flex flex-col overflow-hidden">
      {/* Top Navigation */}
      <TopNavigation />

      {/* Update Banner */}
      {showBanner && (
        <div className="bg-blue-50 dark:bg-blue-900/30 border-b border-blue-200 dark:border-blue-800 px-4 py-3">
          <div className="flex items-start gap-3 max-w-5xl mx-auto">
            <ArrowUpCircle className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1 text-sm text-blue-700 dark:text-blue-300">
              <p className="font-medium">
                eedc v{update!.neueste_version} ist verfügbar
                <span className="font-normal text-blue-600 dark:text-blue-400"> (aktuell: v{update!.aktuelle_version})</span>
              </p>
              <div className="mt-1.5 text-xs text-blue-600 dark:text-blue-400 space-y-0.5">
                <p>Je nach Installation:</p>
                <p className="font-mono">• Docker: docker-compose pull && docker-compose up -d</p>
                <p className="font-mono">• Home Assistant Add-on: Update über Einstellungen → Add-ons</p>
                <p className="font-mono">• Manuell (Git): git pull && cd frontend && npm run build</p>
              </div>
              {update!.release_url && (
                <a
                  href={update!.release_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block mt-1.5 text-xs font-medium text-blue-700 dark:text-blue-200 underline hover:no-underline"
                >
                  Release Notes auf GitHub →
                </a>
              )}
            </div>
            <button
              onClick={handleDismiss}
              className="text-blue-400 hover:text-blue-600 dark:hover:text-blue-200 transition-colors"
              title="Schließen"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Sub-Tabs (kontextabhängig) */}
      <SubTabs />

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="py-2 px-6 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <p className="text-xs text-gray-500 dark:text-gray-400 text-center">
          {FULL_VERSION_STRING}
        </p>
      </footer>
    </div>
  )
}
