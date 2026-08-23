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
  Activity, AlertTriangle, ArrowUpDown, ArrowUpFromLine, Battery, BatteryCharging, BatteryMedium, Car,
  CheckCircle, Coins, Euro, Flame, Gauge, Hash, Home, Info, Leaf, Plug, RotateCw,
  Sun, Thermometer, TrendingUp, Wallet, Wrench, XCircle, Zap,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { TYP_TEXT_CLASS } from './colors'

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

/**
 * STEUER_H — EINE einheitliche Höhe (32 px) für ALLE Bedien-Elemente einer
 * Filter-/Toolbar-Leiste (Chips, Toggle-Pillen, Segment-Controls, `<input>`,
 * `<select>`) — dritte Kontroll-Höhen-Klasse neben Formular-42px und Button-36px
 * (Style-Guide B15 Kontroll-Höhen-SoT, R3b S5). Behebt detLAN #27 Punkt 2
 * „unterschiedliche Höhen in einer Reihe" (Chips waren 24 px, Inputs 32 px,
 * Selects 39 px) ohne die Aktions-Buttons (36 px) anzufassen. Pillen/Buttons
 * brauchen zusätzlich `inline-flex items-center`, `.input`-Felder `py-0`,
 * damit die feste Höhe greift. (R3b Etappe 2: aus `v4/WerkbankZeitraum`
 * hierher gehoben — Design-Konstante gehört ins lib-SoT-Modul, nicht in eine Sicht.)
 */
export const STEUER_H = 'h-8'

/**
 * Datenrollen-Icon-Kanon (R3b S7/A5 — „eine Datenrolle = ein Icon", analog zur
 * Farb-Regel in `lib/colors.ts`): EINE Map für die Energiebilanz-/Finanz-Rollen
 * der KPI-Kacheln (vorher 3 unabhängige Copy-Paste-Sätze in Tag-/Monat-/JahrBilanz).
 * Prognose-/Preview-Kontexte (z. B. CockpitAussicht) sind eigene Rollen und
 * NICHT über diese Map gebunden.
 */
