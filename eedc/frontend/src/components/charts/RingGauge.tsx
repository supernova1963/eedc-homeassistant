/**
 * SVG Ring-Gauge für Prozentwerte (Autarkie, Eigenverbrauch, SoC, etc.).
 *
 * Extrahiert aus Dashboard.tsx. Verwendet strokeDasharray für den Füllgrad.
 */

interface RingGaugeProps {
  /** Wert in Prozent (0–100). */
  value: number
  /** Farbe des gefüllten Bogens (Hex). */
  color: string
  /** Größe in Pixel (Default: 64). */
  size?: number
  /** Strichstärke (Default: 8). */
  strokeWidth?: number
  /** Beschriftung im Zentrum (Default: gerundeter Wert). */
  label?: string
}

export default function RingGauge({
  value, color, size = 64, strokeWidth = 8, label,
}: RingGaugeProps) {
  const viewBox = 80
  const cx = viewBox / 2
  const cy = viewBox / 2
  const r = (viewBox - strokeWidth) / 2 - 4
  const circ = 2 * Math.PI * r
  const clamped = Math.min(100, Math.max(0, value))
  const filled = (clamped / 100) * circ

  return (
    <svg
      viewBox={`0 0 ${viewBox} ${viewBox}`}
      width={size}
      height={size}
      className="flex-shrink-0"
    >
      {/* Hintergrund-Ring */}
      <circle
        cx={cx} cy={cy} r={r}
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        className="text-gray-200 dark:text-gray-700"
      />
      {/* Gefüllter Bogen */}
      <circle
        cx={cx} cy={cy} r={r}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeDasharray={`${filled} ${circ}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${cx} ${cy})`}
      />
      {/* Zentral-Text */}
      <text
        x={cx} y={cy + 5}
        textAnchor="middle"
        fontSize="15"
        fontWeight="bold"
        fill={color}
      >
        {label ?? clamped.toFixed(0)}
      </text>
    </svg>
  )
}
