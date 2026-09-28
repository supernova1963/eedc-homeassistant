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
import type { LiveFahrzeug, LiveGauge, LiveKomponente } from '../../api/liveDashboard'
import { KATEGORIE_FARBEN } from '../../lib/colors'
import {
  W_DEFAULT, computeDims, distribute, flowPath, layoutNodes,
  type BuehnenMass, type EnergieFlussLayout, type GezeichneterKnoten, type LayoutEingaben,
  kapazitaet, klassifiziere, layoutEnergieFluss, sonstigesZweig, ueberlappungsfrei, wBedarf, waehleStufen,
  wallboxKachelAuto,
} from './energieFlussLayout'

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

// ═══════════════════════════════════════════════════════════════════
// §A3 — Eine Reihe je Zone: Kaskaden, Maßstab, Faltung (#341/#348)
// ═══════════════════════════════════════════════════════════════════
//
// Bestände wie im Muster (`energiefluss-szene.v5.html`, FAELLE A/M/D) und in
// der Plan-Tabelle „Durchgerechnet" (A–E), dazu die vier Zusatzbestände der
// Vorlage (Ü6). Die Erwartungswerte sind von Hand nachgerechnet (Kommentar am
// jeweiligen Fall); die Proben rechnen sie nicht aus dem Code nach.

type Bestand = { komp: LiveKomponente[]; gauges: LiveGauge[]; tages?: Record<string, number | null> }

function knoten(key: string, extra: Partial<LiveKomponente>): LiveKomponente {
  return { key, label: key, icon: 'wrench', erzeugung_kw: null, verbrauch_kw: null, ...extra }
}
const pvS = (id: number, label: string, ausr: string | null, kw: number, kwp: number | null, extra: Partial<LiveKomponente> = {}) =>
  knoten(`pv_${id}`, { label, icon: 'sun', erzeugung_kw: kw, typ: 'pv-module', ausrichtung_label: ausr, leistung_kwp: kwp, ...extra })
/** kw > 0 lädt (Verbrauch), kw < 0 entlädt (Erzeugung) — wie der Builder. */
const spS = (id: number, label: string, kw: number, kap: number | null) =>
  knoten(`batterie_${id}`, {
    label, icon: 'battery', typ: 'speicher', kapazitaet_kwh: kap,
    erzeugung_kw: kw < 0 ? -kw : null, verbrauch_kw: kw >= 0 ? kw : null,
  })
const wpS = (id: number, label: string, kw: number) =>
  knoten(`waermepumpe_${id}`, { label, icon: 'flame', typ: 'waermepumpe', verbrauch_kw: kw })
const wbS = (id: number, label: string, kw: number, fahrzeuge?: LiveFahrzeug[], zuordnung?: 'eindeutig' | 'geschaetzt') =>
  knoten(`wallbox_${id}`, {
    label, icon: 'plug', typ: 'wallbox', verbrauch_kw: kw,
    ...(fahrzeuge ? { fahrzeuge, fahrzeuge_zuordnung: zuordnung } : {}),
  })
const soS = (id: number, label: string, kw: number, kat: string | null) =>
  knoten(`sonstige_${id}`, {
    label, typ: 'sonstiges', kategorie: kat,
    ...(kat === 'erzeuger' ? { erzeugung_kw: kw } : { verbrauch_kw: kw }),
  })
const autoK = (id: number, label: string, kw: number, parent: string | null) =>
  knoten(`eauto_${id}`, { label, icon: 'car', typ: 'e-auto', verbrauch_kw: kw, parent_key: parent })
const fz = (id: number, label: string, soc: number | null, kw: number | null): LiveFahrzeug =>
  ({ investition_id: id, label, soc, kw, v2h: false })
const soc = (id: number, wert: number): LiveGauge =>
  ({ key: `soc_${id}`, label: `soc ${id}`, wert, min_wert: 0, max_wert: 100, einheit: '%' })
const NETZ = knoten('netz', { label: 'Stromnetz', icon: 'zap', erzeugung_kw: 1 })
const HAUS = knoten('haushalt', { label: 'Haushalt', icon: 'home', verbrauch_kw: 0.6 })

/** A · Standard: 1 String, 1 Speicher, WP, Wallbox mit ID.4 (Knoten-Auto als Kind). */
function bestandA(): Bestand {
  return {
    komp: [
      pvS(1, 'Dach Süd', 'Süd', 6.2, 9.8), spS(2, 'Speicher', 1.8, 10), wpS(3, 'Wärmepumpe', 1.1),
      wbS(4, 'Wallbox', 3.7, [fz(5, 'ID.4', 52, 3.7)], 'eindeutig'), autoK(5, 'ID.4', 3.7, 'wallbox_4'), NETZ, HAUS,
    ],
    gauges: [soc(2, 64), soc(5, 52)],
  }
}

/** M · Mittel: 8 Strings (Süd 4 · Ost 2 · West 2), 3 Speicher, WP, Wallbox mit ID.4, Poolpumpe. */
function bestandM(): Bestand {
  return {
    komp: [
      pvS(71, 'Süd 1', 'Süd', 1.6, 2.8), pvS(72, 'Süd 2', 'Süd', 1.5, 2.8), pvS(73, 'Süd 3', 'Süd', 1.4, 2.8),
      pvS(74, 'Süd Gaube', 'Süd', 0.8, 1.4), pvS(75, 'Ost 1', 'Ost', 0.5, 2.0), pvS(76, 'Ost 2', 'Ost', 0.4, 2.0),
      pvS(77, 'West 1', 'West', 1.1, 2.2), pvS(78, 'West 2', 'West', 1.0, 2.2),
      spS(81, 'BYD HVS', 1.5, 10.2), spS(82, 'Pylontech', 0.9, 7.1), spS(83, 'Zendure', -0.3, 1.9),
      wpS(84, 'Wärmepumpe', 1.2), wbS(85, 'Wallbox', 3.7, [fz(88, 'ID.4', 58, 3.7)], 'eindeutig'),
      autoK(88, 'ID.4', 3.7, 'wallbox_85'), soS(86, 'Poolpumpe', 0.6, 'verbraucher'), NETZ, HAUS,
    ],
    gauges: [soc(81, 62), soc(82, 48), soc(83, 27), soc(88, 58)],
  }
}

/**
 * D · Groß: 9 Strings (Süd 5 · Ost 2 · West 2), 4 Speicher, WP, 2 Wallboxen mit
 * 3 Autos (ID.4 an 41, Zoe an 42, Enyaq nur Ladestand — reihum nach ID wie der
 * Builder: 51→41, 52→42, 53→41), Poolpumpe, Sauna, Mini-BHKW.
 */
