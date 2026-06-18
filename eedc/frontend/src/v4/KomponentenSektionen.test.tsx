import { describe, it, expect } from 'vitest'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { KOMPONENTEN_IDENTITAET } from '../lib'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

function d(over: Partial<AktuellerMonatResponse> = {}): AktuellerMonatResponse {
  // Basis = nichts aktiv; Tests aktivieren gezielt einzelne Komponenten.
  return {
    speicher_ladung_kwh: null, speicher_entladung_kwh: null, speicher_kapazitaet_kwh: null,
    speicher_wirkungsgrad_prozent: null, speicher_vollzyklen: null,
    wp_strom_kwh: null, wp_waerme_kwh: null, wp_heizung_kwh: null, wp_warmwasser_kwh: null, wp_ersparnis_euro: null,
    emob_ladung_kwh: null, emob_km: null, emob_ladung_pv_kwh: null, emob_verbrauch_100km: null, emob_ersparnis_euro: null,
    bkw_erzeugung_kwh: null, bkw_eigenverbrauch_kwh: null,
    sonstiges_erzeugung_kwh: null, sonstiges_verbrauch_kwh: null,
    ...over,
  } as AktuellerMonatResponse
}

describe('baueKomponentenBloecke — Aktiv-Gating', () => {
  it('keine Komponente aktiv → keine Blöcke', () => {
    expect(baueKomponentenBloecke(d())).toHaveLength(0)
  })

  it('nur aktive Komponenten erscheinen, in kanonischer Reihenfolge', () => {
    const bloecke = baueKomponentenBloecke(d({
      speicher_ladung_kwh: 99, speicher_vollzyklen: 7.7, speicher_wirkungsgrad_prozent: 73,
      wp_strom_kwh: 330, wp_waerme_kwh: 1240,
    }))
    expect(bloecke.map((b) => b.id)).toEqual(['k-speicher', 'k-waermepumpe'])
    // Sektions-Kopf-Identität kommt aus dem SoT (#3b', TYP_COLORS-Kanon) —
    // gegen die Quelle prüfen, kein hardcodiertes Duplikat.
    expect(bloecke[0].farbe).toBe(KOMPONENTEN_IDENTITAET['speicher'].farbe)
    expect(bloecke[1].farbe).toBe(KOMPONENTEN_IDENTITAET['waermepumpe'].farbe)
    expect(bloecke[1].title).toBe('Wärme/Klima')
  })

  it('Speicher-Summary trägt Ladung/Zyklen/η', () => {
    const b = baueKomponentenBloecke(d({ speicher_ladung_kwh: 99, speicher_vollzyklen: 7.7, speicher_wirkungsgrad_prozent: 73 }))[0]
    expect(b.summary).toMatch(/99 kWh geladen/)
    expect(b.summary).toMatch(/7,7 Zyklen/)
    expect(b.summary).toMatch(/73 % η/)
  })

  it('WP-Summary trägt JAZ (Wärme ÷ Strom)', () => {
    const b = baueKomponentenBloecke(d({ wp_strom_kwh: 330, wp_waerme_kwh: 1254 }))[0]
    expect(b.summary).toMatch(/JAZ 3,80/) // 1254/330 = 3,8
  })

  it('alle fünf Komponenten aktiv → fünf Blöcke (Sonstiges = Erzeuger-Variante)', () => {
    const bloecke = baueKomponentenBloecke(d({
      speicher_ladung_kwh: 99, wp_strom_kwh: 330, emob_ladung_kwh: 62,
      bkw_erzeugung_kwh: 612, sonstiges_erzeugung_kwh: 320,
    }))
    expect(bloecke.map((b) => b.id)).toEqual(['k-speicher', 'k-waermepumpe', 'k-emob', 'k-bkw', 'k-sonstiges-erzeuger'])
  })

  it('Sonstiges (#3c): Block heißt nach dem Gerät; Erzeuger/Verbraucher getrennt', () => {
    const bloecke = baueKomponentenBloecke(d({
      sonstiges_erzeugung_kwh: 120, sonstiges_verbrauch_kwh: 80,
      investitionen_financials: [
        { investition_id: 10, bezeichnung: 'Mini-BHKW', typ: 'sonstiges' },
      ] as unknown as AktuellerMonatResponse['investitionen_financials'],
    }))
    expect(bloecke.map((b) => b.id)).toEqual(['k-sonstiges-erzeuger', 'k-sonstiges-verbraucher'])
    expect(bloecke[0].title).toBe('Mini-BHKW')
    expect(bloecke[1].title).toBe('Mini-BHKW')
  })

  it('Sonstiges ohne Investitionsnamen → Fallback „Sonstiges"', () => {
    const bloecke = baueKomponentenBloecke(d({ sonstiges_erzeugung_kwh: 120 }))
    expect(bloecke[0].title).toBe('Sonstiges')
  })
})
