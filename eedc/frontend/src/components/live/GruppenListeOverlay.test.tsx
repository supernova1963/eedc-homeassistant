/**
 * GruppenListeOverlay — die „Liste mit Balken" (Bau A §A5, #341/#348, Plan §1.6).
 *
 * Die Gruppen kommen hier aus dem ECHTEN Layout (`layoutEnergieFluss`), nicht
 * aus handgebauten Knoten — so prüft jede Probe die Gruppe, die der Anwender
 * tatsächlich antippt. Die Verdrahtung in der Sicht (Öffnen, 5-s-Takt,
 * Fokus-Rückgabe, ESC über dem Vollbild und im Deep-Link) prüft
 * `v4/CockpitLiveEnergieflussGruppen.test.tsx`.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import GruppenListeOverlay from './GruppenListeOverlay'
import { SATZ_ZUORDNUNG_UNBEKANNT } from './EnergieFluss'
import { layoutEnergieFluss, type GezeichneterKnoten } from './energieFlussLayout'
import { CHART_COLORS, KATEGORIE_FARBEN } from '../../lib'
import type { LiveFahrzeug, LiveGauge, LiveKomponente } from '../../api/liveDashboard'

afterEach(() => vi.restoreAllMocks())

// ── Fixtures (Bauform wie `EnergieFluss.gruppen.test.tsx`) ───────────────────
const knoten = (key: string, extra: Partial<LiveKomponente>): LiveKomponente =>
  ({ key, label: key, icon: 'wrench', erzeugung_kw: null, verbrauch_kw: null, ...extra })
const pv = (id: number, label: string, ausr: string | null, kw: number, extra: Partial<LiveKomponente> = {}) =>
  knoten(`pv_${id}`, { label, icon: 'sun', erzeugung_kw: kw, typ: 'pv-module', ausrichtung_label: ausr, leistung_kwp: 3, ...extra })
/** kw ≥ 0 lädt (Verbrauch), kw < 0 entlädt (Erzeugung). */
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
const auto = (id: number, label: string, kw: number, parent: string | null) =>
  knoten(`eauto_${id}`, { label, icon: 'car', typ: 'e-auto', parent_key: parent, ...(kw < 0 ? { erzeugung_kw: -kw } : { verbrauch_kw: kw }) })
const fz = (id: number, label: string, soc: number | null, kw: number | null, v2h = false): LiveFahrzeug =>
  ({ investition_id: id, label, soc, kw, v2h })
const soc = (id: number, wert: number): LiveGauge =>
  ({ key: `soc_${id}`, label: `soc ${id}`, wert, min_wert: 0, max_wert: 100, einheit: '%' })
const NETZ = knoten('netz', { label: 'Stromnetz', icon: 'zap', erzeugung_kw: 3.4 })
const HAUS = knoten('haushalt', { label: 'Haushalt', icon: 'home', verbrauch_kw: 0.6 })

/** Plan-Tabelle D (wie `EnergieFluss.gruppen.test.tsx`), die Süd-Strings mit Träger-Namen. */
function bestandD(): { komp: LiveKomponente[]; gauges: LiveGauge[] } {
  const hd = { traeger_id: 20, traeger_label: 'WR Hausdach' }
  return {
    komp: [
      pv(11, 'Süd 1', 'Süd', 1.9, hd), pv(12, 'Süd 2', 'Süd', 1.8, hd), pv(13, 'Süd 3', 'Süd', 1.5, hd),
      pv(14, 'Süd Garage', 'Süd', 1.2, { leistung_kwp: null }), pv(15, 'Süd Gaube', 'Süd', 0, hd),
      pv(16, 'Ost 1', 'Ost', 0.6), pv(17, 'Ost 2', 'Ost', 0.5), pv(18, 'West 1', 'West', 1.4), pv(19, 'West 2', 'West', 1.3),
      sp(21, 'BYD HVS', 1.2, 10.2), sp(22, 'Pylontech', 0.8, 7.1), sp(23, 'Zendure', -0.6, 1.9), sp(24, 'Sonnen', 0, 10),
      wp(31, 'Wärmepumpe', 1.4, 'Heizen'),
      wb(41, 'Wallbox Garage', 7.4, [fz(51, 'ID.4', 64, 7.4), fz(53, 'Enyaq', 81, null)], 'geschaetzt'),
      wb(42, 'Wallbox Carport', 3.6, [fz(52, 'Zoe', 38, -2.0, true)], 'geschaetzt'),
      auto(51, 'ID.4', 7.4, 'wallbox_41'),
      knoten('sonstige_61', { label: 'Poolpumpe', typ: 'sonstiges', kategorie: 'verbraucher', verbrauch_kw: 0.8 }),
      knoten('sonstige_62', { label: 'Sauna', typ: 'sonstiges', kategorie: 'zaehler', verbrauch_kw: 0 }),
      knoten('sonstige_63', { label: 'Mini-BHKW', typ: 'sonstiges', kategorie: 'erzeuger', erzeugung_kw: 1.0 }),
      NETZ, HAUS,
    ],
    gauges: [soc(21, 71), soc(22, 58), soc(23, 33), soc(24, 90), soc(51, 64), soc(52, 38), soc(53, 81)],
  }
}

