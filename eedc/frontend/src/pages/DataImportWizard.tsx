/**
 * DataImportWizard – Portal-Import Wizard
 *
 * 3-Schritt-Wizard zum Importieren von Energiedaten aus Hersteller-Portal-Exporten (CSV).
 * Schritt 1: Hersteller & Datei wählen
 * Schritt 2: Vorschau & Auswahl
 * Schritt 3: Ergebnis
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FileSpreadsheet,
  Upload,
  ChevronLeft,
  ChevronRight,
  CheckCircle,
  Loader2,
  Search,
  Info,
  X,
} from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Alert from '../components/ui/Alert'
import { anlagenApi } from '../api/anlagen'
import { portalImportApi } from '../api/portalImport'
import type { ParserInfo, PreviewResult, ApplyResult } from '../api/portalImport'
import type { Anlage } from '../types'

const MONAT_NAMEN = [
  '', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
]

export default function DataImportWizard() {
  const navigate = useNavigate()

  // Wizard state
  const [currentStep, setCurrentStep] = useState(0)
  const [error, setError] = useState<string | null>(null)

  // Step 1: Parser & Datei
  const [parsers, setParsers] = useState<ParserInfo[]>([])
  const [selectedParserId, setSelectedParserId] = useState<string>('')
  const [file, setFile] = useState<File | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isParsing, setIsParsing] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Step 2: Vorschau
  const [preview, setPreview] = useState<PreviewResult | null>(null)
  const [selectedMonths, setSelectedMonths] = useState<Set<string>>(new Set())
  const [anlagen, setAnlagen] = useState<Anlage[]>([])
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)
  const [ueberschreiben, setUeberschreiben] = useState(false)

  // Step 3: Ergebnis
  const [isImporting, setIsImporting] = useState(false)
  const [result, setResult] = useState<ApplyResult | null>(null)

  // ── Daten laden ──────────────────────────────────────────────────────────

  useEffect(() => {
    portalImportApi.getParsers().then(setParsers).catch(() => {})
    anlagenApi.list().then((list) => {
      setAnlagen(list)
      if (list.length === 1) setSelectedAnlageId(list[0].id)
    }).catch(() => {})
  }, [])

  // ── Step 1: Datei-Handling ────────────────────────────────────────────────

  const handleFile = useCallback(async (f: File) => {
    setFile(f)
    setError(null)
    setIsParsing(true)

    try {
      const result = await portalImportApi.preview(
        f,
        selectedParserId || undefined
      )
      setPreview(result)
      // Alle Monate vorselektieren
      const keys = new Set(result.monate.map((m) => `${m.jahr}-${m.monat}`))
      setSelectedMonths(keys)
      setCurrentStep(1)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Vorschau fehlgeschlagen')
    } finally {
      setIsParsing(false)
    }
  }, [selectedParserId])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const files = e.dataTransfer.files
    if (files.length > 0) handleFile(files[0])
  }, [handleFile])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) handleFile(files[0])
  }, [handleFile])

  // ── Step 2: Monats-Auswahl ───────────────────────────────────────────────

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
    const allKeys = preview.monate.map((m) => `${m.jahr}-${m.monat}`)
    if (selectedMonths.size === allKeys.length) {
      setSelectedMonths(new Set())
    } else {
      setSelectedMonths(new Set(allKeys))
    }
  }, [preview, selectedMonths])

  // ── Step 3: Import ausführen ──────────────────────────────────────────────

  const handleImport = useCallback(async () => {
    if (!preview || !selectedAnlageId) return
    setIsImporting(true)
    setError(null)

    const monate = preview.monate.filter((m) =>
      selectedMonths.has(`${m.jahr}-${m.monat}`)
    )

    try {
      const result = await portalImportApi.apply(
        selectedAnlageId,
        monate,
        ueberschreiben
      )
      setResult(result)
      setCurrentStep(2)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import fehlgeschlagen')
    } finally {
      setIsImporting(false)
    }
  }, [preview, selectedAnlageId, selectedMonths, ueberschreiben])

  // ── Render ────────────────────────────────────────────────────────────────

  const steps = [
    { title: 'Datei wählen', icon: <Upload className="w-4 h-4" /> },
    { title: 'Vorschau', icon: <Search className="w-4 h-4" /> },
    { title: 'Ergebnis', icon: <CheckCircle className="w-4 h-4" /> },
  ]

  const selectedParser = parsers.find((p) => p.id === selectedParserId)

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <FileSpreadsheet className="w-6 h-6 text-primary-500" />
          Portal-Import
        </h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          Energiedaten aus Ihrem Hersteller-Portal importieren
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

      {/* Step 1: Datei & Hersteller wählen */}
      {currentStep === 0 && (
        <div className="space-y-6">
          {/* Parser-Auswahl */}
          <Card>
            <div className="p-5">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                Hersteller wählen
              </h2>
              <select
                value={selectedParserId}
                onChange={(e) => setSelectedParserId(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white
                  dark:bg-gray-700 dark:border-gray-600 dark:text-white
                  focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">Automatisch erkennen</option>
                {parsers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.hersteller}){!p.getestet ? ' (*)' : ''}
                  </option>
                ))}
              </select>

              {parsers.some((p) => !p.getestet) && (
                <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                  (*) Ungetestet – basiert auf Hersteller-Dokumentation, aber noch nicht mit echten
                  Gerätedaten verifiziert. Feedback willkommen!
                </p>
              )}

              {selectedParser && (
                <div className="mt-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                  <div className="flex items-start gap-2">
                    <Info className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
                    <div className="text-sm text-blue-700 dark:text-blue-300">
                      <p className="font-medium mb-1">{selectedParser.beschreibung}</p>
                      <p className="text-blue-600 dark:text-blue-400 whitespace-pre-line">
                        {selectedParser.anleitung}
                      </p>
                      <p className="mt-2 font-mono text-xs text-blue-500 dark:text-blue-400">
                        Beispiel: {selectedParser.beispiel_header}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </Card>

          {/* Drag & Drop Zone */}
          <Card>
            <div className="p-5">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                CSV-Datei hochladen
              </h2>
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors
                  ${isDragging
                    ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                    : 'border-gray-300 dark:border-gray-600 hover:border-primary-400 hover:bg-gray-50 dark:hover:bg-gray-800'
                  }`}
              >
                {isParsing ? (
                  <>
                    <Loader2 className="w-12 h-12 mx-auto text-primary-500 mb-3 animate-spin" />
                    <p className="text-gray-700 dark:text-gray-300 font-medium">Datei wird analysiert...</p>
                  </>
                ) : (
                  <>
                    <Upload className="w-12 h-12 mx-auto text-gray-400 mb-3" />
                    <p className="text-gray-700 dark:text-gray-300 font-medium">
                      CSV-Datei hier ablegen oder klicken
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                      Unterstützt: CSV (Semikolon- oder Komma-getrennt)
                    </p>
                  </>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.CSV"
                  onChange={handleFileSelect}
                  className="hidden"
                />
              </div>

              {file && !isParsing && (
                <div className="mt-3 flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                  <FileSpreadsheet className="w-4 h-4" />
                  {file.name}
                  <button onClick={() => { setFile(null); setPreview(null) }} className="ml-auto text-gray-400 hover:text-gray-600">
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* Step 2: Vorschau & Auswahl */}
      {currentStep === 1 && preview && (
        <div className="space-y-4">
          {/* Parser-Info */}
          <Alert type="info">
            Erkannt: <strong>{preview.parser.name}</strong> – {preview.anzahl_monate} Monate gefunden
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
              onClick={() => { setCurrentStep(0); setPreview(null); setFile(null) }}
            >
              <ChevronLeft className="w-4 h-4 mr-1" />
              Zurück
            </Button>
            <div className="text-sm text-gray-500 dark:text-gray-400">
              {selectedMonths.size} von {preview.monate.length} Monaten ausgewählt
            </div>
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
      )}

      {/* Step 3: Ergebnis */}
      {currentStep === 2 && result && (
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

          {result.erfolg && (
            <Alert type="info" title="Nächster Schritt: Monatsabschluss">
              <p>
                Der Portal-Import erfasst PV-Erzeugung, Einspeisung, Netzbezug und Batterie-Daten.
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
                setFile(null)
                setPreview(null)
                setResult(null)
                setError(null)
              }}
            >
              <Upload className="w-4 h-4 mr-1" />
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
