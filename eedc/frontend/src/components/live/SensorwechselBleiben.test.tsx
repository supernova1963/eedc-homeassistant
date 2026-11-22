/**
 * Sensorwechsel U2 Lauf b «Fragen» — die eine Frage «bleiben oder verwerfen» zwischen zwei HA-Sensoren.
 *
 * (1) Mit `bleiben` (zwei HA-Sensoren, ohne Überlappung): «bleiben» nennt den Satz «wie Home Assistant», zeigt unter «Was danach
 * geschieht» die Sätze des Backends, **kein** Feld «Der neue Sensor zählt ab»; «Übernehmen» sendet ohne `zaehlt_ab`. (2) Mit
 * Überlappung: das Feld steht da, vorbelegt und begrenzt mit den Stunden der Antwort; eine andere Stunde holt die Vorschau neu
 * und wird gesendet; die Vorgabe selbst wird nicht gesendet. (3) Ein Wartegrund steht als Satz da (keine Zahl gerechnet).
 * (4) Ohne `bleiben` (jede andere Quelle) bleibt der bisherige Satz. (5) Der Lauf des Ansetzens heißt nicht «Korrektur».
 * (6) Wartende Wechsel an der Fläche zeigen den Satz des Backends. Der Client rechnet nichts.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import SensorwechselDialog, {
  GRUND_BLEIBEN_HA_FOLGE, GRUND_FORTSETZUNG, GRUND_FORTSETZUNG_FOLGE, GRUND_LOESCHEN, ZAEHLT_AB_LABEL,
} from './SensorwechselDialog'
import { ANSETZEN_FERTIG_TAGE, ANSETZEN_LAEUFT, WartendeWechsel, fortschrittSatz } from './KorrekturFortschritt'
import type { BleibenAngaben, KorrekturLaufStand, QuellePruefung } from '../../api/datenquellen'

const BLEIBEN: BleibenAngaben = {
  wartet: null, seit: '2026-11-10T07:00:00', ueberlappung: false, zaehlt_ab: '2026-11-10T07:00:00',
  zaehlt_ab_vorgabe: null, zaehlt_ab_frueheste: null, zaehlt_ab_spaeteste: null, stunden: 3, tage: 0, monate: [],
  saetze: ['Home Assistant führt sensor.neu seit 10.11.2026 07:00 Uhr.', 'Satz zum Umfang aus dem Backend.'],
}
const UEBERLAPPUNG: BleibenAngaben = {
  ...BLEIBEN, ueberlappung: true, zaehlt_ab: '2026-11-10T10:00:00', zaehlt_ab_vorgabe: '2026-11-10T10:00:00',
  zaehlt_ab_frueheste: '2026-11-09T01:00:00', zaehlt_ab_spaeteste: '2026-11-10T10:00:00',
  saetze: ['Beide Sensoren haben eine Zeit lang gleichzeitig gezählt.'],
}
const FRAGE: QuellePruefung = {
  grund_erforderlich: true, erster_wert: '2025-11-01T02:00:00', tage: 649, stand_alt: null, stand_neu: null,
  sensor_key: 'inv:2:ladung_kwh', label: 'Wallbox – Ladung', verzeichnet: true,
  bleiben: BLEIBEN,
}

// Feste Uhr (Wächter N7): die Fixtures tragen Datums-Literale.
beforeEach(() => { vi.useFakeTimers({ now: new Date(2026, 10, 19, 12, 0), shouldAdvanceTime: true }) })
afterEach(() => { vi.useRealTimers() })

const radio = (wert: 'fortsetzung' | 'korrektur' | 'loeschen') =>
  document.querySelector(`input[type="radio"][value="${wert}"]`) as HTMLInputElement

function dialog(f: QuellePruefung, extra: Partial<Parameters<typeof SensorwechselDialog>[0]> = {}) {
  const onBestaetigen = vi.fn()
  const onBleibenVorschau = vi.fn(() => Promise.resolve({ ...UEBERLAPPUNG, saetze: ['Vorschau an 07:00.'] }))
  render(<SensorwechselDialog isOpen fragen={[f]}
    onBleibenVorschau={onBleibenVorschau} onBestaetigen={onBestaetigen} onAbbrechen={vi.fn()} {...extra} />)
  return { onBestaetigen, onBleibenVorschau }
}

describe('Sensorwechsel U2 Lauf b — eine Frage: bleiben oder verwerfen', () => {
  it('(1) zwei HA-Sensoren ohne Überlappung: Sätze des Backends, kein Feld «zählt ab», sendet ohne zaehlt_ab', async () => {
    const { onBestaetigen } = dialog(FRAGE)
    expect(radio('fortsetzung').closest('label')?.textContent).toContain(GRUND_FORTSETZUNG)
    expect(radio('loeschen').closest('label')?.textContent).toContain(GRUND_LOESCHEN)
    expect(radio('korrektur')).toBeNull()                      // Weg B: kein «verwerfen» beim Wechsel
    expect(screen.getByText(GRUND_BLEIBEN_HA_FOLGE)).toBeInTheDocument()
    expect(screen.queryByText(GRUND_FORTSETZUNG_FOLGE)).toBeNull()
    fireEvent.click(radio('fortsetzung'))
    expect(screen.getByText('Satz zum Umfang aus dem Backend.')).toBeInTheDocument()
    expect(screen.queryByLabelText(ZAEHLT_AB_LABEL)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Übernehmen/ }))
    expect(onBestaetigen).toHaveBeenCalledWith({ 'inv:2:ladung_kwh': { grund: 'fortsetzung' } })
  })

  it('(2) Überlappung: Feld vorbelegt und begrenzt; eine andere Stunde holt die Vorschau und wird gesendet', async () => {
    const { onBestaetigen, onBleibenVorschau } = dialog({ ...FRAGE, bleiben: UEBERLAPPUNG })
    fireEvent.click(radio('fortsetzung'))
    const feld = screen.getByLabelText(ZAEHLT_AB_LABEL) as HTMLInputElement
    expect([feld.value, feld.min, feld.max]).toEqual(['2026-11-10T10:00', '2026-11-09T01:00', '2026-11-10T10:00'])
    fireEvent.click(screen.getByRole('button', { name: /Übernehmen/ }))
    expect(onBestaetigen).toHaveBeenLastCalledWith({ 'inv:2:ladung_kwh': { grund: 'fortsetzung' } })
    fireEvent.change(feld, { target: { value: '2026-11-10T07:00' } })
    expect(onBleibenVorschau).toHaveBeenCalledWith('inv:2:ladung_kwh', '2026-11-10T07:00')
    expect(await screen.findByText('Vorschau an 07:00.')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: /Übernehmen/ })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: /Übernehmen/ }))
    expect(onBestaetigen).toHaveBeenLastCalledWith({ 'inv:2:ladung_kwh': { grund: 'fortsetzung', zaehlt_ab: '2026-11-10T07:00' } })
  })

  it('(2b) eine Stunde, die das Backend ablehnt: Fehler im Dialog, «Übernehmen» gesperrt', async () => {
    dialog({ ...FRAGE, bleiben: UEBERLAPPUNG }, {
      onBleibenVorschau: vi.fn(() => Promise.reject(new Error('«Der neue Sensor zählt ab» muss zwischen … liegen.'))),
    })
    fireEvent.click(radio('fortsetzung'))
    fireEvent.change(screen.getByLabelText(ZAEHLT_AB_LABEL), { target: { value: '2026-11-10T11:00' } })
    expect(await screen.findByText('«Der neue Sensor zählt ab» muss zwischen … liegen.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Übernehmen/ })).toBeDisabled()
  })

  it('(3) Wartegrund: der Satz des Backends, kein Feld', () => {
    const satz = 'Home Assistant führt für sensor.neu noch keine Stundenwerte.'
    dialog({ ...FRAGE, bleiben: { ...BLEIBEN, wartet: 'noch_keine_zeile', seit: null, saetze: [satz] } })
    fireEvent.click(radio('fortsetzung'))
    expect(screen.getByText(satz)).toBeInTheDocument()
    expect(screen.queryByLabelText(ZAEHLT_AB_LABEL)).toBeNull()
  })

  it('(4) ohne bleiben (andere Quelle): der bisherige Satz', () => {
    render(<SensorwechselDialog isOpen fragen={[{ ...FRAGE, bleiben: null }]}
      onBestaetigen={vi.fn()} onAbbrechen={vi.fn()} />)
    expect(screen.getByText(GRUND_FORTSETZUNG_FOLGE)).toBeInTheDocument()
  })
})

describe('Sensorwechsel U2 Lauf b — Nachlauf und Wartegründe an der Fläche', () => {
  const stand = (z: Partial<KorrekturLaufStand>): KorrekturLaufStand => ({
    lauf: 'l', sensor_key: 'inv:2:ladung_kwh', status: 'laeuft', tage: 0, erledigt: 0, fehler: [], beginn: null, ende: null,
    fuellen_offen: false, ...z,
  })

  it('(5) der Lauf des Ansetzens heißt nicht «Korrektur»', () => {
    expect(fortschrittSatz(stand({ art: 'ansetzen' }))).toBe(ANSETZEN_LAEUFT)
    expect(fortschrittSatz(stand({ art: 'ansetzen', status: 'fertig', tage: 4, erledigt: 4 }))).toBe(ANSETZEN_FERTIG_TAGE('4 Tage'))
    expect(fortschrittSatz(stand({ art: 'ansetzen', tage: 4, erledigt: 1 }))).toBe('Tage werden im Hintergrund neu gebildet: 1 von 4.')
    for (const z of [stand({ art: 'ansetzen' }), stand({ art: 'ansetzen', status: 'fertig' })]) {
      expect(fortschrittSatz(z)).not.toMatch(/Korrektur/)
    }
    expect(fortschrittSatz(stand({}))).toBe('Korrektur läuft …')
  })

  it('(6) wartende Wechsel: Feld und Satz des Backends', () => {
    render(<WartendeWechsel liste={[{ sensor_key: 'inv:2:ladung_kwh', label: 'Wallbox – Ladung', wartet: 'ha_nicht_erreichbar',
      satz: 'Home Assistant ist gerade nicht erreichbar.' }]} />)
    expect(screen.getByText('Wallbox – Ladung')).toBeInTheDocument()
    expect(screen.getByText('Home Assistant ist gerade nicht erreichbar.')).toBeInTheDocument()
  })
})
