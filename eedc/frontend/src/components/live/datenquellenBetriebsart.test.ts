/**
 * datenquellenBetriebsart — Blockregel und Blockkopf-Status (P-433-2 S2, E3).
 *
 * Die Fälle je Bauart kommen NICHT aus einer Client-Tabelle, sondern aus der Route
 * (`src/test/datenquellen-wp-faelle.json`, gehalten von
 * `backend/tests/test_p433_2_datenquellen_betriebsart.py::test_fixture_der_client_probe_ist_aktuell`).
 * Darunter Einzelproben der Status-Wörter an handgebauten Feldern.
 */
import { describe, it, expect } from 'vitest'
import type { DatenquelleFeld, DatenquelleGruppe } from '../../api/datenquellen'
import { WP_FAELLE, gruppeAusFall, type WpFall } from '../../test/datenquellenWpFaelle'
import { betriebsartBloecke, blockSichtbar, blockStatus, feldZeichen, statusKontext } from './datenquellenBetriebsart'

type Fall = WpFall

function kopf(name: Fall): Record<string, string | null> {
  const g = gruppeAusFall(name)
  const ctx = statusKontext(g)
  return Object.fromEntries(betriebsartBloecke(g).map((b) => {
    const st = blockStatus(b, ctx)
    return [b.betriebsart, st ? `${st.zeichen ? `${st.zeichen} ` : ''}${st.text}` : null]
  }))
}

describe('Blöcke je Bauart — über die Route', () => {
  it('luft_wasser ohne Kühlung: Gerät · Heizen · Warmwasser — kein Kühlen-Block, Lüften/Entfeuchten hinter «Weitere Größen»', () => {
    expect(kopf('luft_wasser')).toEqual({
      geraet: '⊘ fehlt: Strom, Wärme', heizen: '⊘ fehlt: Strom, Wärme', warmwasser: '⊘ fehlt: Strom, Wärme',
    })
  })

  it('luft_luft: die Betriebsarten des Klimageräts — kein Warmwasser-Block', () => {
    expect(kopf('luft_luft')).toEqual({
      geraet: '⊘ fehlt: Strom, Wärme', heizen: '⊘ fehlt: Strom, Wärme',
      kuehlen: '⊘ fehlt: Strom, Wärme', lueften: '⊘ fehlt: Strom, Wärme', entfeuchten: '⊘ fehlt: Strom, Wärme',
    })
  })

  it('brauchwasser: kein Heizen-Block, kein Kühlen-Block', () => {
    expect(kopf('brauchwasser')).toEqual({ geraet: '⊘ fehlt: Strom, Wärme', warmwasser: '⊘ fehlt: Strom, Wärme' })
  })

  it('MartyBr: Kühl-Leistung ohne Stammdatum steht oben, weil zugeordnet — der Block hat keinen Status', () => {
    const g = gruppeAusFall('martybr')
    const kuehlen = betriebsartBloecke(g).find((b) => b.betriebsart === 'kuehlen')
    expect(kuehlen?.felder.map((f) => f.feld)).toEqual(['leistung_kuehlen_w'])
    expect(kopf('martybr').kuehlen).toBeNull()
  })

  it('Sole, passiv gekühlt, ohne Kühlzähler: Kopf «passiv»; Wärme gesamt Σ durch die Heizwärme gedeckt', () => {
    expect(kopf('sole_passiv_ohne_kuehlfeld')).toEqual({
      geraet: '● vollständig', heizen: '⊘ fehlt: Strom', warmwasser: '⊘ fehlt: Strom, Wärme', kuehlen: 'passiv',
    })
  })

  it('Mathek (Sole, getrennte Messung, passiv): Heizen und Warmwasser vollständig, Kühlen passiv', () => {
    expect(kopf('mathek')).toEqual({
      geraet: '● vollständig', heizen: '● vollständig', warmwasser: '● vollständig', kuehlen: 'passiv',
    })
  })

  it('pipp086: der Betriebsart-Zähler Heizen steht im Block Heizen', () => {
    const g = gruppeAusFall('pipp086')
    const heizen = betriebsartBloecke(g).find((b) => b.betriebsart === 'heizen')
    expect(heizen?.felder.map((f) => f.feld)).toEqual(['heizenergie_kwh', 'betriebsart_strom_heizen_kwh', 'leistung_heizen_w'])
    expect(kopf('pipp086').heizen).toBe('⊘ fehlt: Wärme')
  })

  it('Betriebsmodus-Sensor + Gesamtstrom: Heizen, Warmwasser und Kühlen «aus Betriebsmodus abgeleitet»', () => {
    expect(kopf('betriebsmodus')).toEqual({
      geraet: '● vollständig', heizen: 'Σ aus Betriebsmodus abgeleitet',
      warmwasser: 'Σ aus Betriebsmodus abgeleitet · fehlt: Wärme', kuehlen: 'Σ aus Betriebsmodus abgeleitet · fehlt: Wärme',
    })
  })

  it('jeder Block ordnet kWh vor W vor Sonstigen, ohne erweiterte Felder', () => {
    for (const name of WP_FAELLE) {
      for (const b of betriebsartBloecke(gruppeAusFall(name))) {
        expect(b.felder.every((f) => !f.erweitert)).toBe(true)
        const rang = b.felder.map((f) => (f.einheit === 'kWh' ? 0 : f.einheit === 'W' ? 1 : 2))
        expect(rang).toEqual([...rang].sort())
      }
    }
  })
})

