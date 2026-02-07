/**
 * HAExportSettings - Einstellungen für HA-Sensor-Export
 *
 * Ermöglicht:
 * - REST API Export (YAML-Snippet für configuration.yaml)
 * - MQTT Discovery Export (native HA-Entitäten)
 * - Übersicht aller exportierbaren Sensoren mit Werten/Formeln
 */

import { useState, useEffect } from 'react'
import {
  Home,
  RefreshCw,
  Loader2,
  CheckCircle,
  XCircle,
  Copy,
  Download,
  Send,
  Trash2,
  AlertTriangle,
  Info,
  ChevronDown,
  ChevronRight
} from 'lucide-react'
import { haApi, anlagenApi } from '../api'
import type {
  FullExportResponse,
  AnlageExport,
  SensorExportItem,
  MQTTTestResult,
  MQTTPublishResult,
  HAYamlSnippet
} from '../api/ha'
import type { Anlage } from '../types'

export default function HAExportSettings() {
  // State
  const [anlagen, setAnlagen] = useState<Anlage[]>([])
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)
  const [exportData, setExportData] = useState<FullExportResponse | null>(null)
  const [anlageExport, setAnlageExport] = useState<AnlageExport | null>(null)
  const [yamlSnippet, setYamlSnippet] = useState<HAYamlSnippet | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // MQTT State
  const [mqttHost, setMqttHost] = useState('core-mosquitto')
  const [mqttPort, setMqttPort] = useState(1883)
  const [mqttUser, setMqttUser] = useState('')
  const [mqttPassword, setMqttPassword] = useState('')
  const [mqttTestResult, setMqttTestResult] = useState<MQTTTestResult | null>(null)
  const [mqttPublishResult, setMqttPublishResult] = useState<MQTTPublishResult | null>(null)
  const [mqttTesting, setMqttTesting] = useState(false)
  const [mqttPublishing, setMqttPublishing] = useState(false)
  const [mqttRemoving, setMqttRemoving] = useState(false)

  // UI State
  const [activeTab, setActiveTab] = useState<'rest' | 'mqtt'>('mqtt')
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(['energie', 'finanzen']))
  const [copiedYaml, setCopiedYaml] = useState(false)

  // Daten laden
  const loadData = async () => {
    try {
      setLoading(true)
      setError(null)

      const [anlagenData, exportDataResult] = await Promise.all([
        anlagenApi.list(),
        haApi.getExportSensors()
      ])

      setAnlagen(anlagenData)
      setExportData(exportDataResult)

      // Erste Anlage auswählen
      if (anlagenData.length > 0 && !selectedAnlageId) {
        setSelectedAnlageId(anlagenData[0].id)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden')
    } finally {
      setLoading(false)
    }
  }

  // Anlage-spezifische Daten laden
  const loadAnlageData = async (anlageId: number) => {
    try {
      const [anlageData, yamlData] = await Promise.all([
        haApi.getAnlageSensors(anlageId),
        haApi.getYamlSnippet(anlageId)
      ])
      setAnlageExport(anlageData)
      setYamlSnippet(yamlData)
    } catch (e) {
      console.error('Fehler beim Laden der Anlage-Daten:', e)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    if (selectedAnlageId) {
      loadAnlageData(selectedAnlageId)
    }
  }, [selectedAnlageId])

  // MQTT Verbindung testen
  const testMqttConnection = async () => {
    setMqttTesting(true)
    setMqttTestResult(null)
    try {
      const result = await haApi.testMqtt({
        host: mqttHost,
        port: mqttPort,
        username: mqttUser || undefined,
        password: mqttPassword || undefined
      })
      setMqttTestResult(result)
    } catch (e) {
      setMqttTestResult({
        connected: false,
        error: e instanceof Error ? e.message : 'Verbindungsfehler'
      })
    } finally {
      setMqttTesting(false)
    }
  }

  // MQTT Sensoren publizieren
  const publishMqttSensors = async () => {
    if (!selectedAnlageId) return
    setMqttPublishing(true)
    setMqttPublishResult(null)
    try {
      const result = await haApi.publishMqtt(selectedAnlageId, {
        host: mqttHost,
        port: mqttPort,
        username: mqttUser || undefined,
        password: mqttPassword || undefined
      })
      setMqttPublishResult(result)
    } catch (e) {
      setMqttPublishResult({
        message: e instanceof Error ? e.message : 'Fehler beim Publizieren',
        anlage_id: selectedAnlageId,
        total: 0,
        success: 0,
        failed: 0
      })
    } finally {
      setMqttPublishing(false)
    }
  }

  // MQTT Sensoren entfernen
  const removeMqttSensors = async () => {
    if (!selectedAnlageId) return
    if (!confirm('Alle EEDC-Sensoren für diese Anlage aus Home Assistant entfernen?')) return

    setMqttRemoving(true)
    try {
      await haApi.removeMqtt(selectedAnlageId, {
        host: mqttHost,
        port: mqttPort,
        username: mqttUser || undefined,
        password: mqttPassword || undefined
      })
      setMqttPublishResult(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Entfernen')
    } finally {
      setMqttRemoving(false)
    }
  }

  // YAML kopieren
  const copyYaml = async () => {
    if (!yamlSnippet) return
    try {
      await navigator.clipboard.writeText(yamlSnippet.yaml)
      setCopiedYaml(true)
      setTimeout(() => setCopiedYaml(false), 2000)
    } catch {
      // Fallback für ältere Browser
      const textarea = document.createElement('textarea')
      textarea.value = yamlSnippet.yaml
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      setCopiedYaml(true)
      setTimeout(() => setCopiedYaml(false), 2000)
    }
  }

  // YAML downloaden
  const downloadYaml = () => {
    if (!yamlSnippet || !anlageExport) return
    const blob = new Blob([yamlSnippet.yaml], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `eedc_sensors_${anlageExport.anlage_name.toLowerCase().replace(/\s+/g, '_')}.yaml`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  // Kategorie toggle
  const toggleCategory = (category: string) => {
    setExpandedCategories(prev => {
      const next = new Set(prev)
      if (next.has(category)) {
        next.delete(category)
      } else {
        next.add(category)
      }
      return next
    })
  }

  // Sensoren nach Kategorie gruppieren
  const groupSensorsByCategory = (sensors: SensorExportItem[]) => {
    const groups: Record<string, SensorExportItem[]> = {}
    sensors.forEach(sensor => {
      const cat = sensor.category || 'sonstige'
      if (!groups[cat]) groups[cat] = []
      groups[cat].push(sensor)
    })
    return groups
  }

  const categoryLabels: Record<string, string> = {
    energie: 'Energie',
    finanzen: 'Finanzen',
    autarkie: 'Autarkie & Eigenverbrauch',
    umwelt: 'Umwelt',
    performance: 'Performance',
    sonstige: 'Sonstige'
  }

  const categoryIcons: Record<string, string> = {
    energie: '⚡',
    finanzen: '💰',
    autarkie: '🏠',
    umwelt: '🌱',
    performance: '📊',
    sonstige: '📌'
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-primary-500" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Home className="h-6 w-6 text-cyan-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            HA-Sensor-Export
          </h1>
        </div>
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

      {/* Info Box */}
      <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg flex gap-3">
        <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-blue-700 dark:text-blue-300">
          <p className="font-medium mb-1">Berechnete KPIs nach Home Assistant exportieren</p>
          <p>
            EEDC kann berechnete Kennzahlen (Autarkie, Ersparnis, CO₂, ROI) als Sensoren an Home Assistant zurückgeben.
            Wähle zwischen REST API (YAML-Konfiguration) oder MQTT Discovery (native Entitäten).
          </p>
        </div>
      </div>

      {/* Anlage Auswahl */}
      {anlagen.length > 1 && (
        <div className="card p-4">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Anlage auswählen
          </label>
          <select
            value={selectedAnlageId || ''}
            onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
          >
            {anlagen.map((a) => (
              <option key={a.id} value={a.id}>
                {a.anlagenname}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex gap-4">
          <button
            onClick={() => setActiveTab('mqtt')}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'mqtt'
                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            MQTT Discovery (empfohlen)
          </button>
          <button
            onClick={() => setActiveTab('rest')}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'rest'
                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            REST API (YAML)
          </button>
        </nav>
      </div>

      {/* MQTT Tab */}
      {activeTab === 'mqtt' && (
        <div className="space-y-6">
          {/* MQTT Konfiguration */}
          <div className="card p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              MQTT-Broker Konfiguration
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Host
                </label>
                <input
                  type="text"
                  value={mqttHost}
                  onChange={(e) => setMqttHost(e.target.value)}
                  placeholder="core-mosquitto"
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800"
                />
                <p className="mt-1 text-xs text-gray-500">
                  Bei HA Add-on: core-mosquitto
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Port
                </label>
                <input
                  type="number"
                  value={mqttPort}
                  onChange={(e) => setMqttPort(Number(e.target.value))}
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Benutzername (optional)
                </label>
                <input
                  type="text"
                  value={mqttUser}
                  onChange={(e) => setMqttUser(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Passwort (optional)
                </label>
                <input
                  type="password"
                  value={mqttPassword}
                  onChange={(e) => setMqttPassword(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800"
                />
              </div>
            </div>

            {/* Test Ergebnis */}
            {mqttTestResult && (
              <div className={`mb-4 p-3 rounded-lg ${
                mqttTestResult.connected
                  ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                  : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
              }`}>
                <div className="flex items-center gap-2">
                  {mqttTestResult.connected ? (
                    <>
                      <CheckCircle className="w-4 h-4 text-green-500" />
                      <span className="text-green-700 dark:text-green-300 text-sm">
                        Verbunden mit {mqttTestResult.broker}
                      </span>
                    </>
                  ) : (
                    <>
                      <XCircle className="w-4 h-4 text-red-500" />
                      <span className="text-red-700 dark:text-red-300 text-sm">
                        {mqttTestResult.error}
                      </span>
                    </>
                  )}
                </div>
                {mqttTestResult.hint && (
                  <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
                    {mqttTestResult.hint}
                  </p>
                )}
              </div>
            )}

            {/* Publish Ergebnis */}
            {mqttPublishResult && (
              <div className={`mb-4 p-3 rounded-lg ${
                mqttPublishResult.success > 0
                  ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                  : 'bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800'
              }`}>
                <div className="flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 text-green-500" />
                  <span className="text-gray-700 dark:text-gray-300 text-sm">
                    {mqttPublishResult.success} von {mqttPublishResult.total} Sensoren publiziert
                  </span>
                </div>
                {mqttPublishResult.failed > 0 && (
                  <p className="mt-1 text-xs text-yellow-600 dark:text-yellow-400">
                    {mqttPublishResult.failed} Sensoren konnten nicht publiziert werden
                  </p>
                )}
              </div>
            )}

            <div className="flex flex-wrap gap-3">
              <button
                onClick={testMqttConnection}
                disabled={mqttTesting}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
              >
                {mqttTesting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <RefreshCw className="w-4 h-4" />
                )}
                Verbindung testen
              </button>
              <button
                onClick={publishMqttSensors}
                disabled={mqttPublishing || !selectedAnlageId}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors disabled:opacity-50"
              >
                {mqttPublishing ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
                Sensoren publizieren
              </button>
              <button
                onClick={removeMqttSensors}
                disabled={mqttRemoving || !selectedAnlageId}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-800/30 transition-colors disabled:opacity-50"
              >
                {mqttRemoving ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Trash2 className="w-4 h-4" />
                )}
                Sensoren entfernen
              </button>
            </div>
          </div>

          <div className="p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg flex gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-amber-700 dark:text-amber-300">
              <p className="font-medium mb-1">MQTT Discovery</p>
              <p>
                Die Sensoren erscheinen automatisch in Home Assistant unter <strong>Einstellungen → Geräte & Dienste → MQTT</strong>.
                Um die Werte aktuell zu halten, muss die Publizierung regelmäßig erfolgen (manuell oder via Automatisierung).
              </p>
            </div>
          </div>
        </div>
      )}

      {/* REST Tab */}
      {activeTab === 'rest' && yamlSnippet && (
        <div className="space-y-6">
          <div className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                YAML für configuration.yaml
              </h2>
              <div className="flex gap-2">
                <button
                  onClick={copyYaml}
                  className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  {copiedYaml ? (
                    <>
                      <CheckCircle className="w-4 h-4 text-green-500" />
                      Kopiert!
                    </>
                  ) : (
                    <>
                      <Copy className="w-4 h-4" />
                      Kopieren
                    </>
                  )}
                </button>
                <button
                  onClick={downloadYaml}
                  className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  <Download className="w-4 h-4" />
                  Download
                </button>
              </div>
            </div>

            <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm font-mono max-h-96">
              {yamlSnippet.yaml}
            </pre>

            <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
              {yamlSnippet.hinweis}
            </p>
          </div>

          <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg flex gap-3">
            <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-blue-700 dark:text-blue-300">
              <p className="font-medium mb-1">REST Sensor Konfiguration</p>
              <p>
                Füge diesen YAML-Block in deine <code className="px-1 bg-blue-100 dark:bg-blue-800 rounded">configuration.yaml</code> ein.
                Die Sensoren werden alle {yamlSnippet.sensor_count > 0 ? '60 Sekunden' : ''} aktualisiert.
                Nach Änderungen muss Home Assistant neu gestartet werden.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Sensor Übersicht */}
      {anlageExport && (
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Verfügbare Sensoren ({anlageExport.sensors.length})
          </h2>

          <div className="space-y-4">
            {Object.entries(groupSensorsByCategory(anlageExport.sensors)).map(([category, sensors]) => (
              <div key={category} className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                <button
                  onClick={() => toggleCategory(category)}
                  className="w-full flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span>{categoryIcons[category] || '📌'}</span>
                    <span className="font-medium text-gray-900 dark:text-white">
                      {categoryLabels[category] || category}
                    </span>
                    <span className="text-sm text-gray-500">({sensors.length})</span>
                  </div>
                  {expandedCategories.has(category) ? (
                    <ChevronDown className="w-5 h-5 text-gray-400" />
                  ) : (
                    <ChevronRight className="w-5 h-5 text-gray-400" />
                  )}
                </button>

                {expandedCategories.has(category) && (
                  <div className="divide-y divide-gray-200 dark:divide-gray-700">
                    {sensors.map((sensor) => (
                      <div key={sensor.key} className="p-3 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-lg">{sensor.icon}</span>
                              <span className="font-medium text-gray-900 dark:text-white">
                                {sensor.name}
                              </span>
                            </div>
                            <code className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                              {sensor.key}
                            </code>
                          </div>
                          <div className="text-right">
                            <span className="text-lg font-semibold text-gray-900 dark:text-white">
                              {sensor.value !== null ? (
                                typeof sensor.value === 'number'
                                  ? sensor.value.toLocaleString('de-DE', { maximumFractionDigits: 2 })
                                  : sensor.value
                              ) : '-'}
                            </span>
                            <span className="ml-1 text-sm text-gray-500">{sensor.unit}</span>
                          </div>
                        </div>
                        {sensor.formel && (
                          <div className="mt-2 p-2 bg-gray-100 dark:bg-gray-800 rounded text-xs text-gray-600 dark:text-gray-400">
                            <span className="font-medium">Formel:</span> {sensor.formel}
                            {sensor.berechnung && (
                              <span className="ml-2 text-gray-500">= {sensor.berechnung}</span>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Investitionen */}
      {exportData && exportData.investitionen.length > 0 && (
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Investitions-Sensoren
          </h2>

          <div className="space-y-4">
            {exportData.investitionen.map((inv) => (
              <details key={inv.investition_id} className="border border-gray-200 dark:border-gray-700 rounded-lg">
                <summary className="p-3 bg-gray-50 dark:bg-gray-800 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700">
                  <span className="font-medium text-gray-900 dark:text-white">
                    {inv.bezeichnung}
                  </span>
                  <span className="ml-2 text-sm text-gray-500">
                    ({inv.typ} - {inv.sensors.length} Sensoren)
                  </span>
                </summary>
                <div className="p-3 space-y-2">
                  {inv.sensors.map((sensor) => (
                    <div key={sensor.key} className="flex justify-between items-center py-1">
                      <div>
                        <span className="text-sm text-gray-700 dark:text-gray-300">{sensor.name}</span>
                        <code className="ml-2 text-xs text-gray-500">{sensor.key}</code>
                      </div>
                      <div className="text-right">
                        <span className="font-medium">
                          {sensor.value !== null ? (
                            typeof sensor.value === 'number'
                              ? sensor.value.toLocaleString('de-DE', { maximumFractionDigits: 2 })
                              : sensor.value
                          ) : '-'}
                        </span>
                        <span className="ml-1 text-sm text-gray-500">{sensor.unit}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
