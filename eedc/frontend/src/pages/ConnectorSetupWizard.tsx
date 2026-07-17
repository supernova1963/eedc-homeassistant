/**
 * ConnectorSetupWizard – Geräte-Connector einrichten
 *
 * 3-Schritt-Wizard zur direkten Verbindung mit Wechselrichtern über lokale REST-API.
 * Schritt 1: Verbindungsdaten eingeben + testen
 * Schritt 2: Gerät bestätigen + einrichten
 * Schritt 3: Status + manuelle Ablesung (= Ergebnis/Betrieb)
 *
 * IA-V4 (Style-Guide Teil D): SoT-Controls (Input/Select/Stepper/Alert),
 * Snapshot-/Zuordnungs-Helfer nach `components/connector/` ausgelagert. Overlay-
 * tauglich über {@link useWizardHost} (W2/W5); Entfernen über {@link ConfirmDialog}
 * statt nativem `confirm()` (M9).
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
} from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Alert from '../components/ui/Alert'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import Stepper from '../components/ui/Stepper'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import { useWizardHost } from '../v4/wizardHost'
import SnapshotTable from '../components/connector/SnapshotTable'
import InvestitionMapping from '../components/connector/InvestitionMapping'
import { formatKwh, formatDate, fieldLabel } from '../components/connector/connectorFormat'
import { anlagenApi } from '../api/anlagen'
import { connectorApi } from '../api/connector'
import { investitionenApi } from '../api/investitionen'
import type {
  ConnectorInfo,
  ConnectionTestResult,
  ConnectorStatus,
  FetchResult,
} from '../api/connector'
import type { Anlage, Investition } from '../types'

/** Connectors die read_live() implementieren und Echtzeit-Watt liefern können. */
const LIVE_CONNECTORS = new Set([
  'shelly_em',        // Shelly 3EM / Pro 3EM
  'opendtu',          // OpenDTU / AhoyDTU
  'fronius_solar_api', // Fronius Wechselrichter
  'sonnen_batterie',  // sonnenBatterie
  'go_echarger',      // go-eCharger Wallbox
])

