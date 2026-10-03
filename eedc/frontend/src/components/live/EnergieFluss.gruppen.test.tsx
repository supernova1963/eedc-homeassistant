/**
 * Energiefluss — Gruppenkachel, Wallbox mit Auto, Tooltip (Bau A §A4, #341/#348).
 *
 * Das Layout (`energieFlussLayout.ts`) entscheidet, WAS gezeichnet wird — das
 * prüft `energieFlussLayout.test.ts`. Hier geht es um das, was eine reine
 * Funktion nicht zeigt: dass die Komponente die Gruppe wirklich als Gruppe
 * zeichnet (Stapel-Optik, „Name (n)"), den Tooltip mit einer Zeile je Mitglied
 * füllt, das Auto in die Wallbox-Kachel legt und im Vollbild die Zeichenfläche
 * auf das Overlay-Verhältnis zieht.
 *
 * ⭐ **Seit §A5 Positiv-Probe (vorher A4-Gegenrichtung „keine Klick-Affordanz"):**
 * eine GRUPPENkachel ist ein Knopf (`role="button"`, `tabindex="0"`,
 * `cursor-pointer`, Klick + Enter/Leertaste) — aber nur, wenn der Aufrufer
 * `onGruppeKlick` reicht; Einzelkacheln sind es nie. Der letzte Block hält das
 * fest, dazu die Meldung der gezeichneten Gruppen (`onGruppen`, P-1).
 *
 * ⚠ Kartenbreite und (im Vollbild) Höhe der Zeichenfläche misst ein
 * ResizeObserver; jsdom hat keinen (der Stub in `setup.ts` meldet nie).
 * `mitBreite(px, svgHoehe)` stellt einen, der beim `observe` des Containers
 * die Breite und beim `observe` des SVG dessen Höhe meldet — immer, auch in
 * der Karte (dort muss die Komponente sie ignorieren).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import EnergieFluss, { SATZ_ZUORDNUNG_UNBEKANNT } from './EnergieFluss'
import { ThemeProvider } from '../../context/ThemeContext'
import { stubMatchMedia } from '../../test/render'
import type { LiveFahrzeug, LiveGauge, LiveKomponente } from '../../api/liveDashboard'
import type { GezeichneterKnoten } from './energieFlussLayout'
import { useTouchTitleTooltip } from '../../hooks/useTouchTitleTooltip'

const ORIGINAL_RO = globalThis.ResizeObserver

function mitBreite(px: number, svgHoehe = 500) {
  vi.stubGlobal('ResizeObserver', class {
    private cb: ResizeObserverCallback
    constructor(cb: ResizeObserverCallback) { this.cb = cb }
    observe(target: Element) {
      const istSvg = target.tagName.toLowerCase() === 'svg'
      this.cb([{ target, contentRect: { width: px, height: istSvg ? svgHoehe : 900 } } as unknown as ResizeObserverEntry], this as unknown as ResizeObserver)
    }
    unobserve() {}
    disconnect() {}
  })
}

beforeEach(() => {
  stubMatchMedia()
  localStorage.clear()
})
afterEach(() => {
  vi.unstubAllGlobals()
  globalThis.ResizeObserver = ORIGINAL_RO
})

// ── Fixtures (Bauform wie `energieFlussLayout.test.ts`) ──────────────────────

const knoten = (key: string, extra: Partial<LiveKomponente>): LiveKomponente =>
  ({ key, label: key, icon: 'wrench', erzeugung_kw: null, verbrauch_kw: null, ...extra })
const pv = (id: number, label: string, ausr: string | null, kw: number, extra: Partial<LiveKomponente> = {}) =>
  knoten(`pv_${id}`, { label, icon: 'sun', erzeugung_kw: kw, typ: 'pv-module', ausrichtung_label: ausr, leistung_kwp: 3, ...extra })
const sp = (id: number, label: string, kw: number, kap: number | null) =>
  knoten(`batterie_${id}`, {
    label, icon: 'battery', typ: 'speicher', kapazitaet_kwh: kap,
    erzeugung_kw: kw < 0 ? -kw : null, verbrauch_kw: kw >= 0 ? kw : null,
  })
const wp = (id: number, label: string, kw: number, modus: string | null = null) =>
  knoten(`waermepumpe_${id}`, { label, icon: 'flame', typ: 'waermepumpe', verbrauch_kw: kw, betriebsmodus_label: modus })
const wb = (id: number, label: string, kw: number, fahrzeuge: LiveFahrzeug[], zuordnung: 'eindeutig' | 'geschaetzt') =>
  knoten(`wallbox_${id}`, {
    label, icon: 'plug', typ: 'wallbox', fahrzeuge, fahrzeuge_zuordnung: zuordnung,
    ...(kw < 0 ? { erzeugung_kw: -kw } : { verbrauch_kw: kw }),
  })
/** kw > 0 lädt (Verbrauch), kw < 0 gibt ab (V2H, Erzeugung) — wie der Builder. */
const auto = (id: number, label: string, kw: number, parent: string | null) =>
  knoten(`eauto_${id}`, { label, icon: 'car', typ: 'e-auto', parent_key: parent, ...(kw < 0 ? { erzeugung_kw: -kw } : { verbrauch_kw: kw }) })
