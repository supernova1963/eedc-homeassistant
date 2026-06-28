import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { isValidElement } from 'react'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { KOMPONENTEN_IDENTITAET } from '../lib'
import type { Block } from '../components/blocks'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

/** Park-Stub: alles geparkt (Element-Park-Doktrin — leerer Block verschwindet). */
const ALLES_GEPARKT: ParkApi = {
  aktiv: true, istGeparkt: () => true, park: () => {}, entparke: () => {}, zuruecksetzen: () => {}, geparkt: [],
}

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
      bkw_erzeugung_kwh: 612,
      sonstiges_geraete: [{ bezeichnung: 'Mini-BHKW', kategorie: 'erzeuger', erzeugung_kwh: 320 }],
    }))
    // Default-Reihenfolge = INVESTITION_TYP_ORDER (SoT): Speicher → Balkonkraftwerk
    // → Wärmepumpe → E-Mobilität → Sonstiges (BKW vor WP).
    expect(bloecke.map((b) => b.id)).toEqual(['k-speicher', 'k-bkw', 'k-waermepumpe', 'k-emob', 'k-sonstiges-erzeuger'])
  })

  it('Sonstiges-Sonderdarstellung: 2 feste Blöcke (Erzeuger/Verbraucher), pro Gerät eigene Werte-Zeile', () => {
    const bloecke = baueKomponentenBloecke(d({
      sonstiges_geraete: [
        { bezeichnung: 'Mini-BHKW', kategorie: 'erzeuger', erzeugung_kwh: 120 },
        { bezeichnung: 'Heizstab Warmwasser', kategorie: 'verbraucher', verbrauch_kwh: 80 },
      ],
    }))
    // Feste, generische Block-Titel (NICHT der Gerätename) — der Gerätename steht
    // PRO Gerät im Block-Inhalt.
    expect(bloecke.map((b) => b.id)).toEqual(['k-sonstiges-erzeuger', 'k-sonstiges-verbraucher'])
    expect(bloecke[0].title).toBe('Sonstiges – Erzeuger')
    expect(bloecke[1].title).toBe('Sonstiges – Verbraucher')
    // Pro-Gerät-Zeile: Bezeichnung erscheint im gerenderten Block-Inhalt.
    renderBlock(bloecke, 'k-sonstiges-verbraucher')
    expect(screen.getByText('Heizstab Warmwasser')).toBeInTheDocument()
  })

  it('Sonstiges nur Erzeuger → nur Erzeuger-Block (generischer Titel)', () => {
    const bloecke = baueKomponentenBloecke(d({
      sonstiges_geraete: [{ bezeichnung: 'Mini-BHKW', kategorie: 'erzeuger', erzeugung_kwh: 120 }],
    }))
    expect(bloecke.map((b) => b.id)).toEqual(['k-sonstiges-erzeuger'])
    expect(bloecke[0].title).toBe('Sonstiges – Erzeuger')
  })

  it('Element-Park: alle Elemente geparkt → keine Blöcke (Block-Hide-Doktrin)', () => {
    const data = d({
      speicher_ladung_kwh: 99, wp_strom_kwh: 330, emob_ladung_kwh: 62, bkw_erzeugung_kwh: 612,
      sonstiges_geraete: [{ bezeichnung: 'Mini-BHKW', kategorie: 'erzeuger', erzeugung_kwh: 320 }],
    })
    expect(baueKomponentenBloecke(data, ALLES_GEPARKT)).toHaveLength(0)
  })
})

// E-Gegencheck: periodensinnvolle IST-Detailwerte in die Komponenten-Blöcke übernommen.
function renderBlock(bloecke: Block[], id: string) {
  const b = bloecke.find((x) => x.id === id)!
  const node = b.render(false)
  if (!isValidElement(node)) throw new Error('render() ergab kein Element')
  return render(node)
}

