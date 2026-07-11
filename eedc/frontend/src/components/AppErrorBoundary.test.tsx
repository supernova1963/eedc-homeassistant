/**
 * AppErrorBoundary — R18-1: ChunkLoadError (veralteter Hash-Chunk nach Deploy)
 * endet in „eedc wurde aktualisiert" + Reload-Angebot; generische Render-Fehler
 * im Fehler-Baustein mit Reload. Kein dauerhaft schwarzer Bildschirm mehr.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AppErrorBoundary } from './AppErrorBoundary'

function Bombe({ fehler }: { fehler: Error }): never {
  throw fehler
}

describe('AppErrorBoundary (R18-1)', () => {
  // React loggt gefangene Fehler laut auf console.error — im Test stummschalten.
  beforeEach(() => vi.spyOn(console, 'error').mockImplementation(() => {}))
  afterEach(() => vi.restoreAllMocks())

  it('rendert Kinder ohne Fehler unverändert', () => {
    render(<AppErrorBoundary><p>Inhalt</p></AppErrorBoundary>)
    expect(screen.getByText('Inhalt')).toBeInTheDocument()
  })

  it('Vite-Chunk-Fehler → „eedc wurde aktualisiert" + Neu-laden-Button', () => {
    const fehler = new TypeError('Failed to fetch dynamically imported module: https://x/assets/CockpitV4-abc.js')
    render(<AppErrorBoundary><Bombe fehler={fehler} /></AppErrorBoundary>)
    expect(screen.getByText('eedc wurde aktualisiert')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Neu laden/ })).toBeInTheDocument()
  })

  it('klassischer ChunkLoadError (name) wird ebenfalls erkannt', () => {
    const fehler = new Error('Loading chunk 42 failed.')
    fehler.name = 'ChunkLoadError'
    render(<AppErrorBoundary><Bombe fehler={fehler} /></AppErrorBoundary>)
    expect(screen.getByText('eedc wurde aktualisiert')).toBeInTheDocument()
  })

  it('generischer Render-Fehler → „Unerwarteter Fehler" + Reload löst location.reload aus', () => {
    const reload = vi.fn()
    const original = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...original, reload },
    })
    render(<AppErrorBoundary><Bombe fehler={new Error('Kaputt')} /></AppErrorBoundary>)
    expect(screen.getByText('Unerwarteter Fehler')).toBeInTheDocument()
    expect(screen.getByText(/Kaputt/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Neu laden/ }))
    expect(reload).toHaveBeenCalledTimes(1)
    Object.defineProperty(window, 'location', { configurable: true, value: original })
  })
})
