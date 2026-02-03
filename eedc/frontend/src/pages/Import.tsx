import { useState, useRef, DragEvent, ChangeEvent } from 'react'
import { Upload, FileSpreadsheet, Home, Download, Check, AlertTriangle, X } from 'lucide-react'
import { Button, Alert, Card, LoadingSpinner } from '../components/ui'
import { useAnlagen } from '../hooks'
import { importApi } from '../api'
import type { ImportResult } from '../types'

export default function Import() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ueberschreiben, setUeberschreiben] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

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

        {/* HA Import */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-cyan-50 dark:bg-cyan-900/20">
              <Home className="h-6 w-6 text-cyan-500" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Home Assistant Import
            </h2>
          </div>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Importiere Daten direkt aus deinem Home Assistant Energy Dashboard.
          </p>
          <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg text-sm text-yellow-700 dark:text-yellow-300 mb-4">
            <strong>Phase 2:</strong> Diese Funktion wird in einer zukünftigen Version verfügbar sein.
            Konfiguriere zuerst die Sensor-Zuordnung in den Einstellungen.
          </div>
          <Button variant="secondary" className="w-full" disabled>
            Aus Home Assistant importieren
          </Button>
        </Card>
      </div>

      {/* Hilfe */}
      <Card>
        <h3 className="font-semibold text-gray-900 dark:text-white mb-3">
          CSV-Format
        </h3>
        <div className="text-sm text-gray-600 dark:text-gray-400 space-y-2">
          <p>Das CSV muss folgende Pflichtspalten enthalten:</p>
          <ul className="list-disc list-inside ml-2 space-y-1">
            <li><code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">Jahr</code> - Jahr (z.B. 2024)</li>
            <li><code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">Monat</code> - Monat (1-12)</li>
            <li><code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">Einspeisung_kWh</code> - Einspeisung ins Netz</li>
            <li><code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">Netzbezug_kWh</code> - Bezug aus dem Netz</li>
          </ul>
          <p className="mt-2">Optionale Spalten für erweiterte Auswertungen:</p>
          <ul className="list-disc list-inside ml-2 space-y-1">
            <li><code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">PV_Erzeugung_kWh</code> - Gesamte PV-Erzeugung</li>
            <li><code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">Direktverbrauch_kWh</code> - Direkter Eigenverbrauch</li>
            <li><code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">Batterie_Ladung_kWh</code> - Batterieladung</li>
            <li><code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">Batterie_Entladung_kWh</code> - Batterieentladung</li>
          </ul>
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
  const isSuccess = result.erfolg && result.fehler.length === 0

  return (
    <div className={`
      relative p-4 rounded-lg border
      ${isSuccess
        ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
        : 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
      }
    `}>
      <button
        onClick={onClose}
        className="absolute top-2 right-2 p-1 text-gray-400 hover:text-gray-600"
      >
        <X className="h-4 w-4" />
      </button>

      <div className="flex items-start gap-3">
        {isSuccess ? (
          <Check className="h-5 w-5 text-green-500 mt-0.5" />
        ) : (
          <AlertTriangle className="h-5 w-5 text-yellow-500 mt-0.5" />
        )}
        <div>
          <h4 className={`font-medium ${isSuccess ? 'text-green-800 dark:text-green-200' : 'text-yellow-800 dark:text-yellow-200'}`}>
            {isSuccess ? 'Import erfolgreich' : 'Import mit Warnungen'}
          </h4>
          <div className="text-sm mt-1 space-y-1">
            <p className={isSuccess ? 'text-green-700 dark:text-green-300' : 'text-yellow-700 dark:text-yellow-300'}>
              {result.importiert} Datensätze importiert
              {result.uebersprungen > 0 && `, ${result.uebersprungen} übersprungen`}
            </p>
            {result.fehler.length > 0 && (
              <ul className="list-disc list-inside text-yellow-700 dark:text-yellow-300">
                {result.fehler.slice(0, 5).map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
                {result.fehler.length > 5 && (
                  <li>... und {result.fehler.length - 5} weitere Fehler</li>
                )}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