function bestandD(): Bestand {
  const autos41 = [fz(51, 'ID.4', 64, 7.4), fz(53, 'Enyaq', 81, null)]
  const autos42 = [fz(52, 'Zoe', 38, 3.6)]
  return {
    komp: [
      pvS(11, 'Süd 1', 'Süd', 1.9, 3.2), pvS(12, 'Süd 2', 'Süd', 1.8, 3.2), pvS(13, 'Süd 3', 'Süd', 1.7, 3.2),
      pvS(14, 'Süd Garage', 'Süd', 1.2, 2.1), pvS(15, 'Süd Gaube', 'Süd', 0.9, 1.6), pvS(16, 'Ost 1', 'Ost', 0.6, 2.4),
      pvS(17, 'Ost 2', 'Ost', 0.5, 2.4), pvS(18, 'West 1', 'West', 1.4, 2.8), pvS(19, 'West 2', 'West', 1.3, 2.8),
      spS(21, 'BYD HVS', 1.2, 10.2), spS(22, 'Pylontech', 0.8, 7.1), spS(23, 'Zendure', -0.6, 1.9), spS(24, 'Sonnen', 0.4, 10),
      wpS(31, 'Wärmepumpe', 1.4), wbS(41, 'Wallbox Garage', 7.4, autos41, 'geschaetzt'), wbS(42, 'Wallbox Carport', 3.6, autos42, 'geschaetzt'),
      autoK(51, 'ID.4', 7.4, 'wallbox_41'), autoK(52, 'Zoe', 3.6, 'wallbox_42'),
      soS(61, 'Poolpumpe', 0.8, 'verbraucher'), soS(62, 'Sauna', 0, 'verbraucher'), soS(63, 'Mini-BHKW', 1.0, 'erzeuger'),
      knoten('netz', { label: 'Stromnetz', icon: 'zap', erzeugung_kw: 3.4 }), HAUS,
    ],
    gauges: [soc(21, 71), soc(22, 58), soc(23, 33), soc(24, 90), soc(51, 64), soc(52, 38), soc(53, 81)],
  }
}

/** B · 5 Strings (Ost 1 · Süd 3 · West 1), 2 Speicher, WP + Klima. */
function bestandB(): Bestand {
  return {
    komp: [
      pvS(1, 'Ost', 'Ost', 0.8, 2), pvS(2, 'Süd 1', 'Süd', 1.5, 3), pvS(3, 'Süd 2', 'Süd', 1.4, 3),
      pvS(4, 'Süd 3', 'Süd', 1.3, 3), pvS(5, 'West', 'West', 0.9, 2),
      spS(6, 'Speicher 1', 0.5, 5), spS(7, 'Speicher 2', -0.3, 5), wpS(8, 'Wärmepumpe', 1.1), wpS(9, 'Klima', 0.7),
      NETZ, HAUS,
    ],
    gauges: [soc(6, 50), soc(7, 70)],
  }
}

/** (a) `pv_gesamt`-Fallback — Summensensor + Speicher + WP, der häufigste einfache Aufbau. */
function bestandPvGesamt(): Bestand {
  return {
    komp: [
      knoten('pv_gesamt', { label: 'PV Gesamt 9.8 kWp', icon: 'sun', erzeugung_kw: 4.2 }),
      spS(2, 'Speicher', 1.0, 10), wpS(3, 'Wärmepumpe', 1.4), NETZ, HAUS,
    ],
    gauges: [soc(2, 40)],
  }
}

/** (b) Bestand ohne PV. */
function bestandOhnePv(): Bestand {
  return {
    komp: [spS(2, 'Speicher', -1.0, 10), wpS(3, 'Wärmepumpe', 1.4), wbS(4, 'Wallbox', 0, [], 'eindeutig'), NETZ, HAUS],
    gauges: [soc(2, 40)],
  }
}

/** (c) ≥ 2 E-Autos ohne Wallbox (Steckerlader, eigene Kacheln) + WP + Sonstige. */
function bestandAutosOhneWallbox(): Bestand {
  return {
    komp: [
      pvS(1, 'Dach', 'Süd', 3, 5), autoK(11, 'Auto 1', 2.3, null), autoK(12, 'Auto 2', 1.1, null),
      autoK(13, 'Auto 3', 0, null), autoK(14, 'Auto 4', 3.6, null), wpS(15, 'Wärmepumpe', 0.9),
      soS(16, 'Pool', 0.4, 'verbraucher'), NETZ, HAUS,
    ],
    gauges: [soc(11, 50), soc(12, 60), soc(13, 70), soc(14, 80)],
  }
}

/**
 * (d) Erschöpfung: sieben Verbraucherklassen je einmal — nichts lässt sich
 * bündeln. ⚠ Datenbestand, kein Builder-Bestand: ein `eauto_`-Knoten ohne
 * `parent_key` NEBEN einer live liefernden Wallbox baut der Builder nicht
 * (`live_komponenten_builder.py`, Zuordnungsblock) — die Probe hält nur fest,
 * dass die Schleife auch dann terminiert und zoomt statt zu überlappen.
 */
function bestandErschoepft(): Bestand {
  return {
    komp: [
      pvS(1, 'Dach', 'Süd', 3, 5), wpS(2, 'Wärmepumpe', 1), wbS(3, 'Wallbox', 2, [], 'eindeutig'),
      autoK(4, 'Steckerlader', 1.5, null), soS(5, 'Pool', 0.4, 'verbraucher'), soS(6, 'Nachbar', 0.5, 'abgabe'),
      soS(7, 'BHKW', 1.2, 'erzeuger'), knoten('sonstige_8', { label: 'Akku alt', typ: 'sonstiges', kategorie: 'speicher', erzeugung_kw: 0.3 }),
      NETZ, HAUS,
    ],
    gauges: [],
  }
}

/** Groß-Bestand für das Raster: 12 Strings (vier Richtungen + ohne), 6 Speicher, 3 WP, 3 Wallboxen, 5 Sonstige. */
function bestandGross(): Bestand {
  const richtungen = ['Ost', 'Süd', 'West', 'Nord', null]
  return {
    komp: [
      ...Array.from({ length: 12 }, (_, i) => pvS(100 + i, `String ${i + 1}`, richtungen[i % 5], 0.5 + i / 10, i === 7 ? null : 2)),
      ...Array.from({ length: 6 }, (_, i) => spS(200 + i, `Akku ${i + 1}`, i % 2 ? -0.5 : 0.7, 5)),
      wpS(301, 'WP 1', 1), wpS(302, 'WP 2', 0.4), wpS(303, 'Klima', 0.2),
      wbS(311, 'WB 1', 3, [fz(321, 'Auto A', 30, 3)], 'geschaetzt'), wbS(312, 'WB 2', 0, [fz(322, 'Auto B', 60, null)], 'geschaetzt'),
      wbS(313, 'WB 3', 11, [], 'geschaetzt'), autoK(321, 'Auto A', 3, 'wallbox_311'),
      soS(331, 'Pool', 0.4, 'verbraucher'), soS(332, 'Sauna', 3, 'zaehler'), soS(333, 'BHKW 1', 1, 'erzeuger'),
      soS(334, 'BHKW 2', 0.8, 'erzeuger'), soS(335, 'Nachbar', 0.2, 'abgabe'), NETZ, HAUS,
    ],
    gauges: Array.from({ length: 6 }, (_, i) => soc(200 + i, 20 + 10 * i)),
  }
}

