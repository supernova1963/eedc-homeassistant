import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { ManuelleWerteHinweis } from './ManuelleWerteHinweis'

/**
 * Der Hinweis ist das, was den Überschreiben-Haken vertretbar macht (12.08.,
 * #349): Seitdem ersetzt der Haken auch von Hand gepflegte Werte. Ohne die
 * Ansage vorher wäre aus einer Bevormundung ein stiller Datenverlust geworden
 * — diese Proben halten fest, dass sie erscheint, wann sie erscheint, und dass
 * ein Fehler beim Abruf den Import nicht blockiert.
 */

const getManuelleWerte = vi.fn()
vi.mock('../../api/portalImport', () => ({
  portalImportApi: {
    getManuelleWerte: (...a: unknown[]) => getManuelleWerte(...a),
  },
}))

beforeEach(() => {
  getManuelleWerte.mockReset()
})

describe('ManuelleWerteHinweis', () => {
  it('schweigt, solange der Haken aus ist — und fragt gar nicht erst', () => {
    render(
      <ManuelleWerteHinweis anlageId={1} perioden={['2024-06']} aktiv={false} />,
    )
    expect(getManuelleWerte).not.toHaveBeenCalled()
    expect(screen.queryByText(/gepflegt/)).toBeNull()
  })

  it('schweigt, wenn nichts von Hand gepflegt ist', async () => {
    getManuelleWerte.mockResolvedValue({
      betroffen: false, monate: 0, felder: 0, beispiele: [],
    })
    render(
      <ManuelleWerteHinweis anlageId={1} perioden={['2024-06']} aktiv />,
    )
    await waitFor(() => expect(getManuelleWerte).toHaveBeenCalled())
    expect(screen.queryByText(/gepflegt/)).toBeNull()
  })

  it('nennt Anzahl, Monate und Beispiele', async () => {
    getManuelleWerte.mockResolvedValue({
      betroffen: true, monate: 3, felder: 6,
      beispiele: ['06/2024: einspeisung_kwh', '07/2024: pv_erzeugung_kwh'],
    })
    render(
      <ManuelleWerteHinweis
        anlageId={1}
        perioden={['2024-06', '2024-07']}
        aktiv
      />,
    )
    expect(await screen.findByText(/6 Werte in 3 Monaten/)).toBeTruthy()
    expect(screen.getByText(/einspeisung_kwh/)).toBeTruthy()
    // Der Ausweg gehört dazu — sonst ist es eine Drohung statt einer Auskunft.
    expect(screen.getByText(/Ohne den Haken/)).toBeTruthy()
  })

  it('beugt den Singular', async () => {
    getManuelleWerte.mockResolvedValue({
      betroffen: true, monate: 1, felder: 1, beispiele: [],
    })
    render(<ManuelleWerteHinweis anlageId={1} perioden={['2024-06']} aktiv />)
    expect(await screen.findByText(/1 Wert in einem Monat/)).toBeTruthy()
  })

  /**
   * ⚠ **Grenze dieser Probe, gemessen statt behauptet.** Ein Sprengsatz, der
   * den `.catch()`-Zweig der Komponente entfernt, lässt sie **grün** — ohne
   * `catch` wird `setInfo` schlicht nie gerufen, `info` bleibt `null`, und für
   * den Anwender sieht beides gleich aus. Geprüft ist damit die *Wirkung*
   * (ein gescheiterter Abruf zeigt nichts und hält nichts auf), **nicht** das
   * Vorhandensein der Fehlerbehandlung; die verhindert zusätzlich eine
   * unbehandelte Promise-Ablehnung in der Konsole und bleibt richtig.
   */
  it('zeigt nichts und hält nichts auf, wenn der Abruf scheitert', async () => {
    getManuelleWerte.mockRejectedValue(new Error('Netz weg'))
    render(<ManuelleWerteHinweis anlageId={1} perioden={['2024-06']} aktiv />)
    await waitFor(() => expect(getManuelleWerte).toHaveBeenCalled())
    expect(screen.queryByText(/gepflegt/)).toBeNull()
  })

  it('fragt ohne gewählte Monate nicht an', () => {
    render(<ManuelleWerteHinweis anlageId={1} perioden={[]} aktiv />)
    expect(getManuelleWerte).not.toHaveBeenCalled()
  })
})
