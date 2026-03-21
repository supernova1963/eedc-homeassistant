/**
 * QuickLink: Navigations-Karte mit Titel und Beschreibung
 */

import { ArrowRight } from 'lucide-react'

export default function QuickLink({ title, description, onClick }: { title: string; description: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="card p-4 text-left hover:shadow-md transition-shadow group">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-gray-900 dark:text-white">{title}</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">{description}</p>
        </div>
        <ArrowRight className="h-5 w-5 text-gray-400 group-hover:text-primary-600 transition-colors" />
      </div>
    </button>
  )
}
