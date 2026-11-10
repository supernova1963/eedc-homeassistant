/**
 * E4 (4) «Daten-Checker: Sprung aufs Feld» im Komponenten-Formular (Entscheid Master H-E4-B, Option A).
 *
 * `feld=<key>` landet auf `name="<key>"` bzw. `name="param_<key>"`. Liegt das Feld in einem zugeklappten Abschnitt
 * (`FormSection variant="erweitert"`), startet der Abschnitt offen, solange `SprungFeldKontext` einen Sprung trägt —
 * ohne Sprung bleibt er zu wie bisher. Die Hervorhebung ist der Fokus des Eingabefelds (bestehende Fokus-Optik).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import InvestitionForm from './InvestitionForm'
import { SprungFeldKontext, feldSelektor, useAufFeldSpringen } from '../../lib/sprungFeld'
import type { Investition } from '../../types'

vi.mock('../../api/investitionen', () => ({
  investitionenApi: { list: vi.fn(() => Promise.resolve([])) },
}))

const eauto: Investition = { id: 5, anlage_id: 1, typ: 'e-auto', bezeichnung: 'Zoe', anschaffungsdatum: '2024-01-01', aktiv: true }
const speicher: Investition = {
  id: 7, anlage_id: 1, typ: 'speicher', bezeichnung: 'AC-Speicher', anschaffungsdatum: '2024-06-01', aktiv: true,
  parameter: { kapazitaet_kwh: 10, arbitrage_faehig: true },
}

function MitSprung({ feld, investition, onFertig }: { feld: string | null; investition: Investition; onFertig: () => void }) {
  const selektor = feld ? feldSelektor(feld) : null
  useAufFeldSpringen(selektor, onFertig)
  return (
    <SprungFeldKontext.Provider value={selektor}>
      <InvestitionForm anlageId={1} typ={investition.typ} investition={investition} onSubmit={vi.fn()} onCancel={() => {}} />
    </SprungFeldKontext.Provider>
  )
}

// Feste Uhr (Wächter N7): nur `Date` — die Wartezeit des Sprungs (`setTimeout`) läuft echt.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-11-10T12:00:00'))
  Element.prototype.scrollIntoView = vi.fn()
})
afterEach(() => { vi.useRealTimers() })

describe('Komponenten-Formular: Sprung aufs Feld (E4)', () => {
  it('Spalte im zugeklappten Abschnitt «Weitere Angaben & Kosten»: Abschnitt offen, Feld fokussiert', async () => {
    const fertig = vi.fn()
    render(<MitSprung feld="anschaffungskosten_alternativ" investition={eauto} onFertig={fertig} />)
    await waitFor(() => expect(fertig).toHaveBeenCalled())
    const feld = document.querySelector('[name="anschaffungskosten_alternativ"]')
    expect(feld).not.toBeNull()
    expect(document.activeElement).toBe(feld)
  })

  it('Typ-Parameter (Lab-Punkt arbitrage_ladepreis_fehlt): `param_`-Feld in «Netzladung & Arbitrage» fokussiert', async () => {
    const fertig = vi.fn()
    render(<MitSprung feld="lade_durchschnittspreis_cent" investition={speicher} onFertig={fertig} />)
    await waitFor(() => expect(fertig).toHaveBeenCalled())
    expect(document.activeElement).toBe(document.querySelector('[name="param_lade_durchschnittspreis_cent"]'))
  })

  it('Datumsfeld und Schalter tragen ihren Anker (`data-feld`)', async () => {
    const fertig = vi.fn()
    render(<MitSprung feld="aktiv" investition={eauto} onFertig={fertig} />)
    await waitFor(() => expect(fertig).toHaveBeenCalled())
    expect(document.querySelector('[data-feld="anschaffungsdatum"]')).not.toBeNull()
    expect(document.querySelector('[data-feld="aktiv"]')!.contains(document.activeElement)).toBe(true)
  })

  it('ohne Sprung bleibt der Abschnitt zu', async () => {
    render(<MitSprung feld={null} investition={eauto} onFertig={vi.fn()} />)
    await waitFor(() => expect(document.querySelector('[name="bezeichnung"]')).not.toBeNull())
    expect(document.querySelector('[name="anschaffungskosten_alternativ"]')).toBeNull()
  })
})