const fz = (id: number, label: string, soc: number | null, kw: number | null, v2h = false): LiveFahrzeug =>
  ({ investition_id: id, label, soc, kw, v2h })
const soc = (id: number, wert: number): LiveGauge =>
  ({ key: `soc_${id}`, label: `soc ${id}`, wert, min_wert: 0, max_wert: 100, einheit: '%' })
const NETZ = knoten('netz', { label: 'Stromnetz', icon: 'zap', erzeugung_kw: 1 })
const HAUS = knoten('haushalt', { label: 'Restverbrauch', icon: 'home', verbrauch_kw: 0.6 })

/** Plan-Tabelle D: 9 Strings (Süd 5 · Ost 2 · West 2), 4 Speicher, WP, 2 Wallboxen, 3 Autos, Pool, Sauna, BHKW. */
function bestandD(): { komp: LiveKomponente[]; gauges: LiveGauge[] } {
  return {
    komp: [
      pv(11, 'Süd 1', 'Süd', 1.9), pv(12, 'Süd 2', 'Süd', 1.8), pv(13, 'Süd 3', 'Süd', 1.7),
      pv(14, 'Süd Garage', 'Süd', 1.2), pv(15, 'Süd Gaube', 'Süd', 0.9), pv(16, 'Ost 1', 'Ost', 0.6),
      pv(17, 'Ost 2', 'Ost', 0.5), pv(18, 'West 1', 'West', 1.4), pv(19, 'West 2', 'West', 1.3),
      sp(21, 'BYD HVS', 1.2, 10.2), sp(22, 'Pylontech', 0.8, 7.1), sp(23, 'Zendure', -0.6, 1.9), sp(24, 'Sonnen', 0.4, 10),
      wp(31, 'Wärmepumpe', 1.4, 'Heizen'),
      wb(41, 'Wallbox Garage', 7.4, [fz(51, 'ID.4', 64, 7.4), fz(53, 'Enyaq', 81, null)], 'geschaetzt'),
      wb(42, 'Wallbox Carport', 3.6, [fz(52, 'Zoe', 38, 3.6)], 'geschaetzt'),
      auto(51, 'ID.4', 7.4, 'wallbox_41'), auto(52, 'Zoe', 3.6, 'wallbox_42'),
      knoten('sonstige_61', { label: 'Poolpumpe', typ: 'sonstiges', kategorie: 'verbraucher', verbrauch_kw: 0.8 }),
      knoten('sonstige_62', { label: 'Sauna', typ: 'sonstiges', kategorie: 'verbraucher', verbrauch_kw: 0 }),
      knoten('sonstige_63', { label: 'Mini-BHKW', typ: 'sonstiges', kategorie: 'erzeuger', erzeugung_kw: 1.0 }),
      knoten('netz', { label: 'Stromnetz', icon: 'zap', erzeugung_kw: 3.4 }), HAUS,
    ],
    gauges: [soc(21, 71), soc(22, 58), soc(23, 33), soc(24, 90), soc(51, 64), soc(52, 38), soc(53, 81)],
  }
}

