/**
 * EnergieFluss — Animiertes Energiefluss-Diagramm (ersetzt EnergieBilanz).
 *
 * Zeigt alle Komponenten als Knoten um ein zentrales Haus-Symbol.
 * Animierte Linien zeigen Flussrichtung und -stärke.
 * Informationsparität mit EnergieBilanz: kW-Werte, Icons, Farben,
 * Tages-kWh Tooltips, Σ Erzeugung/Verbrauch.
 */

import { useState, useEffect, useRef, useMemo, type ReactNode } from 'react'
import { Sun, Zap, Battery, Car, Flame, Wrench, Home, Plug, Heater, Droplets, Snowflake, Fan, Waves, Sparkles, Zap as ZapIcon } from 'lucide-react'
import type { LiveFahrzeug, LiveKomponente, LiveGauge } from '../../api/liveDashboard'
import { CHART_COLORS, COLORS, ENERGIEFLUSS_SAUM, KATEGORIE_FARBEN, SOLAR_INTENSITAET, STATUS_COLORS, fmtZahl } from '../../lib'
import { useChartTheme } from '../../context/ThemeContext'
import EnergieFlussBackground from './EnergieFlussBackground'
import {
  RAHMEN_CHIP_HOEHE, W_DEFAULT, flowPath, layoutEnergieFluss,
  type BuehnenMass, type GezeichneterKnoten, type KachelAuto,
} from './energieFlussLayout'
import { verbergeTouchTooltip } from '../../hooks/useTouchTitleTooltip'

// ─── Lite-Modus (reduzierte Animationen für Mobile/WebView) ─────────

const LITE_STORAGE_KEY = 'eedc-energiefluss-lite'

/** Auto-Detect: HA Companion App, iPad/Tablet oder schmales Viewport → lite */
function detectLiteDefault(): boolean {
  if (typeof window === 'undefined') return false
  const ua = navigator.userAgent
  // HA Companion App (Android/iOS)
  if (/HomeAssistant/i.test(ua)) return true
  // iPad — auch iPadOS 13+, das sich in Safari als "Macintosh" mit Touch-Support meldet
  if (/iPad|iPod/i.test(ua)) return true
  if (/Macintosh/i.test(ua) && navigator.maxTouchPoints > 1) return true
  // Phones
  if (/Android|iPhone/i.test(ua) && window.innerWidth < 768) return true
  // prefers-reduced-motion
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return true
  return false
}

function useLiteMode(): [boolean, () => void] {
  const [lite, setLite] = useState(() => {
    const stored = localStorage.getItem(LITE_STORAGE_KEY)
    if (stored !== null) return stored === '1'
    return detectLiteDefault()
  })

  useEffect(() => {
    localStorage.setItem(LITE_STORAGE_KEY, lite ? '1' : '0')
  }, [lite])

  const toggle = () => setLite(prev => !prev)
  return [lite, toggle]
}

// ─── Hintergrund-Variante ────────────────────────────────────────────

const BG_VARIANT_KEY = 'eedc-energiefluss-bg'
export type BgVariant = 'default' | 'haus' | 'sunset' | 'alps' | 'alpenpanorama' | 'milchstrasse' | 'dolomiten' | 'nebula' | 'sternennacht' | 'exoplanet'

const BG_VARIANTS: BgVariant[] = ['default', 'haus', 'sunset', 'alps', 'alpenpanorama', 'milchstrasse', 'dolomiten', 'nebula', 'sternennacht', 'exoplanet']

const BG_LABELS: Record<BgVariant, string> = {
  default:       'Tech',
  haus:          'Haus',
  sunset:        'Sunset',
  alps:          'Alpen',
  alpenpanorama: 'Alpenpanorama',
  milchstrasse:  'Milchstraße',
  dolomiten:     'Dolomiten',
  nebula:        'Nebula',
  sternennacht:  'Sternennacht',
  exoplanet:     'Exoplanet',
}

/** Foto-Varianten: Dateiname in /backgrounds/ */
const BG_PHOTO_FILE: Partial<Record<BgVariant, string>> = {
  alpenpanorama: './backgrounds/alpenpanorama.webp',
  milchstrasse:  './backgrounds/milchstrasse.webp',
  dolomiten:     './backgrounds/dolomiten.webp',
  nebula:        './backgrounds/nebula.webp',
  sternennacht:  './backgrounds/sternennacht.webp',
  exoplanet:     './backgrounds/exoplanet.webp',
}

function useBgVariant(): [BgVariant, (v: BgVariant) => void] {
  const [bgVariant, setBgVariant] = useState<BgVariant>(() => {
    const stored = localStorage.getItem(BG_VARIANT_KEY) as BgVariant | null
    return stored && BG_VARIANTS.includes(stored) ? stored : 'default'
  })

  useEffect(() => {
    localStorage.setItem(BG_VARIANT_KEY, bgVariant)
  }, [bgVariant])

  return [bgVariant, setBgVariant]
}

// ─── Shared Utilities (aus EnergieBilanz) ───────────────────────────

const ICON_MAP: Record<string, React.ElementType> = {
  sun: Sun, zap: Zap, battery: Battery, car: Car, plug: Plug,
  flame: Flame, wrench: Wrench, home: Home, heater: Heater, droplets: Droplets,
  // #398 Stufe 3: das Symbol wechselt mit dem Betriebsmodus — und AUSSCHLIESSLICH
  // hier. Der Energiefluss ist die einzige Fläche, die ohnehin „jetzt" meint;
  // `lib/komponentenStyle.ts` bleibt unberührt (Entscheid Maintainer 27.08.:
  // in Listen, Kacheln und Auswertungen behauptete ein wechselndes Symbol eine
  // Momentaktualität, die die Zahl daneben nicht hat).
  // Die Namen kommen aus dem Backend-Kanon `BETRIEBSMODUS_ICON`.
  snowflake: Snowflake, fan: Fan, waves: Waves,
}

const COLOR_MAP = KATEGORIE_FARBEN

function getColor(key: string): string {
  if (COLOR_MAP[key]) return COLOR_MAP[key]
  // Erst versuche: key ohne trailing _zahl (z.B. "waermepumpe_5" → "waermepumpe")
  const prefix = key.replace(/_\d+$/, '')
  if (COLOR_MAP[prefix]) return COLOR_MAP[prefix]
  // Dann: Basis-Kategorie aus erstem Segment (z.B. "waermepumpe_5_heizen" → "waermepumpe")
  const basis = key.split('_')[0]
  return COLOR_MAP[basis] || KATEGORIE_FARBEN.sonstige
}

/** Netz-Farbe dynamisch nach Flussrichtung: grün=Balance, orange=Einspeisung, rot=Bezug
 *  Backend-Semantik: erzeugung_kw = Netzbezug (Netz liefert ans Haus),
 *                    verbrauch_kw = Einspeisung (Netz nimmt vom Haus) */
