/**
 * Dashboard KPICard: Kennzahl-Karte mit frei wählbaren Farb-Klassen
 *
 * Hinweis: Dies ist die Dashboard-spezifische Version mit string-basierten
 * color/bgColor Props. Die generische Version liegt in components/ui/KPICard.tsx.
 */

import { Card, FormelTooltip } from '../../components/ui'

export interface KPICardProps {
  title: string; value: string; unit: string; subtitle?: string
  icon: React.ElementType; color: string; bgColor: string
  onClick?: () => void; formel?: string; berechnung?: string; ergebnis?: string
}

export default function KPICard({ title, value, unit, subtitle, icon: Icon, color, bgColor, onClick, formel, berechnung, ergebnis }: KPICardProps) {
  const valueContent = (
    <span className="text-xl font-bold text-gray-900 dark:text-white">
      {value} <span className="text-sm font-normal text-gray-500">{unit}</span>
    </span>
  )

  const content = (
    <div className="flex items-start justify-between">
      <div className="flex-1 min-w-0">
        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{title}</p>
        <div className="mt-0.5">
          {formel
            ? <FormelTooltip formel={formel} berechnung={berechnung} ergebnis={ergebnis}>{valueContent}</FormelTooltip>
            : valueContent
          }
        </div>
        {subtitle && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate">{subtitle}</p>}
      </div>
      <div className={`p-2 rounded-lg ${bgColor} ml-2 flex-shrink-0`}>
        <Icon className={`h-5 w-5 ${color}`} />
      </div>
    </div>
  )

  if (onClick) {
    return <button onClick={onClick} className="card p-3 text-left hover:shadow-md transition-shadow w-full">{content}</button>
  }
  return <Card className="p-3">{content}</Card>
}