/**
 * Eine Wallbox (eindeutig) mit den übergebenen Autos, dazu PV und WP. Wie im
 * Builder: ein Auto MIT gemessener Leistung hat einen Kind-Knoten
 * (`parent_key`), eines ohne (nur Ladestand / Sensor geteilt) nicht.
 */
function eineWallbox(kw: number, autos: LiveFahrzeug[]): LiveKomponente[] {
  const kinder = autos.filter(a => a.kw != null).map(a => auto(a.investition_id, a.label, a.kw!, 'wallbox_4'))
  return [pv(1, 'Dach Süd', 'Süd', 6.2), wp(3, 'Wärmepumpe', 1.1), wb(4, 'Wallbox', kw, autos, 'eindeutig'), ...kinder, NETZ, HAUS]
}

function zeichne(
  komponenten: LiveKomponente[],
  opt: {
    gauges?: LiveGauge[]; tagesWerte?: Record<string, number | null>; vollbild?: boolean
    onGruppeKlick?: (key: string) => void; onGruppen?: (g: GezeichneterKnoten[]) => void
  } = {},
) {
  return render(
    <ThemeProvider>
      <EnergieFluss
        komponenten={komponenten}
        summeErzeugung={10}
        summeVerbrauch={10}
        summePv={10}
        gauges={opt.gauges ?? []}
        tagesWerte={opt.tagesWerte}
        vollbild={opt.vollbild}
        onGruppeKlick={opt.onGruppeKlick}
        onGruppen={opt.onGruppen}
      />
    </ThemeProvider>,
  )
}

/** Alle Knoten-Gruppen (`<g data-title>`) mit ihrem Tooltip. */
function kacheln(container: HTMLElement) {
  return [...container.querySelectorAll('svg g[data-title]')].map(g => ({
    g,
    tip: g.getAttribute('data-title') ?? '',
    titel: g.querySelector(':scope > title')?.textContent ?? '',
    texte: [...g.querySelectorAll('text')].map(t => t.textContent?.trim() ?? ''),
    stapel: g.querySelectorAll('rect[data-stapel]').length,
  })).filter(k => !k.tip.startsWith('Restverbrauch'))
}
const kachel = (container: HTMLElement, ersteZeile: string) => {
  const treffer = kacheln(container).filter(k => k.tip.split('\n')[0] === ersteZeile)
  expect(treffer, `keine Kachel „${ersteZeile}"`).toHaveLength(1)
  return treffer[0]
}
/** Der SoC-Pegel: das einzige Rechteck mit Deckkraft 0,3 in der Kachel. */
const hatFuellstand = (g: Element) => g.querySelector('rect[fill-opacity="0.3"]') != null

