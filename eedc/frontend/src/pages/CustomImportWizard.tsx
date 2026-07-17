/**
 * CustomImportWizard – Generischer CSV/JSON-Import mit benutzerdefiniertem Feld-Mapping
 *
 * 4-Schritt-Wizard:
 * 1. Datei hochladen → Spalten werden erkannt
 * 2. Spalten auf eedc-Felder mappen (mit Auto-Detect + Templates)
 * 3. Vorschau der gemappten Daten
 * 4. Ergebnis
 *
 * IA-V4 (Style-Guide Teil D): SoT-Controls (Input/Select/Checkbox/Stepper/Alert),
 * Schritt 2 in Sektionen ausgelagert (`components/import/custom/`), Ergebnis-
 * Schritt + Terminal-Nav im geteilten `ImportErgebnis`. Overlay-tauglich über
 * {@link useWizardHost} (W2/W5).
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
  Save,
  ArrowRight,
  X,
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
import MappingTabelle from '../components/import/custom/MappingTabelle'
import ImportOptionen from '../components/import/custom/ImportOptionen'
import { customImportApi } from '../api/customImport'
import type {
  AnalyzeResult,
  MappingConfig,
  FieldMapping,
  PreviewResult,
  TemplateInfo,
  ApplyResult,
} from '../api/customImport'
import { useSelectedAnlage } from '../hooks'
import { MONAT_NAMEN } from '../lib'

export default function CustomImportWizard() {
  const navigate = useNavigate()
  const host = useWizardHost()

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
  const [invertierungen, setInvertierungen] = useState<Record<string, boolean>>({})
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

  // W5: ungespeicherte Eingaben melden, solange noch nicht importiert wurde.
  const dirty = result === null && (file !== null || analysis !== null)
  useEffect(() => {
    host.setzeBlocker(dirty)
    return () => host.setzeBlocker(false)
  }, [dirty, host])

  // ── Step 1: Datei-Upload ──────────────────────────────────────────────────

  const handleFile = useCallback(async (f: File) => {
    setFile(f)
    setError(null)
    setIsAnalyzing(true)

    try {
      const result = await customImportApi.analyze(f, selectedAnlageId)
      setAnalysis(result)

      // Auto-Mapping setzen — Investitions-Spalten ausfiltern (werden automatisch importiert)
      const invSpaltenNames = new Set((result.investitions_spalten ?? []).map(i => i.spalte))
      const filteredMapping: Record<string, string> = {}
      for (const [k, v] of Object.entries(result.auto_mapping)) {
        if (!invSpaltenNames.has(k)) filteredMapping[k] = v
      }
      setMappings(filteredMapping)

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
    // `selectedAnlageId` MUSS in den Deps stehen: ohne sie analysiert ein Anlage-
    // Wechsel mitten im Wizard weiter gegen die alte Anlage (stale closure).
  }, [selectedAnlageId])

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

  const toggleInvert = useCallback((spalte: string) => {
    setInvertierungen(prev => ({ ...prev, [spalte]: !prev[spalte] }))
  }, [])

  const buildMappingConfig = useCallback((): MappingConfig => {
    const fieldMappings: FieldMapping[] = Object.entries(mappings)
      .filter(([, v]) => v !== '')
      .map(([spalte, eedc_feld]) => ({
        spalte,
        eedc_feld,
        ...(invertierungen[spalte] ? { invertieren: true } : {}),
      }))

    return {
      mappings: fieldMappings,
      einheit,
      dezimalzeichen,
      datum_spalte: datumSpalte,
      datum_format: datumFormat,
    }
  }, [mappings, invertierungen, einheit, dezimalzeichen, datumSpalte, datumFormat])

  const applyTemplate = useCallback((template: TemplateInfo) => {
    const newMappings: Record<string, string> = {}
    const newInvertierungen: Record<string, boolean> = {}
    for (const m of template.mapping.mappings) {
      newMappings[m.spalte] = m.eedc_feld
      if (m.invertieren) newInvertierungen[m.spalte] = true
    }
    setMappings(newMappings)
    setInvertierungen(newInvertierungen)
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
  const hasAnyValueMapping =
    Object.values(mappings).some(v => v !== 'jahr' && v !== 'monat' && v !== '') ||
    (analysis?.investitions_spalten?.length ?? 0) > 0
  const mappingValid = hasJahrMapping && hasMonatMapping && hasAnyValueMapping

  // ── Step 3: Preview ───────────────────────────────────────────────────────

  const handlePreview = useCallback(async () => {
    if (!file) return
    setIsPreviewing(true)
    setError(null)

    try {
      const config = buildMappingConfig()
      const result = await customImportApi.preview(file, config, selectedAnlageId)
      setPreview(result)
      const keys = new Set(result.monate.map(m => `${m.jahr}-${m.monat}`))
      setSelectedMonths(keys)
      setCurrentStep(2)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Vorschau fehlgeschlagen')
    } finally {
      setIsPreviewing(false)
    }
    // s. o.: sonst zeigt die Vorschau die Werte der zuvor gewählten Anlage.
  }, [file, buildMappingConfig, selectedAnlageId])

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
    if (!preview || !selectedAnlageId || !file) return
    setIsImporting(true)
    setError(null)

    const selectedMonthList = preview.monate
      .filter(m => selectedMonths.has(`${m.jahr}-${m.monat}`))
      .map(m => ({ jahr: m.jahr, monat: m.monat }))

    try {
      const result = await customImportApi.apply(
        selectedAnlageId,
        file,
        buildMappingConfig(),
        selectedMonthList,
        ueberschreiben,
      )
      setResult(result)
      setCurrentStep(3)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import fehlgeschlagen')
    } finally {
      setIsImporting(false)
    }
  }, [preview, selectedAnlageId, file, selectedMonths, ueberschreiben, buildMappingConfig])

  // W3: Abbrechen — im Overlay Dirty-geschützt schließen, sonst zurück navigieren.
  const handleAbbrechen = useCallback(() => {
    if (host.imOverlay) host.abbrechen()
    else navigate(-1)
  }, [host, navigate])

  // ── Render ──────────────────────────────────────────────────────────────

  const steps = [
    { titel: 'Datei wählen' },
    { titel: 'Mapping' },
    { titel: 'Vorschau' },
    { titel: 'Ergebnis' },
  ]

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <FileSpreadsheet className="w-6 h-6 text-primary-500" />
          Eigene Datei importieren
        </h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          CSV oder JSON-Datei hochladen und Spalten den eedc-Feldern zuordnen
        </p>
      </div>

      {/* Stepper (W1) */}
      <Stepper schritte={steps} aktuell={currentStep} className="mb-6" />

      {error && (
        <Alert type="error" title="Fehler" onClose={() => setError(null)} className="mb-4">
          {error}
        </Alert>
      )}

      {/* Step 1: Datei hochladen */}
      {currentStep === 0 && (
        <Card>
          <div className="p-5">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
              Datei hochladen
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              CSV- oder JSON-Datei mit monatlichen Energiedaten. Die Spalten werden automatisch erkannt.
            </p>

            {/* Anlage wählen (optional, für eedc-Vorlage) */}
            {anlagen.length > 0 && (
              <div className="mb-4 sm:max-w-md">
                <Select
                  label="Anlage wählen"
                  hint="empfohlen – für automatische Erkennung von Investitions-Spalten"
                  value={selectedAnlageId ?? ''}
                  onChange={(e) => { const v = Number(e.target.value); if (v) setSelectedAnlageId(v) }}
                  placeholder="Anlage wählen…"
                  options={anlagen.map(a => ({ value: String(a.id), label: `${a.anlagenname} (${a.leistung_kwp} kWp)` }))}
                />
              </div>
            )}
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
                  <p className="text-gray-700 dark:text-gray-300 font-medium">Datei wird analysiert…</p>
                </>
              ) : (
                <>
                  <Upload className="w-12 h-12 mx-auto text-gray-400 dark:text-gray-500 mb-3" />
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
                aria-label="CSV oder JSON Datei auswählen"
                className="hidden"
              />
            </div>

            {/* Navigation (W3) */}
            <div className="flex justify-start mt-5">
              <Button variant="ghost" onClick={handleAbbrechen}>
                Abbrechen
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Step 2: Feld-Mapping */}
      {currentStep === 1 && analysis && (
        <div className="space-y-4">
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
                      <Button type="button" variant="secondary" size="sm" onClick={() => applyTemplate(t)}>
                        {t.name}
                      </Button>
                      <Button
                        type="button" variant="ghost" size="icon"
                        onClick={() => handleDeleteTemplate(t.name)}
                        aria-label="Template löschen" title="Template löschen"
                      >
                        <X className="w-3 h-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          )}

          {/* Mapping-Tabelle (ausgelagert) */}
          <MappingTabelle
            analysis={analysis}
            mappings={mappings}
            invertierungen={invertierungen}
            onSetMapping={setMapping}
            onToggleInvert={toggleInvert}
          />

          {/* Investitions-Spalten (eedc-Vorlage) */}
          {(analysis.investitions_spalten?.length ?? 0) > 0 && (
            <Card>
              <div className="p-4">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
                  eedc-Investitions-Spalten erkannt
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                  Diese Spalten werden beim Import automatisch den jeweiligen Investitionen zugeordnet.
                </p>
                <div className="space-y-1">
                  {analysis.investitions_spalten.map(inv => (
                    <div key={inv.spalte} className="flex items-center gap-2 text-sm py-1">
                      <span className="font-mono text-gray-600 dark:text-gray-400 text-xs bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded flex-shrink-0">
                        {inv.spalte}
                      </span>
                      <ArrowRight className="w-3 h-3 text-gray-400 dark:text-gray-500 flex-shrink-0" />
                      <span className="text-gray-700 dark:text-gray-300">
                        {inv.inv_bezeichnung}
                        <span className="text-gray-400 dark:text-gray-500 ml-1">({inv.suffix})</span>
                      </span>
                      <CheckCircle className="w-3.5 h-3.5 text-green-500 flex-shrink-0 ml-auto" />
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          )}

          {/* Optionen (ausgelagert) */}
          <ImportOptionen
            einheit={einheit}
            onEinheit={setEinheit}
            dezimalzeichen={dezimalzeichen}
            onDezimalzeichen={setDezimalzeichen}
            datumSpalte={datumSpalte}
            onDatumSpalte={setDatumSpalte}
            datumFormat={datumFormat}
            onDatumFormat={setDatumFormat}
            spalten={analysis.spalten}
          />

          {/* Template speichern */}
          <Card>
            <div className="p-4">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                Mapping als Template speichern
              </h3>
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <Input
                    aria-label="Template-Name"
                    value={templateName}
                    onChange={(e) => setTemplateName(e.target.value)}
                    placeholder="Template-Name (z.B. 'Mein Netzbetreiber')"
                  />
                </div>
                <Button
                  variant="secondary"
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

          {/* Validierung */}
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

          {/* Navigation (W3) */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Button variant="ghost" onClick={handleAbbrechen}>
                Abbrechen
              </Button>
              <Button variant="ghost" onClick={() => { setCurrentStep(0); setAnalysis(null); setFile(null) }}>
                <ChevronLeft className="w-4 h-4 mr-1" />
                Zurück
              </Button>
            </div>
            <Button
              variant="primary"
              onClick={handlePreview}
              loading={isPreviewing}
              disabled={!mappingValid}
            >
              {isPreviewing ? 'Vorschau laden…' : 'Vorschau'}
              {!isPreviewing && <ChevronRight className="w-4 h-4 ml-1" />}
            </Button>
          </div>
        </div>
      )}

      {/* Step 3: Vorschau & Auswahl */}
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

          {/* Anlage + Optionen */}
          <Card>
            <div className="p-4 flex flex-wrap items-end gap-4">
              {!selectedAnlageId && (
                <div className="flex-1 min-w-[200px]">
                  <Select
                    label="Ziel-Anlage"
                    value={selectedAnlageId ?? ''}
                    onChange={(e) => { const v = Number(e.target.value); if (v) setSelectedAnlageId(v) }}
                    placeholder="Anlage wählen…"
                    options={anlagen.map(a => ({ value: String(a.id), label: `${a.anlagenname} (${a.leistung_kwp} kWp)` }))}
                  />
                </div>
              )}
              {selectedAnlageId && (
                <div className="text-sm text-gray-700 dark:text-gray-300">
                  Ziel-Anlage: <strong>{anlagen.find(a => a.id === selectedAnlageId)?.anlagenname}</strong>
                </div>
              )}
              <div className="pb-2">
                <Checkbox
                  label="Bestehende Monate überschreiben"
                  checked={ueberschreiben}
                  onChange={(e) => setUeberschreiben(e.target.checked)}
                />
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
                    {(preview.inv_spalten ?? []).map(sp => (
                      <th key={sp} className="px-4 py-3 text-right font-medium text-gray-700 dark:text-gray-300" title={sp}>
                        {sp}
                      </th>
                    ))}
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
                          {/* stopPropagation: sonst feuert zusätzlich der onClick der <tr>
                              und das Toggle hebt sich auf → einzelne Monate ließen sich
                              nicht abwählen (#72). */}
                          <div onClick={e => e.stopPropagation()}>
                            <Checkbox
                              checked={selected}
                              onChange={() => toggleMonth(key)}
                              label={<span className="text-gray-900 dark:text-white">{MONAT_NAMEN[m.monat]} {m.jahr}</span>}
                            />
                          </div>
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
                        {(preview.inv_spalten ?? []).map(sp => (
                          <td key={sp} className="px-4 py-2.5 text-right text-gray-700 dark:text-gray-300 tabular-nums">
                            {m.inv_werte?.[sp] !== undefined ? m.inv_werte[sp].toFixed(1) : '–'}
                          </td>
                        ))}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Navigation (W3) */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Button variant="ghost" onClick={handleAbbrechen}>
                Abbrechen
              </Button>
              <Button variant="ghost" onClick={() => setCurrentStep(1)}>
                <ChevronLeft className="w-4 h-4 mr-1" />
                Mapping anpassen
              </Button>
            </div>
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
                {isImporting ? 'Importiere…' : `${selectedMonths.size} Monate importieren`}
                {!isImporting && <ChevronRight className="w-4 h-4 ml-1" />}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Step 4: Ergebnis */}
      {currentStep === 3 && result && (
        <ImportErgebnis
          result={result}
          selectedAnlageId={selectedAnlageId ?? null}
          weiterIcon={<Upload className="w-4 h-4 mr-1" />}
          onWeiter={() => {
            setCurrentStep(0)
            setFile(null)
            setAnalysis(null)
            setPreview(null)
            setResult(null)
            setError(null)
          }}
        />
      )}
    </div>
  )
}