/** BKW-Rest + seine Module + ein Wechselrichter, ohne Ausrichtung (nur die Träger-Stufe trennt). */
function bestandBkw(): Bestand {
  return {
    komp: [
      pvS(30, 'Balkon', null, 0.2, 0.8, { typ: 'balkonkraftwerk', traeger_id: 30 }),
      pvS(31, 'Balkon links', null, 0.3, 0.4, { traeger_id: 30 }), pvS(32, 'Balkon rechts', null, 0.3, 0.4, { traeger_id: 30 }),
      pvS(40, 'Dach 1', null, 1, 3, { traeger_id: 44 }), pvS(41, 'Dach 2', null, 1, 3, { traeger_id: 44 }),
      pvS(42, 'Dach 3', null, 1, 3, { traeger_id: 44 }), pvS(43, 'Dach 4', null, 1, 3, { traeger_id: 44 }),
      wpS(50, 'Wärmepumpe', 1), NETZ, HAUS,
    ],
    gauges: [],
  }
}

const BESTAENDE: Record<string, () => Bestand> = {
  A: bestandA, M: bestandM, D: bestandD, B: bestandB, pvGesamt: bestandPvGesamt, ohnePv: bestandOhnePv,
  autosOhneWallbox: bestandAutosOhneWallbox, erschoepft: bestandErschoepft, gross: bestandGross, bkw: bestandBkw,
}
const BREITEN = [320, 360, 374, 375, 420, 450, 499, 500, 600, 700, 800, 1000, 1064, 1065, 1150, 1194, 1195, 1400, 1850]
const VOLLBILD: BuehnenMass[] = [
  { breitePx: 1850, vollbild: { hoehePx: 900 } }, { breitePx: 1200, vollbild: { hoehePx: 900 } },
  { breitePx: 800, vollbild: { hoehePx: 1100 } }, { breitePx: 1000, vollbild: { hoehePx: 350 } },
]
const MASSE: BuehnenMass[] = [...BREITEN.map(b => ({ breitePx: b })), ...VOLLBILD]

function lay(b: Bestand, mass: BuehnenMass | number): EnergieFlussLayout {
  const eingaben: LayoutEingaben = { gauges: b.gauges, tagesWerte: b.tages }
  return layoutEnergieFluss(b.komp, typeof mass === 'number' ? { breitePx: mass } : mass, eingaben)
}
const zone = (l: EnergieFlussLayout, z: GezeichneterKnoten['zone']) => l.nodes.filter(n => n.zone === z)
const keys = (ns: GezeichneterKnoten[]) => ns.map(n => n.komp.key)
const labels = (ns: GezeichneterKnoten[]) => ns.map(n => n.komp.label)
const alleLayouts = () => Object.entries(BESTAENDE).flatMap(([name, f]) =>
  MASSE.map(m => ({ name: `${name}@${m.breitePx}${m.vollbild ? `x${m.vollbild.hoehePx}` : ''}`, l: lay(f(), m) })))

describe('§A3 Klassifikation — Key-Präfix zuerst, typ/kategorie verfeinern', () => {
  it('Zonen über das Präfix', () => {
    expect(klassifiziere(knoten('pv_7', {})).zone).toBe('oben')
    expect(klassifiziere(knoten('pv_gesamt', {})).zone).toBe('oben')
    expect(klassifiziere(knoten('batterie_3', {})).zone).toBe('rechts')
    expect(klassifiziere(knoten('netz', {})).zone).toBe('links')
    expect(klassifiziere(knoten('haushalt', {})).zone).toBeNull()
    for (const k of ['eauto_4', 'wallbox_6', 'waermepumpe_5', 'sonstige_9']) expect(klassifiziere(knoten(k, {})).zone).toBe('unten')
    // Ein sonstiger Speicher bleibt unten (Präfix `sonstige_`), die Speicherspalte gehört `batterie_`.
    expect(klassifiziere(knoten('sonstige_9', { kategorie: 'speicher' })).zone).toBe('unten')
  })

  it('typ verfeinert PV (BKW sortiert nach den Modulen), das Präfix bleibt Zone und Klasse', () => {
    expect(klassifiziere(knoten('pv_7', { typ: 'balkonkraftwerk' }))).toEqual({ zone: 'oben', typ: 'balkonkraftwerk', klasse: 'pv' })
    expect(klassifiziere(knoten('pv_7', {}))).toEqual({ zone: 'oben', typ: 'pv-module', klasse: 'pv' })
  })

  it('Sonstiges: Buchungszweig aus der Kategorie, `zaehler` und fehlend bei den Verbrauchern', () => {
    expect(sonstigesZweig(knoten('sonstige_1', { kategorie: 'erzeuger' }))).toBe('erzeuger')
    expect(sonstigesZweig(knoten('sonstige_1', { kategorie: 'abgabe' }))).toBe('abgabe')
    expect(sonstigesZweig(knoten('sonstige_1', { kategorie: 'speicher' }))).toBe('speicher')
    expect(sonstigesZweig(knoten('sonstige_1', { kategorie: 'verbraucher' }))).toBe('verbraucher')
    expect(sonstigesZweig(knoten('sonstige_1', { kategorie: 'zaehler', verbrauch_kw: 1 }))).toBe('verbraucher')
    // fehlt die Kategorie, entscheidet die Seite (altes Backend; neues Backend: Verbraucher-Zweig)
    expect(sonstigesZweig(knoten('sonstige_1', { kategorie: null, verbrauch_kw: 1 }))).toBe('verbraucher')
    expect(sonstigesZweig(knoten('sonstige_1', { verbrauch_kw: 0.2 }))).toBe('verbraucher')
    expect(sonstigesZweig(knoten('sonstige_1', { erzeugung_kw: 0 }))).toBe('erzeuger')
    expect(sonstigesZweig(knoten('sonstige_1', { kategorie: '', erzeugung_kw: 1.5 }))).toBe('erzeuger')
  })

  it('`zaehler` und fehlende Kategorie bündeln mit den Verbrauchern, der BHKW nicht', () => {
    const b: Bestand = {
      komp: [
        pvS(1, 'Dach', 'Süd', 3, 5), wpS(2, 'WP', 1),
        soS(3, 'Wasserzähler', 0.1, 'zaehler'), knoten('sonstige_4', { label: 'Alt', typ: 'sonstiges', verbrauch_kw: 0.2 }),
        soS(5, 'Pool', 0.4, 'verbraucher'), soS(6, 'BHKW', 1.1, 'erzeuger'), NETZ, HAUS,
      ],
      gauges: [],
    }
    const unten = zone(lay(b, 360), 'unten')
    const grp = unten.find(n => n.komp.key === 'sonstige_grp_verbraucher')!
    expect(keys(unten)).toEqual(['waermepumpe_2', 'sonstige_grp_verbraucher', 'sonstige_6'])
    expect(grp.mitglieder!.map(m => m.key)).toEqual(['sonstige_3', 'sonstige_4', 'sonstige_5'])
  })
})

