import { useEffect, useState } from 'react'
import { Sunrise, Sunset } from 'lucide-react'

interface SunProgressBarProps {
  sunrise: string   // "06:12"
  sunset: string    // "19:47"
  solar_noon?: string // "12:54"
  sonnenstunden?: number | null       // Tagessumme (Ist + Prognose)
  sonnenstundenBisher?: number | null // Ist-Sonnenstunden bis jetzt
  sonnenstundenRest?: number | null   // Prognostizierte Sonnenstunden ab jetzt
}

function timeToSeconds(t: string): number {
  const [h, m] = t.split(':').map(Number)
  return h * 3600 + m * 60
}

function secondsToHMS(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m.toString().padStart(2, '0')}m ${s.toString().padStart(2, '0')}s`
  if (m > 0) return `${m}m ${s.toString().padStart(2, '0')}s`
  return `${s}s`
}

// Rückwärtskompatibilität für sonnenstunden-Formatierung
function fmtH(h: number): string {
  const hh = Math.floor(h)
  const mm = Math.round((h - hh) * 60).toString().padStart(2, '0')
  return hh > 0 ? `${hh}h ${mm}m` : `${mm}m`
}

export default function SunProgressBar({ sunrise, sunset, solar_noon, sonnenstunden, sonnenstundenBisher, sonnenstundenRest }: SunProgressBarProps) {
  const [now, setNow] = useState(() => {
    const d = new Date()
    return d.getHours() * 3600 + d.getMinutes() * 60 + d.getSeconds()
  })

  useEffect(() => {
    const timer = setInterval(() => {
      const d = new Date()
      setNow(d.getHours() * 3600 + d.getMinutes() * 60 + d.getSeconds())
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  const sunriseS = timeToSeconds(sunrise)
  const sunsetS = timeToSeconds(sunset)
  const totalS = sunsetS - sunriseS
  if (totalS <= 0) return null

  const pct = Math.min(100, Math.max(0, ((now - sunriseS) / totalS) * 100))
  const noonPct = solar_noon
    ? Math.min(100, Math.max(0, ((timeToSeconds(solar_noon) - sunriseS) / totalS) * 100))
    : 50

  const beforeSunrise = now < sunriseS
  const afterSunset = now >= sunsetS
  const remainingS = sunsetS - now

  return (
    <div className="py-1">
      {/* Sonnenstunden über der ProgressBar */}
      {sonnenstunden != null && !beforeSunrise && (
        <div className="flex items-center justify-between mb-1 text-[10px]">
          <span className="text-yellow-600 dark:text-yellow-400 font-medium" title="Sonnenstunden bis jetzt (Ist-Werte)">
            ☀ {sonnenstundenBisher != null ? fmtH(sonnenstundenBisher) : '—'} bisher
          </span>
          {!afterSunset && sonnenstundenRest != null && sonnenstundenRest > 0 && (
            <span className="text-amber-500 dark:text-amber-400 font-medium" title="Prognostizierte Sonnenstunden bis Sonnenuntergang">
              ~{fmtH(sonnenstundenRest)} erwartet
            </span>
          )}
          {afterSunset && (
            <span className="text-gray-400 dark:text-gray-500">
              {fmtH(sonnenstunden)} gesamt
            </span>
          )}
        </div>
      )}

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
          {beforeSunrise && `Sonnenaufgang in ${secondsToHMS(sunriseS - now)}`}
          {!beforeSunrise && !afterSunset && (
            <span className="text-amber-500 dark:text-amber-400">
              noch {secondsToHMS(remainingS)} Tageslicht
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
