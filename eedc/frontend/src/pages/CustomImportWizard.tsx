/**
 * CustomImportWizard – Generischer CSV/JSON-Import mit benutzerdefiniertem Feld-Mapping
 *
 * 4-Schritt-Wizard:
 * 1. Datei hochladen → Spalten werden erkannt
 * 2. Spalten auf EEDC-Felder mappen (mit Auto-Detect + Templates)
 * 3. Vorschau der gemappten Daten
 * 4. Ergebnis
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
  Settings2,
  Save,
  ArrowRight,
  X,
} from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Alert from '../components/ui/Alert'
import { portalImportApi } from '../api/portalImport'
import { customImportApi } from '../api/customImport'
import type {
  AnalyzeResult,
  MappingConfig,
  FieldMapping,
  PreviewResult,
  TemplateInfo,
} from '../api/customImport'
import type { ApplyResult } from '../api/portalImport'
import { useSelectedAnlage } from '../hooks'
import { MONAT_NAMEN } from '../lib'

export default function CustomImportWizard() {
  const navigate = useNavigate()

  // Wizard
  const [currentStep, setCurrentStep] = useState(0)
  const [error, setError] = useState<string | null>(null)

  // Step 1: Upload
  const [file, setFile] = useState<File | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Step 2: Mapping
  const [mappings, setMappings] = useState<Record<string, string>>({})
  const [einheit, setEinheit] = useState('kwh')
  const [dezimalzeichen, setDezimalzeichen] = useState('auto')
  const [datumSpalte, setDatumSpalte] = useState<string | null>(null)
  const [datumFormat, setDatumFormat] = useState<string | null>(null)
  const [templates, setTemplates] = useState<TemplateInfo[]>([])
  const [templateName, setTemplateName] = useState('')
  const [savingTemplate, setSavingTemplate] = useState(false)

  // Step 3: Preview
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [preview, setPreview] = useState<PreviewResult | null>(null)
  const [selectedMonths, setSelectedMonths] = useState<Set<string>>(new Set())
  const { anlagen, selectedAnlageId, setSelectedAnlageId } = useSelectedAnlage()
  const [ueberschreiben, setUeberschreiben] = useState(false)

  // Step 4: Ergebnis
  const [isImporting, setIsImporting] = useState(false)
  const [result, setResult] = useState<ApplyResult | null>(null)

  // Templates laden
  useEffect(() => {
    customImportApi.getTemplates().then(setTemplates).catch(() => {})
  }, [])

  // ── Step 1: Datei-Upload ──────────────────────────────────────────────────

  const handleFile = useCallback(async (f: File) => {
    setFile(f)
    setError(null)
    setIsAnalyzing(true)

    try {
      const result = await customImportApi.analyze(f)
      setAnalysis(result)

      // Auto-Mapping setzen
      setMappings(result.auto_mapping)

      // Prüfe ob Jahr/Monat im Auto-Mapping fehlen → vielleicht Datumsspalte?
      const hasJahr = Object.values(result.auto_mapping).includes('jahr')
      const hasMonat = Object.values(result.auto_mapping).includes('monat')
      if (!hasJahr || !hasMonat) {
        // Suche nach Datumsspalte
        for (const col of result.spalten) {
          const samples = col.sample_values
          if (samples.some(s => /^\d{4}[-/]\d{1,2}/.test(s) || /^\d{1,2}[-/]\d{4}/.test(s))) {
            setDatumSpalte(col.name)
            break
          }
        }
      }

      setCurrentStep(1)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analyse fehlgeschlagen')
    } finally {
      setIsAnalyzing(false)
    }
  }, [])

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

  // ── Step 2: Mapping ───────────────────────────────────────────────────────

  const setMapping = useCallback((spalte: string, eedc_feld: string) => {
    setMappings(prev => {
      const next = { ...prev }
      if (eedc_feld === '') {
        delete next[spalte]
      } else {
        // Feld nur einmal zuweisen (altes Mapping entfernen)
        for (const [key, val] of Object.entries(next)) {
          if (val === eedc_feld && key !== spalte) {
            delete next[key]
          }
        }
        next[spalte] = eedc_feld
      }
      return next
    })
  }, [])

  const buildMappingConfig = useCallback((): MappingConfig => {
    const fieldMappings: FieldMapping[] = Object.entries(mappings)
      .filter(([, v]) => v !== '')
      .map(([spalte, eedc_feld]) => ({ spalte, eedc_feld }))

    return {
      mappings: fieldMappings,
      einheit,
      dezimalzeichen,
      datum_spalte: datumSpalte,
      datum_format: datumFormat,
    }
  }, [mappings, einheit, dezimalzeichen, datumSpalte, datumFormat])

  const applyTemplate = useCallback((template: TemplateInfo) => {
    const newMappings: Record<string, string> = {}
    for (const m of template.mapping.mappings) {
      newMappings[m.spalte] = m.eedc_feld
    }
    setMappings(newMappings)
    setEinheit(template.mapping.einheit)
    setDezimalzeichen(template.mapping.dezimalzeichen)
    setDatumSpalte(template.mapping.datum_spalte || null)
    setDatumFormat(template.mapping.datum_format || null)
  }, [])

  const handleSaveTemplate = useCallback(async () => {
    if (!templateName.trim()) return
    setSavingTemplate(true)
    try {
      await customImportApi.saveTemplate(templateName.trim(), buildMappingConfig())
      const updated = await customImportApi.getTemplates()
      setTemplates(updated)
      setTemplateName('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Template speichern fehlgeschlagen')
    } finally {
      setSavingTemplate(false)
    }
  }, [templateName, buildMappingConfig])

  const handleDeleteTemplate = useCallback(async (name: string) => {
    try {
      await customImportApi.deleteTemplate(name)
      setTemplates(prev => prev.filter(t => t.name !== name))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Template löschen fehlgeschlagen')
    }
  }, [])

  // Mapping-Validierung
  const hasJahrMapping = Object.values(mappings).includes('jahr') || datumSpalte != null
  const hasMonatMapping = Object.values(mappings).includes('monat') || datumSpalte != null
  const hasAnyValueMapping = Object.values(mappings).some(v =>
    v !== 'jahr' && v !== 'monat' && v !== ''
  )
  const mappingValid = hasJahrMapping && hasMonatMapping && hasAnyValueMapping

  // ── Step 3: Preview ───────────────────────────────────────────────────────

  const handlePreview = useCallback(async () => {
    if (!file) return
    setIsPreviewing(true)
    setError(null)

    try {
      const config = buildMappingConfig()
      const result = await customImportApi.preview(file, config)
      setPreview(result)
      const keys = new Set(result.monate.map(m => `${m.jahr}-${m.monat}`))
      setSelectedMonths(keys)
      setCurrentStep(2)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Vorschau fehlgeschlagen')
    } finally {
      setIsPreviewing(false)
    }
  }, [file, buildMappingConfig])

  const toggleMonth = useCallback((key: string) => {
    setSelectedMonths(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const toggleAll = useCallback(() => {
    if (!preview) return
    const allKeys = preview.monate.map(m => `${m.jahr}-${m.monat}`)
    if (selectedMonths.size === allKeys.length) {
      setSelectedMonths(new Set())
    } else {
      setSelectedMonths(new Set(allKeys))
    }
  }, [preview, selectedMonths])

  // ── Step 4: Import ────────────────────────────────────────────────────────

  const handleImport = useCallback(async () => {
    if (!preview || !selectedAnlageId) return
    setIsImporting(true)
    setError(null)

    const monate = preview.monate.filter(m =>
      selectedMonths.has(`${m.jahr}-${m.monat}`)
    )

    try {
      const result = await portalImportApi.apply(
        selectedAnlageId,
        monate,
        ueberschreiben,
        'custom_import'
      )
      setResult(result)
      setCurrentStep(3)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import fehlgeschlagen')
    } finally {
      setIsImporting(false)
    }
  }, [preview, selectedAnlageId, selectedMonths, ueberschreiben])

  // ── Render ──────────────────────────────────────────────────────────────

  const steps = [
    { title: 'Datei wählen', icon: <Upload className="w-4 h-4" /> },
    { title: 'Mapping', icon: <Settings2 className="w-4 h-4" /> },
    { title: 'Vorschau', icon: <Search className="w-4 h-4" /> },
    { title: 'Ergebnis', icon: <CheckCircle className="w-4 h-4" /> },
  ]

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <FileSpreadsheet className="w-6 h-6 text-primary-500" />
          Eigene Datei importieren
        </h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          CSV oder JSON-Datei hochladen und Spalten den EEDC-Feldern zuordnen
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
              <span className="hidden sm:inline">{step.title}</span>
            </div>
          </div>
        ))}
      </div>

      {error && (
        <Alert type="error" title="Fehler" onClose={() => setError(null)} className="mb-4">
          {error}
        </Alert>
      )}

      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {/* Step 1: Datei hochladen */}
      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {currentStep === 0 && (
        <Card>
          <div className="p-5">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
              Datei hochladen
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              CSV- oder JSON-Datei mit monatlichen Energiedaten. Die Spalten werden automatisch erkannt.
            </p>
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
              {isAnalyzing ? (
                <>
                  <Loader2 className="w-12 h-12 mx-auto text-primary-500 mb-3 animate-spin" />
                  <p className="text-gray-700 dark:text-gray-300 font-medium">Datei wird analysiert...</p>
                </>
              ) : (
                <>
                  <Upload className="w-12 h-12 mx-auto text-gray-400 mb-3" />
                  <p className="text-gray-700 dark:text-gray-300 font-medium">
                    Datei hier ablegen oder klicken
                  </p>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    Unterstützt: CSV (Semikolon, Komma, Tab) und JSON
                  </p>
                </>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.CSV,.json,.JSON"
                onChange={handleFileSelect}
                className="hidden"
              />
            </div>
          </div>
        </Card>
      )}

      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {/* Step 2: Feld-Mapping */}
      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {currentStep === 1 && analysis && (
        <div className="space-y-4">
          {/* Info */}
          <Alert type="info">
            <strong>{analysis.dateiname}</strong> – {analysis.zeilen_gesamt} Zeilen, {analysis.spalten.length} Spalten erkannt ({analysis.format.toUpperCase()})
          </Alert>

          {/* Templates */}
          {templates.length > 0 && (
            <Card>
              <div className="p-4">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                  Gespeicherte Mappings
                </h3>
                <div className="flex flex-wrap gap-2">
                  {templates.map(t => (
                    <div key={t.name} className="flex items-center gap-1">
                      <button
                        onClick={() => applyTemplate(t)}
                        className="px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300"
                      >
                        {t.name}
                      </button>
                      <button
                        onClick={() => handleDeleteTemplate(t.name)}
                        className="p-1 text-gray-400 hover:text-red-500"
                        title="Template löschen"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          )}

          {/* Mapping-Tabelle */}
          <Card>
            <div className="p-4">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                Spalten zuordnen
              </h3>
              <div className="space-y-2">
                {analysis.spalten.map(col => {
                  const currentMapping = mappings[col.name] || ''
                  return (
                    <div key={col.name} className="flex items-center gap-3 py-2 border-b border-gray-100 dark:border-gray-800 last:border-0">
                      {/* Quelltitel + Samples */}
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm text-gray-900 dark:text-white truncate">
                          {col.name}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                          {col.sample_values.slice(0, 3).join(' | ')}
                        </div>
                      </div>

                      {/* Pfeil */}
                      <ArrowRight className="w-4 h-4 text-gray-400 flex-shrink-0" />

                      {/* Dropdown */}
                      <select
                        value={currentMapping}
                        onChange={(e) => setMapping(col.name, e.target.value)}
                        className={`w-48 px-2 py-1.5 text-sm border rounded-lg
                          ${currentMapping
                            ? 'border-primary-300 bg-primary-50 dark:bg-primary-900/20 dark:border-primary-600 text-primary-700 dark:text-primary-300'
                            : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                          }
                          focus:ring-2 focus:ring-primary-500`}
                      >
                        <option value="">– Ignorieren –</option>
                        <optgroup label="Zeit">
                          <option value="jahr" disabled={Object.values(mappings).includes('jahr') && currentMapping !== 'jahr'}>Jahr</option>
                          <option value="monat" disabled={Object.values(mappings).includes('monat') && currentMapping !== 'monat'}>Monat</option>
                        </optgroup>
                        <optgroup label="Energie">
                          <option value="pv_erzeugung_kwh">PV-Erzeugung (kWh)</option>
                          <option value="einspeisung_kwh">Einspeisung (kWh)</option>
                          <option value="netzbezug_kwh">Netzbezug (kWh)</option>
                          <option value="eigenverbrauch_kwh">Eigenverbrauch (kWh)</option>
                        </optgroup>
                        <optgroup label="Batterie">
                          <option value="batterie_ladung_kwh">Batterie Ladung (kWh)</option>
                          <option value="batterie_entladung_kwh">Batterie Entladung (kWh)</option>
                        </optgroup>
                        <optgroup label="Wallbox / E-Auto">
                          <option value="wallbox_ladung_kwh">Wallbox Ladung (kWh)</option>
                          <option value="wallbox_ladung_pv_kwh">Wallbox PV-Ladung (kWh)</option>
                          <option value="wallbox_ladevorgaenge">Wallbox Ladevorgänge</option>
                          <option value="eauto_km_gefahren">E-Auto km gefahren</option>
                        </optgroup>
                      </select>
                    </div>
                  )
                })}
              </div>
            </div>
          </Card>

          {/* Optionen */}
          <Card>
            <div className="p-4">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                Optionen
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                    Einheit der Werte
                  </label>
                  <select
                    value={einheit}
                    onChange={(e) => setEinheit(e.target.value)}
                    className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                  >
                    <option value="kwh">Kilowattstunden (kWh)</option>
                    <option value="wh">Wattstunden (Wh) → wird in kWh umgerechnet</option>
                    <option value="mwh">Megawattstunden (MWh) → wird in kWh umgerechnet</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                    Dezimalzeichen
                  </label>
                  <select
                    value={dezimalzeichen}
                    onChange={(e) => setDezimalzeichen(e.target.value)}
                    className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                  >
                    <option value="auto">Automatisch erkennen</option>
                    <option value="punkt">Punkt (1234.56)</option>
                    <option value="komma">Komma (1234,56)</option>
                  </select>
                </div>
              </div>

              {/* Datumsspalte (optional) */}
              <div className="mt-4">
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                  Kombinierte Datumsspalte (optional, falls Jahr+Monat in einer Spalte)
                </label>
                <div className="flex gap-2">
                  <select
                    value={datumSpalte || ''}
                    onChange={(e) => setDatumSpalte(e.target.value || null)}
                    className="flex-1 px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                  >
                    <option value="">Nicht verwendet (separate Jahr/Monat-Spalten)</option>
                    {analysis.spalten.map(col => (
                      <option key={col.name} value={col.name}>{col.name}</option>
                    ))}
                  </select>
                  {datumSpalte && (
                    <input
                      type="text"
                      value={datumFormat || ''}
                      onChange={(e) => setDatumFormat(e.target.value || null)}
                      placeholder="z.B. %Y-%m"
                      className="w-36 px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                    />
                  )}
                </div>
                {datumSpalte && (
                  <p className="mt-1 text-xs text-gray-500">
                    Formate: %Y-%m (2024-01), %m/%Y (01/2024), %d.%m.%Y (15.01.2024)
                  </p>
                )}
              </div>
            </div>
          </Card>

          {/* Template speichern */}
          <Card>
            <div className="p-4">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                Mapping als Template speichern
              </h3>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  placeholder="Template-Name (z.B. 'Mein Netzbetreiber')"
                  className="flex-1 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                />
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleSaveTemplate}
                  loading={savingTemplate}
                  disabled={!templateName.trim() || !mappingValid}
                >
                  <Save className="w-4 h-4 mr-1" />
                  Speichern
                </Button>
              </div>
            </div>
          </Card>

          {/* Validierung + Navigation */}
          {!mappingValid && (
            <Alert type="warning">
              {!hasJahrMapping && !datumSpalte && 'Bitte eine Spalte für "Jahr" zuordnen. '}
              {!hasMonatMapping && !datumSpalte && 'Bitte eine Spalte für "Monat" zuordnen. '}
              {!hasAnyValueMapping && 'Bitte mindestens ein Energiefeld zuordnen.'}
              {!hasJahrMapping && !hasMonatMapping && datumSpalte == null && (
                <span className="block mt-1 text-xs">
                  Alternativ eine kombinierte Datumsspalte unter "Optionen" wählen.
                </span>
              )}
            </Alert>
          )}

          <div className="flex items-center justify-between">
            <Button
              variant="ghost"
              onClick={() => { setCurrentStep(0); setAnalysis(null); setFile(null) }}
            >
              <ChevronLeft className="w-4 h-4 mr-1" />
              Zurück
            </Button>
            <Button
              variant="primary"
              onClick={handlePreview}
              loading={isPreviewing}
              disabled={!mappingValid}
            >
              {isPreviewing ? 'Vorschau laden...' : 'Vorschau'}
              {!isPreviewing && <ChevronRight className="w-4 h-4 ml-1" />}
            </Button>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {/* Step 3: Vorschau & Auswahl */}
      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {currentStep === 2 && preview && (
        <div className="space-y-4">
          <Alert type="info">
            {preview.anzahl_monate} Monate erkannt
            {preview.warnungen.length > 0 && (
              <span className="block text-xs mt-1">
                {preview.warnungen.join('. ')}
              </span>
            )}
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
                    onChange={(e) => { const v = Number(e.target.value); if (v) setSelectedAnlageId(v) }}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white
                      dark:bg-gray-700 dark:border-gray-600 dark:text-white
                      focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">Anlage wählen...</option>
                    {anlagen.map(a => (
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

          {/* Daten-Tabelle */}
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
                  {preview.monate.map(m => {
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
              onClick={() => setCurrentStep(1)}
            >
              <ChevronLeft className="w-4 h-4 mr-1" />
              Mapping anpassen
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

      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {/* Step 4: Ergebnis */}
      {/* ═══════════════════════════════════════════════════════════════════════ */}
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

          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              onClick={() => {
                setCurrentStep(0)
                setFile(null)
                setAnalysis(null)
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
