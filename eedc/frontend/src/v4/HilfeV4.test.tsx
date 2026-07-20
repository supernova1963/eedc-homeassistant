/**
 * HilfeV4 — Hilfe-Sicht der IA-V4 (R2b).
 * Sichert: TOC mit den 3 Kategorien, „Was ist neu" als eigener prominenter
 * Einstieg (aus der Kategorie-Liste gelöst), Default-Dokument + `?doc=`-Deep-Link
 * rendern Markdown, und ein TOC-Klick wechselt das Dokument.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import HilfeV4 from './HilfeV4'

const INDEX = [
  { slug: 'benutzerhandbuch', title: 'Übersicht', category: 'Einstieg', filename: 'BENUTZERHANDBUCH.md' },
  { slug: 'was-ist-neu', title: 'Was ist neu', category: 'Einstieg', filename: 'WAS-IST-NEU.md' },
  { slug: 'installation', title: 'Teil I: Installation', category: 'Handbuch', filename: 'HANDBUCH_INSTALLATION.md' },
  { slug: 'glossar', title: 'Glossar', category: 'Referenz', filename: 'GLOSSAR.md' },
]

function mockFetch() {
  return vi.fn((url: string) => {
    if (url.endsWith('index.json')) return Promise.resolve({ ok: true, json: () => Promise.resolve(INDEX) })
    const md = url.match(/help\/([^./]+)\.md$/)
    if (md) return Promise.resolve({ ok: true, text: () => Promise.resolve(`# Inhalt ${md[1]}\n`) })
    return Promise.resolve({ ok: false, status: 404 })
  })
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <HilfeV4 />
    </MemoryRouter>,
  )
}

beforeEach(() => { vi.stubGlobal('fetch', mockFetch()) })
afterEach(() => { vi.unstubAllGlobals() })

describe('HilfeV4', () => {
  it('rendert die Kategorie-TOC (Einstieg/Handbuch/Referenz) und das Default-Dokument', async () => {
    renderAt('/v4/hilfe')
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Inhalt benutzerhandbuch' })).toBeInTheDocument())
    const nav = screen.getByRole('navigation', { name: 'Hilfe-Navigation' })
    expect(within(nav).getByText('Einstieg')).toBeInTheDocument()
    expect(within(nav).getByText('Handbuch')).toBeInTheDocument()
    expect(within(nav).getByText('Referenz')).toBeInTheDocument()
  })

  it('verortet „Was ist neu" als eigenen prominenten Einstieg (nicht in der Kategorie-Liste)', async () => {
    renderAt('/v4/hilfe')
    const neu = await screen.findByRole('link', { name: /Was ist neu/ })
    expect(neu).toHaveAttribute('href', expect.stringContaining('doc=was-ist-neu'))
    // In der Desktop-Kategorie-Liste taucht „Was ist neu" NICHT mehr als Eintrag auf.
    const nav = screen.getByRole('navigation', { name: 'Hilfe-Navigation' })
    const einstiegLinks = within(nav).getAllByRole('link').map((a) => a.textContent)
    expect(einstiegLinks).toContain('Übersicht')
    expect(einstiegLinks).not.toContain('Was ist neu')
  })

  it('lädt bei ?doc=<slug> direkt das passende Dokument', async () => {
    renderAt('/v4/hilfe?doc=glossar')
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Inhalt glossar' })).toBeInTheDocument())
  })

  it('ein TOC-Klick wechselt das Dokument', async () => {
    renderAt('/v4/hilfe')
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Inhalt benutzerhandbuch' })).toBeInTheDocument())
    const nav = screen.getByRole('navigation', { name: 'Hilfe-Navigation' })
    fireEvent.click(within(nav).getByRole('link', { name: 'Glossar' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Inhalt glossar' })).toBeInTheDocument())
  })
})