function getNetzColor(komp: LiveKomponente, pufferW: number): string {
  const einspeisungKw = komp.verbrauch_kw ?? 0
  const bezugKw = komp.erzeugung_kw ?? 0
  const nettoW = (bezugKw - einspeisungKw) * 1000
  if (Math.abs(nettoW) <= pufferW) return STATUS_COLORS.ok // grün — Balance
  if (nettoW < 0) return COLORS.solar                       // amber — Einspeisung (PV-Überschuss)
  return COLORS.grid                                        // dunkelrot — Netzbezug (F2)
}

/** Farbe für eine Komponente — Netz dynamisch, Batterie nach Lade-/Entladezustand, Rest statisch.
 *  Exportiert für die „Liste mit Balken" (`GruppenListeOverlay`, Bau A §A5):
 *  ein Balken trägt dieselbe Rollenfarbe wie die Kachel — EINE Farbquelle. */
export function getNodeColor(komp: LiveKomponente, netzPufferW = 100): string {
  if (komp.key === 'netz') return getNetzColor(komp, netzPufferW)
  // Batterie/Speicher: Kanon Ladung=grün / Entladung=blau (Maintainer-entschieden)
  if (komp.key.startsWith('batterie_')) {
    const entlaedt = (komp.erzeugung_kw ?? 0) > (komp.verbrauch_kw ?? 0)
    return entlaedt ? CHART_COLORS.speicherEntladung : CHART_COLORS.speicherLadung
  }
  return getColor(komp.key)
}

/** Leistung formatieren: < 10 kW → Watt, ≥ 10 kW → kW. Exportiert für die
 *  „Liste mit Balken" — ihr Wert steht im selben Format wie auf der Kachel. */
export function formatPower(kw: number): string {
  if (kw <= 0) return '0 W'
  const w = Math.round(kw * 1000)
  if (w < 10000) return `${fmtZahl(w, 0)} W`
  return `${fmtZahl(kw, 1)} kW`
}

/** „Heute"-kWh eines EINZELNEN Knotens aus `tagesWerte`: exakter Key, sonst
 *  der Key ohne angehängte Nummer (`waermepumpe_5` → `waermepumpe`); fehlt
 *  beides, `null` — nichts statt 0 (ADR-002/P4). Exportiert für die „Liste mit
 *  Balken" (`GruppenListeOverlay`, Bau A §A7): Tooltip und Mitglieder-Zeile
 *  lesen den Tageswert mit EINER Regel. Nicht für Gruppen (deren Σ trägt
 *  `heuteKwh` aus dem Layout) und nicht fürs Netz (Bezug/Einspeisung getrennt). */
export function heuteKwhVon(tagesWerte: Record<string, number | null> | undefined, key: string): number | null {
  return tagesWerte?.[key]
    ?? tagesWerte?.[key.replace(/_\d+$/, '')]
    ?? null
}

/** log(1 + kW) für Liniendicke, normiert auf min..max px */
function logThickness(kw: number, maxKw: number): number {
  if (kw <= 0) return 1.5
  const maxLog = Math.log(1 + Math.max(maxKw, 0.1))
  const norm = Math.log(1 + kw) / maxLog
  return 2 + norm * 6 // 2px .. 8px
}

// ─── Types ──────────────────────────────────────────────────────────

interface EnergieFlussProps {
  komponenten: LiveKomponente[]
  summeErzeugung: number
  summeVerbrauch: number
  summePv: number
  tagesWerte?: Record<string, number | null>
  gauges?: LiveGauge[]
  pvSollKw?: number | null
  netzPufferW?: number
  /** Optionale Aktion ganz rechts in der Kopfzeile (z. B. Fokus/Vollbild-⤢). */
  kopfAktion?: ReactNode
  /**
   * Bau A §A3/§A4: steht der Energiefluss im Vollbild-Overlay (⤢ oder
   * Deep-Link)? Nur dann wird die gemessene HÖHE der Zeichenfläche
   * ausgewertet — die Zeichenfläche behält die Höhe `380·k` und wird so BREIT,
   * wie die Fläche es erlaubt. In der Karte bleibt die Höhe unausgewertet: dort
   * hängt sie am eigenen viewBox-Verhältnis (ResizeObserver → viewBox → Höhe
   * wäre eine Rückkopplung).
   */
  vollbild?: boolean
  /**
   * Bau A §A5: Klick (oder Enter/Leertaste) auf eine GRUPPENkachel meldet
   * ihren Key nach oben — `CockpitLiveV4` öffnet damit die „Liste mit Balken".
   * Ohne Handler bleibt die Kachel ohne Klick-Affordanz (kein Knopf ohne
   * Wirkung). ⛔ Nicht an `max-sm:hidden` gebunden: der Melder-Fall (viele
   * Strings, gruppiert) ist mobil.
   */
  onGruppeKlick?: (key: string) => void
  /**
   * Bau A §A5 (P-1): meldet nach jeder Layout-Änderung die GEZEICHNETEN
   * Gruppenknoten. Das Layout hängt an der gemessenen Breite, die nur diese
   * Komponente kennt — der Aufrufer braucht es, um zu entscheiden, ob der Key
   * eines offenen Overlays noch existiert. Reine Meldung: `EnergieFluss` hält
   * keinen Overlay-Zustand. `CockpitLiveV4` setzt den Prop nur bei offenem
   * Overlay (sonst kein zusätzlicher Render je 5-s-Takt).
   */
  onGruppen?: (gruppen: GezeichneterKnoten[]) => void
}

/** Versatz der hinteren Stapel-Rechtecke einer Gruppenkachel (Muster `stack: 7`, detLAN #138). */
const STAPEL_VERSATZ = 7

/** Tooltip des „Gesamtleistung"-Chips (#341) — bei BHKW-Anlagen die Abgrenzung des Werts. */
export const TIP_GESAMTLEISTUNG = 'Summe aller PV-Erzeuger (ohne Batterie/Netz)'

/** Tooltip-Satz bei ≥ 2 Wallboxen (Plan §1.4a) — eedc kennt die Zuordnung Auto → Wallbox noch nicht. */
export const SATZ_ZUORDNUNG_UNBEKANNT = 'Welches Auto an welcher Wallbox lädt, weiß eedc noch nicht.'

/** Kürzt `name` so, dass `name + suffix` höchstens `max` Zeichen hat — der Suffix (Anzahl, Ladestand) bleibt immer ganz. */
function kuerzeMitSuffix(name: string, suffix: string, max: number): string {
  if (name.length + suffix.length <= max) return name + suffix
  const platz = max - suffix.length
  return platz >= 3 ? name.slice(0, platz - 1) + '…' + suffix : suffix.trimStart()
}

