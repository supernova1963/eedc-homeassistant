import { useState, useRef, DragEvent, ChangeEvent } from 'react'
import { Upload, FileSpreadsheet, Download, Check, AlertTriangle, X, Sparkles, Trash2 } from 'lucide-react'
import { Button, Alert, Card, LoadingSpinner } from '../components/ui'
import { useAnlagen } from '../hooks'
import { importApi } from '../api'
import type { ImportResult } from '../types'
import type { DemoDataResult } from '../api'

export default function Import() {
  const { anlagen, loading: anlagenLoading, refresh: refreshAnlagen } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ueberschreiben, setUeberschreiben] = useState(false)
  const [demoLoading, setDemoLoading] = useState(false)
  const [demoResult, setDemoResult] = useState<DemoDataResult | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Prüfen ob Demo-Anlage existiert
  const hasDemoAnlage = anlagen.some(a => a.anlagenname === 'Demo-Anlage')

  // Automatisch erste Anlage auswählen
  const anlageId = selectedAnlageId ?? anlagen[0]?.id

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = async (e: DragEvent) => {
    e.preventDefault()
    setIsDragging(false)

    const files = e.dataTransfer.files
    if (files.length > 0) {
      await handleFile(files[0])
    }
  }

  const handleFileSelect = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      await handleFile(files[0])
    }
    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleFile = async (file: File) => {
    if (!anlageId) {
      setError('Bitte zuerst eine Anlage auswählen')
      return
    }

    if (!file.name.endsWith('.csv')) {
      setError('Bitte eine CSV-Datei auswählen')
      return
    }

    setError(null)
    setResult(null)
    setImporting(true)

    try {
      const importResult = await importApi.importCSV(anlageId, file, ueberschreiben)
      setResult(importResult)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import fehlgeschlagen')
    } finally {
      setImporting(false)
    }
  }

  const handleDownloadTemplate = () => {
    if (!anlageId) {
      setError('Bitte zuerst eine Anlage auswählen')
      return
    }
    window.location.href = importApi.getTemplateDownloadUrl(anlageId)
  }

  const handleExport = () => {
    if (!anlageId) {
      setError('Bitte zuerst eine Anlage auswählen')
      return
    }
    window.location.href = importApi.getExportUrl(anlageId)
  }

  const handleCreateDemoData = async () => {
    setError(null)
    setDemoResult(null)
    setDemoLoading(true)

    try {
      const result = await importApi.createDemoData()
      setDemoResult(result)
      refreshAnlagen()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Erstellen der Demo-Daten')
    } finally {
      setDemoLoading(false)
    }
  }

  const handleDeleteDemoData = async () => {
    setError(null)
    setDemoResult(null)
    setDemoLoading(true)

    try {
      await importApi.deleteDemoData()
      refreshAnlagen()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Löschen der Demo-Daten')
    } finally {
      setDemoLoading(false)
    }
  }

  if (anlagenLoading) {
    return <LoadingSpinner text="Lade..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Daten Import
        </h1>
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an, bevor du Daten importierst.
        </Alert>

        {/* Demo-Daten auch ohne Anlage verfügbar */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-amber-50 dark:bg-amber-900/20">
              <Sparkles className="h-6 w-6 text-amber-500" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Demo-Daten
            </h2>
          </div>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Starte mit einer kompletten Demo-Anlage inkl. PV-System, Speicher, E-Auto, Wärmepumpe, Balkonkraftwerk, Mini-BHKW und 31 Monaten Testdaten.
          </p>
          <Button
            onClick={handleCreateDemoData}
            loading={demoLoading}
            className="w-full"
          >
            <Sparkles className="h-4 w-4 mr-2" />
            Demo-Daten erstellen
          </Button>
          {demoResult && (
            <div className="mt-4 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg text-sm text-green-700 dark:text-green-300">
              <Check className="inline h-4 w-4 mr-1" />
              {demoResult.message}
            </div>
          )}
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Daten Import
        </h1>
        {anlagen.length > 1 && (
          <select
            value={anlageId ?? ''}
            onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
            className="input w-auto"
          >
            {anlagen.map((a) => (
              <option key={a.id} value={a.id}>
                {a.anlagenname}
              </option>
            ))}
          </select>
        )}
      </div>

      {error && (
        <Alert type="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {result && (
        <ImportResultCard result={result} onClose={() => setResult(null)} />
      )}

      <div className="grid md:grid-cols-2 gap-6">
        {/* CSV Import */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-blue-50 dark:bg-blue-900/20">
              <FileSpreadsheet className="h-6 w-6 text-blue-500" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              CSV Import
            </h2>
          </div>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Importiere Monatsdaten aus einer CSV-Datei. Das Template enthält alle verfügbaren Spalten.
          </p>

          <div className="space-y-4">
            <Button variant="secondary" className="w-full" onClick={handleDownloadTemplate}>
              <Download className="h-4 w-4 mr-2" />
              Template herunterladen
            </Button>

            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`
                border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
                ${isDragging
                  ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                  : 'border-gray-300 dark:border-gray-600 hover:border-primary-500'
                }
                ${importing ? 'opacity-50 pointer-events-none' : ''}
              `}
            >
              {importing ? (
                <div className="flex flex-col items-center">
                  <LoadingSpinner size="sm" />
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                    Importiere...
                  </p>
                </div>
              ) : (
                <>
                  <Upload className="h-8 w-8 mx-auto text-gray-400 mb-2" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    CSV-Datei hierher ziehen oder klicken zum Auswählen
                  </p>
                </>
              )}
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={handleFileSelect}
              className="hidden"
            />

            <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
              <input
                type="checkbox"
                checked={ueberschreiben}
                onChange={(e) => setUeberschreiben(e.target.checked)}
                className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              Bestehende Daten überschreiben
            </label>
          </div>

          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            <Button variant="secondary" size="sm" onClick={handleExport}>
              <Download className="h-4 w-4 mr-2" />
              Daten exportieren
            </Button>
          </div>
        </Card>

        {/* Demo-Daten */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-amber-50 dark:bg-amber-900/20">
              <Sparkles className="h-6 w-6 text-amber-500" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Demo-Daten
            </h2>
          </div>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            {hasDemoAnlage
              ? 'Demo-Anlage ist bereits vorhanden. Du kannst sie löschen, um sie neu zu erstellen.'
              : 'Erstelle eine komplette Demo-Anlage mit allen Investitionstypen und 31 Monaten Testdaten.'
            }
          </p>

          {hasDemoAnlage ? (
            <Button
              variant="danger"
              onClick={handleDeleteDemoData}
              loading={demoLoading}
              className="w-full"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Demo-Anlage löschen
            </Button>
          ) : (
            <Button
              onClick={handleCreateDemoData}
              loading={demoLoading}
              className="w-full"
            >
              <Sparkles className="h-4 w-4 mr-2" />
              Demo-Daten erstellen
            </Button>
          )}

          {demoResult && (
            <div className="mt-4 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg text-sm text-green-700 dark:text-green-300">
              <Check className="inline h-4 w-4 mr-1" />
              {demoResult.message}
            </div>
          )}

          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400">
            <strong>Enthält:</strong> 20 kWp PV-Anlage (3 Strings), 15 kWh Speicher, Tesla Model 3 mit V2H, Wärmepumpe, Wallbox, Balkonkraftwerk mit Speicher, Mini-BHKW, Strompreise 2023-2025
          </div>
        </Card>
      </div>

      {/* Hilfe */}
      <Card>
        <h3 className="font-semibold text-gray-900 dark:text-white mb-3">
          CSV-Format
        </h3>
        <div className="text-sm text-gray-600 dark:text-gray-400 space-y-3">
          <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
            <p className="font-medium text-blue-800 dark:text-blue-200 mb-1">💡 Tipp: Template herunterladen</p>
            <p className="text-blue-700 dark:text-blue-300">
              Das Template enthält automatisch alle Spalten passend zu deinen angelegten Investitionen
              (z.B. <code className="text-xs bg-blue-100 dark:bg-blue-800 px-1 rounded">Sueddach_kWh</code>,{' '}
              <code className="text-xs bg-blue-100 dark:bg-blue-800 px-1 rounded">BYD_HVS_Ladung_kWh</code>).
            </p>
          </div>

          <p><strong>Pflichtspalten:</strong></p>
          <ul className="list-disc list-inside ml-2 space-y-1">
            <li><code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">Jahr</code> - Jahr (z.B. 2024)</li>
            <li><code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">Monat</code> - Monat (1-12)</li>
            <li><code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">Einspeisung_kWh</code> - Einspeisung ins Netz</li>
            <li><code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">Netzbezug_kWh</code> - Bezug aus dem Netz</li>
          </ul>

          <p><strong>Investitions-Spalten (automatisch im Template):</strong></p>
          <ul className="list-disc list-inside ml-2 space-y-1">
            <li>PV-Module: <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">[Name]_kWh</code></li>
            <li>Speicher: <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">[Name]_Ladung_kWh</code>, <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">[Name]_Entladung_kWh</code></li>
            <li>E-Auto: <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">[Name]_km</code>, <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">[Name]_Verbrauch_kWh</code>, etc.</li>
            <li>Wärmepumpe: <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">[Name]_Strom_kWh</code>, <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">[Name]_Heizung_kWh</code></li>
          </ul>

          <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg mt-2">
            <p className="font-medium text-amber-800 dark:text-amber-200 mb-1">⚠️ Hinweis zu Legacy-Spalten</p>
            <p className="text-amber-700 dark:text-amber-300 text-xs">
              Die Spalten <code className="bg-amber-100 dark:bg-amber-800 px-1 rounded">PV_Erzeugung_kWh</code> und{' '}
              <code className="bg-amber-100 dark:bg-amber-800 px-1 rounded">Batterie_*_kWh</code> werden nicht mehr
              unterstützt, wenn PV-Module/Speicher als Investitionen angelegt sind. Verwende stattdessen die
              individuellen Investitions-Spalten.
            </p>
          </div>
        </div>
      </Card>
    </div>
  )
}

interface ImportResultCardProps {
  result: ImportResult
  onClose: () => void
}

function ImportResultCard({ result, onClose }: ImportResultCardProps) {
  const hasErrors = result.fehler.length > 0
  const hasWarnings = result.warnungen && result.warnungen.length > 0

  // Farbe basierend auf Status
  const getColorClass = () => {
    if (hasErrors) return 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
    if (hasWarnings) return 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
    return 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
  }

  const getTextColorClass = () => {
    if (hasErrors) return 'text-red-800 dark:text-red-200'
    if (hasWarnings) return 'text-yellow-800 dark:text-yellow-200'
    return 'text-green-800 dark:text-green-200'
  }

  const getSubTextColorClass = () => {
    if (hasErrors) return 'text-red-700 dark:text-red-300'
    if (hasWarnings) return 'text-yellow-700 dark:text-yellow-300'
    return 'text-green-700 dark:text-green-300'
  }

  return (
    <div className={`relative p-4 rounded-lg border ${getColorClass()}`}>
      <button
        onClick={onClose}
        className="absolute top-2 right-2 p-1 text-gray-400 hover:text-gray-600"
      >
        <X className="h-4 w-4" />
      </button>

      <div className="flex items-start gap-3">
        {hasErrors ? (
          <X className="h-5 w-5 text-red-500 mt-0.5" />
        ) : hasWarnings ? (
          <AlertTriangle className="h-5 w-5 text-yellow-500 mt-0.5" />
        ) : (
          <Check className="h-5 w-5 text-green-500 mt-0.5" />
        )}
        <div className="flex-1">
          <h4 className={`font-medium ${getTextColorClass()}`}>
            {hasErrors
              ? 'Import mit Fehlern'
              : hasWarnings
                ? 'Import erfolgreich (mit Hinweisen)'
                : 'Import erfolgreich'
            }
          </h4>
          <div className="text-sm mt-1 space-y-2">
            <p className={getSubTextColorClass()}>
              {result.importiert} Datensätze importiert
              {result.uebersprungen > 0 && `, ${result.uebersprungen} übersprungen`}
            </p>

            {/* Fehler anzeigen */}
            {hasErrors && (
              <div>
                <p className="font-medium text-red-700 dark:text-red-300 mt-2">Fehler:</p>
                <ul className="list-disc list-inside text-red-700 dark:text-red-300 ml-2">
                  {result.fehler.slice(0, 5).map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                  {result.fehler.length > 5 && (
                    <li>... und {result.fehler.length - 5} weitere Fehler</li>
                  )}
                </ul>
              </div>
            )}

            {/* Warnungen anzeigen */}
            {hasWarnings && (
              <div>
                <p className="font-medium text-amber-700 dark:text-amber-300 mt-2">Hinweise:</p>
                <ul className="list-disc list-inside text-amber-700 dark:text-amber-300 ml-2">
                  {result.warnungen!.slice(0, 5).map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                  {result.warnungen!.length > 5 && (
                    <li>... und {result.warnungen!.length - 5} weitere Hinweise</li>
                  )}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
