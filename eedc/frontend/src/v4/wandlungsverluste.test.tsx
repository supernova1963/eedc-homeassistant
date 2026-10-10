/**
 * Wandlungsverluste — angezeigt (HA-Bauform E4b, Wortlaut Gernot 06.10.2026); seit N-588 bewertet unter dem Messpunkt-Vertrag.
 *
 * Drei Orte, EINE Konstante (`lib/wandlungsverluste.ts`): Unterzeile am Label „PV-Erzeugung" in der Vergleichstabelle
 * von Cockpit → Monat und Cockpit → Jahr, eine Zeile im Block „Verlauf" des PV-Hubs (gesamte Historie). Sichtbar nur
 * mit Wert > 0 — das Backend liefert `null` ohne Anlagenzähler bzw. ohne Kanal-Deckung; bei 0 keine Zeile (kein
 * „0,0 kWh", kein „—"). Wert und Prozent kommen aus dem Layer; der Client formatiert nur.
 *
 * Schwesterdateien: backend/tests/test_wandlungsverluste_anzeige.py, KomponentenTypV4.herkunft.test.tsx,
 * JahrBilanz.hinweise.test.tsx.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ThemeProvider } from '../context/ThemeContext'
import { MonatBilanz } from './MonatBilanz'
import { JahrBilanz } from './JahrBilanz'
import { geraetBloecke } from './KomponentenTypV4'
import {
  VERLUSTE_GRUND_TEXT, WANDLUNGSVERLUSTE_HINWEIS, WANDLUNGSVERLUSTE_LABEL, verlusteGrundSatz,
  wandlungsverlusteUnterzeile, wandlungsverlusteVerlaufZeile, wandlungsverlusteWert,
} from '../lib/wandlungsverluste'
import { aktuellerMonat, monatsZeile } from '../test/factories'
import { stubMatchMedia } from '../test/render'
import type { ParkApi } from '../components/park'
import type { KompGeraet } from './komponentenAdapter'
import type { Investition } from '../types'

const ZEILE = 'Wandlungsverluste 36,0 kWh (5,7 %)'

describe('lib/wandlungsverluste — Wortlaut und Sichtbarkeit', () => {
  it('Bezeichnung und Hinweistext sind wortgleich mit dem freigegebenen Wortlaut', () => {
    expect(WANDLUNGSVERLUSTE_LABEL).toBe('Wandlungsverluste')
    // N-588 (Vorlage Fassung 2, B2): Ersparnis, USt und CO₂ ziehen die Verluste ab, die Bilanz trägt sie.
    expect(WANDLUNGSVERLUSTE_HINWEIS).toBe(
      'Differenz zwischen der Summe der String-Zähler (vor dem Wechselrichter) und dem Anlagenzähler (dahinter). '
      + 'Ersparnis, USt und CO₂ rechnen mit dem Eigenverbrauch ohne diese Verluste; '
      + 'Bilanz, Autarkie und Eigenverbrauchsquote tragen sie weiter.',
    )
  })

  it('N-588: mit Grund nennt der Tooltip, warum die Verluste nicht bewertet sind; ohne Grund nicht', () => {
    const mit = wandlungsverlusteUnterzeile({ wandlungsverluste_kwh: 36, wandlungsverluste_prozent: 5.7,
      verluste_grund: 'dc_speicher_angenommen' })
    expect(mit?.hinweis).toBe(`${WANDLUNGSVERLUSTE_HINWEIS} ${verlusteGrundSatz('dc_speicher_angenommen')}`)
    expect(verlusteGrundSatz('dc_speicher_angenommen')).toContain('Speicher-Kopplung nicht gepflegt, als DC angenommen')
    expect(wandlungsverlusteUnterzeile({ wandlungsverluste_kwh: 36, wandlungsverluste_prozent: 5.7 })?.hinweis)
      .toBe(WANDLUNGSVERLUSTE_HINWEIS)
  })

  it.each(Object.keys(VERLUSTE_GRUND_TEXT))('Grund %s hat einen Satz', (g) => {
    expect(verlusteGrundSatz(g)).toMatch(/^Angezeigt, nicht bewertet: .+\.$/)
  })

  it('formatiert kWh und Prozent mit je einer Nachkommastelle, Leerzeichen vor %', () => {
    expect(wandlungsverlusteWert(36, 36 / 630 * 100)).toBe('36,0 kWh (5,7 %)')
    expect(wandlungsverlusteWert(1234.56, 2.04)).toBe('1.234,6 kWh (2,0 %)')
  })

  it.each([[null], [undefined], [0], [0.04], [-3]])('keine Zeile bei %s', (kwh) => {
    expect(wandlungsverlusteWert(kwh as number | null | undefined, 1)).toBeNull()
  })
})

describe('Cockpit → Monat: Unterzeile unter „PV-Erzeugung"', () => {
  const d = (over = {}) => aktuellerMonat(2026, 6, {
    pv_erzeugung_kwh: 630, einspeisung_kwh: 180, netzbezug_kwh: 72, eigenverbrauch_kwh: 450, gesamtverbrauch_kwh: 522,
    ...over,
  })
  const rendere = (over = {}) => render(<MonatBilanz d={d(over)} vm={monatsZeile(2026, 5, {})} glMonStats={null} monatName="Juni" />)

  it('sichtbar mit Wert > 0 (mobil und Tabelle), Hinweistext als Tooltip derselben Zeile', () => {
    rendere({ wandlungsverluste_kwh: 36, wandlungsverluste_prozent: 36 / 630 * 100 })
    expect(screen.getAllByText(ZEILE)).toHaveLength(2)
  })

  it.each([
    ['ohne Anlagenzähler (null)', { wandlungsverluste_kwh: null, wandlungsverluste_prozent: null }],
    ['ohne Feld', {}],
    ['bei 0', { wandlungsverluste_kwh: 0, wandlungsverluste_prozent: 0 }],
  ])('keine Zeile %s', (_n, over) => {
    rendere(over)
    expect(screen.queryByText(/Wandlungsverluste/)).toBeNull()
  })

  it('die Kachel „PV-Erzeugung" bleibt unberührt (ihre Zweitzeile trägt weiter SOLL/VM)', () => {
    rendere({ wandlungsverluste_kwh: 36, wandlungsverluste_prozent: 5.7 })
    // Die Zeile steht nur in der Vergleichstabelle (mobil + Tabelle), nicht ein drittes Mal in der Kachel.
    expect(screen.getAllByText(/Wandlungsverluste/)).toHaveLength(2)
  })
})

describe('Cockpit → Jahr: Unterzeile unter „PV-Erzeugung"', () => {
  beforeEach(() => { stubMatchMedia() })
  const rendere = (over = {}) => render(
    <ThemeProvider>
      <JahrBilanz d={aktuellerMonat(2026, 0, { monat_name: '2026', pv_erzeugung_kwh: 630, ...over })}
        vj={null} oj={null} ojCount={0} />
    </ThemeProvider>,
  )

  it('sichtbar mit Wert > 0', () => {
    rendere({ wandlungsverluste_kwh: 36, wandlungsverluste_prozent: 36 / 630 * 100 })
    expect(screen.getAllByText(ZEILE)).toHaveLength(2)
  })

  it.each([
    ['ohne Anlagenzähler (null)', { wandlungsverluste_kwh: null }],
    ['bei 0', { wandlungsverluste_kwh: 0, wandlungsverluste_prozent: 0 }],
  ])('keine Zeile %s', (_n, over) => {
    rendere(over)
    expect(screen.queryByText(/Wandlungsverluste/)).toBeNull()
  })
})

describe('PV-Hub → Verlauf: eine Zeile über die gesamte Historie', () => {
  const NICHTS_GEPARKT: ParkApi = {
    aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {}, zuruecksetzen: () => {},
    geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
  }
  const geraet = (zeile: NonNullable<KompGeraet['verlauf']>['zeile']): KompGeraet => ({
    inv: { id: 0, anlage_id: 1, typ: 'pv-module', bezeichnung: 'PV-Anlage', aktiv: true } as Investition,
    label: 'PV-Anlage',
    status: [],
    verlauf: {
      bars: [{ key: 'm11', label: 'Süd', farbe: 'bg-red-500', stapel: 'erz' }],
      rows: [{ name: '2026', m11: 630 }],
      gestapelt: true,
      zeile,
    },
  })
  const verlauf = (g: KompGeraet) => {
    const b = geraetBloecke(g, 'pv-module', 1, NICHTS_GEPARKT, {}, () => {}).find((x) => x.id === 'verlauf')
    if (!b) throw new Error('Verlauf-Block fehlt')
    return b
  }

  it('Zeile aus der Übersicht (Summe + Prozent vom Backend)', () => {
    const zeile = wandlungsverlusteVerlaufZeile({ wandlungsverluste_kwh: 36, wandlungsverluste_prozent: 36 / 630 * 100 })
    expect(zeile).toEqual({ text: ZEILE, hinweis: WANDLUNGSVERLUSTE_HINWEIS, titel: 'Wandlungsverluste' })
    render(<>{verlauf(geraet(zeile)).render(false)}</>)
    expect(screen.getByText(ZEILE)).toBeInTheDocument()
  })

  it.each([
    ['ohne Anlagenzähler', { wandlungsverluste_kwh: null, wandlungsverluste_prozent: null }],
    ['bei 0', { wandlungsverluste_kwh: 0, wandlungsverluste_prozent: 0 }],
  ])('keine Zeile %s', (_n, u) => {
    const zeile = wandlungsverlusteVerlaufZeile(u)
    expect(zeile).toBeNull()
    render(<>{verlauf(geraet(zeile)).render(false)}</>)
    expect(screen.queryByText(/Wandlungsverluste/)).toBeNull()
  })
})
