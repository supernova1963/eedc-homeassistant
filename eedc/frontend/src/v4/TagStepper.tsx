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
import { DatumPicker } from '../components/ui/DatumPicker'
import { fmtZahl, WT_KURZ, verschiebeIsoTage } from '../lib'

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

// Über den SoT (F-5). Die frühere Fassung war zufällig richtig — sie legte den
// Zwischenwert auf die lokale Mittagszeit, dort fällt das UTC-Datum mit dem
// lokalen zusammen. Zufällig richtig ist kein Grund, es stehen zu lassen.
const verschieben = (iso: string, n: number) => verschiebeIsoTage(iso, n)
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
        // Datumsauswahl erreicht ALLE verfügbaren Tage (min = ältester Tag). D13-4/12:
        // Custom-DatumPicker (SoT), Portal-Popover → nicht mehr vom overflow-hidden-
        // Dropdown abgeschnitten (löst auch D12-9-Fokus-Ring-Clip).
        <DatumPicker
          modus="tag" ariaLabel="Datum wählen" value={datum} max={newest} min={untergrenze}
          onChange={(v) => { onSelect(clamp(v)); close() }} className="w-full text-sm"
        />
      )}
      zuruecksetzen={
        // Zurücksetzen → neuester Tag (Ausgangs-Ansicht), wenn man in die
        // Historie gesprungen ist (Gernot 2026-06-26); Render = ZeitStepper-Unterbau (B15/S2).
        datum !== newest
          ? { label: '↺ Zurücksetzen (neuester Tag)', onClick: () => onSelect(newest) }
          : null
      }
      immerSichtbar={immerSichtbar}
    />
  )
}
