// Gemeinsame KPI Card Komponente für alle Tabs
import { Card, FormelTooltip } from '../../components/ui'

interface KPICardProps {
  title: string
  value: string
  unit: string
  subtitle?: string
  icon: React.ElementType
  color: string
  bgColor: string
  // Tooltip-Props
  formel?: string
  berechnung?: string
  ergebnis?: string
  sicht?: string
}

export function KPICard({ title, value, unit, subtitle, icon: Icon, color, bgColor, formel, berechnung, ergebnis, sicht }: KPICardProps) {
  const valueContent = (
    <span className="text-2xl font-bold text-gray-900 dark:text-white">
      {value} <span className="text-sm font-normal">{unit}</span>
    </span>
  )

  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
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
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{subtitle}</p>
          )}
        </div>
        <div className={`p-3 rounded-xl ${bgColor}`}>
          <Icon className={`h-6 w-6 ${color}`} />
        </div>
      </div>
    </Card>
  )
}
