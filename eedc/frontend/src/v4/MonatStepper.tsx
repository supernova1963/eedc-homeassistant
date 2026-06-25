/**
 * MonatStepper — Monats-Adapter der generischen {@link ZeitStepper}-SoT (mobil).
 * Desktop behält die {@link MonatsRail}; mobil ersetzt der Stepper die Chip-Leiste:
 *   ⏮ ältester · ⏪ −1 Jahr · ◀ −1 Monat · [Monat ▾ → Liste] · ▶ +1 Monat · ⏩ +1 Jahr · ⏭ neuester
 * Hier nur noch die monats-spezifische Navigation/Beschriftung; Hülle, Pille und
 * Dropdown-Liste liefert ZeitStepper.
 */
import { useMemo } from 'react'
import { ChevronFirst, ChevronsLeft, ChevronLeft, ChevronRight, ChevronsRight, ChevronLast } from 'lucide-react'
import { MONAT_KURZ } from '../lib'
import type { RailEintrag } from './MonatsRail'
import { ZeitStepper, type ZeitStepperEintrag } from './ZeitStepper'

interface MonatStepperProps {
  entries: RailEintrag[]
  jahr: number
  monat: number
  onSelect: (jahr: number, monat: number) => void
}

const k = (j: number, m: number) => j * 100 + m

export function MonatStepper({ entries, jahr, monat, onSelect }: MonatStepperProps) {
  const asc = useMemo(
    () => [...entries].sort((a, b) => (a.jahr !== b.jahr ? a.jahr - b.jahr : a.monat - b.monat)),
    [entries],
  )
  const idx = asc.findIndex((e) => e.jahr === jahr && e.monat === monat)
  const find = (j: number, m: number) => asc.find((e) => e.jahr === j && e.monat === m) ?? null
  const oldest = asc[0] ?? null
  const newest = asc[asc.length - 1] ?? null
  const prev = idx > 0 ? asc[idx - 1] : null
  const next = idx >= 0 && idx < asc.length - 1 ? asc[idx + 1] : null
  const prevYear = find(jahr - 1, monat)
  const nextYear = find(jahr + 1, monat)
  const aktuell = idx >= 0 ? asc[idx] : null

  // Ziel-Aktion oder null (am Rand / auf sich selbst deaktiviert).
  const go = (z: RailEintrag | null) =>
    z && k(z.jahr, z.monat) !== k(jahr, monat) ? () => onSelect(z.jahr, z.monat) : null

  const eintraege: ZeitStepperEintrag[] = [...asc].reverse().map((e) => ({
    key: String(k(e.jahr, e.monat)),
    label: `${MONAT_KURZ[e.monat]} ${e.jahr}`,
    wert: e.laufend ? 'läuft' : `${Math.round(e.pv_kwh)} kWh`,
    aktiv: !!e.laufend,
    gewaehlt: e.jahr === jahr && e.monat === monat,
    onClick: () => onSelect(e.jahr, e.monat),
  }))

  return (
    <ZeitStepper
      zurueck={[
        { icon: ChevronFirst, label: 'ältester Monat', go: go(oldest) },
        { icon: ChevronsLeft, label: 'ein Jahr zurück', go: go(prevYear) },
        { icon: ChevronLeft, label: 'voriger Monat', go: go(prev) },
      ]}
      vor={[
        { icon: ChevronRight, label: 'nächster Monat', go: go(next) },
        { icon: ChevronsRight, label: 'ein Jahr vor', go: go(nextYear) },
        { icon: ChevronLast, label: 'neuester Monat', go: go(newest) },
      ]}
      titel={aktuell ? `${MONAT_KURZ[aktuell.monat]} ${aktuell.jahr}` : '—'}
      badge={aktuell?.laufend ? 'läuft' : null}
      eintraege={eintraege}
    />
  )
}
