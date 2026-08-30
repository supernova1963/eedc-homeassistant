/**
 * Monatsbericht im Berichts-Hub (#395 Punkt 4) — die Client-Hälfte.
 *
 * Was hier geprüft wird, prüft keine Backend-Probe: **Bedingung 3** des
 * Konzepts (`docs/KONZEPT-MONATSBERICHT.md` §2) ist eine Entscheidung über die
 * Oberfläche — ein *sichtbarer* Schalter statt einer stillen Regel,
 * voreingestellt an, und **gar nicht angezeigt, wenn nichts geparkt ist**.
 *
 * Und die zweite Hälfte derselben Bedingung: Der Park-Zustand lebt nur im
 * `localStorage` DIESES Browsers. Ist der Schalter aus, darf die Adresse
 * **keinen** `ohne`-Parameter tragen — sonst bekäme derselbe Anwender an zwei
 * Geräten zwei verschiedene Berichte, ohne dass etwas kaputt wäre.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderMitProvidern, stubMatchMedia } from '../test/render'
import DokumentationsDialog from './DokumentationsDialog'
import type { Anlage } from '../types'

vi.mock('../api/monatsdaten', () => ({
  monatsdatenApi: {
    list: vi.fn().mockResolvedValue([
      { jahr: 2026, monat: 3 },
      { jahr: 2026, monat: 4 },
    ]),
  },
}))
vi.mock('../api/infothek', () => ({
  infothekApi: { getCount: vi.fn().mockResolvedValue(0) },
}))

// ⚠ `downloadFile` wird ERSETZT statt ausgeführt, und das ist kein Bequemlichkeits-
// Mock: Die echte Fassung hängt einen `<a download>` ins DOM und klickt ihn.
// jsdom kennt keine Navigation, meldet das per Timer nach — ein erster Entwurf
// dieser Datei rief den Adress-Leser INNERHALB von `waitFor` auf und löste damit
// bei jedem Poll einen Download aus; der Lauf hing über zwei Minuten, statt rot
// zu werden. Hier interessiert allein die ADRESSE, die die Karte baut.
const geladen: string[] = []
vi.mock('../lib', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib')>()),
  downloadFile: vi.fn(async (url: string) => { geladen.push(url) }),
}))

const ANLAGE = { id: 7, anlagenname: 'Haus Süd' } as unknown as Anlage

function schalte(matcher: string | RegExp) {
  fireEvent.click(screen.getByLabelText(matcher))
}

/**
 * Die Adresse, die die Monatsbericht-Karte gerade trägt.
 *
 * ⚠ **Nach dem Klick muss der Ladezustand zurück sein.** Die Karte ist während
 * des Downloads `disabled`; ein zweiter Klick im selben Tick tut schlicht
 * nichts, und der Leser lieferte dann die Adresse des ERSTEN Klicks. Genau so
 * meldete ein erster Entwurf, ein abgeschalteter Themenschalter wirke nicht —
 * der Schalter wirkte, die Probe las eine alte Adresse.
 */
async function berichtsAdresse(): Promise<string> {
  const vorher = geladen.length
  fireEvent.click(screen.getByRole('button', { name: /Monatsbericht/ }))
  await waitFor(() => expect(geladen.length).toBe(vorher + 1))
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /Monatsbericht/ })).toBeEnabled(),
  )
  return geladen.at(-1) ?? ''
}

beforeEach(() => {
  localStorage.clear()
  geladen.length = 0
  stubMatchMedia()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    blob: async () => new Blob(['x']),
    text: async () => '# Monatsbericht',
    json: async () => ({}),
  }))
  // jsdom kann keinen Download auslösen.
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:x')
  globalThis.URL.revokeObjectURL = vi.fn()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Monatsbericht im Berichts-Hub', () => {
  it('zeigt den Park-Schalter NICHT, wenn nichts geparkt ist', async () => {
    renderMitProvidern(<DokumentationsDialog anlage={ANLAGE} onClose={() => {}} />)

    await screen.findByLabelText('Monatsbericht für:')
    expect(screen.queryByText(/Wie in meiner Monatsansicht/)).not.toBeInTheDocument()
    // Die Gegenprobe zur Gegenprobe: die übrigen Schalter stehen sehr wohl da.
    expect(screen.getByLabelText('Anlagenname und Standort nennen')).toBeInTheDocument()
  })

  it('zeigt ihn voreingestellt AN, sobald etwas geparkt ist — und nennt die Anzahl', async () => {
    localStorage.setItem('eedc-park:v4-cockpit-monat', JSON.stringify([
      { id: 'el:bilanz-grundlast', titel: 'Grundlast SOLL/IST' },
      { id: 'el:tagesprofil', titel: 'Typisches Tagesprofil' },
    ]))
    renderMitProvidern(<DokumentationsDialog anlage={ANLAGE} onClose={() => {}} />)

    const schalter = await screen.findByLabelText(/Wie in meiner Monatsansicht \(2 geparkte Anzeigen weglassen\)/)
    expect(schalter).toBeChecked()
  })

  it('schickt die geparkten IDs mit — und ohne den Schalter keinen einzigen', async () => {
    localStorage.setItem('eedc-park:v4-cockpit-monat', JSON.stringify([
      { id: 'el:bilanz-grundlast', titel: 'Grundlast SOLL/IST' },
    ]))
    renderMitProvidern(<DokumentationsDialog anlage={ANLAGE} onClose={() => {}} />)
    await screen.findByLabelText('Monatsbericht für:')

    expect(await berichtsAdresse()).toContain('ohne=el%3Abilanz-grundlast')
    // Neuester Monat vorausgewählt (Datums-Listen absteigend, Style-Guide).
    expect(await berichtsAdresse()).toContain('jahr=2026&monat=4')

    schalte(/Wie in meiner Monatsansicht/)
    expect(await berichtsAdresse()).not.toContain('ohne=')
  })

  it('lässt ein abgewähltes Thema aus der Adresse fallen', async () => {
    renderMitProvidern(<DokumentationsDialog anlage={ANLAGE} onClose={() => {}} />)
    await screen.findByLabelText('Monatsbericht für:')

    expect(await berichtsAdresse()).toContain('themen=finanzen')
    schalte('Finanzen')
    expect(await berichtsAdresse()).not.toContain('themen=finanzen')
    // Die übrigen drei bleiben — ein Schalter schaltet nicht die Nachbarn ab.
    expect(await berichtsAdresse()).toContain('themen=energie')
    expect(await berichtsAdresse()).toContain('themen=co2')
  })
})
