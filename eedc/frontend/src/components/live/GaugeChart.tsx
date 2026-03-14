/**
 * GaugeChart — SVG-Halbkreis-Gauge für SoC, Netz, Autarkie.
 */

interface GaugeChartProps {
  wert: number
  min: number
  max: number
  label: string
  einheit: string
}

// Farbe basierend auf Key und Wert
function getGaugeColor(key: string, wert: number, min: number, max: number): string {
  if (key === 'netz') {
    // Netz: grün bei Einspeisung (negativ), rot bei Bezug (positiv)
    return wert <= 0 ? '#22c55e' : '#ef4444'
  }
  // SoC / Autarkie: rot < 20%, gelb 20-50%, grün > 50%
  const prozent = max > min ? ((wert - min) / (max - min)) * 100 : 0
  if (prozent < 20) return '#ef4444'
  if (prozent < 50) return '#eab308'
  return '#22c55e'
}

export default function GaugeChart({ wert, min, max, label, einheit }: GaugeChartProps) {
  // Feste ViewBox-Größen — SVG skaliert per width="100%"
  const cx = 80
  const cy = 72
  const r = 60
  const strokeW = 10
  const svgW = 160
  const svgH = 92
  const valueFontSize = 22
  const unitFontSize = 13

  const startAngle = Math.PI
  const endAngle = 0

  // Wert normalisieren
  const range = max - min || 1
  const clampedWert = Math.max(min, Math.min(max, wert))
  const ratio = (clampedWert - min) / range

  // SVG Arc Path
  const arcPath = (startA: number, endA: number) => {
    const x1 = cx + r * Math.cos(startA)
    const y1 = cy - r * Math.sin(startA)
    const x2 = cx + r * Math.cos(endA)
    const y2 = cy - r * Math.sin(endA)
    const sweep = startA > endA ? 1 : 0
    return `M ${x1} ${y1} A ${r} ${r} 0 0 ${sweep} ${x2} ${y2}`
  }

  // Wert-Bogen berechnen
  const wertEndAngle = startAngle - ratio * Math.PI
  const color = getGaugeColor(label.toLowerCase(), wert, min, max)

  // Formatierung
  const displayWert = Math.abs(wert) >= 1000
    ? `${(wert / 1000).toFixed(1)}k`
    : Number.isInteger(wert) ? wert.toString() : wert.toFixed(1)

  return (
    <div className="flex flex-col items-center">
      <svg width="100%" viewBox={`0 0 ${svgW} ${svgH}`}>
        {/* Hintergrund-Bogen */}
        <path
          d={arcPath(startAngle, endAngle)}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeW}
          strokeLinecap="round"
          className="text-gray-200 dark:text-gray-700"
        />
        {/* Wert-Bogen */}
        {ratio > 0.01 && (
          <path
            d={arcPath(startAngle, wertEndAngle)}
            fill="none"
            stroke={color}
            strokeWidth={strokeW}
            strokeLinecap="round"
          />
        )}
        {/* Wert-Text */}
        <text
          x={cx}
          y={cy - 8}
          textAnchor="middle"
          className="fill-gray-900 dark:fill-gray-100"
          fontSize={valueFontSize}
          fontWeight="bold"
        >
          {displayWert}
        </text>
        <text
          x={cx}
          y={cy + 12}
          textAnchor="middle"
          className="fill-gray-500 dark:fill-gray-400"
          fontSize={unitFontSize}
        >
          {einheit}
        </text>
      </svg>
      <span className="text-gray-600 dark:text-gray-400 -mt-1 text-sm font-medium">
        {label}
      </span>
    </div>
  )
}
