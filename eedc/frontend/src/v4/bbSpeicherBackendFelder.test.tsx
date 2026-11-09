/**
 * Päckchen BB (9.11.2026): Speicher-Bilanz und Wirkungsverluste (Nachlauf: E-Mobilität am Tag, N-783) kommen als
 * Felder aus dem Backend — Monat/Jahr als
 * `computed_field` der Antwort, Tag aus `tag-detail` (durchgereicht von `baueTagAlsMonat`).
 *
 * Je Stelle zwei Aussagen: (1) die Sicht zeigt den Wert des Feldes, (2) ohne das Feld rechnet sie NICHT selbst nach,
 * obwohl Ladung und Entladung in der Antwort stehen. Die Gleichheit Backend = alte Client-Formel ist auf den
 * Demo-Kopien gemessen (Bericht `PAECKCHEN-BB-2026-11-09.md`) und in `test_bb_speicher_tag_felder.py` festgehalten.
 */
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { baueTagAlsMonat } from './TagKomponenten'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { TagDetail } from '../api/energie_profil'
import { aktuellerMonat, tagWerte } from '../test/factories'

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date('2026-07-27T12:00:00')) })
afterEach(() => { cleanup(); vi.useRealTimers() })

function speicherText(d: AktuellerMonatResponse, periode: 'monat' | 'tag' = 'monat') {
  const b = baueKomponentenBloecke(d, NOOP, periode).find((x) => x.id === 'k-speicher')
  expect(b, 'k-speicher muss entstehen').toBeDefined()
  cleanup()
  return render(<>{b!.render(false)}</>).container.textContent ?? ''
}

const SPEICHER = { speicher_ladung_kwh: 100, speicher_entladung_kwh: 90, einspeise_preis_cent: 8, netzbezug_preis_cent: 30 }

describe('Speicher — Bilanz und Wirkungsverluste aus dem Backend', () => {
  it('zeigt die Felder der Antwort (Werte, die aus 100/90 nicht folgen)', () => {
    const t = speicherText(aktuellerMonat(2026, 6, {
      ...SPEICHER, speicher_bilanz_kwh: -12.3, speicher_wirkungsverluste_euro: 4.56,
      speicher_verlust_pv_kwh: 7, speicher_verlust_netz_kwh: 0,
    }))
    expect(t).toContain('-12,3 kWh')
    expect(t).toContain('−4,56 €')
  })

  it('ohne Felder rechnet die Sicht nicht nach — keine Bilanz-, keine Verlust-Zeile', () => {
    const t = speicherText(aktuellerMonat(2026, 6, SPEICHER))
    expect(t).not.toContain('Bilanz (Entladung − Ladung)')
    expect(t).not.toContain('Wirkungsverluste')
  })
})

describe('Tag — baueTagAlsMonat reicht die Felder des Tagesdetails durch', () => {
  it('Bilanz und Wirkungsverluste kommen aus `tag-detail`, nicht aus Ladung − Entladung der Tageszeile', () => {
    const tag = tagWerte('2026-07-26', { speicher_ladung: 10, speicher_entladung: 8 })
    const detail = {
      speicher_bilanz_kwh: -1.5, speicher_wirkungsverluste_euro: 0.33, speicher_verlust_pv_kwh: 1.5,
      speicher_verlust_netz_kwh: 0, speicher_netzladung_anteil_gekappt: false, einspeise_preis_cent: 8,
    } as unknown as TagDetail
    const d = baueTagAlsMonat(tag, [], [], detail)
    expect(d.speicher_bilanz_kwh).toBe(-1.5)
    expect(d.speicher_wirkungsverluste_euro).toBe(0.33)
    const t = speicherText(d, 'tag')
    expect(t).toContain('-1,5 kWh')
    expect(t).toContain('−0,33 €')
  })

  it('ohne Tagesdetail fehlen beide Zeilen statt einer Client-Rechnung', () => {
    const d = baueTagAlsMonat(tagWerte('2026-07-26', { speicher_ladung: 10, speicher_entladung: 8 }), [], [], null)
    expect(d.speicher_bilanz_kwh).toBeNull()
    const t = speicherText(d, 'tag')
    expect(t).not.toContain('Bilanz (Entladung − Ladung)')
  })
})

// ── Nachlauf BB2 (N-783): E-Mobilität am Tag aus dem Tagesdetail ─────────────────────────────────────────────────
function emobText(d: AktuellerMonatResponse): string | null {
  const b = baueKomponentenBloecke(d, NOOP, 'tag').find((x) => x.id === 'k-emob')
  if (!b) return null
  cleanup()
  return render(<>{b.render(false)}</>).container.textContent ?? ''
}

describe('Tag — E-Mobilität aus `tag-detail` (N-783, Zählerpfad vor Leistungspfad im Backend)', () => {
  it('Tag ohne Stunden-Serie, Tagesdetail mit Ladung ⇒ der Block ist da (Produktiv-Box 6.8.2026: 11,81 kWh ⇒ «12», 68 %)', () => {
    const detail = {
      emob_ladung_kwh: 11.81, emob_ladung_quelle: 'zaehler', emob_ladung_pv_kwh: 8.0,
      emob_pv_anteil_prozent: (8.0 / 11.81) * 100, emob_km: 26,
    } as unknown as TagDetail
    const d = baueTagAlsMonat(tagWerte('2026-08-06'), [], [], detail)
    expect(d.emob_ladung_kwh).toBe(11.81)
    const t = emobText(d)
    expect(t).not.toBeNull()
    expect(t).toContain('Ladung gesamt12')
    expect(t).toContain('68')
    expect(t).toContain('26')
  })

  it('Stunden-Serien allein erzeugen keinen Block mehr — die Summe rechnet das Backend', () => {
    const stunden = [{ stunde: 10, komponenten: { wallbox_5: -7.5 } }] as unknown as Parameters<typeof baueTagAlsMonat>[1]
    const serien = [{ key: 'wallbox_5', label: 'WB', typ: 'wallbox', kategorie: 'wallbox', seite: 'senke' }] as unknown as Parameters<typeof baueTagAlsMonat>[2]
    const d = baueTagAlsMonat(tagWerte('2026-08-06'), stunden, serien, null)
    expect(d.emob_ladung_kwh).toBeNull()
    expect(d.emob_pv_anteil_prozent).toBeNull()
    expect(emobText(d)).toBeNull()
  })
})
