/**
 * Etappe E3 «Daten-Checker: ein Handgriff je Befund» (Konzept §5, Bauplan §4 W-10): eine Befund-Zeile mit genau einem
 * Handgriff — Aktion mit Vorschau (Plan → Kasten → «Anwenden»/«Abbrechen», «nichts zu tun», Fehler), Sprung, Auskunft
 * (öffnet den Lösungsweg), der Fenster-Knopf des Panels nur außerhalb von Home Assistant, und der Komponenten-Hub lädt
 * nach «Anwenden» neu (Gegenprüfung Ü7).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

const plan = vi.fn()
const execute = vi.fn()
const discard = vi.fn()
const check = vi.fn()

vi.mock('../../api/repair', async (orig) => ({
  ...(await orig<typeof import('../../api/repair')>()),
  repairApi: {
    plan: (...a: unknown[]) => plan(...a),
    execute: (...a: unknown[]) => execute(...a),
    discard: (...a: unknown[]) => discard(...a),
  },
}))
vi.mock('../../api/datenChecker', () => ({ datenCheckerApi: { check: (...a: unknown[]) => check(...a) } }))
vi.mock('../../hooks/useHelpKatalog', async (orig) => ({
  ...(await orig<typeof import('../../hooks/useHelpKatalog')>()),
  useHelpKatalog: () => ({ docs: [], grouped: [], activeDoc: undefined, content: '## Abschnitt\n\nSchritte\n\n#### Temperatur <a name="temperatur_aus_messung_moeglich"></a>\n\n1. Schritt eins\n\n#### Anderer Code <a name="x"></a>\n\nfremd', loading: false,
    error: null, rewriteLink: () => ({ type: 'external', target: '#' }) }),
}))

import BefundHandgriff from './BefundHandgriff'
import LoesungswegPanel from './LoesungswegPanel'
import { DatenCheckerBlock } from '../../v4/KomponentenTypV4'
import type { CheckErgebnis } from '../../api/datenChecker'
import type { RepairPlan } from '../../api/repair'

const TEMP: CheckErgebnis = {
  kategorie: 'wetterwert_fehlt', schwere: 'info', meldung: 'Ø Temperatur fehlt in 3 Monat(en), für 2 davon reicht die Messreihe',
  details: null, ziel: null, action: { operation: 'temperatur_aus_messung', params: {}, label: 'Temperatur aus Messung übernehmen' },
  knopf: 'Temperatur aus Messung übernehmen', investition_id: null,
} as unknown as CheckErgebnis

/** E5: der Handgriff steht in `action` bzw. `ziel`, der Knopf-Text in `knopf` (die Altfelder sind entfallen). */
function aktion(operation: string, knopf: string, params: Record<string, unknown> = {}): CheckErgebnis {
  return { ...TEMP, action: { operation, params, label: knopf }, knopf }
}

function planVon(over: Partial<RepairPlan>): RepairPlan {
  return {
    plan_id: 'p-1', anlage_id: 7, operation: 'temperatur_aus_messung', operation_params: {},
    created_at: '2026-11-10T11:00:00+00:00', expires_at: '2026-11-10T12:00:00+00:00',
    estimated_changes: { monate_temperatur_gefuellt: 2, monate_ohne_temperatur: 3 }, diff_preview: [], diff_total_count: 0,
    warnings: [], operation_preview: { monate: ['01/2026', '02/2026'] }, ...over,
  }
}

function Ort() {
  const l = useLocation()
  return <span data-testid="ort">{l.pathname}{l.search}</span>
}

