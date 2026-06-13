/**
 * Komponenten-Stil-SoT (Style-Guide A5 + KONZEPT-IA-V4 D2 · Regel 0/0a).
 *
 * Pro Komponententyp die 4 Status-KPIs (Kanon entschieden 2026-06-02, F9
 * bestätigt 2026-06-12) mit Titel, Icon und Farbe — Stile = ratifizierter
 * Bestand der heutigen Dashboards. Konsumenten spreaden die Records direkt:
 *
 *   <KPICard {...WP_KPI.jaz} value={...} />
 *   <KPICard {...WP_KPI.jaz} title="JAZ Heizen" value={...} />  // Variante per Override
 *
 * COLOR_CLASSES ist die EINZIGE Definition der KPI-Farbklassen —
 * `ui/KPICard.tsx` importiert sie (keine Parallel-Pflege, §9-Klasse 7).
 * „PV-Anlage" ist ein UI-Aggregat (pv-module/wechselrichter/balkonkraftwerk),
 * kein eigener `InvestitionTyp`.
 */

import {
  Activity, AlertTriangle, Battery, Car, CheckCircle, Flame, Hash, Home, Info,
  Leaf, RotateCw, Sun, Thermometer, TrendingUp, XCircle, Zap,
} from 'lucide-react'

/**
 * Status-Achse (F3) — Icon-Satz als EINE Quelle (Style-Guide B17). Farben dazu:
 * `STATUS_COLORS` in `lib/colors.ts`. Alerts/Badges/Daten-Checker konsumieren beide.
 */
export const STATUS_ICONS = {
  ok: CheckCircle,
  warnung: AlertTriangle,
  kritisch: XCircle,
  info: Info,
} as const

export type KomponentenColor = 'orange' | 'red' | 'yellow' | 'green' | 'blue' | 'purple' | 'cyan' | 'gray'

/** KPI-Farbklassen (Datentyp-Achse) — einzige Definition, KPICard leitet ab. */
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

// ─── D2-Kanon: 4 Status-KPIs je Komponententyp ───────────────────────────────

/** PV-Anlage (UI-Aggregat): Leistung · Gesamterzeugung · Spez. Ertrag · Eigenverbrauch */
export const PV_ANLAGE_KPI = {
  leistung:       { title: 'Anlagenleistung', icon: Sun,        color: 'yellow' as const },
  erzeugung:      { title: 'Gesamterzeugung', icon: Zap,        color: 'green'  as const },
  spezErtrag:     { title: 'Spez. Ertrag',    icon: TrendingUp, color: 'blue'   as const },
  eigenverbrauch: { title: 'Eigenverbrauch',  icon: Activity,   color: 'purple' as const },
} as const satisfies Record<string, KpiStyle>

/** Speicher: Vollzyklen · Wirkungsgrad η · Durchsatz · Ersparnis */
export const SPEICHER_KPI = {
  vollzyklen:   { title: 'Vollzyklen',     icon: RotateCw,   color: 'blue'   as const },
  wirkungsgrad: { title: 'Wirkungsgrad η', icon: Activity,   color: 'cyan'   as const },
  durchsatz:    { title: 'Durchsatz',      icon: Zap,        color: 'yellow' as const },
  ersparnis:    { title: 'Ersparnis',      icon: TrendingUp, color: 'green'  as const },
} as const satisfies Record<string, KpiStyle>

/** Wärme/Klima: JAZ · Wärme erzeugt · Strom verbraucht · Ersparnis vs. Gas */
export const WP_KPI = {
  jaz:       { title: 'JAZ',              icon: Thermometer, color: 'orange' as const },
  waerme:    { title: 'Wärme erzeugt',    icon: Flame,       color: 'red'    as const },
  strom:     { title: 'Strom verbraucht', icon: Zap,         color: 'yellow' as const },
  ersparnis: { title: 'Ersparnis vs. Gas',icon: TrendingUp,  color: 'green'  as const },
} as const satisfies Record<string, KpiStyle>