describe('EnergieFluss §A4 — Gruppenkachel', () => {
  it('Bestand D in einer 600-px-Karte: PV nach Ausrichtung, „Speicher (4)" — je Gruppe zwei Stapel-Rahmen', () => {
    mitBreite(600)
    const { container } = zeichne(bestandD().komp, { gauges: bestandD().gauges })
    const gruppen = kacheln(container).filter(k => k.stapel > 0)
    expect(gruppen.map(g => g.tip.split('\n')[0])).toEqual(['Ost (2)', 'Süd (5)', 'West (2)', 'Speicher (4)'])
    gruppen.forEach(g => expect(g.stapel).toBe(2))
    // Einzelkacheln tragen keinen Stapel.
    expect(kachel(container, 'Wärmepumpe').stapel).toBe(0)
    // Die Beschriftung trägt die Anzahl: „Süd (5)" im Kachel-Text.
    expect(kachel(container, 'Süd (5)').texte).toContain('Süd (5)')
  })

  it('Tooltip: eine Zeile je Mitglied, `data-title` und `<title>` gleich (useTouchTitleTooltip-Bauform)', () => {
    mitBreite(600)
    const { container } = zeichne(bestandD().komp, { gauges: bestandD().gauges })
    const sued = kachel(container, 'Süd (5)')
    expect(sued.titel).toBe(sued.tip)
    const zeilen = sued.tip.split('\n')
    expect(zeilen.filter(z => z.startsWith('• '))).toEqual([
      '• Süd 1: 1,90 kW', '• Süd 2: 1,80 kW', '• Süd 3: 1,70 kW', '• Süd Garage: 1,20 kW', '• Süd Gaube: 0,90 kW',
    ])
    expect(zeilen).toContain('Summe: 7,50 kW (Erzeugung)')
    // Speicher: netto, Ladestand gewichtet, gegenläufige markiert, Ladestand je Mitglied.
    const speicher = kachel(container, 'Speicher (4)')
    expect(speicher.tip).toContain('Summe: 1,80 kW (Verbrauch, netto)')
    expect(speicher.tip).toContain('• Zendure: 0,60 kW (33 %, gegenläufig: gibt ab)')
    expect(speicher.tip).toMatch(/Ladestand: \d+ % \(nach Kapazität gewichtet\)/)
  })

  it('„Heute"-kWh der Gruppe = Σ der Mitglieds-Keys — und fehlt, sobald ein Mitglied fehlt', () => {
    mitBreite(600)
    const komp = bestandD().komp
    const voll = { pv_16: 1.5, pv_17: 1.25 }
    const { container } = zeichne(komp, { tagesWerte: voll })
    expect(kachel(container, 'Ost (2)').tip).toContain('Heute: 2,8 kWh')
    const halb = zeichne(komp, { tagesWerte: { pv_16: 1.5 } })
    expect(kachel(halb.container, 'Ost (2)').tip).not.toContain('Heute:')
  })

  it('Träger-Gruppe heißt „<traeger_label> (n)"; ohne Feld „PV-Gruppe 1 (n)" — die Anzahl bleibt beim Kürzen ganz', () => {
    mitBreite(360)
    const mitName = (id: number, label: string, t: number, name?: string) =>
      pv(id, label, null, 1, { traeger_id: t, ...(name ? { traeger_label: name } : {}) })
    const komp = (nameA?: string, nameB?: string) => [
      mitName(1, 'A1', 7, nameA), mitName(2, 'A2', 7, nameA), mitName(3, 'A3', 7, nameA),
      mitName(4, 'B1', 8, nameB), mitName(5, 'B2', 8, nameB), mitName(6, 'B3', 8, nameB), mitName(9, 'B4', 8, nameB),
      wp(10, 'WP', 1), NETZ, HAUS,
    ]
    const { container } = zeichne(komp('WR Dach', 'Fronius Symo Gen24 Plus'))
    const oben = kacheln(container).filter(k => k.stapel > 0).map(k => k.tip.split('\n')[0])
    expect(oben).toEqual(['WR Dach (3)', 'Fronius Symo Gen24 Plus (4)'])
    const lang = kachel(container, 'Fronius Symo Gen24 Plus (4)')
    // gekürzt, aber mit Anzahl
    expect(lang.texte.some(t => /…\s\(4\)$/.test(t))).toBe(true)
    const ohne = zeichne(komp())
    expect(kacheln(ohne.container).filter(k => k.stapel > 0).map(k => k.tip.split('\n')[0]))
      .toEqual(['PV-Gruppe 1 (3)', 'PV-Gruppe 2 (4)'])
  })

  it('Gruppentitel kürzt nach Kachelbreite, nicht nach `labelMaxChars`: „Speicher (4)" bleibt ganz (kompakte Kachel)', () => {
    // Bestand D bei 1150 px: sechs Kacheln unten ⇒ kompakte Größe (80 breit,
    // labelMaxChars 11) — „Speicher (4)" hat 12 Zeichen und passt trotzdem.
    mitBreite(1150)
    const { container } = zeichne(bestandD().komp, { gauges: bestandD().gauges })
    expect(kachel(container, 'Speicher (4)').texte).toContain('Speicher (4)')
  })

  it('Kinder werden nicht gezeichnet: kein Auto hinter der Wallbox als eigene Kachel', () => {
    mitBreite(1150)
    const { container } = zeichne(bestandD().komp, { gauges: bestandD().gauges })
    const erste = kacheln(container).map(k => k.tip.split('\n')[0])
    expect(erste).not.toContain('ID.4')
    expect(erste).not.toContain('Zoe')
  })
})

