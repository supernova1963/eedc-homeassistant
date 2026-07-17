/**
 * HaVerbindungForm — HA-Verbindung als eigenständiger SoT-Baustein (Basis).
 *
 * Datenquellen-V4 / B4a (SoT: docs/drafts/KONZEPT-DATENQUELLEN-V4.md §2a):
 * zweiter Verbindungs-Block neben dem MQTT-Broker. HA-App (Supervisor) → nur
 * Status; Standalone → Basis-URL + Long-Lived-Token eingeben/testen/speichern.
 *
 * **Nur Basis:** einrichten + testen. HA-Sensoren tatsächlich als Datenquelle
 * nutzen (im Standalone) verlangt den Gate-Umbau und folgt später (P3).
 */
import { useState, useEffect } from 'react'
import { Radio } from 'lucide-react'
import { Input, Button, Switch, Alert } from '../ui'
import { haRemoteApi } from '../../api/haRemote'
import type { HaRemoteTestResult, MqttImportFolge } from '../../api/haRemote'
import { VERBINDUNG_GEAENDERT_EVENT } from '../../api/datenquellen'

export default function HaVerbindungForm() {
  const [loading, setLoading] = useState(true)
  const [supervisor, setSupervisor] = useState(false)
  const [enabled, setEnabled] = useState(false)
  const [baseUrl, setBaseUrl] = useState('')
  const [token, setToken] = useState('')

  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testResult, setTestResult] = useState<HaRemoteTestResult | null>(null)
  const [saveResult, setSaveResult] = useState<string | null>(null)
  const [mqttFolge, setMqttFolge] = useState<MqttImportFolge | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    haRemoteApi.getSettings().then((s) => {
      setSupervisor(s.supervisor_verfuegbar)
      setEnabled(s.enabled)
      setBaseUrl(s.base_url)
      setToken(s.token) // '***' wenn gesetzt
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const testConnection = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      setTestResult(await haRemoteApi.test({ base_url: baseUrl, token }))
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
      const r = await haRemoteApi.saveSettings({ enabled, base_url: baseUrl, token })
      if (r.gespeichert) {
        setSaveResult(enabled ? `Gespeichert. HA-Verbindung: ${r.base_url}` : 'Gespeichert. HA-Verbindung deaktiviert.')
        // B7-5c: Das Aktivieren stellt den MQTT-Import auf den Default (aus) —
        // das MUSS hier stehen, sonst wirkt es wie ein stiller Nebeneffekt und
        // die Ursache ausbleibender Werte stünde in einem anderen Block.
        setMqttFolge(r.mqtt_import ?? null)
        // Datenquellen-Fläche über die geänderte HA-Verfügbarkeit informieren (ohne F5).
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

  // HA-App: die Integration läuft über den Supervisor — keine Remote-Verbindung nötig.
  if (supervisor) {
    return (
      <Alert type="success">
        Verbunden über die Home-Assistant-Integration (Supervisor). Eine separate Remote-Verbindung ist nicht erforderlich.
      </Alert>
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600 dark:text-gray-300">
        eedc ohne Home-Assistant-Integration mit einer entfernten HA-Installation verbinden — Basis-URL + Long-Lived-Token (aus dem HA-Benutzerprofil).
      </p>

      <div className="flex items-center gap-3">
        <Switch checked={enabled} onChange={setEnabled} ariaLabel="HA-Verbindung aktivieren" />
        <span className="text-sm text-gray-700 dark:text-gray-300">HA-Verbindung aktivieren</span>
      </div>

      {enabled && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="Basis-URL" value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://homeassistant.local:8123" required
          />
          <Input
            label="Long-Lived-Token" type="password" value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Token aus dem HA-Profil" autoComplete="off" required
          />
        </div>
      )}

      <div className="flex flex-wrap gap-3 pt-1">
        {enabled && (
          <Button type="button" variant="secondary" onClick={testConnection} disabled={testing || !baseUrl} loading={testing}>
            {!testing && <Radio className="w-4 h-4 mr-2" />}Verbindung testen
          </Button>
        )}
        <Button type="button" onClick={saveSettings} disabled={saving || (enabled && !baseUrl)} loading={saving}>
          Speichern
        </Button>
      </div>

      {testResult && (
        <Alert type={testResult.connected ? 'success' : 'error'}>
          {testResult.connected ? testResult.message : testResult.error}
        </Alert>
      )}
      {saveResult && <Alert type="success">{saveResult}</Alert>}

      {/* B7-5c: Folge fürs MQTT-Modell benennen — „MQTT nur für Export" ist der
          gewollte Default, darf aber nicht stumm passieren. */}
      {mqttFolge?.abgeschaltet && (
        <Alert type="info">
          MQTT-Import wurde abgeschaltet — die Zuordnung läuft jetzt über HA-Sensoren, MQTT bleibt
          für den Export (HA-Discovery) aktiv.
          {mqttFolge.connectoren
            ? ` Achtung: ${mqttFolge.connectoren} Geräte-Connector${mqttFolge.connectoren === 1 ? '' : 'en'} liefern ihre Werte über MQTT — deren Daten pausieren, bis du „Daten über MQTT empfangen" im Block MQTT-Broker-Verbindung wieder einschaltest.`
            : ' Bei Bedarf im Block „MQTT-Broker-Verbindung" wieder einschalten.'}
        </Alert>
      )}
      {mqttFolge?.grund === 'gateway_in_benutzung' && (
        <Alert type="info">
          MQTT-Import bleibt aktiv: {mqttFolge.gateway_mappings} Gateway-Zuordnung
          {mqttFolge.gateway_mappings === 1 ? '' : 'en'} sind in Benutzung und würden sonst wirkungslos.
          Abschalten kannst du ihn im Block „MQTT-Broker-Verbindung".
        </Alert>
      )}
      {saveError && <Alert type="error">{saveError}</Alert>}

      <p className="text-xs text-gray-500 dark:text-gray-400">
        Die Verbindung wird hier eingerichtet und getestet. HA-Sensoren als Datenquelle zu nutzen folgt in einem späteren Schritt.
      </p>
    </div>
  )
}
