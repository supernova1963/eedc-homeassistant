/**
 * Backup & Restore – Vollständiger JSON-Export und -Import einer Anlage
 *
 * Ersetzt das versteckte Download-Icon in Import/Export durch eine
 * eigenständige, gut sichtbare Seite im System-Menü.
 */

import { useState, useRef, DragEvent, ChangeEvent } from 'react'
import { Download, Upload, Check, FileJson, HardDrive, AlertTriangle } from 'lucide-react'
import { Button, Alert, Card, LoadingSpinner } from '../components/ui'
import { useAnlagen } from '../hooks'
import { importApi } from '../api'
import type { JSONImportResult } from '../types'

export default function Backup() {
  const { anlagen, loading: anlagenLoading, refresh: refreshAnlagen } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)

  // Import States
  const [isDragging, setIsDragging] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<JSONImportResult | null>(null)
  const [ueberschreiben, setUeberschreiben] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const anlageId = selectedAnlageId ?? anlagen[0]?.id

  const handleExport = () => {
    if (!anlageId) return
    window.open(importApi.getFullExportUrl(anlageId), '_blank')
  }

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
    if (files.length > 0) await handleFile(files[0])
  }

  const handleFileSelect = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) await handleFile(files[0])
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleFile = async (file: File) => {
    if (!file.name.endsWith('.json')) {
      setError('Bitte eine JSON-Datei auswählen')
      return
    }
    setError(null)
    setImportResult(null)
    setImporting(true)
    try {
      const result = await importApi.importJSON(file, ueberschreiben)
      setImportResult(result)
      if (result.erfolg) refreshAnlagen()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import fehlgeschlagen')
    } finally {
      setImporting(false)
    }
  }

  if (anlagenLoading) return <LoadingSpinner text="Lade..." />

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <HardDrive className="w-6 h-6 text-gray-500" />
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Backup & Restore
        </h1>
      </div>

      <p className="text-gray-500 dark:text-gray-400">
        Erstelle ein vollständiges Backup deiner Anlage (Stammdaten, Investitionen, Monatsdaten,
        Strompreise, PVGIS-Prognosen) oder stelle eine Anlage aus einem Backup wieder her.
      </p>

      {error && <Alert type="error" onClose={() => setError(null)}>{error}</Alert>}

      {/* Backup erstellen */}
      <Card>
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-lg bg-blue-50 dark:bg-blue-900/20">
            <Download className="h-6 w-6 text-blue-500" />
          </div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Backup erstellen
          </h2>
        </div>

        {anlagen.length === 0 ? (
          <p className="text-gray-500 dark:text-gray-400">
            Keine Anlagen vorhanden. Lege zuerst eine Anlage an.
          </p>
        ) : (
          <div className="space-y-4">
            {anlagen.length > 1 && (
              <select
                value={anlageId ?? ''}
                onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
                className="input w-full"
              >
                {anlagen.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.anlagenname} ({a.leistung_kwp} kWp)
                  </option>
                ))}
              </select>
            )}
            <Button onClick={handleExport} className="w-full">
              <Download className="h-4 w-4 mr-2" />
              Backup als JSON herunterladen
            </Button>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              Enthält alle Daten der Anlage. Sensor-Mapping wird mitexportiert,
              MQTT-Setup muss nach Restore neu eingerichtet werden.
            </p>
          </div>
        )}
      </Card>

      {/* Restore */}
      <Card>
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-lg bg-green-50 dark:bg-green-900/20">
            <Upload className="h-6 w-6 text-green-500" />
          </div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Restore aus Backup
          </h2>
        </div>

        {importResult && importResult.erfolg && (
          <div className="mb-4 p-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
            <div className="flex items-center gap-2 text-green-700 dark:text-green-300 font-medium mb-2">
              <Check className="h-5 w-5" />
              Anlage „{importResult.anlage_name}" erfolgreich importiert
            </div>
            <div className="text-sm text-green-600 dark:text-green-400 space-y-1">
              {importResult.importiert && Object.entries(importResult.importiert).map(([key, count]) => (
                count > 0 && <div key={key}>{key}: {count}</div>
              ))}
            </div>
            {importResult.warnungen && importResult.warnungen.length > 0 && (
              <div className="mt-3 space-y-1">
                {importResult.warnungen.map((w, i) => (
                  <div key={i} className="flex items-start gap-1.5 text-xs text-amber-600 dark:text-amber-400">
                    <AlertTriangle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
                    {w}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {importResult && !importResult.erfolg && (
          <Alert type="error" className="mb-4">
            {importResult.fehler?.join(', ') || 'Import fehlgeschlagen'}
          </Alert>
        )}

        <div className="space-y-4">
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`
              border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
              ${isDragging
                ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                : 'border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500'
              }
            `}
          >
            <FileJson className="h-10 w-10 mx-auto mb-3 text-gray-400" />
            {importing ? (
              <LoadingSpinner text="Importiere..." />
            ) : (
              <>
                <p className="text-gray-600 dark:text-gray-300 font-medium">
                  JSON-Backup hierher ziehen oder klicken
                </p>
                <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">
                  .json Datei aus einem früheren EEDC-Export
                </p>
              </>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={handleFileSelect}
              className="hidden"
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <input
              type="checkbox"
              checked={ueberschreiben}
              onChange={(e) => setUeberschreiben(e.target.checked)}
              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            Existierende Anlage mit gleichem Namen überschreiben
          </label>
        </div>
      </Card>
    </div>
  )
}