describe('EnergieFluss §A4 — das Auto steckt in der Wallbox-Kachel (Plan §1.4a)', () => {
  it('eindeutig, ein Auto: Füllstand = sein Ladestand, Zweitzeile „ID.4 52 %"', () => {
    mitBreite(1150)
    const { container } = zeichne(eineWallbox(3.7, [fz(5, 'ID.4', 52, 3.7)]))
    const w = kachel(container, 'Wallbox')
    expect(w.texte).toContain('ID.4 52 %')
    expect(hatFuellstand(w.g)).toBe(true)
    expect(w.tip).toContain('Auto ID.4: 52 %, lädt 3,70 kW')
    expect(w.tip).not.toContain(SATZ_ZUORDNUNG_UNBEKANNT)
  })

  it('Auto-Zeile in der kompakten Kachel: „VW ID.4 45 %" bleibt ganz (Budget nach Kachelbreite)', () => {
    // Fünf Kacheln unten ⇒ kompakte Größe (80 breit, labelMaxChars 11); die
    // Auto-Zeile hat 12 Zeichen und passt in die Kachel.
    mitBreite(1150)
    const komp = [
      ...eineWallbox(3.7, [fz(5, 'VW ID.4', 45, 3.7)]),
      wp(6, 'Klima', 0.4), knoten('sonstige_7', { label: 'Pool', typ: 'sonstiges', kategorie: 'verbraucher', verbrauch_kw: 0.3 }),
      knoten('sonstige_8', { label: 'BHKW', typ: 'sonstiges', kategorie: 'erzeuger', erzeugung_kw: 0.9 }),
    ]  // unten: Wärmepumpe · Wallbox · Klima · Pool · BHKW = 5
    const { container } = zeichne(komp)
    expect(kachel(container, 'Wallbox').texte).toContain('VW ID.4 45 %')
  })

  it('eindeutig, mehrere Autos: das ladende steht auf der Kachel', () => {
    mitBreite(1150)
    const { container } = zeichne(eineWallbox(3.7, [fz(5, 'ID.4', 52, 3.7), fz(6, 'Zoe', 81, 0)]))
    const w = kachel(container, 'Wallbox')
    expect(w.texte).toContain('ID.4 52 %')
    expect(w.texte).not.toContain('Zoe 81 %')
    expect(hatFuellstand(w.g)).toBe(true)
  })

  it('eindeutig, keines lädt: die Ladestände nebeneinander, OHNE Füllstand', () => {
    mitBreite(1150)
    const { container } = zeichne(eineWallbox(0, [fz(5, 'ID.4', 64, 0), fz(6, 'Zoe', 81, null)]))
    const w = kachel(container, 'Wallbox')
    expect(w.texte).toContain('64 · 81 %')
    expect(hatFuellstand(w.g)).toBe(false)
  })

  it('V2H: die Wallbox ist Quelle (N-575), die Zweitzeile trägt „· entlädt", der Tooltip das entladende Auto', () => {
    mitBreite(1150)
    const { container } = zeichne(eineWallbox(-2.0, [fz(5, 'ID.4', 52, -2.0, true)]))
    const w = kachel(container, 'Wallbox')
    // „ID.4 52 % · entlädt" (19 Zeichen) sprengt die 100er-Kachel in DejaVu Sans
    // (gemessen 105 Einheiten) — der Name weicht zuerst, Ladestand und Richtung nie.
    expect(w.texte).toContain('52 % · entlädt')
    expect(hatFuellstand(w.g)).toBe(true)
    expect(w.tip).toContain('Aktuell: 2,00 kW (Erzeugung)')
    expect(w.tip).toContain('Auto ID.4: 52 %, entlädt 2,00 kW (V2H)')
  })

  it('≥ 2 Wallboxen (geschätzt): kein Auto auf der Kachel; der Tooltip listet ALLE Autos und den Satz', () => {
    mitBreite(1150)
    const d = bestandD()
    const { container } = zeichne(d.komp, { gauges: d.gauges })
    for (const name of ['Wallbox Garage', 'Wallbox Carport']) {
      const w = kachel(container, name)
      expect(w.texte.some(t => /ID\.4|Zoe|Enyaq/.test(t))).toBe(false)
      expect(hatFuellstand(w.g)).toBe(false)
      expect(w.tip).toContain(SATZ_ZUORDNUNG_UNBEKANNT)
      // alle drei — auch das Auto, das reihum der ANDEREN Wallbox zugeschlagen ist
      expect(w.tip).toContain('• ID.4: 64 %, lädt 7,40 kW')
      expect(w.tip).toContain('• Zoe: 38 %, lädt 3,60 kW')
      expect(w.tip).toContain('• Enyaq: 81 %')
    }
  })
})