/**
 * Zeichenbudget der zwei Texte, die Bau A neu in die Kachel bringt — Gruppen-
 * titel „Name (n)" und Auto-Zeile der Wallbox: Kachelbreite abzüglich Rand,
 * geteilt durch die mittlere Zeichenbreite. 0,62 em ist am breitesten
 * gängigen Font gemessen (DejaVu Sans, die System-Schrift der Dev-Box:
 * 0,49–0,71 em je Zeichen, 28.09.2026) — schmalere Schriften haben Luft.
 * ⚠ Die Einzelkachel bleibt bei `labelMaxChars` (vertraute Anzeige); für den
 * Gruppentitel ist die Grenze zu eng: „Speicher (4)" (≈ 57 von 80 Einheiten)
 * würde zu „Speich… (4)".
 */
function zeichenBudget(nodeW: number, fontSize: number): number {
  return Math.floor((nodeW - 6) / (0.62 * fontSize))
}

/**
 * Die Auto-Zeile der Wallbox-Kachel (Plan §1.4a, Muster `faltAutos`):
 * ein Auto „ID.4 52 %" (entlädt es — V2H —, mit „· entlädt"); mehrere, von
 * denen keines eindeutig lädt, die Ladestände nebeneinander „64 · 81 %".
 * Der Name weicht zuerst, Ladestand und Richtung nie.
 */
function autoZeile(auto: KachelAuto, max: number): string {
  if (auto.art === 'ladestaende') {
    return auto.autos.map(a => (a.soc != null ? String(a.soc) : '–')).join(' · ') + ' %'
  }
  const a = auto.auto
  const rest = [a.soc != null ? `${a.soc} %` : null, (a.kw ?? 0) < 0 ? 'entlädt' : null]
    .filter(Boolean).join(' · ')
  return rest ? kuerzeMitSuffix(a.label, ' ' + rest, max) : kuerzeMitSuffix(a.label, '', max)
}

/** Eine Tooltip-Zeile je Auto: Ladestand und — gemessen — lädt/entlädt. */
function autoTip(a: LiveFahrzeug): string {
  const soc = a.soc != null ? `${a.soc} %` : 'Ladestand unbekannt'
  const kw = a.kw ?? 0
  const richtung = kw > 0 ? `, lädt ${fmtZahl(kw, 2)} kW` : kw < 0 ? `, entlädt ${fmtZahl(-kw, 2)} kW (V2H)` : ''
  return `${a.label}: ${soc}${richtung}`
}

// ─── SVG Helpers ────────────────────────────────────────────────────

/** Animationsgeschwindigkeit: mehr kW = schneller */
function flowDuration(kw: number): number {
  if (kw <= 0) return 0
  return Math.max(0.8, 3 - Math.log(1 + kw) * 0.7)
}

/** Render Lucide Icon als React-Element */
function IconElement({ name, size, color, className }: { name: string; size: number; color?: string; className?: string }) {
  const Icon = ICON_MAP[name]
  if (!Icon) return null
  return <Icon width={size} height={size} color={color} className={className} />
}

/** SoC aus gauges extrahieren für einen Komponenten-Key (z.B. "batterie_3" → soc_3).
 *  Exportiert für die „Liste mit Balken" (Ladestand je Speicher/Auto). */
export function getSoc(key: string, gauges?: LiveGauge[]): number | null {
  if (!gauges) return null
  // Key-Format: "batterie_3" oder "eauto_4" → Investitions-ID ist der Teil nach dem letzten "_"
  const match = key.match(/_(\d+)$/)
  if (!match) return null
  const invId = match[1]
  const gauge = gauges.find(g => g.key === `soc_${invId}`)
  return gauge ? gauge.wert : null
}

/**
 * Nennleistung eines PV-Knotens der Live-Response (kWp) oder `null`. Das Feld
 * liefert der Builder schon EFFEKTIV (`get_erzeuger_kwp`); der Leser steht hier,
 * damit die „Liste mit Balken" (Bau A §A5) ihre Auslastung aus derselben
 * klassifizierten Stelle bezieht wie die Kachel (`check:kennwert-roh`,
 * Eintrag `EnergieFluss.tsx::k`) — kein zweiter Roh-Leser.
 */
export function nennleistungKwp(k: LiveKomponente): number | null {
  return k.leistung_kwp != null && k.leistung_kwp > 0 ? k.leistung_kwp : null
}

/** SoC Farbe: rot < 20%, gelb 20-50%, grün > 50% */
function socColor(pct: number): string {
  if (pct < 20) return STATUS_COLORS.kritisch
  if (pct < 50) return STATUS_COLORS.warnung
  return STATUS_COLORS.ok
}

// ─── Component ──────────────────────────────────────────────────────

