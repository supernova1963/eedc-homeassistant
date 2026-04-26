import { Thermometer, Flame, Zap, TrendingUp, Battery, Activity } from 'lucide-react'

export type KomponentenColor = 'orange' | 'red' | 'yellow' | 'green' | 'blue' | 'purple' | 'cyan' | 'gray'

export const COLOR_CLASSES: Record<KomponentenColor, { text: string; bg: string }> = {
  orange: { text: 'text-orange-500', bg: 'bg-orange-50 dark:bg-orange-900/20' },
  red:    { text: 'text-red-500',    bg: 'bg-red-50 dark:bg-red-900/20' },
  yellow: { text: 'text-yellow-500', bg: 'bg-yellow-50 dark:bg-yellow-900/20' },
  green:  { text: 'text-green-500',  bg: 'bg-green-50 dark:bg-green-900/20' },
  blue:   { text: 'text-blue-500',   bg: 'bg-blue-50 dark:bg-blue-900/20' },
  purple: { text: 'text-purple-500', bg: 'bg-purple-50 dark:bg-purple-900/20' },
  cyan:   { text: 'text-cyan-500',   bg: 'bg-cyan-50 dark:bg-cyan-900/20' },
  gray:   { text: 'text-gray-500',   bg: 'bg-gray-50 dark:bg-gray-800' },
}

export interface KpiStyle {
  title: string
  icon: React.ElementType
  color: KomponentenColor
}

export const WP_KPI = {
  jaz:       { title: 'JAZ',              icon: Thermometer, color: 'orange' as const },
  waerme:    { title: 'Wärme erzeugt',    icon: Flame,       color: 'red'    as const },
  strom:     { title: 'Strom verbraucht', icon: Zap,         color: 'yellow' as const },
  ersparnis: { title: 'Ersparnis vs. Gas',icon: TrendingUp,  color: 'green'  as const },
} as const satisfies Record<string, KpiStyle>

export const WP_KPI_ORDER = ['jaz', 'waerme', 'strom', 'ersparnis'] as const

export const SPEICHER_EFFIZIENZ_KPI: KpiStyle = {
  title: 'Effizienz',
  icon: Activity,
  color: 'cyan',
}

export const SPEICHER_LADUNG_KPI: KpiStyle = {
  title: 'Ladung gesamt',
  icon: Battery,
  color: 'green',
}

export const SPEICHER_ENTLADUNG_KPI: KpiStyle = {
  title: 'Entladung gesamt',
  icon: Battery,
  color: 'blue',
}

export function fmtKpi(value: number | null | undefined, decimals = 0): string {
  if (value == null || !Number.isFinite(value)) return '---'
  return value.toFixed(decimals)
}