describe('§A3 Maßstab — Kapazität, Breitenbedarf, Zirkel-Auflösung', () => {
  it('kapazitaet: 3 bei 360, 4 bei 450, 6 bei 600', () => {
    expect(kapazitaet(360, 80)).toBe(3)
    expect(kapazitaet(360, 100)).toBe(3)
    expect(kapazitaet(450, 80)).toBe(4)
    expect(kapazitaet(450, 88)).toBe(4)
    expect(kapazitaet(600, 80)).toBe(6)
  })

  it('wBedarf = nodeW + 30 + (n−1)·(nodeW+12) — 662 · 754 · 846 für 7 · 8 · 9 Kacheln à 80', () => {
    expect(wBedarf(6, 80)).toBe(570)
    expect(wBedarf(7, 80)).toBe(662)
    expect(wBedarf(8, 80)).toBe(754)
    expect(wBedarf(9, 80)).toBe(846)
  })

  // Muster-Erwartungswerte, von Hand: einzeln passt, sobald 8,5 · Karte / wBedarf ≥ 12,
  // also M (8) ab 12·754/8,5 = 1064,47 px, D (9) ab 12·846/8,5 = 1194,35 px.
  it('M: 8 Strings einzeln ab 1065 px (Muster-Raster: ab 1070), darunter nach Ausrichtung', () => {
    expect(waehleStufen([8, 3, 1], [3], { breitePx: 1064 }).iP).toBe(1)
    expect(waehleStufen([8, 3, 1], [3], { breitePx: 1065 }).iP).toBe(0)
    expect(waehleStufen([8, 3, 1], [3], { breitePx: 1060 }).iP).toBe(1)
    expect(waehleStufen([8, 3, 1], [3], { breitePx: 1070 }).iP).toBe(0)
  })

  it('D: 9 Strings einzeln ab 1195 px (Muster-Raster: ab 1200)', () => {
    expect(waehleStufen([9, 3, 1], [6], { breitePx: 1194 }).iP).toBe(1)
    expect(waehleStufen([9, 3, 1], [6], { breitePx: 1195 }).iP).toBe(0)
    expect(waehleStufen([9, 3, 1], [6], { breitePx: 1190 }).iP).toBe(1)
    expect(waehleStufen([9, 3, 1], [6], { breitePx: 1200 }).iP).toBe(0)
  })

  it('Full HD (1150 px) fasst 8 Kacheln, 9 nicht (9 einzeln bräuchten 11,6 px)', () => {
    const acht = waehleStufen([8, 1], [1], { breitePx: 1150 })
    expect(acht.iP).toBe(0)
    expect(acht.schriftPx).toBeCloseTo(8.5 * 1150 / 754, 10)
    const neun = waehleStufen([9, 1], [1], { breitePx: 1150 })
    expect(neun.iP).toBe(1)
    expect(8.5 * 1150 / 846).toBeCloseTo(11.55, 2)
  })

  it('D bei 1150 px ⇒ Ausrichtungs-Stufe, k = 1, 16 px', () => {
    const l = lay(bestandD(), 1150)
    expect(l.stufen.oben.name).toBe('ausrichtung')
    expect(l.k).toBe(1)
    expect([l.W, l.H]).toEqual([600, 380])
    expect(Math.round(l.schriftPx)).toBe(16)
    expect(l.schriftPx).toBeCloseTo(8.5 * 1150 / 600, 10)
  })

  it('k = 1 für A und D bei 1150 px', () => {
    expect(lay(bestandA(), 1150).k).toBe(1)
    expect(lay(bestandD(), 1150).k).toBe(1)
  })

  it('ab 500 px: Höhe = Breite × 380/600 (die Karte wird nie höher); Handy: 360/450 × 380, kein Zoom', () => {
    for (const [name, f] of Object.entries(BESTAENDE)) {
      for (const b of BREITEN) {
        const l = lay(f(), b)
        if (b >= 500) {
          expect(b * l.H / l.W, `${name}@${b}`).toBeCloseTo(b * 380 / 600, 9)
          expect(l.W / l.k, `${name}@${b}`).toBeCloseTo(600, 9)
        } else {
          expect([l.W, l.H, l.k], `${name}@${b}`).toEqual([b < 375 ? 360 : 450, 380, 1])
        }
      }
    }
  })

  it('Inhalt senkrecht mittig: alle y-Anker um (H − 380)/2 verschoben', () => {
    const l = lay(bestandM(), 1150) // 8 einzeln ⇒ k = 754/600
    expect(l.k).toBeCloseTo(754 / 600, 10)
    const yOff = (l.H - 380) / 2
    expect(zone(l, 'oben')[0].y).toBeCloseTo(50 + yOff, 9)
    expect(l.CY).toBeCloseTo(170 + yOff, 9)
    expect(zone(l, 'unten')[0].y).toBeCloseTo(305 + yOff, 9)
    expect(l.CX).toBeCloseTo(l.W / 2, 9)
  })

  it('Vollbild: Höhe bleibt 380·k, die Breite nimmt das Overlay-Verhältnis an; Schrift über die Höhe', () => {
    for (const m of VOLLBILD) {
      for (const [name, f] of Object.entries(BESTAENDE)) {
        const l = lay(f(), m)
        const r = m.breitePx / m.vollbild!.hoehePx
        expect(l.H, `${name}`).toBeCloseTo(380 * l.k, 9)
        expect(l.W / l.H, `${name}`).toBeCloseTo(r, 9)
        expect(l.W, `${name}`).toBeGreaterThanOrEqual(600 - 1e-9)
        expect(l.schriftPx, `${name}`).toBeCloseTo(l.dims.labelFontSize * m.vollbild!.hoehePx / l.H, 9)
        // die Verbraucherreihe bleibt im Bild
        expect(l.dims.verbraucherY + l.dims.nodeH / 2, `${name}`).toBeLessThanOrEqual(l.H)
      }
    }
  })

  it('Mindestschrift: nie unterschritten, solange eine Kaskadenstufe frei ist', () => {
    for (const { name, l } of alleLayouts()) {
      if (l.mindestSchriftPx == null) continue
      if (l.schriftPx < l.mindestSchriftPx - 1e-9) {
        expect(l.stufen.oben.index, name).toBe(l.stufen.oben.anzahl - 1)
        expect(l.stufen.unten.index, name).toBe(l.stufen.unten.anzahl - 1)
      }
    }
  })

  it('unten schrittweise: bei Gleichstand bündelt zuerst der Typ, der in INVESTITION_TYP_ORDER vorn steht', () => {
    // D + zweite WP bei 800 px: sieben Kacheln (662 > 600 ⇒ 10,3 px < 11,3 px) — WP, Wallbox
    // und Sonstige haben je zwei; eine Stufe genügt, und sie trifft die Wärmepumpen.
    const b = bestandD()
    b.komp = [...b.komp, wpS(32, 'Klima', 0.6)]
    const l = lay(b, 800)
    expect(keys(zone(l, 'unten'))).toEqual(['waermepumpe_grp', 'wallbox_41', 'wallbox_42', 'sonstige_61', 'sonstige_62', 'sonstige_63'])
    expect(l.stufen.unten.index).toBe(1)
  })

  it('Mindestschrift = min(12 px, heutige Schrift) — der Laptop gruppiert nicht sofort', () => {
    // D bei 800 px: unten 6 Kacheln à 80 brauchen 570 ≤ 600 ⇒ k = 1, Schrift 8,5 · 800/600 = 11,33 px.
    // Mit der festen Grenze 12 px würden die sechs sofort gebündelt; mit min(12, heute) nicht.
    const l = lay(bestandD(), 800)
    expect(l.k).toBe(1)
    expect(l.schriftPx).toBeCloseTo(8.5 * 800 / 600, 9)
    expect(l.mindestSchriftPx).toBeCloseTo(8.5 * 800 / 600, 9)
    expect(l.stufen.unten.index).toBe(0)
    expect(zone(l, 'unten')).toHaveLength(6)
  })
})