describe('Komponenten-Detail (E-Gegencheck)', () => {
  it('Speicher: Netzladung + Bilanz + Wirkungsverluste (€)', () => {
    const bloecke = baueKomponentenBloecke(d({
      speicher_ladung_kwh: 100, speicher_entladung_kwh: 90, speicher_ladung_netz_kwh: 0,
      einspeise_preis_cent: 8, netzbezug_preis_cent: 30,
    }))
    renderBlock(bloecke, 'k-speicher')
    expect(screen.getByText('Netzladung (Arbitrage)')).toBeInTheDocument()
    expect(screen.getByText(/Bilanz \(Entladung − Ladung\)/)).toBeInTheDocument()
    // Verlust 10 kWh × 100 % PV × 8 ct = 0,80 €
    expect(screen.getByText('Wirkungsverluste (Opportunitätskosten)')).toBeInTheDocument()
    expect(screen.getByText('−0,80 €')).toBeInTheDocument()
  })

  it('Wärmepumpe: #238 Kompressor-Starts + Betriebsstunden (Σ Monat) + Strom-Split', () => {
    const bloecke = baueKomponentenBloecke(d({
      wp_strom_kwh: 330, wp_waerme_kwh: 1254,
      wp_starts_max_tag: 5, wp_starts_summe_monat: 120,
      wp_betriebsstunden_max_tag: 8.5, wp_betriebsstunden_summe_monat: 210,
      wp_strom_heizen_kwh: 200, wp_strom_warmwasser_kwh: 130,
    }))
    renderBlock(bloecke, 'k-waermepumpe')
    expect(screen.getByText('Kompressor-Starts')).toBeInTheDocument()
    expect(screen.getByText('120')).toBeInTheDocument()
    expect(screen.getByText('Betriebsstunden')).toBeInTheDocument()
    expect(screen.getByText('Stromverbrauch · davon Heizung')).toBeInTheDocument()
    expect(screen.getByText('Stromverbrauch · davon Warmwasser')).toBeInTheDocument()
  })

  it('WP ohne Counter-Daten: keine #238-Kacheln', () => {
    const bloecke = baueKomponentenBloecke(d({ wp_strom_kwh: 330, wp_waerme_kwh: 1254 }))
    renderBlock(bloecke, 'k-waermepumpe')
    expect(screen.queryByText('Kompressor-Starts')).not.toBeInTheDocument()
    expect(screen.queryByText('Betriebsstunden')).not.toBeInTheDocument()
  })

  it('E-Mobilität: Netz-Anteil + extern + V2H-Rückspeisung', () => {
    const bloecke = baueKomponentenBloecke(d({
      emob_ladung_kwh: 62, emob_ladung_netz_kwh: 20, emob_ladung_extern_kwh: 5, emob_v2h_kwh: 3,
    }))
    renderBlock(bloecke, 'k-emob')
    expect(screen.getByText('Ladung · Netz-Anteil')).toBeInTheDocument()
    expect(screen.getByText('Ladung · extern')).toBeInTheDocument()
    expect(screen.getByText('V2H-Rückspeisung')).toBeInTheDocument()
  })
})

describe('Geräte-Hinweis (Aggregation kenntlich machen)', () => {
  it('mehrere Geräte im Block → „Aggregiert aus …" mit Namen (E-Mob: Auto + Wallbox)', () => {
    const bloecke = baueKomponentenBloecke(d({
      emob_ladung_kwh: 62,
      komponenten_geraete: { 'e-auto': ['Tesla Model 3'], 'wallbox': ['go-eCharger'] },
    }))
    renderBlock(bloecke, 'k-emob')
    expect(screen.getByText(/Aggregiert aus:/)).toBeInTheDocument()
    expect(screen.getByText(/Tesla Model 3 · go-eCharger/)).toBeInTheDocument()
  })

  it('nur ein Gerät → kein Hinweis', () => {
    const bloecke = baueKomponentenBloecke(d({
      speicher_ladung_kwh: 99,
      komponenten_geraete: { 'speicher': ['BYD HVS'] },
    }))
    renderBlock(bloecke, 'k-speicher')
    expect(screen.queryByText(/Aggregiert aus/)).not.toBeInTheDocument()
  })
})
