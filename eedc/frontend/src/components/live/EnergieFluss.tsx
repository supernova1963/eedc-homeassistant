/**
 * EnergieFluss — Animiertes Energiefluss-Diagramm (ersetzt EnergieBilanz).
 *
 * Zeigt alle Komponenten als Knoten um ein zentrales Haus-Symbol.
 * Animierte Linien zeigen Flussrichtung und -stärke.
 * Informationsparität mit EnergieBilanz: kW-Werte, Icons, Farben,
 * Tages-kWh Tooltips, Σ Erzeugung/Verbrauch.
 */

import { Sun, Zap, Battery, Car, Flame, Wrench, Home, Plug } from 'lucide-react'
import type { LiveKomponente, LiveGauge } from '../../api/liveDashboard'

// ─── Shared Utilities (aus EnergieBilanz) ───────────────────────────

const ICON_MAP: Record<string, React.ElementType> = {
  sun: Sun, zap: Zap, battery: Battery, car: Car, plug: Plug,
  flame: Flame, wrench: Wrench, home: Home,
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
  tagesWerte?: Record<string, number | null>
  gauges?: LiveGauge[]
}

interface NodePosition {
  x: number
  y: number
  komp: LiveKomponente
}

// ─── Layout ─────────────────────────────────────────────────────────

const W = 600
const CX = W / 2

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

function layoutNodes(komponenten: LiveKomponente[]): LayoutResult {
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

  // Kinder in Verbraucher-Reihe einreihen (Flusslinie geht trotzdem zum Parent)
  const alleUnten = [...verbraucher, ...kinder]

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
  komponenten, summeErzeugung, summeVerbrauch, tagesWerte, gauges,
}: EnergieFlussProps) {
  if (komponenten.length === 0) return null

  const { nodes, dims } = layoutNodes(komponenten)
  const { nodeW: NODE_W, nodeH: NODE_H, nodeR: NODE_R, hausR: HAUS_R } = dims
  const CY = dims.cy
  const nodeMap = new Map(nodes.map(n => [n.komp.key, n]))
  const haushalt = komponenten.find(k => k.key === 'haushalt')

  // Dynamische Höhe: Basis 380, erweitert wenn Knoten tiefer liegen
  const maxY = Math.max(...nodes.map(n => n.y), dims.verbraucherY)
  const svgH = Math.max(380, maxY + NODE_H / 2 + 10)

  // Max kW für Dicken-Normierung
  const allKw = komponenten.flatMap(k => [k.erzeugung_kw ?? 0, k.verbrauch_kw ?? 0])
  const maxKw = Math.max(...allKw, 0.1)

  return (
    <div className="flex flex-col h-full">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 shrink-0">
        Energiefluss
      </h3>

      <svg
        viewBox={`0 0 ${W} ${svgH}`}
        className="w-full flex-1 min-h-0"
      >
        {/* CSS Animation */}
        <defs>
          <style>{`
            @keyframes flow-forward {
              from { stroke-dashoffset: 20; }
              to { stroke-dashoffset: 0; }
            }
            @keyframes flow-reverse {
              from { stroke-dashoffset: 0; }
              to { stroke-dashoffset: 20; }
            }
          `}</style>
        </defs>

        {/* Verbindungslinien */}
        {nodes.map(node => {
          const k = node.komp
          const kw = (k.erzeugung_kw ?? 0) + (k.verbrauch_kw ?? 0)
          const thickness = logThickness(kw, maxKw)
          const color = getColor(k.key)
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
              {/* Hintergrundlinie */}
              <path
                d={d}
                fill="none"
                stroke={isActive ? color : '#9ca3af'}
                strokeWidth={thickness}
                strokeOpacity={isActive ? 0.15 : 0.08}
                strokeLinecap="round"
              />
              {/* Animierte Flusslinie */}
              {isActive && (
                <path
                  d={d}
                  fill="none"
                  stroke={color}
                  strokeWidth={thickness}
                  strokeOpacity={0.7}
                  strokeLinecap="round"
                  strokeDasharray="5 15"
                  style={{
                    animation: `${isSource ? 'flow-forward' : 'flow-reverse'} ${duration}s linear infinite`,
                  }}
                />
              )}
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
          <circle
            cx={CX} cy={CY} r={HAUS_R}
            className="fill-white dark:fill-gray-800 stroke-gray-300 dark:stroke-gray-600"
            strokeWidth={2}
          />
          <foreignObject x={CX - dims.hausIconSize / 2} y={CY - dims.hausIconSize * 0.75} width={dims.hausIconSize} height={dims.hausIconSize}>
            <IconElement name="home" size={dims.hausIconSize} className="text-emerald-500" />
          </foreignObject>
          {/* Haushalt kW */}
          <text
            x={CX} y={CY + dims.hausIconSize * 0.7}
            textAnchor="middle"
            style={{ fontSize: `${dims.kwFontSize}px` }}
            className="font-bold fill-gray-900 dark:fill-white"
          >
            {haushalt ? `${(haushalt.verbrauch_kw ?? 0).toFixed(2)} kW` : ''}
          </text>
        </g>

        {/* Energieumsatz unter Haus */}
        <text
          x={CX} y={CY + HAUS_R + 16}
          textAnchor="middle"
          style={{ fontSize: `${dims.socFontSize}px` }}
          className="fill-gray-500 dark:fill-gray-400"
        >
          Energieumsatz {Math.max(summeErzeugung, summeVerbrauch).toFixed(2)} kW
        </text>

        {/* Komponenten-Knoten */}
        {nodes.map(node => {
          const k = node.komp
          const kw = Math.max(k.erzeugung_kw ?? 0, k.verbrauch_kw ?? 0)
          const color = getColor(k.key)
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
          // Netz: Bezug + Einspeisung separat anzeigen
          if (k.key === 'netz') {
            const bezug = tagesWerte?.netz_bezug
            const einsp = tagesWerte?.netz_einspeisung
            if (bezug != null) tipParts.push(`Heute Bezug: ${bezug.toFixed(1)} kWh`)
            if (einsp != null) tipParts.push(`Heute Einspeisung: ${einsp.toFixed(1)} kWh`)
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

              {/* Knoten-Hintergrund */}
              <rect
                x={nx} y={ny}
                width={NODE_W} height={NODE_H}
                rx={NODE_R}
                className="fill-white dark:fill-gray-800"
                stroke={isActive ? color : '#9ca3af'}
                strokeWidth={isActive ? 1.5 : 1}
                strokeOpacity={isActive ? 0.8 : 0.4}
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
                {isActive ? `${kw.toFixed(2)} kW` : '0 kW'}
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
