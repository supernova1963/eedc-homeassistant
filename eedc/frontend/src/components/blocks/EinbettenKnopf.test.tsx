/**
 * EinbettenKnopf (FD-2) — die EINE Adresse, die ein Anwender in eine
 * HA-Webseiten-Karte einfügt.
 *
 * Geprüft: die Adresse aus einer **gestellten** `location` (Ingress und
 * Standalone), `&ansicht=tabelle` nur bei offener Tabelle, der
 * Standalone-Hinweis zur Mixed-Content-Grenze — und dass der Knopf in der
 * Deep-Link-Ansicht NICHT erscheint (dort gibt es niemanden, der kopiert).
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EinbettenKnopf, baueDeepLink, istIngress, type OrtAngaben } from './EinbettenKnopf'
import { FokusVollbild } from './FokusVollbild'

/** So sieht `window.location` unter dem HA-Ingress aus (gemessen 20.09.2026). */
const INGRESS: OrtAngaben = {
  href: 'http://homeassistant.local:8123/api/hassio_ingress/AbC123/#/cockpit/jahr?jahr=2025',
  hash: '#/cockpit/jahr?jahr=2025',
  pathname: '/api/hassio_ingress/AbC123/',
}

/** Standalone/Add-on-Port. */
const STANDALONE: OrtAngaben = {
  href: 'http://192.168.1.50:8099/#/cockpit/live',
  hash: '#/cockpit/live',
  pathname: '/',
}

describe('baueDeepLink — die Adresse', () => {
  it('hängt fokus an den Sicht-Pfad, unter Ingress mit Ingress-Basis', () => {
    expect(baueDeepLink(INGRESS, 'bilanz', 'chart'))
      .toBe('http://homeassistant.local:8123/api/hassio_ingress/AbC123/#/cockpit/jahr?fokus=bilanz')
  })

  it('Standalone: dieselbe Form auf dem eigenen Port', () => {
    expect(baueDeepLink(STANDALONE, 'live:tagesverlauf', 'chart'))
      .toBe('http://192.168.1.50:8099/#/cockpit/live?fokus=live%3Atagesverlauf')
  })

  it('ansicht=tabelle nur, wenn die Tabelle offen ist (CT-5)', () => {
    expect(baueDeepLink(STANDALONE, 'verlauf', 'tabelle'))
      .toBe('http://192.168.1.50:8099/#/cockpit/live?fokus=verlauf&ansicht=tabelle')
    expect(baueDeepLink(STANDALONE, 'verlauf', 'chart')).not.toMatch(/ansicht/)
  })

  it('⛔ Zeitraum-Parameter der Sicht kommen NICHT mit (Entscheid 22.09.)', () => {
    // `?jahr=2025` steht in der Quell-Adresse — die Karte soll trotzdem das
    // laufende Jahr zeigen, nicht das beim Kopieren offene.
    expect(baueDeepLink(INGRESS, 'bilanz', 'chart')).not.toMatch(/jahr=2025/)
  })

  it('verträgt eine Adresse ohne Hash (Wurzel)', () => {
    expect(baueDeepLink({ href: 'http://x/', hash: '', pathname: '/' }, 'a', 'chart'))
      .toBe('http://x/#/?fokus=a')
  })

  it('erkennt den Ingress am Pfad', () => {
    expect(istIngress(INGRESS)).toBe(true)
    expect(istIngress(STANDALONE)).toBe(false)
  })
})

describe('EinbettenKnopf — Dialog', () => {
  it('zeigt Adresse + Anleitung; der Standalone-Hinweis nur ohne Ingress', () => {
    render(<EinbettenKnopf fokusId="bilanz" ansicht="chart" ort={STANDALONE} />)
    fireEvent.click(screen.getByRole('button', { name: /Link \/ Einbetten/ }))
    expect(screen.getByText('http://192.168.1.50:8099/#/cockpit/live?fokus=bilanz')).toBeInTheDocument()
    expect(screen.getByText(/Dashboard bearbeiten/)).toBeInTheDocument()
    expect(screen.getByText(/Mixed Content/)).toBeInTheDocument()
  })

  it('unter Ingress steht der Mixed-Content-Satz NICHT da (er gilt dort nicht)', () => {
    render(<EinbettenKnopf fokusId="bilanz" ansicht="chart" ort={INGRESS} />)
    fireEvent.click(screen.getByRole('button', { name: /Link \/ Einbetten/ }))
    expect(screen.getByText(/api\/hassio_ingress\/AbC123/)).toBeInTheDocument()
    expect(screen.queryByText(/Mixed Content/)).not.toBeInTheDocument()
  })
})

describe('EinbettenKnopf im Fokus-Overlay', () => {
  const URSPRUNG = window.location.hash
  beforeEach(() => { window.location.hash = '' })
  afterEach(() => { window.location.hash = URSPRUNG })

  it('steht im normalen Betrieb in der Kopfzeile und kennt die offene Ablesung', () => {
    render(
      <FokusVollbild
        titel="Verlauf" onClose={() => {}} tabelle={<p>Tabellen-Inhalt</p>}
        aktionen={(ansicht) => <EinbettenKnopf fokusId="verlauf" ansicht={ansicht} ort={STANDALONE} />}
      >
        <p>Chart-Inhalt</p>
      </FokusVollbild>,
    )
    fireEvent.click(screen.getByRole('button', { name: /Link \/ Einbetten/ }))
    expect(screen.getByText(/\?fokus=verlauf$/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Schließen' }))

    // Auf die Tabelle umschalten ⇒ die Adresse trägt `&ansicht=tabelle`.
    fireEvent.click(screen.getByRole('button', { name: 'Tabelle' }))
    fireEvent.click(screen.getByRole('button', { name: /Link \/ Einbetten/ }))
    expect(screen.getByText(/\?fokus=verlauf&ansicht=tabelle$/)).toBeInTheDocument()
  })

  it('in der Deep-Link-Ansicht gibt es ihn nicht', () => {
    render(
      <FokusVollbild
        titel="Verlauf" onClose={() => {}} deepLink
        aktionen={(ansicht) => <EinbettenKnopf fokusId="verlauf" ansicht={ansicht} ort={STANDALONE} />}
      >
        <p>Chart-Inhalt</p>
      </FokusVollbild>,
    )
    expect(screen.queryByRole('button', { name: /Link \/ Einbetten/ })).not.toBeInTheDocument()
  })
})
