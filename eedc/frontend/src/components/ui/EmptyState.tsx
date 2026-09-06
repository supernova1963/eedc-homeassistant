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
    // `data-leer-erklaert` ist das DOM-Merkmal der Doktrin „Leere Sichten erklären sich"
    // (v4.0.4) — dieselbe Bauform wie `data-park-id`: ein Prüfer entdeckt es selbst und
    // braucht keine gepflegte Sichtenliste. Es unterscheidet „hier ist nichts zu messen,
    // und die Sicht sagt warum" von „hier wurde nichts gemessen" (N-318).
    // Bewusst NICHT an `FehlerZustand`: ein Fehler erklärt keine legitime Leere.
    //
    // ⚠ **Sein Leser ist am 2026-09-06 entfallen** — `check:park-leertest` ist durch
    // `check:park-gate` und `check:park-idliste` ersetzt, und die arbeiten am Quelltext
    // statt am gerenderten DOM. Das Merkmal steht damit ohne aktuellen Konsumenten; es
    // bleibt, weil es die Semantik der Sicht trägt und nichts kostet, aber wer es künftig
    // anfasst, weiß: es schützt gerade kein Gate mehr.
    <div className="text-center py-12" data-leer-erklaert>
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
