/**
 * Block-Identitäts-SoT (IA v4 #3b · Regel 0/0a) — Icon + Farbe je universellem
 * Inhalts-Block (Kennzahlen · Energie-Bilanz · Verlauf · Werte/Tabelle ·
 * Finanzen · Community).
 *
 * Vorher pro Sicht hardcodiert (CockpitMonatV4/CockpitV4/MonatRahmen + Preview)
 * → Drift (z. B. Energie-Bilanz mal `Scale`/farblos, mal `Sun`/gelb). Hier die
 * EINE Quelle; alle Sichten + die Vorschau konsumieren sie.
 *
 * Farb-Schema (Gernot 2026-06-18): Struktur-Blöcke ohne Eigensemantik bleiben
 * neutral (kein `farbe` → BlockShell-Grau); semantisch aufgeladene Blöcke tragen
 * ihre Rollenfarbe aus dem 8er-Kanon — Energie-Bilanz = Solar (`yellow`),
 * Finanzen = Geld (`green`), Community = „eigene Serie" (`blue`). Farben werden
 * NICHT roh notiert, sondern aus `COLOR_CLASSES` (`lib/komponentenStyle`, der
 * EINEN 8er-Farbklassen-Definition; Werte aus `lib/colors.ts`) bezogen.
 */
import { Activity, Scale, LineChart, Table2, Euro, Users, CloudSun, CalendarRange, TrendingDown, Flame } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { COLOR_CLASSES } from './komponentenStyle'

export type BlockKind =
  | 'kennzahlen'
  | 'energieBilanz'
  | 'verlauf'
  | 'werte'
  | 'finanzen'
  | 'community'
  // Cockpit/Aussicht (A.4) — Projektions-Blöcke
  | 'wetter'
  | 'saison'
  | 'degradation'
  | 'wpAussicht'

export interface BlockIdentitaet {
  icon: LucideIcon
  /** Tailwind-Text-Klasse fürs Icon; `undefined` = neutral (BlockShell-Grau). */
  farbe?: string
}

export const BLOCK_IDENTITAET: Record<BlockKind, BlockIdentitaet> = {
  kennzahlen:    { icon: Activity }, // neutral — Aggregat ohne Einzelsemantik
  energieBilanz: { icon: Scale,     farbe: COLOR_CLASSES.yellow.text }, // Solar/Energie
  verlauf:       { icon: LineChart }, // neutral
  werte:         { icon: Table2 },    // neutral
  finanzen:      { icon: Euro,      farbe: COLOR_CLASSES.green.text }, // Geld-Logik
  community:     { icon: Users,     farbe: COLOR_CLASSES.blue.text },  // „eigene Serie"
  // Aussicht: Wetter = Solar/gelb (Umgebung treibt PV); übrige neutral (Projektion
  // ohne Einzel-Datenrolle), Degradation NICHT rot gefärbt (Status-Hinweis, kein Alarm).
  wetter:         { icon: CloudSun,     farbe: COLOR_CLASSES.yellow.text },
  saison:         { icon: CalendarRange }, // neutral
  degradation:    { icon: TrendingDown }, // neutral
  wpAussicht:     { icon: Flame, farbe: COLOR_CLASSES.red.text }, // WP-Identität (rot, dokumentiert)
}
