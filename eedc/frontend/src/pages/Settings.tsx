import { Moon, Sun, Monitor, Home, Database } from 'lucide-react'
import { useTheme } from '../context/ThemeContext'

export default function Settings() {
  const { theme, setTheme } = useTheme()

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        Einstellungen
      </h1>

      {/* Appearance */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Erscheinungsbild
        </h2>

        <div className="space-y-4">
          <label className="label">Theme</label>
          <div className="flex gap-3">
            {[
              { value: 'light', label: 'Hell', icon: Sun },
              { value: 'dark', label: 'Dunkel', icon: Moon },
              { value: 'system', label: 'System', icon: Monitor },
            ].map((option) => (
              <button
                key={option.value}
                onClick={() => setTheme(option.value as 'light' | 'dark' | 'system')}
                className={`flex-1 flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-colors ${
                  theme === option.value
                    ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                    : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                }`}
              >
                <option.icon className="h-5 w-5" />
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Home Assistant Integration */}
      <div className="card p-6">
        <div className="flex items-center gap-3 mb-4">
          <Home className="h-6 w-6 text-cyan-500" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Home Assistant Integration
          </h2>
        </div>

        <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg mb-4">
          <div className="flex items-center gap-2 text-sm">
            <span className="w-2 h-2 rounded-full bg-gray-400"></span>
            <span className="text-gray-600 dark:text-gray-300">
              Status: Nicht verbunden
            </span>
          </div>
        </div>

        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
          Sensor-Zuordnung
        </h3>
        <div className="space-y-3">
          {['PV-Erzeugung', 'Einspeisung', 'Netzbezug', 'Batterie Ladung', 'Batterie Entladung'].map((label) => (
            <div key={label}>
              <label className="label">{label}</label>
              <select className="input">
                <option value="">-- Sensor auswählen --</option>
              </select>
            </div>
          ))}
        </div>
      </div>

      {/* Database */}
      <div className="card p-6">
        <div className="flex items-center gap-3 mb-4">
          <Database className="h-6 w-6 text-gray-500" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Datenbank
          </h2>
        </div>

        <div className="text-sm text-gray-500 dark:text-gray-400 space-y-1">
          <p>Pfad: /data/eedc.db</p>
          <p>Anlagen: 0</p>
          <p>Monatsdaten: 0</p>
          <p>Investitionen: 0</p>
        </div>

        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <button className="btn btn-secondary text-sm">
            Daten exportieren
          </button>
        </div>
      </div>
    </div>
  )
}
