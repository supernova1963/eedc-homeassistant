/**
 * Zeitfenster (HT/NT) im Tarif-Formular — N-267, MeinerB in Discussion #380.
 *
 * Bernds Tarif: „täglich 19:00–20:00 nur 50 % des regulären Preises". Bis
 * v4.0.33 gab es dafür kein Feld; das Modell kannte nur Tage, keine Uhrzeit.
 *
 * ⚑ **Warum hier eine Probe TIPPT und nicht nur rendert.** Beim N-274-Bau
 * hatte der erste Entwurf bei jedem Tastendruck den Ladezustand gesetzt: das
 * Eingabefeld wurde ausgehängt, der Fokus war nach dem ersten Zeichen weg.
 * Das ist an `tsc` und an jedem Backend-Test vorbeigelaufen und nur aufgefallen,
 * weil eine Probe wirklich getippt hat. Diese Fläche hat **vier** Eingaben je
 * Fenster, also dieselbe Gefahr in vierfacher Ausführung.
 *
 * ⛔ Was hier NICHT geprüft wird, und zwar bewusst: die Umrechnung der Uhrzeit
 * auf den Backward-Slot (#144). Sie gehört ins Backend
 * (`core/berechnungen/zeittarif.py`) und ist dort gewächtert — sie im Client
 * nachzubauen wäre die zweite Wahrheit, gegen die ADR-001 gebaut ist.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import { StrompreisForm } from './StrompreiseTeile'
import type { Strompreis } from '../types'

const basis = (over: Partial<Strompreis> = {}): Strompreis => ({
  id: 1,
  anlage_id: 1,
  netzbezug_arbeitspreis_cent_kwh: 30,
  einspeiseverguetung_cent_kwh: 8,
  gueltig_ab: '2024-01-01',
  verwendung: 'allgemein',
  ...over,
}) as Strompreis

const zeigeNeu = (onCreate = vi.fn(async () => {})) => {
  render(<StrompreisForm anlageId={1} onCreate={onCreate} onCancel={() => {}} />)
  return onCreate
}

describe('Tarif-Formular — Zeitfenster (N-267)', () => {
  it('bietet die Fläche an, startet aber ohne Fenster', () => {
    zeigeNeu()
    expect(screen.getByText('Zeitfenster (HT/NT)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Zeitfenster hinzufügen/ })).toBeInTheDocument()
    // Kein Fenster ⇒ keine Eingabefelder. Die Fläche drängt sich nicht auf.
    expect(screen.queryByLabelText(/Von \(Uhr\)/)).not.toBeInTheDocument()
  })

  it('legt ein Fenster mit dem gemeldeten Fall als Vorbelegung an', () => {
    zeigeNeu()
    fireEvent.click(screen.getByRole('button', { name: /Zeitfenster hinzufügen/ }))

    expect(screen.getByLabelText(/Von \(Uhr\)/)).toHaveValue(19)
    expect(screen.getByLabelText(/Bis \(Uhr\)/)).toHaveValue(20)
    // „täglich" — Bernds Fall braucht keine Wochentag-Auswahl
    expect(screen.getByText(/täglich 19–20 Uhr/)).toBeInTheDocument()
  })

  it('⭐ behält beim Tippen den Fokus (die N-274-Falle)', () => {
    zeigeNeu()
    fireEvent.click(screen.getByRole('button', { name: /Zeitfenster hinzufügen/ }))

    const vorher = screen.getByLabelText(/Arbeitspreis/) as HTMLInputElement
    vorher.focus()
    expect(document.activeElement).toBe(vorher)

    // Zwei Eingaben nacheinander — jede loest ein Re-Render aus.
    fireEvent.change(vorher, { target: { value: '1' } })
    const nachErster = screen.getByLabelText(/Arbeitspreis/)
    fireEvent.change(nachErster, { target: { value: '15' } })
    const nachZweiter = screen.getByLabelText(/Arbeitspreis/)

    // Derselbe DOM-Knoten wie vor dem Tippen: haengt die Sicht das Feld
    // zwischendurch aus (N-274: `laedt` bei JEDEM Abruf gesetzt), ist es ein
    // anderer Knoten und der Fokus liegt auf document.body.
    expect(nachZweiter).toBe(vorher)
    expect(document.activeElement).toBe(nachZweiter)
    expect(nachZweiter).toHaveValue(15)
  })

  it('beschreibt das Fenster in Worten, samt Vergleich zum Hochtarif', () => {
    zeigeNeu()
    fireEvent.click(screen.getByRole('button', { name: /Zeitfenster hinzufügen/ }))
    fireEvent.change(screen.getByLabelText(/Arbeitspreis/), { target: { value: '15' } })

    expect(screen.getByText(/täglich 19–20 Uhr: 15,00 ct\/kWh statt 30,00/)).toBeInTheDocument()
  })

  it('nennt „über Mitternacht", wenn das Fenster den Tag wechselt', () => {
    zeigeNeu()
    fireEvent.click(screen.getByRole('button', { name: /Zeitfenster hinzufügen/ }))
    fireEvent.change(screen.getByLabelText(/Von \(Uhr\)/), { target: { value: '22' } })
    fireEvent.change(screen.getByLabelText(/Bis \(Uhr\)/), { target: { value: '6' } })

    expect(screen.getByText(/22–6 Uhr \(über Mitternacht\)/)).toBeInTheDocument()
  })

  it('das letzte Wochentag-Häkchen lässt sich nicht abwählen', () => {
    zeigeNeu()
    fireEvent.click(screen.getByRole('button', { name: /Zeitfenster hinzufügen/ }))

    // Sechs der sieben abwählen — der siebte muss bleiben.
    for (const tag of ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']) {
      fireEvent.click(screen.getByRole('button', { name: tag, pressed: true }))
    }
    expect(screen.getByRole('button', { name: 'So', pressed: true })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'So', pressed: true }))
    expect(screen.getByRole('button', { name: 'So', pressed: true })).toBeInTheDocument()
  })

  it('schickt das Fenster mit — als Uhrzeiten, nicht als Slots', async () => {
    const onCreate = zeigeNeu()
    fireEvent.click(screen.getByRole('button', { name: /Zeitfenster hinzufügen/ }))
    fireEvent.change(screen.getByLabelText(/Arbeitspreis/), { target: { value: '15' } })
    fireEvent.click(screen.getByRole('button', { name: /Speichern|Anlegen|Erstellen/ }))

    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1))
    const gesendet = (onCreate as unknown as { mock: { calls: [Record<string, unknown>][] } })
      .mock.calls[0][0]
    expect(gesendet.zeitfenster).toEqual([
      { von_stunde: 19, bis_stunde: 20, wochentage: '0123456', arbeitspreis_cent_kwh: 15 },
    ])
  })

  it('zeigt ein bestehendes Fenster beim Bearbeiten an', () => {
    render(
      <StrompreisForm
        anlageId={1}
        strompreis={basis({
          zeitfenster: [{
            id: 7, von_stunde: 22, bis_stunde: 6,
            wochentage: '01234', arbeitspreis_cent_kwh: 12,
          }],
        })}
        onUpdate={async () => {}}
        onCancel={() => {}}
      />,
    )
    expect(screen.getByLabelText(/Von \(Uhr\)/)).toHaveValue(22)
    expect(screen.getByText(/Mo, Di, Mi, Do, Fr 22–6 Uhr \(über Mitternacht\)/)).toBeInTheDocument()
  })

  it('ein entferntes Fenster wird als leere Liste geschickt, nicht weggelassen', async () => {
    const onUpdate = vi.fn(async () => {})
    render(
      <StrompreisForm
        anlageId={1}
        strompreis={basis({
          zeitfenster: [{
            id: 7, von_stunde: 19, bis_stunde: 20,
            wochentage: '0123456', arbeitspreis_cent_kwh: 15,
          }],
        })}
        onUpdate={onUpdate}
        onCancel={() => {}}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /Entfernen/ }))
    fireEvent.click(screen.getByRole('button', { name: /Speichern|Aktualisieren/ }))

    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1))
    const gesendet = (onUpdate as unknown as { mock: { calls: [Record<string, unknown>][] } })
      .mock.calls[0][0]
    // `[]` statt `undefined`: nur so raeumt das Backend die Fenster ab.
    expect(gesendet.zeitfenster).toEqual([])
  })
})
