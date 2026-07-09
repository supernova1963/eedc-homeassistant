/**
 * CsvImportWizard — schlanker eedc-CSV-Roundtrip als V4-Overlay-Wizard (D17-9).
 *
 * Löst den früheren Dead-End: der „CSV / JSON"-Button navigierte als EINZIGER
 * Importer in die V3-Seite `pages/Import` (nur per Browser-Back zurück). Hier läuft
 * der eedc-Template-CSV-Roundtrip im Overlay wie die übrigen Importer:
 *   Template herunterladen → CSV hochladen (`importCSV`) → Ergebnis (geteilter W4).
 *   + „Daten exportieren" (CSV-Roundtrip).
 * JSON-Restore lebt nativ im Backup-Block (hier NICHT dupliziert), Demo-Daten ist ein
 * separater Belang. Overlay-tauglich über {@link useWizardHost}; Anlage aus
 * {@link useSelectedAnlage}; Ergebnis-/Terminal-Schritt über den geteilten
 * {@link ImportErgebnis} („Fertig" schließt im Overlay statt V3-Navigation).
 */
import { useState, useRef, useCallback, type DragEvent, type ChangeEvent } from 'react'
import { Upload, Download } from 'lucide-react'
import { Button, Alert, Checkbox, LoadingSpinner } from '../components/ui'
import ImportErgebnis from '../components/import/ImportErgebnis'
import { useWizardHost } from '../v4/wizardHost'
import { useSelectedAnlage } from '../hooks'
import { importApi } from '../api'
import { downloadFile } from '../lib'
import type { ImportResult } from '../types'

export default function CsvImportWizard() {
  const host = useWizardHost()
  const { selectedAnlage, selectedAnlageId } = useSelectedAnlage()
  const [isDragging, setIsDragging] = useState(false)
  const [importing, setImporting] = useState(false)
  const [ueberschreiben, setUeberschreiben] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const safeName = (selectedAnlage?.anlagenname || 'anlage').replace(/\s+/g, '_')
  const keineAnlage = selectedAnlageId == null

  const handleFile = useCallback(async (file: File) => {
    if (selectedAnlageId == null) { setError('Bitte zuerst eine Anlage auswählen'); return }
    if (!file.name.toLowerCase().endsWith('.csv')) { setError('Bitte eine CSV-Datei auswählen'); return }
    setError(null); setResult(null); setImporting(true); host.setzeBlocker(true)
    try {
      setResult(await importApi.importCSV(selectedAnlageId, file, ueberschreiben))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import fehlgeschlagen')
    } finally {
      setImporting(false); host.setzeBlocker(false)
    }
  }, [selectedAnlageId, ueberschreiben, host])

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) void handleFile(f)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }
  const handleDrop = (e: DragEvent) => {
    e.preventDefault(); setIsDragging(false)
    const f = e.dataTransfer.files?.[0]
    if (f) void handleFile(f)
  }

  const handleTemplate = async () => {
    if (selectedAnlageId == null) { setError('Bitte zuerst eine Anlage auswählen'); return }
    try { await downloadFile(importApi.getTemplateDownloadUrl(selectedAnlageId), `eedc_template_${safeName}.csv`) }
    catch (e) { setError(e instanceof Error ? e.message : 'Template-Download fehlgeschlagen') }
  }
  const handleExport = async () => {
    if (selectedAnlageId == null) { setError('Bitte zuerst eine Anlage auswählen'); return }
    try { await downloadFile(importApi.getExportUrl(selectedAnlageId), `eedc_export_${safeName}.csv`) }
    catch (e) { setError(e instanceof Error ? e.message : 'Export fehlgeschlagen') }
  }

  // Ergebnis-Schritt (geteilter W4): „Fertig" schließt im Overlay, „Weitere CSV" setzt zurück.
  if (result) {
    return (
      <div className="max-w-2xl mx-auto">
        <ImportErgebnis
          result={{
            erfolg: result.erfolg,
            importiert: result.importiert,
            uebersprungen: result.uebersprungen,
            fehler: result.fehler,
            warnungen: result.warnungen ?? [],
          }}
          selectedAnlageId={selectedAnlageId ?? null}
          onWeiter={() => setResult(null)}
          weiterLabel="Weitere CSV importieren"
          weiterIcon={<Upload className="w-4 h-4 mr-1" />}
        />
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      {keineAnlage && (
        <Alert type="warning">Bitte zuerst eine Anlage auswählen, um CSV-Daten zu importieren.</Alert>
      )}
      {error && <Alert type="error" onClose={() => setError(null)}>{error}</Alert>}

      <p className="text-sm text-gray-600 dark:text-gray-300">
        Monatsdaten als CSV importieren. Das Template enthält automatisch alle Spalten passend zu deinen
        angelegten Investitionen. Für abweichende Fremd-Dateien mit Spalten-Zuordnung nutze „Eigene Datei / Vorlage".
      </p>

      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" onClick={handleTemplate} disabled={keineAnlage}>
          <Download className="h-4 w-4 mr-1" /> Template herunterladen
        </Button>
        <Button variant="secondary" size="sm" onClick={handleExport} disabled={keineAnlage}>
          <Download className="h-4 w-4 mr-1" /> Daten exportieren
        </Button>
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); if (!keineAnlage) setIsDragging(true) }}
        onDragLeave={(e) => { e.preventDefault(); setIsDragging(false) }}
        onDrop={handleDrop}
        onClick={() => { if (!importing && !keineAnlage) fileInputRef.current?.click() }}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          keineAnlage
            ? 'opacity-50 pointer-events-none border-gray-300 dark:border-gray-600'
            : isDragging
              ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 cursor-pointer'
              : 'border-gray-300 dark:border-gray-600 hover:border-primary-500 cursor-pointer'
        } ${importing ? 'opacity-50 pointer-events-none' : ''}`}
      >
        {importing ? (
          <div className="flex flex-col items-center">
            <LoadingSpinner size="sm" />
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">Importiere…</p>
          </div>
        ) : (
          <>
            <Upload className="h-8 w-8 mx-auto text-gray-400 dark:text-gray-500 mb-2" />
            <p className="text-sm text-gray-500 dark:text-gray-400">CSV-Datei hierher ziehen oder klicken zum Auswählen</p>
          </>
        )}
      </div>
      <input ref={fileInputRef} type="file" accept=".csv" onChange={handleFileSelect} className="hidden" />

      <Checkbox
        checked={ueberschreiben}
        onChange={(e) => setUeberschreiben(e.target.checked)}
        label="Bestehende Daten überschreiben"
      />
    </div>
  )
}