/** E-Auto: Gefahren · Verbrauch · PV-Anteil · Ersparnis vs. Benzin */
export const EAUTO_KPI = {
  gefahren:  { title: 'Gefahren',            icon: Car,        color: 'blue'   as const },
  verbrauch: { title: 'Verbrauch',           icon: Zap,        color: 'yellow' as const },
  pvAnteil:  { title: 'PV-Anteil (Heim)',    icon: Leaf,       color: 'green'  as const },
  ersparnis: { title: 'Ersparnis vs. Benzin',icon: TrendingUp, color: 'green'  as const },
} as const satisfies Record<string, KpiStyle>

/** Wallbox: Heimladung · PV-Anteil · Ladevorgänge · Ersparnis vs. Extern */
export const WALLBOX_KPI = {
  heimladung:    { title: 'Heimladung',          icon: Home,       color: 'purple' as const },
  pvAnteil:      { title: 'PV-Anteil',           icon: Leaf,       color: 'green'  as const },
  ladevorgaenge: { title: 'Ladevorgänge',        icon: Hash,       color: 'blue'   as const },
  ersparnis:     { title: 'Ersparnis vs. Extern',icon: TrendingUp, color: 'green'  as const },
} as const satisfies Record<string, KpiStyle>

/** BKW: Erzeugung · Eigenverbrauch · Ersparnis · Spez. Ertrag (achsenrein, ohne CO₂) */
export const BKW_KPI = {
  erzeugung:      { title: 'Erzeugung',      icon: Zap,        color: 'yellow' as const },
  eigenverbrauch: { title: 'Eigenverbrauch', icon: Home,       color: 'green'  as const },
  ersparnis:      { title: 'Ersparnis',      icon: TrendingUp, color: 'green'  as const },
  spezErtrag:     { title: 'Spez. Ertrag',   icon: TrendingUp, color: 'blue'   as const },
} as const satisfies Record<string, KpiStyle>

// ─── Sonstiges: 3 Varianten nach Wirkrichtung ────────────────────────────────

/** Sonstiges/Erzeuger: Erzeugung · Eigenverbrauch · Ersparnis · CO₂ (Cross-Link CO₂-Tab) */
export const SONSTIGES_ERZEUGER_KPI = {
  erzeugung:      { title: 'Erzeugung',      icon: Zap,        color: 'yellow' as const },
  eigenverbrauch: { title: 'Eigenverbrauch', icon: Home,       color: 'green'  as const },
  ersparnis:      { title: 'Ersparnis',      icon: TrendingUp, color: 'green'  as const },
  co2:            { title: 'CO₂ gespart',    icon: Leaf,       color: 'green'  as const },
} as const satisfies Record<string, KpiStyle>

/** Sonstiges/Verbraucher: Verbrauch · PV-Anteil · Netzkosten · PV-Ersparnis */
export const SONSTIGES_VERBRAUCHER_KPI = {
  verbrauch:   { title: 'Verbrauch',    icon: Zap,        color: 'blue'  as const },
  pvAnteil:    { title: 'PV-Anteil',    icon: Home,       color: 'green' as const },
  netzkosten:  { title: 'Netzkosten',   icon: TrendingUp, color: 'red'   as const },
  pvErsparnis: { title: 'PV-Ersparnis', icon: Leaf,       color: 'green' as const },
} as const satisfies Record<string, KpiStyle>

/** Sonstiges/Speicher: Ladung · Entladung · Effizienz · Ersparnis */
export const SONSTIGES_SPEICHER_KPI = {
  ladung:    { title: 'Ladung',    icon: Battery,    color: 'purple' as const },
  entladung: { title: 'Entladung', icon: Zap,        color: 'green'  as const },
  effizienz: { title: 'Effizienz', icon: TrendingUp, color: 'blue'   as const },
  ersparnis: { title: 'Ersparnis', icon: TrendingUp, color: 'green'  as const },
} as const satisfies Record<string, KpiStyle>
