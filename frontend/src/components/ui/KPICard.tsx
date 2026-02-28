/**
 * KPICard Komponente
 * Zeigt eine Kennzahl mit Icon, optional mit Tooltip für Berechnungsdetails
 */

import Card from './Card'
import FormelTooltip from './FormelTooltip'

interface KPICardProps {
  title: string
  value: string | number
  unit?: string
  subtitle?: string
  icon: React.ElementType
  color?: 'blue' | 'green' | 'yellow' | 'red' | 'purple' | 'orange' | 'gray'
  trend?: 'up' | 'down'
  // Tooltip für Berechnungsdetails
  formel?: string
  berechnung?: string
  ergebnis?: string
}

const colorClasses = {
  blue: { icon: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-900/20' },
  green: { icon: 'text-green-500', bg: 'bg-green-50 dark:bg-green-900/20' },
  yellow: { icon: 'text-yellow-500', bg: 'bg-yellow-50 dark:bg-yellow-900/20' },
  red: { icon: 'text-red-500', bg: 'bg-red-50 dark:bg-red-900/20' },
  purple: { icon: 'text-purple-500', bg: 'bg-purple-50 dark:bg-purple-900/20' },
  orange: { icon: 'text-orange-500', bg: 'bg-orange-50 dark:bg-orange-900/20' },
  gray: { icon: 'text-gray-500', bg: 'bg-gray-50 dark:bg-gray-800' },
}

export function KPICard({
  title,
  value,
  unit,
  subtitle,
  icon: Icon,
  color = 'blue',
  trend,
  formel,
  berechnung,
  ergebnis,
}: KPICardProps) {
  const colors = colorClasses[color]

  const valueContent = (
    <span className="text-2xl font-bold text-gray-900 dark:text-white">
      {typeof value === 'number' ? value.toLocaleString('de-DE') : value}
      {unit && <span className="text-sm font-normal ml-1">{unit}</span>}
      {trend === 'up' && <span className="ml-2 text-green-500">↑</span>}
      {trend === 'down' && <span className="ml-2 text-red-500">↓</span>}
    </span>
  )

  return (
    <Card>
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{title}</p>
          <div className="mt-1">
            {formel ? (
              <FormelTooltip formel={formel} berechnung={berechnung} ergebnis={ergebnis}>
                {valueContent}
              </FormelTooltip>
            ) : (
              valueContent
            )}
          </div>
          {subtitle && (
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 truncate">{subtitle}</p>
          )}
        </div>
        <div className={`p-3 rounded-xl ${colors.bg} ml-3 flex-shrink-0`}>
          <Icon className={`h-6 w-6 ${colors.icon}`} />
        </div>
      </div>
    </Card>
  )
}
