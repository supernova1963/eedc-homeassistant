/**
 * Section + SectionLink: Abschnitts-Container mit Icon-Titel
 */

import { ChevronRight } from 'lucide-react'

export default function Section({ title, icon: Icon, children }: {
  title: string; icon: React.ElementType; children: React.ReactNode
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Icon className="h-5 w-5 text-gray-500" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
      </div>
      {children}
    </div>
  )
}

export function SectionLink({ title, icon: Icon, onClick, children }: {
  title: string; icon: React.ElementType; onClick: () => void; children: React.ReactNode
}) {
  return (
    <div className="space-y-3">
      <button onClick={onClick} className="flex items-center gap-2 group hover:opacity-80 transition-opacity">
        <Icon className="h-5 w-5 text-gray-500" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
        <ChevronRight className="h-4 w-4 text-gray-400 group-hover:text-primary-500 transition-colors" />
      </button>
      {children}
    </div>
  )
}
