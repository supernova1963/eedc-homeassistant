/**
 * JahrStepper — Jahres-Adapter der generischen {@link ZeitStepper}-SoT (mobil).
 * Desktop behält die {@link JahresRail}; mobil:
 *   ⏮ ältestes · ◀ −1 Jahr · [Jahr ▾ → Liste] · ▶ +1 Jahr · ⏭ neuestes
 * (Jahre sind wenige → nur 2+2 Buttons, kein ±N-Sprung, kein Datumsfeld.)
 */
import { useMemo } from 'react'
import { ChevronFirst, ChevronLeft, ChevronRight, ChevronLast } from 'lucide-react'
import type { JahrRailEintrag } from './JahresRail'
import { ZeitStepper, type ZeitStepperEintrag } from './ZeitStepper'
import { fmtZahl } from '../lib'

interface JahrStepperProps {
  entries: JahrRailEintrag[]
  jahr: number
  onSelect: (jahr: number) => void
  /** D10-2: im Fokus/Vollbild-Kopf auf jeder Breite sichtbar (durchgereicht). */
  immerSichtbar?: boolean
}

export function JahrStepper({ entries, jahr, onSelect, immerSichtbar }: JahrStepperProps) {
  const desc = useMemo(() => [...entries].sort((a, b) => b.jahr - a.jahr), [entries])
  const oldest = useMemo(() => entries.reduce((m, e) => Math.min(m, e.jahr), entries[0]?.jahr ?? jahr), [entries, jahr])
  const newest = useMemo(() => entries.reduce((m, e) => Math.max(m, e.jahr), entries[0]?.jahr ?? jahr), [entries, jahr])

  // Ziel-Aktion oder null (am Rand / auf sich selbst deaktiviert).
  const go = (j: number) => {
    const c = j < oldest ? oldest : j > newest ? newest : j
    return c === jahr ? null : () => onSelect(c)
  }
  const aktuell = entries.find((e) => e.jahr === jahr) ?? null

  const eintraege: ZeitStepperEintrag[] = desc.map((e) => ({
    key: String(e.jahr),
    label: String(e.jahr),
    wert: e.laufend ? 'läuft' : `${fmtZahl(e.pv_kwh, 0)} kWh`,
    aktiv: !!e.laufend,
    gewaehlt: e.jahr === jahr,
    onClick: () => onSelect(e.jahr),
  }))

  return (
    <ZeitStepper
      zurueck={[
        { icon: ChevronFirst, label: 'ältestes Jahr', go: go(oldest) },
        { icon: ChevronLeft, label: 'voriges Jahr', go: go(jahr - 1) },
      ]}
      vor={[
        { icon: ChevronRight, label: 'nächstes Jahr', go: go(jahr + 1) },
        { icon: ChevronLast, label: 'neuestes Jahr', go: go(newest) },
      ]}
      titel={String(jahr)}
      badge={aktuell?.laufend ? 'läuft' : null}
      eintraege={eintraege}
      immerSichtbar={immerSichtbar}
    />
  )
}
