/**
 * CloudImportWizard – Cloud-Import Wizard
 *
 * 4-Schritt-Wizard zum Importieren von historischen Energiedaten aus Cloud-APIs.
 * Schritt 1: Provider wählen, Credentials eingeben, Verbindung testen
 * Schritt 2: Zeitraum wählen, Daten abrufen
 * Schritt 3: Vorschau & Monatauswahl, Anlage wählen, Importieren
 * Schritt 4: Ergebnis
 *
 * IA-V4 (Style-Guide Teil D): SoT-Controls (Input/Select/Checkbox/Stepper/Alert)
 * statt roher Primitive; Overlay-tauglich über {@link useWizardHost} (W2/W5) —
 * Terminal-Aktionen schließen das Overlay statt in eine V3-Route zu navigieren,
 * ungespeicherte Eingaben lösen die Verwerfen-Nachfrage aus.
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Cloud,
  ChevronLeft,
  ChevronRight,
  Wifi,
  WifiOff,
  Save,
} from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Alert from '../components/ui/Alert'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import Checkbox from '../components/ui/Checkbox'
import Stepper from '../components/ui/Stepper'
import { useWizardHost } from '../v4/wizardHost'
import ImportErgebnis from '../components/import/ImportErgebnis'
import { anlagenApi } from '../api/anlagen'
import { cloudImportApi } from '../api/cloudImport'
import { portalImportApi } from '../api/portalImport'
import { investitionenApi } from '../api/investitionen'
import type { CloudProviderInfo, CloudTestResult, CloudPreviewResult } from '../api/cloudImport'
import type { ApplyResult } from '../api/portalImport'
import type { Anlage, Investition } from '../types'
import { MONAT_NAMEN } from '../lib/constants'
import { fmtZahl } from '../lib/einheiten'
import { ManuelleWerteHinweis } from '../components/import/ManuelleWerteHinweis'

export default function CloudImportWizard() {
  const navigate = useNavigate()
  const host = useWizardHost()

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
  const [fetchElapsed, setFetchElapsed] = useState(0)
  const [preview, setPreview] = useState<CloudPreviewResult | null>(null)

  // Step 3: Vorschau & Import
  const [anlagen, setAnlagen] = useState<Anlage[]>([])
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)
  // F-22 (#349): Ziel-Erzeuger. Leer = die Quelle beschreibt die ganze Anlage
  // (bisheriges Verhalten). Gesetzt = sie misst genau diesen Wechselrichter,
  // dann bleiben die Hauszähler-Werte unberührt und eine zweite Quelle kann
  // dieselben Monate liefern, ohne die erste zu verdrängen.
  const [zielInvestitionId, setZielInvestitionId] = useState<number | null>(null)
  const [zielKandidaten, setZielKandidaten] = useState<Investition[]>([])
  const [selectedMonths, setSelectedMonths] = useState<Set<string>>(new Set())
  const [ueberschreiben, setUeberschreiben] = useState(false)
  const [isImporting, setIsImporting] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  // Rückmeldung des Speicherns — sie nennt das Gerät und die Zahl der Quellen,
  // damit sichtbar ist, dass die zweite die erste NICHT verdrängt hat (N-229).
  const [gespeichert, setGespeichert] = useState<string | null>(null)
  const [result, setResult] = useState<ApplyResult | null>(null)

  // Load providers and anlagen
  useEffect(() => {
    cloudImportApi.getProviders().then(setProviders).catch(() => {})
    anlagenApi.list().then((list: Anlage[]) => {
      setAnlagen(list)
      if (list.length === 1) setSelectedAnlageId(list[0].id)
    }).catch(() => {})
  }, [])

  // Ziel-Kandidaten der gewählten Anlage: die Geräte, unter denen PV-Module
  // bzw. Speicher hängen dürfen — dieselbe Menge wie `ZIEL_ERLAUBTE_TYPEN` im
  // Backend (Parent-SoT `models/investition.py::ERLAUBTE_PARENT_TYPEN`).
  useEffect(() => {
    setZielInvestitionId(null)
    if (!selectedAnlageId) {
      setZielKandidaten([])
      return
    }
    investitionenApi.list(selectedAnlageId)
      .then((list) => setZielKandidaten(
        list.filter((i) => i.typ === 'wechselrichter' || i.typ === 'balkonkraftwerk')
      ))
      .catch(() => setZielKandidaten([]))
  }, [selectedAnlageId])

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

  // W5: ungespeicherte Eingaben melden, solange noch nicht importiert wurde.
  const dirty = result === null && (selectedProviderId !== '' || preview !== null)
  useEffect(() => {
    host.setzeBlocker(dirty)
    return () => host.setzeBlocker(false)
  }, [dirty, host])

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
    setFetchElapsed(0)
    // #328: Abruf läuft als Hintergrund-Job (Polling) — bei langen Zeiträumen
    // würde ein synchroner Request in Browser/Ingress-Timeouts laufen. Der
    // Sekunden-Zähler gibt dem Nutzer Rückmeldung, dass es weiterläuft.
    const startedAt = Date.now()
    const timer = window.setInterval(() => {
      setFetchElapsed(Math.round((Date.now() - startedAt) / 1000))
    }, 1000)
    try {
      const result = await cloudImportApi.fetchPreviewAsync(
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
      window.clearInterval(timer)
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
        selectedAnlageId, monate, ueberschreiben, 'cloud_import',
        undefined, zielInvestitionId
      )
      setResult(importResult)
      setCurrentStep(3)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import fehlgeschlagen')
    } finally {
      setIsImporting(false)
    }
  }, [preview, selectedAnlageId, selectedMonths, ueberschreiben, zielInvestitionId])

  const handleSaveCredentials = useCallback(async () => {
    if (!selectedAnlageId || !selectedProviderId) return
    setIsSaving(true)
    try {
      // Das Ziel wird mitgespeichert (N-229): nur so liegen die Konten zweier
      // Wechselrichter nebeneinander, statt sich gegenseitig zu verdrängen —
      // und der Monatsabschluss weiß, welcher Wert zu welchem Gerät gehört.
      const antwort = await cloudImportApi.saveCredentials(
        selectedAnlageId, selectedProviderId, credentials, zielInvestitionId
      )
      setGespeichert(antwort.message)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Speichern fehlgeschlagen')
    } finally {
      setIsSaving(false)
    }
  }, [selectedAnlageId, selectedProviderId, credentials, zielInvestitionId])

  // W3: Abbrechen — im Overlay Dirty-geschützt schließen, sonst zurück navigieren.
  const handleAbbrechen = useCallback(() => {
    if (host.imOverlay) host.abbrechen()
    else navigate(-1)
  }, [host, navigate])

  // ── Render ─────────────────────────────────────────────────────────────────

  const steps = [
    { titel: 'Verbinden' },
    { titel: 'Zeitraum' },
    { titel: 'Vorschau' },
    { titel: 'Ergebnis' },
  ]

  // Options für Selects
  const providerOptions = providers.map((p) => ({
    value: p.id,
    label: `${p.name} (${p.hersteller})${!p.getestet ? ' (*)' : ''}`,
  }))
  const monatOptions = MONAT_NAMEN.slice(1).map((name, idx) => ({ value: String(idx + 1), label: name }))
  const yearOptions: { value: string; label: string }[] = []
  for (let y = now.getFullYear() - 5; y <= now.getFullYear(); y++) {
    yearOptions.push({ value: String(y), label: String(y) })
  }
  const anlageOptions = anlagen.map((a) => ({
    value: String(a.id),
    label: `${a.anlagenname} (${a.leistung_kwp} kWp)`,
  }))

  const zielOptions = [
    { value: '', label: 'Die ganze Anlage (Gesamtwerte)' },
    ...zielKandidaten.map((i) => ({
      value: String(i.id),
      label: i.bezeichnung || i.typ,
    })),
  ]

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

      {/* Stepper (W1) */}
      <Stepper schritte={steps} aktuell={currentStep} className="mb-6" />

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
              <Select
                label="Cloud-Provider"
                value={selectedProviderId}
                onChange={(e) => setSelectedProviderId(e.target.value)}
                options={providerOptions}
                placeholder="Provider wählen…"
                hint={providers.some((p) => !p.getestet)
                  ? '(*) Ungetestet – basiert auf Hersteller-Dokumentation, aber noch nicht mit echten Gerätedaten verifiziert. Feedback willkommen!'
                  : undefined}
              />

              {selectedProvider && (
                <Alert type="info" title={selectedProvider.beschreibung} className="mt-3">
                  <p className="whitespace-pre-line">{selectedProvider.anleitung}</p>
                </Alert>
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
                    field.type === 'select' ? (
                      <Select
                        key={field.id}
                        label={field.label}
                        required={field.required}
                        value={credentials[field.id] || ''}
                        onChange={(e) => setCredentials({ ...credentials, [field.id]: e.target.value })}
                        options={field.options.map((opt) => ({ value: opt.value, label: opt.label }))}
                      />
                    ) : (
                      <Input
                        key={field.id}
                        label={field.label}
                        required={field.required}
                        type={field.type === 'password' ? 'password' : 'text'}
                        value={credentials[field.id] || ''}
                        onChange={(e) => setCredentials({ ...credentials, [field.id]: e.target.value })}
                        placeholder={field.placeholder}
                      />
                    )
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
                    {isTesting ? 'Teste…' : 'Verbindung testen'}
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

                {/* Fehler-Details (bei Misserfolg) — Backend-Fehlermeldung sichtbar machen,
                    statt nur das generische "Verbindung fehlgeschlagen" zu zeigen.
                    Sonst muss der Anwender Backend-Logs lesen, um die eigentliche
                    API-Antwort zu sehen. */}
                {testResult && !testResult.erfolg && testResult.fehler && (
                  <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg text-sm text-red-700 dark:text-red-300">
                    <div className="font-medium mb-1">Fehler-Details vom Anbieter:</div>
                    <div className="font-mono text-xs whitespace-pre-wrap break-all">
                      {testResult.fehler}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* Navigation (W3) */}
          <div className="flex items-center justify-end gap-2">
            <Button variant="secondary" onClick={handleAbbrechen}>
              Abbrechen
            </Button>
            <Button
              variant="primary"
              onClick={() => setCurrentStep(1)}
              disabled={!testResult?.erfolg}
            >
              Weiter
              <ChevronRight className="w-4 h-4 ml-1" />
            </Button>
          </div>
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
                  <span className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Von</span>
                  <div className="flex gap-2">
                    <Select
                      value={String(startMonth)}
                      onChange={(e) => setStartMonth(Number(e.target.value))}
                      options={monatOptions}
                    />
                    <Select
                      compact
                      value={String(startYear)}
                      onChange={(e) => setStartYear(Number(e.target.value))}
                      options={yearOptions}
                    />
                  </div>
                </div>

                {/* Bis */}
                <div>
                  <span className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Bis</span>
                  <div className="flex gap-2">
                    <Select
                      value={String(endMonth)}
                      onChange={(e) => setEndMonth(Number(e.target.value))}
                      options={monatOptions}
                    />
                    <Select
                      compact
                      value={String(endYear)}
                      onChange={(e) => setEndYear(Number(e.target.value))}
                      options={yearOptions}
                    />
                  </div>
                </div>
              </div>

              <Alert type="info" className="mt-4">
                <p className="text-sm">
                  Die Cloud-API wird pro Woche abgefragt. Bei längeren Zeiträumen kann der Abruf
                  mehrere Minuten dauern.
                </p>
                {isFetching && (
                  <p className="text-sm mt-2 font-medium">
                    Abruf läuft im Hintergrund … ({fetchElapsed}s). Das Fenster kann offen bleiben —
                    der Abruf wird nicht abgebrochen.
                  </p>
                )}
              </Alert>
            </div>
          </Card>

          {/* Navigation (W3) */}
          <div className="flex items-center justify-between">
            <Button variant="ghost" onClick={() => setCurrentStep(0)}>
              <ChevronLeft className="w-4 h-4 mr-1" />
              Zurück
            </Button>
            <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={handleAbbrechen}>
              Abbrechen
            </Button>
            <Button
              variant="primary"
              onClick={handleFetch}
              loading={isFetching}
              disabled={(startYear * 100 + startMonth) > (endYear * 100 + endMonth)}
            >
              {isFetching ? 'Daten werden abgerufen…' : 'Daten abrufen'}
              {!isFetching && <ChevronRight className="w-4 h-4 ml-1" />}
            </Button>
            </div>
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
                  <Select
                    label="Ziel-Anlage"
                    value={selectedAnlageId != null ? String(selectedAnlageId) : ''}
                    onChange={(e) => setSelectedAnlageId(Number(e.target.value) || null)}
                    options={anlageOptions}
                    placeholder="Anlage wählen…"
                  />
                </div>
                {zielKandidaten.length > 0 && (
                  <div className="flex-1 min-w-[200px]">
                    <Select
                      label="Diese Quelle misst"
                      value={zielInvestitionId != null ? String(zielInvestitionId) : ''}
                      onChange={(e) => setZielInvestitionId(Number(e.target.value) || null)}
                      options={zielOptions}
                    />
                  </div>
                )}
                <div className="pb-2">
                  <Checkbox
                    label="Bestehende Monate überschreiben"
                    checked={ueberschreiben}
                    onChange={(e) => setUeberschreiben(e.target.checked)}
                  />
                  <ManuelleWerteHinweis
                    anlageId={selectedAnlageId}
                    perioden={[...selectedMonths].map((k) => {
                      const [j, m] = k.split('-')
                      return `${j}-${String(Number(m)).padStart(2, '0')}`
                    })}
                    aktiv={ueberschreiben}
                  />
                </div>
              </div>
              {zielInvestitionId != null && (
                <Alert type="info" className="mt-4">
                  Erzeugung und Speicherwerte gehen an die PV-Module und den Speicher
                  dieses Geräts. Einspeisung und Netzbezug misst kein Wechselrichter
                  selbst — sie kommen vom Zähler am Hausanschluss und gelten deshalb
                  für die ganze Anlage: sie werden einmal in den Monat übernommen,
                  eine zweite Quelle addiert sie nicht dazu.
                </Alert>
              )}
            </div>
          </Card>

          {/* Monatsdaten-Tabelle */}
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="px-4 py-3 text-left">
                      <Checkbox
                        checked={selectedMonths.size === preview.monate.length}
                        onChange={toggleAll}
                        label={<span className="font-medium text-gray-700 dark:text-gray-300">Monat</span>}
                      />
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
                          <Checkbox
                            checked={selected}
                            onChange={() => toggleMonth(key)}
                            label={<span className="text-gray-900 dark:text-white">{MONAT_NAMEN[m.monat]} {m.jahr}</span>}
                          />
                        </td>
                        <td className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">
                          {fmtZahl(m.pv_erzeugung_kwh, 1)}
                        </td>
                        <td className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">
                          {fmtZahl(m.einspeisung_kwh, 1)}
                        </td>
                        <td className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">
                          {fmtZahl(m.netzbezug_kwh, 1)}
                        </td>
                        <td className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">
                          {fmtZahl(m.batterie_ladung_kwh, 1)}
                        </td>
                        <td className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">
                          {fmtZahl(m.batterie_entladung_kwh, 1)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Navigation (W3) */}
          <div className="flex items-center justify-between">
            <Button variant="ghost" onClick={() => { setCurrentStep(1); setPreview(null) }}>
              <ChevronLeft className="w-4 h-4 mr-1" />
              Zurück
            </Button>
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-500 dark:text-gray-400">
                {selectedMonths.size} von {preview.monate.length} Monaten
              </span>
              <Button variant="secondary" onClick={handleAbbrechen}>
                Abbrechen
              </Button>
              <Button
                variant="primary"
                onClick={handleImport}
                loading={isImporting}
                disabled={selectedMonths.size === 0 || !selectedAnlageId}
              >
                {isImporting ? 'Importiere…' : `${selectedMonths.size} Monate importieren`}
                {!isImporting && <ChevronRight className="w-4 h-4 ml-1" />}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Step 4: Ergebnis (geteilter Baustein, W2/W4) */}
      {currentStep === 3 && result && (
        <ImportErgebnis
          result={result}
          selectedAnlageId={selectedAnlageId}
          weiterIcon={<Cloud className="w-4 h-4 mr-1" />}
          hinweis={
            <p>
              Der Cloud-Import erfasst PV-Erzeugung, Einspeisung, Netzbezug und Batterie-Daten.
              Für einen vollständigen Monatsabschluss müssen ggf. noch weitere Daten ergänzt werden
              (z.B. Wallbox, Wärmepumpe, E-Auto).
            </p>
          }
          extra={result.erfolg && selectedAnlageId ? (
            <Card>
              <div className="p-5">
                <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Zugangsdaten für spätere Imports speichern?
                </h3>
                {zielInvestitionId != null && (
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                    Sie werden dem gewählten Gerät zugeordnet. Hast du mehrere Geräte
                    mit eigenem Cloud-Konto, speicherst du jedes einzeln — sie
                    verdrängen sich nicht.
                  </p>
                )}
                <div className="flex items-center gap-3">
                  <Button
                    variant="secondary"
                    onClick={handleSaveCredentials}
                    loading={isSaving}
                    size="sm"
                  >
                    <Save className="w-4 h-4 mr-1" />
                    {isSaving ? 'Speichere…' : 'Credentials speichern'}
                  </Button>
                </div>
                {gespeichert && (
                  <Alert type="success" className="mt-3">{gespeichert}</Alert>
                )}
              </div>
            </Card>
          ) : undefined}
          onWeiter={() => {
            setCurrentStep(0)
            setPreview(null)
            setResult(null)
            setError(null)
            setTestResult(null)
          }}
        />
      )}
    </div>
  )
}
