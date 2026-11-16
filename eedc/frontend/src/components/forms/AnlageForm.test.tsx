import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import AnlageForm from './AnlageForm'
import type { Anlage } from '../../types'
import { anlagenApi } from '../../api/anlagen'

// Bewertungsgrenze E5 (2026-08-16): Das Inbetriebnahme-Datum ist inzwischen mehr
// als nachrichtlich — es sagt, ab wann eedc Zählerwerte erwartet. Hier ist es
// trotzdem bewusst KEIN Pflichtfeld (Entscheid Gernot): Wer eine Bestandsanlage
// bearbeitet, will meist etwas ganz anderes ändern und soll dabei nicht
// aufgehalten werden. Es gibt eine Warnung — und das Speichern läuft weiter.
// Pflicht ist es nur im Setup-Wizard (`setup-wizard/steps/AnlageStep.test.tsx`),
// den Bestand holt der Daten-Checker (STAMMDATEN, seit demselben Tag ERROR).

vi.mock('../../hooks/useHAAvailable', () => ({ useHAVerbunden: () => false }))
vi.mock('../../api/wetter', () => ({ wetterApi: { getProvider: vi.fn(() => new Promise(() => {})) } }))
vi.mock('../../api/anlagen', () => ({ anlagenApi: { geocode: vi.fn() } }))
vi.mock('./VersorgerSection', () => ({ default: () => null }))
vi.mock('./AnlagenfotoSection', () => ({ default: () => null }))

const WARNUNG = /Fehlt — ohne dieses Datum weiß eedc nicht/i

function anlage(installationsdatum: string | undefined): Anlage {
  return {
    id: 1,
    anlagenname: 'Bestandsanlage',
    leistung_kwp: 9.8,
    installationsdatum,
  } as Anlage
}

describe('AnlageForm — Inbetriebnahme fehlt', () => {
  it('warnt, wenn das Datum fehlt', () => {
    render(<AnlageForm anlage={anlage(undefined)} onSubmit={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByText(WARNUNG)).toBeInTheDocument()
  })

  it('schweigt, wenn das Datum gepflegt ist', () => {
    render(<AnlageForm anlage={anlage('2023-06-01')} onSubmit={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.queryByText(WARNUNG)).not.toBeInTheDocument()
  })

  it('speichert trotz fehlendem Datum — die Warnung blockiert nicht', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<AnlageForm anlage={anlage(undefined)} onSubmit={onSubmit} onCancel={vi.fn()} />)

    // Eine ganz andere Änderung, so wie im echten Fall (PLZ nachtragen).
    fireEvent.change(screen.getByLabelText(/PLZ/i), {
      target: { name: 'standort_plz', value: '12345' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Speichern|Aktualisieren/i }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0][0].standort_plz).toBe('12345')
    expect(onSubmit.mock.calls[0][0].installationsdatum).toBeUndefined()
  })
})

// Geokodierung (16.11.2026): das Formular übergibt die Straße wie der Setup-Wizard, und das Straßenfeld löst die
// Ermittlung aus wie PLZ und Ort. Von Hand eingetragene oder geladene Koordinaten bleiben unangetastet.
describe('AnlageForm — Koordinaten aus der Adresse', () => {
  const geocode = vi.mocked(anlagenApi.geocode)
  const feld = (c: HTMLElement, name: string) => c.querySelector(`input[name="${name}"]`) as HTMLInputElement
  const tippen = (c: HTMLElement, name: string, value: string) => {
    fireEvent.change(feld(c, name), { target: { name, value } })
    fireEvent.blur(feld(c, name))
  }
  const treffer = (lat: number, lon: number) =>
    ({ latitude: lat, longitude: lon, display_name: 'x', erkanntes_land: 'DE' })

  it('übergibt die Straße, und das Straßenfeld präzisiert die eben ermittelten Koordinaten', async () => {
    geocode.mockReset()
    geocode.mockResolvedValueOnce(treffer(50.1, 7.1)).mockResolvedValueOnce(treffer(50.2, 7.2))
    const { container } = render(<AnlageForm onSubmit={vi.fn()} onCancel={vi.fn()} />)

    tippen(container, 'standort_plz', '50667')
    await waitFor(() => expect(feld(container, 'latitude').value).toBe('50.100000'))
    expect(geocode).toHaveBeenLastCalledWith('50667', undefined, undefined)

    tippen(container, 'standort_strasse', 'Rathausplatz 2')
    await waitFor(() => expect(feld(container, 'latitude').value).toBe('50.200000'))
    expect(geocode).toHaveBeenLastCalledWith('50667', undefined, 'Rathausplatz 2')
    expect(feld(container, 'longitude').value).toBe('7.200000')
  })

  it('lässt geladene Koordinaten stehen, auch wenn die Straße sich ändert', async () => {
    geocode.mockReset()
    const bestand = { ...anlage('2023-06-01'), standort_plz: '50667', latitude: 50.9, longitude: 7.4 } as Anlage
    const { container } = render(<AnlageForm anlage={bestand} onSubmit={vi.fn()} onCancel={vi.fn()} />)
    tippen(container, 'standort_strasse', 'Rathausplatz 2')
    await waitFor(() => expect(feld(container, 'standort_strasse').value).toBe('Rathausplatz 2'))
    expect(geocode).not.toHaveBeenCalled()
    expect(feld(container, 'latitude').value).toBe('50.9')
  })

  it('lässt von Hand geänderte Koordinaten stehen, auch nach einer Ermittlung', async () => {
    geocode.mockReset()
    geocode.mockResolvedValue(treffer(50.1, 7.1))
    const { container } = render(<AnlageForm onSubmit={vi.fn()} onCancel={vi.fn()} />)
    tippen(container, 'standort_plz', '50667')
    await waitFor(() => expect(feld(container, 'latitude').value).toBe('50.100000'))

    fireEvent.change(feld(container, 'latitude'), { target: { name: 'latitude', value: '50.93' } })
    tippen(container, 'standort_strasse', 'Rathausplatz 2')
    await waitFor(() => expect(feld(container, 'standort_strasse').value).toBe('Rathausplatz 2'))
    expect(geocode).toHaveBeenCalledTimes(1)
    expect(feld(container, 'latitude').value).toBe('50.93')
  })
})
