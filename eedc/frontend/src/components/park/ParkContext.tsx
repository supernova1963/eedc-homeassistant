/**
 * ParkContext — app-weiter „Anzeige-Papierkorb" auf Element-Ebene (IA-V4 SLICE 1).
 *
 * Zweite, feinere Anpass-Ebene NEBEN {@link BlockShell} (Block-Ebene: einklappen/
 * verschieben/Fokus). Hier: einzelne Anzeigen (KPICard, Chart, Tabelle …) per Geste
 * **parken/entparken** — KEIN Umsortieren, jedes Element hat seine feste kanonische
 * Position und kehrt beim Zurückholen exakt dorthin zurück.
 *
 * SoT-Doku: docs/drafts/SPEC-ELEMENT-LAYOUT-PAPIERKORB.md (Gernot-Abnahme 2026-06-25).
 *
 * Persistenz wie BlockShell: pro Sicht ein localStorage-Eintrag `eedc-park:<key>`.
 * Schema-robust beim Laden (nur gültige Form). `titel` wird MITPERSISTIERT, damit der
 * „Geparkt (n)"-Block die Chips auch nach Reload kennt, bevor ein Element gemountet ist.
 *
 * Release-sicher (vor dem v4-Flip): ohne ParkProvider liefert {@link usePark} das
 * `aktiv:false`-No-Op → Wrapper/KpiStrip bleiben verhaltens- und DOM-gleich. Park-Code
 * ist damit inert, solange keine Sicht aktiv opt-in macht.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

const LS_PREFIX = 'eedc-park:'

export interface GeparktesElement {
  id: string
  titel: string
}

export interface ParkApi {
  /** true nur innerhalb eines ParkProvider — sonst No-Op (Produktion/v3). */
  aktiv: boolean
  istGeparkt: (id: string) => boolean
  /** Parken; `titel` wird für den Papierkorb-Chip mitpersistiert. */
  park: (id: string, titel: string) => void
  entparke: (id: string) => void
  /** alle zurückholen (= Set leeren). */
  zuruecksetzen: () => void
  geparkt: GeparktesElement[]
}

const NOOP: ParkApi = {
  aktiv: false,
  istGeparkt: () => false,
  park: () => {},
  entparke: () => {},
  zuruecksetzen: () => {},
  geparkt: [],
}

const ParkCtx = createContext<ParkApi>(NOOP)

/** Element-Park-Zustand pro Sicht. `usePark()` außerhalb = inertes No-Op. */
export function usePark(): ParkApi {
  return useContext(ParkCtx)
}

function laden(key: string): GeparktesElement[] {
  try {
    const raw = localStorage.getItem(LS_PREFIX + key)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    // Schema-robust: nur {id,titel}-Objekte übernehmen (verträgt alte/fremde Formen).
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (e): e is GeparktesElement =>
        e && typeof e.id === 'string' && typeof e.titel === 'string',
    )
  } catch {
    return []
  }
}

export function ParkProvider({
  persistKey,
  children,
}: {
  persistKey: string
  children: ReactNode
}) {
  const [geparkt, setGeparkt] = useState<GeparktesElement[]>(() => laden(persistKey))

  // Sichtwechsel (persistKey ändert sich) → frisch aus dem passenden Scope laden.
  useEffect(() => {
    setGeparkt(laden(persistKey))
  }, [persistKey])

  useEffect(() => {
    try {
      localStorage.setItem(LS_PREFIX + persistKey, JSON.stringify(geparkt))
    } catch {
      /* localStorage nicht verfügbar (Privatmodus) — Persistenz still überspringen */
    }
  }, [persistKey, geparkt])

  const istGeparkt = useCallback((id: string) => geparkt.some((e) => e.id === id), [geparkt])
  const park = useCallback((id: string, titel: string) => {
    setGeparkt((g) => (g.some((e) => e.id === id) ? g : [...g, { id, titel }]))
  }, [])
  const entparke = useCallback((id: string) => {
    setGeparkt((g) => g.filter((e) => e.id !== id))
  }, [])
  const zuruecksetzen = useCallback(() => setGeparkt([]), [])

  const api = useMemo<ParkApi>(
    () => ({ aktiv: true, istGeparkt, park, entparke, zuruecksetzen, geparkt }),
    [istGeparkt, park, entparke, zuruecksetzen, geparkt],
  )

  return <ParkCtx.Provider value={api}>{children}</ParkCtx.Provider>
}
