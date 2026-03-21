/**
 * Seitenüberschrift mit optionalen Selektoren und Action-Buttons.
 *
 * Konsistentes Layout für alle Seiten: Titel links, Steuerelemente rechts.
 */

interface PageHeaderProps {
  /** Seitentitel. */
  title: string
  /** Optionales Icon (React-Element, z.B. Lucide-Icon). */
  icon?: React.ReactNode
  /** Zusätzliche Elemente rechts (Dropdowns, Buttons). */
  children?: React.ReactNode
}

export default function PageHeader({ title, icon, children }: PageHeaderProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
        {icon}
        {title}
      </h1>
      {children && (
        <div className="flex items-center gap-2 flex-wrap">
          {children}
        </div>
      )}
    </div>
  )
}
