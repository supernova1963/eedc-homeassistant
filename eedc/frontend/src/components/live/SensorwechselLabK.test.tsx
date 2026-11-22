/**
 * Sensorwechsel — Korrekturrunde «Lab-K» (Wortlaute aus den Lab-Durchläufen 1 und 2a), Client-Seite. Der Client rechnet
 * nichts: er setzt die Zahlen des Backends mit Ein- oder Mehrzahl (`lib/plural.ts`) und nennt den zulässigen Bereich.
 *
 * W1 «1 Tage» → «1 Tag» (Fortschritt, Dialog) · W2 «Eigene Werte seit … (n Tage)» mit der Zahl des Backends · F5 der Dialog
 * nennt den zulässigen Bereich von «Der neue Sensor zählt ab» · W8 «Aus Home Assistant neu übernehmen» in Klartext statt
 * «Zeitabschnitte: 23». Je Probe ein benannter Sprengsatz im Text (die alte Fassung wäre hier rot).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import SensorwechselDialog, { ZAEHLT_AB_BEREICH, werteSatz } from './SensorwechselDialog'
import { ANSETZEN_FERTIG_TAGE, fortschrittSatz, tageText } from './KorrekturFortschritt'
import { SPIEGEL_SATZ, vorschauAussage } from '../datenchecker/vorschauZeile'
import type { BleibenAngaben, KorrekturLaufStand, QuellePruefung } from '../../api/datenquellen'
import type { RepairPlan } from '../../api/repair'

beforeEach(() => { vi.useFakeTimers({ now: new Date(2026, 10, 20, 1, 30), shouldAdvanceTime: true }) })
afterEach(() => { vi.useRealTimers() })

const lauf = (over: Partial<KorrekturLaufStand>): KorrekturLaufStand => ({
  lauf: 'abc', art: 'ansetzen', status: 'fertig', tage: 1, erledigt: 1, fehler: [], beginn: null, ende: null,
  fuellen_offen: false, ...over,
} as KorrekturLaufStand)

describe('Lab-K W1 — Ein- und Mehrzahl', () => {
  it('ein Tag: «1 Tag neu gebildet» (Sprengsatz: «1 Tage»)', () => {
    expect(fortschrittSatz(lauf({ tage: 1 }))).toBe(ANSETZEN_FERTIG_TAGE(tageText(1)))
    expect(fortschrittSatz(lauf({ tage: 1 }))).toBe('Werte nach dem Sensorwechsel neu gelesen, 1 Tag neu gebildet.')
    expect(fortschrittSatz(lauf({ tage: 2 }))).toContain('2 Tage neu gebildet.')
    expect(fortschrittSatz(lauf({ tage: 1 }))).not.toContain('1 Tage')
  })
  it('ein Tag mit Fehler: «1 Tag konnte nicht neu gebildet werden.»', () => {
    const z = lauf({ art: 'korrektur' as KorrekturLaufStand['art'], tage: 3, fehler: [{ tag: '2026-11-01', grund: 'x' }] })
    expect(fortschrittSatz(z)).toBe('3 Tage neu gebildet. 1 Tag konnte nicht neu gebildet werden.')
  })
})

const FRAGE: QuellePruefung = {
  grund_erforderlich: true, erster_wert: '2026-10-08T00:00:00', tage: 1, stand_alt: 6117.8, stand_neu: 1.8,
  sensor_key: 'inv:42:pv_erzeugung_kwh', label: 'P1b – PV-Erzeugung', verzeichnet: true,
  bleiben: null,
}

describe('Lab-K W2 — eigene Werte seit', () => {
  it('nennt den frühesten eigenen Wert und die Tage des Backends mit Einzahl (Sprengsatz: «(1 Tage)»)', () => {
    expect(werteSatz(FRAGE)).toBe(
      'Eigene Werte seit 08.10.2026 (1 Tag). Letzter Stand der bisherigen Quelle: 6.117,8. Stand der neuen Quelle jetzt: 1,8.')
    expect(werteSatz({ ...FRAGE, tage: 43 })).toContain('(43 Tage)')
  })
})

describe('Lab-K F5 — zulässiger Bereich von «Der neue Sensor zählt ab»', () => {
  it('der Hinweis am Feld nennt Anfang und Ende des Bereichs (Sprengsatz: nur der allgemeine Hinweis)', () => {
    const bleiben: BleibenAngaben = {
      wartet: null, seit: '2026-10-08T00:00:00', ueberlappung: true, zaehlt_ab: '2026-11-20T01:00:00',
      zaehlt_ab_vorgabe: '2026-11-20T01:00:00', zaehlt_ab_frueheste: '2026-11-20T00:00:00',
      zaehlt_ab_spaeteste: '2026-11-20T01:00:00', stunden: 0, tage: 0, monate: [], saetze: ['Satz des Backends.'],
    }
    render(<SensorwechselDialog isOpen fragen={[{ ...FRAGE, bleiben }]}
      onBestaetigen={vi.fn()} onAbbrechen={vi.fn()} />)
    ;(document.querySelector('input[type="radio"][value="fortsetzung"]') as HTMLInputElement).click()
    expect(screen.getByText(new RegExp(ZAEHLT_AB_BEREICH('20.11.2026 00:00', '20.11.2026 01:00').replace(/[.()]/g, '\\$&'))))
      .toBeTruthy()
  })
})

const plan = (over: Partial<RepairPlan>): RepairPlan => ({
  plan_id: 'p', anlage_id: 6, operation: 'spiegel_abgleich_tag', operation_params: {}, created_at: '2026-11-20T02:12:00',
  expires_at: '2026-11-20T03:12:00', estimated_changes: {}, diff_preview: [], diff_total_count: 0, warnings: [],
  operation_preview: {}, ...over,
} as RepairPlan)

describe('Lab-K W8 — «Aus Home Assistant neu übernehmen» in Klartext', () => {
  it('nennt Zähler und Tage im Satz, keine «Zeitabschnitte» (Sprengsatz: die Zählerzeile)', () => {
    const a = vorschauAussage(plan({ estimated_changes: { spiegel_kanaele: 13, spiegel_abschnitte: 23, tage_neu_aufgebaut: 1 } }))
    expect(a.satz).toBe(`${SPIEGEL_SATZ(13, 1)} — wirksam, wenn du in Home Assistant korrigiert hast`)
    expect(a.satz).toBe('eedc übernimmt die Statistik von 13 Zählern neu aus Home Assistant und baut 1 Tag neu auf — '
      + 'wirksam, wenn du in Home Assistant korrigiert hast')
    expect(a.satz).not.toContain('Zeitabschnitte')
    expect(SPIEGEL_SATZ(1, 0)).toBe('eedc übernimmt die Statistik von 1 Zähler neu aus Home Assistant')
  })
})
