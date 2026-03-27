/**
 * EnergieFluss — Animiertes Energiefluss-Diagramm (ersetzt EnergieBilanz).
 *
 * Zeigt alle Komponenten als Knoten um ein zentrales Haus-Symbol.
 * Animierte Linien zeigen Flussrichtung und -stärke.
 * Informationsparität mit EnergieBilanz: kW-Werte, Icons, Farben,
 * Tages-kWh Tooltips, Σ Erzeugung/Verbrauch.
 */

import { useState, useEffect, useRef } from 'react'
import { Sun, Zap, Battery, Car, Flame, Wrench, Home, Plug, Heater, Droplets, Sparkles, Zap as ZapIcon } from 'lucide-react'
import type { LiveKomponente, LiveGauge } from '../../api/liveDashboard'

// ─── Lite-Modus (reduzierte Animationen für Mobile/WebView) ─────────

const LITE_STORAGE_KEY = 'eedc-energiefluss-lite'

/** Auto-Detect: HA Companion App oder schmales Viewport → lite */
function detectLiteDefault(): boolean {
  if (typeof window === 'undefined') return false
  const ua = navigator.userAgent
  // HA Companion App (Android/iOS)
  if (/HomeAssistant/i.test(ua)) return true
  // Allgemein Mobile
  if (/Android|iPhone|iPad|iPod/i.test(ua) && window.innerWidth < 768) return true
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
type BgVariant = 'default' | 'sunset'

function useBgVariant(): [BgVariant, () => void] {
  const [bgVariant, setBgVariant] = useState<BgVariant>(() => {
    const stored = localStorage.getItem(BG_VARIANT_KEY)
    return stored === 'sunset' ? 'sunset' : 'default'
  })

  useEffect(() => {
    localStorage.setItem(BG_VARIANT_KEY, bgVariant)
  }, [bgVariant])

  const toggle = () => setBgVariant(prev => prev === 'default' ? 'sunset' : 'default')
  return [bgVariant, toggle]
}

// ─── Shared Utilities (aus EnergieBilanz) ───────────────────────────

const ICON_MAP: Record<string, React.ElementType> = {
  sun: Sun, zap: Zap, battery: Battery, car: Car, plug: Plug,
  flame: Flame, wrench: Wrench, home: Home, heater: Heater, droplets: Droplets,
}

const COLOR_MAP: Record<string, string> = {
  pv: '#eab308',
  netz: '#ef4444',
  batterie: '#3b82f6',
  eauto: '#a855f7',
  wallbox: '#a855f7',
  waermepumpe: '#f97316',
  sonstige: '#6b7280',
  haushalt: '#10b981',
}

function getColor(key: string): string {
  if (COLOR_MAP[key]) return COLOR_MAP[key]
  // Erst versuche: key ohne trailing _zahl (z.B. "waermepumpe_5" → "waermepumpe")
  const prefix = key.replace(/_\d+$/, '')
  if (COLOR_MAP[prefix]) return COLOR_MAP[prefix]
  // Dann: Basis-Kategorie aus erstem Segment (z.B. "waermepumpe_5_heizen" → "waermepumpe")
  const basis = key.split('_')[0]
  return COLOR_MAP[basis] || '#6b7280'
}

/** Netz-Farbe dynamisch nach Flussrichtung: grün=Balance, orange=Einspeisung, rot=Bezug
 *  Backend-Semantik: erzeugung_kw = Netzbezug (Netz liefert ans Haus),
 *                    verbrauch_kw = Einspeisung (Netz nimmt vom Haus) */
function getNetzColor(komp: LiveKomponente, pufferW: number): string {
  const einspeisungKw = komp.verbrauch_kw ?? 0
  const bezugKw = komp.erzeugung_kw ?? 0
  const nettoW = (bezugKw - einspeisungKw) * 1000
  if (Math.abs(nettoW) <= pufferW) return '#22c55e' // grün — Balance
  if (nettoW < 0) return '#f59e0b'                    // orange — Einspeisung
  return '#ef4444'                                     // rot — Netzbezug
}

/** Farbe für eine Komponente — Netz dynamisch, Batterie nach Lade-/Entladezustand, Rest statisch */
function getNodeColor(komp: LiveKomponente, netzPufferW = 100): string {
  if (komp.key === 'netz') return getNetzColor(komp, netzPufferW)
  // Batterie/Speicher: Cyan bei Entladung, Blau bei Ladung
  if (komp.key.startsWith('batterie_')) {
    const entlaedt = (komp.erzeugung_kw ?? 0) > (komp.verbrauch_kw ?? 0)
    return entlaedt ? '#06b6d4' : '#3b82f6'  // cyan = Entladung, blau = Ladung
  }
  return getColor(komp.key)
}

/** Leistung formatieren: < 1 kW → Watt, ≥ 1 kW → kW */
function formatPower(kw: number): string {
  if (kw <= 0) return '0 W'
  if (kw < 1) return `${Math.round(kw * 1000)} W`
  return `${kw.toFixed(2)} kW`
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
}

interface NodePosition {
  x: number
  y: number
  komp: LiveKomponente
}

// ─── Layout ─────────────────────────────────────────────────────────

const W_DEFAULT = 600

/** Verteile n Items gleichmäßig auf einer Linie */
function distribute(n: number, minX: number, maxX: number): number[] {
  if (n === 0) return []
  if (n === 1) return [(minX + maxX) / 2]
  const step = (maxX - minX) / (n - 1)
  return Array.from({ length: n }, (_, i) => minX + i * step)
}

/** Dynamische Dimensionen abhängig von der max. Anzahl Komponenten pro Zeile */
interface LayoutDims {
  nodeW: number
  nodeH: number
  nodeR: number
  hausR: number
  cy: number
  verbraucherY: number
  kwFontSize: number
  labelFontSize: number
  socFontSize: number
  labelMaxChars: number
  iconSize: number
  hausIconSize: number
}

function computeDims(maxPerRow: number): LayoutDims {
  // Ab 5+ Items pro Zeile: kompakte Darstellung
  if (maxPerRow >= 5) {
    return {
      nodeW: 80, nodeH: 48, nodeR: 10, hausR: 34,
      cy: 170, verbraucherY: 305,
      kwFontSize: 10, labelFontSize: 8.5, socFontSize: 9,
      labelMaxChars: 11, iconSize: 16, hausIconSize: 24,
    }
  }
  // 4 Items: leicht reduziert
  if (maxPerRow >= 4) {
    return {
      nodeW: 88, nodeH: 52, nodeR: 10, hausR: 36,
      cy: 175, verbraucherY: 310,
      kwFontSize: 10.5, labelFontSize: 8.5, socFontSize: 9.5,
      labelMaxChars: 12, iconSize: 17, hausIconSize: 24,
    }
  }
  // ≤3 Items: Standard-Größe (proportional zur Sidebar)
  return {
    nodeW: 100, nodeH: 58, nodeR: 12, hausR: 38,
    cy: 180, verbraucherY: 320,
    kwFontSize: 11, labelFontSize: 9, socFontSize: 10,
    labelMaxChars: 14, iconSize: 17, hausIconSize: 26,
  }
}

interface LayoutResult {
  nodes: NodePosition[]
  dims: LayoutDims
}

function layoutNodes(komponenten: LiveKomponente[], W: number = W_DEFAULT): LayoutResult {
  const erzeuger = komponenten.filter(k => k.key.startsWith('pv_'))
  const netz = komponenten.filter(k => k.key === 'netz')
  const speicher = komponenten.filter(k => k.key.startsWith('batterie_'))
  // Kinder (E-Autos mit parent_key) separat behandeln
  const kinder = komponenten.filter(k => k.parent_key)
  const kinderKeys = new Set(kinder.map(k => k.key))
  const verbraucher = komponenten.filter(k =>
    !k.key.startsWith('pv_') && k.key !== 'netz' &&
    !k.key.startsWith('batterie_') && k.key !== 'haushalt' &&
    !kinderKeys.has(k.key)
  )

  // Kinder direkt nach ihrem Parent einreihen (z.B. E-Auto neben Wallbox)
  const kinderByParent = new Map<string, LiveKomponente[]>()
  kinder.forEach(k => {
    const list = kinderByParent.get(k.parent_key!) || []
    list.push(k)
    kinderByParent.set(k.parent_key!, list)
  })
  const alleUnten: LiveKomponente[] = []
  verbraucher.forEach(v => {
    alleUnten.push(v)
    const kids = kinderByParent.get(v.key)
    if (kids) kids.forEach(k => alleUnten.push(k))
  })
  // Kinder ohne passenden Parent am Ende anhängen
  kinder.forEach(k => {
    if (!alleUnten.includes(k)) alleUnten.push(k)
  })

  const maxPerRow = Math.max(erzeuger.length, alleUnten.length, 1)
  const dims = computeDims(maxPerRow)
  const { nodeW, nodeH, cy: CY } = dims

  const nodes: NodePosition[] = []

  // Dynamische Ränder: nutzt die volle Breite besser aus
  const margin = nodeW / 2 + 15

  // Oben: Erzeuger (volle Breite abzüglich Rand)
  const ezXs = distribute(erzeuger.length, margin, W - margin)
  erzeuger.forEach((k, i) => nodes.push({ x: ezXs[i], y: 50, komp: k }))

  // Links: Netz
  netz.forEach(k => nodes.push({ x: margin, y: CY, komp: k }))

  // Rechts: Speicher — vertikal gestapelt bei mehreren
  const spX = W - margin
  speicher.forEach((k, i) => {
    const offsetY = speicher.length > 1
      ? (i - (speicher.length - 1) / 2) * (nodeH + 10)
      : 0
    nodes.push({ x: spX, y: CY + offsetY, komp: k })
  })

  // Unten: Verbraucher + Kinder zusammen in einer Reihe
  const vrXs = distribute(alleUnten.length, margin, W - margin)
  alleUnten.forEach((k, i) => nodes.push({ x: vrXs[i], y: dims.verbraucherY, komp: k }))

  return { nodes, dims }
}

// ─── SVG Helpers ────────────────────────────────────────────────────

/** Quadratic Bezier Pfad von Knoten zu Zielpunkt */
function flowPath(nx: number, ny: number, tx: number, ty: number): string {
  const mx = (nx + tx) / 2
  const my = (ny + ty) / 2
  const dx = tx - nx
  const dy = ty - ny
  const len = Math.sqrt(dx * dx + dy * dy) || 1
  const perpX = -dy / len * 25
  const perpY = dx / len * 25
  return `M ${nx} ${ny} Q ${mx + perpX} ${my + perpY} ${tx} ${ty}`
}

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

/** SoC aus gauges extrahieren für einen Komponenten-Key (z.B. "batterie_3" → soc_3) */
function getSoc(key: string, gauges?: LiveGauge[]): number | null {
  if (!gauges) return null
  // Key-Format: "batterie_3" oder "eauto_4" → Investitions-ID ist der Teil nach dem letzten "_"
  const match = key.match(/_(\d+)$/)
  if (!match) return null
  const invId = match[1]
  const gauge = gauges.find(g => g.key === `soc_${invId}`)
  return gauge ? gauge.wert : null
}

/** SoC Farbe: rot < 20%, gelb 20-50%, grün > 50% */
function socColor(pct: number): string {
  if (pct < 20) return '#ef4444'
  if (pct < 50) return '#eab308'
  return '#22c55e'
}

// ─── Component ──────────────────────────────────────────────────────

export default function EnergieFluss({
  komponenten, summeErzeugung, summeVerbrauch, summePv, tagesWerte, gauges, pvSollKw,
  netzPufferW = 100,
}: EnergieFlussProps) {
  const [lite, toggleLite] = useLiteMode()
  const [bgVariant, toggleBgVariant] = useBgVariant()
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerW, setContainerW] = useState(W_DEFAULT)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect.width ?? W_DEFAULT
      setContainerW(w)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  if (komponenten.length === 0) return null

  // SVG-Breite: Container < 375 → 360, 375-499 → 450, ≥500 → 600
  const W = containerW < 375 ? 360 : containerW < 500 ? 450 : 600
  const CX = W / 2

  const { nodes, dims } = layoutNodes(komponenten, W)
  const { nodeW: NODE_W, nodeH: NODE_H, nodeR: NODE_R, hausR: HAUS_R } = dims
  const CY = dims.cy
  const nodeMap = new Map(nodes.map(n => [n.komp.key, n]))
  const haushalt = komponenten.find(k => k.key === 'haushalt')

  // Netto-Hausverbrauch: Summe aller Verbraucher (inkl. Haushalt-Rest, WP, Wallbox etc.)
  // ohne Batterie, Netz, PV-Erzeuger und Kind-Komponenten (z.B. E-Auto wenn Wallbox gleichen Sensor hat)
  const nettoHausverbrauch = komponenten
    .filter(k => !k.key.startsWith('pv_') && k.key !== 'netz' && !k.key.startsWith('batterie_') && !k.parent_key)
    .reduce((sum, k) => sum + (k.verbrauch_kw ?? 0), 0)

  // Dynamische Höhe: Basis 380, erweitert wenn Knoten tiefer liegen
  const maxY = Math.max(...nodes.map(n => n.y), dims.verbraucherY)
  const svgH = Math.max(380, maxY + NODE_H / 2 + 10)

  // Max kW für Dicken-Normierung
  const allKw = komponenten.flatMap(k => [k.erzeugung_kw ?? 0, k.verbrauch_kw ?? 0])
  const maxKw = Math.max(...allKw, 0.1)

  return (
    <div ref={containerRef} className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-2 shrink-0">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
          Energiefluss
        </h3>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={toggleBgVariant}
            className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full transition-colors ${
              bgVariant === 'sunset'
                ? 'bg-orange-50 text-orange-600 dark:bg-orange-900/30 dark:text-orange-400'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            title={bgVariant === 'sunset' ? 'Technischen Hintergrund aktivieren' : 'Sonnenuntergang-Hintergrund aktivieren'}
          >
            <Sun className="w-3 h-3" />
            {bgVariant === 'sunset' ? 'Sunset' : 'Tech'}
          </button>
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
        </div>
      </div>

      <svg
        viewBox={`0 0 ${W} ${svgH}`}
        className="w-full flex-1 min-h-0"
      >
        <defs>
          {!lite && <style>{`
            @keyframes pulse-ring {
              0%, 100% { opacity: 0.15; }
              50% { opacity: 0.04; }
            }
            @keyframes bg-stream {
              from { stroke-dashoffset: 0; }
              to { stroke-dashoffset: -60; }
            }
            @keyframes haus-glow {
              0%, 100% { opacity: 0.35; }
              50% { opacity: 0.55; }
            }
          `}</style>}

          {/* Maske: Perspektivgitter nahe Zentrum ausblenden */}
          <radialGradient id="ef-grid-fade" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="white" stopOpacity="0" />
            <stop offset="25%" stopColor="white" stopOpacity="0.3" />
            <stop offset="60%" stopColor="white" stopOpacity="0.8" />
            <stop offset="100%" stopColor="white" stopOpacity="1" />
          </radialGradient>
          <mask id="ef-grid-mask">
            <rect width={W} height={svgH} fill="url(#ef-grid-fade)" />
          </mask>

          {/* Radiales Glow vom Zentrum — Light (verstärkt) */}
          <radialGradient id="ef-glow-light" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.55} gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.25" />
            <stop offset="20%" stopColor="#06b6d4" stopOpacity="0.14" />
            <stop offset="50%" stopColor="#3b82f6" stopOpacity="0.07" />
            <stop offset="100%" stopColor="#f8fafc" stopOpacity="0" />
          </radialGradient>
          {/* Radiales Glow vom Zentrum — Dark */}
          <radialGradient id="ef-glow-dark" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.55} gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.15" />
            <stop offset="20%" stopColor="#06b6d4" stopOpacity="0.08" />
            <stop offset="50%" stopColor="#3b82f6" stopOpacity="0.04" />
            <stop offset="100%" stopColor="#111827" stopOpacity="0" />
          </radialGradient>

          {/* Inner-Glow (3D-Spot unter dem Haus) — Light (verstärkt) */}
          <radialGradient id="ef-spot-light" cx={CX} cy={CY} r="80" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
          </radialGradient>
          {/* Inner-Glow — Dark */}
          <radialGradient id="ef-spot-dark" cx={CX} cy={CY} r="80" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#34d399" stopOpacity="0.14" />
            <stop offset="100%" stopColor="#34d399" stopOpacity="0" />
          </radialGradient>

          {/* Tiefe-Vignette — Light (verstärkt) */}
          <radialGradient id="ef-vignette-light" cx="50%" cy="50%" r="52%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0" />
            <stop offset="60%" stopColor="#e2e8f0" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#94a3b8" stopOpacity="0.45" />
          </radialGradient>
          {/* Tiefe-Vignette — Dark */}
          <radialGradient id="ef-vignette-dark" cx="50%" cy="50%" r="52%">
            <stop offset="0%" stopColor="#1f2937" stopOpacity="0" />
            <stop offset="70%" stopColor="#0f172a" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#020617" stopOpacity="0.6" />
          </radialGradient>

          {/* Filter: im Lite-Modus ohne Blur (Performance) */}
          {lite ? (
            <>
              <filter id="ef-inner-shadow"><feOffset dx="0" dy="0" /></filter>
              <filter id="ef-ring-glow"><feOffset dx="0" dy="0" /></filter>
              <filter id="ef-line-glow"><feOffset dx="0" dy="0" /></filter>
              <filter id="ef-icon-glow"><feOffset dx="0" dy="0" /></filter>
              <filter id="ef-card-shadow"><feOffset dx="0" dy="0" /></filter>
              <filter id="ef-haus-glow"><feOffset dx="0" dy="0" /></filter>
            </>
          ) : (
            <>
              {/* Innerer Schatten (3D-Einbuchtung) */}
              <filter id="ef-inner-shadow">
                <feGaussianBlur in="SourceAlpha" stdDeviation="8" result="blur" />
                <feOffset dx="0" dy="3" result="offsetBlur" />
                <feComposite in="SourceGraphic" in2="offsetBlur" operator="over" />
              </filter>

              {/* Soft-Glow für Ringe */}
              <filter id="ef-ring-glow">
                <feGaussianBlur stdDeviation="3" />
              </filter>

              {/* Glow-Filter für Flusslinien (weicher Schein) */}
              <filter id="ef-line-glow" x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>

              {/* Glow-Filter für Icons */}
              <filter id="ef-icon-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur in="SourceGraphic" stdDeviation="3" />
              </filter>

              {/* Schatten für Knoten-Karten */}
              <filter id="ef-card-shadow" x="-10%" y="-10%" width="130%" height="140%">
                <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#000000" floodOpacity="0.15" />
              </filter>

              {/* Glow für Haus-Zentrum */}
              <filter id="ef-haus-glow" x="-60%" y="-60%" width="220%" height="220%">
                <feGaussianBlur in="SourceGraphic" stdDeviation="8" />
              </filter>
            </>
          )}

          {/* ─── Sunset-Variante: Gradients ─── */}
          {bgVariant === 'sunset' && <>
            {!lite && <style>{`
              @keyframes pulse-ring-sunset {
                0%, 100% { opacity: 0.20; }
                50% { opacity: 0.06; }
              }
              @keyframes sunset-stream {
                from { stroke-dashoffset: 0; }
                to { stroke-dashoffset: -60; }
              }
              @keyframes shimmer {
                0%, 100% { opacity: 0.12; }
                50% { opacity: 0.30; }
              }
            `}</style>}

            {/* ── Dark Mode: Himmel dunkel-lila → warmes Orange am Horizont ── */}
            <linearGradient id="ef-sky-sunset-dark" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#0f0520" />
              <stop offset="30%"  stopColor="#2d1b4e" />
              <stop offset="70%"  stopColor="#7b2d00" />
              <stop offset="100%" stopColor="#c84b11" />
            </linearGradient>
            {/* ── Dark Mode: Meer dunkles Kupfer → tiefes Marineblau ── */}
            <linearGradient id="ef-sea-sunset-dark" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#5c2a00" />
              <stop offset="40%"  stopColor="#0a1a3a" />
              <stop offset="100%" stopColor="#030d1e" />
            </linearGradient>

            {/* ── Light Mode: Himmel hellblau → Pfirsich → warmes Orange ── */}
            <linearGradient id="ef-sky-sunset-light" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#c8dff5" />
              <stop offset="35%"  stopColor="#f7d8b0" />
              <stop offset="75%"  stopColor="#f5a040" />
              <stop offset="100%" stopColor="#e8731a" />
            </linearGradient>
            {/* ── Light Mode: Meer goldene Spiegelung → Türkis → tieferes Blaugrün ── */}
            <linearGradient id="ef-sea-sunset-light" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#e8b86a" />
              <stop offset="30%"  stopColor="#5bbdc8" />
              <stop offset="100%" stopColor="#2f8a9a" />
            </linearGradient>

            {/* ── Sonnen-Glow Dark ── */}
            <radialGradient id="ef-sun-glow-dark" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.35} gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#ffd700" stopOpacity="0.55" />
              <stop offset="15%"  stopColor="#ff8c00" stopOpacity="0.30" />
              <stop offset="40%"  stopColor="#c84b11" stopOpacity="0.12" />
              <stop offset="100%" stopColor="#000000" stopOpacity="0" />
            </radialGradient>
            {/* ── Sonnen-Glow Light ── */}
            <radialGradient id="ef-sun-glow-light" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.35} gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#ffd700" stopOpacity="0.65" />
              <stop offset="15%"  stopColor="#ff8c00" stopOpacity="0.35" />
              <stop offset="45%"  stopColor="#f5a040" stopOpacity="0.15" />
              <stop offset="100%" stopColor="#ffffff"  stopOpacity="0" />
            </radialGradient>

            {/* ── Atmosphärisches Leuchten Dark ── */}
            <radialGradient id="ef-sun-atmo-dark" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.65} gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#ff6b00" stopOpacity="0.18" />
              <stop offset="35%"  stopColor="#ff4500" stopOpacity="0.08" />
              <stop offset="100%" stopColor="#000000" stopOpacity="0" />
            </radialGradient>
            {/* ── Atmosphärisches Leuchten Light ── */}
            <radialGradient id="ef-sun-atmo-light" cx={CX} cy={CY} r={Math.max(W, svgH) * 0.65} gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#ff8c00" stopOpacity="0.22" />
              <stop offset="35%"  stopColor="#ffa040" stopOpacity="0.10" />
              <stop offset="100%" stopColor="#ffffff"  stopOpacity="0" />
            </radialGradient>

            {/* ── Innerer Sonnen-Spot Dark ── */}
            <radialGradient id="ef-sun-spot-dark" cx={CX} cy={CY} r="70" gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#ffd700" stopOpacity="0.45" />
              <stop offset="60%"  stopColor="#ffa500" stopOpacity="0.15" />
              <stop offset="100%" stopColor="#ffa500" stopOpacity="0" />
            </radialGradient>
            {/* ── Innerer Sonnen-Spot Light ── */}
            <radialGradient id="ef-sun-spot-light" cx={CX} cy={CY} r="70" gradientUnits="userSpaceOnUse">
              <stop offset="0%"   stopColor="#ffd700" stopOpacity="0.55" />
              <stop offset="60%"  stopColor="#ffb020" stopOpacity="0.20" />
              <stop offset="100%" stopColor="#ffb020" stopOpacity="0" />
            </radialGradient>

            {/* ── Vignette Dark (Ränder lila-dunkel) ── */}
            <radialGradient id="ef-vignette-sunset-dark" cx="50%" cy="50%" r="52%">
              <stop offset="0%"   stopColor="#000000" stopOpacity="0" />
              <stop offset="65%"  stopColor="#1a0533"  stopOpacity="0.25" />
              <stop offset="100%" stopColor="#0a0015"  stopOpacity="0.55" />
            </radialGradient>
            {/* ── Vignette Light (Ränder warm-beige) ── */}
            <radialGradient id="ef-vignette-sunset-light" cx="50%" cy="50%" r="52%">
              <stop offset="0%"   stopColor="#ffffff"  stopOpacity="0" />
              <stop offset="60%"  stopColor="#c87820"  stopOpacity="0.10" />
              <stop offset="100%" stopColor="#8b4010"  stopOpacity="0.28" />
            </radialGradient>

            {/* Grid-Fade-Maske für Sunset-Perspektivgitter */}
            <radialGradient id="ef-grid-fade-s" cx="50%" cy="50%" r="50%">
              <stop offset="0%"   stopColor="white" stopOpacity="0" />
              <stop offset="25%"  stopColor="white" stopOpacity="0.3" />
              <stop offset="60%"  stopColor="white" stopOpacity="0.8" />
              <stop offset="100%" stopColor="white" stopOpacity="1" />
            </radialGradient>
            <mask id="ef-grid-mask-s">
              <rect width={W} height={svgH} fill="url(#ef-grid-fade-s)" />
            </mask>
            {/* ClipPaths: Himmel / Meer trennen */}
            <clipPath id="ef-sky-clip">
              <rect x={-W} y={-svgH} width={W * 3} height={CY + svgH} />
            </clipPath>
            <clipPath id="ef-sea-clip">
              <rect x={-W} y={CY} width={W * 3} height={svgH * 2} />
            </clipPath>
          </>}
        </defs>

        {/* ═══ Hintergrund-Layer ═══ */}
        <g className="pointer-events-none">
          {/* Basis-Hintergrund (Light etwas dunkler für Kontrast) */}
          {bgVariant !== 'sunset' && <rect width={W} height={svgH} className="fill-gray-100 dark:fill-gray-900" rx="8" />}
          {/* Sunset: Himmel + Meer — Light Mode */}
          {bgVariant === 'sunset' && <>
            <rect x="0" y="0"  width={W} height={CY}        fill="url(#ef-sky-sunset-light)" className="opacity-100 dark:opacity-0" />
            <rect x="0" y={CY} width={W} height={svgH - CY} fill="url(#ef-sea-sunset-light)" className="opacity-100 dark:opacity-0" />
          </>}
          {/* Sunset: Himmel + Meer — Dark Mode */}
          {bgVariant === 'sunset' && <>
            <rect x="0" y="0"  width={W} height={CY}        fill="url(#ef-sky-sunset-dark)" className="opacity-0 dark:opacity-100" />
            <rect x="0" y={CY} width={W} height={svgH - CY} fill="url(#ef-sea-sunset-dark)" className="opacity-0 dark:opacity-100" />
          </>}

          {/* ─── Perspektivgitter (Fluchtpunkt = Haus-Zentrum) — nur im Effekt-Modus ─── */}
          {!lite && bgVariant !== 'sunset' && (
            <g mask="url(#ef-grid-mask)">
              {/* Radiale Strahlen vom Zentrum zu den Rändern */}
              {Array.from({ length: 32 }, (_, i) => {
                const angle = (i / 32) * Math.PI * 2
                const farR = Math.max(W, svgH) * 0.9
                const ex = CX + Math.cos(angle) * farR
                const ey = CY + Math.sin(angle) * farR
                const isMajor = i % 4 === 0
                const isMid = i % 2 === 0
                return (
                  <line
                    key={`ray-${i}`}
                    x1={CX} y1={CY} x2={ex} y2={ey}
                    stroke="#64748b"
                    strokeWidth={isMajor ? 0.9 : isMid ? 0.5 : 0.3}
                    strokeOpacity={isMajor ? 0.3 : isMid ? 0.2 : 0.12}
                  />
                )
              })}
              {/* Konzentrische Perspektiv-Ringe (Abstand wächst nach außen → Tiefe) */}
              {[30, 55, 85, 125, 175, 240, 320].map((r, i) => (
                <circle
                  key={`pgrid-${i}`}
                  cx={CX} cy={CY} r={r}
                  fill="none"
                  stroke="#64748b"
                  strokeWidth={i < 2 ? 0.3 : 0.5 + i * 0.1}
                  strokeOpacity={0.12 + i * 0.04}
                />
              ))}
              {/* Knotenpunkte an den Schnittpunkten (äußere Ringe) */}
              {[85, 125, 175, 240, 320].flatMap((r, ri) =>
                Array.from({ length: 32 }, (_, ai) => {
                  if (ri < 2 && ai % 2 !== 0) return null
                  if (ri < 1 && ai % 4 !== 0) return null
                  const angle = (ai / 32) * Math.PI * 2
                  const px = CX + Math.cos(angle) * r
                  const py = CY + Math.sin(angle) * r
                  return (
                    <circle
                      key={`node-${ri}-${ai}`}
                      cx={px} cy={py}
                      r={0.7 + ri * 0.2}
                      fill="#64748b"
                      fillOpacity={0.18 + ri * 0.04}
                    />
                  )
                })
              )}
            </g>
          )}
          {/* ─── Sunset-Gitter: Krepuskulare Strahlen (Himmel) + Meerperspektive ─── */}
          {!lite && bgVariant === 'sunset' && (() => {
            // Gemeinsame Geometrie-Berechnung für beide Modi
            const farR = Math.max(W, svgH) * 1.2
            const skyRays = Array.from({ length: 20 }, (_, i) => ({
              angle: -Math.PI + (i / 19) * Math.PI,
              isEven: i % 2 === 0,
              isMajor: i % 4 === 0,
            }))
            const seaLines = Array.from({ length: 20 }, (_, i) => ({
              angle: (i / 19) * Math.PI,
              isMajor: i % 4 === 0,
              isMid: i % 2 === 0,
            }))
            const waveEllipses = [22, 50, 90, 140, 200, 270]
            const sparkRows = [50, 90, 140, 200]
            const arcRadii = [65, 115, 175, 250, 340]

            const renderGrid = (
              rayWide1: string, rayWide2: string,
              rayThin: string,
              arc1: string, arc2: string,
              seaLine: string, wave: string, spark: string,
            ) => (
              <>
                {/* ══ HIMMEL: Krepuskulare Strahlen ══ */}
                {skyRays.map(({ angle, isEven }, i) => {
                  const ex = CX + Math.cos(angle) * farR
                  const ey = CY + Math.sin(angle) * farR
                  return (
                    <line key={`cray-wide-${i}`}
                      x1={CX} y1={CY} x2={ex} y2={ey}
                      stroke={isEven ? rayWide1 : rayWide2}
                      strokeWidth={farR * 0.14}
                      strokeOpacity={isEven ? 0.07 : 0.04}
                      clipPath="url(#ef-sky-clip)" />
                  )
                })}
                {skyRays.map(({ angle, isMajor }, i) => {
                  const ex = CX + Math.cos(angle) * farR
                  const ey = CY + Math.sin(angle) * farR
                  return (
                    <line key={`cray-thin-${i}`}
                      x1={CX} y1={CY} x2={ex} y2={ey}
                      stroke={rayThin}
                      strokeWidth={isMajor ? 0.9 : 0.4}
                      strokeOpacity={isMajor ? 0.38 : 0.18}
                      clipPath="url(#ef-sky-clip)" />
                  )
                })}
                {/* Atmosphären-Bögen */}
                {arcRadii.map((r, i) => (
                  <path key={`arc-${i}`}
                    d={`M ${CX - r} ${CY} A ${r} ${r} 0 0 1 ${CX + r} ${CY}`}
                    fill="none"
                    stroke={i < 2 ? arc1 : arc2}
                    strokeWidth={0.4 + i * 0.15}
                    strokeOpacity={0.14 + i * 0.025}
                    clipPath="url(#ef-sky-clip)" />
                ))}

                {/* ══ MEER: Perspektivlinien ══ */}
                {seaLines.map(({ angle, isMajor, isMid }, i) => {
                  const ex = CX + Math.cos(angle) * (Math.max(W, svgH) * 0.95)
                  const ey = CY + Math.sin(angle) * (Math.max(W, svgH) * 0.95)
                  return (
                    <line key={`pline-${i}`}
                      x1={CX} y1={CY} x2={ex} y2={ey}
                      stroke={seaLine}
                      strokeWidth={isMajor ? 0.9 : isMid ? 0.5 : 0.3}
                      strokeOpacity={isMajor ? 0.32 : isMid ? 0.20 : 0.12}
                      clipPath="url(#ef-sea-clip)" />
                  )
                })}
                {/* Elliptische Wellenebenen */}
                {waveEllipses.map((dy, i) => (
                  <ellipse key={`wave-${i}`}
                    cx={CX} cy={CY + dy}
                    rx={CX * (0.22 + i * 0.14)}
                    ry={Math.max(3, dy * 0.10)}
                    fill="none"
                    stroke={wave}
                    strokeWidth={0.4 + i * 0.12}
                    strokeOpacity={0.12 + i * 0.03}
                    clipPath="url(#ef-sea-clip)" />
                ))}
                {/* Lichtfunken auf dem Wasser */}
                {sparkRows.flatMap((dy, ri) =>
                  Array.from({ length: 14 }, (_, ai) => {
                    if (ri < 1 && ai % 2 !== 0) return null
                    const angle = (ai / 13) * Math.PI
                    const rx = CX * (0.36 + ri * 0.14)
                    const px = CX + Math.cos(angle) * rx
                    const py = CY + dy + Math.sin(angle) * Math.max(3, dy * 0.10)
                    if (py <= CY + 2) return null
                    return (
                      <circle key={`spark-${ri}-${ai}`}
                        cx={px} cy={py}
                        r={0.6 + ri * 0.25}
                        fill={spark}
                        fillOpacity={0.22 + ri * 0.05} />
                    )
                  })
                )}
              </>
            )

            return (
              <>
                {/* Light Mode */}
                <g mask="url(#ef-grid-mask-s)" className="opacity-100 dark:opacity-0">
                  {renderGrid('#c47820', '#c05808', '#c47820', '#c05808', '#8b1a50', '#0e6070', '#0e6070', '#c47820')}
                </g>
                {/* Dark Mode */}
                <g mask="url(#ef-grid-mask-s)" className="opacity-0 dark:opacity-100">
                  {renderGrid('#ffd700', '#ff8c00', '#ffd700', '#ff8c00', '#ec4899', '#c47310', '#c47310', '#ffd700')}
                </g>
              </>
            )
          })()}

          {/* Radiales Energie-Glow (Default) */}
          {bgVariant !== 'sunset' && <>
            <rect width={W} height={svgH} className="opacity-100 dark:opacity-0" fill="url(#ef-glow-light)" rx="8" />
            <rect width={W} height={svgH} className="opacity-0 dark:opacity-100" fill="url(#ef-glow-dark)" rx="8" />
          </>}
          {/* 3D-Spot unter dem Haus (Default) */}
          {bgVariant !== 'sunset' && <>
            <rect width={W} height={svgH} className="opacity-100 dark:opacity-0" fill="url(#ef-spot-light)" rx="8" />
            <rect width={W} height={svgH} className="opacity-0 dark:opacity-100" fill="url(#ef-spot-dark)" rx="8" />
          </>}
          {/* Sunset: Sonnen-Glow-Layer Light */}
          {bgVariant === 'sunset' && <>
            <rect width={W} height={svgH} fill="url(#ef-sun-glow-light)"  className="opacity-100 dark:opacity-0" />
            <rect width={W} height={svgH} fill="url(#ef-sun-atmo-light)"  className="opacity-100 dark:opacity-0" />
            <rect width={W} height={svgH} fill="url(#ef-sun-spot-light)"  className="opacity-100 dark:opacity-0" />
          </>}
          {/* Sunset: Sonnen-Glow-Layer Dark */}
          {bgVariant === 'sunset' && <>
            <rect width={W} height={svgH} fill="url(#ef-sun-glow-dark)"  className="opacity-0 dark:opacity-100" />
            <rect width={W} height={svgH} fill="url(#ef-sun-atmo-dark)"  className="opacity-0 dark:opacity-100" />
            <rect width={W} height={svgH} fill="url(#ef-sun-spot-dark)"  className="opacity-0 dark:opacity-100" />
          </>}
          {/* Horizontlinie (goldener Schimmer) */}
          {bgVariant === 'sunset' && (
            <line x1={0} y1={CY} x2={W} y2={CY} stroke="#ffd700" strokeWidth="0.8" strokeOpacity="0.38" />
          )}

          {/* ─── Hintergrund-Animationen — nur im Effekt-Modus ─── */}
          {!lite && bgVariant !== 'sunset' && (<>
          {/* Fließende Strom-Ströme */}
          <path
            d={`M ${CX - 80} 10 Q ${CX - 40} ${CY * 0.4} ${CX} ${CY}`}
            fill="none" stroke="#ca8a04" strokeWidth="2" strokeOpacity="0.18"
            strokeDasharray="3 12"
            style={{ animation: 'bg-stream 4s linear infinite' }}
          />
          <path
            d={`M ${CX + 80} 10 Q ${CX + 40} ${CY * 0.4} ${CX} ${CY}`}
            fill="none" stroke="#ca8a04" strokeWidth="1.5" strokeOpacity="0.14"
            strokeDasharray="2 10"
            style={{ animation: 'bg-stream 5s linear infinite' }}
          />
          <path
            d={`M ${CX} 5 Q ${CX + 15} ${CY * 0.5} ${CX} ${CY}`}
            fill="none" stroke="#eab308" strokeWidth="1.8" strokeOpacity="0.16"
            strokeDasharray="4 14"
            style={{ animation: 'bg-stream 3.5s linear infinite' }}
          />
          <path
            d={`M ${CX} ${CY} Q ${CX - 50} ${CY + 60} ${CX - 100} ${svgH - 10}`}
            fill="none" stroke="#059669" strokeWidth="1.8" strokeOpacity="0.16"
            strokeDasharray="3 12"
            style={{ animation: 'bg-stream 4.5s linear infinite' }}
          />
          <path
            d={`M ${CX} ${CY} Q ${CX + 50} ${CY + 60} ${CX + 100} ${svgH - 10}`}
            fill="none" stroke="#059669" strokeWidth="1.5" strokeOpacity="0.13"
            strokeDasharray="2 10"
            style={{ animation: 'bg-stream 5.5s linear infinite' }}
          />
          <path
            d={`M 5 ${CY - 30} Q ${CX * 0.4} ${CY - 10} ${CX} ${CY}`}
            fill="none" stroke="#dc2626" strokeWidth="1.5" strokeOpacity="0.14"
            strokeDasharray="2 10"
            style={{ animation: 'bg-stream 6s linear infinite' }}
          />
          <path
            d={`M 5 ${CY + 30} Q ${CX * 0.4} ${CY + 10} ${CX} ${CY}`}
            fill="none" stroke="#dc2626" strokeWidth="1.2" strokeOpacity="0.1"
            strokeDasharray="3 14"
            style={{ animation: 'bg-stream 7s linear infinite' }}
          />
          <path
            d={`M ${CX} ${CY} Q ${CX + CX * 0.6} ${CY - 15} ${W - 5} ${CY - 20}`}
            fill="none" stroke="#2563eb" strokeWidth="1.5" strokeOpacity="0.14"
            strokeDasharray="2 10"
            style={{ animation: 'bg-stream 5s linear infinite' }}
          />
          <path
            d={`M ${CX} ${CY} Q ${CX + CX * 0.6} ${CY + 15} ${W - 5} ${CY + 20}`}
            fill="none" stroke="#2563eb" strokeWidth="1.2" strokeOpacity="0.1"
            strokeDasharray="3 12"
            style={{ animation: 'bg-stream 6.5s linear infinite' }}
          />

          {/* Konzentrische Energieringe mit Glow */}
          {[80, 130, 190, 260].map((r, i) => (
            <g key={`ring-${i}`}>
              <circle
                cx={CX} cy={CY} r={r}
                fill="none"
                stroke="#10b981"
                strokeWidth={3 - i * 0.3}
                strokeOpacity={0.08}
                strokeDasharray="6 12"
                filter="url(#ef-ring-glow)"
                style={{ animation: `pulse-ring ${4 + i * 1.5}s ease-in-out infinite` }}
              />
              <circle
                cx={CX} cy={CY} r={r}
                fill="none"
                stroke="#10b981"
                strokeWidth={1 - i * 0.1}
                strokeOpacity={0.22 - i * 0.03}
                strokeDasharray="4 8"
                style={{ animation: `pulse-ring ${4 + i * 1.5}s ease-in-out infinite` }}
              />
            </g>
          ))}

          {/* Hintergrund-Partikel */}
          {[0, 1, 2, 3, 4].map(i => (
            <circle key={`p-pv-${i}`} fill="#ca8a04" r="1.5">
              <animateMotion
                dur={`${3 + i * 0.8}s`}
                repeatCount="indefinite"
                begin={`${i * 0.7}s`}
                path={`M ${CX - 60 + i * 30} 15 Q ${CX - 20 + i * 10} ${CY * 0.45} ${CX} ${CY}`}
              />
              <animate attributeName="opacity" values="0;0.7;0.4;0" dur={`${3 + i * 0.8}s`} repeatCount="indefinite" begin={`${i * 0.7}s`} />
              <animate attributeName="r" values="1;2;0.6" dur={`${3 + i * 0.8}s`} repeatCount="indefinite" begin={`${i * 0.7}s`} />
            </circle>
          ))}
          {[0, 1, 2, 3].map(i => (
            <circle key={`p-vb-${i}`} fill="#059669" r="1.3">
              <animateMotion
                dur={`${3.5 + i * 0.9}s`}
                repeatCount="indefinite"
                begin={`${i * 1.0}s`}
                path={`M ${CX} ${CY} Q ${CX + (-1) ** i * 40} ${CY + 50} ${CX + (-1) ** i * (60 + i * 20)} ${svgH - 15}`}
              />
              <animate attributeName="opacity" values="0;0.65;0.35;0" dur={`${3.5 + i * 0.9}s`} repeatCount="indefinite" begin={`${i * 1.0}s`} />
              <animate attributeName="r" values="0.8;1.8;0.5" dur={`${3.5 + i * 0.9}s`} repeatCount="indefinite" begin={`${i * 1.0}s`} />
            </circle>
          ))}
          {[0, 1].map(i => (
            <circle key={`p-nz-${i}`} fill="#dc2626" r="1.2">
              <animateMotion
                dur={`${5 + i * 1.5}s`}
                repeatCount="indefinite"
                begin={`${i * 2.5}s`}
                path={`M 8 ${CY + (-1) ** i * 25} Q ${CX * 0.4} ${CY + (-1) ** i * 8} ${CX} ${CY}`}
              />
              <animate attributeName="opacity" values="0;0.6;0.3;0" dur={`${5 + i * 1.5}s`} repeatCount="indefinite" begin={`${i * 2.5}s`} />
            </circle>
          ))}
          {[0, 1].map(i => (
            <circle key={`p-sp-${i}`} fill="#2563eb" r="1.2">
              <animateMotion
                dur={`${4.5 + i * 1.5}s`}
                repeatCount="indefinite"
                begin={`${i * 2.0}s`}
                path={`M ${CX} ${CY} Q ${CX + CX * 0.55} ${CY + (-1) ** i * 12} ${W - 8} ${CY + (-1) ** i * 18}`}
              />
              <animate attributeName="opacity" values="0;0.6;0.3;0" dur={`${4.5 + i * 1.5}s`} repeatCount="indefinite" begin={`${i * 2.0}s`} />
            </circle>
          ))}
          </>)}

          {/* ─── Sunset-Animationen — nur im Effekt-Modus ─── */}
          {!lite && bgVariant === 'sunset' && (<>
            {/* Sonnenstrahlen von oben → Horizont */}
            <path d={`M ${CX - 80} 10 Q ${CX - 40} ${CY * 0.5} ${CX} ${CY}`}
              fill="none" stroke="#ffa500" strokeWidth="2" strokeOpacity="0.22" strokeDasharray="3 12"
              style={{ animation: 'sunset-stream 4s linear infinite' }} />
            <path d={`M ${CX + 80} 10 Q ${CX + 40} ${CY * 0.5} ${CX} ${CY}`}
              fill="none" stroke="#ffa500" strokeWidth="1.5" strokeOpacity="0.18" strokeDasharray="2 10"
              style={{ animation: 'sunset-stream 5s linear infinite' }} />
            <path d={`M ${CX} 5 Q ${CX + 15} ${CY * 0.5} ${CX} ${CY}`}
              fill="none" stroke="#ffd700" strokeWidth="1.8" strokeOpacity="0.20" strokeDasharray="4 14"
              style={{ animation: 'sunset-stream 3.5s linear infinite' }} />
            <path d={`M ${CX - 160} 5 Q ${CX - 80} ${CY * 0.3} ${CX} ${CY}`}
              fill="none" stroke="#ec4899" strokeWidth="1.2" strokeOpacity="0.14" strokeDasharray="2 10"
              style={{ animation: 'sunset-stream 6s linear infinite' }} />
            <path d={`M ${CX + 160} 5 Q ${CX + 80} ${CY * 0.3} ${CX} ${CY}`}
              fill="none" stroke="#ec4899" strokeWidth="1.2" strokeOpacity="0.12" strokeDasharray="3 12"
              style={{ animation: 'sunset-stream 7s linear infinite' }} />
            {/* Seitliche Lichtstreifen vom Horizont */}
            <path d={`M 5 ${CY - 20} Q ${CX * 0.4} ${CY - 8} ${CX} ${CY}`}
              fill="none" stroke="#ff6b35" strokeWidth="1.5" strokeOpacity="0.16" strokeDasharray="2 10"
              style={{ animation: 'sunset-stream 6s linear infinite' }} />
            <path d={`M ${W - 5} ${CY - 20} Q ${CX + CX * 0.6} ${CY - 8} ${CX} ${CY}`}
              fill="none" stroke="#ff6b35" strokeWidth="1.5" strokeOpacity="0.16" strokeDasharray="2 10"
              style={{ animation: 'sunset-stream 5.5s linear infinite' }} />
            {/* Wasserreflektionen — horizontale Shimmer-Bögen unter CY */}
            <path d={`M ${CX - 120} ${CY + 30} Q ${CX} ${CY + 25} ${CX + 120} ${CY + 30}`}
              fill="none" stroke="#ffa500" strokeWidth="1.5" strokeOpacity="0.22" strokeDasharray="8 20"
              style={{ animation: 'shimmer 3s ease-in-out infinite' }} />
            <path d={`M ${CX - 100} ${CY + 55} Q ${CX} ${CY + 50} ${CX + 100} ${CY + 55}`}
              fill="none" stroke="#ff8c00" strokeWidth="1.2" strokeOpacity="0.17" strokeDasharray="6 18"
              style={{ animation: 'shimmer 4s ease-in-out infinite 0.5s' }} />
            <path d={`M ${CX - 80} ${CY + 80} Q ${CX} ${CY + 75} ${CX + 80} ${CY + 80}`}
              fill="none" stroke="#ffa500" strokeWidth="1" strokeOpacity="0.14" strokeDasharray="5 16"
              style={{ animation: 'shimmer 3.5s ease-in-out infinite 1s' }} />
            <path d={`M ${CX - 160} ${CY + 115} Q ${CX} ${CY + 108} ${CX + 160} ${CY + 115}`}
              fill="none" stroke="#c47310" strokeWidth="0.8" strokeOpacity="0.12" strokeDasharray="4 14"
              style={{ animation: 'shimmer 5s ease-in-out infinite 1.5s' }} />
            <path d={`M 20 ${CY + 155} Q ${CX} ${CY + 145} ${W - 20} ${CY + 155}`}
              fill="none" stroke="#c47310" strokeWidth="0.7" strokeOpacity="0.10" strokeDasharray="3 12"
              style={{ animation: 'shimmer 6s ease-in-out infinite 2s' }} />

            {/* Sonnen-Halo Ringe (orange/gold statt emerald) */}
            {[80, 130, 190, 260].map((r, i) => (
              <g key={`ring-sunset-${i}`}>
                <circle cx={CX} cy={CY} r={r} fill="none"
                  stroke="#ff8c00" strokeWidth={3 - i * 0.3} strokeOpacity={0.08}
                  strokeDasharray="6 12" filter="url(#ef-ring-glow)"
                  style={{ animation: `pulse-ring-sunset ${5 + i * 1.5}s ease-in-out infinite` }} />
                <circle cx={CX} cy={CY} r={r} fill="none"
                  stroke={i < 2 ? '#ffd700' : '#ff6b00'}
                  strokeWidth={1 - i * 0.1} strokeOpacity={0.20 - i * 0.025}
                  strokeDasharray="4 8"
                  style={{ animation: `pulse-ring-sunset ${5 + i * 1.5}s ease-in-out infinite` }} />
              </g>
            ))}

            {/* Sonnen-Partikel (golden, von oben → Horizont) */}
            {[0, 1, 2, 3, 4].map(i => (
              <circle key={`p-sun-${i}`} fill="#ffd700" r="1.5">
                <animateMotion dur={`${3 + i * 0.8}s`} repeatCount="indefinite" begin={`${i * 0.7}s`}
                  path={`M ${CX - 60 + i * 30} 15 Q ${CX - 20 + i * 10} ${CY * 0.45} ${CX} ${CY}`} />
                <animate attributeName="opacity" values="0;0.75;0.45;0" dur={`${3 + i * 0.8}s`} repeatCount="indefinite" begin={`${i * 0.7}s`} />
                <animate attributeName="r" values="1;2.2;0.6" dur={`${3 + i * 0.8}s`} repeatCount="indefinite" begin={`${i * 0.7}s`} />
              </circle>
            ))}
            {/* Wasser-Reflexionspartikel (orange, schimmern auf dem Meer) */}
            {[0, 1, 2, 3].map(i => (
              <circle key={`p-reflect-${i}`} fill="#ff8c00" r="1.2">
                <animateMotion dur={`${4 + i * 1.2}s`} repeatCount="indefinite" begin={`${i * 1.1}s`}
                  path={`M ${CX + (-1) ** i * 80} ${CY + 20 + i * 25} Q ${CX + (-1) ** i * 30} ${CY + 30 + i * 20} ${CX} ${CY + 10}`} />
                <animate attributeName="opacity" values="0;0.62;0.30;0" dur={`${4 + i * 1.2}s`} repeatCount="indefinite" begin={`${i * 1.1}s`} />
                <animate attributeName="r" values="0.8;1.8;0.5" dur={`${4 + i * 1.2}s`} repeatCount="indefinite" begin={`${i * 1.1}s`} />
              </circle>
            ))}
            {/* Pink/Magenta Sky-Partikel (von oben-seitlich → Horizont) */}
            {[0, 1].map(i => (
              <circle key={`p-sky-${i}`} fill="#ec4899" r="1.2">
                <animateMotion dur={`${5.5 + i * 1.5}s`} repeatCount="indefinite" begin={`${i * 2.0}s`}
                  path={`M ${i === 0 ? CX - 140 : CX + 140} 8 Q ${CX + (i === 0 ? -60 : 60)} ${CY * 0.4} ${CX} ${CY}`} />
                <animate attributeName="opacity" values="0;0.55;0.25;0" dur={`${5.5 + i * 1.5}s`} repeatCount="indefinite" begin={`${i * 2.0}s`} />
              </circle>
            ))}
          </>)}

          {/* Dezente Achsenlinien (Kreuz durch Zentrum) */}
          {bgVariant !== 'sunset' && <>
            <line x1={CX} y1={12} x2={CX} y2={svgH - 12} stroke="#9ca3af" strokeWidth="0.5" strokeOpacity={0.15} strokeDasharray="2 6" />
            <line x1={12} y1={CY} x2={W - 12} y2={CY} stroke="#9ca3af" strokeWidth="0.5" strokeOpacity={0.15} strokeDasharray="2 6" />
          </>}
          {bgVariant === 'sunset' && <>
            <line x1={CX} y1={12} x2={CX} y2={svgH - 12} stroke="#ff8c00" strokeWidth="0.5" strokeOpacity={0.18} strokeDasharray="2 6" />
            <line x1={12} y1={CY} x2={W - 12} y2={CY} stroke="#ffd700" strokeWidth="0.8" strokeOpacity={0.24} strokeDasharray="4 4" />
          </>}

          {/* Tiefe-Vignette (dunkelt Ränder ab → 3D-Einbuchtung) — nur im Effekt-Modus */}
          {!lite && bgVariant !== 'sunset' && (
            <>
              <rect width={W} height={svgH} className="opacity-100 dark:opacity-0" fill="url(#ef-vignette-light)" rx="8" />
              <rect width={W} height={svgH} className="opacity-0 dark:opacity-100" fill="url(#ef-vignette-dark)" rx="8" />
            </>
          )}
          {!lite && bgVariant === 'sunset' && <>
            <rect width={W} height={svgH} fill="url(#ef-vignette-sunset-light)" rx="8" className="opacity-100 dark:opacity-0" />
            <rect width={W} height={svgH} fill="url(#ef-vignette-sunset-dark)"  rx="8" className="opacity-0 dark:opacity-100" />
          </>}
        </g>

        {/* Verbindungslinien */}
        {nodes.map(node => {
          const k = node.komp
          const kw = (k.erzeugung_kw ?? 0) + (k.verbrauch_kw ?? 0)
          const thickness = logThickness(kw, maxKw)
          const color = getNodeColor(k, netzPufferW)
          const isActive = kw > 0
          const isSource = (k.erzeugung_kw ?? 0) > 0
          const duration = flowDuration(kw)
          // Kinder verbinden sich zum Parent statt zum Haus
          const parentNode = k.parent_key ? nodeMap.get(k.parent_key) : null
          const targetX = parentNode ? parentNode.x : CX
          const targetY = parentNode ? parentNode.y : CY
          const d = flowPath(node.x, node.y, targetX, targetY)

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
                stroke={isActive ? color : '#9ca3af'}
                strokeWidth={thickness}
                strokeOpacity={isActive ? 0.2 : 0.08}
                strokeLinecap="round"
              />
              {/* Kern-Linie (leuchtend, schmal) */}
              {isActive && (
                <path
                  d={d}
                  fill="none"
                  stroke={color}
                  strokeWidth={Math.max(thickness * 0.4, 1.5)}
                  strokeOpacity={0.85}
                  strokeLinecap="round"
                />
              )}
              {/* Animierte Partikel (Elektronen) auf dem Pfad — im Lite-Modus max 1 */}
              {isActive && Array.from({ length: lite ? 1 : Math.min(3, Math.ceil(kw / 2) + 1) }, (_, pi) => {
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
        <g className="cursor-default">
          <title>{[
            'Haushalt',
            `Aktuell: ${haushalt ? (haushalt.verbrauch_kw ?? 0).toFixed(2) : '—'} kW`,
            `Quellen: ${summeErzeugung.toFixed(2)} kW`,
            `Verbrauch: ${summeVerbrauch.toFixed(2)} kW`,
            ...(tagesWerte?.haushalt != null ? [`Heute: ${tagesWerte.haushalt.toFixed(1)} kWh`] : []),
          ].join('\n')}</title>
          {/* Pulsierender Glow-Ring — nur im Effekt-Modus */}
          {!lite && (
            <>
              <circle
                cx={CX} cy={CY} r={HAUS_R + 6}
                fill="none"
                stroke="#10b981"
                strokeWidth={3}
                filter="url(#ef-haus-glow)"
                style={{ animation: 'haus-glow 3s ease-in-out infinite' }}
              />
              <circle
                cx={CX} cy={CY} r={HAUS_R + 2}
                fill="none"
                stroke="#10b981"
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
            stroke="#10b981"
            strokeWidth={2}
            strokeOpacity={0.6}
          />
          <foreignObject x={CX - dims.hausIconSize / 2} y={CY - dims.hausIconSize * 0.75} width={dims.hausIconSize} height={dims.hausIconSize}>
            <IconElement name="home" size={dims.hausIconSize} className="text-emerald-500" />
          </foreignObject>
          {/* Netto-Hausverbrauch im Kreis */}
          <text
            x={CX} y={CY + dims.hausIconSize * 0.7}
            textAnchor="middle"
            style={{ fontSize: `${dims.kwFontSize}px` }}
            className="font-bold fill-gray-900 dark:fill-white"
          >
            {formatPower(nettoHausverbrauch)}
          </text>
        </g>

        {/* Solarleistung + PV-Soll — oberhalb des Hauses */}
        {summePv > 0 && (
          <text
            x={CX} y={CY - HAUS_R - 8}
            textAnchor="middle"
            style={{ fontSize: `${dims.socFontSize}px` }}
            className={bgVariant === 'sunset'
              ? 'fill-amber-800 dark:fill-yellow-400'
              : 'fill-yellow-500 dark:fill-yellow-400'}
          >
            <title>Summe aller PV-Erzeuger (ohne Batterie/Netz)</title>
            Solarleistung {formatPower(summePv)}
          </text>
        )}
        {pvSollKw != null && pvSollKw > 0 && (
          <text
            x={CX} y={CY - HAUS_R - 8 - (summePv > 0 ? dims.socFontSize + 2 : 0)}
            textAnchor="middle"
            style={{ fontSize: `${dims.socFontSize - 1}px` }}
            className={bgVariant === 'sunset'
              ? 'fill-purple-800 dark:fill-purple-400'
              : 'fill-purple-500 dark:fill-purple-400'}
          >
            Solar Soll ~{pvSollKw.toFixed(1)} kW
          </text>
        )}

        {/* Komponenten-Knoten */}
        {nodes.map(node => {
          const k = node.komp
          const kw = Math.max(k.erzeugung_kw ?? 0, k.verbrauch_kw ?? 0)
          const color = getNodeColor(k, netzPufferW)
          const isActive = kw > 0
          const soc = getSoc(k.key, gauges)
          const hasSoc = soc !== null

          // Tooltip — tagesWerte per exaktem Key oder Prefix matchen
          const tagesKwh = tagesWerte?.[k.key]
            ?? tagesWerte?.[k.key.replace(/_\d+$/, '')]
            ?? null
          const tipParts = [k.label]
          if ((k.erzeugung_kw ?? 0) > 0) tipParts.push(`Aktuell: ${k.erzeugung_kw!.toFixed(2)} kW (Erzeugung)`)
          if ((k.verbrauch_kw ?? 0) > 0) tipParts.push(`Aktuell: ${k.verbrauch_kw!.toFixed(2)} kW (Verbrauch)`)
          if (hasSoc) tipParts.push(`SoC: ${soc}%`)
          // Netz: Bezug + Einspeisung separat anzeigen + Farberklärung
          if (k.key === 'netz') {
            const bezug = tagesWerte?.netz_bezug
            const einsp = tagesWerte?.netz_einspeisung
            if (bezug != null) tipParts.push(`Heute Bezug: ${bezug.toFixed(1)} kWh`)
            if (einsp != null) tipParts.push(`Heute Einspeisung: ${einsp.toFixed(1)} kWh`)
            tipParts.push(`Farbe: grün = Balance (< ${netzPufferW} W), orange = Einspeisung, rot = Bezug`)
          } else if (tagesKwh != null) {
            tipParts.push(`Heute: ${tagesKwh.toFixed(1)} kWh`)
          }
          const tip = tipParts.join('\n')

          // Label kürzen
          const maxC = dims.labelMaxChars
          const shortLabel = k.label.length > maxC ? k.label.slice(0, maxC - 2) + '…' : k.label

          const nx = node.x - NODE_W / 2
          const ny = node.y - NODE_H / 2

          return (
            <g key={`node-${k.key}`} className="cursor-default">
              <title>{tip}</title>

              {/* Knoten-Hintergrund (halbtransparent, Gitter scheint durch) */}
              <rect
                x={nx} y={ny}
                width={NODE_W} height={NODE_H}
                rx={NODE_R}
                className="fill-white dark:fill-gray-800"
                fillOpacity={bgVariant === 'sunset' ? 0.92 : 0.6}
                stroke={isActive ? color : '#9ca3af'}
                strokeWidth={isActive ? 1 : 0.5}
                strokeOpacity={isActive ? 0.7 : 0.3}
                filter="url(#ef-card-shadow)"
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
                <IconElement name={k.icon} size={dims.iconSize} color={isActive ? color : '#9ca3af'} />
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

              {/* SoC-Anzeige */}
              {hasSoc && (
                <text
                  x={node.x} y={node.y + dims.kwFontSize + 2}
                  textAnchor="middle"
                  style={{ fontSize: `${dims.socFontSize}px` }}
                  className="font-semibold"
                  fill={socColor(soc)}
                >
                  {soc}%
                </text>
              )}

              {/* Label */}
              <text
                x={node.x} y={node.y + (hasSoc ? NODE_H / 2 - 4 : dims.kwFontSize + 6)}
                textAnchor="middle"
                style={{ fontSize: `${dims.labelFontSize}px` }}
                className="fill-gray-500 dark:fill-gray-400"
              >
                {shortLabel}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
