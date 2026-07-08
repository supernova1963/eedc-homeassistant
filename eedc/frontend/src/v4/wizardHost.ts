/**
 * Wizard-Host-Kontext (IA-V4, Style-Guide Teil D, W2/W5).
 *
 * Getrennt vom {@link EinstellungenModalHost}-Komponentenmodul, damit der Hook
 * `useWizardHost` nicht die react-refresh-Regel bricht (Komponenten-Datei =
 * nur Komponenten-Exporte). Der Host befüllt den Provider, die Wizards ziehen
 * `schliessen`/`abbrechen`/`setzeBlocker` hier heraus. Ohne Provider (Standalone-
 * Route) `imOverlay: false` → die Wizards fallen auf ihr `navigate`-Verhalten zurück.
 */
import { createContext, useContext } from 'react'

export interface WizardHostCtx {
  /** Läuft der Wizard im Overlay-Host (true) oder als Standalone-Route (false)? */
  imOverlay: boolean
  /** Terminal-Schluss (nach Commit/Ergebnis) — schließt das Overlay ohne Nachfrage. */
  schliessen: () => void
  /** Abbruch durch den Nutzer — löst bei gesetztem Blocker die Verwerfen-Nachfrage aus. */
  abbrechen: () => void
  /** Wizard meldet ungespeicherte Eingaben (true) → Frame-Schluss/Abbruch fragt nach. */
  setzeBlocker: (aktiv: boolean) => void
}

const NOOP_HOST: WizardHostCtx = {
  imOverlay: false,
  schliessen: () => {},
  abbrechen: () => {},
  setzeBlocker: () => {},
}

export const WizardHostContext = createContext<WizardHostCtx | null>(null)

/** Wizard-Host-Kontext; ohne Provider (Standalone-Route) `imOverlay: false`. */
export function useWizardHost(): WizardHostCtx {
  return useContext(WizardHostContext) ?? NOOP_HOST
}
