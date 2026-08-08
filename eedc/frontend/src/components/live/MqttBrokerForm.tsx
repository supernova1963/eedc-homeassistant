/**
 * MqttBrokerForm — Broker-Verbindung als eigenständiger SoT-Baustein.
 *
 * Datenquellen-V4 / B1 (SoT: docs/KONZEPT-DATENQUELLEN-V4.md §2a):
 * „Verbindung" getrennt von „was darüber fließt". EIN Broker für Inbound-Empfang,
 * Gateway und Export. Aus dem MqttInboundSetup-Wizard herausgelöst und als eigener
 * Block unter Einstellungen → Integration montiert.
 *
 * **B7-5c — Verbindung und Richtung entflochten:** der Schalter hieß „Broker-
 * Verbindung aktivieren", steuerte real aber den **Import** (Inbound-Subscriber).
 * Damit war „nur Export" unmöglich — der Default der HA App (Zuordnung über
 * HA-Sensoren, MQTT ausschließlich zum Publizieren). Jetzt:
 *   • Zugangsdaten = richtungs-neutral, deshalb IMMER sichtbar (der Export
 *     braucht sie auch, wenn der Import aus ist — vorher waren sie hinter dem
 *     Schalter versteckt).
 *   • Der Switch schaltet die **Import-Richtung** („Daten über MQTT empfangen").
 *     Ist er aus, bietet die Datenquellen-Fläche keine MQTT-Quellen an.
 *   • Die Export-Richtung sitzt im Export-Block (B7-5b).
 * Der DB-Key bleibt `mqtt_inbound` — gleiche Wirkung für Bestand, keine Migration
 * der Zugangsdaten nötig.
 */
import { useState, useEffect } from 'react'
import { Radio } from 'lucide-react'
import { Input, Button, Switch, Alert } from '../ui'
import { liveDashboardApi } from '../../api/liveDashboard'
import type { MqttTestResult, MqttInboundStatus } from '../../api/liveDashboard'
import { VERBINDUNG_GEAENDERT_EVENT } from '../../api/datenquellen'

export default function MqttBrokerForm() {
  const [enabled, setEnabled] = useState(false)
  const [host, setHost] = useState('localhost')
  const [port, setPort] = useState(1883)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [quelle, setQuelle] = useState('')
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<MqttInboundStatus | null>(null)

  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testResult, setTestResult] = useState<MqttTestResult | null>(null)
  const [saveResult, setSaveResult] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

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
      const result = await liveDashboardApi.saveMqttSettings({ enabled, host, port, username, password })
      if (result.gespeichert) {
        setSaveResult(
          result.subscriber_gestartet
            ? `Gespeichert. Verbunden mit ${result.broker}.`
            : 'Gespeichert. MQTT-Import deaktiviert.'
        )
        setQuelle('db')
        liveDashboardApi.getMqttStatus().then(setStatus).catch(() => {})
        // Datenquellen-Fläche über die geänderte Broker-Verfügbarkeit informieren
        // (Gateway/Inbound-Optionen ein-/ausblenden ohne F5).
        window.dispatchEvent(new CustomEvent(VERBINDUNG_GEAENDERT_EVENT))
      } else {
        setSaveError('Speichern fehlgeschlagen.')
      }
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Speichern fehlgeschlagen')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">wird geladen …</p>
  }

  return (
    <div className="space-y-4">
      {/* Zugangsdaten: richtungs-neutral, deshalb immer sichtbar — der Export
          nutzt dieselbe Verbindung, auch wenn der Import aus ist (B7-5c). */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input label="Host" value={host} onChange={(e) => setHost(e.target.value)} placeholder="localhost" required />
        <Input label="Port" type="number" value={port} onChange={(e) => setPort(Number(e.target.value))} min={1} max={65535} />
        <Input label="Benutzername" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="optional" autoComplete="off" />
        <Input label="Passwort" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="optional" autoComplete="off" />
      </div>
      {quelle === 'env' && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Aktuell aus Umgebungsvariablen geladen. Nach dem Speichern werden DB-Einstellungen verwendet.
        </p>
      )}

      {/* Import-Richtung. Der Export sitzt im Block „MQTT-Export". */}
      <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
        <div className="flex items-center gap-3">
          <Switch checked={enabled} onChange={setEnabled} ariaLabel="Daten über MQTT empfangen" />
          <span className="text-sm text-gray-700 dark:text-gray-300">Daten über MQTT empfangen (Import)</span>
        </div>
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
          {enabled
            ? 'MQTT-Topics stehen in den Datenquellen als Feld-Quelle zur Verfügung.'
            : 'Felder werden nicht über MQTT bequellt — die Datenquellen bieten dann keine MQTT-Topics an. Der Export über diese Verbindung bleibt davon unberührt.'}
        </p>
      </div>

      <div className="flex flex-wrap gap-3 pt-1">
        <Button type="button" variant="secondary" onClick={testConnection} disabled={testing || !host} loading={testing}>
          {!testing && <Radio className="w-4 h-4 mr-2" />}Verbindung testen
        </Button>
        <Button type="button" onClick={saveSettings} disabled={saving || !host} loading={saving}>
          Speichern{enabled ? ' & Verbinden' : ''}
        </Button>
      </div>

      {testResult && (
        <Alert type={testResult.connected ? 'success' : 'error'}>
          {testResult.connected ? testResult.message : testResult.error}
        </Alert>
      )}
      {saveResult && <Alert type="success">{saveResult}</Alert>}
      {saveError && <Alert type="error">{saveError}</Alert>}

      {status?.subscriber_aktiv && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Verbunden mit {status.broker} · {status.empfangene_nachrichten ?? 0} Nachrichten empfangen
        </p>
      )}
    </div>
  )
}
