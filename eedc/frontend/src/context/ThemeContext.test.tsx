/**
 * ThemeProvider — Theme-Quelle je Betriebsart (FD-1/B6).
 *
 * Normal: gespeicherte Vorliebe aus `localStorage` (`eedc-theme`), Default
 * `system`. In der **Deep-Link-Ansicht** (`#/…?fokus=<id>`, Webseiten-Karte im
 * HA-Dashboard): immer `system` — und **ohne** die gespeicherte Vorliebe zu
 * überschreiben.
 *
 * ⚠ Der Schreibzugriff läuft im Effekt und damit bei JEDEM Lauf inkl. Init; die
 * Probe prüft deshalb ausdrücklich den `localStorage`-Inhalt NACH dem Rendern,
 * nicht nur den angezeigten Wert.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ThemeProvider, useTheme } from './ThemeContext'

const URSPRUNG = window.location.hash

/** `matchMedia` mit gestelltem `prefers-color-scheme: dark`. */
function stubSystem(dunkel: boolean) {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
    matches: dunkel, media: '', onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }))
}

function Anzeige() {
  const { theme, isDark } = useTheme()
  return <span>{theme}|{String(isDark)}</span>
}

const zeige = () => render(<ThemeProvider><Anzeige /></ThemeProvider>)

describe('ThemeProvider — normaler Betrieb', () => {
  beforeEach(() => { localStorage.clear(); window.location.hash = ''; document.documentElement.classList.remove('dark') })
  afterEach(() => { window.location.hash = URSPRUNG; vi.unstubAllGlobals() })

  it('folgt der gespeicherten Vorliebe', () => {
    localStorage.setItem('eedc-theme', 'dark')
    stubSystem(false)
    zeige()
    expect(screen.getByText('dark|true')).toBeInTheDocument()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('ohne Vorliebe: system', () => {
    stubSystem(true)
    zeige()
    expect(screen.getByText('system|true')).toBeInTheDocument()
    expect(localStorage.getItem('eedc-theme')).toBe('system')
  })
})

describe('ThemeProvider — Deep-Link-Ansicht folgt dem System-Theme (FD-1/B6)', () => {
  beforeEach(() => { localStorage.clear(); window.location.hash = ''; document.documentElement.classList.remove('dark') })
  afterEach(() => { window.location.hash = URSPRUNG; vi.unstubAllGlobals() })

  it('mit ?fokus= gilt `system`, OBWOHL `dark` gespeichert ist', () => {
    localStorage.setItem('eedc-theme', 'dark')
    window.location.hash = '#/cockpit/jahr?fokus=bilanz'
    stubSystem(false)
    zeige()
    expect(screen.getByText('system|false')).toBeInTheDocument()
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('… und die gespeicherte Vorliebe bleibt unangetastet', () => {
    localStorage.setItem('eedc-theme', 'dark')
    window.location.hash = '#/cockpit/jahr?fokus=bilanz'
    stubSystem(true)
    zeige()
    expect(screen.getByText('system|true')).toBeInTheDocument()
    // ⛔ Der Kern: ein Dashboard mit einer eedc-Karte darf die Wahl des
    // Anwenders in der App nicht umschreiben.
    expect(localStorage.getItem('eedc-theme')).toBe('dark')
  })

  it('ein dunkles System färbt die Karte dunkel', () => {
    window.location.hash = '#/cockpit/live?fokus=live:tagesverlauf'
    stubSystem(true)
    zeige()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })
})