describe('§A3 Tabelle „Durchgerechnet" A–E', () => {
  it('A · Full HD: k = 1; unten 2 statt 3 Kacheln, die Wallbox trägt „ID.4 52 %" als Füllstand', () => {
    const l = lay(bestandA(), 1150)
    expect(l.k).toBe(1)
    expect(keys(zone(l, 'oben'))).toEqual(['pv_1'])
    expect(keys(zone(l, 'unten'))).toEqual(['waermepumpe_3', 'wallbox_4'])
    expect(keys(zone(l, 'rechts'))).toEqual(['batterie_2'])
    const wb = zone(l, 'unten')[1]
    expect(wb.kachelAuto).toEqual({ art: 'auto', auto: fz(5, 'ID.4', 52, 3.7) })
    expect(wb.ladestand).toBe(52)
  })

  it('D · Full HD: PV Ost (2) · Süd (5) · West (2); unten 6 einzeln; Speicher (4); k = 1', () => {
    const l = lay(bestandD(), 1150)
    const oben = zone(l, 'oben')
    expect(keys(oben)).toEqual(['pv_grp_ost', 'pv_grp_sued', 'pv_grp_west'])
    expect(labels(oben)).toEqual(['Ost', 'Süd', 'West'])
    expect(oben.map(n => n.mitglieder!.length)).toEqual([2, 5, 2])
    expect(keys(zone(l, 'unten'))).toEqual(['waermepumpe_31', 'wallbox_41', 'wallbox_42', 'sonstige_61', 'sonstige_62', 'sonstige_63'])
    const rechts = zone(l, 'rechts')
    expect(keys(rechts)).toEqual(['batterie_grp'])
    expect(rechts[0].mitglieder!.length).toBe(4)
    expect(l.stufen.speicherGruppiert).toBe(true)
  })

  it('C · Handy 360 (Bestand D): Laden (2) · Weitere (WP, Pool, Sauna) · Mini-BHKW; Speicher (4)', () => {
    const l = lay(bestandD(), 360)
    expect(labels(zone(l, 'oben'))).toEqual(['Ost', 'Süd', 'West'])
    const unten = zone(l, 'unten')
    expect(keys(unten)).toEqual(['wallbox_grp', 'sonstige_grp_weitere', 'sonstige_63'])
    expect(labels(unten)).toEqual(['Laden', 'Weitere', 'Mini-BHKW'])
    expect(unten[1].mitglieder!.map(m => m.key)).toEqual(['waermepumpe_31', 'sonstige_61', 'sonstige_62'])
    expect(keys(zone(l, 'rechts'))).toEqual(['batterie_grp'])
  })

  it('E · HA-Karte 420 (Bestand D): WP · Laden (2) · Sonstige (2) · Mini-BHKW; Speicher (4)', () => {
    const l = lay(bestandD(), 420)
    expect(l.W).toBe(450)
    expect(labels(zone(l, 'oben'))).toEqual(['Ost', 'Süd', 'West'])
    expect(keys(zone(l, 'unten'))).toEqual(['waermepumpe_31', 'wallbox_grp', 'sonstige_grp_verbraucher', 'sonstige_63'])
    expect(labels(zone(l, 'unten'))).toEqual(['Wärmepumpe', 'Laden', 'Sonstige', 'Mini-BHKW'])
    expect(keys(zone(l, 'rechts'))).toEqual(['batterie_grp'])
  })

  it('B · Handy 360: PV Ost · Süd (3) · West; unten 2 Kacheln; 2 Speicher einzeln', () => {
    const l = lay(bestandB(), 360)
    expect(keys(zone(l, 'oben'))).toEqual(['pv_1', 'pv_grp_sued', 'pv_5'])
    expect(zone(l, 'oben')[1].mitglieder!.length).toBe(3)
    expect(keys(zone(l, 'unten'))).toEqual(['waermepumpe_8', 'waermepumpe_9'])
    expect(keys(zone(l, 'rechts'))).toEqual(['batterie_6', 'batterie_7'])
  })

  it('M · Full HD fasst 8 Strings einzeln und 3 Speicher übereinander; bei 1060 px nach Ausrichtung', () => {
    const l = lay(bestandM(), 1150)
    expect(zone(l, 'oben')).toHaveLength(8)
    expect(keys(zone(l, 'rechts'))).toEqual(['batterie_81', 'batterie_82', 'batterie_83'])
    expect(labels(zone(lay(bestandM(), 1060), 'oben'))).toEqual(['Ost', 'Süd', 'West'])
  })
})

