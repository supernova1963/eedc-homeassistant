/**
 * KpiStrip — responsives Raster aus KPICard-SoT-Kacheln (B9).
 *
 * Promoviert aus `components/preview/IASkeleton.tsx`. Trägt jetzt ECHTE
 * KPICard-Props (kein Dummy-Typ): jede Kachel ist genau eine `KPICard`.
 */
import type { LucideIcon } from 'lucide-react'
import { KPICard } from '../ui'
import type { KomponentenColor } from '../../lib/komponentenStyle'

export interface KpiStripItem {
  title: string
  value: string | number
  unit?: string
  color?: KomponentenColor
  icon?: LucideIcon
  onClick?: () => void
  // A6-Tooltip-Slot (Berechnungsdetails) — durchgereicht an KPICard.
  formel?: string
  berechnung?: string
  ergebnis?: string
}

export function KpiStrip({ kpis }: { kpis: KpiStripItem[] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {kpis.map((k) => (
        <KPICard
          key={k.title}
          title={k.title}
          value={k.value}
          unit={k.unit}
          color={k.color}
          icon={k.icon}
          onClick={k.onClick}
          formel={k.formel}
          berechnung={k.berechnung}
          ergebnis={k.ergebnis}
        />
      ))}
    </div>
  )
}
