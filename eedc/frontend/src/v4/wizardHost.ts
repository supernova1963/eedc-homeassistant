/**
 * Wizard-Host-Kontext (IA-V4, Style-Guide Teil D, W2/W5).
 *
 * Getrennt vom {@link EinstellungenModalHost}-Komponentenmodul, damit der Hook
 * `useWizardHost` nicht die react-refresh-Regel bricht (Komponenten-Datei =
 * nur Komponenten-Exporte). Der Host befüllt den Provider, die Wizards ziehen
 * `schliessen`/`abbrechen`/`setzeBlocker` hier heraus. Ohne Provider (Standalone-
 * Route) `imOverlay: false` → die Wizards fallen auf ihr `navigate`-Verhalten zurück.
 *
 * Mängelbehebung D/E (2026-07-11): zusätzlich (a) `oeffneWizard` für
 * Cross-Wizard-Sprünge AUS einem Overlay-Wizard heraus (D1-Hub-Karten,
 * D2 „→ Statistik-Import" — nie `navigate` in einen anderen Overlay-Wizard)
 * und (b) ein `payload`-Kanal (E1: Monatsabschluss braucht anlageId/jahr/monat
 * aus der aufrufenden Zeile). Der globale Öffner lebt im
 * {@link WizardSteuerungContext} (Provider = `WizardOverlayProvider` in LayoutV4).
 */
import { createContext, useContext } from 'react'

/** Schlüssel der im Overlay-Host registrierten Wizards (Registry im ModalHost). */
export type WizardKey =
  | 'sensor-mapping'
  | 'csv-import'
  | 'custom-import'
  | 'portal-import'
  | 'cloud-import'
  | 'connector'
  | 'ha-statistik-import'
  | 'einrichtung'
  | 'mqtt-inbound'
  | 'monatsabschluss'

/** E1/E2-Payload des Monatsabschluss-Wizards (aus Zeile/Button/Fusszeile, wie V3-URL-Params). */
export interface MonatsabschlussPayload {
  anlageId: number
  jahr?: number
  monat?: number
}

export interface WizardHostCtx {
  /** Läuft der Wizard im Overlay-Host (true) oder als Standalone-Route (false)? */
  imOverlay: boolean
  /** Terminal-Schluss (nach Commit/Ergebnis) — schließt das Overlay ohne Nachfrage. */
  schliessen: () => void
  /** Abbruch durch den Nutzer — löst bei gesetztem Blocker die Verwerfen-Nachfrage aus. */
  abbrechen: () => void
  /** Wizard meldet ungespeicherte Eingaben (true) → Frame-Schluss/Abbruch fragt nach. */
  setzeBlocker: (aktiv: boolean) => void
  /** Cross-Wizard-Sprung im selben Overlay (ersetzt `navigate` zwischen Wizards). */
  oeffneWizard: (key: WizardKey, payload?: unknown) => void
  /** Aufruf-Parameter des offenen Wizards (E1-Payload-Kanal), `undefined` ohne. */
  payload: unknown
}

const NOOP_HOST: WizardHostCtx = {
  imOverlay: false,
  schliessen: () => {},
  abbrechen: () => {},
  setzeBlocker: () => {},
  oeffneWizard: () => {},
  payload: undefined,
}

export const WizardHostContext = createContext<WizardHostCtx | null>(null)

/** Wizard-Host-Kontext; ohne Provider (Standalone-Route) `imOverlay: false`. */
export function useWizardHost(): WizardHostCtx {
  return useContext(WizardHostContext) ?? NOOP_HOST
}

/**
 * Globaler Wizard-Öffner (Provider: `WizardOverlayProvider` in LayoutV4) — für
 * Aufrufer AUSSERHALB des Overlays (StatusFusszeile, Katalog-Blöcke, Teile).
 * `null` ohne Provider, damit Aufrufer einen lokalen Fallback fahren können.
 */
export const WizardSteuerungContext =
  createContext<((key: WizardKey, payload?: unknown) => void) | null>(null)

export function useOeffneWizard(): ((key: WizardKey, payload?: unknown) => void) | null {
  return useContext(WizardSteuerungContext)
}
