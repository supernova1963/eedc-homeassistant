/**
 * InvestitionForm — Submit-Nutzlast.
 *
 * Kern des Tests ist der Vertrag mit dem Backend (`model_dump(exclude_unset=True)`):
 * Beim BEARBEITEN muss ein leeres Feld als `null` gesendet werden, sonst fällt der
 * Schlüssel aus dem JSON und der Altwert bleibt stehen — genau daran scheiterte das
 * Lösen einer Wechselrichter-Zuordnung (JayJay, Forum v4.0.0). Beim ANLEGEN bleibt
 * `undefined` richtig, damit die Backend-Defaults greifen.
 * Backend-Hälfte: `backend/tests/test_investition_felder_leeren.py`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import InvestitionForm from './InvestitionForm'
import type { Investition } from '../../types'

const wechselrichter: Investition = {
  id: 3, anlage_id: 1, typ: 'wechselrichter', bezeichnung: 'Hybrid-WR', aktiv: true,
}

vi.mock('../../api/investitionen', () => ({
  investitionenApi: { list: vi.fn(() => Promise.resolve([wechselrichter])) },
}))

const speicher: Investition = {
  id: 7, anlage_id: 1, typ: 'speicher', bezeichnung: 'AC-Speicher',
  anschaffungsdatum: '2024-06-01', aktiv: true, parent_investition_id: 3,
  parameter: { kapazitaet_kwh: 10 },
}

/** Speichern auslösen und die an onSubmit übergebene Nutzlast zurückgeben. */
async function submit(onSubmit: ReturnType<typeof vi.fn>) {
  fireEvent.submit(document.querySelector('form')!)
  await waitFor(() => expect(onSubmit).toHaveBeenCalled())
  return onSubmit.mock.calls[0][0] as Record<string, unknown>
}

