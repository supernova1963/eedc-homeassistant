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
import { Activity, Scale, LineChart, Table2, Euro, Users, CloudSun, CalendarRange, TrendingDown, Flame, Leaf, Gauge } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { COLOR_CLASSES } from './komponentenStyle'

export type BlockKind =
  | 'kennzahlen'
  | 'energieBilanz'
  | 'verlauf'
  | 'werte'
  | 'finanzen'
  | 'community'
  | 'co2'
  // #377 — Verbrauchszähler (Gas/Wasser/Öl). Erfasst, nicht bewertet.
  | 'zaehlerstaende'
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
  // CO₂/Umwelt = grün. Begründung wie bei den Nachbarn: der Block trägt eine
  // eigene Datenrolle, also ihre Rollenfarbe. Die CO₂-Rolle ist Emerald
  // (`CHART_COLORS.co2Pv`, dazu der Text-Zwilling `CO2_TEXT_CLASS`); im
  // 8er-Farbklassen-Kanon hat Emerald keinen eigenen Eintrag, `green` ist sein
  // nächster Nachbar. Bewusst NICHT roh `text-emerald-600` notiert — Block-Icons
  // bleiben auf der EINEN Palette (Kopf-Regel), sonst steht hier die nächste Drift.
  co2:           { icon: Leaf,      farbe: COLOR_CLASSES.green.text },
  // Aussicht: Wetter = Solar/gelb (Umgebung treibt PV); übrige neutral (Projektion
  // ohne Einzel-Datenrolle), Degradation NICHT rot gefärbt (Status-Hinweis, kein Alarm).
  wetter:         { icon: CloudSun,     farbe: COLOR_CLASSES.yellow.text },
  saison:         { icon: CalendarRange }, // neutral
  degradation:    { icon: TrendingDown }, // neutral
  wpAussicht:     { icon: Flame, farbe: COLOR_CLASSES.red.text }, // WP-Identität (rot, dokumentiert)
  // #377: bewusst NEUTRAL (ohne Farbe). Jede Farbe im Kanon steht für eine
  // Datenrolle in der Energie-/Geld-/CO₂-Rechnung — ein Zählerstand hat keine
  // solche Rolle, er wird nicht verrechnet. Ihm eine Rollenfarbe zu geben,
  // hieße ihn optisch zu einer Bilanzgröße zu machen.
  zaehlerstaende: { icon: Gauge },
}