describe('§A3 Zusatzbestände (Ü6)', () => {
  it('(a) `pv_gesamt`-Fallback: PV-Zone per Präfix, nie gruppiert', () => {
    for (const m of MASSE) {
      const l = lay(bestandPvGesamt(), m)
      expect(keys(zone(l, 'oben'))).toEqual(['pv_gesamt'])
      expect(zone(l, 'oben')[0].mitglieder).toBeUndefined()
      expect(l.stufen.oben.anzahl).toBe(1)
    }
  })

  it('(b) ohne PV: die obere Reihe bleibt leer, der Rest steht wie immer', () => {
    const l = lay(bestandOhnePv(), 1150)
    expect(zone(l, 'oben')).toEqual([])
    expect(l.k).toBe(1)
    expect(keys(zone(l, 'unten'))).toEqual(['waermepumpe_3', 'wallbox_4'])
    expect(keys(zone(l, 'links'))).toEqual(['netz'])
  })

  it('(c) ≥ 2 E-Autos ohne Wallbox bündeln als `eauto_grp`', () => {
    const l = lay(bestandAutosOhneWallbox(), 360)
    const unten = zone(l, 'unten')
    expect(keys(unten)).toEqual(['waermepumpe_15', 'eauto_grp', 'sonstige_16'])
    expect(unten[1].komp.label).toBe('E-Autos')
    expect(unten[1].mitglieder!.map(m => m.key)).toEqual(['eauto_11', 'eauto_12', 'eauto_13', 'eauto_14'])
    expect(unten[1].komp.verbrauch_kw).toBeCloseTo(7, 9)
  })

  it('(d) Erschöpfung: 7 Klassen bei 800 px ⇒ Zoom unter die Mindestschrift, kein Fehler, keine Überlappung', () => {
    const l = lay(bestandErschoepft(), 800)
    expect(zone(l, 'unten')).toHaveLength(7)
    expect(l.stufen.unten.anzahl).toBe(1)
    expect(l.k).toBeCloseTo(662 / 600, 10)
    expect(l.schriftPx).toBeCloseTo(8.5 * 800 / 662, 9) // 10,27 px
    expect(l.mindestSchriftPx).toBeCloseTo(8.5 * 800 / 600, 9) // 11,33 px
    expect(l.schriftPx).toBeLessThan(l.mindestSchriftPx!)
    expect(ueberlappungsfrei(l.nodes, l.dims, { x: l.CX, y: l.CY })).toBe(true)
  })
})

describe('§A3 Faltung — Kinder nie als Kachel, das Auto steckt in der Wallbox', () => {
  it('kein gezeichneter Knoten trägt `parent_key`, keiner ist der Haushalt — jede Linie endet am Haus', () => {
    for (const { name, l } of alleLayouts()) {
      expect(l.nodes.filter(n => n.komp.parent_key), name).toEqual([])
      expect(l.nodes.some(n => n.komp.key === 'haushalt'), name).toBe(false)
    }
  })

  it('eine Wallbox, mehrere Autos: das ladende auf der Kachel; lädt keines, die Ladestände ohne Füllstand', () => {
    const ladend = wallboxKachelAuto([fz(1, 'ID.4', 64, 0), fz(2, 'Zoe', 38, 3.6)], 'eindeutig')
    expect(ladend).toEqual({ kachelAuto: { art: 'auto', auto: fz(2, 'Zoe', 38, 3.6) }, ladestand: 38 })
    const ruhend = wallboxKachelAuto([fz(1, 'ID.4', 64, 0), fz(2, 'Zoe', 81, null)], 'eindeutig')
    expect(ruhend).toEqual({ kachelAuto: { art: 'ladestaende', autos: [fz(1, 'ID.4', 64, 0), fz(2, 'Zoe', 81, null)] }, ladestand: null })
    expect(wallboxKachelAuto([fz(1, 'ID.4', 64, null)], 'eindeutig').ladestand).toBe(64)
    expect(wallboxKachelAuto([], 'eindeutig')).toEqual({ kachelAuto: null, ladestand: null })
  })

  it('≥ 2 Wallboxen (geschätzt): kein Auto auf einer Kachel, die Autos bleiben für Tooltip/Overlay', () => {
    const l = lay(bestandD(), 1150)
    const wbs = zone(l, 'unten').filter(n => n.komp.key.startsWith('wallbox_'))
    expect(wbs).toHaveLength(2)
    for (const wb of wbs) {
      expect(wb.kachelAuto).toBeNull()
      expect(wb.ladestand).toBeNull()
      expect(wb.fahrzeugeZuordnung).toBe('geschaetzt')
    }
    expect(wbs[0].fahrzeuge!.map(f => f.label)).toEqual(['ID.4', 'Enyaq'])
    // gebündelt: alle Autos in der Laden-Gruppe, keines auf der Kachel
    const laden = zone(lay(bestandD(), 360), 'unten').find(n => n.komp.key === 'wallbox_grp')!
    expect(laden.fahrzeuge!.map(f => f.investition_id)).toEqual([51, 52, 53])
    expect(laden.kachelAuto).toBeNull()
  })

  it('älteres Backend ohne `fahrzeuge`: der Client faltet die Kinder selbst (Label vom Knoten, Ladestand aus gauges)', () => {
    const b: Bestand = {
      komp: [pvS(1, 'Dach', null, 3, 5), wbS(4, 'Wallbox', 3.7), autoK(5, 'ID.4', 3.7, 'wallbox_4'), NETZ, HAUS],
      gauges: [soc(5, 52)],
    }
    const l = lay(b, 1150)
    expect(keys(zone(l, 'unten'))).toEqual(['wallbox_4'])
    const wb = zone(l, 'unten')[0]
    expect(wb.fahrzeuge).toEqual([{ investition_id: 5, label: 'ID.4', soc: 52, kw: 3.7, v2h: false }])
    expect(wb.fahrzeugeZuordnung).toBe('eindeutig')
    expect(wb.kachelAuto).toEqual({ art: 'auto', auto: wb.fahrzeuge![0] })
    expect(wb.ladestand).toBe(52)
  })

  it('BKW-Rest steht in der Gruppe seiner Module (Träger-Stufe, `traeger_id` = eigene ID)', () => {
    const l = lay(bestandBkw(), 360)
    expect(l.stufen.oben.name).toBe('traeger')
    const oben = zone(l, 'oben')
    expect(keys(oben)).toEqual(['pv_grp_tr30', 'pv_grp_tr44'])
    expect(oben[0].komp.label).toBe('Balkon')
    expect(oben[0].mitglieder!.map(m => m.key)).toEqual(['pv_31', 'pv_32', 'pv_30'])
    expect(oben[1].komp.label).toBe('PV-Gruppe 1') // kein Name in der Response ⇒ neutral nummeriert
  })

  it('A1b: Träger-Gruppen heißen nach `traeger_label` — ohne das Feld bleibt der Rückfall von oben', () => {
    const b = bestandBkw()
    // Der BKW-Name weicht bewusst vom Label des Rest-Knotens („Balkon") ab: so
    // zeigt die Probe, dass der Name aus `traeger_label` kommt, nicht vom Rest.
    b.komp = b.komp.map(x => x.traeger_id === 30 ? { ...x, traeger_label: 'Balkon Süd' }
      : x.traeger_id === 44 ? { ...x, traeger_label: 'WR Dach' } : x)
    const oben = zone(lay(b, 360), 'oben')
    expect(keys(oben)).toEqual(['pv_grp_tr30', 'pv_grp_tr44'])
    expect(labels(oben)).toEqual(['Balkon Süd', 'WR Dach'])
    // Nur der zweiten Gruppe fehlt das Feld (gemischt) ⇒ nur sie fällt auf die Nummer zurück.
    const halb = bestandBkw()
    halb.komp = halb.komp.map(x => x.traeger_id === 30 ? { ...x, traeger_label: 'Balkon Süd' } : x)
    expect(labels(zone(lay(halb, 360), 'oben'))).toEqual(['Balkon Süd', 'PV-Gruppe 1'])
  })

  it('eine Stufe, die die Kachelzahl nicht senkt, wird übersprungen', () => {
    // drei Strings, drei Richtungen: „nach Ausrichtung" wären wieder drei Kacheln
    const drei: Bestand = {
      komp: [pvS(1, 'O', 'Ost', 1, 2), pvS(2, 'S', 'Süd', 1, 2), pvS(3, 'W', 'West', 1, 2), NETZ, HAUS], gauges: [],
    }
    const l3 = lay(drei, 1150)
    expect([l3.stufen.oben.index, l3.stufen.oben.anzahl]).toEqual([0, 2]) // einzeln · gesamt
    // D mit je eigenem Träger: „nach Träger" (9) wäre mehr als „nach Ausrichtung" (3)
    const d = bestandD()
    d.komp = d.komp.map(k => (k.key.startsWith('pv_') ? { ...k, traeger_id: Number(k.key.slice(3)) + 100 } : k))
    expect(lay(d, 1150).stufen.oben.anzahl).toBe(3) // einzeln · ausrichtung · gesamt
  })

  it('ohne `ausrichtung_label`/`traeger_id` (älteres Backend) entfallen beide PV-Stufen → „PV gesamt"', () => {
    const b = bestandD()
    b.komp = b.komp.map(k => (k.key.startsWith('pv_') ? { ...k, ausrichtung_label: undefined, traeger_id: undefined } : k))
    const l = lay(b, 360)
    expect(l.stufen.oben.name).toBe('gesamt')
    expect(keys(zone(l, 'oben'))).toEqual(['pv_grp_gesamt'])
    expect(l.stufen.oben.anzahl).toBe(2)
  })

  it('Ausrichtung nur bei ≥ 2 Kacheln mit Label UND ≥ 2 Labeln; der Rest heißt „Weitere" und steht zuletzt', () => {
    const nurSued: Bestand = {
      komp: [1, 2, 3, 4, 5].map(i => pvS(i, `S${i}`, i < 4 ? 'Süd' : null, 1, 2)).concat([NETZ, HAUS]),
      gauges: [],
    }
    expect(lay(nurSued, 360).stufen.oben.name).toBe('gesamt') // ein Label ⇒ Stufe trennt nichts
    const gemischt: Bestand = {
      komp: [
        pvS(1, 'W', 'West', 1, 2), pvS(2, 'N', 'Nord', 1, 2), pvS(3, 'SO', 'Südost', 1, 2), pvS(4, 'O', 'Ost', 1, 2),
        pvS(5, 'O2', 'Ost', 1, 2), pvS(6, 'x', null, 1, 2), pvS(7, 'y', null, 1, 2), pvS(8, 'OW', 'Ost-West', 1, 2),
        pvS(9, 'NO', 'Nordost', 1, 2), pvS(10, 'SW', 'Südwest', 1, 2), NETZ, HAUS,
      ],
      gauges: [],
    }
    const l = layoutEnergieFluss(gemischt.komp, { breitePx: 1150 }) // 10 einzeln bräuchten 1324 px
    // Kompassrang: Ost · Südost · Süd · Südwest · West · Nordwest · Nord · Nordost · (Ost-West) · Weitere
    expect(labels(zone(l, 'oben'))).toEqual(['Ost', 'SO', 'SW', 'W', 'N', 'NO', 'OW', 'Weitere'])
  })
})

