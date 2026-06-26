/**
 * KpiStrip — responsives Raster aus KPICard-SoT-Kacheln (B9).
 *
 * Promoviert aus `components/preview/IASkeleton.tsx`. Trägt jetzt ECHTE
 * KPICard-Props (kein Dummy-Typ): jede Kachel ist genau eine `KPICard`.
 */
import { Fragment } from 'react'
import type { LucideIcon } from 'lucide-react'
import { KPICard } from '../ui'
import { Parkbar } from '../park'
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
  /** Provenance-/Sicht-Zeile im Formel-Tooltip (z. B. „Gesamt-Anlage · Prognose"). */
  sicht?: string
  /** Voraussetzungs-Hinweis bei fehlendem Wert („—") — Tooltip, was zugeordnet
   *  werden muss (Gernot 2026-06-24). */
  hinweis?: string
  /** Element-Park-id (IA-V4 SLICE 1). Nur gesetzt → Kachel wird parkbar umhüllt;
   *  ohne ParkProvider (Produktion/v3) bleibt {@link Parkbar} inert. */
  parkId?: string
}

export function KpiStrip({ kpis }: { kpis: KpiStripItem[] }) {
  // Inhaltsabhängige Spaltenreduzierung (#243): auto-fit + minmax(248px) senkt die
  // Spaltenzahl stufenlos, sobald „Zahl + Einheit" sonst zu eng würde — keine
  // Engstelle kurz vor einem festen Breakpoint. Regel-SoT, aus der IA-v4-Vorschau
  // übernommen (248px = „Kacheln auch bei vielen Spalten nicht eng"). Style-Guide #243.
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(248px,1fr))] gap-3">
      {kpis.map((k) => {
        const card = (
          <KPICard
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
            sicht={k.sicht}
            hinweis={k.hinweis}
          />
        )
        // parkId gesetzt → parkbar umhüllen (inert ohne ParkProvider). Ohne parkId
        // bleibt die KPICard das direkte Grid-Kind → Produktion/v3 DOM-/verhaltensgleich.
        return k.parkId
          ? <Parkbar key={k.title} id={k.parkId} titel={k.title}>{card}</Parkbar>
          : <Fragment key={k.title}>{card}</Fragment>
      })}
    </div>
  )
}
