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

    await screen.findByLabelText('Monat:')
    expect(screen.queryByText(/Wie in meiner Monatsansicht/)).not.toBeInTheDocument()
    // Die Gegenprobe zur Gegenprobe: die übrigen Schalter stehen sehr wohl da.
    // ⚑ Hier stand bis 2026-08-30 „Anlagenname und Standort nennen"; der
    // Schalter ist entfallen (Entscheid Gernot — seine Begründung war der
    // Forumspost, und das Thema *Teilen* wird nicht verfolgt). Die Aussage der
    // Zeile bleibt dieselbe: es ist nicht ALLES weg, nur der Park-Schalter.
    expect(screen.getByLabelText('Energie')).toBeInTheDocument()
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
    await screen.findByLabelText('Monat:')

    expect(await berichtsAdresse()).toContain('ohne=el%3Abilanz-grundlast')
    // Neuester Monat vorausgewählt (Datums-Listen absteigend, Style-Guide).
    expect(await berichtsAdresse()).toContain('jahr=2026&monat=4')

    schalte(/Wie in meiner Monatsansicht/)
    expect(await berichtsAdresse()).not.toContain('ohne=')
  })

  it('lässt ein abgewähltes Thema aus der Adresse fallen', async () => {
    renderMitProvidern(<DokumentationsDialog anlage={ANLAGE} onClose={() => {}} />)
    await screen.findByLabelText('Monat:')

    expect(await berichtsAdresse()).toContain('themen=finanzen')
    schalte('Finanzen')
    expect(await berichtsAdresse()).not.toContain('themen=finanzen')
    // Die übrigen drei bleiben — ein Schalter schaltet nicht die Nachbarn ab.
    expect(await berichtsAdresse()).toContain('themen=energie')
    expect(await berichtsAdresse()).toContain('themen=co2')
  })
})

/**
 * Der ZIP-Modus (Gernot, 2026-08-30).
 *
 * Vorher trugen die Karten **beides gleichzeitig**: ein Auswahl-Kästchen
 * `absolute top-2 right-2` und darunter, an derselben Ecke, das
 * Download-Symbol — das Symbol war teilweise oder ganz verdeckt. Der Modus
 * löst das baulich: die zwei teilen sich die Ecke nie, weil es sie nie
 * gleichzeitig gibt. Diese Proben halten genau das fest.
 */
