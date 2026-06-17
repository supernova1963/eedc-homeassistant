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
  /** Zweitzeile unter dem Wert (z. B. Vormonat-Vergleich, SOLL-Annotation). */
  subtitle?: string
  /** Trend-Pfeil ↑/↓ neben dem Wert. */
  trend?: 'up' | 'down'
  onClick?: () => void
  // A6-Tooltip-Slot (Berechnungsdetails) — durchgereicht an KPICard.
  formel?: string
  berechnung?: string
  ergebnis?: string
}

export function KpiStrip({ kpis }: { kpis: KpiStripItem[] }) {
  // Inhaltsabhängige Spaltenreduzierung (#243): auto-fit + minmax(248px) senkt die
  // Spaltenzahl stufenlos, sobald „Zahl + Einheit" sonst zu eng würde — keine
  // Engstelle kurz vor einem festen Breakpoint. Regel-SoT, aus der IA-v4-Vorschau
  // übernommen (248px = „Kacheln auch bei vielen Spalten nicht eng"). Style-Guide #243.
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(248px,1fr))] gap-3">
      {kpis.map((k) => (
        <KPICard
          key={k.title}
          title={k.title}
          value={k.value}
          unit={k.unit}
          subtitle={k.subtitle}
          trend={k.trend}
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
