/**
 * Community-Nudge: Einladung zum anonymen Datenteilen.
 * Wird angezeigt wenn community_hash leer ist. Einmal wegklickbar (localStorage).
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Users, ChevronRight, X } from 'lucide-react'

const STORAGE_KEY = 'eedc_community_nudge_dismissed'

export default function CommunityNudge() {
  const navigate = useNavigate()
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(STORAGE_KEY) === '1'
  )

  if (dismissed) return null

  const handleDismiss = (e: React.MouseEvent) => {
    e.stopPropagation()
    localStorage.setItem(STORAGE_KEY, '1')
    setDismissed(true)
  }

  return (
    <button
      onClick={() => navigate('/einstellungen/community')}
      className="w-full text-left card p-4 border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 hover:shadow-md transition-shadow group relative"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-100 dark:bg-blue-800/50 rounded-lg">
            <Users className="h-5 w-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div className="pr-6">
            <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
              Community-Benchmark: Wie gut ist deine Anlage?
            </p>
            <p className="text-xs text-blue-700 dark:text-blue-300">
              Teile deine Daten anonym und vergleiche dich mit anderen PV-Anlagen in deiner Region.
            </p>
          </div>
        </div>
        <ChevronRight className="h-4 w-4 text-blue-500 group-hover:text-blue-700 transition-colors flex-shrink-0" />
      </div>
      <button
        onClick={handleDismiss}
        className="absolute top-2 right-2 p-1 text-blue-400 hover:text-blue-600 dark:hover:text-blue-300 rounded"
        title="Nicht mehr anzeigen"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </button>
  )
}
