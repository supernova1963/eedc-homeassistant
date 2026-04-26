/**
 * ConnectorSetupWizard – Geräte-Connector einrichten
 *
 * 3-Schritt-Wizard zur direkten Verbindung mit Wechselrichtern über lokale REST-API.
 * Schritt 1: Verbindungsdaten eingeben + testen
 * Schritt 2: Gerät bestätigen + einrichten
 * Schritt 3: Status + manuelle Ablesung
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Cpu,
  ChevronLeft,
  ChevronRight,
  CheckCircle,
  Loader2,
  Wifi,
  WifiOff,
  Trash2,
  RefreshCw,
  Info,
} from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Alert from '../components/ui/Alert'
import { anlagenApi } from '../api/anlagen'
import { connectorApi } from '../api/connector'
import type {
  ConnectorInfo,
  ConnectionTestResult,
  ConnectorStatus,
  MeterSnapshot,
  FetchResult,
} from '../api/connector'
import type { Anlage } from '../types'

/** Connectors die read_live() implementieren und Echtzeit-Watt liefern können. */
const LIVE_CONNECTORS = new Set([
  'shelly_em',        // Shelly 3EM / Pro 3EM
  'opendtu',          // OpenDTU / AhoyDTU
  'fronius_solar_api', // Fronius Wechselrichter
  'sonnen_batterie',  // sonnenBatterie
  'go_echarger',      // go-eCharger Wallbox
])

function formatKwh(val: number | null | undefined): string {
  if (val == null) return '–'
  return val.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' kWh'
}

function formatDate(iso: string | undefined): string {
  if (!iso) return '–'
  try {
    return new Date(iso).toLocaleString('de-DE')
  } catch {
    return iso
  }
}

