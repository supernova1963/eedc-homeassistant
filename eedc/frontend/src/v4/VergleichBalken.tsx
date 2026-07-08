/**
 * VergleichBalken — Renderer für den „Vergleich"-Modus (R17-1/R17-2b).
 *
 * Gruppierte (ungestackte) Balken + optionale km-Rechtsachse für ein Preset.
 * Als Fragment direkt in den `<ComposedChart>` der Verlauf-Charts einsetzbar
 * (Recharts flacht Fragmente auf). Presets/Filter aus `./verlaufVergleich`.
 * `onBarClick` = Drill-in (B3, Balken-Klick → Tag/Monat).
 */
import { Bar, YAxis } from 'recharts'
import { yAchse, achsenEinheit, achsenTick } from '../lib'
import { sichtbareSerien, type VergleichPreset } from './verlaufVergleich'

export function VergleichBalken({
  preset,
  istJahr,
  schmal,
  onBarClick,
}: {
  preset: VergleichPreset
  istJahr: boolean
  schmal: boolean
  onBarClick?: (index: number) => void
}) {
  const serien = sichtbareSerien(preset, istJahr)
  const hatKm = serien.some((s) => s.achse === 'km')
  return (
    <>
      {hatKm && (
        <YAxis
          yAxisId="km"
          orientation="right"
          {...yAchse(schmal, 44)}
          tickFormatter={achsenTick}
          label={achsenEinheit('km', 'rechts')}
        />
      )}
      {serien.map((s) => (
        <Bar
          key={s.key}
          yAxisId={s.achse === 'km' ? 'km' : 'kwh'}
          dataKey={s.key}
          name={s.name}
          fill={s.color}
          onClick={onBarClick ? (_d, index) => onBarClick(index) : undefined}
          cursor={onBarClick ? 'pointer' : undefined}
        />
      ))}
    </>
  )
}
