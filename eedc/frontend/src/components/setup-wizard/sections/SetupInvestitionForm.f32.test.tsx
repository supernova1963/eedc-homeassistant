/**
 * F-32, Schreibhälfte — der Einrichtungsassistent schreibt die abgeleitete kWp.
 *
 * Die Nennleistung eines Balkonkraftwerks ist ein **abgeleiteter** Wert: gepflegt
 * werden „Leistung pro Modul (Wp)" und „Anzahl Module" im `parameter`, die Spalte
 * `leistung_kwp` trägt Anzahl × Wp. Das Investitionsformular berechnet und
 * schreibt sie; der Assistent tat es nicht — und drei Lesestellen des
 * Prognose-Pfads lasen `get_pv_kwp`, das die BKW-Form nicht kennt. Folge für
 * genau den Erstnutzer mit Balkonkraftwerk: `/api/solar-prognose` antwortete mit
 * HTTP 400 (*Cockpit → Live* und *Cockpit → Aussicht* ohne Prognose), der
 * Prefetch brach mit `keine_strings` ab. Melder-Weg: Daniel, Forum T89667 #170 ff.
 *
 * Die Lesehälfte ist im Backend gewächtert (`test_bkw_wizard_kwp_f32.py`); hier
 * steht die Schreibhälfte, und zwar an drei Punkten: die Formel kommt aus dem
 * **einen** Client-SoT, der Wizard **schickt** sie mit, und ein geleertes Feld
 * **leert** die Spalte statt den Altwert stehen zu lassen.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SetupInvestitionForm } from './SetupInvestitionForm'
import { bkwLeistungKwp } from '../../forms/sections/investitionFormHelpers'
import type { Investition } from '../../../types'

function bkw(parameter: Record<string, unknown> = {}): Investition {
  return {
    id: 7, anlage_id: 1, typ: 'balkonkraftwerk', bezeichnung: 'Balkonkraftwerk',
    aktiv: true, anschaffungsdatum: '2025-03-01',
    parameter: { leistung_wp: 400, anzahl: 2, ausrichtung: 'Süd', neigung_grad: 30, ...parameter },
  } as unknown as Investition
}

describe('bkwLeistungKwp — der eine Client-SoT der BKW-Formel', () => {
  it('rechnet Anzahl × Wp in kWp', () => {
    expect(bkwLeistungKwp(2, 400)).toBe(0.8)
    expect(bkwLeistungKwp('3', '430')).toBeCloseTo(1.29, 5)
  })

  it('liefert `null` statt 0, wenn eine Eingabe fehlt — 0 sähe wie eine Messung aus', () => {
    expect(bkwLeistungKwp(undefined, 400)).toBeNull()
    expect(bkwLeistungKwp(2, undefined)).toBeNull()
    expect(bkwLeistungKwp('', '')).toBeNull()
    expect(bkwLeistungKwp(0, 400)).toBeNull()
  })
})

describe('F-32 — der Wizard schreibt `leistung_kwp` mit', () => {
  it('schickt die abgeleitete kWp, wenn die Anzahl geändert wird', () => {
    const onUpdate = vi.fn()
    render(
      <SetupInvestitionForm
        investition={bkw()} allInvestitionen={[bkw()]}
        onUpdate={onUpdate} onDelete={() => {}}
      />
    )

    fireEvent.change(screen.getByPlaceholderText('z.B. 2'), { target: { value: '3' } })

    expect(onUpdate).toHaveBeenCalled()
    const nutzlast = onUpdate.mock.calls.at(-1)![0]
    expect(nutzlast.parameter.anzahl).toBe(3)
    expect(nutzlast.leistung_kwp).toBeCloseTo(1.2, 5)
  })

  it('schickt sie auch, wenn die Leistung pro Modul geändert wird', () => {
    const onUpdate = vi.fn()
    render(
      <SetupInvestitionForm
        investition={bkw()} allInvestitionen={[bkw()]}
        onUpdate={onUpdate} onDelete={() => {}}
      />
    )

    fireEvent.change(screen.getByPlaceholderText('z.B. 400'), { target: { value: '500' } })

    const nutzlast = onUpdate.mock.calls.at(-1)![0]
    expect(nutzlast.leistung_kwp).toBeCloseTo(1.0, 5)
  })

  it('leert die Spalte mit `null`, wenn die Anzahl geleert wird', () => {
    // `undefined` fiele aus dem JSON, und das Backend behielte mit
    // `exclude_unset=True` den Altwert — dann behauptete eedc eine Leistung,
    // die niemand mehr gepflegt hat (die JayJay-Falle aus v4.0.0).
    const onUpdate = vi.fn()
    render(
      <SetupInvestitionForm
        investition={bkw()} allInvestitionen={[bkw()]}
        onUpdate={onUpdate} onDelete={() => {}}
      />
    )

    fireEvent.change(screen.getByPlaceholderText('z.B. 2'), { target: { value: '' } })

    const nutzlast = onUpdate.mock.calls.at(-1)![0]
    expect(nutzlast.leistung_kwp).toBeNull()
    expect('leistung_kwp' in nutzlast).toBe(true)
  })

  it('Formular und Wizard kommen bei denselben Eingaben auf denselben Wert', () => {
    // Die Abnahme-Zusicherung: „gleicher Wert wie über das Formular". Beide
    // Wege rufen `bkwLeistungKwp` — der Test hält fest, dass der Wizard-Pfad
    // nicht wieder eine eigene Formel bekommt.
    const onUpdate = vi.fn()
    render(
      <SetupInvestitionForm
        investition={bkw()} allInvestitionen={[bkw()]}
        onUpdate={onUpdate} onDelete={() => {}}
      />
    )
    fireEvent.change(screen.getByPlaceholderText('z.B. 2'), { target: { value: '4' } })

    const nutzlast = onUpdate.mock.calls.at(-1)![0]
    expect(nutzlast.leistung_kwp).toBe(bkwLeistungKwp(4, 400))
  })
})