describe('EnergieFluss §A4 — Maßstab in der Karte und im Vollbild', () => {
  const viewBox = (c: HTMLElement) => c.querySelector('svg.flex-1')!.getAttribute('viewBox')!.split(' ').map(Number)

  it('Karte: Zeichenfläche 600·k × 380·k — die Karte wird nie höher (Bestand D bei 1150 px: 600 × 380)', () => {
    mitBreite(1150)
    const [, , w, h] = viewBox(zeichne(bestandD().komp, { gauges: bestandD().gauges }).container)
    expect([w, h]).toEqual([600, 380])
  })

  it('Handy (360 px): 360 Einheiten, Höhe 380', () => {
    mitBreite(360)
    const [, , w, h] = viewBox(zeichne(bestandD().komp, { gauges: bestandD().gauges }).container)
    expect([w, h]).toEqual([360, 380])
  })

  it('Vollbild: die Zeichenfläche nimmt das Verhältnis der gemessenen Fläche an — ohne `vollbild` bleibt es die Karte', () => {
    // Container 1600 breit, Zeichenfläche 900 hoch (gemessen, nicht das Fenster)
    mitBreite(1600, 900)
    const mit = viewBox(zeichne(bestandD().komp, { vollbild: true }).container)
    expect(mit[2] / mit[3]).toBeCloseTo(16 / 9, 6)
    // Karte: dieselbe gemeldete Höhe bleibt UNAUSGEWERTET (sonst Rückkopplung viewBox → Höhe)
    const ohne = viewBox(zeichne(bestandD().komp, { vollbild: false }).container)
    expect(ohne[2] / ohne[3]).toBeCloseTo(600 / 380, 6)
  })
})

