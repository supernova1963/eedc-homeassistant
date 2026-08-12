/**
 * Slider — DER Schieberegler-SoT (Style-Guide Regel 0a, angelegt 2026-08-12).
 *
 * Bis zum Sizing-Simulator (#358 Phase 3) gab es in der ganzen Oberfläche keinen
 * einzigen Schieberegler. Regel 0a Stufe 2 gilt damit wörtlich: „keine Regel
 * vorhanden, aber sinnvoll → Regel definieren **und die Zentrale erweitern, in
 * derselben Arbeit"** — nicht ein roher `<input type="range">` in der neuen
 * Sicht, dem beim zweiten Aufrufer ein zweiter mit anderer Optik folgt.
 *
 * Die Optik ist von {@link Switch} geerbt: Bahn in `gray-300`/`gray-600`,
 * bedienbarer Teil in `primary-600` (über `accent-primary-600`, das Browser-
 * seitig Knauf **und** gefüllte Bahn einfärbt). Keine rohen Farbwerte — der
 * Wert selbst steht in `lib/colors.ts` bzw. der Tailwind-Palette.
 *
 * Der **Wert wird bewusst nicht mitgerendert**: wie er heißt und in welcher
 * Einheit er steht, weiß nur der Aufrufer (Prozent, kWh, beides). Er beschriftet
 * ihn daneben; der Regler bleibt das Bedienelement.
 */
export function Slider({
  min, max, step = 1, value, onChange, ariaLabel, disabled, id,
}: {
  min: number
  max: number
  step?: number
  value: number
  onChange: (wert: number) => void
  /** Pflicht: der Regler trägt seine Beschriftung nicht selbst. */
  ariaLabel: string
  disabled?: boolean
  id?: string
}) {
  return (
    <input
      id={id}
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      disabled={disabled}
      aria-label={ariaLabel}
      onChange={(e) => onChange(Number(e.target.value))}
      className="h-2 w-full cursor-pointer appearance-none rounded-full bg-gray-300 accent-primary-600 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-gray-600"
    />
  )
}

export default Slider
