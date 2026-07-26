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
import type { ErfassungZustand } from '../ui/ErfassungZustandBadge'

/**
 * Herkunft der Werte einer Anzeige (Chart, Verteilungsbalken …) — für Blöcke,
 * deren Zahlen NICHT gemessen, sondern gerechnet sind (z. B. PV je Modul
 * anteilig nach kWp aus der Anlagen-Erzeugung).
 *
 * Gerendert wird ausschließlich über das SoT-Badge `ErfassungZustandBadge`
 * (Regel 0a: keine zweite Zustands-Bildsprache), bewusst als `iconOnly` —
 * „nach kWp gerechnet" ist eine Eigenschaft der Anzeige, kein Handlungsauftrag
 * wie der gelbe Monatsabschluss-Zustand.
 */
export interface WertHerkunft {
  /** Zustand fürs Badge — für gerechnete Werte `geschaetzt`. */
  zustand: ErfassungZustand
  /** Quell-Zusatz im Badge-Label, z. B. „kWp-Anteil". */
  quelleLabel?: string
  /** Worauf sich die Kennzeichnung bezieht, wenn die Anzeige gemischt ist —
   *  im PV-Verlauf gilt sie nur für den Erzeugungs-Stapel, die Verwendung
   *  daneben ist gemessen. */
  bezug?: string
  /** Sichtbarer Erklärsatz (Wortlaut-SoT: Daten-Checker), inkl. Verweis auf
   *  den Block mit den gemessenen Werten. Auch auf Touch lesbar — deshalb
   *  sichtbar statt nur als Hover-Tooltip. */
  hinweis?: string
}

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
  /** Paket CT: Tabellen-Ablesung des Block-Charts (i. d. R. `ChartDatenTabelle`).
   *  Gesetzt → das Fokus-Overlay zeigt den Chart-⇄-Tabelle-Umschalter. */
  renderTabelle?: () => ReactNode
}
