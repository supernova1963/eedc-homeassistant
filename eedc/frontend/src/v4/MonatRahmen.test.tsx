import { describe, it, expect } from 'vitest'
import { finanzTeaserBlock, communityBlock } from './MonatRahmen'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { MonatsVergleich } from '../api/community'

const d = {
  netto_ertrag_euro: 128, einspeise_erloes_euro: 15, ev_ersparnis_euro: 120, netzbezug_kosten_euro: 7,
  autarkie_prozent: 61, eigenverbrauch_quote_prozent: 54, einspeisung_kwh: 189, netzbezug_kwh: 143,
  feld_quellen: {},
} as unknown as AktuellerMonatResponse

describe('finanzTeaserBlock', () => {
  it('Block mit Netto-Ertrag-Summary + Cross-Link-Heimat', () => {
    const b = finanzTeaserBlock(d)
    expect(b.id).toBe('finanzen')
    expect(b.summary).toMatch(/\+128,00 € Netto-Ertrag/)
  })
})

describe('communityBlock — data-gated (O4)', () => {
  it('null wenn keine Anlagen im Monat', () => {
    const v = { anzahl_anlagen: 0 } as MonatsVergleich
    expect(communityBlock(v, d, 'Mai')).toBeNull()
  })

  it('Block mit Anlagenzahl-Summary wenn Daten vorhanden', () => {
    const v = {
      anzahl_anlagen: 2,
      autarkie: { durchschnitt: 60, median: 58, min: 40, max: 80, anzahl_anlagen: 2 },
    } as MonatsVergleich
    const b = communityBlock(v, d, 'Mai')
    expect(b).not.toBeNull()
    expect(b!.id).toBe('community')
    expect(b!.summary).toMatch(/2 Anlagen im Mai/)
  })

  it('Singular bei genau einer Anlage', () => {
    const v = { anzahl_anlagen: 1 } as MonatsVergleich
    expect(communityBlock(v, d, 'Mai')!.summary).toMatch(/1 Anlage im Mai/)
  })
})
