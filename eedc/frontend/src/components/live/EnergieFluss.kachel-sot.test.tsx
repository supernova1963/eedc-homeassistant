/**
 * Energiefluss — die Kachel ist bitgleich (P-433-2 E0, Wächter seit 24.10.2026).
 *
 * Die Kachel des Live-Energieflusses (`<g data-title>` je Knoten) ist seit
 * P-433-2 eine eigene Komponente (`EnergieFlussKachel.tsx`), weil der Hub-Block
 * «Überblick» dieselbe Kachel auf das Panorama legt (Konzept #433 Stufe 2, B1:
 * dieselbe Komponente, keine Kopie). Die Herauslösung durfte am Energiefluss
 * nichts ändern; diese Probe hält das fest — vorher und seitdem.
 *
 * **Was verglichen wird:** je Zelle der Matrix unten alle Teilbäume
 * `svg g[data-title]` (Kacheln, Haus, „Gesamtleistung"-Chip), serialisiert mit
 * sortierten Attributen. React-Keys stehen nicht im DOM. Die Pfade INNERHALB
 * des Lucide-Icons (`foreignObject > svg > *`) bleiben draußen — sie sind
 * Bibliotheks-Geometrie; das Icon selbst (Name, Größe, Farbe) steht über die
 * Attribute seines `<svg>` drin.
 *
 * **Matrix (18 Zellen, Bauplan P-433-2 §3 E0):** eine Knotenmenge mit je einem
 * Vertreter {Einzel aktiv · Einzel kw = 0 · PV mit kWp (Auslastung; gruppiert
 * Σ kW / Σ kWp) · Speicher mit SoC-Gauge · Wallbox mit Auto-Zeile · WP mit
 * Modus-Zeile · PV-Gruppe · Netz} × `lite` {0, 1} × `bg` {default, sunset, haus}
 * × Breite {600, 1150, 360}. Je Zelle zwei Zeichnungen: Gruppe **mit** und
 * **ohne** `onGruppeKlick` (Knopf-Attribute und Fokusrahmen nur mit).
 *
 * ⚠ **Handler-blind:** die Serialisierung sieht `onClick`/`onKeyDown` nicht.
 * Den Klickpfad hält `EnergieFluss.gruppen.test.tsx` (Klick, Enter, Leertaste)
 * — er gehört ausdrücklich mit ins Gate.
 *
 * ⚠ jsdom: `detectLiteDefault` ergibt hier immer `false`; `lite` wird deshalb
 * über den Storage-Key gesetzt, wie ihn der Schalter schreibt.
 *
 * **Wenn dieser Test rot wird:** Kachel absichtlich geändert? Dann den Snapshot
 * neu schreiben und den Diff im Commit mitschicken:
 *
 *     cd eedc/frontend && EEDC_KACHEL_SNAPSHOT=schreiben npx vitest run src/components/live/EnergieFluss.kachel-sot.test.tsx
 *
 * Unabsichtlich? Dann hat sich der Live-Energiefluss still geändert — das ist
 * genau der Fall, gegen den dieser Wächter steht.
 */
import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import EnergieFluss from './EnergieFluss'
import { ThemeProvider } from '../../context/ThemeContext'
import { stubMatchMedia } from '../../test/render'
import type { LiveFahrzeug, LiveGauge, LiveKomponente } from '../../api/liveDashboard'

const SNAPSHOT = join(process.cwd(), 'src', 'test', 'energiefluss-kacheln.snapshot.json')
const SCHREIBEN = process.env.EEDC_KACHEL_SNAPSHOT === 'schreiben'
const ORIGINAL_RO = globalThis.ResizeObserver

function mitBreite(px: number) {
  vi.stubGlobal('ResizeObserver', class {
    private cb: ResizeObserverCallback
    constructor(cb: ResizeObserverCallback) { this.cb = cb }
    observe(target: Element) {
      this.cb([{ target, contentRect: { width: px, height: 500 } } as unknown as ResizeObserverEntry], this as unknown as ResizeObserver)
    }
    unobserve() {}
    disconnect() {}
  })
}

// ── Knotenmenge (Bauform wie `EnergieFluss.gruppen.test.tsx`) ────────────────

const knoten = (key: string, extra: Partial<LiveKomponente>): LiveKomponente =>
  ({ key, label: key, icon: 'wrench', erzeugung_kw: null, verbrauch_kw: null, ...extra })