describe('ZIP-Modus statt zweier Bedienelemente an derselben Ecke', () => {
  it('aus: die Karte lädt — ein: dieselbe Karte wählt aus', async () => {
    renderMitProvidern(<DokumentationsDialog anlage={ANLAGE} onClose={() => {}} />)
    await screen.findByLabelText('Monat:')
    geladen.length = 0

    // Aus: Klick auf die Karte lädt das Dokument.
    fireEvent.click(screen.getByRole('button', { name: /Jahresbericht/ }))
    await waitFor(() => expect(geladen.length).toBe(1))

    // Ein: derselbe Klick wählt aus, statt zu laden.
    schalte('Mehrere als ZIP')
    const karte = screen.getByRole('button', { name: /Jahresbericht/ })
    expect(karte).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(karte)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Jahresbericht/ }))
        .toHaveAttribute('aria-pressed', 'true'),
    )
    // Und dabei wurde NICHTS geladen — sonst wäre der Modus wirkungslos.
    expect(geladen.length).toBe(1)
  })

  it('der Monatsbericht ist nicht im Sammel-ZIP und sagt es', async () => {
    renderMitProvidern(<DokumentationsDialog anlage={ANLAGE} onClose={() => {}} />)
    await screen.findByLabelText('Monat:')
    schalte('Mehrere als ZIP')

    // Er trägt keinen zipKey ⇒ keine Auswahl, kein `aria-pressed`.
    const karte = screen.getByRole('button', { name: /Monatsbericht/ })
    expect(karte).not.toHaveAttribute('aria-pressed')
    expect(karte).toBeDisabled()
    expect(screen.getByText(/Nicht im Sammel-ZIP/)).toBeInTheDocument()
  })

  it('Beta-Kennzeichnung und Feedback-Link sind weg', async () => {
    renderMitProvidern(<DokumentationsDialog anlage={ANLAGE} onClose={() => {}} />)
    await screen.findByLabelText('Monat:')

    // Issue #121 ist geschlossen — der Link führte ins Leere.
    expect(screen.queryByText(/Feedback zum Beta/)).not.toBeInTheDocument()
    expect(screen.queryByText(/^Beta$/)).not.toBeInTheDocument()
    // Gegenprobe: die Karten, die die Kennzeichnung trugen, gibt es weiterhin.
    expect(screen.getByRole('button', { name: /Anlagendokumentation/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Finanzbericht/ })).toBeInTheDocument()
  })

  it('die Einstellungen stehen IN der Karte, die sie steuern', async () => {
    renderMitProvidern(<DokumentationsDialog anlage={ANLAGE} onClose={() => {}} />)
    const monatswahl = await screen.findByLabelText('Monat:')
    const zeitraum = screen.getByLabelText('Zeitraum:')

    // Jede Option liegt im selben Karten-Container wie ihre Überschrift.
    const monatsKarte = monatswahl.closest('[data-dokument]')
    const jahresKarte = zeitraum.closest('[data-dokument]')
    expect(monatsKarte).not.toBeNull()
    expect(jahresKarte).not.toBeNull()
    expect(monatsKarte).not.toBe(jahresKarte)
    expect(monatsKarte!.getAttribute('data-dokument')).toBe('Monatsbericht')
    expect(jahresKarte!.getAttribute('data-dokument')).toBe('Jahresbericht')
    expect(monatsKarte!.textContent).toContain('Monatsbericht')
    expect(monatsKarte!.textContent).not.toContain('Jahresbericht')
    expect(jahresKarte!.textContent).toContain('Jahresbericht')
    // Und die Themenschalter gehören zum Monatsbericht, nicht zum Dialog.
    expect(monatsKarte!.textContent).toContain('Community')
  })
})

/**
 * Die Optionen dürfen die Karte nicht sprengen (Gernot, 2026-08-30).
 *
 * Der Zeitraum-Wähler des Jahresberichts stand über den Kartenrand hinaus:
 * `Select` mit `compact` rendert den Wrapper als `shrink-0` und das Feld als
 * `w-auto` — es nimmt die Breite seiner längsten Option
 * („Gesamtzeitraum (alle Jahre)") und **weigert sich zu schrumpfen**. In der
 * Kopfleiste, für die `compact` gedacht ist, war das folgenlos; in einer
 * Rasterspalte nicht.
 *
 * ⚠ Pixel misst diese Probe nicht — jsdom hat kein Layout. Sie hält die
 * **Ursache** fest: In einer Karte steht kein `shrink-0`-Wrapper.
 */
describe('Optionen in der Karte sprengen den Rahmen nicht', () => {
  it('kein Select in einer Karte weigert sich zu schrumpfen', async () => {
    renderMitProvidern(<DokumentationsDialog anlage={ANLAGE} onClose={() => {}} />)
    await screen.findByLabelText('Monat:')

    for (const id of ['jahresbericht-jahr', 'monatsbericht-monat']) {
      const feld = screen.getByLabelText(id === 'jahresbericht-jahr' ? 'Zeitraum:' : 'Monat:')
      const wrapper = feld.parentElement!
      expect(wrapper.className, `${id}: Wrapper darf nicht shrink-0 sein`)
        .not.toContain('shrink-0')
      // Gegenprobe: das Feld ist wirklich in einer Karte, nicht irgendwo.
      expect(feld.closest('[data-dokument]')).not.toBeNull()
    }
  })
})