export default function EnergieFluss({
  komponenten, summeErzeugung, summeVerbrauch, summePv, tagesWerte, gauges, pvSollKw,
  netzPufferW = 100, kopfAktion, vollbild = false, onGruppeKlick, onGruppen,
}: EnergieFlussProps) {
  const achsen = useChartTheme()
  const [lite, toggleLite] = useLiteMode()
  const [bgVariant, setBgVariant] = useBgVariant()
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const [containerW, setContainerW] = useState(W_DEFAULT)
  const [flaecheH, setFlaecheH] = useState<number | null>(null)

  // EIN ResizeObserver: die Kartenbreite (Container) und — für das Vollbild —
  // die Höhe der eigenen Zeichenfläche (das SVG). Gemessen wird beides immer;
  // ausgewertet wird die Höhe nur bei `vollbild` (s. `hoeheImVollbild`). Im
  // Overlay ist sie durch das Flex-Layout fest (`flex-1 min-h-0`), in der
  // Karte folgt sie der viewBox. Die Fläche selbst, nicht das Fenster: das
  // Overlay trägt zwei Kopfzeilen, ein Fenster-Verhältnis läge daneben (Bau A
  // W-1, gemessen: 10,74 statt 12,38 px Schrift bei 1280×800).
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const svg = svgRef.current
    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        if (svg && e.target === svg) setFlaecheH(e.contentRect.height)
        else setContainerW(e.contentRect.width ?? W_DEFAULT)
      }
    })
    ro.observe(el)
    if (svg) ro.observe(svg)
    return () => ro.disconnect()
  }, [])
  const hoeheImVollbild = vollbild && flaecheH != null && flaecheH > 0 ? flaecheH : null

  // Layout „eine Reihe je Zone" (Bau A §A3): Kaskaden, Maßstab und Faltung.
  // Die Zeichenfläche folgt der gemessenen Kartenbreite (Handy < 500 px:
  // 360/450 Einheiten, sonst 600·k mit Zoom statt höherer Karte). Im Vollbild
  // zählt zusätzlich die Höhe der Zeichenfläche (Höhe fest 380·k, Breite wächst).
  const { layout, nettoHausverbrauch } = useMemo(() => {
    const mass: BuehnenMass = hoeheImVollbild != null
      ? { breitePx: containerW, vollbild: { hoehePx: hoeheImVollbild } }
      : { breitePx: containerW }
    const _layout = layoutEnergieFluss(komponenten, mass, { gauges, tagesWerte })

    // Mitte = Residual-Verbrauch, der keinem separat dargestellten Verbraucher
    // zugeordnet ist. Das Backend liefert ihn als 'haushalt'-Komponente
    // (live_komponenten_builder: max(0, Quellen − bekannte Senken)), die NICHT
    // als eigener Orbit-Knoten gerendert wird — die Mitte ist ihre Darstellung.
    // Vorher summierte die Mitte alle Top-Level-Verbraucher inkl. Wallbox und
    // wirkte dadurch wie eine Doppelzählung (#314 NongJoWo).
    // WICHTIG: Das ist NICHT zwingend die Grundlast — nur wenn alle Verbraucher
    // einzeln erfasst sind, entspricht das Residual der reinen Haushalts-
    // Grundlast. Nicht gemappte Verbraucher fallen ebenfalls hier hinein.
    // Fallback auf die Summe, falls kein 'haushalt'-Knoten existiert (z. B. ohne
    // PV-/Netz-Sensoren) — dann ist das Residual nicht bestimmbar.
    const _haushaltNode = komponenten.find(k => k.key === 'haushalt')
    const _nettoHausverbrauch = _haushaltNode
      ? (_haushaltNode.verbrauch_kw ?? 0)
      : komponenten
          .filter(k => !k.key.startsWith('pv_') && k.key !== 'netz' && !k.key.startsWith('batterie_') && !k.parent_key)
          .reduce((sum, k) => sum + (k.verbrauch_kw ?? 0), 0)

    return { layout: _layout, nettoHausverbrauch: _nettoHausverbrauch }
  }, [komponenten, containerW, hoeheImVollbild, gauges, tagesWerte])

  // P-1: die gezeichneten Gruppen nach oben melden (nur wenn jemand fragt).
  useEffect(() => {
    onGruppen?.(layout.nodes.filter(n => n.mitglieder))
  }, [layout, onGruppen])

  if (komponenten.length === 0) return null

  // `maxKw` über die GEZEICHNETEN Knoten (eine Gruppe überschreitet jedes
  // Einzelgerät); die Zeichenfläche W × svgH kommt aus dem Layout.
  const { nodes, dims, W, H: svgH, CX, CY, maxKw, gesamtRahmen } = layout
  const { nodeW: NODE_W, nodeH: NODE_H, nodeR: NODE_R, hausR: HAUS_R } = dims
  // Alle Autos an allen Wallboxen — bei „geschätzt" (≥ 2 Wallboxen) listet jede
  // Wallbox ALLE, denn die Zuordnung reihum ist nur eine Annahme (Plan §1.4a).
  const alleAutos = [...new Map(
    nodes.flatMap(n => n.fahrzeuge ?? []).map(f => [f.investition_id, f] as const),
  ).values()].sort((a, b) => a.investition_id - b.investition_id)
  const haushalt = komponenten.find(k => k.key === 'haushalt')
  // PV-Knoten-Anzahl: bei nur einem PV-String ist die Summe redundant
  // (Wert = einzelner Knoten); Issue #137. Seit Bau A §A6 steht sie als
  // „Gesamtleistung" im Rahmen über der PV-Reihe statt über dem Haus.
  const pvCount = komponenten.filter(k => k.key.startsWith('pv_')).length

  // „Gesamtleistung"-Rahmen + Chip (#341 Rainer, Bau A §A6). Bedingung wie die
  // frühere „Solarleistung"-Zeile: Summe > 0 und mehr als ein PV-Knoten (über
  // die Komponenten, nicht über die gezeichneten Kacheln — eine gruppierte
  // Anlage behält ihre Summe). Den Platz (+14 Einheiten) hält das Layout
  // unabhängig vom Wert frei, damit das Bild nicht springt.
  const gesamt = summePv > 0 && pvCount > 1 && gesamtRahmen ? (() => {
    const text = `Gesamtleistung ${formatPower(summePv)}`
    const font = dims.socFontSize + 1
    // Breite geschätzt wie `zeichenBudget` (0,62 em je Zeichen, die breiteste
    // gängige Schrift) plus 7 Einheiten Innenrand je Seite (Muster).
    const breite = text.length * 0.62 * font + 14
    // Muster: links im Rahmen (10 Einheiten eingerückt). Ist der Rahmen dafür
    // zu schmal (eine einzige Kachel, z. B. „PV gesamt"), sitzt der Chip
    // mittig darüber — nie außerhalb der Zeichenfläche.
    const x = breite <= gesamtRahmen.breite - 20
      ? gesamtRahmen.x + 10
      : Math.min(Math.max(2, gesamtRahmen.x + gesamtRahmen.breite / 2 - breite / 2), W - breite - 2)
    return { text, font, breite, x }
  })() : null

  // N-603 (03.10.2026): „Restverbrauch" statt „Haushalt", mit Formel. ⚠ Die Heute-Zeile ist NICHT der Rest:
  // `heute_kwh_pro_komponente.haushalt` ist Eigenverbrauch + Netzbezug (`live_power_service.py::_calc_tages_ev_hv`),
  // also der Gesamtverbrauch — sie heißt deshalb so. Einen Tages-Restverbrauch liefert das Backend nicht.
  const hausTip = [
    'Restverbrauch',
    `Aktuell: ${haushalt ? fmtZahl(haushalt.verbrauch_kw ?? 0, 2) : '—'} kW`,
    'Restverbrauch = Gesamtverbrauch − separat erfasste Verbraucher (z. B. Wallbox, Wärmepumpe);',
    'enthält auch nicht einzeln gemessene Verbraucher',
    `Verbrauchsseite (Bilanz): ${fmtZahl(summeVerbrauch, 2)} kW`,
    `Quellen: ${fmtZahl(summeErzeugung, 2)} kW`,
    ...(tagesWerte?.haushalt != null
      ? [`Heute gesamt (Eigenverbrauch + Netzbezug): ${fmtZahl(tagesWerte.haushalt, 1)} kWh`] : []),
  ].join('\n')

  return (
    <div ref={containerRef} className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-2 shrink-0">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
          Energiefluss
        </h3>
        <div className="flex items-center gap-1.5">
          <select
            value={bgVariant}
            onChange={e => setBgVariant(e.target.value as BgVariant)}
            className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300 border-0 cursor-pointer focus:outline-none focus:ring-1 focus:ring-emerald-500"
            title="Hintergrund wählen"
          >
            {BG_VARIANTS.map(v => (
              <option key={v} value={v}>{BG_LABELS[v]}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={toggleLite}
            className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full transition-colors ${
              lite
                ? 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
                : 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400'
            }`}
            title={lite ? 'Effekte aktivieren (mehr Animationen)' : 'Lite-Modus (weniger Animationen, besser für Mobile)'}
          >
            {lite ? <ZapIcon className="w-3 h-3" /> : <Sparkles className="w-3 h-3" />}
            {lite ? 'Lite' : 'Effekte'}
          </button>
          {kopfAktion}
        </div>
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${svgH}`}
        className="w-full flex-1 min-h-0"
      >
        <EnergieFlussBackground W={W} svgH={svgH} CX={CX} CY={CY} lite={lite} bgVariant={bgVariant} bgPhotoFile={BG_PHOTO_FILE} />

        {/* „Gesamtleistung"-Rahmen (#341, Bau A §A6): fein, in der PV-Farbe,
            HINTER Linien und Kacheln — er fasst die PV-Reihe zusammen, der
            Chip darüber (nach den Kacheln gezeichnet) trägt den Wert. Kein
            Park-Element, keine Fokus-ID. */}
        {gesamt && gesamtRahmen && (
          <rect
            data-gesamtleistung-rahmen
            x={gesamtRahmen.x} y={gesamtRahmen.y}
            width={gesamtRahmen.breite} height={gesamtRahmen.hoehe}
            rx={12}
            fill="none"
            stroke={KATEGORIE_FARBEN.pv}
            strokeOpacity={0.5}
            strokeWidth={1}
            pointerEvents="none"
          />
        )}

        {/* Verbindungslinien */}
        {nodes.map(node => {
          const k = node.komp
          const kw = (k.erzeugung_kw ?? 0) + (k.verbrauch_kw ?? 0)
          const thickness = logThickness(kw, maxKw)
          const color = getNodeColor(k, netzPufferW)
          const isActive = kw > 0
          const isSource = (k.erzeugung_kw ?? 0) > 0
          const duration = flowDuration(kw)
          // Jede Linie endet am Haus: Kinder (Auto hinter der Wallbox) zeichnet
          // das Layout nicht mehr — bei einer Reihe je Zone kreuzt sich nichts.
          const d = flowPath(node.x, node.y, CX, CY)

          return (
            <g key={`line-${k.key}`}>
              {/* Glow-Schatten (weicher farbiger Schein) — nur im Effekt-Modus */}
              {isActive && !lite && (
                <path
                  d={d}
                  fill="none"
                  stroke={color}
                  strokeWidth={thickness + 6}
                  strokeOpacity={0.12}
                  strokeLinecap="round"
                  filter="url(#ef-line-glow)"
                />
              )}
              {/* Basis-Linie (halbtransparent, breit) */}
              <path
                d={d}
                fill="none"
                stroke={isActive ? color : achsen.referenz}
                strokeWidth={thickness}
                strokeOpacity={isActive ? 0.2 : 0.08}
                strokeLinecap="round"
              />
              {/* Saum (Bau B, Regel C): nur „Haus", nur aktive Linien, nur im
                  hellen Bild (`dark:opacity-0`). ⛔ Lesbarkeit, KEIN Effekt —
                  deshalb in BEIDEN Schalterstellungen und nicht im `!lite`-
                  Zweig: gerade in Lite stünde die Kernlinie sonst nackt auf
                  dem hellen Himmel (PV 1,39:1; mit Saum 9,5–10:1). Ohne
                  `flow-line`, die Partikel laufen darüber. */}
              {isActive && bgVariant === 'haus' && (
                <path
                  data-saum
                  d={d}
                  fill="none"
                  stroke={ENERGIEFLUSS_SAUM}
                  strokeWidth={Math.max(thickness * 0.4, 1.5) + 2}
                  strokeOpacity={0.4}
                  strokeLinecap="round"
                  className="dark:opacity-0"
                />
              )}
              {/* Kern-Linie (leuchtend, schmal). Im Lite-Modus zusätzlich
                  CSS-animierter Dashoffset-Fluss (wie LuminaCard / STATS
                  Card) — GPU-beschleunigt, kein SMIL-Ruckler auf Mobile-
                  Safari. Im Effekt-Modus bleibt die Linie solid und die
                  SMIL-Partikel darunter übernehmen den Fluss-Eindruck. */}
              {isActive && (
                <path
                  d={d}
                  fill="none"
                  stroke={color}
                  strokeWidth={Math.max(thickness * 0.4, 1.5)}
                  strokeOpacity={0.85}
                  strokeLinecap="round"
                  className={lite ? (isSource ? 'flow-line' : 'flow-line flow-line--reverse') : undefined}
                  style={lite ? { ['--flow-duration' as string]: `${duration}s` } : undefined}
                />
              )}
              {/* Animierte Partikel (Elektronen) auf dem Pfad — im Lite-Modus aus.
                  SMIL-Animationen (animateMotion + animate) sind auf Mobile-Safari/iPad
                  GPU-intensiv und der Hauptgrund für Ruckler im Lite-Modus. */}
              {isActive && !lite && Array.from({ length: Math.min(3, Math.ceil(kw / 2) + 1) }, (_, pi) => {
                const dur = duration + pi * 0.3
                // Quellen: Partikel fließen Knoten → Haus (vorwärts auf d)
                // Senken: Partikel fließen Haus → Knoten (rückwärts auf d)
                return (
                  <circle key={`el-${k.key}-${pi}`} r={Math.min(thickness * 0.5, 3)} fill="white" fillOpacity="0.9">
                    <animateMotion
                      dur={`${dur}s`}
                      repeatCount="indefinite"
                      begin={`${pi * (duration / 3)}s`}
                      path={d}
                      keyPoints={isSource ? '0;1' : '1;0'}
                      keyTimes="0;1"
                      calcMode="linear"
                    />
                    <animate
                      attributeName="opacity"
                      values="0;0.9;0.9;0"
                      keyTimes="0;0.1;0.9;1"
                      dur={`${dur}s`}
                      repeatCount="indefinite"
                      begin={`${pi * (duration / 3)}s`}
                    />
                  </circle>
                )
              })}
            </g>
          )
        })}

        {/* Haus-Knoten (Zentrum) */}
        <g className="cursor-default" data-title={hausTip}>
          <title>{hausTip}</title>
          {/* Pulsierender Glow-Ring — nur im Effekt-Modus */}
          {!lite && (
            <>
              <circle
                cx={CX} cy={CY} r={HAUS_R + 6}
                fill="none"
                stroke={KATEGORIE_FARBEN.haushalt}
                strokeWidth={3}
                filter="url(#ef-haus-glow)"
                style={{ animation: 'haus-glow 3s ease-in-out infinite' }}
              />
              <circle
                cx={CX} cy={CY} r={HAUS_R + 2}
                fill="none"
                stroke={KATEGORIE_FARBEN.haushalt}
                strokeWidth={1.5}
                strokeOpacity={0.3}
              />
            </>
          )}
          {/* Haupt-Kreis (halbtransparent) */}
          <circle
            cx={CX} cy={CY} r={HAUS_R}
            className="fill-white dark:fill-gray-800"
            fillOpacity={bgVariant === 'sunset' ? 0.92 : 0.65}
            stroke={KATEGORIE_FARBEN.haushalt}
            strokeWidth={2}
            strokeOpacity={0.6}
          />
          <foreignObject x={CX - dims.hausIconSize / 2} y={CY - dims.hausIconSize * 0.75} width={dims.hausIconSize} height={dims.hausIconSize}>
            <IconElement name="home" size={dims.hausIconSize} className="text-emerald-500" />
          </foreignObject>
          {/* Restverbrauch im Kreis (ohne separat erfasste Verbraucher, #314; N-603) */}
          <text
            x={CX} y={CY + dims.hausIconSize * 0.7}
            textAnchor="middle"
            style={{ fontSize: `${dims.kwFontSize}px` }}
            className="font-bold fill-gray-900 dark:fill-white"
          >
            {formatPower(nettoHausverbrauch)}
          </text>
        </g>

        {/* PV-Soll — oberhalb des Hauses. Bis Bau A §A6 stand darüber noch
            „Solarleistung"; die Summe ist in den „Gesamtleistung"-Chip über
            der PV-Reihe gezogen, das Soll rückt auf ihren Platz direkt über
            dem Haus (vorher dort, wenn die Summe fehlte — bei einem PV-Knoten
            oder nachts). */}
        {pvSollKw != null && pvSollKw > 0 && (
          <text
            data-solar-soll
            x={CX} y={CY - HAUS_R - 8}
            textAnchor="middle"
            style={{ fontSize: `${dims.socFontSize - 1}px` }}
            className={bgVariant === 'sunset'
              ? 'fill-purple-800 dark:fill-purple-400'
              : bgVariant === 'alps'
                ? 'fill-indigo-800 dark:fill-indigo-300'
                // „Haus" (Bau B, Regel D): der Text steht nackt auf dem Bild —
                // hell dunkel wie bei Alpen (6,4:1 statt 2,55:1 mit purple-500),
                // dunkel der Bestand.
                : bgVariant === 'haus'
                  ? 'fill-indigo-800 dark:fill-purple-400'
                  : 'fill-purple-500 dark:fill-purple-400'}
          >
            Solar Soll ~{fmtZahl(pvSollKw, 1)} kW
          </text>
        )}

        {/* Komponenten-Knoten — Einzelkacheln und Gruppen (Bau A §A4).
            Seit §A5 ist eine GRUPPENkachel ein Knopf (Klick, Enter, Leertaste)
            und öffnet die „Liste mit Balken" — aber nur, wenn der Aufrufer
            `onGruppeKlick` reicht (kein Knopf ohne Wirkung). Einzelkacheln
            bleiben `cursor-default`, ihr Detailzugang ist der Tooltip. */}
        {nodes.map(node => {
          const k = node.komp
          const mitglieder = node.mitglieder
          const kw = Math.max(k.erzeugung_kw ?? 0, k.verbrauch_kw ?? 0)
          const color = getNodeColor(k, netzPufferW)
          const isActive = kw > 0
          // Füllstand: trägt der gezeichnete Knoten ihn SELBST (Speicher-Gruppe
          // kapazitätsgewichtet, Wallbox = Ladestand des Autos; `null` =
          // ausdrücklich keiner), gilt der; sonst wie bisher aus den Gauges.
          const soc = node.ladestand !== undefined ? node.ladestand : getSoc(k.key, gauges)
          const hasSoc = soc != null

          // Trägt dieser Knoten zwischen kW-Wert und Gerätename eine ZWEITE
          // Zeile? Das sind SoC (Speicher), Betriebsmodus (Wärmepumpe) und seit
          // Bau A die Auto-Zeile der Wallbox — nie zwei davon am selben Gerät,
          // deshalb teilen sie sich den Platz.
          // ⭐ Die Frage steht hier EINMAL, weil ihre Antwort an ZWEI Stellen
          // gebraucht wird: für die Zeile selbst und für die Verschiebung des
          // Namens darunter. Genau diese zweite Stelle hat #398 Stufe 2
          // vergessen (s. Kommentar am Label).
          const zweite: { text: string; fill: string | null } | null = node.kachelAuto
            ? { text: autoZeile(node.kachelAuto, zeichenBudget(NODE_W, dims.socFontSize)), fill: hasSoc ? socColor(soc) : null }
            : hasSoc
              ? { text: `${soc} %`, fill: socColor(soc) }
              : !mitglieder && k.betriebsmodus_label
                ? { text: k.betriebsmodus_label, fill: isActive ? color : achsen.referenz }
                : null
          const zweiteZeile = zweite != null

          // PV-Auslastung: Ist-Leistung / installierte kWp (bei der PV-Gruppe
          // Σ kW / Σ kWp — die Summe ist `null`, sobald einem Mitglied die kWp fehlt)
          const isPv = k.key.startsWith('pv_')
          const auslastungPct = isPv && k.leistung_kwp && k.leistung_kwp > 0 && (k.erzeugung_kw ?? 0) > 0
            ? Math.min(100, ((k.erzeugung_kw ?? 0) / k.leistung_kwp) * 100)
            : null

          // Tooltip — tagesWerte per exaktem Key oder Prefix matchen; die Gruppe
          // bringt ihre Σ der Mitglieds-Keys mit (ihr eigener Key trifft
          // `tagesWerte` nie).
          const tagesKwh = mitglieder
            ? node.heuteKwh ?? null
            : heuteKwhVon(tagesWerte, k.key)
          const tipParts = [mitglieder ? `${k.label} (${mitglieder.length})` : k.label]
          const netto = mitglieder && (node.gegenlaeufig?.length ?? 0) > 0 ? ', netto' : ''
          const aktuell = mitglieder ? 'Summe' : 'Aktuell'
          if ((k.erzeugung_kw ?? 0) > 0) tipParts.push(`${aktuell}: ${fmtZahl(k.erzeugung_kw!, 2)} kW (Erzeugung${netto})`)
          if ((k.verbrauch_kw ?? 0) > 0) tipParts.push(`${aktuell}: ${fmtZahl(k.verbrauch_kw!, 2)} kW (Verbrauch${netto})`)
          if (hasSoc && mitglieder) tipParts.push(`Ladestand: ${soc} % (nach Kapazität gewichtet)`)
          else if (hasSoc && !node.kachelAuto) tipParts.push(`SoC: ${soc} %`)
          // #398 Stufe 2: der Modus im Klartext — im Tooltip UND als zweite
          // Zeile im Knoten (s. dort). Der Tooltip trägt ihn zusätzlich, weil
          // er den ungekürzten Gerätenamen daneben zeigt.
          // ⚠ Hier stand bis 2026-08-27 „Er steht im Tooltip und NICHT als
          // zweite Zeile im Knoten" — der Kommentar beschrieb einen früheren
          // Entwurf und wurde beim Umbau nicht mitgezogen. Dieselbe Klasse wie
          // der 13-Uhr-Kommentar in `prognosen.py` (N-331).
          if (k.betriebsmodus_label) tipParts.push(`Betrieb: ${k.betriebsmodus_label}`)
          if (auslastungPct !== null) tipParts.push(`Auslastung: ${fmtZahl(auslastungPct, 0)} % von ${fmtZahl(k.leistung_kwp, 1)} kWp`)
          // Netz: Bezug + Einspeisung separat anzeigen + Farberklärung
          if (k.key === 'netz') {
            const bezug = tagesWerte?.netz_bezug
            const einsp = tagesWerte?.netz_einspeisung
            if (bezug != null) tipParts.push(`Heute Bezug: ${fmtZahl(bezug, 1)} kWh`)
            if (einsp != null) tipParts.push(`Heute Einspeisung: ${fmtZahl(einsp, 1)} kWh`)
            tipParts.push(`Farbe: grün = Balance (< ${netzPufferW} W), orange = Einspeisung, rot = Bezug`)
          } else if (tagesKwh != null) {
            tipParts.push(`Heute: ${fmtZahl(tagesKwh, 1)} kWh`)
          }
          // Gruppe: eine Zeile je Mitglied (Plan §1.6) — Leistung, beim Speicher
          // der Ladestand, bei der Wärmepumpe die Betriebsart; wer gegen die
          // Netto-Richtung der Gruppe läuft, ist markiert (Plan §1.4).
          if (mitglieder) {
            mitglieder.forEach(m => {
              const mKw = Math.max(m.erzeugung_kw ?? 0, m.verbrauch_kw ?? 0)
              const mSoc = m.key.startsWith('batterie_') ? getSoc(m.key, gauges) : null
              const zusatz = [
                mSoc != null ? `${mSoc} %` : null,
                m.betriebsmodus_label ?? null,
                node.gegenlaeufig?.includes(m) ? ((m.erzeugung_kw ?? 0) > 0 ? 'gegenläufig: gibt ab' : 'gegenläufig: nimmt auf') : null,
              ].filter(Boolean).join(', ')
              tipParts.push(`• ${m.label}: ${mKw > 0 ? `${fmtZahl(mKw, 2)} kW` : '0 kW'}${zusatz ? ` (${zusatz})` : ''}`)
            })
          }
          // Autos an der Wallbox (Plan §1.4a): eindeutig — die eigenen, mit
          // Ladestand und gemessener Richtung (V2H „entlädt"); geschätzt (≥ 2
          // Wallboxen) — ALLE Autos und der Satz, dass eedc die Zuordnung nicht kennt.
          if (node.fahrzeugeZuordnung === 'eindeutig') {
            (node.fahrzeuge ?? []).forEach(a => tipParts.push(`Auto ${autoTip(a)}`))
          } else if (node.fahrzeugeZuordnung === 'geschaetzt' && alleAutos.length > 0) {
            tipParts.push('Autos:')
            alleAutos.forEach(a => tipParts.push(`• ${autoTip(a)}`))
            tipParts.push(SATZ_ZUORDNUNG_UNBEKANNT)
          }
          const tip = tipParts.join('\n')

          // Label kürzen — die Gruppe behält ihre Anzahl „(n)" immer ganz
          const maxC = dims.labelMaxChars
          const shortLabel = mitglieder
            ? kuerzeMitSuffix(k.label, ` (${mitglieder.length})`, zeichenBudget(NODE_W, dims.labelFontSize))
            : k.label.length > maxC ? k.label.slice(0, maxC - 2) + '…' : k.label

          const nx = node.x - NODE_W / 2
          const ny = node.y - NODE_H / 2

          // Gruppe = Knopf (§A5). Der Tap hat per `touchstart` schon den
          // Tooltip der Kachel gezeigt — er stünde sonst bis zu 6 s über dem
          // Overlay (`Z_TOOLTIP` > z-50), deshalb vor dem Öffnen wegräumen.
          const oeffnen = mitglieder && onGruppeKlick
            ? () => { verbergeTouchTooltip(); onGruppeKlick(k.key) }
            : null
          const knopf = oeffnen ? {
            role: 'button',
            tabIndex: 0,
            'aria-label': `${k.label} (${mitglieder!.length}): Liste öffnen`,
            'data-gruppe': k.key,
            onClick: oeffnen,
            onKeyDown: (e: React.KeyboardEvent<SVGGElement>) => {
              if (e.key !== 'Enter' && e.key !== ' ') return
              e.preventDefault()
              oeffnen()
            },
          } : {}

          return (
            <g
              key={`node-${k.key}`}
              className={oeffnen ? 'group cursor-pointer outline-none' : 'cursor-default'}
              data-title={tip}
              {...knopf}
            >
              <title>{tip}</title>

              {/* Tastatur-Fokus der Gruppenkachel: ein Rahmen, nur bei :focus-visible. */}
              {oeffnen && (
                <rect
                  data-fokusrahmen
                  x={nx - 3} y={ny - STAPEL_VERSATZ - 3}
                  width={NODE_W + STAPEL_VERSATZ + 6} height={NODE_H + STAPEL_VERSATZ + 6}
                  rx={NODE_R + 2}
                  fill="none"
                  strokeWidth={1.5}
                  className="stroke-emerald-500 opacity-0 group-focus-visible:opacity-100"
                />
              )}

              {/* Stapel-Optik der Gruppe (detLAN #138, Muster `stack: 7`): zwei
                  versetzte Rahmen hinter der Kachel — „hier liegen mehrere". */}
              {mitglieder && [STAPEL_VERSATZ, STAPEL_VERSATZ / 2].map((v, i) => (
                <rect
                  key={`stapel-${v}`}
                  data-stapel={i + 1}
                  x={nx + v} y={ny - v}
                  width={NODE_W} height={NODE_H}
                  rx={NODE_R}
                  className="fill-white dark:fill-gray-800"
                  fillOpacity={bgVariant === 'sunset' ? 0.5 : 0.33}
                  stroke={isActive ? color : achsen.referenz}
                  strokeWidth={isActive ? 0.8 : 0.5}
                  strokeOpacity={i === 0 ? 0.35 : 0.5}
                />
              ))}

              {/* Knoten-Hintergrund (halbtransparent, Gitter scheint durch).
                  Filter-Attribut im Lite-Modus weglassen, damit Safari pro Knoten
                  keinen separaten Compositing-Layer für den (No-Op-)Filter erstellt. */}
              <rect
                x={nx} y={ny}
                width={NODE_W} height={NODE_H}
                rx={NODE_R}
                className="fill-white dark:fill-gray-800"
                fillOpacity={bgVariant === 'sunset' ? 0.92 : 0.6}
                stroke={isActive ? color : achsen.referenz}
                strokeWidth={isActive ? 1 : 0.5}
                strokeOpacity={isActive ? 0.7 : 0.3}
                filter={lite ? undefined : "url(#ef-card-shadow)"}
              />

              {/* SoC-Pegel (Füllung von unten, kräftig sichtbar) */}
              {hasSoc && (
                <rect
                  x={nx + 1.5} y={ny + 1.5 + (NODE_H - 3) * (1 - soc / 100)}
                  width={NODE_W - 3}
                  height={(NODE_H - 3) * (soc / 100)}
                  rx={NODE_R - 1}
                  fill={socColor(soc)}
                  fillOpacity={0.3}
                />
              )}

              {/* PV-Auslastungs-Pegel (Füllung von unten, gelb/orange) */}
              {auslastungPct !== null && (
                <rect
                  x={nx + 1.5} y={ny + 1.5 + (NODE_H - 3) * (1 - auslastungPct / 100)}
                  width={NODE_W - 3}
                  height={(NODE_H - 3) * (auslastungPct / 100)}
                  rx={NODE_R - 1}
                  fill={auslastungPct >= 80 ? SOLAR_INTENSITAET[2] : auslastungPct >= 40 ? SOLAR_INTENSITAET[1] : SOLAR_INTENSITAET[0]}
                  fillOpacity={0.25}
                />
              )}

              {/* Icon-Glow (farbiger Schein hinter dem Icon) — nur im Effekt-Modus */}
              {isActive && !lite && (
                <circle
                  cx={node.x} cy={node.y - NODE_H / 2 + 6 + dims.iconSize / 2}
                  r={dims.iconSize * 0.6}
                  fill={color}
                  fillOpacity={0.15}
                  filter="url(#ef-icon-glow)"
                />
              )}
              {/* Icon */}
              <foreignObject x={node.x - dims.iconSize / 2} y={node.y - NODE_H / 2 + 6} width={dims.iconSize} height={dims.iconSize}>
                <IconElement name={k.icon} size={dims.iconSize} color={isActive ? color : achsen.referenz} />
              </foreignObject>

              {/* kW-Wert */}
              <text
                x={node.x} y={node.y + 1}
                textAnchor="middle"
                style={{ fontSize: `${dims.kwFontSize}px` }}
                className="font-bold fill-gray-900 dark:fill-white"
              >
                {formatPower(kw)}
              </text>

              {/* Zweite Zeile: SoC · Betriebsmodus im Klartext (#398 Stufe 2) ·
                  Auto der Wallbox (Bau A, Plan §1.4a — „ID.4 52 %", bei V2H
                  „· entlädt"; lädt keins eindeutig: „64 · 81 %" ohne Füllstand).
                  ⭐ Bewusst in DERSELBEN Zeile statt in einer vierten: ein
                  Speicher hat einen SoC und keinen Betriebsmodus, eine
                  Wärmepumpe umgekehrt, eine Wallbox nur ihr Auto — der Platz ist
                  also frei, und der Knoten wächst nicht. Ein Tooltip allein wäre
                  auf dem Handy unerreichbar gewesen; die Frage des Melders war
                  „sieht man, was das Gerät gerade tut?", und Hovern ist dort
                  keine Antwort. */}
              {zweite && (
                <text
                  x={node.x} y={node.y + dims.kwFontSize + 2}
                  textAnchor="middle"
                  style={{ fontSize: `${dims.socFontSize}px` }}
                  className={zweite.fill ? 'font-semibold' : 'font-semibold fill-gray-500 dark:fill-gray-400'}
                  fill={zweite.fill ?? undefined}
                >
                  {zweite.text}
                </text>
              )}

              {/* Label
                  ⛔ **Die Bedingung ist `zweiteZeile`, nicht `hasSoc`** — und
                  genau das war der Fehler, den MartyBr am Tag der Auslieferung
                  von v4.0.30 fotografiert hat (T89667 #230): „Unbestimmt" lag
                  quer über „Vitocal 33…". Der Modus-Text hat sich die
                  **Position** des SoC geliehen (`kwFontSize + 2`), die
                  zugehörige **Verschiebung des Namens** stand aber in einem
                  Ternär, das nur den SoC kannte. Vier Pixel Abstand bei neun
                  Pixel Schriftgröße.
                  ⭐ Deshalb steht die Frage jetzt EINMAL oben (`zweiteZeile`)
                  statt zweimal hier: Wer eine dritte Zeilenart ergänzt, ändert
                  eine Stelle — nicht zwei, von denen er die zweite übersieht. */}
              <text
                x={node.x} y={node.y + (zweiteZeile ? NODE_H / 2 - 4 : dims.kwFontSize + 6)}
                textAnchor="middle"
                style={{ fontSize: `${dims.labelFontSize}px` }}
                className="fill-gray-500 dark:fill-gray-400"
              >
                {shortLabel}
              </text>
            </g>
          )
        })}

        {/* Chip „Gesamtleistung <Wert>" auf der Oberkante des Rahmens — NACH
            den Kacheln, damit ihn die Stapel-Optik einer Gruppe nicht verdeckt.
            Hervorhebung wie die frühere „Solarleistung"-Zeile (Issue #314,
            kingcap1: fett, leicht größer, kräftige PV-Farbe); der Tooltip
            grenzt den Wert ab (bei BHKW-Anlagen zählt der Erzeuger nicht mit). */}
        {gesamt && gesamtRahmen && (
          <g data-gesamtleistung className="cursor-default" data-title={TIP_GESAMTLEISTUNG}>
            <title>{TIP_GESAMTLEISTUNG}</title>
            <rect
              x={gesamt.x} y={gesamtRahmen.y - RAHMEN_CHIP_HOEHE / 2}
              width={gesamt.breite} height={RAHMEN_CHIP_HOEHE}
              rx={RAHMEN_CHIP_HOEHE / 2}
              className="fill-white dark:fill-gray-800"
              fillOpacity={0.92}
              stroke={KATEGORIE_FARBEN.pv}
              strokeOpacity={0.5}
              strokeWidth={1}
            />
            <text
              x={gesamt.x + gesamt.breite / 2} y={gesamtRahmen.y + gesamt.font * 0.35}
              textAnchor="middle"
              style={{ fontSize: `${gesamt.font}px`, fontWeight: 700 }}
              className={bgVariant === 'sunset'
                ? 'fill-amber-900 dark:fill-yellow-300'
                : bgVariant === 'alps'
                  ? 'fill-blue-900 dark:fill-blue-200'
                  : 'fill-amber-600 dark:fill-yellow-300'}
            >
              {gesamt.text}
            </text>
          </g>
        )}
      </svg>
    </div>
  )
}