const pv = (id: number, label: string, ausr: string, kw: number) =>
  knoten(`pv_${id}`, { label, icon: 'sun', erzeugung_kw: kw, typ: 'pv-module', ausrichtung_label: ausr, leistung_kwp: 3 })
const fz = (id: number, label: string, soc: number | null, kw: number | null): LiveFahrzeug =>
  ({ investition_id: id, label, soc, kw, v2h: false })
const soc = (id: number, wert: number): LiveGauge =>
  ({ key: `soc_${id}`, label: `soc ${id}`, wert, min_wert: 0, max_wert: 100, einheit: '%' })

function knotenmenge(): { komp: LiveKomponente[]; gauges: LiveGauge[]; tagesWerte: Record<string, number | null> } {
  return {
    komp: [
      // PV: neun Strings — gruppiert nach Ausrichtung (Gruppe mit Auslastung Σ kW / Σ kWp).
      pv(11, 'Süd 1', 'Süd', 1.9), pv(12, 'Süd 2', 'Süd', 1.8), pv(13, 'Süd 3', 'Süd', 1.7),
      pv(14, 'Süd Garage', 'Süd', 1.2), pv(15, 'Süd Gaube', 'Süd', 0.9), pv(16, 'Ost 1', 'Ost', 0.6),
      pv(17, 'Ost 2', 'Ost', 0.5), pv(18, 'West 1', 'West', 1.4), pv(19, 'West 2', 'West', 1.3),
      // Speicher mit SoC-Gauge.
      knoten('batterie_21', { label: 'BYD HVS', icon: 'battery', typ: 'speicher', kapazitaet_kwh: 10.2, verbrauch_kw: 1.2 }),
      // Wärmepumpe mit Modus-Zeile.
      knoten('waermepumpe_31', { label: 'Wärmepumpe', icon: 'heater', typ: 'waermepumpe', verbrauch_kw: 1.4, betriebsmodus: 'heizen', betriebsmodus_label: 'Heizen' }),
      // Wallbox mit Auto-Zeile (eindeutig, ein Auto mit Kind-Knoten).
      knoten('wallbox_41', {
        label: 'Wallbox Garage', icon: 'plug', typ: 'wallbox', verbrauch_kw: 7.4,
        fahrzeuge: [fz(51, 'ID.4', 64, 7.4)], fahrzeuge_zuordnung: 'eindeutig',
      }),
      knoten('eauto_51', { label: 'ID.4', icon: 'car', typ: 'e-auto', parent_key: 'wallbox_41', verbrauch_kw: 7.4 }),
      // Einzel aktiv und Einzel kw = 0.
      knoten('sonstige_61', { label: 'Poolpumpe mit langem Namen', typ: 'sonstiges', kategorie: 'verbraucher', verbrauch_kw: 0.8 }),
      knoten('sonstige_62', { label: 'Sauna', typ: 'sonstiges', kategorie: 'verbraucher', verbrauch_kw: 0 }),
      knoten('netz', { label: 'Stromnetz', icon: 'zap', erzeugung_kw: 3.4 }),
      knoten('haushalt', { label: 'Restverbrauch', icon: 'home', verbrauch_kw: 0.6 }),
    ],
    gauges: [soc(21, 71), soc(51, 64)],
    tagesWerte: { pv_16: 1.5, pv_17: 1.25, waermepumpe: 6.2, sonstige_61: 2.1, netz_bezug: 4.4, netz_einspeisung: 9.8, haushalt: 12.3 },
  }
}

// ── Matrix ───────────────────────────────────────────────────────────────────

const LITE = ['0', '1'] as const
const BG = ['default', 'sunset', 'haus'] as const
const BREITE = [600, 1150, 360] as const
const ZELLEN = LITE.flatMap(lite => BG.flatMap(bg => BREITE.map(breite => ({ lite, bg, breite }))))
const zellName = (z: { lite: string; bg: string; breite: number }) => `lite=${z.lite} bg=${z.bg} breite=${z.breite}`

/** Ein Element kanonisch: Tag, Attribute sortiert, Kinder rekursiv; Icon-Innenleben draußen. */
function serialisiere(el: Element, imIcon = false): string {
  const attrs = [...el.attributes].map(a => `${a.name}=${JSON.stringify(a.value)}`).sort().join(' ')
  const tag = el.tagName.toLowerCase()
  if (imIcon) return `<${tag} ${attrs}/>`
  const kinder = [...el.childNodes].map(n => {
    if (n.nodeType === 3) return (n.textContent ?? '').trim()
    if (n.nodeType !== 1) return ''
    const kind = n as Element
    const istIcon = tag === 'foreignobject' && kind.tagName.toLowerCase() === 'svg'
    return serialisiere(kind, istIcon)
  }).filter(Boolean)
  return `<${tag} ${attrs}>${kinder.join('')}</${tag}>`
}

