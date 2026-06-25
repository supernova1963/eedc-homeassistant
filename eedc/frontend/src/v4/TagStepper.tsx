/**
 * TagStepper — Tages-Adapter der generischen {@link ZeitStepper}-SoT (mobil).
 * Desktop behält die {@link TagesRail}; mobil:
 *   ⏮ ältester · ⏪ −7 Tage · ◀ −1 Tag · [Datum ▾ → Liste + Date-Picker] · ▶ +1 Tag · ⏩ +7 Tage · ⏭ neuester
 * Tag-Spezifika: ISO-Datums-Navigation + ein Date-Picker als Direktsprung (Tage
 * sind viele — anders als Monate/Jahre).
 */
import { useMemo } from 'react'
import { ChevronFirst, ChevronsLeft, ChevronLeft, ChevronRight, ChevronsRight, ChevronLast } from 'lucide-react'
import type { TagRailEintrag } from './TagesRail'
import { ZeitStepper, type ZeitStepperEintrag } from './ZeitStepper'

interface TagStepperProps {
  entries: TagRailEintrag[]
  datum: string
  onSelect: (datum: string) => void
}

const WT_KURZ = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']
const verschieben = (iso: string, n: number) => {
  const d = new Date(iso + 'T12:00:00'); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10)
}
const label = (iso: string) => {
  const d = new Date(iso + 'T12:00:00')
  return `${WT_KURZ[d.getDay()]} ${d.getDate()}. ${d.toLocaleDateString('de-DE', { month: 'short', year: 'numeric' })}`
}

export function TagStepper({ entries, datum, onSelect }: TagStepperProps) {
  const desc = useMemo(() => [...entries].sort((a, b) => (a.datum < b.datum ? 1 : -1)), [entries])
  const oldest = useMemo(() => entries.reduce((m, e) => (m && m < e.datum ? m : e.datum), entries[0]?.datum ?? datum), [entries, datum])
  const newest = useMemo(() => entries.reduce((m, e) => (m && m > e.datum ? m : e.datum), entries[0]?.datum ?? datum), [entries, datum])

  const clamp = (iso: string) => (iso < oldest ? oldest : iso > newest ? newest : iso)
  // Ziel-Aktion oder null (am Rand / auf sich selbst deaktiviert).
  const go = (iso: string) => {
    const c = clamp(iso)
    return c === datum ? null : () => onSelect(c)
  }
  const aktuell = entries.find((e) => e.datum === datum) ?? null

  const eintraege: ZeitStepperEintrag[] = desc.map((e) => ({
    key: e.datum,
    label: label(e.datum),
    wert: e.heute ? 'heute' : `${Math.round(e.pv_kwh)} kWh`,
    aktiv: !!e.heute,
    gewaehlt: e.datum === datum,
    onClick: () => onSelect(e.datum),
  }))

  return (
    <ZeitStepper
      zurueck={[
        { icon: ChevronFirst, label: 'ältester Tag', go: go(oldest) },
        { icon: ChevronsLeft, label: '7 Tage zurück', go: go(verschieben(datum, -7)) },
        { icon: ChevronLeft, label: 'voriger Tag', go: go(verschieben(datum, -1)) },
      ]}
      vor={[
        { icon: ChevronRight, label: 'nächster Tag', go: go(verschieben(datum, 1)) },
        { icon: ChevronsRight, label: '7 Tage vor', go: go(verschieben(datum, 7)) },
        { icon: ChevronLast, label: 'neuester Tag', go: go(newest) },
      ]}
      titel={label(datum)}
      badge={aktuell?.heute ? 'heute' : null}
      eintraege={eintraege}
      direktsprung={(close) => (
        <input
          type="date" aria-label="Datum wählen" value={datum} max={newest} min={oldest}
          onChange={(e) => { if (e.target.value) { onSelect(clamp(e.target.value)); close() } }}
          className="input w-full text-sm"
        />
      )}
    />
  )
}
