import { useState, useEffect } from 'react'
import { Moon, Sun, Monitor, Home, Database, RefreshCw, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import { useTheme } from '../context/ThemeContext'
import { systemApi, type StatsResponse, type SettingsResponse } from '../api'

export default function Settings() {
  const { theme, setTheme } = useTheme()
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [settings, setSettings] = useState<SettingsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadData = async () => {
    try {
      setLoading(true)
      setError(null)
      const [statsData, settingsData] = await Promise.all([
        systemApi.getStats(),
        systemApi.getSettings(),
      ])
      setStats(statsData)
      setSettings(settingsData)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden der Einstellungen')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Einstellungen
        </h1>
        <button
          onClick={loadData}
          disabled={loading}
          className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          title="Aktualisieren"
        >
          <RefreshCw className={`h-5 w-5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <p className="text-red-700 dark:text-red-300 text-sm">{error}</p>
        </div>
      )}

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
            {settings?.ha_integration_enabled ? (
              <>
                <CheckCircle className="w-4 h-4 text-green-500" />
                <span className="text-green-600 dark:text-green-400">
                  Verbunden
                </span>
              </>
            ) : (
              <>
                <XCircle className="w-4 h-4 text-gray-400" />
                <span className="text-gray-600 dark:text-gray-300">
                  Nicht verbunden
                </span>
              </>
            )}
          </div>
        </div>

        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
          Sensor-Zuordnung
        </h3>
        <div className="space-y-3">
          {[
            { key: 'pv_erzeugung', label: 'PV-Erzeugung' },
            { key: 'einspeisung', label: 'Einspeisung' },
            { key: 'netzbezug', label: 'Netzbezug' },
          ].map(({ key, label }) => (
            <div key={key} className="flex items-center justify-between">
              <span className="text-sm text-gray-700 dark:text-gray-300">{label}</span>
              {settings?.ha_sensors_configured[key as keyof typeof settings.ha_sensors_configured] ? (
                <span className="flex items-center gap-1 text-sm text-green-600 dark:text-green-400">
                  <CheckCircle className="w-4 h-4" />
                  Konfiguriert
                </span>
              ) : (
                <span className="text-sm text-gray-400">Nicht konfiguriert</span>
              )}
            </div>
          ))}
        </div>

        <p className="mt-4 text-xs text-gray-500 dark:text-gray-400">
          Die Sensor-Zuordnung wird über die Add-on-Konfiguration in Home Assistant vorgenommen.
        </p>
      </div>

      {/* Database */}
      <div className="card p-6">
        <div className="flex items-center gap-3 mb-4">
          <Database className="h-6 w-6 text-gray-500" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Datenbank
          </h2>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
          </div>
        ) : stats ? (
          <>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.anlagen}</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">Anlagen</p>
              </div>
              <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.monatsdaten}</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">Monatsdaten</p>
              </div>
              <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.investitionen}</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">Investitionen</p>
              </div>
              <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.strompreise}</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">Stromtarife</p>
              </div>
            </div>

            {stats.gesamt_erzeugung_kwh > 0 && (
              <div className="p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg mb-4">
                <p className="text-lg font-bold text-yellow-700 dark:text-yellow-300">
                  {(stats.gesamt_erzeugung_kwh / 1000).toLocaleString('de-DE', { maximumFractionDigits: 1 })} MWh
                </p>
                <p className="text-sm text-yellow-600 dark:text-yellow-400">
                  Gesamte PV-Erzeugung
                  {stats.daten_zeitraum && (
                    <span> ({stats.daten_zeitraum.von} - {stats.daten_zeitraum.bis})</span>
                  )}
                </p>
              </div>
            )}

            <div className="text-sm text-gray-500 dark:text-gray-400 space-y-1">
              <p>
                <span className="font-medium">Pfad:</span> {stats.database_path}
              </p>
              <p>
                <span className="font-medium">Version:</span> {settings?.version || '0.1.0'}
              </p>
            </div>
          </>
        ) : (
          <p className="text-gray-500 dark:text-gray-400">Keine Daten verfügbar</p>
        )}

        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <a
            href="/api/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-secondary text-sm"
          >
            API-Dokumentation
          </a>
        </div>
      </div>
    </div>
  )
}
