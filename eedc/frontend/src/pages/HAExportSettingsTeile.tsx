/**
 * MQTT-Export — geteilte Teile (HA-Sensor-Export: REST-YAML + MQTT-Discovery +
 * Sensor-Übersicht + Günstig-Schwelle).
 *
 * EINE Code-Wahrheit für IST (`pages/HAExportSettings.tsx`, dünner Komposer) und
 * IA-V4 (Einstellungen-Katalog-Block „MQTT-Export", inline wie Strompreise/
 * Solarprognose — Gernot 2026-07-01). `haOnly` → im Standalone deaktiviert; der
 * V4-Block rendert nur mit HA-Integration. Der Aufrufer reicht die bereits
 * aufgelöste `anlageId` (+ die `anlage` für die Günstig-Schwelle), im Mehr-Anlagen-
 * Fall einen `kopfZusatz` (Anlage-Auswahl) und `onAnlageUpdated` (Refresh nach dem
 * Speichern der Günstig-Schwelle). Sensor-Werte bleiben `toLocaleString('de-DE',
 * {maximumFractionDigits: 2})` — bewusst (generische Multi-Einheit-Werte, festes
 * fmtZahl-NK unpassend; bereits de-DE, nicht vom Check geflaggt).
 *
 * Ermöglicht:
 * - REST API Export (YAML-Snippet für configuration.yaml)
 * - MQTT Discovery Export (native HA-Entitäten)
 * - Übersicht aller exportierbaren Sensoren mit Werten/Formeln
 */

