/**
 * KPICard Komponente
 * Zeigt eine Kennzahl mit Icon, optional mit Tooltip für Berechnungsdetails
 */

import Card from './Card'
import FormelTooltip from './FormelTooltip'
import { COLOR_CLASSES, type KomponentenColor } from '../../lib/komponentenStyle'

interface KPICardProps {
  title: string
  value: string | number
  unit?: string
  subtitle?: string
  icon: React.ElementType
  color?: KomponentenColor
  trend?: 'up' | 'down'
  // Tooltip für Berechnungsdetails
  formel?: string
  berechnung?: string
  ergebnis?: string
  sicht?: string
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
  sicht,
}: KPICardProps) {
  const colors = COLOR_CLASSES[color]

  const valueContent = (
    <span className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white whitespace-nowrap">
      {typeof value === 'number' ? value.toLocaleString('de-DE') : value}
      {unit && <span className="text-xs sm:text-sm font-normal ml-1">{unit}</span>}
      {trend === 'up' && <span className="ml-2 text-green-500">↑</span>}
      {trend === 'down' && <span className="ml-2 text-red-500">↓</span>}
    </span>
  )

  return (
    <Card>
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 truncate">{title}</p>
          <div className="mt-1">
            {formel ? (
              <FormelTooltip formel={formel} berechnung={berechnung} ergebnis={ergebnis} sicht={sicht}>
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
        <div className={`p-2 sm:p-3 rounded-xl ${colors.bg} ml-2 sm:ml-3 flex-shrink-0`}>
          <Icon className={`h-5 w-5 sm:h-6 sm:w-6 ${colors.text}`} />
        </div>
      </div>
    </Card>
  )
}
