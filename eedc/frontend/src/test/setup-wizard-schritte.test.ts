/**
 * Setup-Wizard Schritt-Umfang — v3.46-Scope-Gate (Gernot-Entscheid 2026-07-18):
 * Der D2-Integrations-Schritt darf NUR unter IA_V4 in der Schritt-Reihenfolge
 * stehen. Vitest läuft ohne VITE_IA_V4 und prüft damit exakt den Umfang des
 * v3.x-Release-Builds (Standard-Build ohne Flag).
 */
import { describe, it, expect } from 'vitest'
import { STEP_ORDER } from '../hooks/useSetupWizard'
import { IA_V4 } from '../lib/flags'

describe('Setup-Wizard Schritt-Umfang (v3.46-Scope)', () => {
  it('führt den Integrations-Schritt genau dann, wenn IA_V4 aktiv ist', () => {
    expect(STEP_ORDER.includes('integration')).toBe(IA_V4)
  })

  it('Standard-Build (Flag aus): Alt-Umfang ohne Integrations-Schritt', () => {
    expect(IA_V4).toBe(false)
    expect(STEP_ORDER).toEqual([
      'welcome',
      'anlage',
      'strompreise',
      'investitionen',
      'summary',
      'complete',
    ])
  })
})
