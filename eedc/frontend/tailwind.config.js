/** @type {import('tailwindcss').Config} */

// Farb-SoT: src/lib/colors.ts (Regel 0/0a, Style-Guide A2).
// Tailwind lädt die Config via jiti — der TS-Import funktioniert zur Build-Zeit
// und macht Drift zwischen Theme und Zentrale baulich unmöglich.
import { COLORS, STATUS_COLORS } from './src/lib/colors'

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Eigene Farben für EEDC
        primary: {
          50: '#f0fdf4',
          100: '#dcfce7',
          200: '#bbf7d0',
          300: '#86efac',
          400: '#4ade80',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
          800: '#166534',
          900: '#14532d',
          950: '#052e16',
        },
        energy: {
          solar: COLORS.solar,          // Gelb für PV (F1 kanonisiert)
          grid: COLORS.grid,            // Dunkelrot für Netzbezug (F2)
          battery: COLORS.battery,      // Blau für Batterie
          consumption: COLORS.consumption, // Violett für Verbrauch
          export: COLORS.feedin,        // Grün für Einspeisung
        },
        // Status-Achse (F3): text-status-ok, bg-status-warnung, …
        status: STATUS_COLORS,
      },
    },
  },
  plugins: [],
}