/** Zwei WP, zwei Steckerlader, zwei BHKW — am Handy drei Klassen-Gruppen. */
function bestandKlassen(): { komp: LiveKomponente[]; gauges: LiveGauge[] } {
  return {
    komp: [
      pv(1, 'Dach', 'Süd', 3),
      wp(2, 'WP Haus', 1.2, 'Heizen'), wp(3, 'WP Werkstatt', 0.4, null),
      auto(4, 'Kangoo', 2.3, null), auto(5, 'Twizy', -0.8, null),
      knoten('sonstige_6', { label: 'BHKW Keller', typ: 'sonstiges', kategorie: 'erzeuger', erzeugung_kw: 1.1 }),
      knoten('sonstige_7', { label: 'BHKW Stall', typ: 'sonstiges', kategorie: 'erzeuger', erzeugung_kw: 0.5 }),
      NETZ, HAUS,
    ],
    gauges: [soc(4, 55), soc(5, 72)],
  }
}

function gruppe(b: { komp: LiveKomponente[]; gauges: LiveGauge[] }, breite: number, key: string): GezeichneterKnoten {
  const l = layoutEnergieFluss(b.komp, { breitePx: breite }, { gauges: b.gauges })
  const g = l.nodes.find(n => n.komp.key === key)
  expect(g, `keine Gruppe ${key} bei ${breite} px (gezeichnet: ${l.nodes.map(n => n.komp.key).join(', ')})`).toBeDefined()
  expect(g!.mitglieder, `${key} ist keine Gruppe`).toBeDefined()
  return g!
}

function oeffne(b: { komp: LiveKomponente[]; gauges: LiveGauge[] }, breite: number, key: string, onClose = () => {}) {
  const g = gruppe(b, breite, key)
  const r = render(<GruppenListeOverlay gruppe={g} komponenten={b.komp} gauges={b.gauges} onClose={onClose} />)
  return { ...r, g }
}

/** Die Zeilen der Liste: Name, Wert, Zusatz, Balkenbreite (%), Balkenfarbe. */
function zeilen() {
  return [...document.body.querySelectorAll('li[data-zeile]')].map(li => {
    const balken = li.querySelector<HTMLElement>('[data-balken]')!
    const spans = li.querySelectorAll(':scope > span')
    return {
      key: li.getAttribute('data-zeile'),
      name: spans[0].textContent,
      wert: spans[2].textContent,
      zusatz: li.querySelector('[data-zusatz]')?.textContent ?? null,
      breite: Number.parseFloat(balken.style.width),
      farbe: balken.style.backgroundColor,
      label: spans[1].getAttribute('aria-label'),
    }
  })
}

