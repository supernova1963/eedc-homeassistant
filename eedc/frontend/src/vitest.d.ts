/// <reference types="vitest/globals" />
// Registriert die jest-dom-Matcher-Typen (toBeInTheDocument …) für die
// globale `expect` von Vitest, damit `tsc` die Test-Dateien sauber prüft.
import '@testing-library/jest-dom/vitest'
