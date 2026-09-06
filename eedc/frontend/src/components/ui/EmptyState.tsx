import { ReactNode } from 'react'
import { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: string
  action?: ReactNode
}

export default function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    // ⛔ Hier stand bis zum 2026-09-06 das Merkmal `data-leer-erklaert` (N-318, v4.0.4).
    // Sein einziger Leser war `check:park-leertest`: es unterschied für ihn „hier ist nichts
    // zu messen, und die Sicht sagt warum" von „hier wurde nichts gemessen". Mit der
    // Abschaffung des Leertests (ersetzt durch `check:park-gate` + `check:park-idliste`, die
    // am Quelltext arbeiten) war es ein Vertrag ohne Gegenpartei — **entfernt auf Entscheid
    // Gernot**. Die DOKTRIN bleibt: eine leere Sicht erklärt sich, und ein Fehler ist keine
    // erklärte Leere; das prüft `EmptyState.test.tsx` weiter an Titel und Grund.
    <div className="text-center py-12">
      <div className="mx-auto w-12 h-12 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mb-4">
        <Icon className="h-6 w-6 text-gray-400 dark:text-gray-500" />
      </div>
      <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
        {title}
      </h3>
      <p className="text-gray-500 dark:text-gray-400 mb-4 max-w-md mx-auto">
        {description}
      </p>
      {action && <div>{action}</div>}
    </div>
  )
}