/** jsdom liest `style.backgroundColor` als `rgb(...)` — die Farbe aus `lib/colors` dahin übersetzt. */
function rgb(hex: string): string {
  const n = Number.parseInt(hex.slice(1), 16)
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`
}

describe('GruppenListeOverlay — Dialog und Titel', () => {
  it('ist ein Dialog mit dem echten Gruppentitel als Namen; Fokus auf „Schließen"; keine Fokus-ID, kein Einbetten', () => {
    oeffne(bestandD(), 600, 'pv_grp_sued')
    const d = screen.getByRole('dialog', { name: 'Süd (5)' })
    expect(d.getAttribute('aria-modal')).toBe('true')
    expect(document.activeElement).toBe(within(d).getByRole('button', { name: /Schließen/ }))
    expect(within(d).queryByRole('button', { name: /Einbetten|Link/ })).toBeNull()
    expect(d.querySelector('[data-fokus-id], [fokusid]')).toBeNull()
    expect(within(d).queryByText('Fokus / Vollbild')).toBeNull()
  })

  it('„Schließen" ruft onClose', () => {
    const zu = vi.fn()
    oeffne(bestandD(), 600, 'pv_grp_sued', zu)
    fireEvent.click(screen.getByRole('button', { name: /Schließen/ }))
    expect(zu).toHaveBeenCalledTimes(1)
  })
})

describe('GruppenListeOverlay — je Mitglied eine Zeile mit Balken', () => {
  it('PV (Süd, 5): Namen in Layout-Reihenfolge, Balken relativ zum stärksten, Rollenfarbe PV, Wert wie auf der Kachel', () => {
    oeffne(bestandD(), 600, 'pv_grp_sued')
    const z = zeilen()
    expect(z.map(r => r.name)).toEqual(['Süd 1', 'Süd 2', 'Süd 3', 'Süd Garage', 'Süd Gaube'])
    expect(z.map(r => r.wert)).toEqual(['1.900 W', '1.800 W', '1.500 W', '1.200 W', '0 W'])
    expect(z[0].breite).toBe(100)
    expect(z[1].breite).toBeCloseTo(1.8 / 1.9 * 100, 1)
    expect(z[4].breite).toBe(0)
    z.forEach(r => expect(r.farbe).toBe(rgb(KATEGORIE_FARBEN.pv)))
    // beschrifteter Balken
    expect(z[1].label).toBe('Süd 2: 1.800 W, 95 % des stärksten Geräts')
  })

  it('PV: Auslastung (nur mit kWp) + Ausrichtung + Träger', () => {
    oeffne(bestandD(), 600, 'pv_grp_sued')
    const z = zeilen()
    expect(z[0].zusatz).toBe('63 % von 3,0 kWp · Süd · WR Hausdach')
    // ohne kWp keine Auslastung (P4), ohne Träger kein Träger
    expect(z[3].zusatz).toBe('Süd')
    // steht still: 0 % — die Auslastung ist bekannt, sie ist null
    expect(z[4].zusatz).toBe('0 % von 3,0 kWp · Süd · WR Hausdach')
    expect(screen.getByText(/PV-Gruppe/)).toBeInTheDocument()
    expect(screen.getByText(/Summe: 6,40 kW \(Erzeugung\)/)).toBeInTheDocument()
  })

  it('Speicher (4): lädt/entlädt/ruht + Ladestand + nutzbare Kapazität, Farbe nach Richtung, Fuß mit gewichtetem Ladestand', () => {
    oeffne(bestandD(), 600, 'batterie_grp')
    const z = zeilen()
    expect(z.map(r => [r.name, r.zusatz])).toEqual([
      ['BYD HVS', 'lädt · Ladestand 71 % · 10,2 kWh nutzbar'],
      ['Pylontech', 'lädt · Ladestand 58 % · 7,1 kWh nutzbar'],
      ['Zendure', 'entlädt · Ladestand 33 % · 1,9 kWh nutzbar'],
      ['Sonnen', 'ruht · Ladestand 90 % · 10,0 kWh nutzbar'],
    ])
    expect(z[0].farbe).toBe(rgb(CHART_COLORS.speicherLadung))
    expect(z[2].farbe).toBe(rgb(CHART_COLORS.speicherEntladung))
    expect(screen.getByText(/Summe: 1,40 kW \(Verbrauch, netto\)/)).toBeInTheDocument()
    expect(screen.getByText(/Ladestand der Gruppe \d+ %, gewichtet nach nutzbarer Kapazität\./)).toBeInTheDocument()
  })

  it('Laden (2), geschätzt: jede Wallbox eine Zeile ohne Auto; ALLE Autos einmal darunter + der Satz', () => {
    oeffne(bestandD(), 420, 'wallbox_grp')
    const z = zeilen()
    expect(z.map(r => [r.name, r.wert, r.zusatz])).toEqual([
      ['Wallbox Garage', '7.400 W', null],
      ['Wallbox Carport', '3.600 W', null],
    ])
    z.forEach(r => expect(r.farbe).toBe(rgb(KATEGORIE_FARBEN.wallbox)))
    const autos = document.body.querySelector('[data-autos]')!
    // nach Investitions-ID: ID.4 (51) · Zoe (52) · Enyaq (53)
    expect([...autos.querySelectorAll('li')].map(li => li.textContent)).toEqual([
      'ID.4 · 64 % · lädt 7,40 kW',
      'Zoe · 38 % · entlädt 2,00 kW (V2H)',
      'Enyaq · 81 %',
    ])
    expect(autos.textContent).toContain(SATZ_ZUORDNUNG_UNBEKANNT)
    expect(screen.getByText(/Die Autos zeigen denselben Strom aus Autosicht und werden nicht addiert\./)).toBeInTheDocument()
  })

  it('Sonstige (2): Kategorie im Klartext, Rollenfarbe Sonstige', () => {
    oeffne(bestandD(), 420, 'sonstige_grp_verbraucher')
    const z = zeilen()
    expect(z.map(r => [r.name, r.zusatz])).toEqual([['Poolpumpe', 'Verbraucher'], ['Sauna', 'Verbrauchszähler']])
    z.forEach(r => expect(r.farbe).toBe(rgb(KATEGORIE_FARBEN.sonstige)))
  })

  it('„Weitere Verbraucher" (Handy 360): jedes Mitglied in SEINER Rollenfarbe, WP mit Betriebsart, Fuß-Satz', () => {
    oeffne(bestandD(), 360, 'sonstige_grp_weitere')
    expect(screen.getByRole('dialog', { name: 'Weitere (3)' })).toBeInTheDocument()
    expect(screen.getByText('Weitere Verbraucher')).toBeInTheDocument()
    const z = zeilen()
    expect(z.map(r => [r.name, r.zusatz])).toEqual([
      ['Wärmepumpe', 'Heizen'], ['Poolpumpe', 'Verbraucher'], ['Sauna', 'Verbrauchszähler'],
    ])
    expect(z[0].farbe).toBe(rgb(KATEGORIE_FARBEN.waermepumpe))
    expect(z[1].farbe).toBe(rgb(KATEGORIE_FARBEN.sonstige))
    expect(screen.getByText(/nur Verbraucher, nie zusammen mit Erzeugern oder Speichern/)).toBeInTheDocument()
  })

  it('Wärmepumpen (2): Betriebsart im Klartext — ohne Zuordnung KEINE erfundene', () => {
    oeffne(bestandKlassen(), 360, 'waermepumpe_grp')
    expect(zeilen().map(r => [r.name, r.zusatz])).toEqual([['WP Haus', 'Heizen'], ['WP Werkstatt', null]])
  })

  it('E-Autos ohne Wallbox (2): Ladestand, V2H-Richtung', () => {
    oeffne(bestandKlassen(), 360, 'eauto_grp')
    expect(zeilen().map(r => [r.name, r.zusatz])).toEqual([['Kangoo', 'Ladestand 55 %'], ['Twizy', 'Ladestand 72 % · gibt ab (V2H)']])
    zeilen().forEach(r => expect(r.farbe).toBe(rgb(KATEGORIE_FARBEN.eauto)))
  })

  it('BHKW-Gruppe (Erzeuger): Kategorie „Erzeuger", Summe als Erzeugung', () => {
    oeffne(bestandKlassen(), 360, 'sonstige_grp_erzeuger')
    expect(zeilen().map(r => [r.name, r.zusatz])).toEqual([['BHKW Keller', 'Erzeuger'], ['BHKW Stall', 'Erzeuger']])
    expect(screen.getByText(/Summe: 1,60 kW \(Erzeugung\)/)).toBeInTheDocument()
  })

  it('Wallbox EINDEUTIG in einer Gruppe: die Autos stehen an ihrer Wallbox, kein Satz', () => {
    const b = {
      komp: [
        pv(1, 'Dach', 'Süd', 5), wp(2, 'WP', 1.0, 'Warmwasser'),
        wb(3, 'Wallbox', 3.7, [fz(4, 'ID.4', 52, 3.7)], 'eindeutig'), auto(4, 'ID.4', 3.7, 'wallbox_3'),
        // BHKW und sonstiger Speicher kommen nie in „Weitere" — der Notnagel
        // bündelt deshalb genau WP + Wallbox.
        knoten('sonstige_6', { label: 'Akku alt', typ: 'sonstiges', kategorie: 'speicher', erzeugung_kw: 0.3 }),
        knoten('sonstige_7', { label: 'BHKW', typ: 'sonstiges', kategorie: 'erzeuger', erzeugung_kw: 1 }),
        NETZ, HAUS,
      ],
      gauges: [soc(4, 52)],
    }
    oeffne(b, 360, 'sonstige_grp_weitere')
    const wallbox = zeilen().find(r => r.key === 'wallbox_3')
    expect(wallbox?.zusatz).toBe('Auto ID.4 · 52 % · lädt 3,70 kW')
    expect(document.body.querySelector('[data-autos]')).toBeNull()
    expect(document.body.textContent).not.toContain(SATZ_ZUORDNUNG_UNBEKANNT)
  })
})

describe('GruppenListeOverlay — Tageswert je Mitglied (§A7)', () => {
  /** Öffnet die Gruppe mit `tagesWerte` (der Rest wie `oeffne`). */
  function oeffneMitTag(b: { komp: LiveKomponente[]; gauges: LiveGauge[] }, breite: number, key: string, tagesWerte?: Record<string, number | null>) {
    const g = gruppe(b, breite, key)
    return render(<GruppenListeOverlay gruppe={g} komponenten={b.komp} gauges={b.gauges} tagesWerte={tagesWerte} onClose={() => {}} />)
  }

  it('Wert vorhanden ⇒ „heute X kWh" als letzte Angabe in DER Zeile des Geräts, deutsches Format', () => {
    oeffneMitTag(bestandD(), 600, 'pv_grp_sued', { pv_11: 12.08, pv_12: 9.5, pv_13: 8.04, pv_14: 7, pv_15: 0 })
    expect(zeilen().map(r => [r.name, r.zusatz])).toEqual([
      ['Süd 1', '63 % von 3,0 kWp · Süd · WR Hausdach · heute 12,1 kWh'],
      ['Süd 2', '60 % von 3,0 kWp · Süd · WR Hausdach · heute 9,5 kWh'],
      ['Süd 3', '50 % von 3,0 kWp · Süd · WR Hausdach · heute 8,0 kWh'],
      ['Süd Garage', 'Süd · heute 7,0 kWh'],
      // ein gemessener Tag ohne Ertrag ist bekannt: 0,0 — nicht dasselbe wie „fehlt"
      ['Süd Gaube', '0 % von 3,0 kWp · Süd · WR Hausdach · heute 0,0 kWh'],
    ])
  })

  it('Wert fehlt für EIN Mitglied ⇒ genau dessen Zeile ohne Zusatz, die anderen mit — nichts statt 0 (P4)', () => {
    // pv_13 fehlt im Datensatz, pv_15 ist ausdrücklich null
    oeffneMitTag(bestandD(), 600, 'pv_grp_sued', { pv_11: 12.08, pv_12: 9.5, pv_14: 7, pv_15: null })
    const z = zeilen()
    expect(z.map(r => [r.name, r.zusatz])).toEqual([
      ['Süd 1', '63 % von 3,0 kWp · Süd · WR Hausdach · heute 12,1 kWh'],
      ['Süd 2', '60 % von 3,0 kWp · Süd · WR Hausdach · heute 9,5 kWh'],
      ['Süd 3', '50 % von 3,0 kWp · Süd · WR Hausdach'],
      ['Süd Garage', 'Süd · heute 7,0 kWh'],
      ['Süd Gaube', '0 % von 3,0 kWp · Süd · WR Hausdach'],
    ])
    expect(z[2].zusatz).not.toMatch(/heute|kWh$/)
  })

  it('ohne sonstige Angabe trägt der Tageswert die Zusatzzeile allein', () => {
    oeffneMitTag(bestandKlassen(), 360, 'waermepumpe_grp', { waermepumpe_2: 6.3, waermepumpe_3: 1.94 })
    expect(zeilen().map(r => [r.name, r.zusatz])).toEqual([['WP Haus', 'Heizen · heute 6,3 kWh'], ['WP Werkstatt', 'heute 1,9 kWh']])
  })

  it('Präfix-Fallback greift wie am Kachel-Tooltip: exakter Key zuerst, sonst der Key ohne Nummer', () => {
    oeffneMitTag(bestandKlassen(), 360, 'waermepumpe_grp', { waermepumpe_2: 6.3, waermepumpe: 2.04 })
    expect(zeilen().map(r => [r.name, r.zusatz])).toEqual([['WP Haus', 'Heizen · heute 6,3 kWh'], ['WP Werkstatt', 'heute 2,0 kWh']])
  })

  it('ohne Prop (und mit leerem Datensatz) rendert alles wie bisher — kein „heute" in irgendeiner Zeile', () => {
    for (const tw of [undefined, {}]) {
      for (const [b, breite, key] of [
        [bestandD(), 600, 'pv_grp_sued'], [bestandD(), 600, 'batterie_grp'], [bestandD(), 420, 'wallbox_grp'],
        [bestandKlassen(), 360, 'waermepumpe_grp'], [bestandKlassen(), 360, 'eauto_grp'],
      ] as const) {
        const { unmount } = oeffneMitTag(b, breite, key, tw)
        expect(document.body.textContent, `${key} mit ${JSON.stringify(tw)}`).not.toMatch(/heute/)
        unmount()
      }
    }
    // die bestehenden Zeilen bleiben wortgleich
    oeffneMitTag(bestandD(), 600, 'pv_grp_sued')
    expect(zeilen()[0].zusatz).toBe('63 % von 3,0 kWp · Süd · WR Hausdach')
    expect(zeilen()[3].zusatz).toBe('Süd')
  })
})

describe('GruppenListeOverlay — live und ESC', () => {
  it('die Zeilen kommen aus den AKTUELLEN komponenten, nicht aus der Gruppe (eingefrorene Mitglieder)', () => {
    const b = bestandD()
    const g = gruppe(b, 600, 'pv_grp_sued')
    const { rerender } = render(<GruppenListeOverlay gruppe={g} komponenten={b.komp} gauges={b.gauges} onClose={() => {}} />)
    expect(zeilen()[0].wert).toBe('1.900 W')
    // neuer Takt: dieselbe Gruppe (Objekt unverändert), neue Werte, ein Mitglied weg
    const neu = b.komp
      .map(k => (k.key === 'pv_11' ? { ...k, erzeugung_kw: 0.95 } : k))
      .filter(k => k.key !== 'pv_15')
    rerender(<GruppenListeOverlay gruppe={g} komponenten={neu} gauges={b.gauges} onClose={() => {}} />)
    const z = zeilen()
    expect(z.map(r => r.name)).toEqual(['Süd 1', 'Süd 2', 'Süd 3', 'Süd Garage'])
    expect(z[0].wert).toBe('950 W')
    // der Balken rechnet neu: jetzt ist Süd 2 der stärkste
    expect(z[1].breite).toBe(100)
  })

  it('ESC schließt das Fenster und meldet die Taste als verbraucht (preventDefault)', () => {
    const zu = vi.fn()
    oeffne(bestandD(), 600, 'pv_grp_sued', zu)
    const e = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    document.dispatchEvent(e)
    expect(e.defaultPrevented).toBe(true)
    expect(zu).toHaveBeenCalledTimes(1)
    // andere Tasten nicht
    const a = new KeyboardEvent('keydown', { key: 'a', bubbles: true, cancelable: true })
    document.dispatchEvent(a)
    expect(a.defaultPrevented).toBe(false)
    expect(zu).toHaveBeenCalledTimes(1)
  })

  it('in kleiner Fläche scrollt die Liste (eigener Scroll-Container unter dem Kopf)', () => {
    oeffne(bestandD(), 600, 'pv_grp_sued')
    const liste = document.body.querySelector('[data-gruppenliste="pv_grp_sued"]')!
    expect(liste.className).toMatch(/\boverflow-y-auto\b/)
    expect(liste.className).toMatch(/\bh-full\b/)
  })
})
