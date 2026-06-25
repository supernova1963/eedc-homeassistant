import { CHART_HOVER_CURSOR } from '../../lib'
import ChartTooltip, { type ChartTooltipProps } from './ChartTooltip'

/**
 * Standard-Props für ein Recharts-`<Tooltip>` (Regel D, 2026-06-25) — EINE Stelle
 * setzt Hover-Cursor ({@link CHART_HOVER_CURSOR}) **und** den {@link ChartTooltip}-
 * Content, damit der Cursor nicht pro Chart vergessen werden kann. `<Tooltip>`
 * bleibt direktes Chart-Kind (Recharts erkennt Wrapper-Komponenten nicht):
 *
 *   <Tooltip {...eedcTooltipProps({ unit: ' kW', decimals: 2 })} />
 *
 * Für reine Linien-/Flächen-Charts ohne Bar-Cursor `cursor: false` übergeben.
 * (Eigenes Modul statt Export aus `ChartTooltip.tsx` — react-refresh: Komponenten-
 * Dateien exportieren nur Komponenten.)
 */
export function eedcTooltipProps(
  opts: Omit<ChartTooltipProps, 'active' | 'payload' | 'label'> & { cursor?: boolean } = {},
) {
  const { cursor = true, ...rest } = opts
  return {
    cursor: cursor ? CHART_HOVER_CURSOR : false,
    content: <ChartTooltip {...rest} />,
  } as const
}
