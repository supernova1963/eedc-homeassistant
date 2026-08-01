/**
 * Strompreise — „Aktuell" trägt genau der Tarif, mit dem eedc rechnet.
 *
 * Auslöser Forum simon42 #89667/67 (Algie): drei Tarife, drei grüne „Aktuell"-Badges.
 * Gerechnet wurde korrekt mit dem jüngsten — die Liste behauptete etwas anderes als
 * die Rechnung. Die Auswahl spiegelt jetzt
 * `backend/api/routes/strompreise.py::lade_tarife_fuer_anlage`: gültig am Stichtag UND
 * je Verwendung der jüngste `gueltig_ab`.
 */
import { describe, it, expect } from 'vitest'
import type { Strompreis } from '../types'
import { aktuelleTarifIds, istGueltigHeute } from './StrompreiseTeile'

const tarif = (id: number, gueltig_ab: string, felder: Partial<Strompreis> = {}): Strompreis => ({
  id, anlage_id: 1, gueltig_ab, gueltig_bis: null,
  netzbezug_arbeitspreis_cent_kwh: 30, einspeiseverguetung_cent_kwh: 8.2,
  ...felder,
} as unknown as Strompreis)

const inZukunft = () => {
  const d = new Date()
  d.setFullYear(d.getFullYear() + 1)
  return d.toISOString().split('T')[0]
}

describe('aktuelleTarifIds', () => {
  it('markiert bei mehreren offenen Einträgen nur den jüngsten (Algie-Fall)', () => {
    const ids = aktuelleTarifIds([
      tarif(1, '2023-07-01'),
      tarif(2, '2025-04-01'),
      tarif(3, '2026-04-01'),
    ])

    expect([...ids]).toEqual([3])
  })

  it('trennt nach Verwendung — Standard und Spezialtarif sind gleichzeitig aktuell', () => {
    const ids = aktuelleTarifIds([
      tarif(1, '2024-01-01'),
      tarif(2, '2025-01-01'),
      tarif(3, '2025-01-01', { verwendung: 'waermepumpe' }),
    ])

    expect(ids.has(2)).toBe(true)
    expect(ids.has(3)).toBe(true)
    expect(ids.has(1)).toBe(false)
  })

  it('ignoriert einen Tarif, der erst in der Zukunft gilt', () => {
    const ids = aktuelleTarifIds([
      tarif(1, '2025-01-01'),
      tarif(2, inZukunft()),
    ])

    expect([...ids]).toEqual([1])
  })

  it('ignoriert einen abgelaufenen Tarif trotz jüngerem Beginn', () => {
    const ids = aktuelleTarifIds([
      tarif(1, '2020-01-01'),
      tarif(2, '2024-01-01', { gueltig_bis: '2024-12-31' }),
    ])

    expect([...ids]).toEqual([1])
  })

  it('liefert leer, wenn kein Tarif heute gilt', () => {
    expect(aktuelleTarifIds([tarif(1, inZukunft())]).size).toBe(0)
  })
})

describe('istGueltigHeute', () => {
  it('bleibt das reine Gültigkeits-Prädikat — auch für historische Einträge ohne Ende', () => {
    expect(istGueltigHeute(tarif(1, '2023-07-01'))).toBe(true)
    expect(istGueltigHeute(tarif(2, inZukunft()))).toBe(false)
  })
})
