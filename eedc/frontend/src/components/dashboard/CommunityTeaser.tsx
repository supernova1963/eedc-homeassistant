/**
 * Community-Teaser: Link zum Community-Benchmark
 */

import { useNavigate } from 'react-router-dom'
import { Trophy, ChevronRight } from 'lucide-react'

export default function CommunityTeaser() {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate('/community')}
      className="w-full text-left card p-4 border border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-900/20 hover:shadow-md transition-shadow group"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-yellow-100 dark:bg-yellow-800/50 rounded-lg">
            <Trophy className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
          </div>
          <div>
            <p className="text-sm font-medium text-yellow-900 dark:text-yellow-100">Community-Vergleich aktiv</p>
            <p className="text-xs text-yellow-700 dark:text-yellow-300">Deine Anlage wird mit anderen verglichen → Benchmark ansehen</p>
          </div>
        </div>
        <ChevronRight className="h-4 w-4 text-yellow-500 group-hover:text-yellow-700 transition-colors flex-shrink-0" />
      </div>
    </button>
  )
}
