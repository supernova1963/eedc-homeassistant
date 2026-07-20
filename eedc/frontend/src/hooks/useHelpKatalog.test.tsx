/**
 * useHelpKatalog — geteilte Hilfe-Daten-/Link-Logik (R2b).
 * Sichert: Index-Fetch + Kategorie-Gruppierung (Index-Reihenfolge), Dokument-
 * Fetch, `onDocLoaded`-Callback, unbekannter Slug → Fehler, und der
 * `rewriteLink`-Rewrite (intern/extern/Anker) — die EINE Quelle für V3+V4.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useHelpKatalog, DEFAULT_SLUG, type HelpDoc } from './useHelpKatalog'

const INDEX: HelpDoc[] = [
  { slug: 'benutzerhandbuch', title: 'Übersicht', category: 'Einstieg', filename: 'BENUTZERHANDBUCH.md' },
  { slug: 'was-ist-neu', title: 'Was ist neu', category: 'Einstieg', filename: 'WAS-IST-NEU.md' },
  { slug: 'installation', title: 'Teil I', category: 'Handbuch', filename: 'HANDBUCH_INSTALLATION.md' },
  { slug: 'glossar', title: 'Glossar', category: 'Referenz', filename: 'GLOSSAR.md' },
]

function mockFetch() {
  return vi.fn((url: string) => {
    if (url.endsWith('index.json')) return Promise.resolve({ ok: true, json: () => Promise.resolve(INDEX) })
    const md = url.match(/help\/([^./]+)\.md$/)
    if (md) return Promise.resolve({ ok: true, text: () => Promise.resolve(`# ${md[1]}\n`) })
    return Promise.resolve({ ok: false, status: 404 })
  })
}

beforeEach(() => { vi.stubGlobal('fetch', mockFetch()) })
afterEach(() => { vi.unstubAllGlobals() })

describe('useHelpKatalog', () => {
  it('lädt den Index und gruppiert nach Kategorie in Index-Reihenfolge', async () => {
    const { result } = renderHook(() => useHelpKatalog(DEFAULT_SLUG, ''))
    await waitFor(() => expect(result.current.docs).not.toBeNull())
    expect(result.current.grouped.map((g) => g.category)).toEqual(['Einstieg', 'Handbuch', 'Referenz'])
    expect(result.current.grouped[0].items.map((d) => d.slug)).toEqual(['benutzerhandbuch', 'was-ist-neu'])
    expect(result.current.grouped[2].items).toHaveLength(1)
  })

  it('lädt das aktive Dokument und meldet activeDoc', async () => {
    const { result } = renderHook(() => useHelpKatalog('glossar', ''))
    await waitFor(() => expect(result.current.content).toContain('# glossar'))
    expect(result.current.activeDoc?.slug).toBe('glossar')
    expect(result.current.loading).toBe(false)
  })

  it('ruft onDocLoaded nach dem Dokument-Fetch (mit targetHash)', async () => {
    const onLoaded = vi.fn()
    renderHook(() => useHelpKatalog('benutzerhandbuch', 'abschnitt-x', onLoaded))
    await waitFor(() => expect(onLoaded).toHaveBeenCalledWith('abschnitt-x'))
  })

  it('setzt einen Fehler bei unbekanntem Slug', async () => {
    const { result } = renderHook(() => useHelpKatalog('gibts-nicht', ''))
    await waitFor(() => expect(result.current.error).toContain('gibts-nicht'))
    expect(result.current.content).toBe('')
  })

  describe('rewriteLink', () => {
    async function ladeRewrite() {
      const { result } = renderHook(() => useHelpKatalog(DEFAULT_SLUG, ''))
      await waitFor(() => expect(result.current.docs).not.toBeNull())
      return result.current.rewriteLink
    }

    it('bekanntes .md-Ziel → interner ?doc=-Link (Dateiname → slug)', async () => {
      const rw = await ladeRewrite()
      expect(rw('GLOSSAR.md')).toEqual({ type: 'internal', target: '?doc=glossar' })
      expect(rw('HANDBUCH_INSTALLATION.md#erst-setup')).toEqual({
        type: 'internal', target: '?doc=installation#erst-setup',
      })
    })

    it('unbekanntes .md-Ziel → externer GitHub-Link', async () => {
      const rw = await ladeRewrite()
      const r = rw('IRGENDWAS.md')
      expect(r.type).toBe('external')
      expect(r.target).toContain('github.com/supernova1963/eedc-homeassistant')
    })

    it('Anker und absolute URLs bleiben Anker/extern', async () => {
      const rw = await ladeRewrite()
      expect(rw('#zum-anker')).toEqual({ type: 'anchor', target: '#zum-anker' })
      expect(rw('https://example.com')).toEqual({ type: 'external', target: 'https://example.com' })
    })
  })
})
