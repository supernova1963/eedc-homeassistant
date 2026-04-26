/**
 * CloudImportWizard – Cloud-Import Wizard
 *
 * 4-Schritt-Wizard zum Importieren von historischen Energiedaten aus Cloud-APIs.
 * Schritt 1: Provider wählen, Credentials eingeben, Verbindung testen
 * Schritt 2: Zeitraum wählen, Daten abrufen
 * Schritt 3: Vorschau & Monatauswahl, Anlage wählen, Importieren
 * Schritt 4: Ergebnis
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Cloud,
  ChevronLeft,
  ChevronRight,
  CheckCircle,
  Search,
  Settings,
  Info,
  Wifi,
  WifiOff,
  Calendar,
  Save,
} from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Alert from '../components/ui/Alert'
import { anlagenApi } from '../api/anlagen'
import { cloudImportApi } from '../api/cloudImport'
import { portalImportApi } from '../api/portalImport'
import type { CloudProviderInfo, CloudTestResult, CloudPreviewResult } from '../api/cloudImport'
import type { ApplyResult } from '../api/portalImport'
import type { Anlage } from '../types'
import { MONAT_NAMEN } from '../lib/constants'

export default function CloudImportWizard() {
  const navigate = useNavigate()

  // Wizard state
  const [currentStep, setCurrentStep] = useState(0)
  const [error, setError] = useState<string | null>(null)

  // Step 1: Provider & Credentials
  const [providers, setProviders] = useState<CloudProviderInfo[]>([])
  const [selectedProviderId, setSelectedProviderId] = useState<string>('')
  const [credentials, setCredentials] = useState<Record<string, string>>({})
  const [isTesting, setIsTesting] = useState(false)
  const [testResult, setTestResult] = useState<CloudTestResult | null>(null)

  // Step 2: Zeitraum
  const now = new Date()
  const [startYear, setStartYear] = useState(now.getFullYear())
  const [startMonth, setStartMonth] = useState(1)
  const [endYear, setEndYear] = useState(now.getFullYear())
  const [endMonth, setEndMonth] = useState(now.getMonth() + 1)
  const [isFetching, setIsFetching] = useState(false)
  const [preview, setPreview] = useState<CloudPreviewResult | null>(null)

  // Step 3: Vorschau & Import
  const [anlagen, setAnlagen] = useState<Anlage[]>([])
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)
  const [selectedMonths, setSelectedMonths] = useState<Set<string>>(new Set())
  const [ueberschreiben, setUeberschreiben] = useState(false)
  const [isImporting, setIsImporting] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [result, setResult] = useState<ApplyResult | null>(null)

  // Load providers and anlagen
  useEffect(() => {
    cloudImportApi.getProviders().then(setProviders).catch(() => {})
    anlagenApi.list().then((list: Anlage[]) => {
      setAnlagen(list)
      if (list.length === 1) setSelectedAnlageId(list[0].id)
    }).catch(() => {})
  }, [])

  const selectedProvider = providers.find((p) => p.id === selectedProviderId)

  // Initialize credential fields when provider changes
  useEffect(() => {
    if (selectedProvider) {
      const initial: Record<string, string> = {}
      for (const field of selectedProvider.credential_fields) {
        initial[field.id] = credentials[field.id] || (field.type === 'select' && field.options.length > 0 ? field.options[0].value : '')
      }
      setCredentials(initial)
    }
    setTestResult(null)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProviderId])

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleTest = useCallback(async () => {
    if (!selectedProviderId) return
    setIsTesting(true)
    setError(null)
    setTestResult(null)
    try {
      const result = await cloudImportApi.testConnection(selectedProviderId, credentials)
      setTestResult(result)
      if (!result.erfolg) {
        setError(result.fehler || 'Verbindungstest fehlgeschlagen')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Verbindungstest fehlgeschlagen')
    } finally {
      setIsTesting(false)
    }
  }, [selectedProviderId, credentials])

  const handleFetch = useCallback(async () => {
    if (!selectedProviderId) return
    setIsFetching(true)
    setError(null)
    try {
      const result = await cloudImportApi.fetchPreview(
        selectedProviderId, credentials,
        startYear, startMonth, endYear, endMonth
      )
      setPreview(result)
      // Alle Monate auswählen
      const all = new Set(result.monate.map((m) => `${m.jahr}-${m.monat}`))
      setSelectedMonths(all)
      setCurrentStep(2)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Datenabruf fehlgeschlagen')
    } finally {
      setIsFetching(false)
    }
  }, [selectedProviderId, credentials, startYear, startMonth, endYear, endMonth])

  const toggleMonth = useCallback((key: string) => {
    setSelectedMonths((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const toggleAll = useCallback(() => {
    if (!preview) return
    setSelectedMonths((prev) => {
      if (prev.size === preview.monate.length) return new Set()
      return new Set(preview.monate.map((m) => `${m.jahr}-${m.monat}`))
    })
  }, [preview])

  const handleImport = useCallback(async () => {
    if (!preview || !selectedAnlageId || selectedMonths.size === 0) return
    setIsImporting(true)
    setError(null)
    try {
      const monate = preview.monate.filter((m) => selectedMonths.has(`${m.jahr}-${m.monat}`))
      const importResult = await portalImportApi.apply(
        selectedAnlageId, monate, ueberschreiben, 'cloud_import'
      )
      setResult(importResult)
      setCurrentStep(3)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import fehlgeschlagen')
    } finally {
      setIsImporting(false)
    }
  }, [preview, selectedAnlageId, selectedMonths, ueberschreiben])

  const handleSaveCredentials = useCallback(async () => {
    if (!selectedAnlageId || !selectedProviderId) return
    setIsSaving(true)
    try {
      await cloudImportApi.saveCredentials(selectedAnlageId, selectedProviderId, credentials)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Speichern fehlgeschlagen')
    } finally {
      setIsSaving(false)
    }
  }, [selectedAnlageId, selectedProviderId, credentials])

  // ── Render ─────────────────────────────────────────────────────────────────

  const steps = [
    { title: 'Verbinden', icon: <Settings className="w-4 h-4" /> },
    { title: 'Zeitraum', icon: <Calendar className="w-4 h-4" /> },
    { title: 'Vorschau', icon: <Search className="w-4 h-4" /> },
    { title: 'Ergebnis', icon: <CheckCircle className="w-4 h-4" /> },
  ]

  // Year range for selects
  const yearOptions: number[] = []
  for (let y = now.getFullYear() - 5; y <= now.getFullYear(); y++) {
    yearOptions.push(y)
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Cloud className="w-6 h-6 text-primary-500" />
          Cloud-Import
        </h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          Historische Energiedaten aus Hersteller-Cloud-APIs importieren
        </p>
      </div>

      {/* Stepper */}
      <div className="flex items-center gap-2 mb-6">
        {steps.map((step, idx) => (
          <div key={idx} className="flex items-center gap-2">
            {idx > 0 && (
              <div className={`h-px w-8 ${idx <= currentStep ? 'bg-primary-500' : 'bg-gray-300 dark:bg-gray-600'}`} />
            )}
            <div
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium
                ${idx === currentStep
                  ? 'bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300'
                  : idx < currentStep
                    ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
                    : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
                }`}
            >
              {step.icon}
              {step.title}
            </div>
          </div>
        ))}
      </div>

      {error && (
        <Alert type="error" title="Fehler" onClose={() => setError(null)} className="mb-4">
          {error}
        </Alert>
      )}

      {/* Step 1: Provider & Credentials */}
      {currentStep === 0 && (
        <div className="space-y-6">
          {/* Provider-Auswahl */}
          <Card>
            <div className="p-5">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                Cloud-Provider wählen
              </h2>
              <select
                value={selectedProviderId}
                onChange={(e) => setSelectedProviderId(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white
                  dark:bg-gray-700 dark:border-gray-600 dark:text-white
                  focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">Provider wählen...</option>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.hersteller}){!p.getestet ? ' (*)' : ''}
                  </option>
                ))}
              </select>

              {providers.some((p) => !p.getestet) && (
                <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                  (*) Ungetestet – basiert auf Hersteller-Dokumentation, aber noch nicht mit echten
                  Gerätedaten verifiziert. Feedback willkommen!
                </p>
              )}

              {selectedProvider && (
                <div className="mt-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                  <div className="flex items-start gap-2">
                    <Info className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
                    <div className="text-sm text-blue-700 dark:text-blue-300">
                      <p className="font-medium mb-1">{selectedProvider.beschreibung}</p>
                      <p className="text-blue-600 dark:text-blue-400 whitespace-pre-line">
                        {selectedProvider.anleitung}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </Card>

          {/* Credentials-Eingabe */}
          {selectedProvider && (
            <Card>
              <div className="p-5">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                  Zugangsdaten
                </h2>
                <div className="space-y-4">
                  {selectedProvider.credential_fields.map((field) => (
                    <div key={field.id}>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {field.label}
                        {field.required && <span className="text-red-500 ml-1">*</span>}
                      </label>
                      {field.type === 'select' ? (
                        <select
                          value={credentials[field.id] || ''}
                          onChange={(e) => setCredentials({ ...credentials, [field.id]: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white
                            dark:bg-gray-700 dark:border-gray-600 dark:text-white
                            focus:ring-2 focus:ring-primary-500"
                        >
                          {field.options.map((opt) => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type={field.type === 'password' ? 'password' : 'text'}
                          value={credentials[field.id] || ''}
                          onChange={(e) => setCredentials({ ...credentials, [field.id]: e.target.value })}
                          placeholder={field.placeholder}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white
                            dark:bg-gray-700 dark:border-gray-600 dark:text-white
                            focus:ring-2 focus:ring-primary-500"
                        />
                      )}
                    </div>
                  ))}
                </div>

                {/* Test-Button */}
                <div className="mt-5 flex items-center gap-3">
                  <Button
                    variant="primary"
                    onClick={handleTest}
                    loading={isTesting}
                    disabled={!selectedProvider.credential_fields.every(
                      (f) => !f.required || credentials[f.id]
                    )}
                  >
                    {isTesting ? 'Teste...' : 'Verbindung testen'}
                  </Button>

                  {testResult && (
                    <div className={`flex items-center gap-2 text-sm ${testResult.erfolg ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                      {testResult.erfolg ? (
                        <Wifi className="w-4 h-4" />
                      ) : (
                        <WifiOff className="w-4 h-4" />
                      )}
                      {testResult.erfolg ? 'Verbindung erfolgreich' : 'Verbindung fehlgeschlagen'}
                    </div>
                  )}
                </div>

                {/* Test-Ergebnis */}
                {testResult?.erfolg && (
                  <div className="mt-4 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg text-sm text-green-700 dark:text-green-300">
                    <div className="grid grid-cols-2 gap-2">
                      {testResult.geraet_name && (
                        <><span className="text-green-600 dark:text-green-400">Gerät:</span> <span>{testResult.geraet_name}</span></>
                      )}
                      {testResult.geraet_typ && (
                        <><span className="text-green-600 dark:text-green-400">Typ:</span> <span>{testResult.geraet_typ}</span></>
                      )}
                      {testResult.seriennummer && (
                        <><span className="text-green-600 dark:text-green-400">SN:</span> <span>{testResult.seriennummer}</span></>
                      )}
                      {testResult.verfuegbare_daten && (
                        <><span className="text-green-600 dark:text-green-400">Status:</span> <span>{testResult.verfuegbare_daten}</span></>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* Weiter-Button */}
          {testResult?.erfolg && (
            <div className="flex justify-end">
              <Button
                variant="primary"
                onClick={() => setCurrentStep(1)}
              >
                Weiter
                <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Step 2: Zeitraum */}
      {currentStep === 1 && (
        <div className="space-y-6">
          <Card>
            <div className="p-5">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Zeitraum wählen
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                {/* Von */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Von
                  </label>
                  <div className="flex gap-2">
                    <select
                      value={startMonth}
                      onChange={(e) => setStartMonth(Number(e.target.value))}
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg bg-white
                        dark:bg-gray-700 dark:border-gray-600 dark:text-white
                        focus:ring-2 focus:ring-primary-500"
                    >
                      {MONAT_NAMEN.slice(1).map((name, idx) => (
                        <option key={idx + 1} value={idx + 1}>{name}</option>
                      ))}
                    </select>
                    <select
                      value={startYear}
                      onChange={(e) => setStartYear(Number(e.target.value))}
                      className="w-24 px-3 py-2 border border-gray-300 rounded-lg bg-white
                        dark:bg-gray-700 dark:border-gray-600 dark:text-white
                        focus:ring-2 focus:ring-primary-500"
                    >
                      {yearOptions.map((y) => (
                        <option key={y} value={y}>{y}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Bis */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Bis
                  </label>
                  <div className="flex gap-2">
                    <select
                      value={endMonth}
                      onChange={(e) => setEndMonth(Number(e.target.value))}
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg bg-white
                        dark:bg-gray-700 dark:border-gray-600 dark:text-white
                        focus:ring-2 focus:ring-primary-500"
                    >
                      {MONAT_NAMEN.slice(1).map((name, idx) => (
                        <option key={idx + 1} value={idx + 1}>{name}</option>
                      ))}
                    </select>
                    <select
                      value={endYear}
                      onChange={(e) => setEndYear(Number(e.target.value))}
                      className="w-24 px-3 py-2 border border-gray-300 rounded-lg bg-white
                        dark:bg-gray-700 dark:border-gray-600 dark:text-white
                        focus:ring-2 focus:ring-primary-500"
                    >
                      {yearOptions.map((y) => (
                        <option key={y} value={y}>{y}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <Alert type="info" className="mt-4">
                <p className="text-sm">
                  Die Cloud-API wird pro Woche abgefragt. Bei längeren Zeiträumen kann der Abruf
                  mehrere Minuten dauern.
                </p>
              </Alert>
            </div>
          </Card>

          {/* Navigation */}
          <div className="flex items-center justify-between">
            <Button
              variant="ghost"
              onClick={() => setCurrentStep(0)}
            >
              <ChevronLeft className="w-4 h-4 mr-1" />
              Zurück
            </Button>
            <Button
              variant="primary"
              onClick={handleFetch}
              loading={isFetching}
              disabled={(startYear * 100 + startMonth) > (endYear * 100 + endMonth)}
            >
              {isFetching ? 'Daten werden abgerufen...' : 'Daten abrufen'}
              {!isFetching && <ChevronRight className="w-4 h-4 ml-1" />}
            </Button>
          </div>
        </div>
      )}

      {/* Step 3: Vorschau & Import */}
      {currentStep === 2 && preview && (
        <div className="space-y-4">
          <Alert type="info">
            <strong>{preview.provider.name}</strong> – {preview.anzahl_monate} Monate abgerufen
          </Alert>

          {/* Anlage-Auswahl */}
          <Card>
            <div className="p-5">
              <div className="flex flex-wrap items-end gap-4">
                <div className="flex-1 min-w-[200px]">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Ziel-Anlage
                  </label>
                  <select
                    value={selectedAnlageId ?? ''}
                    onChange={(e) => setSelectedAnlageId(Number(e.target.value) || null)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white
                      dark:bg-gray-700 dark:border-gray-600 dark:text-white
                      focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">Anlage wählen...</option>
                    {anlagen.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.anlagenname} ({a.leistung_kwp} kWp)
                      </option>
                    ))}
                  </select>
                </div>
                <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 pb-2">
                  <input
                    type="checkbox"
                    checked={ueberschreiben}
                    onChange={(e) => setUeberschreiben(e.target.checked)}
                    className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                  />
                  Bestehende Monate überschreiben
                </label>
              </div>
            </div>
          </Card>

          {/* Monatsdaten-Tabelle */}
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="px-4 py-3 text-left">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedMonths.size === preview.monate.length}
                          onChange={toggleAll}
                          className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                        />
                        <span className="font-medium text-gray-700 dark:text-gray-300">Monat</span>
                      </label>
                    </th>
                    <th className="px-4 py-3 text-right font-medium text-gray-700 dark:text-gray-300">PV kWh</th>
                    <th className="px-4 py-3 text-right font-medium text-gray-700 dark:text-gray-300">Einsp. kWh</th>
                    <th className="px-4 py-3 text-right font-medium text-gray-700 dark:text-gray-300">Bezug kWh</th>
                    <th className="px-4 py-3 text-right font-medium text-gray-700 dark:text-gray-300">Bat. Lad.</th>
                    <th className="px-4 py-3 text-right font-medium text-gray-700 dark:text-gray-300">Bat. Entl.</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.monate.map((m) => {
                    const key = `${m.jahr}-${m.monat}`
                    const selected = selectedMonths.has(key)
                    return (
                      <tr
                        key={key}
                        className={`border-b border-gray-100 dark:border-gray-800 cursor-pointer
                          ${selected ? 'bg-white dark:bg-gray-900' : 'bg-gray-50 dark:bg-gray-800/50 opacity-50'}`}
                        onClick={() => toggleMonth(key)}
                      >
                        <td className="px-4 py-2.5">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={() => toggleMonth(key)}
                              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                            />
                            <span className="text-gray-900 dark:text-white">
                              {MONAT_NAMEN[m.monat]} {m.jahr}
                            </span>
                          </label>
                        </td>
                        <td className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">
                          {m.pv_erzeugung_kwh?.toFixed(1) ?? '–'}
                        </td>
                        <td className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">
                          {m.einspeisung_kwh?.toFixed(1) ?? '–'}
                        </td>
                        <td className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">
                          {m.netzbezug_kwh?.toFixed(1) ?? '–'}
                        </td>
                        <td className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">
                          {m.batterie_ladung_kwh?.toFixed(1) ?? '–'}
                        </td>
                        <td className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">
                          {m.batterie_entladung_kwh?.toFixed(1) ?? '–'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Navigation */}
          <div className="flex items-center justify-between">
            <Button
              variant="ghost"
              onClick={() => { setCurrentStep(1); setPreview(null) }}
            >
              <ChevronLeft className="w-4 h-4 mr-1" />
              Zurück
            </Button>
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-500 dark:text-gray-400">
                {selectedMonths.size} von {preview.monate.length} Monaten
              </span>
              <Button
                variant="primary"
                onClick={handleImport}
                loading={isImporting}
                disabled={selectedMonths.size === 0 || !selectedAnlageId}
              >
                {isImporting ? 'Importiere...' : `${selectedMonths.size} Monate importieren`}
                {!isImporting && <ChevronRight className="w-4 h-4 ml-1" />}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Step 4: Ergebnis */}
      {currentStep === 3 && result && (
        <div className="space-y-4">
          <Alert type={result.erfolg ? 'success' : 'warning'} title={result.erfolg ? 'Import erfolgreich' : 'Import mit Hinweisen'}>
            <div className="space-y-1">
              <p>{result.importiert} Monate importiert</p>
              {result.uebersprungen > 0 && (
                <p>{result.uebersprungen} Monate übersprungen (bereits vorhanden)</p>
              )}
            </div>
          </Alert>

          {result.warnungen.length > 0 && (
            <Alert type="info" title="Hinweise">
              <ul className="list-disc list-inside space-y-1">
                {result.warnungen.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </Alert>
          )}

          {result.fehler.length > 0 && (
            <Alert type="error" title="Fehler">
              <ul className="list-disc list-inside space-y-1">
                {result.fehler.map((f, i) => <li key={i}>{f}</li>)}
              </ul>
            </Alert>
          )}

          {/* Credentials speichern */}
          {result.erfolg && selectedAnlageId && (
            <Card>
              <div className="p-5">
                <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Zugangsdaten für spätere Imports speichern?
                </h3>
                <div className="flex items-center gap-3">
                  <Button
                    variant="secondary"
                    onClick={handleSaveCredentials}
                    loading={isSaving}
                    size="sm"
                  >
                    <Save className="w-4 h-4 mr-1" />
                    {isSaving ? 'Speichere...' : 'Credentials speichern'}
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {result.erfolg && (
            <Alert type="info" title="Nächster Schritt: Monatsabschluss">
              <p>
                Der Cloud-Import erfasst PV-Erzeugung, Einspeisung, Netzbezug und Batterie-Daten.
                Für einen vollständigen Monatsabschluss müssen ggf. noch weitere Daten ergänzt werden
                (z.B. Wallbox, Wärmepumpe, E-Auto).
              </p>
            </Alert>
          )}

          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              onClick={() => {
                setCurrentStep(0)
                setPreview(null)
                setResult(null)
                setError(null)
                setTestResult(null)
              }}
            >
              <Cloud className="w-4 h-4 mr-1" />
              Weiteren Import starten
            </Button>
            {selectedAnlageId && (
              <Button
                variant="secondary"
                onClick={() => navigate(`/monatsabschluss/${selectedAnlageId}`)}
              >
                Monatsabschluss starten
              </Button>
            )}
            <Button
              variant="primary"
              onClick={() => navigate('/einstellungen/monatsdaten')}
            >
              <CheckCircle className="w-4 h-4 mr-1" />
              Zur Monatsübersicht
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
