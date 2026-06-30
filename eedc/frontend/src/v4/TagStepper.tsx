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
import { fmtZahl } from '../lib'

interface TagStepperProps {
  entries: TagRailEintrag[]
  datum: string
  onSelect: (datum: string) => void
  /** Ältester verfügbarer Tag (jenseits der 90-Tage-Liste) — Untergrenze für die
   *  Datumsauswahl, damit ALLE vorhandenen Tage direkt anspringbar sind. */
  aeltesterTag?: string
  /** D10-2: im Fokus/Vollbild-Kopf auf jeder Breite sichtbar (durchgereicht). */
  immerSichtbar?: boolean
}

const WT_KURZ = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']
const verschieben = (iso: string, n: number) => {
  const d = new Date(iso + 'T12:00:00'); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10)
}
const label = (iso: string) => {
  const d = new Date(iso + 'T12:00:00')
  return `${WT_KURZ[d.getDay()]} ${d.getDate()}. ${d.toLocaleDateString('de-DE', { month: 'short', year: 'numeric' })}`
}

export function TagStepper({ entries, datum, onSelect, aeltesterTag, immerSichtbar }: TagStepperProps) {
  const desc = useMemo(() => [...entries].sort((a, b) => (a.datum < b.datum ? 1 : -1)), [entries])
  // Aufsteigende, deduplizierte Liste der navigierbaren Tage = Tage MIT Daten ∪ heute
  // (CockpitTagV4 hängt heute immer an `entries` an). Die Stepper-Pfeile springen NUR
  // zu diesen Tagen → kein Landen auf echten Lücken-Tagen (detLAN-Vollbild-Bug
  // 2026-06-30); heute bleibt als rechter Anschlag immer erreichbar.
  const ascDaten = useMemo(() => [...new Set(entries.map((e) => e.datum))].sort(), [entries])
  const oldest = ascDaten[0] ?? datum
  const newest = ascDaten[ascDaten.length - 1] ?? datum
  // Untergrenze NUR für die Datumsauswahl (Picker erreicht ALLE Tage, auch vor der
  // 90-Tage-Liste, R5-F2); die Pfeile bleiben auf den Daten-Tagen.
  const untergrenze = aeltesterTag && aeltesterTag < oldest ? aeltesterTag : oldest
  const clamp = (iso: string) => (iso < untergrenze ? untergrenze : iso > newest ? newest : iso)

  // Nachbar-Tage MIT Daten (überspringt Lücken). ±7 = Kalender-Ziel, auf den
  // nächstgelegenen Daten-Tag in Blätter-Richtung gefangen.
  const vorigerMit = (iso: string) => ascDaten.reduce<string | null>((r, d) => (d < iso ? d : r), null)
  const naechsterMit = (iso: string) => ascDaten.find((d) => d > iso) ?? null
  const sprungZurueck = (iso: string) => {
    const ziel = verschieben(iso, -7)
    return ascDaten.reduce<string | null>((r, d) => (d <= ziel ? d : r), null) ?? (oldest < iso ? oldest : null)
  }
  const sprungVor = (iso: string) => {
    const ziel = verschieben(iso, 7)
    return ascDaten.find((d) => d >= ziel) ?? (newest > iso ? newest : null)
  }
  // Ziel-Aktion oder null (am Rand / kein Daten-Tag in der Richtung).
  const go = (iso: string | null) => (iso != null && iso !== datum ? () => onSelect(iso) : null)
  const aktuell = entries.find((e) => e.datum === datum) ?? null

  const eintraege: ZeitStepperEintrag[] = desc.map((e) => ({
    key: e.datum,
    label: label(e.datum),
    wert: e.heute ? 'heute' : `${fmtZahl(e.pv_kwh, 0)} kWh`,
    aktiv: !!e.heute,
    gewaehlt: e.datum === datum,
    onClick: () => onSelect(e.datum),
  }))

  return (
    <ZeitStepper
      zurueck={[
        { icon: ChevronFirst, label: 'ältester Tag mit Daten', go: go(oldest) },
        { icon: ChevronsLeft, label: '~7 Tage zurück', go: go(sprungZurueck(datum)) },
        { icon: ChevronLeft, label: 'voriger Tag mit Daten', go: go(vorigerMit(datum)) },
      ]}
      vor={[
        { icon: ChevronRight, label: 'nächster Tag mit Daten', go: go(naechsterMit(datum)) },
        { icon: ChevronsRight, label: '~7 Tage vor', go: go(sprungVor(datum)) },
        { icon: ChevronLast, label: 'neuester Tag', go: go(newest) },
      ]}
      titel={label(datum)}
      badge={aktuell?.heute ? 'heute' : null}
      eintraege={eintraege}
      direktsprung={(close) => (
        <div className="space-y-2">
          {/* Datumsauswahl erreicht ALLE verfügbaren Tage (min = ältester Tag). */}
          <input
            type="date" aria-label="Datum wählen" value={datum} max={newest} min={untergrenze}
            onChange={(e) => { if (e.target.value) { onSelect(clamp(e.target.value)); close() } }}
            /* D12-9: ring-inset — Fokus-Ring würde sonst vom overflow-hidden-Dropdown abgeschnitten. */
            className="input w-full text-sm ring-inset"
          />
          {/* Zurücksetzen → neuester Tag (Ausgangs-Ansicht), wenn man in die
              Historie gesprungen ist (Gernot 2026-06-26). */}
          {datum !== newest && (
            <button
              type="button"
              onClick={() => { onSelect(newest); close() }}
              className="w-full text-xs px-2 py-1 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
            >
              ↺ Zurücksetzen (neuester Tag)
            </button>
          )}
        </div>
      )}
      immerSichtbar={immerSichtbar}
    />
  )
}