function zeile(befund: CheckErgebnis, extra: Record<string, unknown> = {}) {
  return render(
    <MemoryRouter initialEntries={['/einstellungen/daten']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes><Route path="*" element={<><BefundHandgriff befund={befund} anlageId={7} {...extra} /><Ort /></>} /></Routes>
    </MemoryRouter>,
  )
}

describe('BefundHandgriff', () => {
  beforeEach(() => {
    vi.setSystemTime(new Date(2026, 10, 10, 12))
    for (const f of [plan, execute, discard, check]) f.mockReset()
    discard.mockResolvedValue(undefined)
  })
  afterEach(() => { vi.useRealTimers() })

  it('Aktion: Vorschau zuerst, dann «Anwenden» — Ergebnis-Satz an den Aufrufer', async () => {
    plan.mockResolvedValue({ plan: planVon({}), expires_in_seconds: 3600 })
    execute.mockResolvedValue({ plan_id: 'p-1', operation: 'temperatur_aus_messung', actual_changes: {}, audit_log_ids: [],
      operation_summary: { gefuellt: 2, offen: 1 } })
    const onErgebnis = vi.fn()
    zeile(TEMP, { onErgebnis })
    fireEvent.click(screen.getByRole('button', { name: /Temperatur aus Messung übernehmen/ }))
    await waitFor(() => expect(plan).toHaveBeenCalledWith({ anlage_id: 7, operation: 'temperatur_aus_messung', params: {} }))
    expect(execute).not.toHaveBeenCalled()
    expect(await screen.findByText(/Monate erhalten eine Ø Temperatur: 2 · Monate ohne Ø Temperatur: 3 \(01\/2026, 02\/2026\)/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Anwenden' }))
    await waitFor(() => expect(execute).toHaveBeenCalledWith('p-1'))
    await waitFor(() => expect(onErgebnis).toHaveBeenCalledWith(expect.objectContaining({ art: 'ok' })))
    expect(screen.queryByTestId('vorschau-kasten')).toBeNull()
  })

  it('«Abbrechen» verwirft den Plan, nichts wird ausgeführt', async () => {
    plan.mockResolvedValue({ plan: planVon({}), expires_in_seconds: 3600 })
    zeile(TEMP)
    fireEvent.click(screen.getByRole('button', { name: /Temperatur aus Messung übernehmen/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Abbrechen' }))
    await waitFor(() => expect(discard).toHaveBeenCalledWith('p-1'))
    expect(execute).not.toHaveBeenCalled()
    expect(screen.queryByTestId('vorschau-kasten')).toBeNull()
  })

  it('«nichts zu tun»: der Satz des Plans, kein «Anwenden»', async () => {
    plan.mockResolvedValue({ plan: planVon({ estimated_changes: {},
      operation_preview: { nichts_zu_tun: 'Der Monat 10/2025 hat noch eine Zählerzeile.' } }), expires_in_seconds: 3600 })
    zeile(TEMP)
    fireEvent.click(screen.getByRole('button', { name: /Temperatur aus Messung übernehmen/ }))
    expect(await screen.findByText('Der Monat 10/2025 hat noch eine Zählerzeile.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Anwenden' })).toBeNull()
  })

  it('Lösch-Operation: «endgültig» in der Zeile und ein roter Knopf', async () => {
    plan.mockResolvedValue({ plan: planVon({ operation: 'feldwert_entfernen', estimated_changes: { monate_wert_entfernt: 2 },
      operation_preview: { endgueltig: true, monate: ['05/2026', '06/2026'] } }), expires_in_seconds: 3600 })
    zeile(aktion('feldwert_entfernen', 'Wert entfernen'))
    fireEvent.click(screen.getByRole('button', { name: /Wert entfernen/ }))
    expect(await screen.findByText(/Monate verlieren den Wert: 2 \(05\/2026, 06\/2026\) — endgültig/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Anwenden' }).className).toContain('bg-red-600')
  })

  it('Spiegel-Abgleich: die Vorbedingung steht in der Zeile', async () => {
    plan.mockResolvedValue({ plan: planVon({ operation: 'spiegel_abgleich_tag',
      estimated_changes: { spiegel_kanaele: 1, spiegel_abschnitte: 1, tage_neu_aufgebaut: 1 },
      operation_preview: { hat_spiegel: true } }), expires_in_seconds: 3600 })
    zeile(aktion('spiegel_abgleich_tag', 'Aus Home Assistant neu übernehmen', { datum: '2026-11-02' }))
    fireEvent.click(screen.getByRole('button', { name: /Aus Home Assistant neu übernehmen/ }))
    expect(await screen.findByText(/wirksam, wenn du in Home Assistant korrigiert hast/)).toBeTruthy()
  })

  it('Fehler beim Ausführen: roter Satz, der Befund und der Kasten bleiben', async () => {
    plan.mockResolvedValue({ plan: planVon({}), expires_in_seconds: 3600 })
    execute.mockRejectedValue(new Error('Home Assistant ist nicht erreichbar'))
    const onErgebnis = vi.fn()
    zeile(TEMP, { onErgebnis })
    fireEvent.click(screen.getByRole('button', { name: /Temperatur aus Messung übernehmen/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Anwenden' }))
    expect(await screen.findByText('Home Assistant ist nicht erreichbar')).toBeTruthy()
    expect(screen.getByTestId('vorschau-kasten')).toBeTruthy()
    expect(onErgebnis).not.toHaveBeenCalled()
  })

  it('Sprung: der Knopf trägt den Katalog-Text (E5.7 L1, kein «Beheben») und navigiert zum Ziel, ohne Plan', () => {
    zeile({ ...TEMP, action: null, knopf: 'Monat erfassen',
      ziel: { bereich: 'daten', block: 'monatsdaten', params: { erfassen: '2026-01' } } } as unknown as CheckErgebnis)
    expect(screen.queryByRole('button', { name: /Beheben/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Monat erfassen/ }))
    expect(screen.getByTestId('ort').textContent).toBe('/einstellungen/daten?erfassen=2026-01')
    expect(plan).not.toHaveBeenCalled()
  })

  it('Sprung am Gerät: «Gerät bearbeiten» (E5.7 L1, JAZ-Zeile)', () => {
    zeile({ ...TEMP, action: null, knopf: 'Gerät bearbeiten', kategorie: 'investitionen',
      ziel: { bereich: 'komponenten', block: null, params: { bearbeiten: 4, feld: 'param_jaz' } } } as unknown as CheckErgebnis)
    fireEvent.click(screen.getByRole('button', { name: /Gerät bearbeiten/ }))
    expect(screen.getByTestId('ort').textContent).toBe('/einstellungen/komponenten?bearbeiten=4&feld=param_jaz')
  })

  it('Auskunft: «Was gilt» öffnet den Lösungsweg; jede offene Zeile trägt den Link «Lösungsweg»', () => {
    const onLoesungsweg = vi.fn()
    const auskunft = { ...TEMP, schwere: 'warning', action: null, knopf: 'Was gilt', ziel: null } as unknown as CheckErgebnis
    zeile(auskunft, { onLoesungsweg })
    fireEvent.click(screen.getByRole('button', { name: 'Was gilt' }))
    fireEvent.click(screen.getByRole('button', { name: 'Lösungsweg' }))
    expect(onLoesungsweg).toHaveBeenCalledTimes(2)
  })

  it('ein Vorgang zur Zeit: gesperrt ⇒ der Knopf ist aus', () => {
    zeile(TEMP, { gesperrt: true })
    expect((screen.getByRole('button', { name: /Temperatur aus Messung übernehmen/ }) as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('LoesungswegPanel', () => {
  afterEach(() => { window.history.replaceState(null, '', '/') })

  function panel() {
    return render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <LoesungswegPanel befund={TEMP} als="einschub" onClose={() => undefined} />
      </MemoryRouter>,
    )
  }

  it('außerhalb von Home Assistant: «In eigenem Fenster öffnen» am Anker der Kategorie', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    panel()
    fireEvent.click(screen.getByRole('button', { name: /In eigenem Fenster öffnen/ }))
    expect(open).toHaveBeenCalledWith('#/hilfe?doc=daten-checker#425-wetterwerte-fehlende-monatswerte', '_blank', 'noopener')
    open.mockRestore()
  })

  it('hinter dem Ingress: kein Fenster-Knopf, stattdessen der Hinweis', () => {
    window.history.replaceState(null, '', '/api/hassio_ingress/abc/')
    panel()
    expect(screen.queryByRole('button', { name: /In eigenem Fenster öffnen/ })).toBeNull()
    // E5.7 L3: ein Satz für Browser über das HA-Seitenmenü und die Companion-App, mit dem Weg zum Knopf.
    expect(screen.getByTestId('loesungsweg-hinweis').textContent).toBe(
      'Innerhalb von Home Assistant nur hier im Panel — ein eigenes Fenster hätte keine Anmeldung. Direkt geöffnet (Port 8099) gibt es den Knopf.')
  })

  it('mit Code: der Abschnitt des Codes, Fenster-Knopf am Anker des Codes (E5)', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <LoesungswegPanel befund={{ ...TEMP, code: 'temperatur_aus_messung_moeglich' }} als="einschub" onClose={() => undefined} />
      </MemoryRouter>,
    )
    expect(screen.getByTestId('loesungsweg-inhalt').textContent).toContain('Schritt eins')
    expect(screen.getByTestId('loesungsweg-inhalt').textContent).not.toContain('Anderer Code')
    fireEvent.click(screen.getByRole('button', { name: /In eigenem Fenster öffnen/ }))
    expect(open).toHaveBeenCalledWith('#/hilfe?doc=daten-checker#temperatur_aus_messung_moeglich', '_blank', 'noopener')
    open.mockRestore()
  })
})

describe('Komponenten-Hub: dieselben Handgriffe, Neuladen nach «Anwenden» (Ü7)', () => {
  beforeEach(() => {
    vi.setSystemTime(new Date(2026, 10, 10, 12))
    for (const f of [plan, execute, discard, check]) f.mockReset()
  })
  afterEach(() => { vi.useRealTimers() })

  it('lädt die Befunde nach dem Lauf neu und zeigt den Satz', async () => {
    const befund = { ...TEMP, investition_id: 5 } as CheckErgebnis
    check.mockResolvedValueOnce({ anlage_id: 7, ergebnisse: [befund], zusammenfassung: {} })
      .mockResolvedValue({ anlage_id: 7, ergebnisse: [], zusammenfassung: {} })
    plan.mockResolvedValue({ plan: planVon({}), expires_in_seconds: 3600 })
    execute.mockResolvedValue({ plan_id: 'p-1', operation: 'temperatur_aus_messung', actual_changes: {}, audit_log_ids: [],
      operation_summary: { gefuellt: 2, offen: 0 } })
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <DatenCheckerBlock anlageId={7} invs={[{ id: 5 } as never]} />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: /Temperatur aus Messung übernehmen/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Anwenden' }))
    expect(await screen.findByText(/2 Monat\(e\) haben jetzt eine Ø Temperatur/)).toBeTruthy()
    await waitFor(() => expect(check).toHaveBeenCalledTimes(2))
  })
})
