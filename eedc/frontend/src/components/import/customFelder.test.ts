/**
 * `vorlageFuerAnlage` — eine gespeicherte Vorlage verliert beim Laden die `inv:`-Zuordnungen, die die gewählte
 * Anlage nicht anbietet (N-705: fremde Anlage, gelöschte oder neu vergebene Investitions-ID).
 *
 * Schwesterprobe im Backend: `test_n705_custom_import_inv_id_der_anlage.py` (der Import prüft dieselbe Regel und
 * schreibt nie in eine fremde Anlage). Weitere Schwester: `custom/MappingTabelle.test.tsx`.
 */
import { describe, it, expect } from 'vitest'
import { vorlageFuerAnlage } from './customFelder'
import type { AnalyzeResult } from '../../api/customImport'

function analyse(ids: string[]): AnalyzeResult {
  return {
    spalten: [],
    investitions_felder: ids.map((id) => ({ id, label: id, required: false, group: 'inv_pv' })),
  } as unknown as AnalyzeResult
}

describe('vorlageFuerAnlage', () => {
  it('entfernt inv:-Zuordnungen, die die Anlage nicht anbietet, und nennt die Spalten', () => {
    const { mappings, entfernt } = vorlageFuerAnlage(
      {
        Jahr: 'jahr',
        Monat: 'monat',
        Ertrag: 'pv_erzeugung_kwh',
        Sued: 'inv:1:pv_erzeugung_kwh',
        Fremd: 'inv:15:pv_erzeugung_kwh',
        Weg: 'inv:4242:ladung_kwh',
      },
      analyse(['inv:1:pv_erzeugung_kwh']),
    )
    expect(mappings).toEqual({
      Jahr: 'jahr',
      Monat: 'monat',
      Ertrag: 'pv_erzeugung_kwh',
      Sued: 'inv:1:pv_erzeugung_kwh',
    })
    expect(entfernt).toEqual(['Fremd', 'Weg'])
  })

  it('lässt eine passende Vorlage unverändert', () => {
    const vorlage = { Jahr: 'jahr', Monat: 'monat', Sued: 'inv:1:pv_erzeugung_kwh' }
    const { mappings, entfernt } = vorlageFuerAnlage(vorlage, analyse(['inv:1:pv_erzeugung_kwh']))
    expect(mappings).toEqual(vorlage)
    expect(entfernt).toEqual([])
  })
})
