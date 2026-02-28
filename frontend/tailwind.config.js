/** @type {import('tailwindcss').Config} */
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
          solar: '#fbbf24',    // Gelb für PV
          grid: '#ef4444',     // Rot für Netzbezug
          battery: '#3b82f6',  // Blau für Batterie
          consumption: '#8b5cf6', // Violett für Verbrauch
          export: '#10b981',   // Grün für Einspeisung
        }
      },
    },
  },
  plugins: [],
}
