/**
 * ResponsiveContainer-Wrapper mit konsistenter Größen-Semantik.
 *
 * Kapselt das Pattern: <div className="h-XX"><ResponsiveContainer width="100%" height="100%">
 */

import { ResponsiveContainer } from 'recharts'

interface ChartContainerProps {
  /** Höhe als Tailwind-Klasse (z.B. "h-80") oder Pixel-Zahl. */
  height?: string | number
  /** Zusätzliche CSS-Klassen für den Wrapper. */
  className?: string
  children: React.ReactNode
}

export default function ChartContainer({ height = 'h-80', className = '', children }: ChartContainerProps) {
  const isPixels = typeof height === 'number'

  return (
    <div
      className={isPixels ? className : `${height} ${className}`}
      style={isPixels ? { height: `${height}px` } : undefined}
    >
      <ResponsiveContainer width="100%" height="100%">
        {children as React.ReactElement}
      </ResponsiveContainer>
    </div>
  )
}
