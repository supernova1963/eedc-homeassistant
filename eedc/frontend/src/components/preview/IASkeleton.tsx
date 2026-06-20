/**
 * IASkeleton — klickbares Vorschau-Skelett der IA-v4.0.0-Struktur
 * (Etappenziel 1/2). **Guard-frei** und damit in zwei Kontexten lauffähig:
 *   1. lokal über `pages/DesignPreview.tsx` (DEV-Guard davor) auf
 *      `/dev/design-preview`;
 *   2. als eigenständiger Vorschau-Entry (`preview-main.tsx` + `preview.html`,
 *      `vite.preview.config.ts`) für das öffentliche GitHub-Pages-Hosting unter
 *      `/eedc-homeassistant/preview/` (Etappe 2) — das ist ein **Production**-
 *      Build, deshalb darf hier KEIN `import.meta.env.DEV`-Guard stehen.
 *
 * Zweck (KONZEPT-IA-V4 §„Vorab-Sichtung"): Die wiederkehrende Tester-Frage
 * „kann man vorher sehen, was sich ändert?" mit einer **klickbaren Vorschau
 * aus echten Komponenten** beantworten — kein Design-Tool, kein Wegwerf-Mock.
 * Es ist bewusst eine reine **Navigations-Schale** (keine echten Daten): die
 * neue Top-Nav (Zeit/Was/Wie-Achsen), die Cockpit-Sub-Tabs, der Komponenten-
 * Hub (Variante C) und das Einstellungs-Kachelgrid — als Dummy-Karten mit der
 * KPICard-SoT (B9). Struktur **exakt** nach KONZEPT-IA-V4/Journal, damit E2
 * die richtige Struktur testet.
 *
 * Diese Schale läuft als eigenständige In-Page-Navigation (interner State,
 * keine echten Routen — die v4-Routen entstehen erst ab E3). Mobile-Quer-
 * schnitt: `h-dvh`, Touch-Targets ≥ 44 px, Hamburger (M0).
 */