describe('InvestitionForm — Submit-Nutzlast', () => {
  beforeEach(() => vi.clearAllMocks())

  it('löst die Parent-Zuordnung, wenn „Keine Zuordnung" gewählt wird', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    render(<InvestitionForm anlageId={1} typ="speicher" investition={speicher} onSubmit={onSubmit} onCancel={() => {}} />)

    const select = await screen.findByLabelText(/Gehört zu/i)
    fireEvent.change(select, { target: { value: '' } })

    const nutzlast = await submit(onSubmit)
    // Der Schlüssel MUSS mitgehen — sonst greift exclude_unset und der alte
    // Wechselrichter bleibt für immer stehen.
    expect('parent_investition_id' in nutzlast).toBe(true)
    expect(nutzlast.parent_investition_id).toBeNull()
  })

  it('sendet beim Bearbeiten null für nicht gefüllte optionale Felder', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    render(<InvestitionForm anlageId={1} typ="speicher" investition={speicher} onSubmit={onSubmit} onCancel={() => {}} />)

    const nutzlast = await submit(onSubmit)
    expect(nutzlast.anschaffungskosten_alternativ).toBeNull()
    expect(nutzlast.stilllegungsdatum).toBeNull()
    // Gefüllte Felder behalten ihren Wert.
    expect(nutzlast.anschaffungsdatum).toBe('2024-06-01')
  })

  it('blockiert das Anlegen ohne Anschaffungsdatum', async () => {
    // v4.0.1: Das Datum ist die Grenze jeder Auswertung und der Nullpunkt der
    // Amortisationskurve — ohne es darf keine Komponente mehr entstehen.
    const onSubmit = vi.fn(() => Promise.resolve())
    render(<InvestitionForm anlageId={1} typ="speicher" onSubmit={onSubmit} onCancel={() => {}} />)

    fireEvent.change(screen.getByLabelText(/Bezeichnung/i), { target: { value: 'Neuer Speicher' } })
    fireEvent.submit(document.querySelector('form')!)

    await waitFor(() => expect(screen.getByText(/Bitte das Anschaffungsdatum angeben/i)).toBeInTheDocument())
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('#351 zeigt bei ungepflegter Kopplung, WAS abgeleitet wird — und speichert die Wahl', async () => {
    // Genau JayJays Konstellation: AC-Speicher an einem Hybrid-Wechselrichter.
    // Solange nichts gepflegt ist, leitet eedc „DC" ab (weil zugeordnet) — der
    // Hinweis muss das sagen, sonst ist die Angabe unauffindbar.
    const onSubmit = vi.fn(() => Promise.resolve())
    render(<InvestitionForm anlageId={1} typ="speicher" investition={speicher} onSubmit={onSubmit} onCancel={() => {}} />)

    const select = await screen.findByLabelText(/Kopplung/i)
    expect((select as HTMLSelectElement).value).toBe('')
    expect(screen.getByText(/Ohne Angabe: DC-gekoppelt/i)).toBeInTheDocument()

    fireEvent.change(select, { target: { value: 'ac' } })
    const nutzlast = await submit(onSubmit)
    expect((nutzlast.parameter as Record<string, unknown>).kopplung).toBe('ac')
    // Die Zuordnung bleibt bestehen — Struktur und Bauform sind getrennt.
    expect(nutzlast.parent_investition_id).toBe(3)
  })

  it('#351 zeigt eine gepflegte Kopplung beim Bearbeiten wieder an', async () => {
    // Ohne diesen Weg stünde das Feld beim zweiten Öffnen auf „Automatisch" —
    // die Anzeige behauptete dann eine Ableitung, obwohl ein Wert gepflegt ist,
    // und ein Speichern würde ihn stillschweigend löschen.
    const onSubmit = vi.fn(() => Promise.resolve())
    const acSpeicher = { ...speicher, parameter: { kapazitaet_kwh: 10, kopplung: 'ac' } }
    render(<InvestitionForm anlageId={1} typ="speicher" investition={acSpeicher} onSubmit={onSubmit} onCancel={() => {}} />)

    const select = await screen.findByLabelText(/Kopplung/i)
    expect((select as HTMLSelectElement).value).toBe('ac')
    const nutzlast = await submit(onSubmit)
    expect((nutzlast.parameter as Record<string, unknown>).kopplung).toBe('ac')
  })

  it('sendet beim Anlegen undefined statt null (Backend-Defaults greifen)', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    render(<InvestitionForm anlageId={1} typ="speicher" onSubmit={onSubmit} onCancel={() => {}} />)

    fireEvent.change(screen.getByLabelText(/Bezeichnung/i), { target: { value: 'Neuer Speicher' } })
    // Datum über den Kalender setzen (DatumPicker ist ein Dialog, kein Input).
    fireEvent.click(screen.getByLabelText('Anschaffungsdatum'))
    fireEvent.click(await screen.findByRole('button', { name: '15' }))

    const nutzlast = await submit(onSubmit)
    expect(nutzlast.anschaffungsdatum).toBeTruthy()
    expect(nutzlast.anschaffungskosten_alternativ).toBeUndefined()
    expect(nutzlast.parent_investition_id).toBeUndefined()
  })

  // ── „Ertrag/Jahr" (Wirtschaftlichkeits-Konzept §8/1) ──
  //
  // Die Typ-Grenze ist kein Anzeige-Detail: gelesen wird das Feld nur im
  // `else`-Zweig der ROI-Typkette (Wallbox/Sonstiges). Stünde es an einer
  // PV- oder Speicher-Zeile, könnte der Anwender einen Betrag pflegen, der
  // nirgends ankommt — SoT der Menge ist `ERTRAGSFELD_TYPEN` (Backend-Pendant
  // in `models/investition.py`). Backend-Hälfte:
  // `test_konzept_wirtschaftlichkeit_konformitaet.py::…schritt1…`/`…typ_grenze…`.

  it('§8/1 bietet „Ertrag/Jahr" bei Sonstiges an und sendet den Wert', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    const sonstiges: Investition = {
      id: 9, anlage_id: 1, typ: 'sonstiges', bezeichnung: 'Zweiter Erzeuger',
      anschaffungsdatum: '2024-01-01', aktiv: true,
    }
    render(<InvestitionForm anlageId={1} typ="sonstiges" investition={sonstiges} onSubmit={onSubmit} onCancel={() => {}} />)

    // Das Feld steht in der einklappbaren Sektion „Weitere Angaben & Kosten"
    // (`variant="erweitert"`), die geschlossen startet.
    fireEvent.click(screen.getByRole('button', { name: /Weitere Angaben & Kosten/i }))
    const feld = screen.getByLabelText(/Ertrag\/Jahr/i)
    fireEvent.change(feld, { target: { value: '500' } })

    const nutzlast = await submit(onSubmit)
    expect(nutzlast.einsparung_prognose_jahr).toBe(500)
  })

  it('§8/1 zeigt „Ertrag/Jahr" NICHT bei selbst gerechneten Typen', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    render(<InvestitionForm anlageId={1} typ="speicher" investition={speicher} onSubmit={onSubmit} onCancel={() => {}} />)

    // Dieselbe Sektion aufklappen — sonst wäre die Abwesenheit nur die des
    // eingeklappten Blocks und die Probe könnte nichts sehen.
    fireEvent.click(screen.getByRole('button', { name: /Weitere Angaben & Kosten/i }))
    expect(screen.getByLabelText(/Betriebskosten\/Jahr/i)).toBeTruthy()
    expect(screen.queryByLabelText(/Ertrag\/Jahr/i)).toBeNull()
    // … und der Schlüssel darf auch nicht still mitgehen.
    const nutzlast = await submit(onSubmit)
    expect('einsparung_prognose_jahr' in nutzlast).toBe(false)
  })
})
