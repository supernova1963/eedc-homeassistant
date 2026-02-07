import { useState, useEffect } from 'react'
import { Moon, Sun, Monitor, Home, Database, RefreshCw, CheckCircle, XCircle, Loader2, Info, Search } from 'lucide-react'
import { useTheme } from '../context/ThemeContext'
import { systemApi, haApi, anlagenApi, type StatsResponse, type SettingsResponse, type HASensor } from '../api'
import { DiscoveryDialog } from '../components/discovery'
import type { Anlage } from '../types'

export default function Settings() {
  const { theme, setTheme } = useTheme()
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [settings, setSettings] = useState<SettingsResponse | null>(null)
  const [haSensors, setHaSensors] = useState<HASensor[]>([])
  const [anlagen, setAnlagen] = useState<Anlage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showDiscovery, setShowDiscovery] = useState(false)
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)

  const loadData = async () => {
    try {
      setLoading(true)
      setError(null)
      const [statsData, settingsData, anlagenData] = await Promise.all([
        systemApi.getStats(),
        systemApi.getSettings(),
        anlagenApi.list(),
      ])
      setStats(statsData)
      setSettings(settingsData)
      setAnlagen(anlagenData)

      // Erste Anlage als Standard auswählen
      if (anlagenData.length > 0 && !selectedAnlageId) {
        setSelectedAnlageId(anlagenData[0].id)
      }

      // Lade verfügbare HA-Sensoren wenn verbunden
      if (settingsData.ha_integration_enabled) {
        try {
          const sensors = await haApi.getSensors()
          setHaSensors(sensors)
        } catch {
          // HA nicht erreichbar - ignorieren
        }
      }
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
                {haSensors.length > 0 && (
                  <span className="text-gray-500 dark:text-gray-400 ml-2">
                    ({haSensors.length} Energy-Sensoren verfügbar)
                  </span>
                )}
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
          Datenerfassung
        </h3>
        <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg flex gap-2">
          <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-blue-700 dark:text-blue-300">
            <p className="font-medium mb-1">Monatsdaten via CSV-Import</p>
            <p>
              Die Erfassung der Monatsdaten erfolgt über <strong>CSV-Import</strong> oder <strong>manuelle Eingabe</strong>.
              Gehe zu <strong>Einstellungen → Import/Export</strong> um deine Daten zu importieren.
            </p>
          </div>
        </div>

        {/* Discovery Button */}
        {settings?.ha_integration_enabled && anlagen.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Auto-Discovery
                </h4>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Durchsuche Home Assistant nach Geräten (SMA, evcc, Smart, Wallbox) und erstelle Investitionen.
                </p>
              </div>
              <div className="flex items-center gap-2">
                {anlagen.length > 1 && (
                  <select
                    value={selectedAnlageId || ''}
                    onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
                    className="text-sm px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
                  >
                    {anlagen.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.anlagenname}
                      </option>
                    ))}
                  </select>
                )}
                <button
                  onClick={() => setShowDiscovery(true)}
                  disabled={!selectedAnlageId}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500 text-white hover:bg-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Search className="w-4 h-4" />
                  Geräte erkennen
                </button>
              </div>
            </div>
          </div>
        )}

        {haSensors.length > 0 && (
          <details className="mt-4">
            <summary className="text-sm font-medium text-gray-700 dark:text-gray-300 cursor-pointer hover:text-primary-600">
              Verfügbare Energy-Sensoren anzeigen
            </summary>
            <div className="mt-2 max-h-64 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg">
              <table className="w-full text-xs">
                <thead className="bg-gray-100 dark:bg-gray-800 sticky top-0">
                  <tr>
                    <th className="text-left p-2 font-medium">Entity ID</th>
                    <th className="text-left p-2 font-medium">Name</th>
                    <th className="text-left p-2 font-medium">Einheit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  {haSensors.map((sensor) => (
                    <tr key={sensor.entity_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                      <td className="p-2 font-mono text-gray-600 dark:text-gray-400">{sensor.entity_id}</td>
                      <td className="p-2 text-gray-700 dark:text-gray-300">{sensor.friendly_name || '-'}</td>
                      <td className="p-2 text-gray-500">{sensor.unit_of_measurement || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
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

      {/* Discovery Dialog */}
      {showDiscovery && selectedAnlageId && (
        <DiscoveryDialog
          isOpen={true}
          onClose={() => setShowDiscovery(false)}
          anlageId={selectedAnlageId}
          onInvestitionenCreated={loadData}
        />
      )}
    </div>
  )
}
