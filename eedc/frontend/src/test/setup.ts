// Vitest-Setup: jest-dom-Matcher (toBeInTheDocument etc.) registrieren +
// nach jedem Test das DOM aufräumen. Wird via vitest.config.ts geladen.
import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
})