import { useState, useEffect, type ReactNode } from 'react'
import {
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
import Icon from '@mdi/react'
import {
  mdiSolarPower,
  mdiSolarPowerVariant,
  mdiLightningBolt,
  mdiHomeLightningBolt,
  mdiHomeLightningBoltOutline,
  mdiHomeBattery,
  mdiTransmissionTowerExport,
  mdiTransmissionTowerImport,
  mdiPercent,
  mdiCashPlus,
  mdiCashCheck,
  mdiCash,
  mdiCashRefund,
  mdiPiggyBank,
  mdiMoleculeCo2,
  mdiChartLine,
  mdiCalendarClock,
  mdiCalendar,
  mdiCalendarMonth,
  mdiCalendarText,
  mdiCarElectric,
  mdiGauge,
  mdiFuel,
  mdiHeatPump,
  mdiBatterySync,
  mdiBatteryCheck,
  mdiCounter,
  mdiHelpCircleOutline
} from '@mdi/js'
import { haApi, anlagenApi } from '../api'
import { Button, Input, SegmentControl } from '../components/ui'

const MDI_ICON_MAP: Record<string, string> = {
  'mdi:solar-power': mdiSolarPower,
  'mdi:solar-power-variant': mdiSolarPowerVariant,
  'mdi:lightning-bolt': mdiLightningBolt,
  'mdi:home-lightning-bolt': mdiHomeLightningBolt,
  'mdi:home-lightning-bolt-outline': mdiHomeLightningBoltOutline,
  'mdi:home-battery': mdiHomeBattery,
  'mdi:transmission-tower-export': mdiTransmissionTowerExport,
  'mdi:transmission-tower-import': mdiTransmissionTowerImport,
  'mdi:percent': mdiPercent,
  'mdi:cash-plus': mdiCashPlus,
  'mdi:cash-check': mdiCashCheck,
  'mdi:cash': mdiCash,
  'mdi:cash-refund': mdiCashRefund,
  'mdi:piggy-bank': mdiPiggyBank,
  'mdi:molecule-co2': mdiMoleculeCo2,
  'mdi:chart-line': mdiChartLine,
  'mdi:calendar-clock': mdiCalendarClock,
  'mdi:calendar': mdiCalendar,
  'mdi:calendar-month': mdiCalendarMonth,
  'mdi:calendar-text': mdiCalendarText,
  'mdi:car-electric': mdiCarElectric,
  'mdi:gauge': mdiGauge,
  'mdi:fuel': mdiFuel,
  'mdi:heat-pump': mdiHeatPump,
  'mdi:battery-sync': mdiBatterySync,
  'mdi:battery-check': mdiBatteryCheck,
  'mdi:counter': mdiCounter,
}

function MdiIcon({ name }: { name: string }) {
  const path = MDI_ICON_MAP[name] ?? mdiHelpCircleOutline
  return <Icon path={path} size={0.9} className="text-gray-600 dark:text-gray-300" />
}
import type {
  FullExportResponse,
  AnlageExport,
  SensorExportItem,
  MQTTTestResult,
  MQTTPublishResult,
  HAYamlSnippet,
  MQTTConfigFromAddon
} from '../api/ha'
import type { Anlage } from '../types'
import { TYP_LABELS, INVESTITION_TYP_ORDER } from '../lib/constants'

/**
 * Volle MQTT-Export-Verwaltung. Wird von der IST-Seite (V3-Hülle) und dem V4-
 * Integration-Block geteilt. `anlageId` ist bereits aufgelöst; `anlage` liefert die
 * Günstig-Schwelle; `kopfZusatz` (z. B. Anlage-Auswahl) wandert in die Kopfleiste;
 * `onAnlageUpdated` triggert den Anlage-Refresh nach dem Speichern der Schwelle.
 */
export function MqttExportVerwaltung({ anlageId, anlage, kopfZusatz, onAnlageUpdated }: {
  anlageId: number
  anlage?: Anlage
  kopfZusatz?: ReactNode
  onAnlageUpdated?: () => void
}) {
  // State
  const [exportData, setExportData] = useState<FullExportResponse | null>(null)
  const [anlageExport, setAnlageExport] = useState<AnlageExport | null>(null)
  const [yamlSnippet, setYamlSnippet] = useState<HAYamlSnippet | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // MQTT State - wird aus Add-on Config geladen
  const [mqttConfig, setMqttConfig] = useState<MQTTConfigFromAddon | null>(null)
  const [mqttHost, setMqttHost] = useState('core-mosquitto')
  const [mqttPort, setMqttPort] = useState(1883)
  const [mqttUser, setMqttUser] = useState('')
  const [mqttPassword, setMqttPassword] = useState('')
  const [mqttTestResult, setMqttTestResult] = useState<MQTTTestResult | null>(null)
  const [mqttPublishResult, setMqttPublishResult] = useState<MQTTPublishResult | null>(null)
  const [mqttTesting, setMqttTesting] = useState(false)
  const [mqttPublishing, setMqttPublishing] = useState(false)
  const [mqttRemoving, setMqttRemoving] = useState(false)

  // Günstig-Schwelle der Börsenpreis-Sensoren (pro Anlage, % unter Ø ohne 3 Peaks)
  const [guenstigProzent, setGuenstigProzent] = useState<string>('10')
  const [guenstigSaving, setGuenstigSaving] = useState(false)
  const [guenstigSaved, setGuenstigSaved] = useState(false)

  // UI State
  const [activeTab, setActiveTab] = useState<'rest' | 'mqtt'>('mqtt')
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(['energie', 'finanzen']))
  const [copiedYaml, setCopiedYaml] = useState(false)

  // Daten laden
  const loadData = async () => {
    try {
      setLoading(true)
      setError(null)

      const [exportDataResult, mqttConfigResult] = await Promise.all([
        haApi.getExportSensors(),
        haApi.getMqttConfig().catch(() => null)  // Optional, falls Endpoint nicht erreichbar
      ])

      setExportData(exportDataResult)

      // MQTT-Config aus Add-on Optionen laden
      if (mqttConfigResult) {
        setMqttConfig(mqttConfigResult)
        setMqttHost(mqttConfigResult.host)
        setMqttPort(mqttConfigResult.port)
        setMqttUser(mqttConfigResult.username)
        // Passwort nicht übernehmen (ist maskiert), Benutzer muss es neu eingeben
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
      // Fehler stillschweigend ignoriert
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    if (anlageId) {
      loadAnlageData(anlageId)
    }
  }, [anlageId])

  // Günstig-Schwelle aus der gewählten Anlage übernehmen
  useEffect(() => {
    setGuenstigProzent(
      anlage?.guenstig_schwelle_prozent != null
        ? String(anlage.guenstig_schwelle_prozent)
        : '10'
    )
    setGuenstigSaved(false)
  }, [anlageId, anlage])

  const saveGuenstigSchwelle = async () => {
    if (!anlageId) return
    const wert = parseFloat(guenstigProzent.replace(',', '.'))
    if (isNaN(wert) || wert < 0 || wert > 50) {
      setError('Die Günstig-Schwelle muss zwischen 0 und 50 % liegen.')
      return
    }
    setGuenstigSaving(true)
    setError(null)
    try {
      await anlagenApi.update(anlageId, {
        guenstig_schwelle_prozent: wert,
      })
      onAnlageUpdated?.()
      setGuenstigSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Speichern fehlgeschlagen')
    } finally {
      setGuenstigSaving(false)
    }
  }

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
    if (!anlageId) return
    setMqttPublishing(true)
    setMqttPublishResult(null)
    try {
      const result = await haApi.publishMqtt(anlageId, {
        host: mqttHost,
        port: mqttPort,
        username: mqttUser || undefined,
        password: mqttPassword || undefined
      })
      setMqttPublishResult(result)
    } catch (e) {
      setMqttPublishResult({
        message: e instanceof Error ? e.message : 'Fehler beim Publizieren',
        anlage_id: anlageId,
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
    if (!anlageId) return
    if (!confirm('Alle eedc-Sensoren für diese Anlage aus Home Assistant entfernen?')) return

    setMqttRemoving(true)
    try {
      await haApi.removeMqtt(anlageId, {
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

  // #179: alle Categories aus backend/services/ha_sensors_export.py:SensorCategory
  // mit deutschen Labels + sprechenden Icons. Fehlende Mappings landeten vorher
  // als roher Enum-Wert mit Pin-Default-Icon (detLAN-Bild: quote/anlage/
  // investition/speicher/status).
  const categoryLabels: Record<string, string> = {
    anlage: 'Anlage',
    energie: 'Energie',
    quote: 'Quoten',
    finanzen: 'Finanzen',
    umwelt: 'Umwelt',
    investition: 'Investition',
    waermepumpe: 'Wärmepumpe',
    speicher: 'Speicher',
    e_auto: 'E-Auto',
    wallbox: 'Wallbox',
    status: 'Status',
    // Defensive Fallbacks fuer aelteren Backend-Stand
    autarkie: 'Autarkie & Eigenverbrauch',
    performance: 'Performance',
    sonstige: 'Sonstige',
  }

  const categoryIcons: Record<string, string> = {
    anlage: '🏠',
    energie: '⚡',
    quote: '📊',
    finanzen: '💰',
    umwelt: '🌱',
    investition: '💼',
    waermepumpe: '🔥',
    speicher: '🔋',
    e_auto: '🚗',
    wallbox: '🔌',
    status: '⚙️',
    autarkie: '🏠',
    performance: '📊',
    sonstige: '📌',
  }

  // Anzeige-Reihenfolge — detLAN #186/4: Anlage → Energie → Speicher (früh, weil
  // wichtigster Speicher) → Investition + Komponenten-Aspekte → Finanzen → Quote →
  // Umwelt → Status (zuletzt). Komponenten-Reihenfolge konsistent zu
  // INVESTITION_TYP_ORDER (Wallbox → E-Auto → WP).
  const CATEGORY_ORDER = [
    'anlage', 'energie', 'speicher',
    'investition', 'wallbox', 'e_auto', 'waermepumpe',
    'finanzen', 'quote', 'umwelt',
    'autarkie', 'performance', 'sonstige',
    'status',
  ]
  const sortCategories = (entries: [string, SensorExportItem[]][]) =>
    [...entries].sort(([a], [b]) => {
      const ai = CATEGORY_ORDER.indexOf(a)
      const bi = CATEGORY_ORDER.indexOf(b)
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi)
    })

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-primary-500" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* #218 P11: Überschrift „HA-Sensor-Export" entfernt — passt nicht zum
          Sub-Tab „MQTT-Export". Erklärung liefert die Info-Box unten.
          #217: Refresh als Schaltfläche statt flach. */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">{kopfZusatz}</div>
        <Button
          variant="secondary"
          size="sm"
          onClick={loadData}
          disabled={loading}
          title="Aktualisieren"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Aktualisieren
        </Button>
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
            eedc kann berechnete Kennzahlen (Autarkie, Ersparnis, CO₂, ROI) als Sensoren an Home Assistant zurückgeben.
            Wähle zwischen REST API (YAML-Konfiguration) oder MQTT Discovery (native Entitäten).
          </p>
        </div>
      </div>

      {/* Günstig-Schwelle der Börsenpreis-Sensoren (gilt für MQTT + REST) */}
      <div className="card p-4">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="sm:flex-1">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Günstig-Schwelle der Börsenpreis-Sensoren
            </label>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Eine Stunde gilt als „günstig", wenn ihr Börsenpreis mindestens diesen Prozentsatz
              unter dem Tagesdurchschnitt (ohne die 3 teuersten Stunden) liegt. Standard: 10&nbsp;%.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Input
              type="number"
              min={0}
              max={50}
              step={0.5}
              value={guenstigProzent}
              onChange={(e) => {
                setGuenstigProzent(e.target.value)
                setGuenstigSaved(false)
              }}
              aria-label="Günstig-Schwelle in Prozent"
              className="w-24"
            />
            <span className="text-sm text-gray-500 dark:text-gray-400">%</span>
            <Button
              size="sm"
              onClick={saveGuenstigSchwelle}
              disabled={guenstigSaving || !anlageId}
            >
              {guenstigSaving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                'Speichern'
              )}
            </Button>
            {guenstigSaved && <CheckCircle className="h-4 w-4 text-green-500" />}
          </div>
        </div>
      </div>

      {/* Export-Weg-Umschalter (C2: SegmentControl-SoT statt Hand-Tab-Bar) */}
      <SegmentControl
        optionen={[
          { key: 'mqtt', label: 'MQTT Discovery (empfohlen)' },
          { key: 'rest', label: 'REST API (YAML)' },
        ]}
        value={activeTab}
        onChange={(key) => setActiveTab(key)}
        ariaLabel="Export-Weg wählen"
      />

      {/* MQTT Tab */}
      {activeTab === 'mqtt' && (
        <div className="space-y-6">
          {/* MQTT Konfiguration */}
          <div className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                MQTT-Broker Konfiguration
              </h2>
              {mqttConfig && (
                <span className="text-xs text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-900/30 px-2 py-1 rounded">
                  Aus App-Optionen geladen
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div>
                <Input
                  type="text"
                  label="Host"
                  value={mqttHost}
                  onChange={(e) => setMqttHost(e.target.value)}
                  placeholder="core-mosquitto"
                  hint="Bei HA-App: core-mosquitto"
                />
              </div>
              <div>
                <Input
                  type="number"
                  label="Port"
                  value={mqttPort}
                  onChange={(e) => setMqttPort(Number(e.target.value))}
                />
              </div>
              <div>
                <Input
                  type="text"
                  label="Benutzername (optional)"
                  value={mqttUser}
                  onChange={(e) => setMqttUser(e.target.value)}
                />
              </div>
              <div>
                <Input
                  type="password"
                  label="Passwort (optional)"
                  value={mqttPassword}
                  onChange={(e) => setMqttPassword(e.target.value)}
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
              <Button
                type="button"
                variant="secondary"
                onClick={testMqttConnection}
                loading={mqttTesting}
              >
                {!mqttTesting && <RefreshCw className="w-4 h-4 mr-2" />}
                Verbindung testen
              </Button>
              <Button
                type="button"
                onClick={publishMqttSensors}
                disabled={!anlageId}
                loading={mqttPublishing}
              >
                {!mqttPublishing && <Send className="w-4 h-4 mr-2" />}
                Sensoren publizieren
              </Button>
              <Button
                type="button"
                variant="danger"
                onClick={removeMqttSensors}
                disabled={!anlageId}
                loading={mqttRemoving}
              >
                {!mqttRemoving && <Trash2 className="w-4 h-4 mr-2" />}
                Sensoren entfernen
              </Button>
            </div>
          </div>

          <div className={`p-4 rounded-lg flex gap-3 ${
            mqttConfig?.auto_publish
              ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
              : 'bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800'
          }`}>
            {mqttConfig?.auto_publish ? (
              <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
            )}
            <div className={`text-sm ${
              mqttConfig?.auto_publish
                ? 'text-green-700 dark:text-green-300'
                : 'text-amber-700 dark:text-amber-300'
            }`}>
              <p className="font-medium mb-1">MQTT Discovery</p>
              <p>
                Die Sensoren erscheinen automatisch in Home Assistant unter <strong>Einstellungen → Geräte & Dienste → MQTT</strong>.
                {mqttConfig?.auto_publish ? (
                  <> Die automatische Publizierung ist aktiviert (alle {mqttConfig.publish_interval_minutes} Minuten).</>
                ) : (
                  <> Um die Werte aktuell zu halten, muss die Publizierung regelmäßig erfolgen (manuell oder via Automatisierung). Aktiviere <strong>auto_publish</strong> in den App-Optionen für automatische Updates.</>
                )}
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
                <Button type="button" variant="secondary" size="sm" onClick={copyYaml}>
                  {copiedYaml ? (
                    <>
                      <CheckCircle className="w-4 h-4 mr-1 text-green-500" />
                      Kopiert!
                    </>
                  ) : (
                    <>
                      <Copy className="w-4 h-4 mr-1" />
                      Kopieren
                    </>
                  )}
                </Button>
                <Button type="button" variant="secondary" size="sm" onClick={downloadYaml}>
                  <Download className="w-4 h-4 mr-1" />
                  Download
                </Button>
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
            {sortCategories(Object.entries(groupSensorsByCategory(anlageExport.sensors))).map(([category, sensors]) => (
              <div key={category} className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                <div className="bg-gray-50 dark:bg-gray-800">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => toggleCategory(category)}
                  aria-expanded={expandedCategories.has(category)}
                  className="w-full justify-between text-left"
                >
                  <span className="flex items-center gap-2">
                    <span>{categoryIcons[category] || '📌'}</span>
                    <span className="font-medium text-gray-900 dark:text-white">
                      {categoryLabels[category] || category}
                    </span>
                    <span className="text-sm text-gray-500">({sensors.length})</span>
                  </span>
                  {expandedCategories.has(category) ? (
                    <ChevronDown className="w-5 h-5 text-gray-400 dark:text-gray-500" />
                  ) : (
                    <ChevronRight className="w-5 h-5 text-gray-400 dark:text-gray-500" />
                  )}
                </Button>
                </div>

                {expandedCategories.has(category) && (
                  <div className="divide-y divide-gray-200 dark:divide-gray-700">
                    {sensors.map((sensor) => (
                      <div key={sensor.key} className="p-3 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <MdiIcon name={sensor.icon} />
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
            {/* #179: feste Reihenfolge analog Sensor-Zuordnung-Zusammenfassung,
                + overflow-hidden fuer Card-Ecken (vorher schnitt der Hover-
                Hintergrund von <summary> ueber den rounded-lg-Border). */}
            {[...exportData.investitionen]
              .sort((a, b) => {
                const ai = INVESTITION_TYP_ORDER.indexOf(a.typ as never)
                const bi = INVESTITION_TYP_ORDER.indexOf(b.typ as never)
                return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi)
              })
              .map((inv) => (
              <details key={inv.investition_id} className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                <summary className="p-3 bg-gray-50 dark:bg-gray-800 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700">
                  <span className="font-medium text-gray-900 dark:text-white">
                    {inv.bezeichnung}
                  </span>
                  <span className="ml-2 text-sm text-gray-500">
                    ({TYP_LABELS[inv.typ] ?? inv.typ} - {inv.sensors.length} Sensoren)
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
