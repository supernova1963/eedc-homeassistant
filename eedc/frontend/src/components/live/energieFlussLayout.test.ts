/**
 * energieFlussLayout — der IST-Zustand der Layout-Logik, festgenagelt vor dem Umbau.
 *
 * Bau A §A2 (#341/#348): `layoutNodes` & Co. sind aus `EnergieFluss.tsx` in ein
 * reines Modul gezogen worden — reiner Umzug. Diese Proben halten fest, was das
 * Layout HEUTE tut, damit §A3 (Kaskaden, Maßstab, Faltung) gegen einen gemessenen
 * Ausgangspunkt baut.
 *
 * ⭐ **Der Regressionsanker aus #348:** neun PV-Strings auf der 600er-Zeichenfläche
 * stehen im Abstand **61,25** bei **80** Einheiten Kachelbreite — sie überlappen
 * sich um **18,75**. Nachgerechnet: `computeDims(9)` ⇒ `nodeW = 80`, Rand
 * `80/2 + 15 = 55`, `(600 − 2·55)/(9 − 1) = 490/8 = 61,25`, `80 − 61,25 = 18,75`.
 *
 * ⛔ **Keine Kapazitätsformel** (`kapazitaet(W, nodeW)`, „6 bei 600 / 3 bei 360") —
 * die ist A3-Soll, kein IST: das heutige Layout kennt keine Kapazität, es verteilt
 * jede Kachelzahl auf dieselbe Breite.
 */
import { describe, it, expect } from 'vitest'
import type { LiveKomponente } from '../../api/liveDashboard'
import { W_DEFAULT, computeDims, distribute, flowPath, layoutNodes } from './energieFlussLayout'

function k(key: string, extra: Partial<LiveKomponente> = {}): LiveKomponente {
  return { key, label: key, icon: 'sun', erzeugung_kw: 1, verbrauch_kw: null, ...extra }
}

function pvStrings(n: number): LiveKomponente[] {
  return Array.from({ length: n }, (_, i) => k(`pv_${i + 1}`))
}

describe('energieFlussLayout — IST vor §A3', () => {
  it('W_DEFAULT ist die 600er-Zeichenfläche', () => {
    expect(W_DEFAULT).toBe(600)
  })

  it('distribute: leer, mittig, gleichmäßig', () => {
    expect(distribute(0, 0, 100)).toEqual([])
    expect(distribute(1, 0, 100)).toEqual([50])
    expect(distribute(3, 0, 100)).toEqual([0, 50, 100])
  })

  it('computeDims: drei Größenstufen nach der längsten Reihe', () => {
    expect(computeDims(1).nodeW).toBe(100)
    expect(computeDims(3)).toMatchObject({ nodeW: 100, nodeH: 58, cy: 180, verbraucherY: 320, labelFontSize: 9 })
    expect(computeDims(4)).toMatchObject({ nodeW: 88, nodeH: 52, cy: 175, verbraucherY: 310, labelFontSize: 8.5 })
    expect(computeDims(5)).toMatchObject({ nodeW: 80, nodeH: 48, cy: 170, verbraucherY: 305, labelFontSize: 8.5 })
    expect(computeDims(9)).toEqual(computeDims(5))
  })

  it('#348-Anker: 9 Strings auf W=600 — Schritt 61,25, Überlappung 18,75', () => {
    const { nodes, dims } = layoutNodes(pvStrings(9), 600)
    const xs = nodes.filter(n => n.komp.key.startsWith('pv_')).map(n => n.x)
    expect(dims.nodeW).toBe(80)
    expect(xs).toHaveLength(9)
    expect(xs[0]).toBe(55)
    expect(xs[8]).toBe(545)
    const schritt = xs[1] - xs[0]
    expect(schritt).toBeCloseTo(61.25, 10)
    for (let i = 1; i < xs.length; i++) expect(xs[i] - xs[i - 1]).toBeCloseTo(61.25, 10)
    expect(dims.nodeW - schritt).toBeCloseTo(18.75, 10)
  })

  it('Erzeuger stehen oben (y = 50) in EINER Reihe über die volle Breite', () => {
    const { nodes, dims } = layoutNodes(pvStrings(4), 600)
    expect(nodes.every(n => n.y === 50)).toBe(true)
    const rand = dims.nodeW / 2 + 15
    expect(nodes.map(n => n.x)).toEqual(distribute(4, rand, 600 - rand))
  })

  it('Netz links auf Hausmitte, Speicher rechts um die Hausmitte gestapelt', () => {
    const { nodes, dims } = layoutNodes(
      [k('pv_1'), k('netz'), k('batterie_1'), k('batterie_2'), k('batterie_3')], 600,
    )
    const rand = dims.nodeW / 2 + 15
    const netz = nodes.find(n => n.komp.key === 'netz')!
    expect([netz.x, netz.y]).toEqual([rand, dims.cy])
    const sp = nodes.filter(n => n.komp.key.startsWith('batterie_'))
    expect(sp.map(n => n.x)).toEqual([600 - rand, 600 - rand, 600 - rand])
    expect(sp.map(n => n.y)).toEqual([dims.cy - (dims.nodeH + 10), dims.cy, dims.cy + (dims.nodeH + 10)])
  })

  it('Verbraucher unten; ein Kind (parent_key) direkt hinter seinem Parent; Haushalt ohne Knoten', () => {
    const { nodes, dims } = layoutNodes([
      k('wallbox_6', { verbrauch_kw: 7, erzeugung_kw: null }),
      k('waermepumpe_5', { verbrauch_kw: 2, erzeugung_kw: null }),
      k('eauto_4', { verbrauch_kw: 7, erzeugung_kw: null, parent_key: 'wallbox_6' }),
      k('haushalt', { verbrauch_kw: 1, erzeugung_kw: null }),
    ], 600)
    const unten = nodes.filter(n => n.y === dims.verbraucherY).map(n => n.komp.key)
    expect(unten).toEqual(['wallbox_6', 'eauto_4', 'waermepumpe_5'])
    expect(nodes.some(n => n.komp.key === 'haushalt')).toBe(false)
  })

  it('ein Kind ohne passenden Parent hängt am Ende der unteren Reihe', () => {
    const { nodes, dims } = layoutNodes([
      k('eauto_4', { verbrauch_kw: 3, erzeugung_kw: null, parent_key: 'wallbox_99' }),
      k('waermepumpe_5', { verbrauch_kw: 2, erzeugung_kw: null }),
    ], 600)
    expect(nodes.filter(n => n.y === dims.verbraucherY).map(n => n.komp.key))
      .toEqual(['waermepumpe_5', 'eauto_4'])
  })

  it('die Größenstufe hängt an der längeren der beiden Reihen (Kinder zählen mit)', () => {
    const unten = [
      k('wallbox_1', { parent_key: null }), k('eauto_2', { parent_key: 'wallbox_1' }),
      k('waermepumpe_3'), k('sonstige_4'),
    ]
    expect(layoutNodes([k('pv_1'), ...unten], 600).dims.nodeW).toBe(88)
  })

  it('flowPath: quadratischer Bézier mit 25 Einheiten Beule, senkrecht zur Linie', () => {
    expect(flowPath(0, 0, 100, 0)).toBe('M 0 0 Q 50 25 100 0')
    expect(flowPath(0, 0, 0, 100)).toBe('M 0 0 Q -25 50 0 100')
    // Länge 0: kein NaN (Nenner fällt auf 1).
    expect(flowPath(10, 10, 10, 10)).toBe('M 10 10 Q 10 10 10 10')
  })
})