export default function ConnectorSetupWizard() {
  const navigate = useNavigate()
  const wizardHost = useWizardHost()

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
  const [investitionen, setInvestitionen] = useState<Investition[]>([])
  const [isFetching, setIsFetching] = useState(false)
  const [fetchResult, setFetchResult] = useState<FetchResult | null>(null)
  const [isRemoving, setIsRemoving] = useState(false)
  const [removeDialogOffen, setRemoveDialogOffen] = useState(false)

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

  // W5: ungespeicherte Verbindungsdaten melden, solange nicht eingerichtet.
  const dirty = !status?.configured && (host !== '' || password !== '')
  useEffect(() => {
    wizardHost.setzeBlocker(dirty)
    return () => wizardHost.setzeBlocker(false)
  }, [dirty, wizardHost])

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
        try {
          setInvestitionen(await investitionenApi.list(anlageId, undefined, true))
        } catch {
          setInvestitionen([])
        }
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

  // Connector entfernen (M9: ConfirmDialog statt nativem confirm)
  async function handleRemove() {
    if (!selectedAnlageId) return

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
      setRemoveDialogOffen(false)
    }
  }

  // W3: Abbrechen — im Overlay Dirty-geschützt schließen, sonst zurück navigieren.
  function handleAbbrechen() {
    if (wizardHost.imOverlay) wizardHost.abbrechen()
    else navigate(-1)
  }

  // Terminal-„Zur Monatsübersicht" — im Overlay schließen (W2), sonst navigieren.
  function handleMonatsuebersicht() {
    if (wizardHost.imOverlay) wizardHost.schliessen()
    else navigate('/einstellungen/monatsdaten')
  }

  const steps = [
    { titel: 'Verbindung' },
    { titel: 'Einrichten' },
    { titel: 'Status' },
  ]

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

      {/* Stepper (W1) */}
      <Stepper schritte={steps} aktuell={currentStep} />

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
                <Select
                  label="Anlage"
                  value={selectedAnlageId ?? ''}
                  onChange={e => setSelectedAnlageId(Number(e.target.value) || null)}
                  placeholder="Anlage wählen…"
                  options={anlagen.map(a => ({ value: String(a.id), label: a.anlagenname }))}
                />
              )}

              {/* Connector-Typ */}
              <Select
                label="Connector-Typ"
                value={selectedConnectorId}
                onChange={e => setSelectedConnectorId(e.target.value)}
                options={connectors.map(c => ({ value: c.id, label: `${c.name}${!c.getestet ? ' (*)' : ''}` }))}
                hint={connectors.some(c => !c.getestet)
                  ? '(*) Ungetestet – basiert auf Hersteller-Dokumentation, aber noch nicht mit echten Gerätedaten verifiziert. Feedback willkommen!'
                  : undefined}
              />

              {/* Live-Daten Info */}
              {selectedConnector && (
                LIVE_CONNECTORS.has(selectedConnector.id) ? (
                  <Alert type="success">
                    <strong>Live-Daten:</strong> Dieser Connector liefert Echtzeit-Leistungswerte (Watt).
                    Bei aktiver MQTT-Verbindung erscheinen die Daten automatisch im Live-Dashboard und Energiefluss.
                  </Alert>
                ) : (
                  <Alert type="info">
                    <strong>Nur Zählerstände:</strong> Dieser Connector liest kumulative kWh-Werte.
                    Echtzeit-Leistungsdaten für das Live-Dashboard sind nicht verfügbar.
                  </Alert>
                )
              )}

              {/* Anleitung */}
              {selectedConnector && (
                <Alert type="info">
                  <div className="text-sm whitespace-pre-line">{selectedConnector.anleitung}</div>
                </Alert>
              )}

              {/* IP-Adresse */}
              <Input
                label="IP-Adresse / Hostname"
                value={host}
                onChange={e => setHost(e.target.value)}
                placeholder="z.B. 192.168.1.100"
              />

              {/* Benutzername */}
              <Input
                label="Benutzername"
                value={username}
                onChange={e => setUsername(e.target.value)}
              />

              {/* Passwort */}
              <Input
                label="Passwort"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Geräte-Passwort"
              />
            </div>

            {/* Navigation (W3) */}
            {/* D19-6-Kanon: [Abbrechen secondary][Primär] rechtsgebündelt. */}
            <div className="flex items-center justify-end gap-2 mt-6">
              <Button variant="secondary" onClick={handleAbbrechen}>
                Abbrechen
              </Button>
              <Button
                onClick={handleTest}
                disabled={isTesting || !host || !password}
              >
                {isTesting ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Teste Verbindung…</>
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
                <Select
                  label="Anlage für diesen Connector"
                  value={selectedAnlageId ?? ''}
                  onChange={e => setSelectedAnlageId(Number(e.target.value) || null)}
                  placeholder="Anlage wählen…"
                  options={anlagen.map(a => ({ value: String(a.id), label: a.anlagenname }))}
                />
              )}
            </div>

            {/* Navigation (W3) */}
            <div className="flex items-center justify-between mt-6">
              <Button variant="ghost" onClick={() => setCurrentStep(0)}>
                <ChevronLeft className="h-4 w-4 mr-1" /> Zurück
              </Button>
              <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={handleAbbrechen}>
                Abbrechen
              </Button>
              <Button
                onClick={handleSetup}
                disabled={isSettingUp || !selectedAnlageId}
              >
                {isSettingUp ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Richte ein…</>
                ) : (
                  <>Connector einrichten <ChevronRight className="h-4 w-4 ml-1" /></>
                )}
              </Button>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Step 2: Status & Ablesung (= Ergebnis/Betrieb) */}
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
                  onClick={() => setRemoveDialogOffen(true)}
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

          {/* Zuordnung zu Investitionen */}
          {selectedAnlageId && (
            <InvestitionMapping
              anlageId={selectedAnlageId}
              investitionen={investitionen}
              snapshot={status.latest_snapshot ?? null}
              initialMap={status.field_inv_map ?? {}}
              onSaved={(m) => setStatus({ ...status, field_inv_map: m })}
              onError={setError}
            />
          )}

          {/* Manuelle Ablesung */}
          <Card>
            <div className="p-5">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                Zählerstand ablesen
              </h2>
              <div className="space-y-3">
                <Alert type="info">
                  Liest die aktuellen kumulativen Zählerstände vom Wechselrichter und berechnet
                  die Differenz zum letzten gespeicherten Snapshot.
                </Alert>

                <Button onClick={handleFetch} disabled={isFetching}>
                  {isFetching ? (
                    <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Lese Zähler…</>
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
                <Button variant="secondary" onClick={handleMonatsuebersicht}>
                  {wizardHost.imOverlay ? 'Fertig' : 'Zur Monatsübersicht'}
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
            <WifiOff className="h-12 w-12 mx-auto text-gray-400 dark:text-gray-500 mb-3" />
            <p className="text-gray-600 dark:text-gray-400">
              Kein Connector konfiguriert.
            </p>
            <Button className="mt-4" onClick={() => setCurrentStep(0)}>
              Connector einrichten
            </Button>
          </div>
        </Card>
      )}

      {/* Entfernen-Bestätigung (M9) */}
      <ConfirmDialog
        isOpen={removeDialogOffen}
        onClose={() => setRemoveDialogOffen(false)}
        onConfirm={handleRemove}
        title="Connector entfernen?"
        message="Connector-Konfiguration wirklich entfernen? Gespeicherte Snapshots gehen verloren."
        confirmLabel="Entfernen"
        variant="danger"
      />
    </div>
  )
}
