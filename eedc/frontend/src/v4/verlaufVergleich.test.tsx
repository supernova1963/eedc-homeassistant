import { describe, it, expect } from 'vitest'
import {
  VERLAUF_PRESETS, verfuegbarePresets, sichtbareSerien, verlaufTabellenSpalten,
  tagDrillInPfad, monatDrillInPfad, datumAusQuery, monatRefAusQuery,
} from './verlaufVergleich'

describe('verlaufVergleich — Presets + Jahr-only-Filter', () => {
  it('Jahr-Sicht zeigt alle Presets inkl. E-Auto', () => {
    const keys = verfuegbarePresets(true).map((p) => p.key)
    expect(keys).toEqual(['verbrauch', 'erzeugung', 'ertrag', 'batterie', 'emob'])
  })

  it('Monat-Sicht blendet das E-Auto-Preset aus (nurJahr)', () => {
    const keys = verfuegbarePresets(false).map((p) => p.key)
    expect(keys).not.toContain('emob')
    expect(keys).toEqual(['verbrauch', 'erzeugung', 'ertrag', 'batterie'])
  })

  it('Batterie-Preset: Netzladung nur in der Jahr-Sicht', () => {
    const batterie = VERLAUF_PRESETS.find((p) => p.key === 'batterie')!
    const jahr = sichtbareSerien(batterie, true).map((s) => s.key)
    const monat = sichtbareSerien(batterie, false).map((s) => s.key)
    expect(jahr).toContain('netzladung')
    expect(monat).not.toContain('netzladung')
    expect(monat).toEqual(['speicherLadung', 'speicherEntladung'])
  })

  it('E-Auto-Preset: Fahrleistung liegt auf der km-Achse', () => {
    const emob = VERLAUF_PRESETS.find((p) => p.key === 'emob')!
    expect(emob.serien.find((s) => s.key === 'eautoKm')?.achse).toBe('km')
  })
})

describe('verlaufVergleich — Drill-in (B3)', () => {
  it('tagDrillInPfad → Cockpit/Tag mit ?datum=', () => {
    expect(tagDrillInPfad('2026-05-10')).toBe('/cockpit/tag?datum=2026-05-10')
  })

  it('monatDrillInPfad → Cockpit/Monat mit ?jahr=&monat=', () => {
    expect(monatDrillInPfad(2026, 5)).toBe('/cockpit/monat?jahr=2026&monat=5')
  })

  it('datumAusQuery: gültiges ISO-Datum durchreichen, sonst null', () => {
    expect(datumAusQuery(new URLSearchParams('datum=2026-05-10'))).toBe('2026-05-10')
    expect(datumAusQuery(new URLSearchParams('datum=foo'))).toBeNull()
    expect(datumAusQuery(new URLSearchParams(''))).toBeNull()
  })

  it('monatRefAusQuery: gültiges jahr/monat, Monat 1–12, sonst null', () => {
    expect(monatRefAusQuery(new URLSearchParams('jahr=2026&monat=5'))).toEqual({ jahr: 2026, monat: 5 })
    expect(monatRefAusQuery(new URLSearchParams('jahr=2026&monat=13'))).toBeNull()
    expect(monatRefAusQuery(new URLSearchParams('jahr=2026&monat=0'))).toBeNull()
    expect(monatRefAusQuery(new URLSearchParams('jahr=1822&monat=5'))).toBeNull()
    expect(monatRefAusQuery(new URLSearchParams('monat=5'))).toBeNull()
  })
})

describe('verlaufVergleich — Tabellen-Spalten (Paket CT)', () => {
  it('Monat-Sicht: Union der Chart-Serien ohne nurJahr-Spalten, Autarkie zuletzt', () => {
    const keys = verlaufTabellenSpalten(false).map((s) => s.key)
    expect(keys).toEqual([
      'eigenverbrauch', 'einspeisung', 'netzbezug', 'direktverbrauch', 'speicherEntladung',
      'pvAnlage', 'bkw', 'neg51', 'speicherLadung', 'autarkie',
    ])
  })

  it('Jahr-Sicht ergänzt Netzladung + E-Auto (gleiche Datengrenze wie der Chart)', () => {
    const keys = verlaufTabellenSpalten(true).map((s) => s.key)
    expect(keys).toContain('netzladung')
    expect(keys).toContain('eautoLadung')
    expect(keys).toContain('eautoKm')
  })

  it('Einheiten: kWh-Mengen + Fahrleistung km + Autarkie %', () => {
    const spalten = verlaufTabellenSpalten(true)
    expect(spalten.find((s) => s.key === 'eautoKm')?.einheit).toBe('km')
    expect(spalten.find((s) => s.key === 'autarkie')?.einheit).toBe('%')
    expect(spalten.filter((s) => s.einheit === 'kWh').length).toBeGreaterThanOrEqual(9)
  })
})
