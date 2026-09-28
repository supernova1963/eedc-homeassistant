/**
 * energieFlussLayout — die reine Layout-Logik des Energiefluss-Diagramms (kein JSX).
 *
 * Aus `EnergieFluss.tsx` herausgezogen (Bau A §A2, #341/#348), damit sie ohne
 * Render prüfbar ist — reiner Umzug, Signaturen und Verhalten unverändert.
 * Gruppierung, Maßstab und Faltung (§A3) kommen erst hier hinein.
 */

import type { LiveKomponente } from '../../api/liveDashboard'

export interface NodePosition {
  x: number
  y: number
  komp: LiveKomponente
}

// ─── Layout ─────────────────────────────────────────────────────────

export const W_DEFAULT = 600

/** Verteile n Items gleichmäßig auf einer Linie */
export function distribute(n: number, minX: number, maxX: number): number[] {
  if (n === 0) return []
  if (n === 1) return [(minX + maxX) / 2]
  const step = (maxX - minX) / (n - 1)
  return Array.from({ length: n }, (_, i) => minX + i * step)
}

/** Dynamische Dimensionen abhängig von der max. Anzahl Komponenten pro Zeile */
export interface LayoutDims {
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

export function computeDims(maxPerRow: number): LayoutDims {
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

export interface LayoutResult {
  nodes: NodePosition[]
  dims: LayoutDims
}

export function layoutNodes(komponenten: LiveKomponente[], W: number = W_DEFAULT): LayoutResult {
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
export function flowPath(nx: number, ny: number, tx: number, ty: number): string {
  const mx = (nx + tx) / 2
  const my = (ny + ty) / 2
  const dx = tx - nx
  const dy = ty - ny
  const len = Math.sqrt(dx * dx + dy * dy) || 1
  const perpX = -dy / len * 25
  const perpY = dx / len * 25
  return `M ${nx} ${ny} Q ${mx + perpX} ${my + perpY} ${tx} ${ty}`
}