describe('§A3 Gruppenwerte (Plan §1.4)', () => {
  it('PV: Σ Leistung, Σ kWp nur wenn jedes Mitglied eine hat', () => {
    const sued = zone(lay(bestandD(), 1150), 'oben')[1]
    expect(sued.komp.erzeugung_kw).toBeCloseTo(7.5, 9)
    expect(sued.komp.leistung_kwp).toBeCloseTo(13.3, 9)
    expect(sued.komp.icon).toBe('sun')
    const b = bestandD()
    b.komp = b.komp.map(k => (k.key === 'pv_14' ? { ...k, leistung_kwp: null } : k))
    expect(zone(lay(b, 1150), 'oben')[1].komp.leistung_kwp).toBeNull()
  })

  it('Speicher: netto, Ladestand kapazitätsgewichtet, gegenläufige markiert', () => {
    const grp = zone(lay(bestandD(), 1150), 'rechts')[0]
    // Laden 1,2 + 0,8 + 0,4 = 2,4; Entladen 0,6 ⇒ netto 1,8 Ladung
    expect(grp.komp.verbrauch_kw).toBeCloseTo(1.8, 9)
    expect(grp.komp.erzeugung_kw).toBeNull()
    // (71·10,2 + 58·7,1 + 33·1,9 + 90·10) / 29,2 = 2098,7 / 29,2 = 71,87 ⇒ 72
    expect(grp.ladestand).toBe(72)
    expect(grp.komp.kapazitaet_kwh).toBeCloseTo(29.2, 9)
    expect(grp.gegenlaeufig!.map(m => m.key)).toEqual(['batterie_23'])
  })

  it('Speicher: eine fehlende Kapazität oder ein fehlender Ladestand ⇒ kein Füllstand', () => {
    const ohneKap = bestandD()
    ohneKap.komp = ohneKap.komp.map(k => (k.key === 'batterie_22' ? { ...k, kapazitaet_kwh: null } : k))
    expect(zone(lay(ohneKap, 1150), 'rechts')[0].ladestand).toBeNull()
    const ohneSoc = bestandD()
    ohneSoc.gauges = ohneSoc.gauges.filter(g => g.key !== 'soc_24')
    expect(zone(lay(ohneSoc, 1150), 'rechts')[0].ladestand).toBeNull()
  })

  it('„Heute"-kWh: Σ der Mitglieds-Keys, nur wenn alle bekannt', () => {
    const b = bestandD()
    b.tages = { pv_16: 1.2, pv_17: 1.1, pv_18: 2, pv_19: 2.1, pv_11: 3, pv_12: 3, pv_13: 3, pv_14: 2, pv_15: 1 }
    const oben = zone(lay(b, 1150), 'oben')
    expect(oben[0].heuteKwh).toBeCloseTo(2.3, 9)
    expect(oben[1].heuteKwh).toBeCloseTo(12, 9)
    delete b.tages.pv_19
    expect(zone(lay(b, 1150), 'oben')[2].heuteKwh).toBeNull()
  })

  it('maxKw über die GEZEICHNETEN Knoten — die Gruppe überschreitet jedes Einzelgerät', () => {
    const b = bestandD()
    const l = lay(b, 1150)
    const einzelMax = Math.max(...b.komp.flatMap(k => [k.erzeugung_kw ?? 0, k.verbrauch_kw ?? 0]))
    expect(einzelMax).toBeCloseTo(7.4, 9)
    expect(l.maxKw).toBeCloseTo(7.5, 9) // Süd (5)
  })

  it('BHKW nie mit Verbrauchern — auch nicht im Notnagel; Speicher nie im Notnagel', () => {
    for (const { name, l } of alleLayouts()) {
      for (const n of l.nodes.filter(x => x.mitglieder)) {
        const zweige = n.mitglieder!.filter(m => m.key.startsWith('sonstige_')).map(sonstigesZweig)
        if (zweige.includes('erzeuger')) expect(new Set(zweige), `${name} ${n.komp.key}`).toEqual(new Set(['erzeuger']))
        if (n.komp.key === 'sonstige_grp_weitere') {
          expect(zweige.filter(z => z === 'erzeuger' || z === 'speicher'), `${name}`).toEqual([])
          expect(n.mitglieder!.some(m => m.key.startsWith('batterie_') || m.key.startsWith('pv_')), `${name}`).toBe(false)
        }
      }
    }
  })
})

