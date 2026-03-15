/**
 * EnergieFluss — Animiertes Energiefluss-Diagramm (ersetzt EnergieBilanz).
 *
 * Zeigt alle Komponenten als Knoten um ein zentrales Haus-Symbol.
 * Animierte Linien zeigen Flussrichtung und -stärke.
 * Informationsparität mit EnergieBilanz: kW-Werte, Icons, Farben,
 * Tages-kWh Tooltips, Σ Erzeugung/Verbrauch.
 */

import { Sun, Zap, Battery, Car, Flame, Wrench, Home } from 'lucide-react'
import type { LiveKomponente, LiveGauge } from '../../api/liveDashboard'

// ─── Shared Utilities (aus EnergieBilanz) ───────────────────────────

const ICON_MAP: Record<string, React.ElementType> = {
  sun: Sun, zap: Zap, battery: Battery, car: Car,
  flame: Flame, wrench: Wrench, home: Home,
}

const COLOR_MAP: Record<string, string> = {
  pv: '#eab308',
  netz: '#ef4444',
  batterie: '#3b82f6',
  eauto: '#a855f7',
  waermepumpe: '#f97316',
  sonstige: '#6b7280',
  haushalt: '#10b981',
}

function getColor(key: string): string {
  if (COLOR_MAP[key]) return COLOR_MAP[key]
  const prefix = key.replace(/_\d+$/, '')
  return COLOR_MAP[prefix] || '#6b7280'
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
const CY = 210  // Festes Zentrum (unabhängig von Höhe)

// Knoten-Dimensionen
const NODE_W = 110
const NODE_H = 68
const NODE_R = 12
const HAUS_R = 46

/** Verteile n Items gleichmäßig auf einer Linie */
function distribute(n: number, minX: number, maxX: number): number[] {
  if (n === 0) return []
  if (n === 1) return [(minX + maxX) / 2]
  const step = (maxX - minX) / (n - 1)
  return Array.from({ length: n }, (_, i) => minX + i * step)
}

function layoutNodes(komponenten: LiveKomponente[]): NodePosition[] {
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

  const nodes: NodePosition[] = []

  // Oben: Erzeuger
  const ezXs = distribute(erzeuger.length, 140, 460)
  erzeuger.forEach((k, i) => nodes.push({ x: ezXs[i], y: 50, komp: k }))

  // Links: Netz
  netz.forEach(k => nodes.push({ x: 70, y: CY, komp: k }))

  // Rechts: Speicher
  const spXs = distribute(speicher.length, 510, 540)
  speicher.forEach((k, i) => nodes.push({ x: spXs[i], y: CY, komp: k }))

  // Unten: Verbraucher (ohne Kinder)
  const vrXs = distribute(verbraucher.length, 110, 490)
  verbraucher.forEach((k, i) => nodes.push({ x: vrXs[i], y: 370, komp: k }))

  // Kinder: direkt unter/neben ihrem Parent positionieren
  const parentPositions = new Map(nodes.map(n => [n.komp.key, n]))
  kinder.forEach(k => {
    const parent = parentPositions.get(k.parent_key!)
    if (parent) {
      // Kind 70px unter dem Parent, leicht versetzt
      const kinderOfParent = kinder.filter(c => c.parent_key === k.parent_key!)
      const idx = kinderOfParent.indexOf(k)
      const offsetX = (idx - (kinderOfParent.length - 1) / 2) * 120
      nodes.push({ x: parent.x + offsetX, y: parent.y + 65, komp: k })
    } else {
      // Fallback: als normaler Verbraucher unten
      nodes.push({ x: CX, y: 370, komp: k })
    }
  })

  return nodes
}

// ─── SVG Helpers ────────────────────────────────────────────────────

/** Quadratic Bezier Pfad von Knoten zu Zielpunkt */
function flowPath(nx: number, ny: number, tx: number = CX, ty: number = CY): string {
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

  const nodes = layoutNodes(komponenten)
  const nodeMap = new Map(nodes.map(n => [n.komp.key, n]))
  const haushalt = komponenten.find(k => k.key === 'haushalt')

  // Dynamische Höhe: Basis 420, erweitert wenn Knoten tiefer liegen
  const maxY = Math.max(...nodes.map(n => n.y), 370)
  const svgH = Math.max(420, maxY + NODE_H / 2 + 10)

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
          <foreignObject x={CX - 16} y={CY - 24} width={32} height={32}>
            <IconElement name="home" size={32} className="text-emerald-500" />
          </foreignObject>
          {/* Haushalt kW */}
          <text
            x={CX} y={CY + 22}
            textAnchor="middle"
            className="text-[13px] font-bold fill-gray-900 dark:fill-white"
          >
            {haushalt ? `${(haushalt.verbrauch_kw ?? 0).toFixed(2)} kW` : ''}
          </text>
        </g>

        {/* Summenzeile unter Haus */}
        <text
          x={CX} y={CY + HAUS_R + 18}
          textAnchor="middle"
          className="text-[11px] fill-gray-500 dark:fill-gray-400"
        >
          <tspan className="fill-green-600 dark:fill-green-400">
            ▲ {summeErzeugung.toFixed(2)}
          </tspan>
          <tspan> / </tspan>
          <tspan className="fill-red-600 dark:fill-red-400">
            ▼ {summeVerbrauch.toFixed(2)}
          </tspan>
          <tspan> kW</tspan>
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
          if (tagesKwh !== null) tipParts.push(`Heute: ${tagesKwh.toFixed(1)} kWh`)
          const tip = tipParts.join('\n')

          // Label kürzen
          const shortLabel = k.label.length > 16 ? k.label.slice(0, 14) + '…' : k.label

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
              <foreignObject x={node.x - 10} y={node.y - 28} width={20} height={20}>
                <IconElement name={k.icon} size={20} color={isActive ? color : '#9ca3af'} />
              </foreignObject>

              {/* kW-Wert */}
              <text
                x={node.x} y={node.y + 1}
                textAnchor="middle"
                className="text-[13px] font-bold fill-gray-900 dark:fill-white"
              >
                {isActive ? `${kw.toFixed(2)} kW` : '0 kW'}
              </text>

              {/* SoC-Anzeige */}
              {hasSoc && (
                <text
                  x={node.x} y={node.y + 16}
                  textAnchor="middle"
                  className="text-[11px] font-semibold"
                  fill={socColor(soc)}
                >
                  {soc}%
                </text>
              )}

              {/* Label */}
              <text
                x={node.x} y={node.y + (hasSoc ? 28 : 18)}
                textAnchor="middle"
                className="text-[10px] fill-gray-500 dark:fill-gray-400"
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
