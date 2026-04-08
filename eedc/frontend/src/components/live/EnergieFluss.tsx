/**
 * EnergieFluss — Animiertes Energiefluss-Diagramm (ersetzt EnergieBilanz).
 *
 * Zeigt alle Komponenten als Knoten um ein zentrales Haus-Symbol.
 * Animierte Linien zeigen Flussrichtung und -stärke.
 * Informationsparität mit EnergieBilanz: kW-Werte, Icons, Farben,
 * Tages-kWh Tooltips, Σ Erzeugung/Verbrauch.
 */

import { useState, useEffect, useRef, useMemo } from 'react'
import { Sun, Zap, Battery, Car, Flame, Wrench, Home, Plug, Heater, Droplets, Sparkles, Zap as ZapIcon } from 'lucide-react'
import type { LiveKomponente, LiveGauge } from '../../api/liveDashboard'
import EnergieFlussBackground from './EnergieFlussBackground'

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
export type BgVariant = 'default' | 'sunset' | 'alps' | 'alpenpanorama' | 'milchstrasse' | 'dolomiten' | 'nebula' | 'sternennacht' | 'exoplanet'

const BG_VARIANTS: BgVariant[] = ['default', 'sunset', 'alps', 'alpenpanorama', 'milchstrasse', 'dolomiten', 'nebula', 'sternennacht', 'exoplanet']

const BG_LABELS: Record<BgVariant, string> = {
  default:       'Tech',
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
  const [bgVariant, setBgVariant] = useBgVariant()
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

  // Layout + abgeleitete Werte memoizen (teuerste Berechnung, O(n²) Filter/Map)
  const { nodes, dims, nodeMap, maxKw, nettoHausverbrauch, svgH } = useMemo(() => {
    const layout = layoutNodes(komponenten, W)
    const _nodeMap = new Map(layout.nodes.map(n => [n.komp.key, n]))

    const _nettoHausverbrauch = komponenten
      .filter(k => !k.key.startsWith('pv_') && k.key !== 'netz' && !k.key.startsWith('batterie_') && !k.parent_key)
      .reduce((sum, k) => sum + (k.verbrauch_kw ?? 0), 0)

    const _maxY = Math.max(...layout.nodes.map(n => n.y), layout.dims.verbraucherY)
    const _svgH = Math.max(380, _maxY + layout.dims.nodeH / 2 + 10)

    const allKw = komponenten.flatMap(k => [k.erzeugung_kw ?? 0, k.verbrauch_kw ?? 0])
    const _maxKw = Math.max(...allKw, 0.1)

    return { nodes: layout.nodes, dims: layout.dims, nodeMap: _nodeMap, maxKw: _maxKw, nettoHausverbrauch: _nettoHausverbrauch, svgH: _svgH }
  }, [komponenten, W])

  const { nodeW: NODE_W, nodeH: NODE_H, nodeR: NODE_R, hausR: HAUS_R } = dims
  const CY = dims.cy
  const haushalt = komponenten.find(k => k.key === 'haushalt')

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
        </div>
      </div>

      <svg
        viewBox={`0 0 ${W} ${svgH}`}
        className="w-full flex-1 min-h-0"
      >
        <EnergieFlussBackground W={W} svgH={svgH} CX={CX} CY={CY} lite={lite} bgVariant={bgVariant} bgPhotoFile={BG_PHOTO_FILE} />


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
        <g className="cursor-default" {...{title: [
            'Haushalt',
            `Aktuell: ${haushalt ? (haushalt.verbrauch_kw ?? 0).toFixed(2) : '—'} kW`,
            `Quellen: ${summeErzeugung.toFixed(2)} kW`,
            `Verbrauch: ${summeVerbrauch.toFixed(2)} kW`,
            ...(tagesWerte?.haushalt != null ? [`Heute: ${tagesWerte.haushalt.toFixed(1)} kWh`] : []),
          ].join('\n')} as any}>
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
              : bgVariant === 'alps'
                ? 'fill-blue-800 dark:fill-blue-300'
                : 'fill-yellow-500 dark:fill-yellow-400'}
          {...{title: "Summe aller PV-Erzeuger (ohne Batterie/Netz)"} as any}
          >
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
              : bgVariant === 'alps'
                ? 'fill-indigo-800 dark:fill-indigo-300'
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

          // PV-Auslastung: Ist-Leistung / installierte kWp
          const isPv = k.key.startsWith('pv_')
          const auslastungPct = isPv && k.leistung_kwp && k.leistung_kwp > 0 && (k.erzeugung_kw ?? 0) > 0
            ? Math.min(100, ((k.erzeugung_kw ?? 0) / k.leistung_kwp) * 100)
            : null

          // Tooltip — tagesWerte per exaktem Key oder Prefix matchen
          const tagesKwh = tagesWerte?.[k.key]
            ?? tagesWerte?.[k.key.replace(/_\d+$/, '')]
            ?? null
          const tipParts = [k.label]
          if ((k.erzeugung_kw ?? 0) > 0) tipParts.push(`Aktuell: ${k.erzeugung_kw!.toFixed(2)} kW (Erzeugung)`)
          if ((k.verbrauch_kw ?? 0) > 0) tipParts.push(`Aktuell: ${k.verbrauch_kw!.toFixed(2)} kW (Verbrauch)`)
          if (hasSoc) tipParts.push(`SoC: ${soc}%`)
          if (auslastungPct !== null) tipParts.push(`Auslastung: ${auslastungPct.toFixed(0)}% von ${k.leistung_kwp} kWp`)
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
            <g key={`node-${k.key}`} className="cursor-default" {...{title: tip} as any}>

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

              {/* PV-Auslastungs-Pegel (Füllung von unten, gelb/orange) */}
              {auslastungPct !== null && (
                <rect
                  x={nx + 1.5} y={ny + 1.5 + (NODE_H - 3) * (1 - auslastungPct / 100)}
                  width={NODE_W - 3}
                  height={(NODE_H - 3) * (auslastungPct / 100)}
                  rx={NODE_R - 1}
                  fill={auslastungPct >= 80 ? '#f59e0b' : auslastungPct >= 40 ? '#eab308' : '#86efac'}
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