export default function ConnectorSetupWizard() {
  const navigate = useNavigate()

  // Wizard state
  const [currentStep, setCurrentStep] = useState(0)
  const [error, setError] = useState<string | null>(null)

  // Anlagen
  const [anlagen, setAnlagen] = useState<Anlage[]>([])
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)

  // Connectoren
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([])
  const [selectedConnectorId, setSelectedConnectorId] = useState<string>('')

  // Step 1: Verbindungsdaten
  const [host, setHost] = useState('')
  const [username, setUsername] = useState('User')
  const [password, setPassword] = useState('')
  const [isTesting, setIsTesting] = useState(false)
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null)

  // Step 2: Setup
  const [isSettingUp, setIsSettingUp] = useState(false)

  // Step 3: Status
  const [status, setStatus] = useState<ConnectorStatus | null>(null)
  const [isFetching, setIsFetching] = useState(false)
  const [fetchResult, setFetchResult] = useState<FetchResult | null>(null)
  const [isRemoving, setIsRemoving] = useState(false)

  // Initialisierung
  useEffect(() => {
    loadAnlagen()
    loadConnectors()
  }, [])

  // Wenn Anlage gewählt, prüfe ob Connector schon konfiguriert
  useEffect(() => {
    if (selectedAnlageId) {
      loadStatus(selectedAnlageId)
    }
  }, [selectedAnlageId])

  async function loadAnlagen() {
    try {
      const data = await anlagenApi.list()
      setAnlagen(data)
      if (data.length === 1) {
        setSelectedAnlageId(data[0].id)
      }
    } catch {
      setError('Fehler beim Laden der Anlagen')
    }
  }

  async function loadConnectors() {
    try {
      const data = await connectorApi.getConnectors()
      setConnectors(data)
      if (data.length > 0) {
        setSelectedConnectorId(data[0].id)
      }
    } catch {
      setError('Fehler beim Laden der Connectoren')
    }
  }

  async function loadStatus(anlageId: number) {
    try {
      const s = await connectorApi.getStatus(anlageId)
      setStatus(s)
      if (s.configured) {
        setCurrentStep(2) // Direkt zum Status
      }
    } catch {
      // Status nicht ladbar - ok
    }
  }

  // Step 1: Verbindung testen
  async function handleTest() {
    if (!host || !password) {
      setError('Bitte IP-Adresse und Passwort eingeben')
      return
    }

    setIsTesting(true)
    setError(null)
    setTestResult(null)

    try {
      const result = await connectorApi.testConnection(
        selectedConnectorId,
        host,
        username,
        password
      )
      setTestResult(result)

      if (result.erfolg) {
        setCurrentStep(1)
      } else {
        setError(result.fehler || 'Verbindungstest fehlgeschlagen')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Verbindungstest fehlgeschlagen')
    } finally {
      setIsTesting(false)
    }
  }

  // Step 2: Connector einrichten
  async function handleSetup() {
    if (!selectedAnlageId) {
      setError('Bitte eine Anlage auswählen')
      return
    }

    setIsSettingUp(true)
    setError(null)

    try {
      await connectorApi.setup(
        selectedAnlageId,
        selectedConnectorId,
        host,
        username,
        password
      )
      // Status neu laden
      await loadStatus(selectedAnlageId)
      setCurrentStep(2)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Einrichtung fehlgeschlagen')
    } finally {
      setIsSettingUp(false)
    }
  }

  // Step 3: Manuell ablesen
  async function handleFetch() {
    if (!selectedAnlageId) return

    setIsFetching(true)
    setError(null)
    setFetchResult(null)

    try {
      const result = await connectorApi.fetch(selectedAnlageId)
      setFetchResult(result)
      // Status aktualisieren
      await loadStatus(selectedAnlageId)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ablesung fehlgeschlagen')
    } finally {
      setIsFetching(false)
    }
  }

  // Connector entfernen
  async function handleRemove() {
    if (!selectedAnlageId) return
    if (!confirm('Connector-Konfiguration wirklich entfernen? Gespeicherte Snapshots gehen verloren.')) return

    setIsRemoving(true)
    setError(null)

    try {
      await connectorApi.remove(selectedAnlageId)
      setStatus(null)
      setTestResult(null)
      setFetchResult(null)
      setCurrentStep(0)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Entfernen fehlgeschlagen')
    } finally {
      setIsRemoving(false)
    }
  }

  const steps = ['Verbindung', 'Einrichten', 'Status']

  const selectedConnector = connectors.find(c => c.id === selectedConnectorId)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Cpu className="h-6 w-6 text-primary-600" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Geräte-Connector
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Direkte Verbindung zum Wechselrichter über lokale REST-API
          </p>
        </div>
      </div>

      {/* Stepper */}
      <div className="flex items-center justify-center gap-2">
        {steps.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <div
              className={`flex items-center justify-center w-8 h-8 rounded-full text-sm font-medium ${
                i < currentStep
                  ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
                  : i === currentStep
                    ? 'bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300'
                    : 'bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-500'
              }`}
            >
              {i < currentStep ? <CheckCircle className="h-5 w-5" /> : i + 1}
            </div>
            <span className={`text-sm ${
              i === currentStep ? 'font-medium text-gray-900 dark:text-white' : 'text-gray-500'
            }`}>
              {label}
            </span>
            {i < steps.length - 1 && (
              <div className={`w-12 h-0.5 mx-1 ${
                i < currentStep ? 'bg-green-300 dark:bg-green-700' : 'bg-gray-200 dark:bg-gray-700'
              }`} />
            )}
          </div>
        ))}
      </div>

      {/* Error */}
      {error && (
        <Alert type="error" onClose={() => setError(null)}>{error}</Alert>
      )}

      {/* Step 0: Verbindung */}
      {currentStep === 0 && (
        <Card>
          <div className="p-5">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Verbindung konfigurieren
            </h2>
            <div className="space-y-4">
              {/* Anlage */}
              {anlagen.length > 1 && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Anlage
                  </label>
                  <select
                    value={selectedAnlageId ?? ''}
                    onChange={e => setSelectedAnlageId(Number(e.target.value) || null)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  >
                    <option value="">Anlage wählen...</option>
                    {anlagen.map(a => (
                      <option key={a.id} value={a.id}>{a.anlagenname}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Connector-Typ */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Connector-Typ
                </label>
                <select
                  value={selectedConnectorId}
                  onChange={e => setSelectedConnectorId(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                >
                  {connectors.map(c => (
                    <option key={c.id} value={c.id}>{c.name}{!c.getestet ? ' (*)' : ''}</option>
                  ))}
                </select>
                {connectors.some(c => !c.getestet) && (
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    (*) Ungetestet – basiert auf Hersteller-Dokumentation, aber noch nicht mit echten
                    Gerätedaten verifiziert. Feedback willkommen!
                  </p>
                )}
              </div>

              {/* Live-Daten Info */}
              {selectedConnector && (
                LIVE_CONNECTORS.has(selectedConnector.id) ? (
                  <div className="flex items-start gap-2 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg text-sm text-green-700 dark:text-green-400">
                    <span className="shrink-0 mt-0.5">⚡</span>
                    <span>
                      <strong>Live-Daten:</strong> Dieser Connector liefert Echtzeit-Leistungswerte (Watt).
                      Bei aktiver MQTT-Verbindung erscheinen die Daten automatisch im Live-Dashboard und Energiefluss.
                    </span>
                  </div>
                ) : (
                  <div className="flex items-start gap-2 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm text-gray-500 dark:text-gray-400">
                    <span className="shrink-0 mt-0.5">📊</span>
                    <span>
                      <strong>Nur Zählerstände:</strong> Dieser Connector liest kumulative kWh-Werte.
                      Echtzeit-Leistungsdaten für das Live-Dashboard sind nicht verfügbar.
                    </span>
                  </div>
                )
              )}

              {/* Anleitung */}
              {selectedConnector && (
                <Alert type="info">
                  <div className="text-sm whitespace-pre-line">{selectedConnector.anleitung}</div>
                </Alert>
              )}

              {/* IP-Adresse */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  IP-Adresse / Hostname
                </label>
                <input
                  type="text"
                  value={host}
                  onChange={e => setHost(e.target.value)}
                  placeholder="z.B. 192.168.1.100"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400"
                />
              </div>

              {/* Benutzername */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Benutzername
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                />
              </div>

              {/* Passwort */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Passwort
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Geräte-Passwort"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400"
                />
              </div>
            </div>

            <div className="flex justify-end mt-6">
              <Button
                onClick={handleTest}
                disabled={isTesting || !host || !password}
              >
                {isTesting ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Teste Verbindung...</>
                ) : (
                  <><Wifi className="h-4 w-4 mr-2" /> Verbindung testen</>
                )}
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Step 1: Gerät bestätigen */}
      {currentStep === 1 && testResult && (
        <Card>
          <div className="p-5">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Gerät erkannt
            </h2>
            <div className="space-y-4">
              {/* Geräteinfo */}
              <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <CheckCircle className="h-5 w-5 text-green-600" />
                  <span className="font-medium text-green-800 dark:text-green-300">
                    Verbindung erfolgreich
                  </span>
                </div>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                  {testResult.geraet_name && (
                    <>
                      <dt className="text-gray-500 dark:text-gray-400">Gerätename</dt>
                      <dd className="font-medium text-gray-900 dark:text-white">{testResult.geraet_name}</dd>
                    </>
                  )}
                  {testResult.geraet_typ && (
                    <>
                      <dt className="text-gray-500 dark:text-gray-400">Typ</dt>
                      <dd className="font-medium text-gray-900 dark:text-white">{testResult.geraet_typ}</dd>
                    </>
                  )}
                  {testResult.seriennummer && (
                    <>
                      <dt className="text-gray-500 dark:text-gray-400">Seriennummer</dt>
                      <dd className="font-medium text-gray-900 dark:text-white">{testResult.seriennummer}</dd>
                    </>
                  )}
                  {testResult.firmware && (
                    <>
                      <dt className="text-gray-500 dark:text-gray-400">Firmware</dt>
                      <dd className="font-medium text-gray-900 dark:text-white">{testResult.firmware}</dd>
                    </>
                  )}
                </dl>
              </div>

              {/* Aktuelle Zählerstände */}
              {testResult.aktuelle_werte && (
                <div>
                  <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Aktuelle Zählerstände (kumulativ)
                  </h3>
                  <SnapshotTable snapshot={testResult.aktuelle_werte} />
                </div>
              )}

              {/* Verfügbare Sensoren */}
              {testResult.verfuegbare_sensoren.length > 0 && (
                <details className="text-sm">
                  <summary className="cursor-pointer text-gray-500 dark:text-gray-400 hover:text-gray-700">
                    {testResult.verfuegbare_sensoren.length} Sensoren verfügbar
                  </summary>
                  <div className="mt-2 max-h-40 overflow-y-auto text-xs font-mono bg-gray-50 dark:bg-gray-800 rounded p-2">
                    {testResult.verfuegbare_sensoren.map(s => (
                      <div key={s} className="text-gray-600 dark:text-gray-400">{s}</div>
                    ))}
                  </div>
                </details>
              )}

              {/* Anlage auswählen (falls noch nicht) */}
              {!selectedAnlageId && anlagen.length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Anlage für diesen Connector
                  </label>
                  <select
                    value={selectedAnlageId ?? ''}
                    onChange={e => setSelectedAnlageId(Number(e.target.value) || null)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  >
                    <option value="">Anlage wählen...</option>
                    {anlagen.map(a => (
                      <option key={a.id} value={a.id}>{a.anlagenname}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div className="flex justify-between mt-6">
              <Button variant="secondary" onClick={() => setCurrentStep(0)}>
                <ChevronLeft className="h-4 w-4 mr-1" /> Zurück
              </Button>
              <Button
                onClick={handleSetup}
                disabled={isSettingUp || !selectedAnlageId}
              >
                {isSettingUp ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Richte ein...</>
                ) : (
                  <>Connector einrichten <ChevronRight className="h-4 w-4 ml-1" /></>
                )}
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Step 2: Status & Ablesung */}
      {currentStep === 2 && status?.configured && (
        <div className="space-y-4">
          {/* Connector-Info */}
          <Card>
            <div className="p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                  <Wifi className="h-5 w-5 text-green-600" />
                  Connector aktiv
                </h2>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleRemove}
                  disabled={isRemoving}
                >
                  {isRemoving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <><Trash2 className="h-4 w-4 mr-1" /> Entfernen</>
                  )}
                </Button>
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <dt className="text-gray-500 dark:text-gray-400">Gerät</dt>
                <dd className="font-medium text-gray-900 dark:text-white">
                  {status.geraet_name || '–'}
                </dd>
                <dt className="text-gray-500 dark:text-gray-400">Host</dt>
                <dd className="font-medium text-gray-900 dark:text-white">{status.host}</dd>
                <dt className="text-gray-500 dark:text-gray-400">Seriennummer</dt>
                <dd className="font-medium text-gray-900 dark:text-white">
                  {status.seriennummer || '–'}
                </dd>
                <dt className="text-gray-500 dark:text-gray-400">Letzte Ablesung</dt>
                <dd className="font-medium text-gray-900 dark:text-white">
                  {formatDate(status.last_fetch)}
                </dd>
                <dt className="text-gray-500 dark:text-gray-400">Snapshots gespeichert</dt>
                <dd className="font-medium text-gray-900 dark:text-white">
                  {status.snapshot_count ?? 0}
                </dd>
              </dl>
            </div>
          </Card>

          {/* Letzte Werte */}
          {status.latest_snapshot && (
            <Card>
              <div className="p-5">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                  Letzte Zählerstände
                </h2>
                <SnapshotTable snapshot={status.latest_snapshot} />
              </div>
            </Card>
          )}

          {/* Manuelle Ablesung */}
          <Card>
            <div className="p-5">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                Zählerstand ablesen
              </h2>
              <div className="space-y-3">
                <div className="flex items-start gap-2 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                  <Info className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
                  <span className="text-sm text-blue-700 dark:text-blue-300">
                    Liest die aktuellen kumulativen Zählerstände vom Wechselrichter und berechnet
                    die Differenz zum letzten gespeicherten Snapshot.
                  </span>
                </div>

                <Button onClick={handleFetch} disabled={isFetching}>
                  {isFetching ? (
                    <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Lese Zähler...</>
                  ) : (
                    <><RefreshCw className="h-4 w-4 mr-2" /> Jetzt ablesen</>
                  )}
                </Button>

                {/* Fetch-Ergebnis */}
                {fetchResult && (
                  <div className="mt-4 space-y-3">
                    <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Neue Ablesung ({formatDate(fetchResult.timestamp)})
                    </h4>
                    <SnapshotTable snapshot={fetchResult.snapshot} />

                    {fetchResult.differenz && Object.keys(fetchResult.differenz).length > 0 && (
                      <div>
                        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mt-3 mb-1">
                          Differenz seit letzter Ablesung
                        </h4>
                        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
                          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                            {Object.entries(fetchResult.differenz).map(([key, val]) => (
                              <div key={key} className="contents">
                                <dt className="text-gray-500 dark:text-gray-400">
                                  {fieldLabel(key)}
                                </dt>
                                <dd className="font-medium text-gray-900 dark:text-white">
                                  +{formatKwh(val)}
                                </dd>
                              </div>
                            ))}
                          </dl>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                <Button
                  variant="secondary"
                  onClick={() => navigate('/einstellungen/monatsdaten')}
                >
                  Zur Monatsübersicht
                </Button>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Fallback wenn Status nicht konfiguriert aber Step 2 */}
      {currentStep === 2 && status && !status.configured && (
        <Card>
          <div className="text-center py-8">
            <WifiOff className="h-12 w-12 mx-auto text-gray-400 mb-3" />
            <p className="text-gray-600 dark:text-gray-400">
              Kein Connector konfiguriert.
            </p>
            <Button className="mt-4" onClick={() => setCurrentStep(0)}>
              Connector einrichten
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}

// =============================================================================
// Hilfskomponenten
// =============================================================================

function fieldLabel(key: string): string {
  const labels: Record<string, string> = {
    pv_erzeugung_kwh: 'PV-Erzeugung',
    einspeisung_kwh: 'Einspeisung',
    netzbezug_kwh: 'Netzbezug',
    batterie_ladung_kwh: 'Batterie Ladung',
    batterie_entladung_kwh: 'Batterie Entladung',
  }
  return labels[key] || key
}

function SnapshotTable({ snapshot }: { snapshot: MeterSnapshot }) {
  const fields = [
    { key: 'pv_erzeugung_kwh', label: 'PV-Erzeugung' },
    { key: 'einspeisung_kwh', label: 'Einspeisung' },
    { key: 'netzbezug_kwh', label: 'Netzbezug' },
    { key: 'batterie_ladung_kwh', label: 'Batterie Ladung' },
    { key: 'batterie_entladung_kwh', label: 'Batterie Entladung' },
  ] as const

  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        {fields.map(({ key, label }) => {
          const val = snapshot[key]
          if (val == null) return null
          return (
            <div key={key} className="contents">
              <dt className="text-gray-500 dark:text-gray-400">{label}</dt>
              <dd className="font-medium text-gray-900 dark:text-white font-mono">
                {formatKwh(val)}
              </dd>
            </div>
          )
        })}
      </dl>
    </div>
  )
}
