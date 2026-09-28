/**
 * FokusVollbild (Paket CT) — Chart-⇄-Tabelle-Umschalter NUR in der
 * Overlay-Kopfzeile: ohne `tabelle`-Slot kein Umschalter; mit Slot startet
 * jede Fokus-Öffnung beim Chart, „Tabelle" tauscht den Inhalt aus.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FokusVollbild } from './FokusVollbild'
import { DatumPicker } from '../ui/DatumPicker'

// Die Entscheidung des Vollbilds fällt in einem Makrotask (s. Komponente) — erst danach messen.
const tick = () => new Promise((r) => setTimeout(r, 0))

describe('FokusVollbild — Chart ⇄ Tabelle (Paket CT)', () => {
  it('ohne tabelle-Slot: kein Umschalter in der Kopfzeile', () => {
    render(
      <FokusVollbild titel="Verlauf" onClose={() => {}}>
        <p>Chart-Inhalt</p>
      </FokusVollbild>,
    )
    expect(screen.getByText('Chart-Inhalt')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Darstellung' })).not.toBeInTheDocument()
  })

  it('mit tabelle-Slot: startet beim Chart, Umschalter tauscht auf die Tabelle und zurück', () => {
    render(
      <FokusVollbild titel="Verlauf" onClose={() => {}} tabelle={<p>Tabellen-Inhalt</p>}>
        <p>Chart-Inhalt</p>
      </FokusVollbild>,
    )
    expect(screen.getByText('Chart-Inhalt')).toBeInTheDocument()
    expect(screen.queryByText('Tabellen-Inhalt')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Tabelle' }))
    expect(screen.getByText('Tabellen-Inhalt')).toBeInTheDocument()
    expect(screen.queryByText('Chart-Inhalt')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Chart' }))
    expect(screen.getByText('Chart-Inhalt')).toBeInTheDocument()
    expect(screen.queryByText('Tabellen-Inhalt')).not.toBeInTheDocument()
  })
})

describe('FokusVollbild — ESC schließt (Style-Guide B16)', () => {
  // ⚠ Grenze dieser Proben: jsdom bildet die Reihenfolge der document-Zuhörer nach,
  // aber NICHT Chromes Microtask-Checkpoint zwischen zwei Zuhörern. Dass der Nachrang
  // in der Anwendung wirkt, ist am 2026-08-28 an der Dev-Box gemessen worden, nicht
  // hier. Was diese Proben halten, ist der Riegel selbst (`defaultPrevented`).

  // Ein Backdrop-Klick ist hier nicht prüfbar und auch nicht gebaut: das Overlay ist
  // deckend, es gibt kein Daneben. ESC ist der einzige Ausweg neben „Zurück".
  const escSenden = () => {
    const ereignis = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    document.dispatchEvent(ereignis)
    return ereignis
  }

  it('ESC ruft onClose', async () => {
    const onClose = vi.fn()
    render(<FokusVollbild titel="Verlauf" onClose={onClose}><p>Inhalt</p></FokusVollbild>)

    escSenden()
    await tick()
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('ESC, das ein Overlay DARIN verbraucht hat, lässt das Vollbild offen', async () => {
    // Der reale Fall: der `DatumPicker` im kopf-Slot von Cockpit/Tag und /Monat. Sein
    // Zuhörer wird SPÄTER registriert und läuft daher nach unserem; er meldet die Taste
    // per preventDefault als verbraucht. Ohne das nähme ESC beides auf einmal.
    const onClose = vi.fn()
    render(<FokusVollbild titel="Verlauf" onClose={onClose}><p>Inhalt</p></FokusVollbild>)

    const inneres = (e: KeyboardEvent) => { if (e.key === 'Escape') e.preventDefault() }
    document.addEventListener('keydown', inneres)
    try {
      escSenden()
      await tick()
      expect(onClose).not.toHaveBeenCalled()
    } finally {
      document.removeEventListener('keydown', inneres)
    }
  })

  it('nach dem Abbau hört niemand mehr mit', async () => {
    const onClose = vi.fn()
    const { unmount } = render(<FokusVollbild titel="Verlauf" onClose={onClose}><p>Inhalt</p></FokusVollbild>)
    unmount()

    escSenden()
    await tick()
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('FokusVollbild — ESC mit echtem DatumPicker im kopf-Slot', () => {
  it('schließt den Picker, nicht das Vollbild (der Fall aus Cockpit/Tag und /Monat)', async () => {
    const onClose = vi.fn()
    render(
      <FokusVollbild
        titel="Verlauf"
        onClose={onClose}
        kopf={<DatumPicker modus="monat" value="2026-06" onChange={() => {}} ariaLabel="Monat" />}
      >
        <p>Inhalt</p>
      </FokusVollbild>,
    )
    // Picker öffnen — sein Zuhörer wird JETZT registriert, also nach dem des Vollbilds.
    fireEvent.click(screen.getByRole('button', { name: 'Monat' }))
    expect(screen.getByRole('button', { name: 'Aug' })).toBeInTheDocument()

    fireEvent.keyDown(document, { key: 'Escape' })
    await tick()

    expect(screen.queryByRole('button', { name: 'Aug' })).not.toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByText('Inhalt')).toBeInTheDocument()
  })
})

describe('FokusVollbild — Deep-Link-Ansicht (FD-1/FD-3)', () => {
  const escSenden = () => document.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
  )

  it('deepLink: kein „Zurück", keine Unterzeile, keine Aktionen — Chart⇄Tabelle und kopf bleiben', () => {
    render(
      <FokusVollbild
        titel="Energie-Bilanz"
        onClose={() => {}}
        deepLink
        aktionen={<button type="button">Link / Einbetten</button>}
        kopf={<p>Zeitraum-Nav</p>}
        tabelle={<p>Tabellen-Inhalt</p>}
      >
        <p>Chart-Inhalt</p>
      </FokusVollbild>,
    )
    expect(screen.queryByRole('button', { name: /Zurück/ })).not.toBeInTheDocument()
    expect(screen.queryByText('Fokus / Vollbild')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Link / Einbetten' })).not.toBeInTheDocument()
    // Was bleibt: die Zeitraum-Nav und der Chart-⇄-Tabelle-Umschalter.
    expect(screen.getByText('Zeitraum-Nav')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Tabelle' }))
    expect(screen.getByText('Tabellen-Inhalt')).toBeInTheDocument()
  })

  it('deepLink: ESC bleibt wirkungslos (kein Zuhörer registriert)', async () => {
    const onClose = vi.fn()
    render(<FokusVollbild titel="Verlauf" onClose={onClose} deepLink><p>Inhalt</p></FokusVollbild>)
    escSenden()
    await tick()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByText('Inhalt')).toBeInTheDocument()
  })

  it('ansichtStart="tabelle" startet in der Tabellen-Ablesung (CT-5)', () => {
    render(
      <FokusVollbild titel="Verlauf" onClose={() => {}} ansichtStart="tabelle" tabelle={<p>Tabellen-Inhalt</p>}>
        <p>Chart-Inhalt</p>
      </FokusVollbild>,
    )
    expect(screen.getByText('Tabellen-Inhalt')).toBeInTheDocument()
    expect(screen.queryByText('Chart-Inhalt')).not.toBeInTheDocument()
    // Der Umschalter bleibt bedienbar — `ansichtStart` ist ein Startwert, kein Zwang.
    fireEvent.click(screen.getByRole('button', { name: 'Chart' }))
    expect(screen.getByText('Chart-Inhalt')).toBeInTheDocument()
  })

  it('im normalen Betrieb steht der aktionen-Slot links vom „Zurück"', () => {
    render(
      <FokusVollbild titel="Verlauf" onClose={() => {}} aktionen={<button type="button">Link / Einbetten</button>}>
        <p>Inhalt</p>
      </FokusVollbild>,
    )
    const aktion = screen.getByRole('button', { name: 'Link / Einbetten' })
    const zurueck = screen.getByRole('button', { name: /Zurück/ })
    expect(aktion).toBeInTheDocument()
    // DOCUMENT_POSITION_FOLLOWING = 4: „Zurück" steht NACH der Aktion.
    expect(aktion.compareDocumentPosition(zurueck) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})

describe('FokusVollbild — Dialog-Betriebsart (Bau A §A5)', () => {
  const escSenden = () => document.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
  )

  it('Bestandsschutz: OHNE `dialog` rendert es exakt wie bisher — „Fokus / Vollbild", „Zurück", kein role/aria-modal', () => {
    // Auflage des Masters: der Default darf keinen bestehenden Nutzer verändern
    // (BlockShell, FokusKachel, Energiefluss-⤢, Deep-Link, FokusFehlt).
    render(<FokusVollbild titel="Verlauf" onClose={() => {}}><p>Inhalt</p></FokusVollbild>)
    expect(screen.getByText('Fokus / Vollbild')).toBeInTheDocument()
    // „Zurück" samt Klassen bitgleich zum Stand vor §A5 (ein Knopf für beide Betriebsarten)
    expect(screen.getByRole('button', { name: /Zurück/ }).className).toBe(
      'min-h-[44px] flex items-center gap-2 px-3 rounded-lg text-sm font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700',
    )
    expect(screen.queryByRole('button', { name: /Schließen/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const flaeche = document.body.querySelector('.fixed.inset-0') as HTMLElement
    expect(flaeche.hasAttribute('role')).toBe(false)
    expect(flaeche.hasAttribute('aria-modal')).toBe(false)
    expect(flaeche.hasAttribute('aria-labelledby')).toBe(false)
    expect(screen.getByRole('heading', { name: /Verlauf/ }).hasAttribute('id')).toBe(false)
    // …und der Fokus bleibt, wo er war — nur der Dialog zieht ihn an sich.
    expect(document.activeElement).toBe(document.body)
  })

  it('dialog: role="dialog" + aria-modal, der zugängliche Name IST der Titel', () => {
    render(<FokusVollbild titel="Süd (5)" dialog onClose={() => {}}><p>Liste</p></FokusVollbild>)
    const d = screen.getByRole('dialog', { name: 'Süd (5)' })
    expect(d.getAttribute('aria-modal')).toBe('true')
    const ueberschrift = document.getElementById(d.getAttribute('aria-labelledby')!)
    expect(ueberschrift?.tagName).toBe('H2')
    expect(ueberschrift?.textContent).toBe('Süd (5)')
    // Inhalt UND Schließen-Knopf liegen im modalen Bereich.
    expect(d.contains(screen.getByText('Liste'))).toBe(true)
    expect(d.contains(screen.getByRole('button', { name: /Schließen/ }))).toBe(true)
  })

  it('dialog: „Schließen" statt „Zurück", keine Unterzeile „Fokus / Vollbild", Fokus steht auf „Schließen"', () => {
    const onClose = vi.fn()
    render(<FokusVollbild titel="Speicher (4)" dialog onClose={onClose}><p>Liste</p></FokusVollbild>)
    const schliessen = screen.getByRole('button', { name: /Schließen/ })
    expect(screen.queryByRole('button', { name: /Zurück/ })).not.toBeInTheDocument()
    expect(screen.queryByText('Fokus / Vollbild')).not.toBeInTheDocument()
    expect(document.activeElement).toBe(schliessen)
    fireEvent.click(schliessen)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('dialog: ESC schließt wie im Normalmodus (Makrotask, nach defaultPrevented)', async () => {
    const onClose = vi.fn()
    render(<FokusVollbild titel="Laden (2)" dialog onClose={onClose}><p>Liste</p></FokusVollbild>)
    escSenden()
    await tick()
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
