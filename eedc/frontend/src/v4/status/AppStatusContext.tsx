/**
 * AppStatusContext — Versorgungsschicht der app-weiten Status-Fusszeile (G11, P1).
 *
 * SPEC: `docs/drafts/SPEC-STATUS-FUSSZEILE.md`. Zwei Belange, ein Provider in der
 * Shell (`LayoutV4`):
 *   - **Demo-Modus** global (war zuvor lokaler State der Live-Sicht; nur Live nutzt
 *     ihn funktional, aber der Schalter sitzt jetzt global in der Fusszeile).
 *   - **Sicht-Daten-Status**: die gerade gezeigte Sicht *meldet* Frische/Live/Quelle
 *     via {@link useReportDatenStatus}; die Fusszeile *konsumiert* sie.
 *
 * Außerhalb des Providers (Tests, backendlose Preview) liefert der Context einen
 * no-op-Default — robuster Leser, kein Crash ([[feedback_persistenter_cache_versions_skew]]-Geist).
 */
import { createContext, useContext, useState, useEffect, useMemo, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DEMO_DEFAULT } from '../../lib/flags'

/** Was eine Sicht über die Frische/Herkunft der gezeigten Daten meldet. */
export interface SichtStatus {
  /** Live-Datenkanal aktiv (grüner Punkt). */
  live?: boolean
  /** Zeitpunkt der letzten Aktualisierung, bereits formatiert (z. B. „09:59:57"). */
  aktualisiertText?: string | null
  /** Poll-Intervall-Hinweis, z. B. „(5s)" — nur wo gepollt wird. */
  intervallText?: string | null
  /** Datenquelle/Provenance der Sicht (P5-Ausbau). */
  quelle?: string | null
}

interface AppStatusValue {
  status: SichtStatus
  setStatus: (s: SichtStatus) => void
  demoMode: boolean
  setDemoMode: (v: boolean) => void
  /** Demo-Schalter nur unter `?debug` / `VITE_DEMO_DEFAULT` sichtbar (Dev-Affordance). */
  isDebug: boolean
}

const DEFAULT: AppStatusValue = {
  status: {},
  setStatus: () => {},
  demoMode: DEMO_DEFAULT,
  setDemoMode: () => {},
  isDebug: DEMO_DEFAULT,
}

const AppStatusContext = createContext<AppStatusValue>(DEFAULT)

export function AppStatusProvider({ children }: { children: ReactNode }) {
  const [searchParams] = useSearchParams()
  const [status, setStatus] = useState<SichtStatus>({})
  const [demoMode, setDemoMode] = useState(DEMO_DEFAULT)
  const isDebug = searchParams.has('debug') || DEMO_DEFAULT

  const value = useMemo<AppStatusValue>(
    () => ({ status, setStatus, demoMode, setDemoMode, isDebug }),
    [status, demoMode, isDebug],
  )
  return <AppStatusContext.Provider value={value}>{children}</AppStatusContext.Provider>
}

export function useAppStatus(): AppStatusValue {
  return useContext(AppStatusContext)
}

/** Globaler Demo-Schalter (Live liest ihn für seine Requests; Fusszeile schaltet ihn). */
export function useDemoMode() {
  const { demoMode, setDemoMode, isDebug } = useAppStatus()
  return { demoMode, setDemoMode, isDebug }
}

/**
 * Die aktive Sicht meldet ihren Daten-Status in die Fusszeile und räumt beim
 * Verlassen wieder auf (Sichtwechsel = Live-Intervall-Hinweis verschwindet).
 */
export function useReportDatenStatus(s: SichtStatus): void {
  const { setStatus } = useAppStatus()
  const { live, aktualisiertText, intervallText, quelle } = s
  useEffect(() => {
    setStatus({ live, aktualisiertText, intervallText, quelle })
    return () => setStatus({})
  }, [setStatus, live, aktualisiertText, intervallText, quelle])
}