const feld = (p: Partial<DatenquelleFeld>): DatenquelleFeld => ({
  id: p.feld ?? 'x', feld: 'x', typ: 'waermepumpe', label: p.feld ?? 'x', einheit: 'kWh', kategorie: 'energy',
  hinweis: '', standard_topic: '', quelle: 'keine', gateway_topic: null, ha_entity: null, invertieren: false,
  wert: null, wert_zeit: null, probleme: [], bedarf: 'optional', bedarf_grund: null, bedarf_text: null, ...p,
})

describe('Blockregel und Zeichen', () => {
  it('sichtbar ⇔ ein Feld nicht erweitert (die Kühlung wirkt über die Registry, nicht hier)', () => {
    const erw = [feld({ erweitert: true, betriebsart: 'lueften' })]
    expect(blockSichtbar(erw)).toBe(false)
    expect(blockSichtbar([...erw, feld({ betriebsart: 'lueften' })])).toBe(true)
    expect(blockSichtbar([])).toBe(false)
  })

  it('● Sensor · Σ durch andere gedeckt · ⊘ keine', () => {
    expect(feldZeichen({ quelle: 'ha_app', bedarf: 'pflicht' })).toBe('●')
    expect(feldZeichen({ quelle: 'keine', bedarf: 'inaktiv' })).toBe('Σ')
    expect(feldZeichen({ quelle: 'keine', bedarf: 'pflicht' })).toBe('⊘')
  })

  it('«aus Betriebsmodus abgeleitet» nur mit Gesamtstrom — ohne ihn gibt es nichts aufzuteilen', () => {
    const b = { betriebsart: 'heizen', alleFelder: [feld({ betriebsart: 'heizen', menge: 'waerme', quelle: 'ha_app' })] }
    const ctx = { kuehlungArt: 'keine', modusAbleitbar: ['heizen'], modusZugeordnet: true, geraetStromGedeckt: false }
    expect(blockStatus(b, ctx)?.text).toBe('fehlt: Strom')
    expect(blockStatus(b, { ...ctx, geraetStromGedeckt: true })?.text).toBe('aus Betriebsmodus abgeleitet')
    expect(blockStatus(b, { ...ctx, modusAbleitbar: [] })?.text).toBe('vollständig')
  })

  it('«passiv» weicht, sobald ein Kühlzähler misst', () => {
    const ctx = { kuehlungArt: 'passiv', modusAbleitbar: ['kuehlen'], modusZugeordnet: false, geraetStromGedeckt: true }
    const leer = [feld({ betriebsart: 'kuehlen', menge: 'strom' })]
    expect(blockStatus({ betriebsart: 'kuehlen', alleFelder: leer }, ctx)?.text).toBe('passiv')
    const mitZaehler = [feld({ betriebsart: 'kuehlen', menge: 'strom', quelle: 'ha_app' })]
    expect(blockStatus({ betriebsart: 'kuehlen', alleFelder: mitZaehler }, ctx)?.text).toBe('vollständig')
  })

  it('kein Status ohne Mengen-Feld in der ersten Reihe (nur Leistung/Temperatur)', () => {
    const ctx = { kuehlungArt: 'keine', modusAbleitbar: ['warmwasser'], modusZugeordnet: true, geraetStromGedeckt: true }
    expect(blockStatus({ betriebsart: 'warmwasser', alleFelder: [feld({ einheit: 'W', menge: null })] }, ctx)).toBeNull()
  })

  it('ein Feld ohne Betriebsart (älteres Backend) zählt zum Gerät', () => {
    const g: DatenquelleGruppe = { id: 'inv:1', titel: 'WP', typ: 'waermepumpe', felder: [feld({ feld: 'a' })] }
    expect(betriebsartBloecke(g).map((b) => b.betriebsart)).toEqual(['geraet'])
  })
})
