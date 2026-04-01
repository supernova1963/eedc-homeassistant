import { useEffect, useState } from 'react'
import { Sunrise, Sunset } from 'lucide-react'

interface SunProgressBarProps {
  sunrise: string   // "06:12"
  sunset: string    // "19:47"
  solar_noon?: string // "12:54"
}

function timeToMinutes(t: string): number {
  const [h, m] = t.split(':').map(Number)
  return h * 60 + m
}

function minutesToHM(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = Math.floor(minutes % 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

export default function SunProgressBar({ sunrise, sunset, solar_noon }: SunProgressBarProps) {
  const [now, setNow] = useState(() => {
    const d = new Date()
    return d.getHours() * 60 + d.getMinutes()
  })

  useEffect(() => {
    const timer = setInterval(() => {
      const d = new Date()
      setNow(d.getHours() * 60 + d.getMinutes())
    }, 30000)
    return () => clearInterval(timer)
  }, [])

  const sunriseMin = timeToMinutes(sunrise)
  const sunsetMin = timeToMinutes(sunset)
  const totalMin = sunsetMin - sunriseMin
  if (totalMin <= 0) return null

  const pct = Math.min(100, Math.max(0, ((now - sunriseMin) / totalMin) * 100))
  const noonPct = solar_noon
    ? Math.min(100, Math.max(0, ((timeToMinutes(solar_noon) - sunriseMin) / totalMin) * 100))
    : 50

  const beforeSunrise = now < sunriseMin
  const afterSunset = now >= sunsetMin
  const remainingMin = sunsetMin - now

  return (
    <div className="py-1">
      {/* Balken */}
      <div className="relative h-3 rounded-full overflow-visible bg-gray-200 dark:bg-gray-700">
        {/* Gradient-Fortschritt */}
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${pct}%`,
            background: 'linear-gradient(to right, #fbbf24, #f59e0b, #f97316)',
          }}
        />
        {/* Solar-Noon-Markierung */}
        <div
          className="absolute top-0 bottom-0 w-px bg-orange-400 opacity-60"
          style={{ left: `${noonPct}%` }}
          title={solar_noon ? `Solar Noon ${solar_noon}` : 'Solar Noon'}
        />
        {/* Aktuelle-Zeit-Marker */}
        {!beforeSunrise && !afterSunset && (
          <div
            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full bg-yellow-400 border-2 border-white dark:border-gray-800 shadow-sm z-10"
            style={{ left: `${pct}%` }}
          />
        )}
      </div>

      {/* Beschriftung */}
      <div className="flex items-center justify-between mt-1 text-[10px] text-gray-400 dark:text-gray-500">
        <span className="flex items-center gap-0.5">
          <Sunrise className="w-3 h-3 text-amber-400" />
          {sunrise}
        </span>
        <span className="text-center font-medium">
          {beforeSunrise && `Sonnenaufgang in ${minutesToHM(sunriseMin - now)}`}
          {!beforeSunrise && !afterSunset && (
            <span className="text-amber-500 dark:text-amber-400">
              noch {minutesToHM(remainingMin)} Sonnenschein
            </span>
          )}
          {afterSunset && 'Sonne untergegangen'}
        </span>
        <span className="flex items-center gap-0.5">
          {sunset}
          <Sunset className="w-3 h-3 text-orange-400" />
        </span>
      </div>
    </div>
  )
}