describe('EnergieFluss §A5 — Gruppenkacheln sind klickbar (Positiv-Probe, vorher A4-Gegenrichtung)', () => {
  const svgVon = (c: HTMLElement) => c.querySelector('svg.flex-1')!

  it('mit onGruppeKlick: JEDE Gruppe trägt role="button", tabindex="0", cursor-pointer und ihren Key — keine Einzelkachel', () => {
    mitBreite(600)
    const { container } = zeichne(bestandD().komp, { gauges: bestandD().gauges, onGruppeKlick: () => {} })
    const gruppen = kacheln(container).filter(k => k.stapel > 0)
    expect(gruppen.map(g => g.g.getAttribute('data-gruppe'))).toEqual(['pv_grp_ost', 'pv_grp_sued', 'pv_grp_west', 'batterie_grp'])
    gruppen.forEach(({ g }) => {
      expect(g.getAttribute('role')).toBe('button')
      expect(g.getAttribute('tabindex')).toBe('0')
      expect(g.classList.contains('cursor-pointer')).toBe(true)
      expect(g.getAttribute('aria-label')).toMatch(/\(\d+\): Liste öffnen$/)
    })
    // Einzelkacheln bleiben ohne Affordanz — genau die Gruppen sind Knöpfe.
    const svg = svgVon(container)
    expect(svg.querySelectorAll('[role="button"]')).toHaveLength(gruppen.length)
    expect(svg.querySelectorAll('[tabindex]')).toHaveLength(gruppen.length)
    expect(svg.querySelectorAll('.cursor-pointer')).toHaveLength(gruppen.length)
    expect(kachel(container, 'Wärmepumpe').g.hasAttribute('role')).toBe(false)
  })

  it('OHNE onGruppeKlick: keine Affordanz — kein Knopf ohne Wirkung', () => {
    mitBreite(360)
    const { container } = zeichne(bestandD().komp, { gauges: bestandD().gauges })
    const svg = svgVon(container)
    expect(kacheln(container).filter(k => k.stapel > 0).length).toBeGreaterThan(0)
    expect(svg.querySelectorAll('[role="button"], [tabindex], .cursor-pointer')).toHaveLength(0)
  })

  it('Klick, Enter und Leertaste melden den Gruppen-Key; andere Tasten nicht', () => {
    mitBreite(600)
    const klick = vi.fn()
    const { container } = zeichne(bestandD().komp, { gauges: bestandD().gauges, onGruppeKlick: klick })
    const sued = kachel(container, 'Süd (5)').g
    fireEvent.click(sued)
    expect(klick).toHaveBeenLastCalledWith('pv_grp_sued')
    const speicher = kachel(container, 'Speicher (4)').g
    fireEvent.keyDown(speicher, { key: 'Enter' })
    expect(klick).toHaveBeenLastCalledWith('batterie_grp')
    fireEvent.keyDown(sued, { key: ' ' })
    expect(klick).toHaveBeenCalledTimes(3)
    fireEvent.keyDown(sued, { key: 'a' })
    fireEvent.keyDown(sued, { key: 'Tab' })
    expect(klick).toHaveBeenCalledTimes(3)
    // Klick auf eine Einzelkachel meldet nichts.
    fireEvent.click(kachel(container, 'Wärmepumpe').g)
    expect(klick).toHaveBeenCalledTimes(3)
  })

  it('Handy (360 px): der Klickpfad hängt an keinem max-sm:hidden — der Melder-Fall ist mobil', () => {
    mitBreite(360)
    const klick = vi.fn()
    const { container } = zeichne(bestandD().komp, { gauges: bestandD().gauges, onGruppeKlick: klick })
    const knoepfe = [...svgVon(container).querySelectorAll('[role="button"]')]
    expect(knoepfe.length).toBeGreaterThan(0)
    knoepfe.forEach(k => {
      for (let el: Element | null = k; el; el = el.parentElement) {
        expect(el.getAttribute('class') ?? '').not.toMatch(/(^|\s)(max-sm:hidden|hidden|sm:block)(\s|$)/)
      }
    })
    fireEvent.click(knoepfe[0])
    expect(klick).toHaveBeenCalledTimes(1)
  })

  it('der Tipp räumt einen offenen Touch-Tooltip weg, bevor das Fenster aufgeht', () => {
    mitBreite(600)
    // Ein Touch-Tooltip, wie ihn useTouchTitleTooltip anlegt — dafür ist der
    // Hook hier eingehängt (App-global in App.tsx).
    render(<TooltipHaken />)
    const ef = zeichne(bestandD().komp, { gauges: bestandD().gauges, onGruppeKlick: () => {} })
    const sued = kachel(ef.container, 'Süd (5)').g
    fireEvent.touchStart(sued, { touches: [{ clientX: 50, clientY: 200 }] })
    expect(touchTooltips()).toHaveLength(1)
    fireEvent.click(sued)
    expect(touchTooltips()).toHaveLength(0)
  })

  it('onGruppen meldet die GEZEICHNETEN Gruppen (P-1) — und nur, wenn der Prop gesetzt ist', () => {
    mitBreite(600)
    const meldung = vi.fn()
    zeichne(bestandD().komp, { gauges: bestandD().gauges, onGruppen: meldung })
    const letzte = meldung.mock.calls.at(-1)![0] as GezeichneterKnoten[]
    expect(letzte.map(g => g.komp.key)).toEqual(['pv_grp_ost', 'pv_grp_sued', 'pv_grp_west', 'batterie_grp'])
    expect(letzte.find(g => g.komp.key === 'pv_grp_sued')!.mitglieder!.map(m => m.key)).toEqual(['pv_11', 'pv_12', 'pv_13', 'pv_14', 'pv_15'])
  })
})

function TooltipHaken() {
  useTouchTitleTooltip()
  return null
}
const touchTooltips = () => [...document.body.children]
  .filter(el => el.tagName === 'DIV' && (el as HTMLElement).style.position === 'fixed')
