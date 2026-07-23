/**
 * Setup-Wizard Schritt-Umfang (IA-V4, Flip v4.0.0).
 * Der D2-Integrations-Schritt ist fester Bestandteil der Schritt-Reihenfolge —
 * das frühere flag-abhängige Gate (IA_V4) ist mit dem Flip entfallen.
 */
import { describe, it, expect } from 'vitest'
import { STEP_ORDER } from '../hooks/useSetupWizard'

describe('Setup-Wizard Schritt-Umfang', () => {
  it('führt den Integrations-Schritt (D2)', () => {
    expect(STEP_ORDER.includes('integration')).toBe(true)
  })

  it('vollständige Schritt-Reihenfolge', () => {
    expect(STEP_ORDER).toEqual([
      'welcome',
      'anlage',
      'strompreise',
      'investitionen',
      'integration',
      'summary',
      'complete',
    ])
  })
})
