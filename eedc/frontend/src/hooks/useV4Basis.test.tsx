/**
 * useV4Basis — Cross-Link-Präfix je Welt (geteilte pages/*Teile.tsx).
 * Sichert: unter /v4/… → '/v4', in V3 → '' (kein V4→V3-Sackgassen-Link).
 */
import { describe, it, expect } from 'vitest'
import type { ReactNode } from 'react'
import { renderHook } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { useV4Basis } from './useV4Basis'

function wrapper(path: string) {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
  )
}

describe('useV4Basis', () => {
  it("liefert '/v4' unter /v4/…", () => {
    const { result } = renderHook(() => useV4Basis(), { wrapper: wrapper('/v4/einstellungen/komponenten') })
    expect(result.current).toBe('/v4')
  })

  it("liefert '' in der V3-Welt", () => {
    const { result } = renderHook(() => useV4Basis(), { wrapper: wrapper('/einstellungen/investitionen') })
    expect(result.current).toBe('')
  })
})
