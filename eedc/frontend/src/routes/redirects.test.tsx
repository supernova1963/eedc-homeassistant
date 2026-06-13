import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom'
import { LEGACY_REDIRECTS, REAL_ROUTE_PATHS } from './routeManifest'

// Redirect-Auto-Test (E1-P3) — Fundament für den vollständigen 3.8-Test.
// Sichert die zwei Invarianten der Redirect-Tabelle: jeder Alt-Pfad landet
// ohne 404 auf einer echten Route, und es gibt keine Redirect-Ketten.

/** Normalisiert einen Ziel-/Quell-Pfad auf segmentierte Form ohne führenden Slash. */
function segs(p: string): string[] {
  return p.replace(/^\/+/, '').split('/').filter(Boolean)
}

/** Trifft ein konkreter Pfad eine der echten Routen (`:param` ist Wildcard)? */
function matchtEchteRoute(target: string): boolean {
  const t = segs(target)
  return REAL_ROUTE_PATHS.some((pattern) => {
    const p = segs(pattern)
    if (p.length !== t.length) return false
    return p.every((s, i) => s.startsWith(':') || s === t[i])
  })
}

const fromSet = new Set(LEGACY_REDIRECTS.map((r) => segs(r.from).join('/')))

describe('Bestands-Redirects — Datenintegrität', () => {
  it('jeder Eintrag ist wohlgeformt (from ohne Slash, to mit Slash)', () => {
    for (const r of LEGACY_REDIRECTS) {
      expect(r.from.length, `from leer: ${JSON.stringify(r)}`).toBeGreaterThan(0)
      expect(r.from.startsWith('/'), `from mit Slash: ${r.from}`).toBe(false)
      expect(r.to.startsWith('/'), `to ohne Slash: ${r.to}`).toBe(true)
    }
  })

  it('keine Redirect-Ketten (kein Ziel ist selbst ein Alt-Pfad)', () => {
    for (const r of LEGACY_REDIRECTS) {
      const zielSchluessel = segs(r.to).join('/')
      expect(
        fromSet.has(zielSchluessel),
        `Kette: ${r.from} → ${r.to} (Ziel ist selbst ein Redirect)`,
      ).toBe(false)
    }
  })

  it('jedes Ziel trifft eine echte Route (kein 404)', () => {
    for (const r of LEGACY_REDIRECTS) {
      expect(matchtEchteRoute(r.to), `Ziel ohne echte Route (404): ${r.from} → ${r.to}`).toBe(true)
    }
  })

  it('keine doppelten Alt-Pfade', () => {
    const froms = LEGACY_REDIRECTS.map((r) => segs(r.from).join('/'))
    expect(new Set(froms).size).toBe(froms.length)
  })
})

// Vollständige Routen-Tabelle nachbauen: echte Routen = Stub „OK", Redirects =
// Navigate, alles andere = „404". Beweist, dass die Navigate-Logik jeden
// Alt-Pfad auf einen echten Stub auflöst (Render-Pfad, nicht nur Daten).
function renderPfad(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        {REAL_ROUTE_PATHS.map((p) => (
          <Route key={p} path={p} element={<div>OK</div>} />
        ))}
        {LEGACY_REDIRECTS.map((r) => (
          <Route key={r.from} path={r.from} element={<Navigate to={r.to} replace />} />
        ))}
        <Route path="*" element={<div>404</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('Bestands-Redirects — Render (keine 404)', () => {
  it.each(LEGACY_REDIRECTS)('Alt-Pfad /$from landet ohne 404', (r) => {
    const { unmount } = renderPfad(`/${r.from}`)
    expect(screen.getByText('OK')).toBeInTheDocument()
    expect(screen.queryByText('404')).not.toBeInTheDocument()
    unmount()
  })

  it('eine Auswahl echter Routen rendert direkt (Stichprobe)', () => {
    for (const p of ['/live', '/auswertungen/energie', '/aussichten/kurzfristig', '/community/uebersicht', '/cockpit/monatsberichte']) {
      const { unmount } = renderPfad(p)
      expect(screen.getByText('OK')).toBeInTheDocument()
      unmount()
    }
  })

  it('ein unbekannter Pfad fällt auf 404', () => {
    renderPfad('/gibt-es-nicht')
    expect(screen.getByText('404')).toBeInTheDocument()
  })
})
