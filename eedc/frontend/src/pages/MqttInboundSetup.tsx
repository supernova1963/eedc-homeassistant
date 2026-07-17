/**
 * MQTT-Inbound Einrichtung — Broker-Konfiguration für Live-Daten via MQTT.
 *
 * Ermöglicht Standalone-Usern, einen MQTT-Broker zu konfigurieren,
 * über den Live-Leistungsdaten empfangen werden.
 */

import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { Radio, CheckCircle, XCircle, Info, Copy, Check, Activity, RefreshCw, ChevronDown, BookOpen, Trash2, Wand2 } from 'lucide-react'
import Input from '../components/ui/Input'
import Button from '../components/ui/Button'
import Select from '../components/ui/Select'
import Switch from '../components/ui/Switch'
import Stepper from '../components/ui/Stepper'
import RadioGroup from '../components/ui/RadioGroup'
import { liveDashboardApi } from '../api/liveDashboard'
import type { MqttTestResult, MqttInboundStatus, MqttTopic, MqttCacheWert } from '../api/liveDashboard'
import { DataLoadingState } from '../components/common'
import { useSelectedAnlage } from '../hooks'
import { useWizardHost } from '../v4/wizardHost'
import MqttGateway from '../components/live/MqttGateway'

/**
 * Teil D (D4, Gernot 2026-07-09): im V4-Overlay ist das EIN Kombi-Wizard
 * „Live-Daten via MQTT" — Schritt 1 = Modus-Wahl (Empfangen = Inbound /
 * Senden = Gateway), Schritt 2 = der jeweilige Zweig. Die V3-Standalone-Route
 * behält ihr lineares IST-Layout (V3-Release-Grenze: Strukturumbau nur /v4).
 */
type MqttModus = 'inbound' | 'gateway'