import { useEffect, useMemo, useState } from 'react'
import { KPICard } from '../ui'
import { compareTyp } from '../../lib/constants'
import { BLOCK_IDENTITAET } from '../../lib/blockStyle'
import { KOMPONENTEN_IDENTITAET } from '../../lib/komponentenStyle'
import type { KomponentenColor } from '../../lib/komponentenStyle'
import {
  LayoutDashboard, Boxes, BarChart3, Users, HelpCircle, Settings,
  Sun, Battery, Flame, Car, Plug, Wrench, Zap, Euro, Leaf, PiggyBank, Table2,
  Activity, TrendingUp, Trophy, MapPin, ArrowRight, LineChart, Wallet,
  ArrowUp, ArrowDown, ChevronDown, Maximize2, Minimize2,
  CheckCircle2, AlertTriangle, Sparkles, BookOpen, FileText,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { IATopNav } from '../layout/IATopNav'
import { IASubTabBar } from '../layout/IASubTabBar'
import { AnlagenSelektorView } from '../layout/AnlagenSelektorView'
import { APP_VERSION } from '../../config/version'

// ─── Achsen / Tabs (Struktur-SoT: KONZEPT-IA-V4) ─────────────────────────────
type TopKey = 'cockpit' | 'komponenten' | 'auswertungen' | 'community' | 'hilfe' | 'einstellungen'

const TOP_INHALT: { key: TopKey; label: string; icon: LucideIcon }[] = [
  { key: 'cockpit',      label: 'Cockpit',      icon: LayoutDashboard },
  { key: 'komponenten',  label: 'Komponenten',  icon: Boxes },
  { key: 'auswertungen', label: 'Auswertungen', icon: BarChart3 },
  { key: 'community',    label: 'Community',    icon: Users },
]
const TOP_META: { key: TopKey; label: string; icon: LucideIcon }[] = [
  { key: 'hilfe',         label: 'Hilfe',         icon: HelpCircle },
  { key: 'einstellungen', label: 'Einstellungen', icon: Settings },
]

const COCKPIT_SUBS = ['Live', 'Tag', 'Monat', 'Jahr/Gesamt', 'Aussicht'] as const
type CockpitSub = (typeof COCKPIT_SUBS)[number]

// Reihenfolge folgt der kanonischen INVESTITION_TYP_ORDER (lib/constants.ts).
// Variante C konsolidiert: Wechselrichter+PV-Module → „PV-Anlage", Wärmepumpe →
// „Wärme/Klima", Balkonkraftwerk → „BKW". `.sort(compareTyp)` hält die Hub-Folge
// driftfest an der SoT (detLAN #243: E-Auto stand vor Wallbox, BKW zu weit hinten).
// Icon je Typ aus dem Identitäts-SoT (KOMPONENTEN_IDENTITAET, #3b'); Tab-Labels
// bewusst kurz (PV-Anlage/BKW). `.sort(compareTyp)` hält die Hub-Folge driftfest.
const KOMP_TYPEN: { key: string; label: string; icon: LucideIcon; typ: string }[] = [
  { key: 'pv',        label: 'PV-Anlage',   typ: 'pv-module' },
  { key: 'speicher',  label: 'Speicher',    typ: 'speicher' },
  { key: 'bkw',       label: 'BKW',         typ: 'balkonkraftwerk' },
  { key: 'waerme',    label: 'Wärme/Klima', typ: 'waermepumpe' },
  { key: 'wallbox',   label: 'Wallbox',     typ: 'wallbox' },
  { key: 'eauto',     label: 'E-Auto',      typ: 'e-auto' },
  { key: 'sonstiges', label: 'Sonstiges',   typ: 'sonstiges' },
].map((t) => ({ ...t, icon: KOMPONENTEN_IDENTITAET[t.typ].icon })).sort(compareTyp)

const AUSW_SUBS = ['Finanzen', 'CO₂', 'ROI', 'Tabelle', 'Prognose-vs-IST'] as const
const COMM_SUBS = ['Übersicht', 'PV-Ertrag', 'Komponenten', 'Regional', 'Trends'] as const

// ─── KPI-Dummy-Sätze (KONZEPT-IA-V4: D1-Strip + D2-Status-Kanon) ─────────────
interface KpiDummy { title: string; value: string; unit?: string; color: KomponentenColor; icon: LucideIcon }

// D1 — universeller Cockpit-Strip; ab Monat + Netto-Ertrag, Jahr + spez. Ertrag.
function cockpitStrip(sub: CockpitSub): KpiDummy[] {
  const basis: KpiDummy[] = [
    { title: 'PV-Erzeugung',   value: '412', unit: 'kWh', color: 'yellow', icon: Sun },
    { title: 'Autarkie',       value: '68',  unit: '%',   color: 'green',  icon: Activity },
    { title: 'Eigenverbrauch', value: '54',  unit: '%',   color: 'purple', icon: Zap },
    { title: 'Einspeisung',    value: '189', unit: 'kWh', color: 'green',  icon: ArrowRight },
    { title: 'Netzbezug',      value: '143', unit: 'kWh', color: 'red',    icon: Plug },
  ]
  if (sub === 'Monat') basis.push({ title: 'Netto-Ertrag', value: '128', unit: '€', color: 'blue', icon: Euro })
  if (sub === 'Jahr/Gesamt') {
    basis.push({ title: 'Netto-Ertrag', value: '1.480', unit: '€', color: 'blue', icon: Euro })
    basis.push({ title: 'Spez. Ertrag', value: '1.040', unit: 'kWh/kWp', color: 'cyan', icon: TrendingUp })
  }
  return basis
}

// D2 — Status-KPIs je Komponententyp (Kanon, KONZEPT-IA-V4 Z. 177-185).
const KOMP_STATUS: Record<string, KpiDummy[]> = {
  pv: [
    { title: 'Anlagenleistung', value: '9,8',  unit: 'kWp',     color: 'yellow', icon: Sun },
    { title: 'Gesamterzeugung', value: '38,2', unit: 'MWh',     color: 'yellow', icon: Activity },
    { title: 'Spez. Ertrag',    value: '1.040', unit: 'kWh/kWp', color: 'cyan',  icon: TrendingUp },
    { title: 'Eigenverbrauch',  value: '54',   unit: '%',       color: 'purple', icon: Zap },
  ],
  speicher: [
    { title: 'Vollzyklen',    value: '312', color: 'blue', icon: Activity },
    { title: 'Wirkungsgrad η', value: '92', unit: '%', color: 'cyan', icon: TrendingUp },
    { title: 'Durchsatz',     value: '4,1', unit: 'MWh', color: 'blue', icon: Zap },
    { title: 'Ersparnis',     value: '286', unit: '€', color: 'green', icon: Euro },
  ],
  waerme: [
    { title: 'JAZ',             value: '3,8', color: 'orange', icon: Flame },
    { title: 'Wärme erzeugt',   value: '12,4', unit: 'MWh', color: 'orange', icon: Activity },
    { title: 'Strom verbraucht', value: '3,3', unit: 'MWh', color: 'yellow', icon: Zap },
    { title: 'Ersparnis vs. Gas', value: '410', unit: '€', color: 'green', icon: Euro },
  ],
  eauto: [
    { title: 'Gefahren',  value: '14.200', unit: 'km', color: 'blue', icon: Car },
    { title: 'Verbrauch', value: '17,2', unit: 'kWh/100km', color: 'yellow', icon: Zap },
    { title: 'PV-Anteil', value: '61', unit: '%', color: 'green', icon: Sun },
    { title: 'Ersparnis vs. Benzin', value: '1.120', unit: '€', color: 'green', icon: Euro },
  ],
  wallbox: [
    { title: 'Heimladung',   value: '2,4', unit: 'MWh', color: 'blue', icon: Plug },
    { title: 'PV-Anteil',    value: '58', unit: '%', color: 'green', icon: Sun },
    { title: 'Ladevorgänge', value: '143', color: 'blue', icon: Activity },
    { title: 'Ersparnis vs. Extern', value: '640', unit: '€', color: 'green', icon: Euro },
  ],
  bkw: [
    { title: 'Erzeugung',      value: '612', unit: 'kWh', color: 'yellow', icon: Sun },
    { title: 'Eigenverbrauch', value: '94', unit: '%', color: 'purple', icon: Zap },
    { title: 'Ersparnis',      value: '184', unit: '€', color: 'green', icon: Euro },
    { title: 'Spez. Ertrag',   value: '980', unit: 'kWh/kWp', color: 'cyan', icon: TrendingUp },
  ],
  sonstiges: [
    { title: 'Erzeugung',     value: '320', unit: 'kWh', color: 'yellow', icon: Sun },
    { title: 'EV-Quote',      value: '72', unit: '%', color: 'purple', icon: Zap },
    { title: 'Ersparnis',     value: '96', unit: '€', color: 'green', icon: Euro },
    { title: 'CO₂ vermieden →', value: '0,2', unit: 't', color: 'green', icon: Leaf },
  ],
}

// ─── B-Variante (#243 A1, Gernot-Entscheid): Parameter AM ORT der Komponente ───
// Rainers „nicht raten, wo eine Einstellung sitzt": jede Komponente trägt einen
// Einstellungen-Block mit ALLEN ihren Parametern (Inventur investitionParameter.ts).
// Anlagenweit/regulatorisch (USt/§51/Netz-Puffer/Prognosequelle) + zeitlich
// variable Strompreise bleiben bewusst im Einstellungen-Bereich (anderer
// Geltungsbereich) und werden dort verlinkt — siehe Hinweis je Block.
interface ParamFeld { label: string; wert: string }
interface ParamGruppe { titel: string; felder: ParamFeld[] }
const KOMP_PARAMETER: Record<string, ParamGruppe[]> = {
  pv: [
    { titel: 'Module', felder: [{ label: 'Leistung', wert: '9,8 kWp' }, { label: 'Ausrichtung', wert: 'Süd' }, { label: 'Neigung', wert: '30°' }] },
    { titel: 'Wechselrichter', felder: [{ label: 'Max. Leistung', wert: '8 kW' }, { label: 'Wirkungsgrad', wert: '97 %' }, { label: 'Hybrid', wert: 'ja' }] },
  ],
  speicher: [
    { titel: 'Technik', felder: [{ label: 'Kapazität', wert: '10 kWh' }, { label: 'nutzbar', wert: '9 kWh' }, { label: 'Wirkungsgrad η', wert: '95 %' }, { label: 'Lade/Entlade', wert: '5 / 5 kW' }] },
    { titel: 'Netz & Arbitrage', felder: [{ label: 'lädt aus Netz', wert: '☑' }, { label: 'arbitragefähig', wert: '☑' }, { label: 'Ladepreis', wert: '12 ct/kWh' }, { label: 'vermied. Preis', wert: '35 ct/kWh' }] },
  ],
  bkw: [
    { titel: 'Module', felder: [{ label: 'Leistung', wert: '800 Wp' }, { label: 'Anzahl', wert: '2' }, { label: 'Ausrichtung', wert: 'Süd' }, { label: 'Neigung', wert: '30°' }] },
    { titel: 'Speicher', felder: [{ label: 'hat Speicher', wert: '☑' }, { label: 'Kapazität', wert: '2.000 Wh' }] },
  ],
  waerme: [
    { titel: 'Effizienz', felder: [{ label: 'Modus', wert: 'SCOP' }, { label: 'SCOP Heizung', wert: '4,5' }, { label: 'SCOP Warmwasser', wert: '3,2' }, { label: 'Vorlauf', wert: '35 °C' }] },
    { titel: 'Wärmebedarf', felder: [{ label: 'Heizung', wert: '12.000 kWh' }, { label: 'Warmwasser', wert: '3.000 kWh' }, { label: 'PV-Anteil', wert: '30 %' }] },
    { titel: 'Wirtschaftlichkeit', felder: [{ label: 'alt. Energieträger', wert: 'Gas' }, { label: 'alter Preis', wert: '12 ct/kWh' }, { label: 'WP-Stromtarif', wert: '→ Strompreise' }] },
    { titel: 'Messung', felder: [{ label: 'getrennte Strommessung', wert: '☑ Heizung/WW' }] },
  ],
  wallbox: [
    { titel: 'Technik', felder: [{ label: 'Max. Leistung', wert: '11 kW' }, { label: 'PV-optimiert', wert: '☑' }, { label: 'bidirektional (V2H)', wert: '☐' }] },
    { titel: 'Zuordnung', felder: [{ label: 'dienstlich', wert: '☐' }, { label: 'Wallbox-Tarif', wert: '→ Strompreise' }] },
  ],
  eauto: [
    { titel: 'Fahrprofil', felder: [{ label: 'Verbrauch', wert: '17,2 kWh/100km' }, { label: 'Jahresfahrleistung', wert: '14.200 km' }, { label: 'PV-Ladeanteil', wert: '60 %' }] },
    { titel: 'Vergleich Verbrenner', felder: [{ label: 'Verbrauch', wert: '7,5 L/100km' }, { label: 'Benzinpreis', wert: '1,65 €' }, { label: 'dienstlich', wert: '☐' }] },
    { titel: 'V2H', felder: [{ label: 'V2H-fähig', wert: '☐' }] },
  ],
  sonstiges: [
    { titel: 'Allgemein', felder: [{ label: 'Kategorie', wert: 'Erzeuger' }, { label: 'Beschreibung', wert: '—' }] },
  ],
}

function ParamGruppen({ typ }: { typ: string }) {
  const gruppen = KOMP_PARAMETER[typ] ?? []
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {gruppen.map((g) => (
          <div key={g.titel} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-2">{g.titel}</p>
            <dl className="space-y-1">
              {g.felder.map((f) => (
                <div key={f.label} className="flex items-center justify-between gap-2 text-sm">
                  <dt className="text-gray-500 dark:text-gray-400">{f.label}</dt>
                  <dd className="font-medium text-gray-900 dark:text-white whitespace-nowrap">{f.wert}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
      <a href="#" className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
        <Settings className="h-4 w-4" /> Diese Parameter bearbeiten (Investition öffnen)
      </a>
      <p className="text-xs text-gray-400 dark:text-gray-500">
        Anlagenweite Einstellungen (USt, §51 EEG, Netz-Puffer, Prognosequelle) und zeitlich variable
        Strompreise liegen weiterhin unter <span className="font-medium">Einstellungen</span> — anderer
        Geltungsbereich, von dort verlinkt.
      </p>
    </div>
  )
}

// Berichte-Cross-Link im Fluss (#243 Punkt 4, Konzept §18 G10): Teaser dort, wo
// der Bericht entsteht (Cockpit/Jahr → Jahresbericht, Auswertungen/Finanzen →
// Finanzbericht) + Verweis auf die zentrale Verwaltung in Stammdaten.
function BerichtTeaser({ titel, dateiname }: { titel: string; dateiname: string }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600 dark:text-gray-300">{titel} als PDF erzeugen — oder alle Berichte zentral verwalten.</p>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <button type="button" className="min-h-[44px] inline-flex items-center gap-2 px-4 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700">
          <FileText className="h-4 w-4" /> {dateiname} (PDF)
        </button>
        <a href="#" className="min-h-[44px] inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
          <ArrowRight className="h-4 w-4" /> Alle Berichte (Einstellungen › Stammdaten)
        </a>
      </div>
    </div>
  )
}

// ─── Bausteine ───────────────────────────────────────────────────────────────
function KpiStrip({ kpis }: { kpis: KpiDummy[] }) {
  // Inhaltsabhängige Spaltenreduzierung (#243 Gernot): auto-fit + minmax lässt die
  // Spaltenzahl stufenlos sinken, sobald eine Kachel sonst zu schmal für „Zahl +
  // Einheit" würde — die Engstelle kurz vor einem festen Breakpoint entfällt damit.
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(248px,1fr))] gap-3">
      {kpis.map((k) => (
        <KPICard key={k.title} title={k.title} value={k.value} unit={k.unit} color={k.color} icon={k.icon} />
      ))}
    </div>
  )
}

function DummyChart({ label, tall }: { label: string; tall?: boolean }) {
  return (
    <div className={`${tall ? 'h-full min-h-[300px]' : 'h-40'} rounded-lg border border-dashed border-gray-300 dark:border-gray-600 flex items-center justify-center text-gray-400 dark:text-gray-500 text-sm gap-2`}>
      <LineChart className="h-5 w-5" />
      {label}
    </div>
  )
}

// Dünner Adapter auf die geteilte IASubTabBar (SoT) — hält die state-getriebene
// Vorschau-Signatur (tabs/active/onSelect), rendert aber die EINE Leiste.
function SubTabBar<T extends string>({ tabs, active, onSelect }: { tabs: readonly T[]; active: T; onSelect: (t: T) => void }) {
  return (
    <IASubTabBar items={tabs.map((t) => ({ key: t, label: t, active: active === t, onClick: () => onSelect(t) }))} />
  )
}

// View-Schale: zweite Leiste bleibt ab `lg` FIX (außerhalb des Scrollbereichs),
// darunter scrollt alles zusammen (Mobile-Schale, detLAN/Gernot #243). Damit
// schließt der vertikale Scrollbalken die zweite Leiste auf dem Desktop NICHT
// mehr ein — behebt das Safari/Firefox-Ruckeln der vormals `sticky`-Leiste.
function ViewShell({ bar, children }: { bar?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="lg:flex lg:flex-col lg:h-full lg:min-h-0">
      {bar}
      <div className="lg:flex-1 lg:overflow-auto lg:min-h-0">{children}</div>
    </div>
  )
}

// ─── Persistenz Klappzustand + Reihenfolge (detLAN #243 A4) ───────────────────
// Vorschau merkt sich pro Sicht, welche Blöcke zu/auf sind (und im Cockpit die
// Reihenfolge) — via localStorage. In der echten App ist das der B6-SoT.
const LS_PREFIX = 'eedc-preview-bloecke:'
function ladeBlockState(key: string): { order?: string[]; zu?: string[] } {
  try {
    const raw = localStorage.getItem(LS_PREFIX + key)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}
function speichereBlockState(key: string, state: { order: string[]; zu: string[] }) {
  try {
    localStorage.setItem(LS_PREFIX + key, JSON.stringify(state))
  } catch {
    /* localStorage nicht verfügbar (Privatmodus o. Ä.) — Persistenz still überspringen */
  }
}

// ─── Universelles Block-Modell (Gernot-Entscheid 2026-06-13) ──────────────────
// JEDER Block (KPI-Strip, Hauptblock, Werte/Tabelle, Detail-Sektion …) ist
// einklappbar (⌄) und hat einen Fokus/Vollbild-Schalter (⤢) — app-weit auf allen
// Inhalts-Achsen (Cockpit/Komponenten/Auswertungen/Community). In den Cockpit-
// Zeitsichten zusätzlich per ↑↓ verschiebbar (Monatsbericht-Muster, fester Satz).
// Fokus macht u. a. den Live-Energiefluss wieder bildschirmfüllend (Erhalt der
// beliebten Live-Seite). Persistenz pro Sicht = B6-SoT (in der echten App).
interface Block {
  id: string
  title: string
  icon?: LucideIcon
  farbe?: string
  summary?: string
  /** Optionales Status-Element rechts im Kopf (z. B. Einstellungs-Status-Icon). */
  badge?: React.ReactNode
  /** Default-Zustand; false = startet eingeklappt (z. B. datenreich/mobil). */
  defaultOpen?: boolean
  /** `fokus` = Vollbild-Render (Charts groß). Param mit _ wenn ungenutzt. */
  render: (fokus: boolean) => React.ReactNode
}

function BloeckeView({ bloecke, sortierbar = false, persistKey }: { bloecke: Block[]; sortierbar?: boolean; persistKey: string }) {
  const ids = useMemo(() => bloecke.map((b) => b.id), [bloecke])
  const [order, setOrder] = useState<string[]>(() => {
    const gespeichert = ladeBlockState(persistKey).order
    if (!gespeichert) return ids
    // Nur bekannte IDs übernehmen, neue/fehlende hinten anhängen (Schema-robust).
    const gueltig = gespeichert.filter((id) => ids.includes(id))
    return [...gueltig, ...ids.filter((id) => !gueltig.includes(id))]
  })
  const [zu, setZu] = useState<Set<string>>(() => {
    const gespeichert = ladeBlockState(persistKey).zu
    return gespeichert
      ? new Set(gespeichert.filter((id) => ids.includes(id)))
      : new Set(bloecke.filter((b) => b.defaultOpen === false).map((b) => b.id))
  })
  const [fokus, setFokus] = useState<string | null>(null)
  const byId = useMemo(() => Object.fromEntries(bloecke.map((b) => [b.id, b] as const)), [bloecke])

  // Klappzustand (+ Reihenfolge) pro Sicht merken.
  useEffect(() => {
    speichereBlockState(persistKey, { order, zu: [...zu] })
  }, [persistKey, order, zu])

  const verschieben = (i: number, r: -1 | 1) => {
    const ziel = i + r
    if (ziel < 0 || ziel >= order.length) return
    const next = [...order]
    ;[next[i], next[ziel]] = [next[ziel], next[i]]
    setOrder(next)
  }
  const toggle = (id: string) => {
    const next = new Set(zu)
    next.has(id) ? next.delete(id) : next.add(id)
    setZu(next)
  }

  // ── Fokus/Vollbild: nur dieser Block, füllt den Inhaltsbereich ──────────────
  if (fokus && byId[fokus]) {
    const b = byId[fokus]
    return (
      <div className="min-h-[85vh] flex flex-col p-3 sm:p-6 gap-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
            {b.icon && <b.icon className={`h-5 w-5 ${b.farbe ?? ''}`} />}
            {b.title}
            <span className="text-xs font-normal text-gray-400 dark:text-gray-500">Fokus / Vollbild</span>
          </h2>
          <button type="button" onClick={() => setFokus(null)}
            className="min-h-[44px] flex items-center gap-2 px-3 rounded-lg text-sm font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700">
            <Minimize2 className="h-4 w-4" /> Zurück
          </button>
        </div>
        <div className="flex-1 min-h-0">{b.render(true)}</div>
      </div>
    )
  }

  const ordered = order.map((id) => byId[id]).filter(Boolean) as Block[]
  return (
    <div className="p-3 sm:p-6 space-y-3 max-w-[1920px] mx-auto">
      <p className="text-xs text-gray-400 dark:text-gray-500">
        Jeder Block: <ChevronDown className="inline h-3 w-3" /> einklappen · <Maximize2 className="inline h-3 w-3" /> Fokus/Vollbild
        {sortierbar && <> · <ArrowUp className="inline h-3 w-3" /><ArrowDown className="inline h-3 w-3" /> verschieben</>}
        {' '}· Zustand bleibt gemerkt
      </p>
      {ordered.map((b, i) => {
        const istZu = zu.has(b.id)
        return (
          <section key={b.id} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
            <div className="flex items-center gap-2 px-3 min-h-[44px]">
              <button type="button" onClick={() => toggle(b.id)} className="flex-1 flex items-center gap-2 text-left py-2 min-w-0">
                {b.icon && <b.icon className={`h-4 w-4 flex-shrink-0 ${b.farbe ?? 'text-gray-400 dark:text-gray-500'}`} />}
                <span className="text-sm font-semibold text-gray-900 dark:text-white whitespace-nowrap">{b.title}</span>
                {b.summary && <span className="text-xs text-gray-400 dark:text-gray-500 truncate">{b.summary}</span>}
              </button>
              {b.badge && <div className="flex-shrink-0">{b.badge}</div>}
              <div className="flex items-center gap-0.5 flex-shrink-0">
                {sortierbar && (
                  <>
                    <button type="button" onClick={() => verschieben(i, -1)} disabled={i === 0} aria-label="nach oben"
                      className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-30 disabled:cursor-default">
                      <ArrowUp className="h-4 w-4" />
                    </button>
                    <button type="button" onClick={() => verschieben(i, 1)} disabled={i === ordered.length - 1} aria-label="nach unten"
                      className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-30 disabled:cursor-default">
                      <ArrowDown className="h-4 w-4" />
                    </button>
                  </>
                )}
                <button type="button" onClick={() => setFokus(b.id)} aria-label="Fokus / Vollbild"
                  className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                  <Maximize2 className="h-4 w-4" />
                </button>
                <button type="button" onClick={() => toggle(b.id)} aria-label={istZu ? 'aufklappen' : 'einklappen'}
                  className="p-2 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                  <ChevronDown className={`h-4 w-4 transition-transform ${istZu ? '-rotate-90' : ''}`} />
                </button>
              </div>
            </div>
            {!istZu && <div className="px-3 pb-3">{b.render(false)}</div>}
          </section>
        )
      })}
    </div>
  )
}

// Detail-Sektionen der Cockpit-Zeitsichten (Summary-Zeilen wie im Monatsbericht).
// Universelle Blöcke aus dem Block-SoT (#3b), Komponenten-Zeilen aus dem
// Identitäts-SoT (#3b') — keine hardcodierten Icons/Farben mehr.
// Reihenfolge wie entschieden: Energie-Bilanz → Komponenten → Finanzen UNTEN (B5).
// Community-Block bewusst ENTFERNT (O4 — lebt auf der Community-Top-Achse).
const COCKPIT_DETAIL: { id: string; icon: LucideIcon; title: string; summary: string; farbe?: string }[] = [
  { id: 'd-energie',   ...BLOCK_IDENTITAET.energieBilanz, title: 'Energie-Bilanz',     summary: '618 kWh PV · 96 % Autarkie' },
  { id: 'd-speicher',  icon: KOMPONENTEN_IDENTITAET['speicher'].icon, farbe: KOMPONENTEN_IDENTITAET['speicher'].farbe, title: 'Speicher',     summary: '99 kWh geladen · 7,7 Zyklen · 73 % η' },
  { id: 'd-emob',      icon: KOMPONENTEN_IDENTITAET['e-auto'].icon,   farbe: KOMPONENTEN_IDENTITAET['e-auto'].farbe,   title: 'E-Mobilität', summary: '62 kWh geladen · 221 km · +7,82 € vs. Verbrenner' },
  { id: 'd-finanzen',  ...BLOCK_IDENTITAET.finanzen,      title: 'Finanzen',            summary: '+90,25 € Monatsergebnis' },
]

// ─── Inhalts-Sichten ──────────────────────────────────────────────────────────
function CockpitView() {
  const [sub, setSub] = useState<CockpitSub>('Live')
  const istLive = sub === 'Live'

  const bloecke: Block[] =
    sub === 'Aussicht'
      ? [
          { id: 'kpi', title: 'Kennzahlen', ...BLOCK_IDENTITAET.kennzahlen, defaultOpen: true, render: (_f) => <KpiStrip kpis={cockpitStrip(sub)} /> },
          { id: 'wetter', title: 'Wetter + PV-Ertragsprognose', icon: Sun, render: (f) => <DummyChart label="Prognose-Verlauf (7/14 Tage · 12 Monate · Mehrjahr)" tall={f} /> },
          { id: 'quellen', title: 'Forward-Quellenvergleich', icon: BarChart3, summary: 'OpenMeteo · eedc · Solcast', render: (f) => <DummyChart label="Quellenvergleich" tall={f} /> },
        ]
      : [
          { id: 'kpi', title: 'Kennzahlen', ...BLOCK_IDENTITAET.kennzahlen, defaultOpen: true, render: (_f) => <KpiStrip kpis={cockpitStrip(sub)} /> },
          // Hauptblock: Monat/Tag/Jahr = gestapelter Verlauf-Chart (Toggle „⇄ Fluss" verworfen, O3/B4);
          // Live = Energiefluss-Default. Werte/Tabelle-Embed ENTFERNT (B9 → Auswertungen/Tabelle).
          { id: 'haupt', title: 'Hauptblock', ...BLOCK_IDENTITAET.verlauf, summary: istLive ? 'Energiefluss' : 'Verlauf', defaultOpen: true, render: (f) => <DummyChart label={istLive ? 'Energiefluss (Default Live) — ⤢ für Vollbild' : 'Verlauf'} tall={f} /> },
          ...COCKPIT_DETAIL.map((d): Block => ({
            id: d.id, title: d.title, icon: d.icon, farbe: d.farbe, summary: d.summary, defaultOpen: false,
            render: (f) => <DummyChart label={`${d.title} — Detail`} tall={f} />,
          })),
          ...(sub === 'Jahr/Gesamt'
            ? [{ id: 'berichte', title: 'Berichte & Dokumente', icon: FileText, summary: 'Jahresbericht · Dossier', defaultOpen: false, render: (_f: boolean) => <BerichtTeaser titel="Der Jahresbericht" dateiname="Jahresbericht 2025" /> } as Block]
            : []),
        ]

  return (
    <ViewShell bar={<SubTabBar tabs={COCKPIT_SUBS} active={sub} onSelect={setSub} />}>
      {/* Cockpit-Zeitsichten: alle Blöcke klapp-/fokussierbar UND sortierbar */}
      <BloeckeView key={`cockpit-${sub}`} persistKey={`cockpit-${sub}`} bloecke={bloecke} sortierbar />
    </ViewShell>
  )
}

function KomponentenView() {
  const [typ, setTyp] = useState(KOMP_TYPEN[0].key)
  const aktiv = KOMP_TYPEN.find((t) => t.key === typ)!
  // Variante C — fixe lineare Folge (Stabilität über Typen): nicht sortierbar,
  // aber klapp- und fokussierbar. Letzter Block = Einstellungen (#243 A1):
  // alle Parameter dieser Komponente am Ort der Komponente, eingeklappt.
  const bloecke: Block[] = [
    { id: 'status', title: 'Aktueller Status', icon: Activity, defaultOpen: true, render: (_f) => <KpiStrip kpis={KOMP_STATUS[typ]} /> },
    { id: 'verlauf', title: 'Verlauf im Zeitraum', ...BLOCK_IDENTITAET.verlauf, defaultOpen: true, render: (f) => <DummyChart label="Tages-/Monatschart" tall={f} /> },
    { id: 'vergleich', title: 'Vergleich', icon: BarChart3, summary: 'Diagramm ⇄ Tabelle · Saison-Toggle', defaultOpen: false, render: (f) => <DummyChart label="Vorjahr/Vormonat · wetternormalisiert" tall={f} /> },
    { id: 'aussicht', title: 'Aussicht', icon: TrendingUp, summary: 'komponentenspezifische Prognose', defaultOpen: false, render: (_f) => <p className="text-sm text-gray-500 dark:text-gray-400">z. B. „wann voll/leer" (Speicher) — entfällt bei Typen ohne sinnvolle Prognose.</p> },
    { id: 'einstellungen', title: 'Einstellungen', icon: Settings, summary: 'alle Parameter dieser Komponente — nicht mehr raten (#243)', defaultOpen: false, render: (_f) => <ParamGruppen typ={typ} /> },
  ]
  return (
    <ViewShell bar={
      <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-3 sm:px-6">
        <nav className="flex items-center gap-1 h-14 overflow-x-auto scrollbar-none">
          {KOMP_TYPEN.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTyp(t.key)}
              className={`min-h-[44px] flex items-center gap-2 px-3 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
                typ === t.key
                  ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                  : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800/50'
              }`}
            >
              <t.icon className="h-4 w-4" />
              {t.label}
            </button>
          ))}
        </nav>
      </div>
    }>
      <div className="px-3 sm:px-6 pt-4 flex items-center justify-between max-w-[1920px] mx-auto">
        <h2 className="text-lg font-bold text-gray-900 dark:text-white">{aktiv.label}</h2>
        <span className="min-h-[44px] flex items-center px-3 rounded-lg text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300">Mai 2026 ▾</span>
      </div>
      <BloeckeView key={`komp-${typ}`} persistKey={`komp-${typ}`} bloecke={bloecke} />
    </ViewShell>
  )
}

function AuswertungenView() {
  const [sub, setSub] = useState<(typeof AUSW_SUBS)[number]>('Finanzen')
  const bloecke: Block[] = [
    { id: 'main', title: sub, icon: BarChart3, summary: 'analytischer Schnitt über die ganze Anlage', defaultOpen: true, render: (f) => <DummyChart label={sub === 'Tabelle' ? 'Volle Werkbank (Spalten-Picker, CSV)' : `${sub}-Auswertung`} tall={f} /> },
    ...(sub === 'Finanzen'
      ? [
          { id: 'tkonto', title: 'SOLL/HABEN-T-Konto', icon: Wallet, summary: 'aus dem Monatsbericht hierher verlagert (F2-a)', defaultOpen: true, render: (_f: boolean) => <p className="text-sm text-gray-500 dark:text-gray-400">zeitraum-parametrisiert (Tag/Monat/Jahr) + sonstige Positionen (#310).</p> } as Block,
          { id: 'finanzbericht', title: 'Berichte & Dokumente', icon: FileText, summary: 'Finanzbericht', defaultOpen: false, render: (_f: boolean) => <BerichtTeaser titel="Der Finanzbericht" dateiname="Finanzbericht" /> } as Block,
        ]
      : []),
  ]
  return (
    <ViewShell bar={<SubTabBar tabs={AUSW_SUBS} active={sub} onSelect={setSub} />}>
      <BloeckeView key={`ausw-${sub}`} persistKey={`ausw-${sub}`} bloecke={bloecke} />
    </ViewShell>
  )
}

function CommunityView() {
  const [sub, setSub] = useState<(typeof COMM_SUBS)[number]>('Übersicht')
  const kpis: KpiDummy[] = [
    { title: 'Dein Rang',    value: '#12', color: 'blue', icon: Trophy },
    { title: 'Spez. Ertrag', value: '1.040', unit: 'kWh/kWp', color: 'cyan', icon: TrendingUp },
    { title: 'Region',       value: 'Bayern', color: 'green', icon: MapPin },
  ]
  const bloecke: Block[] = [
    { id: 'kpi', title: 'Kennzahlen', icon: Trophy, defaultOpen: true, render: (_f) => <KpiStrip kpis={kpis} /> },
    { id: 'inhalt', title: sub, icon: BarChart3, defaultOpen: true, render: (f) => <DummyChart label={`Community: ${sub}`} tall={f} /> },
  ]
  return (
    <ViewShell bar={<SubTabBar tabs={COMM_SUBS} active={sub} onSelect={setSub} />}>
      <BloeckeView key={`comm-${sub}`} persistKey={`comm-${sub}`} bloecke={bloecke} />
    </ViewShell>
  )
}

function HilfeView() {
  return (
    <ViewShell>
      <div className="p-3 sm:p-6 space-y-4 max-w-3xl mx-auto">
        <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">Hilfe <span className="text-xs font-normal text-gray-400 dark:text-gray-500">In-App-Handbuch</span></h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">Inkl. „Wo ist X hin?" beim v4-Flip (Aussichten → Cockpit/Aussicht, T-Konto → Auswertungen/Finanzen …).</p>
        </section>
      </div>
    </ViewShell>
  )
}

// Status je Einstellungs-Kachel (#243-Review): klares Icon + Tooltip statt
// kryptischer Emojis. Farbachse OK/Warnung/Info = Status-Kanon (in der echten
// App aus dem STATUS_ICONS/colors-SoT). `hinweis` = Daten-Checker-artiger
// Tooltip, der bei ⚠ erklärt, WAS zu tun ist (OK/NOK mit Begründung).
type KachelStatus = 'ok' | 'warn' | 'neu'
const STATUS_META: Record<KachelStatus, { icon: LucideIcon; farbe: string; standardTitel: string }> = {
  ok:   { icon: CheckCircle2,  farbe: 'text-green-500', standardTitel: 'eingerichtet' },
  warn: { icon: AlertTriangle, farbe: 'text-amber-500', standardTitel: 'braucht Aufmerksamkeit' },
  neu:  { icon: Sparkles,      farbe: 'text-blue-500',  standardTitel: 'neu — noch nicht eingerichtet' },
}

// Einstellungs-Eintrag = ein Block (auf-/zuklappbar + Fokus, analog Komponenten):
// eingeklappt nur Titel + Status; aufgeklappt Erläuterung + Hilfeverweis +
// Aktions-Button (#243-Review: keine Kachel-Buttons mehr als Navigation).
// Konkreter Seiten-Inhalt je Eintrag (#243-Review „weiter konkretisieren"):
// realistische Form/Tabelle/Liste/Wizard statt generischer Dummy-Felder.
type Inhalt =
  | { kind: 'form'; felder: { label: string; wert: string }[] }
  | { kind: 'tabelle'; spalten: string[]; zeilen: string[][] }
  | { kind: 'liste'; eintraege: string[] }
  | { kind: 'wizard'; schritte: string[] }

interface EinstellungEintrag {
  id: string
  name: string
  icon: LucideIcon
  status: KachelStatus
  hinweis?: string
  beschreibung: string
  hilfe?: string
  aktion: string
  aktionIcon?: LucideIcon
  inhalt: Inhalt
}
// Kategorien = zweite Leiste, analog Komponenten (fix, nicht verschiebbar).
const EINSTELLUNGEN_KATEGORIEN: { key: string; label: string; icon: LucideIcon; eintraege: EinstellungEintrag[] }[] = [
  { key: 'stammdaten', label: 'Stammdaten', icon: Settings, eintraege: [
    { id: 'anlage', name: 'Anlage', icon: Settings, status: 'ok', aktion: 'Speichern', aktionIcon: Settings,
      beschreibung: 'Stammdaten der Anlage: Name, Leistung, Standort, Steuern (USt / §51 EEG) und Prognosequelle.', hilfe: 'Hilfe: Anlage einrichten',
      inhalt: { kind: 'form', felder: [
        { label: 'Anlagenname', wert: 'Haus Müller' }, { label: 'Leistung', wert: '9,8 kWp' },
        { label: 'Standort', wert: '85221 Dachau' }, { label: 'USt-Behandlung', wert: 'Regelbesteuerung (19 %)' },
        { label: '§51 EEG (Negativpreise)', wert: 'aktiv' }, { label: 'Prognosequelle', wert: 'eedc (kalibriert)' },
      ] } },
    { id: 'strompreise', name: 'Strompreise', icon: Zap, status: 'ok', aktion: 'Tarif hinzufügen', aktionIcon: Zap,
      beschreibung: 'Netzbezug, Einspeisevergütung und Grundpreis — zeitlich gestaffelt (gültig ab/bis), inkl. WP-/Wallbox-Spezialtarife.', hilfe: 'Hilfe: Strompreise',
      inhalt: { kind: 'tabelle', spalten: ['Gültig ab', 'Netzbezug', 'Einspeisung', 'Verwendung'], zeilen: [
        ['01.2026', '32,1 ct', '8,2 ct', 'allgemein'], ['01.2026', '28,0 ct', '—', 'Wärmepumpe'], ['01.2025', '30,5 ct', '8,2 ct', 'allgemein'],
      ] } },
    { id: 'investitionen', name: 'Investitionen', icon: PiggyBank, status: 'ok', aktion: 'Komponente hinzufügen', aktionIcon: PiggyBank,
      beschreibung: 'Komponenten anlegen oder entfernen. Parameter bearbeitest du hier oder direkt bei der Komponente (beides möglich).', hilfe: 'Hilfe: Investitionen',
      inhalt: { kind: 'liste', eintraege: [
        'PV-Anlage · 9,8 kWp', 'Speicher · 10 kWh', 'Wärmepumpe · Luft/Wasser', 'Wallbox · 11 kW', 'E-Auto · 14.200 km/Jahr',
      ] } },
    { id: 'solarprognose', name: 'Solarprognose', icon: Sun, status: 'warn', hinweis: 'PVGIS-Abruf älter als 7 Tage — Prognose neu abrufen',
      aktion: 'Prognose neu abrufen', aktionIcon: Activity, beschreibung: 'PVGIS-Ertragsprognose und Horizontprofil der Anlage.', hilfe: 'Hilfe: Solarprognose',
      inhalt: { kind: 'form', felder: [
        { label: 'Systemverluste', wert: '14 %' }, { label: 'Horizontprofil', wert: 'hochgeladen' },
        { label: 'Letzter Abruf', wert: 'vor 8 Tagen' }, { label: 'Strahlungsmodell', wert: 'PVGIS-SARAH3' },
      ] } },
    { id: 'infothek', name: 'Infothek', icon: BookOpen, status: 'ok', aktion: 'Eintrag hinzufügen', aktionIcon: BookOpen,
      beschreibung: 'Wissensspeicher zu deiner Anlage: Notizen, Links und Dokumente — eng an die Investitionen geknüpft.', hilfe: 'Hilfe: Infothek',
      inhalt: { kind: 'liste', eintraege: ['Wärmepumpe — Handbuch & Wartung', 'PV-Module — Datenblätter', 'Speicher — Garantie-Unterlagen', 'Förderbescheid 2021'] } },
    { id: 'berichte', name: 'Berichte & Dokumente', icon: FileText, status: 'ok', aktion: 'ZIP erstellen', aktionIcon: FileText,
      beschreibung: 'Anlagengebundene PDF-Berichte und Dossiers — einzeln oder als ZIP, mit Jahr-Auswahl.', hilfe: 'Hilfe: Berichte',
      inhalt: { kind: 'liste', eintraege: ['Jahresbericht 2025', 'Anlagendokumentation', 'Finanzbericht', 'Infothek-Dossier'] } },
  ] },
  { key: 'daten', label: 'Daten', icon: Table2, eintraege: [
    { id: 'monatsdaten', name: 'Monatsdaten', icon: Table2, status: 'ok', aktion: 'Wert erfassen',
      beschreibung: 'Zählerstände und Monatswerte pflegen und korrigieren.',
      inhalt: { kind: 'tabelle', spalten: ['Monat', 'Netzbezug', 'Einspeisung', 'PV-Erzeugung'], zeilen: [
        ['Mai 2026', '143 kWh', '189 kWh', '612 kWh'], ['Apr 2026', '201 kWh', '142 kWh', '548 kWh'], ['Mär 2026', '288 kWh', '96 kWh', '421 kWh'],
      ] } },
    { id: 'energieprofil', name: 'Energieprofil-Pflege', icon: Activity, status: 'ok', aktion: 'Ausführen', aktionIcon: ArrowRight,
      beschreibung: 'Backfill aus der HA-Statistik und einzelne Tage neu berechnen.',
      inhalt: { kind: 'liste', eintraege: ['Vollbackfill aus HA-Statistik', 'Einzelnen Tag neu berechnen', 'Zeitraum neu aggregieren'] } },
    { id: 'datenchecker', name: 'Daten-Checker', icon: Wallet, status: 'warn', hinweis: '3 Plausibilitäts-Hinweise offen — ansehen',
      aktion: 'Reparatur-Werkbank', beschreibung: 'Plausibilitäts-Prüfung deiner Daten — findet Lücken und Ausreißer.', hilfe: 'Hilfe: Daten-Checker',
      inhalt: { kind: 'liste', eintraege: [
        '⚠ Mai: PV-Erzeugung an 2 Tagen 0 kWh', '⚠ WP-Zählerstand-Sprung am 12.05.', 'ℹ Speicher-Wirkungsgrad < 80 % im April',
      ] } },
  ] },
  { key: 'integration', label: 'Integration', icon: Plug, eintraege: [
    { id: 'sensoren', name: 'Sensor-Zuordnung', icon: MapPin, status: 'ok', aktion: 'Zuordnung speichern',
      beschreibung: 'Home-Assistant-Entities den eedc-Feldern zuordnen.', hilfe: 'Hilfe: Sensor-Zuordnung',
      inhalt: { kind: 'tabelle', spalten: ['eedc-Feld', 'HA-Entity', 'Status'], zeilen: [
        ['PV-Erzeugung', 'sensor.pv_total', '✓'], ['Netzbezug', 'sensor.grid_import', '✓'], ['WP-Strom', 'sensor.hp_power', '⚠ kW statt kWh'],
      ] } },
    { id: 'statistik-import', name: 'Statistik-Import', icon: BarChart3, status: 'neu', aktion: 'Import starten', aktionIcon: ArrowRight,
      beschreibung: 'Langzeit-Statistik aus Home Assistant rückwirkend importieren.',
      inhalt: { kind: 'wizard', schritte: ['Quelle wählen', 'Zeitraum festlegen', 'Vorschau prüfen', 'Importieren'] } },
    { id: 'mqtt', name: 'MQTT-Export', icon: ArrowRight, status: 'ok', aktion: 'Speichern',
      beschreibung: 'eedc-Kennzahlen und Prognosen als MQTT-/HA-Sensoren ausgeben.', hilfe: 'Hilfe: MQTT-Export',
      inhalt: { kind: 'form', felder: [
        { label: 'Broker', wert: 'core-mosquitto' }, { label: 'Topic-Präfix', wert: 'eedc/' },
        { label: 'Aktive Sensoren', wert: '12' }, { label: 'Diagnose-Sensoren', wert: 'aktiv' },
      ] } },
    { id: 'import-wizards', name: 'Import-Assistenten', icon: Boxes, status: 'neu', aktion: 'Assistent starten', aktionIcon: ArrowRight,
      beschreibung: 'Cloud-Importe (Anker, EcoFlow …) und Datei-Importe.',
      inhalt: { kind: 'liste', eintraege: ['Anker SOLIX', 'EcoFlow', 'Sungrow', 'CSV-Datei'] } },
    { id: 'einrichtung', name: 'Ersteinrichtung', icon: Settings, status: 'ok', aktion: 'Assistent starten', aktionIcon: ArrowRight,
      beschreibung: 'Geführte Einrichtung in einem Durchlauf: Anlage, Sensoren und Strompreise.', hilfe: 'Hilfe: Erste Schritte',
      inhalt: { kind: 'wizard', schritte: ['Anlage anlegen', 'Sensoren zuordnen', 'Strompreise erfassen', 'Fertig'] } },
  ] },
  { key: 'system', label: 'System', icon: Wrench, eintraege: [
    { id: 'allgemein', name: 'Allgemein', icon: Settings, status: 'ok', aktion: 'Speichern',
      beschreibung: 'Theme, Sprache und allgemeine Optionen.',
      inhalt: { kind: 'form', felder: [
        { label: 'Theme', wert: 'System' }, { label: 'Sprache', wert: 'Deutsch' }, { label: 'Einheiten', wert: 'kWh / €' },
      ] } },
    { id: 'backup', name: 'Backup', icon: Battery, status: 'warn', hinweis: 'Letztes Backup vor 21 Tagen',
      aktion: 'Backup erstellen', beschreibung: 'Sicherung und Wiederherstellung der eedc-Datenbank.',
      inhalt: { kind: 'liste', eintraege: ['24.05.2026 03:00 · automatisch', '17.05.2026 03:00 · automatisch', '01.05.2026 18:22 · manuell'] } },
    { id: 'protokolle', name: 'Protokolle', icon: LineChart, status: 'ok', aktion: 'Aktualisieren',
      beschreibung: 'System-Logs einsehen.',
      inhalt: { kind: 'liste', eintraege: ['07:05 Snapshot-Job ok', '06:00 Prognose-Abruf ok', '03:00 Backup erstellt'] } },
  ] },
  { key: 'teilen', label: 'Daten teilen', icon: Users, eintraege: [
    { id: 'community', name: 'Community-Share', icon: Users, status: 'neu', aktion: 'Einrichten',
      beschreibung: 'Anonyme Kennzahlen zum Community-Benchmark beitragen.', hilfe: 'Hilfe: Community',
      inhalt: { kind: 'form', felder: [
        { label: 'Auto-Share', wert: 'nach Monatsabschluss' }, { label: 'Sichtbarkeit', wert: 'anonym' }, { label: 'Region', wert: 'Bayern' },
      ] } },
  ] },
]

// Die EIGENTLICHE Seite, je nach Inhalts-Art gerendert (Skelett, echte Struktur).
function EinstellungSeite({ inhalt, fokus }: { inhalt: Inhalt; fokus: boolean }) {
  switch (inhalt.kind) {
    case 'form':
      return (
        <div className={`grid gap-3 ${fokus ? 'sm:grid-cols-2 lg:grid-cols-3' : 'sm:grid-cols-2'}`}>
          {inhalt.felder.map((f) => (
            <label key={f.label} className="block">
              <span className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{f.label}</span>
              <span className="flex items-center h-9 px-3 rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 text-sm text-gray-900 dark:text-white">{f.wert}</span>
            </label>
          ))}
        </div>
      )
    case 'tabelle':
      return (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-400 dark:text-gray-500">
                {inhalt.spalten.map((s) => <th key={s} className="py-1 pr-4 font-medium whitespace-nowrap">{s}</th>)}
              </tr>
            </thead>
            <tbody>
              {inhalt.zeilen.map((z, i) => (
                <tr key={i} className="border-t border-gray-100 dark:border-gray-700">
                  {z.map((c, j) => <td key={j} className="py-1.5 pr-4 text-gray-700 dark:text-gray-300 whitespace-nowrap">{c}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    case 'liste':
      return (
        <ul className="space-y-1.5 text-sm text-gray-700 dark:text-gray-300">
          {inhalt.eintraege.map((e) => (
            <li key={e} className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-gray-300 dark:bg-gray-600" />{e}
            </li>
          ))}
        </ul>
      )
    case 'wizard':
      return (
        <ol className="space-y-2">
          {inhalt.schritte.map((s, i) => (
            <li key={s} className="flex items-center gap-3 text-sm text-gray-700 dark:text-gray-300">
              <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/50 text-primary-700 dark:text-primary-300 text-xs font-semibold">{i + 1}</span>
              {s}
            </li>
          ))}
        </ol>
      )
  }
}

// Aufgeklappter Block: Erläuterung + die EIGENTLICHE Seite eingebettet
// (#243-Review: inline statt Wegnavigieren; im Fokus großflächig) + Aktion/Hilfe.
function EinstellungInhalt({ e, fokus }: { e: EinstellungEintrag; fokus: boolean }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600 dark:text-gray-300">{e.beschreibung}</p>
      <div className={`rounded-lg border border-dashed border-gray-300 dark:border-gray-600 p-4 ${fokus ? 'min-h-[280px]' : ''}`}>
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">
          {e.name} — <span className="italic">Muster, stark verkürzt (nur Platzhalter, nicht die vollständige Seite)</span>{fokus ? ' · Vollbild' : ' · ⤢ Fokus'}
        </p>
        <EinstellungSeite inhalt={e.inhalt} fokus={fokus} />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <button type="button" className="min-h-[44px] inline-flex items-center gap-2 px-4 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700">
          {e.aktionIcon && <e.aktionIcon className="h-4 w-4" />}
          {e.aktion}
        </button>
        {e.hilfe && (
          <a href="#" className="min-h-[44px] inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
            <HelpCircle className="h-4 w-4" /> {e.hilfe}
          </a>
        )}
      </div>
    </div>
  )
}

function EinstellungenView() {
  const [kat, setKat] = useState(EINSTELLUNGEN_KATEGORIEN[0].key)
  const aktiv = EINSTELLUNGEN_KATEGORIEN.find((k) => k.key === kat)!
  const bloecke: Block[] = aktiv.eintraege.map((e) => {
    const m = STATUS_META[e.status]
    return {
      id: e.id,
      title: e.name,
      icon: e.icon,
      defaultOpen: false,
      badge: (
        <span title={e.hinweis ?? m.standardTitel} className="flex items-center">
          <m.icon className={`h-4 w-4 ${m.farbe}`} aria-label={m.standardTitel} />
        </span>
      ),
      render: (f: boolean) => <EinstellungInhalt e={e} fokus={f} />,
    }
  })
  return (
    <ViewShell bar={
      /* Zweite Leiste = Kategorien (analog Komponenten, fix). Aktiver Reiter = Überschrift. */
      <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-3 sm:px-6">
        <nav className="flex items-center gap-1 h-14 overflow-x-auto scrollbar-none">
          {EINSTELLUNGEN_KATEGORIEN.map((k) => (
            <button
              key={k.key}
              type="button"
              onClick={() => setKat(k.key)}
              className={`min-h-[44px] flex items-center gap-2 px-3 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
                kat === k.key
                  ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                  : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800/50'
              }`}
            >
              <k.icon className="h-4 w-4" />
              {k.label}
            </button>
          ))}
        </nav>
      </div>
    }>
      <div className="px-3 sm:px-6 pt-4 space-y-3 max-w-[1920px] mx-auto">
        <input
          type="search"
          placeholder="🔍 Suchen in allen Einstellungen …"
          className="w-full min-h-[44px] rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 text-sm text-gray-900 dark:text-white"
        />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-400 dark:text-gray-500">
          <span className="flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5 text-green-500" /> eingerichtet</span>
          <span className="flex items-center gap-1"><AlertTriangle className="h-3.5 w-3.5 text-amber-500" /> braucht Aufmerksamkeit (Tooltip zeigt Grund)</span>
          <span className="flex items-center gap-1"><Sparkles className="h-3.5 w-3.5 text-blue-500" /> neu</span>
        </div>
        <p className="text-xs text-gray-400 dark:text-gray-500">
          Komponenten-Parameter (z. B. WP-Effizienz, Speicher-Preise) bearbeitest du an beiden Stellen:
          hier über <span className="font-medium">Investitionen</span> oder direkt bei der Komponente unter{' '}
          <span className="font-medium">Komponenten › ‹Typ› › Einstellungen</span>.
        </p>
      </div>
      <BloeckeView key={`einst-${kat}`} persistKey={`einst-${kat}`} bloecke={bloecke} />
    </ViewShell>
  )
}

// ─── Schale ───────────────────────────────────────────────────────────────────
// Demo-Anlagen für den Vorschau-Selektor (backendlos; ≥2 → Selektor sichtbar).
const DEMO_ANLAGEN = [
  { id: 1, anlagenname: 'Eigenheim' },
  { id: 2, anlagenname: 'Ferienhaus Süd' },
]

// ─── VORSCHLAG Shell-Konzept-Runde: persistente Status-Fußzeile ───────────────
// „Wie geht's dem System gerade?" — heute über die App verstreut (Connector-
// Status, Daten-Checker, MQTT-Badge, Backup-Alter, Update-Banner). Idee (Gernot
// 2026-06-20, à la Windows-Dienste): EINE glanceable Leiste unten, je Dienst ein
// Status-Punkt + Detail, klickbar → Details/Cross-Link. Hier als Demo-Vorschlag;
// gehört in die gemeinsame Shell-Konzept-Runde (Header-Chrome + Footer), bevor
// die echte (geteilte) Komponente entsteht. Version wandert mit hierher.
const STATUS_DIENSTE: { label: string; ton: 'ok' | 'warnung' | 'kritisch'; detail: string }[] = [
  { label: 'Connectoren', ton: 'ok', detail: '2/2 online' },
  { label: 'Daten-Checker', ton: 'warnung', detail: '3 Hinweise' },
  { label: 'MQTT', ton: 'ok', detail: 'verbunden' },
  { label: 'Backup', ton: 'ok', detail: 'vor 2 Tagen' },
  { label: 'Solarprognose', ton: 'warnung', detail: 'PVGIS > 7 Tage' },
]
const TON_KLASSE = { ok: 'text-green-500', warnung: 'text-amber-500', kritisch: 'text-red-500' } as const

function StatusFooter() {
  return (
    <footer className="shrink-0 h-9 border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 px-3 sm:px-6 flex items-center gap-4 overflow-x-auto scrollbar-none text-xs">
      {STATUS_DIENSTE.map((d) => {
        const Icon = d.ton === 'ok' ? CheckCircle2 : AlertTriangle
        return (
          <button key={d.label} type="button" title={`${d.label}: ${d.detail} — Details öffnen`}
            className="flex items-center gap-1.5 whitespace-nowrap shrink-0 hover:underline">
            <Icon className={`h-3.5 w-3.5 ${TON_KLASSE[d.ton]}`} />
            <span className="text-gray-600 dark:text-gray-300 font-medium">{d.label}</span>
            <span className="text-gray-400 dark:text-gray-500">{d.detail}</span>
          </button>
        )
      })}
      <span className="ml-auto shrink-0 font-mono text-gray-400 dark:text-gray-500 whitespace-nowrap">eedc v{APP_VERSION}</span>
    </footer>
  )
}

export default function IASkeleton() {
  const [top, setTop] = useState<TopKey>('cockpit')
  const [demoAnlageId, setDemoAnlageId] = useState(1)

  // State-getriebene Items für die geteilte IATopNav (SoT). Marke, Theme-Cycle,
  // Hamburger + lg-Responsive liefert die Shell; die Vorschau steuert nur `top`.
  const item = (t: { key: TopKey; label: string; icon: LucideIcon }) => ({
    key: t.key, label: t.label, icon: t.icon, active: top === t.key, onClick: () => setTop(t.key),
  })
  const badge = (
    <span className="ml-3 px-2 py-0.5 text-[10px] font-mono rounded bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200">
      Vorschau
    </span>
  )

  return (
    <div className="h-dvh flex flex-col overflow-hidden bg-gray-50 dark:bg-gray-900">
      <IATopNav
        inhalt={TOP_INHALT.map(item)}
        meta={TOP_META.map(item)}
        modusBadge={badge}
        anlagenSelektor={<AnlagenSelektorView anlagen={DEMO_ANLAGEN} selectedId={demoAnlageId} onSelect={setDemoAnlageId} />}
      />

      {/* Inhalt je Achse. Ab `lg` scrollt nur der Inhalt (ViewShell), darunter
          scrollt `main` komplett (zweite Leiste scrollt mit weg, Mobile-Schale). */}
      <main className="flex-1 overflow-auto lg:overflow-hidden lg:flex lg:flex-col lg:min-h-0">
        {top === 'cockpit' && <CockpitView />}
        {top === 'komponenten' && <KomponentenView />}
        {top === 'auswertungen' && <AuswertungenView />}
        {top === 'community' && <CommunityView />}
        {top === 'hilfe' && <HilfeView />}
        {top === 'einstellungen' && <EinstellungenView />}
      </main>

      {/* VORSCHLAG (Shell-Konzept-Runde): persistente Status-Fußzeile + Version. */}
      <StatusFooter />
    </div>
  )
}
