import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { CHART_ACHSEN } from '../lib/colors'

type Theme = 'light' | 'dark' | 'system'

interface ThemeContextType {
  theme: Theme
  setTheme: (theme: Theme) => void
  isDark: boolean
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    // Aus localStorage laden oder 'system' als Default
    const saved = localStorage.getItem('eedc-theme')
    return (saved as Theme) || 'system'
  })

  const [isDark, setIsDark] = useState(false)

  useEffect(() => {
    // Theme in localStorage speichern
    localStorage.setItem('eedc-theme', theme)

    // Dark Mode bestimmen
    const root = window.document.documentElement

    if (theme === 'system') {
      const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      setIsDark(systemDark)
      root.classList.toggle('dark', systemDark)
    } else {
      setIsDark(theme === 'dark')
      root.classList.toggle('dark', theme === 'dark')
    }
  }, [theme])

  // System-Theme Änderungen beobachten
  useEffect(() => {
    if (theme !== 'system') return

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => {
      setIsDark(e.matches)
      document.documentElement.classList.toggle('dark', e.matches)
    }

    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, setTheme, isDark }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}

/**
 * Dark-aware Chart-Infrastruktur-Farben (Achse/Grid/Referenz) — der EINE Weg,
 * Recharts-Inline-Styles theme-abhängig zu färben (Regel Nr. 0).
 *
 * Hintergrund (Style-Guide A2, P2): Recharts-TEXT (Tick-Werte, Legende,
 * Pie-Labels) wird zentral über die `html.dark .recharts-*`-Overrides in
 * `index.css` dark-aware. Recharts-STROKES/FILLS (CartesianGrid, ReferenceLine,
 * PolarGrid, neutrale Balken …) lassen sich nur per Inline-Style setzen — dafür
 * dieser Hook. So gibt es genau zwei klar getrennte Mechanismen (Text=CSS,
 * Stroke=Hook), nicht pro Komponente hartkodierte `CHART_ACHSEN.light.*`.
 */
export function useChartTheme() {
  const { isDark } = useTheme()
  return isDark ? CHART_ACHSEN.dark : CHART_ACHSEN.light
}
