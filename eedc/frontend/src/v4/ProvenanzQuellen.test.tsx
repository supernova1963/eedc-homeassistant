/**
 * ProvenanzQuellen — die geteilte „Quellen:"-Zeile (#360).
 *
 * Sichert die Auflöse-Regel selbst (Label-SoT, Dedup, Teilzeitraum-Grenze) und
 * die Abgrenzung E3: die Jahres-Sicht ruft OHNE Monatskontext und bekommt
 * deshalb nie einen Zeitraum ans Badge.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { provenanzQuellen } from './ProvenanzQuellen'
import { JahrHeader } from './JahrRahmen'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

const JULI = { start: new Date(2025, 6, 1), tage: 31 }

const quellen = (feld_quellen: Record<string, unknown>) =>
  feld_quellen as unknown as AktuellerMonatResponse['feld_quellen']

describe('provenanzQuellen', () => {
  it('Roh-Enum → Label aus der SoT-Map, je Quelle genau ein Eintrag', () => {
    const q = provenanzQuellen(quellen({
      pv_erzeugung_kwh: { quelle: 'ha_statistics', konfidenz: 95 },
      netzbezug_kwh: { quelle: 'ha_statistics', konfidenz: 95 },
      einspeisung_kwh: { quelle: 'local_connector', konfidenz: 90 },
    }))
    expect(q.map((e) => e.label)).toEqual(['HA-Statistik', 'Connector'])
    expect(q.every((e) => e.zusatz === undefined)).toBe(true)
  })

  it('Teilabdeckung nur MIT Monatskontext', () => {
    const fq = quellen({
      pv_erzeugung_kwh: {
        quelle: 'local_connector', konfidenz: 90,
        abdeckung_von: '2025-07-28T14:03:00', abdeckung_bis: '2025-07-30T09:12:00',
      },
    })
    expect(provenanzQuellen(fq)[0].zusatz).toBeUndefined()
    expect(provenanzQuellen(fq, JULI)[0].zusatz).toBe('28.–30.07.2025')
  })

  it('fehlendes Bis-Datum → „ab TT.MM.JJJJ" statt halbem Zeitraum', () => {
    const q = provenanzQuellen(quellen({
      pv_erzeugung_kwh: { quelle: 'local_connector', konfidenz: 90, abdeckung_von: '2025-07-28T14:03:00' },
    }), JULI)
    expect(q[0].zusatz).toBe('ab 28.07.2025')
    expect(q[0].titel).toContain('erst ab dem 28.07.2025')
  })

  it('Zeitraum unter einem Tag wird nicht auf 0 gerundet behauptet', () => {
    const q = provenanzQuellen(quellen({
      pv_erzeugung_kwh: {
        quelle: 'local_connector', konfidenz: 90,
        abdeckung_von: '2025-07-30T08:00:00', abdeckung_bis: '2025-07-30T18:00:00',
      },
    }), JULI)
    expect(q[0].titel).toContain('unter 1 von 31 Tagen')
  })
})

describe('JahrHeader — E3: kein Zeitraum in der Jahres-Sicht', () => {
  it('Connector-Badge bleibt ohne Zeitraum, auch bei Teilabdeckung', () => {
    const d = {
      feld_quellen: {
        pv_erzeugung_kwh: {
          quelle: 'local_connector', konfidenz: 90,
          abdeckung_von: '2025-07-28T14:03:00', abdeckung_bis: '2025-07-30T09:12:00',
        },
      },
    } as unknown as AktuellerMonatResponse
    render(<JahrHeader jahr={2025} laufend d={d} />)
    expect(screen.getByText('Connector')).toBeInTheDocument()
    expect(screen.queryByText(/Connector \(/)).not.toBeInTheDocument()
  })
})