function zeichneZelle(z: { lite: string; bg: string; breite: number }, mitKlick: boolean): string[] {
  localStorage.clear()
  localStorage.setItem('eedc-energiefluss-lite', z.lite)
  localStorage.setItem('eedc-energiefluss-bg', z.bg)
  mitBreite(z.breite)
  const { komp, gauges, tagesWerte } = knotenmenge()
  const summePv = komp.filter(k => k.key.startsWith('pv_')).reduce((s, k) => s + (k.erzeugung_kw ?? 0), 0)
  const { container } = render(
    <ThemeProvider>
      <EnergieFluss
        komponenten={komp}
        summeErzeugung={summePv + 3.4}
        summeVerbrauch={summePv + 3.4}
        summePv={summePv}
        gauges={gauges}
        tagesWerte={tagesWerte}
        pvSollKw={8.5}
        onGruppeKlick={mitKlick ? () => {} : undefined}
      />
    </ThemeProvider>,
  )
  const teile = [...container.querySelectorAll('svg g[data-title]')].map(g => serialisiere(g))
  cleanup()
  return teile
}

type Snapshot = Record<string, { mitKlick: string[]; ohneKlick: string[] }>

const ist: Snapshot = {}
beforeAll(() => {
  stubMatchMedia()
  for (const z of ZELLEN) {
    ist[zellName(z)] = { mitKlick: zeichneZelle(z, true), ohneKlick: zeichneZelle(z, false) }
  }
})
afterEach(() => { localStorage.clear() })
afterAll(() => {
  vi.unstubAllGlobals()
  globalThis.ResizeObserver = ORIGINAL_RO
})

describe('Energiefluss-Kachel bitgleich (P-433-2 E0, 18-Zellen-Matrix)', () => {
  it('die Matrix hat 18 Zellen und jede Zelle zeichnet Kacheln, Gruppen und einen Knopf nur mit Handler', () => {
    expect(Object.keys(ist)).toHaveLength(18)
    for (const [name, z] of Object.entries(ist)) {
      expect(z.mitKlick.length, name).toBeGreaterThan(5)
      expect(z.mitKlick.length, name).toBe(z.ohneKlick.length)
      expect(z.mitKlick.some(s => s.includes('data-stapel=')), `${name}: keine Gruppe`).toBe(true)
      expect(z.mitKlick.some(s => s.includes('data-fokusrahmen')), `${name}: kein Fokusrahmen`).toBe(true)
      expect(z.ohneKlick.some(s => s.includes('data-fokusrahmen')), `${name}: Fokusrahmen ohne Handler`).toBe(false)
    }
  })

  it('jeder Vertreter der Knotenmenge kommt in der Matrix vor (Pegel, Modus-, Auto- und SoC-Zeile)', () => {
    const alles = Object.values(ist).flatMap(z => z.mitKlick).join('\n')
    expect(alles).toContain('fill-opacity="0.25"')   // PV-Auslastung
    expect(alles).toContain('fill-opacity="0.3"')    // SoC-Pegel
    expect(alles).toContain('>Heizen<')              // Modus-Zeile
    expect(alles).toContain('ID.4 64 %')             // Auto-Zeile der Wallbox
    expect(alles).toContain('>71 %<')                // SoC-Zeile
    expect(alles).toContain('filter="url(#ef-card-shadow)"')
  })

  it('jede Zelle ist gleich dem eingecheckten Snapshot', () => {
    if (SCHREIBEN) {
      writeFileSync(SNAPSHOT, JSON.stringify(ist, null, 1) + '\n')
      return
    }
    expect(existsSync(SNAPSHOT), `Snapshot fehlt — erzeugen per Befehl im Kopf dieser Datei`).toBe(true)
    const soll = JSON.parse(readFileSync(SNAPSHOT, 'utf8')) as Snapshot
    expect(Object.keys(ist).sort()).toEqual(Object.keys(soll).sort())
    for (const name of Object.keys(soll)) {
      expect(ist[name].mitKlick, `${name} (mit onGruppeKlick)`).toEqual(soll[name].mitKlick)
      expect(ist[name].ohneKlick, `${name} (ohne onGruppeKlick)`).toEqual(soll[name].ohneKlick)
    }
  })
})
