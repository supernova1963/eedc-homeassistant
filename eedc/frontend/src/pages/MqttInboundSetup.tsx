/**
 * MQTT-Inbound Einrichtung — Broker-Konfiguration für Live-Daten via MQTT.
 *
 * Ermöglicht Standalone-Usern, einen MQTT-Broker zu konfigurieren,
 * über den Live-Leistungsdaten empfangen werden.
 */

import { useState, useEffect } from 'react'
import { Radio, CheckCircle, XCircle, Loader2, Info, Copy, Check } from 'lucide-react'
import Input from '../components/ui/Input'
import { liveDashboardApi } from '../api/liveDashboard'
import type { MqttTestResult, MqttInboundStatus, MqttTopic } from '../api/liveDashboard'
import { useAnlagen } from '../hooks'

export default function MqttInboundSetup() {
  const { anlagen } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)

  // Form State
  const [enabled, setEnabled] = useState(false)
  const [host, setHost] = useState('localhost')
  const [port, setPort] = useState(1883)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(true)
  const [quelle, setQuelle] = useState<string>('')

  // Action State
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testResult, setTestResult] = useState<MqttTestResult | null>(null)
  const [saveResult, setSaveResult] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Status
  const [status, setStatus] = useState<MqttInboundStatus | null>(null)

  // Copy-State für Topic-Beispiele
  const [copied, setCopied] = useState<string | null>(null)

  // Konkrete Topics
  const [topics, setTopics] = useState<MqttTopic[]>([])

  // Erste Anlage vorauswählen
  useEffect(() => {
    if (anlagen.length > 0 && selectedAnlageId === null) {
      setSelectedAnlageId(anlagen[0].id)
    }
  }, [anlagen, selectedAnlageId])

  // Settings laden
  useEffect(() => {
    Promise.all([
      liveDashboardApi.getMqttSettings(),
      liveDashboardApi.getMqttStatus(),
    ]).then(([settings, mqttStatus]) => {
      setEnabled(settings.enabled)
      setHost(settings.host)
      setPort(settings.port)
      setUsername(settings.username)
      setPassword(settings.password)
      setQuelle(settings.quelle || '')
      setStatus(mqttStatus)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  // Topics laden wenn Anlage gewählt
  useEffect(() => {
    if (selectedAnlageId === null) return
    liveDashboardApi.getMqttTopics(selectedAnlageId)
      .then(resp => setTopics(resp.topics || []))
      .catch(() => setTopics([]))
  }, [selectedAnlageId])

  const testConnection = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const result = await liveDashboardApi.testMqttConnection({
        host, port, username: username || undefined, password: password || undefined,
      })
      setTestResult(result)
    } catch (e) {
      setTestResult({ connected: false, error: e instanceof Error ? e.message : 'Verbindungsfehler' })
    } finally {
      setTesting(false)
    }
  }

  const saveSettings = async () => {
    setSaving(true)
    setSaveResult(null)
    setSaveError(null)
    try {
      const result = await liveDashboardApi.saveMqttSettings({
        enabled, host, port, username, password,
      })
      if (result.gespeichert) {
        setSaveResult(
          result.subscriber_gestartet
            ? `Gespeichert. Subscriber verbunden mit ${result.broker}.`
            : 'Gespeichert. MQTT-Inbound deaktiviert.'
        )
        setQuelle('db')
        // Status neu laden
        liveDashboardApi.getMqttStatus().then(setStatus).catch(() => {})
      }
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    } finally {
      setSaving(false)
    }
  }

  const copyTopic = (topic: string) => {
    navigator.clipboard.writeText(topic)
    setCopied(topic)
    setTimeout(() => setCopied(null), 2000)
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
      </div>
    )
  }

  // Erstes konkretes Topic für Beispiel-Befehl
  const erstesInvTopic = topics.find(t => t.topic.includes('/inv/'))

  return (
    <div className="p-4 sm:p-6 max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <Radio className="h-6 w-6 text-blue-600 dark:text-blue-400" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">
            MQTT-Inbound
          </h1>
          {status?.subscriber_aktiv && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
              aktiv
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
          Empfange Live-Leistungsdaten von jedem Smarthome-System via MQTT.
          Funktioniert mit Node-RED, Home Assistant, ioBroker, FHEM, openHAB.
        </p>
      </div>

      {/* Broker-Konfiguration */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5 space-y-4">
        <h2 className="font-semibold text-gray-900 dark:text-white">Broker-Verbindung</h2>

        {/* Enabled Toggle */}
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="w-4 h-4 text-primary-600 rounded border-gray-300 dark:border-gray-600 focus:ring-primary-500"
          />
          <span className="text-sm text-gray-700 dark:text-gray-300">
            MQTT-Inbound aktivieren
          </span>
        </label>

        {enabled && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Input
                label="Host"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder="localhost"
                required
              />
              <Input
                label="Port"
                type="number"
                value={port}
                onChange={(e) => setPort(Number(e.target.value))}
                min={1}
                max={65535}
              />
              <Input
                label="Benutzername"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="optional"
                autoComplete="off"
              />
              <Input
                label="Passwort"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="optional"
                autoComplete="off"
              />
            </div>

            {quelle === 'env' && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Aktuell aus Umgebungsvariablen geladen. Nach dem Speichern werden DB-Einstellungen verwendet.
              </p>
            )}
          </>
        )}

        {/* Actions */}
        <div className="flex flex-wrap gap-3 pt-2">
          {enabled && (
            <button
              onClick={testConnection}
              disabled={testing || !host}
              className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 transition-colors"
            >
              {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Radio className="w-4 h-4" />}
              Verbindung testen
            </button>
          )}
          <button
            onClick={saveSettings}
            disabled={saving || (enabled && !host)}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
          >
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            Speichern{enabled ? ' & Verbinden' : ''}
          </button>
        </div>

        {/* Test Result */}
        {testResult && (
          <div className={`flex items-start gap-2 p-3 rounded-lg text-sm ${
            testResult.connected
              ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
              : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'
          }`}>
            {testResult.connected
              ? <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" />
              : <XCircle className="w-4 h-4 mt-0.5 shrink-0" />}
            <span>{testResult.connected ? testResult.message : testResult.error}</span>
          </div>
        )}

        {/* Save Result */}
        {saveResult && (
          <div className="flex items-start gap-2 p-3 rounded-lg text-sm bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400">
            <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{saveResult}</span>
          </div>
        )}
        {saveError && (
          <div className="flex items-start gap-2 p-3 rounded-lg text-sm bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400">
            <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{saveError}</span>
          </div>
        )}
      </div>

      {/* Status */}
      {status?.subscriber_aktiv && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5 space-y-2">
          <h2 className="font-semibold text-gray-900 dark:text-white">Status</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
            <div>
              <span className="text-gray-500 dark:text-gray-400">Broker: </span>
              <span className="text-gray-900 dark:text-white">{status.broker}</span>
            </div>
            <div>
              <span className="text-gray-500 dark:text-gray-400">Nachrichten: </span>
              <span className="text-gray-900 dark:text-white">{status.empfangene_nachrichten ?? 0}</span>
            </div>
            {status.letzte_nachricht && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">Letzte: </span>
                <span className="text-gray-900 dark:text-white">
                  {new Date(status.letzte_nachricht).toLocaleTimeString('de-DE')}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Topic-Dokumentation */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Info className="w-5 h-5 text-blue-500" />
            <h2 className="font-semibold text-gray-900 dark:text-white">Topic-Struktur</h2>
          </div>
          {anlagen.length > 1 && (
            <select
              value={selectedAnlageId ?? ''}
              onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
              className="text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              {anlagen.map(a => (
                <option key={a.id} value={a.id}>{a.anlagenname || `Anlage ${a.id}`}</option>
              ))}
            </select>
          )}
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Publishe Werte auf diese Topics, um sie im Live-Dashboard zu sehen.
          Die Topics werden automatisch aus deinen Anlagen und Investitionen generiert.
        </p>

        {topics.length > 0 ? (
          <div className="space-y-2">
            {topics.map((t) => (
              <TopicRow
                key={t.topic}
                label={t.label}
                topic={t.topic}
                copied={copied}
                onCopy={copyTopic}
              />
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-400 italic">
            Keine Anlagen/Investitionen vorhanden. Lege zuerst eine Anlage mit Investitionen an.
          </p>
        )}

        {/* Beispiel-Befehl */}
        {erstesInvTopic && (
          <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Beispiel (mosquitto_pub):</p>
            <code className="text-xs text-gray-800 dark:text-gray-200 break-all">
              mosquitto_pub -h {host || 'localhost'} -t &quot;{erstesInvTopic.topic}&quot; -m &quot;4200&quot;
            </code>
          </div>
        )}
      </div>
    </div>
  )
}

function TopicRow({ label, topic, copied, onCopy }: {
  label: string
  topic: string
  copied: string | null
  onCopy: (topic: string) => void
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-gray-500 dark:text-gray-400 w-48 shrink-0 truncate" title={label}>{label}</span>
      <code className="flex-1 text-xs bg-gray-100 dark:bg-gray-900 px-2 py-1 rounded text-gray-800 dark:text-gray-200 font-mono truncate">
        {topic}
      </code>
      <button
        onClick={() => onCopy(topic)}
        className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 shrink-0"
        title="Topic kopieren"
      >
        {copied === topic ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
      </button>
    </div>
  )
}
