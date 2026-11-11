/**
 * Etappe E5 «Daten-Checker: ein Handgriff je Befund» — Verdichtung (Konzept §6), Klapp-Regel und Handgriff-Leiste (§7),
 * Mockup: OK-Zeilen gefaltet («n Prüfungen bestanden»), Gruppenzeile mit Gliedern (V2), Kopf mit Chips und den nicht
 * ausführbaren Prüfungen (V4), K1 (offen ⇔ Fehler, Warnung oder Aktion), K2 (Leiste nur mit Aktion), E5.7 L2 (das
 * Lösungsweg-Panel holt sich aus der letzten Kategorie ins Bild).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

const check = vi.fn()
vi.mock('../api/datenChecker', () => ({ datenCheckerApi: { check: (...a: unknown[]) => check(...a) } }))
vi.mock('../hooks/useHelpKatalog', async (orig) => ({
  ...(await orig<typeof import('../hooks/useHelpKatalog')>()),
  useHelpKatalog: () => ({ docs: [], grouped: [], activeDoc: undefined, content: '', loading: false, error: null,
    rewriteLink: () => ({ type: 'external', target: '#' }) }),
}))

import { DatenCheckerVerwaltung } from './DatenCheckerTeile'

const OK = (kategorie: string, meldung: string) => ({ kategorie, schwere: 'ok', meldung, code: 'x_ok', knopf: null })
const MONAT = (m: string) => ({
  kategorie: 'monatsdaten_vollstaendigkeit', schwere: 'error', meldung: `${m}/2026 fehlt`, code: 'monat_fehlt',
  knopf: 'Monat erfassen', ziel: { bereich: 'daten', block: 'monatsdaten', params: { erfassen: `2026-${m}` } },
  gruppe: { schluessel: 'monatsdaten_vollstaendigkeit:monat_fehlt', titel: '15 Monate fehlen', glied: `${m}/2026`,
    weitere: 13, details: 'Ein Monat öffnet seine Erfassung.' },
})
const WETTER = {
  kategorie: 'wetterwert_fehlt', schwere: 'info', meldung: '34 abgeschlossene(r) Monat(e) tragen keine festgehaltene Wetterquelle',
  code: 'wetterreihe_nachziehen', knopf: 'Wetterreihe nachziehen',
  action: { operation: 'wetter_backfill', params: {}, label: 'Wetterreihe nachziehen' },
}
const TARIF = { kategorie: 'strompreise', schwere: 'info', meldung: 'Kein Ladetarif hinterlegt', code: 'kein_ladetarif',
  knopf: 'Was gilt' }

function antwort() {
  return {
    anlage_id: 7, anlage_name: 'Haus',
    ergebnisse: [OK('stammdaten', 'Installationsdatum vorhanden'), TARIF, OK('strompreise', '3 Tarife'),
      MONAT('01'), MONAT('02'), OK('monatsdaten_vollstaendigkeit', 'x'), WETTER],
    zusammenfassung: { error: 2, warning: 0, info: 2, ok: 3 },
    nicht_ausfuehrbar: [{ pruefung: 'Sensoren gegen die Langzeitstatistik', grund: 'Standalone' },
      { pruefung: 'MQTT-Topic-Abdeckung', grund: 'MQTT-Import aus' }],
  }
}

function Ort() {
  const l = useLocation()
  return <span data-testid="ort">{l.pathname}{l.search}</span>
}

async function verwaltung() {
  render(
    <MemoryRouter initialEntries={['/einstellungen/daten']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes><Route path="*" element={<><DatenCheckerVerwaltung anlageId={7} /><Ort /></>} /></Routes>
    </MemoryRouter>,
  )
  return await screen.findByTestId('checker-kopf')
}

function kategorie(label: string) {
  return within(screen.getAllByTestId('kategorie').find((k) => k.getAttribute('aria-label') === label)!)
}

describe('Daten-Checker E5: Verdichtung, Klapp-Regel, Leiste', () => {
  beforeEach(() => {
    vi.setSystemTime(new Date(2026, 10, 11, 9, 5))
    check.mockReset()
    check.mockResolvedValue(antwort())
  })
  afterEach(() => { vi.useRealTimers() })

  it('Kopf: Chips der Zusammenfassung, Stand und die nicht ausführbaren Prüfungen (V4)', async () => {
    const kopf = await verwaltung()
    expect(kopf.textContent).toContain('2 Fehler')
    expect(kopf.textContent).toContain('2 Hinweise')
    expect(kopf.textContent).toContain('3 bestanden')
    expect(kopf.textContent).toContain('Stand 09:05')
    expect(kopf.textContent).toContain('2 Prüfungen nicht ausführbar (Standalone / MQTT-Import aus)')
  })

  it('V1: OK-Zeilen stehen nicht in der Liste — der Fuß «n Prüfungen bestanden» klappt sie auf', async () => {
    await verwaltung()
    const monate = kategorie('Monatsdaten – Vollständigkeit')
    expect(monate.queryByText('x')).toBeNull()
    fireEvent.click(monate.getByRole('button', { name: /1 Prüfung bestanden/ }))
    expect(monate.getByText('x')).toBeTruthy()
  })

  it('K1: offen mit Fehler oder Aktion, zu mit nur Hinweisen ohne Handgriff (der Kopf zeigt die Chips)', async () => {
    await verwaltung()
    expect(kategorie('Monatsdaten – Vollständigkeit').getByRole('button', { name: /Monatsdaten/ }).getAttribute('aria-expanded')).toBe('true')
    expect(kategorie('Wetterwerte – fehlende Monatswerte').getByRole('button', { name: /Wetterwerte/ }).getAttribute('aria-expanded')).toBe('true')
    const tarif = kategorie('Strompreise')
    expect(tarif.getByRole('button', { name: /Strompreise/ }).getAttribute('aria-expanded')).toBe('false')
    expect(tarif.queryByText('Kein Ladetarif hinterlegt')).toBeNull()
    expect(tarif.getByText('1 Hinweis')).toBeTruthy()
  })

  it('V2: eine Gruppenzeile mit Gliedern; ein Glied springt auf genau seinen Monat', async () => {
    await verwaltung()
    const monate = kategorie('Monatsdaten – Vollständigkeit')
    expect(monate.getAllByTestId('befund-gruppe')).toHaveLength(1)
    expect(monate.getByText('15 Monate fehlen')).toBeTruthy()
    expect(monate.getByText('+ 13 weitere')).toBeTruthy()
    expect(monate.queryByText('01/2026 fehlt')).toBeNull()
    fireEvent.click(monate.getByRole('button', { name: '02/2026' }))
    expect(screen.getByTestId('ort').textContent).toBe('/einstellungen/daten?erfassen=2026-02')
  })

  it('K2: die Leiste trägt nur die Aktion, mit Kategorie und Lösungsweg; ohne Aktion keine Leiste', async () => {
    await verwaltung()
    const leiste = within(screen.getByTestId('handgriff-leiste'))
    expect(leiste.getByText('1 Handgriff aus allen Kategorien')).toBeTruthy()
    expect(leiste.getByRole('button', { name: /Wetterreihe nachziehen/ })).toBeTruthy()
    expect(leiste.getByText(/Wetterwerte – fehlende Monatswerte/)).toBeTruthy()
    expect(leiste.queryByText('Kein Ladetarif hinterlegt')).toBeNull()
  })

  it('ohne Aktion keine Leiste', async () => {
    check.mockResolvedValue({ ...antwort(), ergebnisse: [TARIF] })
    await verwaltung()
    expect(screen.queryByTestId('handgriff-leiste')).toBeNull()
  })

  it('E5.7 L2: «Lösungsweg» aus der letzten Kategorie holt das Panel ins Bild', async () => {
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    await verwaltung()
    const letzte = kategorie('Wetterwerte – fehlende Monatswerte')
    fireEvent.click(letzte.getByRole('button', { name: 'Lösungsweg' }))
    expect(await screen.findByTestId('loesungsweg-panel')).toBeTruthy()
    expect(screen.getByTestId('loesungsweg-spalte').className).toContain('lg:sticky')
    expect(scroll).toHaveBeenCalledWith({ block: 'nearest', behavior: 'smooth' })
  })
})