describe('§A3 Schlüssel, Reihenfolge, Überlappung', () => {
  it('Schlüssel verschieden; Gruppen-Keys `<präfix>_grp[_<slug>]`, Präfix trifft KATEGORIE_FARBEN, nie `_<Ziffern>` am Ende', () => {
    for (const { name, l } of alleLayouts()) {
      const ks = keys(l.nodes)
      expect(new Set(ks).size, name).toBe(ks.length)
      for (const n of l.nodes.filter(x => x.mitglieder)) {
        const key = n.komp.key
        expect(key, name).toMatch(/^[a-z]+_grp(_[a-z0-9]+)?$/)
        expect(Object.keys(KATEGORIE_FARBEN), `${name} ${key}`).toContain(key.split('_')[0])
        expect(/_\d+$/.test(key), `${name} ${key}`).toBe(false)
        expect(n.sortId, `${name} ${key}`).toBe(Math.min(...n.mitglieder!.map(m => Number(/_(\d+)$/.exec(m.key)![1]))))
      }
    }
  })

  it('stabile Reihenfolge: vertauschte Werte und gemischte Eingabe ändern die Kachelfolge nicht', () => {
    for (const f of [bestandD, bestandM, bestandGross]) {
      for (const m of [360, 420, 800, 1150]) {
        const b = f()
        const vorher = lay(b, m).nodes.map(n => `${n.zone}:${n.komp.key}`)
        const kw = b.komp.map(k => [k.erzeugung_kw, k.verbrauch_kw])
        const gedreht = b.komp.map((k, i) => {
          const [e, v] = kw[(i + 3) % kw.length]
          const wert = Math.max(e ?? 0, v ?? 0)
          return k.key === 'netz' || k.key === 'haushalt' ? k
            : { ...k, erzeugung_kw: k.erzeugung_kw != null ? wert : null, verbrauch_kw: k.verbrauch_kw != null ? wert : null }
        }).reverse()
        const nachher = lay({ ...b, komp: gedreht }, m).nodes.map(n => `${n.zone}:${n.komp.key}`)
        expect(nachher, `${f.name}@${m}`).toEqual(vorher)
      }
    }
  })

  it('ueberlappungsfrei: Rechtecke paarweise mit Mindestabstand, dazu der Hauskreis', () => {
    const d = { nodeW: 80, nodeH: 48, hausR: 34 }
    const haus = { x: 300, y: 170 }
    expect(ueberlappungsfrei([{ x: 55, y: 50 }, { x: 147, y: 50 }], d, haus)).toBe(true)
    expect(ueberlappungsfrei([{ x: 55, y: 50 }, { x: 138, y: 50 }], d, haus)).toBe(false) // 83 < 80 + 4
    expect(ueberlappungsfrei([{ x: 55, y: 50 }, { x: 139, y: 50 }], d, haus)).toBe(true) // genau 84
    expect(ueberlappungsfrei([{ x: 545, y: 50 }, { x: 545, y: 102 }], d, haus)).toBe(true)
    expect(ueberlappungsfrei([{ x: 545, y: 50 }, { x: 545, y: 101 }], d, haus)).toBe(false)
    expect(ueberlappungsfrei([{ x: 300, y: 115 }], d, haus)).toBe(false) // Kachelunterkante 139 > 136
    expect(ueberlappungsfrei([{ x: 300, y: 111 }], d, haus)).toBe(true)
  })

  it('Raster Breiten × Bestände (+ Vollbild): überlappungsfrei, je Zone eine Reihe, alles im Bild', () => {
    for (const { name, l } of alleLayouts()) {
      expect(ueberlappungsfrei(l.nodes, l.dims, { x: l.CX, y: l.CY }), name).toBe(true)
      expect(new Set(zone(l, 'oben').map(n => n.y)).size, name).toBeLessThanOrEqual(1)
      expect(new Set(zone(l, 'unten').map(n => n.y)).size, name).toBeLessThanOrEqual(1)
      expect(new Set(zone(l, 'rechts').map(n => n.x)).size, name).toBeLessThanOrEqual(1)
      expect(zone(l, 'links').length, name).toBeLessThanOrEqual(1)
      for (const n of l.nodes) {
        expect(n.x - l.dims.nodeW / 2, `${name} ${n.komp.key}`).toBeGreaterThanOrEqual(-1e-9)
        expect(n.x + l.dims.nodeW / 2, `${name} ${n.komp.key}`).toBeLessThanOrEqual(l.W + 1e-9)
        expect(n.y - l.dims.nodeH / 2, `${name} ${n.komp.key}`).toBeGreaterThanOrEqual(-1e-9)
        expect(n.y + l.dims.nodeH / 2, `${name} ${n.komp.key}`).toBeLessThanOrEqual(l.H + 1e-9)
      }
    }
  })

  it('der Handy-Notnagel lässt am Handy nie mehr als die Kapazität übrig', () => {
    for (const [name, f] of Object.entries(BESTAENDE)) {
      for (const b of [320, 360, 420, 450]) {
        const l = lay(f(), b)
        expect(zone(l, 'unten').length, `${name}@${b}`).toBeLessThanOrEqual(kapazitaet(l.W, l.dims.nodeW))
        expect(zone(l, 'oben').length, `${name}@${b}`).toBeLessThanOrEqual(kapazitaet(l.W, l.dims.nodeW))
      }
    }
  })

  it('der alte Pfad bleibt: `layoutNodes` rechnet unverändert, Gruppen entstehen nur im neuen Layout', () => {
    const b = bestandD()
    const alt = layoutNodes(b.komp, 600)
    expect(alt.nodes.some(n => n.komp.key.includes('_grp'))).toBe(false)
    expect(alt.nodes.filter(n => n.komp.key.startsWith('pv_'))).toHaveLength(9)
  })
})