export default function MqttInboundSetup() {
  const wizardHost = useWizardHost()
  const { anlagen, selectedAnlageId, setSelectedAnlageId } = useSelectedAnlage()

  // Kombi-Wizard-State (nur im Overlay wirksam)
  const [modus, setModus] = useState<MqttModus | null>(null)
  const [schritt, setSchritt] = useState(0)

  // Form State
  const [enabled, setEnabled] = useState(false)
  const [host, setHost] = useState('localhost')
  const [port, setPort] = useState(1883)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(true)
  const [quelle, setQuelle] = useState<string>('')

  // Topics laden wenn Anlage gewählt
  useEffect(() => {
    if (selectedAnlageId == null) return
    liveDashboardApi.getMqttTopics(selectedAnlageId)
      .then(resp => setTopics(resp.topics || []))
      .catch(() => setTopics([]))
  }, [selectedAnlageId])

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

  // Monitor
  const [cacheValues, setCacheValues] = useState<MqttCacheWert[]>([])
  const [monitorLoading, setMonitorLoading] = useState(false)

  // W5-Dirty-Referenz: Broker-Form-Snapshot nach Laden/Speichern.
  const geladenRef = useRef('')

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
      geladenRef.current = JSON.stringify({
        enabled: settings.enabled, host: settings.host, port: settings.port,
        username: settings.username, password: settings.password,
      })
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
        geladenRef.current = JSON.stringify({ enabled, host, port, username, password })
        // Status neu laden
        liveDashboardApi.getMqttStatus().then(setStatus).catch(() => {})
      }
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    } finally {
      setSaving(false)
    }
  }

  const copyTopic = async (topic: string) => {
    // navigator.clipboard ist nur in „secure contexts" (HTTPS/localhost) verfügbar.
    // Über http://<lokale-IP>:8099 (HA-Add-on/Standalone im LAN) blockiert der
    // Browser sie — Fallback auf execCommand, damit der Button dort funktioniert
    // (Dirk-PN 2026-06-01).
    let ok = false
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(topic)
        ok = true
      }
    } catch {
      ok = false
    }
    if (!ok) {
      try {
        const ta = document.createElement('textarea')
        ta.value = topic
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        document.body.appendChild(ta)
        ta.focus()
        ta.select()
        ok = document.execCommand('copy')
        document.body.removeChild(ta)
      } catch {
        ok = false
      }
    }
    if (ok) {
      setCopied(topic)
      setTimeout(() => setCopied(null), 2000)
    }
  }

  const loadCacheValues = async () => {
    setMonitorLoading(true)
    try {
      const resp = await liveDashboardApi.getMqttValues()
      setCacheValues(resp.werte || [])
    } catch {
      setCacheValues([])
    } finally {
      setMonitorLoading(false)
    }
  }

  // W5: ungespeicherte Broker-Eingaben melden (Overlay-Verwerfen-Nachfrage).
  const formDirty =
    !!geladenRef.current &&
    JSON.stringify({ enabled, host, port, username, password }) !== geladenRef.current &&
    saveResult === null
  useEffect(() => {
    wizardHost.setzeBlocker(formDirty)
    return () => wizardHost.setzeBlocker(false)
  }, [formDirty, wizardHost])

  if (loading) {
    return <DataLoadingState loading={true} error={null}><div /></DataLoadingState>
  }

  // Erstes konkretes Topic für Beispiel-Befehl
  const erstesInvTopic = topics.find(t => t.topic.includes('/inv/'))

  const inboundKern = (
    <>
      {/* Broker-Konfiguration */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5 space-y-4">
        <h2 className="font-semibold text-gray-900 dark:text-white">Broker-Verbindung</h2>

        {/* Enabled Toggle — B15/S3: Switch-SoT (An-Aus-Schalter) */}
        <div className="flex items-center gap-3">
          <Switch checked={enabled} onChange={setEnabled} ariaLabel="MQTT-Inbound aktivieren" />
          <span className="text-sm text-gray-700 dark:text-gray-300">
            MQTT-Inbound aktivieren
          </span>
        </div>

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

        {/* Actions — Button-SoT */}
        <div className="flex flex-wrap gap-3 pt-2">
          {enabled && (
            <Button
              type="button" variant="secondary"
              onClick={testConnection}
              disabled={testing || !host}
              loading={testing}
            >
              {!testing && <Radio className="w-4 h-4 mr-2" />}Verbindung testen
            </Button>
          )}
          <Button
            type="button"
            onClick={saveSettings}
            disabled={saving || (enabled && !host)}
            loading={saving}
          >
            Speichern{enabled ? ' & Verbinden' : ''}
          </Button>
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

      {/* Empfangene Werte (Monitor) */}
      {status?.subscriber_aktiv && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-green-500" />
              <h2 className="font-semibold text-gray-900 dark:text-white">Empfangene Werte</h2>
            </div>
            <div className="flex gap-2">
              <Button
                type="button" variant="ghost" size="sm"
                onClick={loadCacheValues}
                disabled={monitorLoading}
              >
                <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${monitorLoading ? 'animate-spin' : ''}`} />
                Aktualisieren
              </Button>
              {cacheValues.length > 0 && (
                <Button
                  type="button" variant="danger" size="sm"
                  onClick={async () => {
                    await liveDashboardApi.deleteMqttCache(undefined, true)
                    setCacheValues([])
                    liveDashboardApi.getMqttStatus().then(setStatus).catch(() => {})
                  }}
                  title="Löscht Cache und Retained Messages am Broker"
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1.5" />
                  Cache leeren
                </Button>
              )}
            </div>
          </div>

          {cacheValues.length > 0 ? (
            <div className="space-y-1">
              {cacheValues.map((w) => (
                <div key={w.topic} className="flex items-center gap-2 text-sm">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    w.kategorie === 'live'
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                      : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                  }`}>
                    {w.kategorie}
                  </span>
                  <code className="flex-1 text-xs font-mono text-gray-600 dark:text-gray-400 truncate" title={w.topic}>
                    {w.topic}
                  </code>
                  <span className="font-medium text-gray-900 dark:text-white tabular-nums">
                    {w.wert}
                  </span>
                  <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
                    {new Date(w.zeitpunkt).toLocaleTimeString('de-DE')}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 dark:text-gray-500 italic">
              Noch keine Werte empfangen. Klicke &quot;Aktualisieren&quot; nach dem Senden von Testdaten.
            </p>
          )}
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
            <Select
              steuer
              value={selectedAnlageId != null ? String(selectedAnlageId) : ''}
              onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
              aria-label="Anlage wählen"
              options={anlagen.map(a => ({ value: String(a.id), label: a.anlagenname || `Anlage ${a.id}` }))}
            />
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
                beschreibung={t.beschreibung}
                topic={t.topic}
                copied={copied}
                onCopy={copyTopic}
              />
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-400 dark:text-gray-500 italic">
            Keine Anlagen/Investitionen vorhanden. Lege zuerst eine Anlage mit Investitionen an.
          </p>
        )}

        {/* Beispiel-Befehl */}
        {erstesInvTopic && (
          <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Beispiel (mosquitto_pub):</p>
            <code className="text-xs text-gray-800 dark:text-gray-200 break-all">
              mosquitto_pub -h {host || 'localhost'} -r -t &quot;{erstesInvTopic.topic}&quot; -m &quot;4200&quot;
            </code>
          </div>
        )}
      </div>

      {/* HA Automation Generator */}
      <HaAutomationGenerator anlagen={anlagen} />

      {/* Beispiel-Flows für andere Systeme */}
      <AndereSystemeFlows topics={topics} host={host || 'localhost'} />
    </>
  )

  const gatewayKern = (
    <MqttGateway
      anlageId={selectedAnlageId ?? null}
      mqttAktiv={!!status?.subscriber_aktiv}
    />
  )

  // ── Overlay (V4): Kombi-Wizard „Live-Daten via MQTT" — Schritt 1 = Modus-Wahl ──
  if (wizardHost.imOverlay) {
    return (
      <div className="space-y-6">
        <Stepper
          schritte={[
            { titel: 'Modus' },
            { titel: modus === 'gateway' ? 'Senden (Gateway)' : 'Empfangen (Inbound)' },
          ]}
          aktuell={schritt}
          onSchrittKlick={setSchritt}
        />
        {schritt === 0 ? (
          <div className="space-y-4">
            <RadioGroup
              label="Was möchtest du einrichten?"
              name="mqtt-modus"
              value={modus ?? ''}
              onChange={(k) => setModus(k as MqttModus)}
              options={[
                {
                  value: 'inbound',
                  label: 'Live-Daten empfangen (MQTT-Inbound)',
                  description: 'eedc empfängt Live-Leistungsdaten von deinem Smarthome-System (Node-RED, HA, ioBroker, FHEM, openHAB) über einen MQTT-Broker.',
                },
                {
                  value: 'gateway',
                  label: 'Werte an eedc senden (Gateway-Mapping)',
                  description: 'Fremde MQTT-Topics (z. B. Zendure, Shelly) auf eedc-Topics umlenken — inkl. Presets und JSON-Pfaden.',
                },
              ]}
            />
            <div className="flex justify-end">
              <Button type="button" disabled={modus == null} onClick={() => setSchritt(1)}>
                Weiter
              </Button>
            </div>
          </div>
        ) : modus === 'gateway' ? (
          gatewayKern
        ) : (
          <div className="space-y-6">{inboundKern}</div>
        )}
      </div>
    )
  }

  // ── Standalone-Route (V3): lineares IST-Layout unverändert ──
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

      {inboundKern}

      {/* MQTT Gateway */}
      {gatewayKern}
    </div>
  )
}