export const DATENROLLEN_ICONS = {
  pv: Sun,
  autarkie: Activity,
  eigenverbrauch: Zap,
  einspeisung: ArrowUpFromLine,
  netzbezug: Plug,
  nettoErtrag: Euro,
  ergebnis: Wallet,
  netzladungKosten: BatteryCharging,
  netzpreis: Coins,
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
  icon: LucideIcon
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

/** Speicher: Vollzyklen · Wirkungsgrad η · Durchsatz · Ersparnis · Auslastung */
export const SPEICHER_KPI = {
  vollzyklen:   { title: 'Vollzyklen',     icon: RotateCw,   color: 'blue'   as const },
  wirkungsgrad: { title: 'Wirkungsgrad η', icon: Activity,   color: 'cyan'   as const },
  durchsatz:    { title: 'Durchsatz',      icon: Zap,        color: 'yellow' as const },
  ersparnis:    { title: 'Ersparnis',      icon: TrendingUp, color: 'green'  as const },
  // #358 Phase 1: zeitraum-normierte Nutzung — Entladung ÷ (Kapazität × Tage).
  // Anders als die Vollzyklen ist sie zwischen Monat und Jahr vergleichbar.
  auslastung:   { title: 'Auslastung',     icon: Gauge,      color: 'purple' as const },
  // Ladezustand (Tag): der einzige BESTANDS-Wert unter lauter Flussgrößen —
  // deshalb eine eigene Farbe statt der von „Auslastung" (Nutzungsgrad der
  // Kapazität, inhaltlich verwandt und gerade darum nicht gleich zu färben).
  // Wortwahl wie im Live-Dashboard („Ladezustand"); „SoC" bleibt der Fachbegriff
  // in der Stundentabelle. Gemeldet von dietmar1968 (Forum T89667 #97).
  ladezustand:  { title: 'Ladezustand',    icon: BatteryMedium, color: 'orange' as const },
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

/** Sonstiges/Zähler: Stand · Verbrauch im Zeitraum (#377).
 *
 *  Nur ZWEI Kennzahlen, und das ist die Aussage: Ein Verbrauchszähler wird
 *  erfasst, nicht bewertet — es gibt weder Ersparnis noch CO₂ noch einen
 *  PV-Anteil. Vier Kacheln zu füllen, indem man Nullen hineinschreibt, ist
 *  genau der v4.0.17-Befund bei der Klimaanlage.
 *
 *  Farbe **neutral (gray)**: Jede andere Farbe im Kanon steht für eine
 *  Datenrolle in der Energie-, Geld- oder CO₂-Rechnung. Ein Zählerstand hat
 *  keine solche Rolle. */
export const SONSTIGES_ZAEHLER_KPI = {
  stand:     { title: 'Zählerstand', icon: Gauge, color: 'gray' as const },
  verbrauch: { title: 'Verbrauch',   icon: Zap,   color: 'gray' as const },
} as const satisfies Record<string, KpiStyle>

/** Sonstiges/Speicher: Ladung · Entladung · Effizienz · Ersparnis */
export const SONSTIGES_SPEICHER_KPI = {
  ladung:    { title: 'Ladung',    icon: Battery,    color: 'purple' as const },
  entladung: { title: 'Entladung', icon: Zap,        color: 'green'  as const },
  effizienz: { title: 'Effizienz', icon: TrendingUp, color: 'blue'   as const },
  ersparnis: { title: 'Ersparnis', icon: TrendingUp, color: 'green'  as const },
} as const satisfies Record<string, KpiStyle>

/** Börsenpreis-Kennzahlen des Live-Blocks (#335).
 *
 *  Alle drei sind dieselbe Größe in ct/kWh und tragen deshalb dieselbe Farbe —
 *  `purple`, die Rollenfarbe des Strompreises (`CHART_COLORS.strompreis`). Was
 *  sie unterscheidet, ist ihre Rolle zueinander (Ist · Bezugsgröße · Grenze),
 *  und das sagt der Titel, nicht die Farbe. Die Stufenfarben der Chart-Linie
 *  stehen getrennt in `colors.ts::PREISSTUFEN_FARBEN` — sie färben nach Wert,
 *  diese hier benennen Kennzahlen. */
export const BOERSENPREIS_KPI = {
  aktuell:      { title: 'Aktueller Preis',  icon: Coins, color: 'purple' as const },
  // Zusage an Rainer (PN 2026-08-20): die allgemein lesbaren Zahlen zuerst —
  // Höchst, Tiefst, Monatsmittel —, die Optimierer-Werte danach. Dieselbe
  // Farbrolle: es ist dieselbe Datenrolle (Preis), nur eine andere Bezugszeit.
  hoechst:      { title: 'Höchstpreis heute', icon: ArrowUpDown, color: 'purple' as const },
  tiefst:       { title: 'Tiefstpreis heute', icon: ArrowUpDown, color: 'purple' as const },
  monat:        { title: 'Ø Monat',          icon: Gauge, color: 'purple' as const },
  // rapahl-PN 2026-08-23: der schlichte Tages-Ø. Er stand nirgends, obwohl
  // gleich DREI Kacheln daneben auf den Ø *ohne* die Peaks zeigen — „Nicht
  // jeder will ja seinen Akku mit Netzstrom laden". Bewusst VOR den
  // Optimierer-Werten: allgemein lesbare Zahlen zuerst, dieselbe Ordnung wie
  // bei Höchst/Tiefst/Monat.
  tagesMittel:  { title: 'Ø heute',          icon: Gauge, color: 'purple' as const },
  durchschnitt: { title: 'Ø ohne 3 Peaks',   icon: Gauge, color: 'purple' as const },
  schwelle:     { title: 'Günstig-Schwelle', icon: Hash,  color: 'purple' as const },
  // N-173: der Abstand als Betrag. Bewusst dieselbe Farbrolle wie die drei
  // anderen Preis-Kennzahlen — es ist dieselbe Datenrolle, nur eine andere
  // Größenart.
  abstand:      { title: 'Abstand zum Ø',    icon: ArrowUpDown, color: 'purple' as const },
} as const satisfies Record<string, KpiStyle>

// ─── Komponenten-Identität (#3b') — Icon + Farbe + Label je Investitionstyp ───
//
// Sektions-Kopf-Identität (Cockpit-Teaser, Komponenten-Achse, Vorschau). Icon +
// Label zentral, Farbe = Tailwind-Zwilling des Farb-Kanons `TYP_COLORS`
// (lib/colors.ts). Löst die vier hardcodierten `TYP_ICONS`-Dubletten ab. Label
// folgt `TYP_LABELS`, außer `waermepumpe` → „Wärme/Klima" (#263).

export interface KomponentenIdentitaet {
  icon: LucideIcon
  /** Tailwind-Text-Klasse (Zwilling von `TYP_COLORS`). */
  farbe: string
  label: string
}

export const KOMPONENTEN_IDENTITAET: Record<string, KomponentenIdentitaet> = {
  'pv-module':       { icon: Sun,     farbe: TYP_TEXT_CLASS['pv-module'],       label: 'PV-Module' },
  'wechselrichter':  { icon: Zap,     farbe: TYP_TEXT_CLASS['wechselrichter'],  label: 'Wechselrichter' },
  'speicher':        { icon: Battery, farbe: TYP_TEXT_CLASS['speicher'],        label: 'Speicher' },
  'balkonkraftwerk': { icon: Sun,     farbe: TYP_TEXT_CLASS['balkonkraftwerk'], label: 'Balkonkraftwerk' },
  'waermepumpe':     { icon: Flame,   farbe: TYP_TEXT_CLASS['waermepumpe'],     label: 'Wärme/Klima' },
  'wallbox':         { icon: Plug,    farbe: TYP_TEXT_CLASS['wallbox'],         label: 'Wallbox' },
  'e-auto':          { icon: Car,     farbe: TYP_TEXT_CLASS['e-auto'],          label: 'E-Auto' },
  'sonstiges':       { icon: Wrench,  farbe: TYP_TEXT_CLASS['sonstiges'],       label: 'Sonstiges' },
  'pv-system':       { icon: Sun,     farbe: TYP_TEXT_CLASS['pv-system'],       label: 'PV-System' },
}
