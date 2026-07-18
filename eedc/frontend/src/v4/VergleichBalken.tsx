/**
 * vergleichBalken — Render-Helfer für den „Vergleich"-Modus (R17-1/R17-2b).
 *
 * Gruppierte (ungestackte) Balken + optionale km-Rechtsachse für ein Preset.
 * ⚠️ BEWUSST eine FUNKTION (kein `<Component/>`): Recharts erkennt Chart-Elemente
 * (Bar/YAxis) nur als DIREKTE Kinder bzw. in Fragmenten/Arrays, die es aufflacht —
 * eine Custom-Komponente `<VergleichBalken/>` würde es als unbekannten Kind-Typ
 * ignorieren (Bars unsichtbar). Darum inline als `{vergleichBalken({…})}` aufrufen,
 * damit das zurückgegebene Fragment DIREKTES Kind des `<ComposedChart>` wird —
 * genau wie die gestackten Erzeugung/Verbrauch-Fragmente. Presets/Filter aus
 * `./verlaufVergleich`. `onBarClick` = Drill-in (B3, Balken-Klick → Tag/Monat).
 */
import { Bar, YAxis } from 'recharts'
import { yAchse, achsenEinheit, achsenTick } from '../lib'
import { sichtbareSerien, type VergleichPreset } from './verlaufVergleich'

export function vergleichBalken({
  preset,
  istJahr,
  schmal,
  onBarClick,
  hidden,
}: {
  preset: VergleichPreset
  istJahr: boolean
  schmal: boolean
  onBarClick?: (index: number) => void
  /** Per Legende ausgeblendete Serien-Keys (Skalen-Lesbarkeit: große Serie ausblenden). */
  hidden?: ReadonlySet<string>
}) {
  const serien = sichtbareSerien(preset, istJahr)
  const hatKm = serien.some((s) => s.achse === 'km' && !hidden?.has(s.key))
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
          // `hide` (nicht Daten filtern) → Recharts dimmt den Legenden-Eintrag und
          // reskaliert die Y-Achse auf die sichtbaren Serien; Re-Klick bringt sie zurück.
          hide={hidden?.has(s.key)}
          onClick={onBarClick ? (_d, index) => onBarClick(index) : undefined}
          cursor={onBarClick ? 'pointer' : undefined}
        />
      ))}
    </>
  )
}