function TopicRow({ label, beschreibung, topic, copied, onCopy }: {
  label: string
  beschreibung?: string | null
  topic: string
  copied: string | null
  onCopy: (topic: string) => void
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-gray-500 dark:text-gray-400 w-48 shrink-0 truncate" title={beschreibung || label}>{label}</span>
      <code className="flex-1 text-xs bg-gray-100 dark:bg-gray-900 px-2 py-1 rounded text-gray-800 dark:text-gray-200 font-mono truncate">
        {topic}
      </code>
      <Button
        type="button" variant="ghost" size="icon" className="shrink-0"
        onClick={() => onCopy(topic)}
        aria-label="Topic kopieren" title="Topic kopieren"
      >
        {copied === topic ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
      </Button>
    </div>
  )
}

/** Label → Sensor-Platzhalter: "SolarEdge – Leistung (W)" → "solaredge_leistung" */
function labelToSensorId(label: string): string {
  return label
    .replace(/\s*\([^)]*\)\s*/g, '')   // Einheit entfernen
    .replace(/\s*–\s*/g, '_')
    .replace(/[äÄ]/g, 'ae').replace(/[öÖ]/g, 'oe').replace(/[üÜ]/g, 'ue').replace(/ß/g, 'ss')
    .replace(/[^a-zA-Z0-9_]/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
    .toLowerCase()
}

/** HA Automation Generator — Wizard zum Zuordnen von HA-Entities zu MQTT-Topics */
function HaAutomationGenerator({ anlagen }: { anlagen: { id: number; anlagenname: string }[] }) {
  const [open, setOpen] = useState(false)
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)
  const [topics, setTopics] = useState<MqttTopic[]>([])
  const [entityMap, setEntityMap] = useState<Record<string, string>>({})
  const [copiedYaml, setCopiedYaml] = useState<string | null>(null)
  const [interval, setInterval] = useState('5')

  // Erste Anlage vorauswählen
  useEffect(() => {
    if (anlagen.length > 0 && selectedAnlageId === null) {
      setSelectedAnlageId(anlagen[0].id)
    }
  }, [anlagen, selectedAnlageId])

  // Topics laden wenn Anlage gewählt
  useEffect(() => {
    if (selectedAnlageId === null) return
    liveDashboardApi.getMqttTopics(selectedAnlageId)
      .then(resp => setTopics(resp.topics || []))
      .catch(() => setTopics([]))
  }, [selectedAnlageId])

  // Topics in Live und Energy aufteilen
  const { liveTopics, energyTopics } = useMemo(() => {
    const live: MqttTopic[] = []
    const energy: MqttTopic[] = []
    for (const t of topics) {
      if (t.typ === 'live') live.push(t)
      else if (t.typ === 'energy') energy.push(t)
    }
    return { liveTopics: live, energyTopics: energy }
  }, [topics])

  // Default-Platzhalter für Entity-IDs
  const getPlaceholder = useCallback((t: MqttTopic) => {
    return `sensor.${labelToSensorId(t.label)}`
  }, [])

  const updateEntity = (topic: string, value: string) => {
    setEntityMap(prev => ({ ...prev, [topic]: value }))
  }

  // YAML generieren für eine Gruppe von Topics. useCallback, damit die beiden
  // useMemo unten es als Dep führen können — es schließt über `entityMap`, das
  // dort ohnehin schon in den Deps steht.
  const generateYaml = useCallback((
    groupTopics: MqttTopic[],
    alias: string,
    triggerSeconds: string,
  ): string => {
    const mapped = groupTopics.filter(t => entityMap[t.topic]?.trim())
    if (mapped.length === 0) return ''

    const actions = mapped.map(t => {
      const entity = entityMap[t.topic]!.trim()
      return `      - service: mqtt.publish
        data:
          topic: "${t.topic}"
          payload: "{{ states('${entity}') }}"
          retain: true`
    }).join('\n')

    return `automation:
  - alias: "${alias}"
    description: "Generiert von eedc — sendet ${mapped.length} Sensor(en) per MQTT"
    trigger:
      - platform: time_pattern
        seconds: "/${triggerSeconds}"
    condition:
      - condition: template
        value_template: "{{ true }}"
    action:
${actions}`
  }, [entityMap])

  const liveYaml = useMemo(
    () => generateYaml(liveTopics, 'eedc Live-Daten senden', interval),
    [liveTopics, interval, generateYaml],
  )
  const energyYaml = useMemo(
    () => generateYaml(energyTopics, 'eedc Energy-Daten senden', '60'),
    [energyTopics, generateYaml],
  )

  const copyYaml = (id: string, yaml: string) => {
    navigator.clipboard.writeText(yaml)
    setCopiedYaml(id)
    setTimeout(() => setCopiedYaml(null), 2000)
  }

  const liveCount = liveTopics.filter(t => entityMap[t.topic]?.trim()).length
  const energyCount = energyTopics.filter(t => entityMap[t.topic]?.trim()).length

  if (anlagen.length === 0) return null

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
      {/* Disclosure-Kopf (B15-Muster: ghost + w-full + justify-between + aria-expanded) */}
      <Button
        type="button" variant="ghost"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full justify-between p-5 text-left"
      >
        <div className="flex items-center gap-2">
          <Wand2 className="w-5 h-5 text-purple-500" />
          <h2 className="font-semibold text-gray-900 dark:text-white">HA Automation Generator</h2>
          <span className="text-xs text-gray-400 dark:text-gray-500">Home Assistant YAML erzeugen</span>
        </div>
        <ChevronDown className={`w-5 h-5 text-gray-400 dark:text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </Button>

      {open && (
        <div className="px-5 pb-5 space-y-6">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Ordne deine Home Assistant Sensoren den eedc-Topics zu.
            Am Ende erhältst du zwei fertige Automationen (Live + Energy) zum Kopieren.
          </p>

          {/* Anlage + Intervall */}
          <div className="flex flex-wrap items-center gap-4">
            {anlagen.length > 1 && (
              <div className="flex items-center gap-2">
                <label className="text-sm text-gray-600 dark:text-gray-400">Anlage:</label>
                <Select
                  steuer
                  value={selectedAnlageId != null ? String(selectedAnlageId) : ''}
                  onChange={(e) => {
                    setSelectedAnlageId(Number(e.target.value))
                    setEntityMap({})
                  }}
                  aria-label="Anlage wählen"
                  options={anlagen.map(a => ({ value: String(a.id), label: a.anlagenname || `Anlage ${a.id}` }))}
                />
              </div>
            )}
            <div className="flex items-center gap-2">
              <label className="text-sm text-gray-600 dark:text-gray-400">Live-Intervall:</label>
              <Select
                steuer
                value={interval}
                onChange={(e) => setInterval(e.target.value)}
                aria-label="Live-Intervall"
                options={[
                  { value: '5', label: 'Alle 5 Sekunden' },
                  { value: '10', label: 'Alle 10 Sekunden' },
                  { value: '30', label: 'Alle 30 Sekunden' },
                  { value: '60', label: 'Jede Minute' },
                ]}
              />
            </div>
          </div>

          {/* Live-Sensoren */}
          {liveTopics.length > 0 && (
            <TopicMappingSection
              title="Live-Sensoren"
              description="Echtzeit-Leistung in Watt — für das Live Dashboard"
              badge="live"
              topics={liveTopics}
              entityMap={entityMap}
              getPlaceholder={getPlaceholder}
              onUpdate={updateEntity}
            />
          )}

          {/* Energy-Sensoren */}
          {energyTopics.length > 0 && (
            <TopicMappingSection
              title="Energy-Sensoren"
              description="Zählerstände in kWh — für den Monatsabschluss"
              badge="energy"
              topics={energyTopics}
              entityMap={entityMap}
              getPlaceholder={getPlaceholder}
              onUpdate={updateEntity}
            />
          )}

          {/* Generiertes YAML */}
          {(liveCount > 0 || energyCount > 0) && (
            <div className="space-y-4 pt-2 border-t border-gray-200 dark:border-gray-700">
              <h3 className="font-medium text-gray-900 dark:text-white text-sm">
                Generierte Automationen
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Kopiere das YAML und füge es in Home Assistant ein:
                Einstellungen → Automatisierungen → ⋮ → YAML-Modus, oder in <code className="bg-gray-100 dark:bg-gray-900 px-1 rounded">automations.yaml</code>.
              </p>

              {liveYaml && (
                <YamlOutput
                  id="live"
                  title={`Live-Automation (${liveCount} Sensor${liveCount !== 1 ? 'en' : ''}, alle ${interval}s)`}
                  yaml={liveYaml}
                  copied={copiedYaml}
                  onCopy={copyYaml}
                />
              )}
              {energyYaml && (
                <YamlOutput
                  id="energy"
                  title={`Energy-Automation (${energyCount} Sensor${energyCount !== 1 ? 'en' : ''}, jede Minute)`}
                  yaml={energyYaml}
                  copied={copiedYaml}
                  onCopy={copyYaml}
                />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TopicMappingSection({ title, description, badge, topics, entityMap, getPlaceholder, onUpdate }: {
  title: string
  description: string
  badge: string
  topics: MqttTopic[]
  entityMap: Record<string, string>
  getPlaceholder: (t: MqttTopic) => string
  onUpdate: (topic: string, value: string) => void
}) {
  return (
    <div className="space-y-3">
      <div>
        <div className="flex items-center gap-2">
          <h3 className="font-medium text-gray-900 dark:text-white text-sm">{title}</h3>
          <span className={`text-xs px-1.5 py-0.5 rounded ${
            badge === 'live'
              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
              : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
          }`}>{badge}</span>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{description}</p>
      </div>
      <div className="space-y-2">
        {topics.map(t => (
          <div key={t.topic} className="flex items-center gap-2">
            <div className="w-40 shrink-0">
              <span className="text-sm text-gray-700 dark:text-gray-300 truncate block" title={t.label}>
                {t.label}
              </span>
            </div>
            <span className="text-gray-300 dark:text-gray-600 shrink-0">→</span>
            <div className="flex-1">
              <Input
                type="text"
                value={entityMap[t.topic] || ''}
                onChange={(e) => onUpdate(t.topic, e.target.value)}
                placeholder={getPlaceholder(t)}
                aria-label={`Entity für ${t.label}`}
                className="font-mono"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function YamlOutput({ id, title, yaml, copied, onCopy }: {
  id: string
  title: string
  yaml: string
  copied: string | null
  onCopy: (id: string, yaml: string) => void
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">{title}</span>
        <Button
          type="button" variant="ghost" size="sm"
          onClick={() => onCopy(id, yaml)}
        >
          {copied === id ? <Check className="w-3 h-3 mr-1 text-green-500" /> : <Copy className="w-3 h-3 mr-1" />}
          {copied === id ? 'Kopiert!' : 'Kopieren'}
        </Button>
      </div>
      <pre className="text-xs bg-gray-50 dark:bg-gray-900 p-3 rounded-lg overflow-x-auto text-gray-800 dark:text-gray-200 max-h-80 overflow-y-auto">
        <code>{yaml}</code>
      </pre>
    </div>
  )
}

/** Beispiel-Flows für andere Smarthome-Systeme (Node-RED, ioBroker, FHEM, openHAB) */
function AndereSystemeFlows({ topics, host }: { topics: MqttTopic[]; host: string }) {
  const [open, setOpen] = useState(false)
  const [copiedSnippet, setCopiedSnippet] = useState<string | null>(null)
  const [selectedIdx, setSelectedIdx] = useState(0)

  useEffect(() => {
    const invIdx = topics.findIndex(t => t.topic.includes('/inv/'))
    if (invIdx >= 0) setSelectedIdx(invIdx)
  }, [topics])

  const selected = topics[selectedIdx]
  const exampleTopic = selected?.topic || 'eedc/1/live/inv/1/leistung_w'
  const sensorId = selected ? labelToSensorId(selected.label) : 'pv_power'
  const aliasName = selected?.label.replace(/\s*\([^)]*\)\s*/g, '').trim() || 'PV-Leistung'

  const copySnippet = (id: string, text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedSnippet(id)
    setTimeout(() => setCopiedSnippet(null), 2000)
  }

  const snippets = [
    {
      id: 'nodered', label: 'Node-RED', code: `[
  {
    "id": "eedc_${sensorId}",
    "type": "mqtt out",
    "topic": "${exampleTopic}",
    "broker": "${host}",
    "retain": true,
    "name": "eedc ${aliasName}"
  }
]
// msg.payload mit dem Sensorwert befüllen (z.B. via Change- oder Function-Node)`,
    },
    {
      id: 'iobroker', label: 'ioBroker JavaScript', code: `// Datenpunkt anpassen ↓
const quellSensor = '0_userdata.0.${sensorId}';

on(quellSensor, (obj) => {
    sendTo('mqtt.0', 'publish', {
        topic: '${exampleTopic}',
        message: String(obj.state.val),
        retain: true
    });
});`,
    },
    {
      id: 'fhem', label: 'FHEM', code: `# Reading-Name anpassen ↓
define eedc_${sensorId} notify ${sensorId}:.* {\\
  fhem("set mqtt2 publish -r ${exampleTopic} " . ReadingsVal("${sensorId}","state","0"))\\
}`,
    },
    {
      id: 'openhab', label: 'openHAB', code: `rule "eedc ${aliasName} senden"
when
    Item ${sensorId} changed  // ← Item-Name anpassen
then
    val mqttActions = getActions("mqtt", "mqtt:broker:myBroker")
    mqttActions.publishMQTT("${exampleTopic}", ${sensorId}.state.toString, true)
end`,
    },
  ]

  if (topics.length === 0) return null

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
      <Button
        type="button" variant="ghost"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full justify-between p-5 text-left"
      >
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-gray-400 dark:text-gray-500" />
          <h2 className="font-semibold text-gray-900 dark:text-white">Andere Systeme</h2>
          <span className="text-xs text-gray-400 dark:text-gray-500">Node-RED, ioBroker, FHEM, openHAB</span>
        </div>
        <ChevronDown className={`w-5 h-5 text-gray-400 dark:text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </Button>

      {open && (
        <div className="px-5 pb-5 space-y-4">
          {topics.length > 0 && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
                Beispiel generieren für:
              </label>
              <Select
                value={String(selectedIdx)}
                onChange={(e) => setSelectedIdx(Number(e.target.value))}
                aria-label="Topic für Beispiel wählen"
                options={topics.map((t, i) => ({ value: String(i), label: t.label }))}
              />
            </div>
          )}

          <p className="text-sm text-gray-600 dark:text-gray-400">
            Kopiere den passenden Beispiel-Flow und ersetze den
            <span className="font-mono text-xs bg-gray-100 dark:bg-gray-900 px-1 rounded mx-1">Sensor-Namen</span>
            durch deinen eigenen. Wiederhole für jedes Topic.
          </p>

          {snippets.map((s) => (
            <div key={s.id} className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400">{s.label}</span>
                <Button
                  type="button" variant="ghost" size="sm"
                  onClick={() => copySnippet(s.id, s.code)}
                >
                  {copiedSnippet === s.id ? <Check className="w-3 h-3 mr-1 text-green-500" /> : <Copy className="w-3 h-3 mr-1" />}
                  {copiedSnippet === s.id ? 'Kopiert' : 'Kopieren'}
                </Button>
              </div>
              <pre className="text-xs bg-gray-50 dark:bg-gray-900 p-3 rounded-lg overflow-x-auto text-gray-800 dark:text-gray-200">
                <code>{s.code}</code>
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
