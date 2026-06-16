/**
 * Universelles Block-Modell (IA v4) — echte, getestete Komponente.
 *
 * Promoviert aus dem Wegwerf-Skelett `components/preview/IASkeleton.tsx`
 * (Gernot-Entscheid 2026-06-13): JEDER Block (KPI-Strip, Hauptblock,
 * Werte/Tabelle, Detail-Sektion …) ist einklappbar (⌄) und hat einen
 * Fokus/Vollbild-Schalter (⤢) — app-weit auf allen Inhalts-Achsen. In den
 * Cockpit-Zeitsichten zusätzlich per ↑↓ verschiebbar (Monatsbericht-Muster).
 * Fokus macht u. a. den Live-Energiefluss wieder bildschirmfüllend. Klapp-/
 * Reihenfolge-Zustand bleibt pro Sicht via localStorage gemerkt (B6-SoT).
 */
import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

export interface Block {
  id: string
  title: string
  icon?: LucideIcon
  /** Tailwind-Textfarbe fürs Block-Icon (z. B. 'text-yellow-500'). */
  farbe?: string
  summary?: string
  /** Optionales Status-Element rechts im Kopf (z. B. Einstellungs-Status-Icon). */
  badge?: ReactNode
  /** Default-Zustand; false = startet eingeklappt (z. B. datenreich/mobil). */
  defaultOpen?: boolean
  /** `fokus` = Vollbild-Render (Charts groß). Param mit _ wenn ungenutzt. */
  render: (fokus: boolean) => ReactNode
}
