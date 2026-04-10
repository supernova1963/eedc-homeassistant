/**
 * DataImportWizard – Portal-Import Wizard
 *
 * Schritt 1: Hersteller & Datei wählen
 * Schritt 2: Vorschau & Monats-Auswahl
 * Schritt 3: Zuordnung (optional — nur wenn mehrere Investments gleichen Typs)
 * Schritt 4: Ergebnis
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
  GitMerge,
} from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Alert from '../components/ui/Alert'
import { anlagenApi } from '../api/anlagen'
import { portalImportApi } from '../api/portalImport'
import type {
  ParserInfo,
  PreviewResult,
  ApplyResult,
  ZuordnungInfo,
  ZuordnungInvestition,
  InvestitionsZuordnung,
} from '../api/portalImport'
import type { Anlage } from '../types'

const MONAT_NAMEN = [
  '', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
]

// ── Zuordnungs-Hilfsfunktionen ──────────────────────────────────────────────

function initPvZuordnung(module: ZuordnungInvestition[]): Record<number, number> {
  return Object.fromEntries(module.map((m) => [m.id, m.default_anteil]))
}

function initBatZuordnung(speicher: ZuordnungInvestition[]): Record<number, number> {
  return Object.fromEntries(speicher.map((s) => [s.id, s.default_anteil]))
}

function summeAnteil(zuordnung: Record<number, number>): number {
  return Object.values(zuordnung).reduce((a, b) => a + b, 0)
}

// ── Zuordnungs-Eingabe für eine Gruppe (PV oder Batterie) ───────────────────

function AnteilEingabe({
  investitionen,
  zuordnung,
  onChange,
  einheit,
}: {
  investitionen: ZuordnungInvestition[]
  zuordnung: Record<number, number>
  onChange: (id: number, wert: number) => void
  einheit: string
}) {
  const summe = summeAnteil(zuordnung)
  const fehler = Math.abs(summe - 100) > 0.5

  return (
    <div className="space-y-2">
      {investitionen.map((inv) => (
        <div key={inv.id} className="flex items-center gap-3">
          <div className="flex-1 text-sm text-gray-800 dark:text-gray-200">
            <span className="font-medium">{inv.bezeichnung}</span>
            {(inv.kwp != null || inv.kwh != null) && (
              <span className="text-gray-500 dark:text-gray-400 ml-1">
                ({inv.kwp != null ? `${inv.kwp} kWp` : `${inv.kwh} kWh`})
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 w-32">
            <input
              type="number"
              min={0}
              max={100}
              step={0.01}
              aria-label={`Anteil ${inv.bezeichnung} in Prozent`}
              value={zuordnung[inv.id] ?? 0}
              onChange={(e) => {
                const val = e.target.valueAsNumber
                if (!isNaN(val)) onChange(inv.id, val)
              }}
              className="w-20 px-2 py-1 text-sm border border-gray-300 rounded dark:border-gray-600
                dark:bg-gray-700 dark:text-white text-right focus:ring-1 focus:ring-primary-500"
            />
            <span className="text-sm text-gray-500">{einheit}</span>
          </div>
        </div>
      ))}
      <div className={`text-xs text-right pt-1 ${fehler ? 'text-red-500 font-medium' : 'text-gray-400'}`}>
        Summe: {summe.toFixed(1)} % {fehler && '— muss 100 % ergeben'}
      </div>
    </div>
  )
}

// ── Auswahl-Radio für Wallbox / E-Auto ──────────────────────────────────────

function AuswahlRadio({
  investitionen,
  selectedId,
  onChange,
}: {
  investitionen: ZuordnungInvestition[]
  selectedId: number | undefined
  onChange: (id: number) => void
}) {
  return (
    <div className="space-y-2">
      {investitionen.map((inv) => (
        <label key={inv.id} className="flex items-center gap-2 cursor-pointer">
          <input
            type="radio"
            name={`inv-${inv.id}`}
            checked={selectedId === inv.id}
            onChange={() => onChange(inv.id)}
            className="text-primary-600 focus:ring-primary-500"
          />
          <span className="text-sm text-gray-800 dark:text-gray-200">{inv.bezeichnung}</span>
        </label>
      ))}
    </div>
  )
}

// ── Hauptkomponente ──────────────────────────────────────────────────────────

export default function DataImportWizard() {
  const navigate = useNavigate()

  const [currentStep, setCurrentStep] = useState(0)
  const [error, setError] = useState<string | null>(null)

  // Step 1
  const [parsers, setParsers] = useState<ParserInfo[]>([])
  const [selectedParserId, setSelectedParserId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isParsing, setIsParsing] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Step 2
  const [preview, setPreview] = useState<PreviewResult | null>(null)
  const [selectedMonths, setSelectedMonths] = useState<Set<string>>(new Set())
  const [anlagen, setAnlagen] = useState<Anlage[]>([])
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)
  const [ueberschreiben, setUeberschreiben] = useState(false)

  // Step 3 (Zuordnung)
  const [zuordnungInfo, setZuordnungInfo] = useState<ZuordnungInfo | null>(null)
  const [isLoadingZuordnung, setIsLoadingZuordnung] = useState(false)
  const [pvZuordnung, setPvZuordnung] = useState<Record<number, number>>({})
  const [batZuordnung, setBatZuordnung] = useState<Record<number, number>>({})
  const [wallboxId, setWallboxId] = useState<number | undefined>()
  const [eautoId, setEautoId] = useState<number | undefined>()

  // Step 4
  const [isImporting, setIsImporting] = useState(false)
  const [result, setResult] = useState<ApplyResult | null>(null)

  useEffect(() => {
    portalImportApi.getParsers().then(setParsers).catch(() => {})
    anlagenApi.list().then((list) => {
      setAnlagen(list)
      if (list.length === 1) setSelectedAnlageId(list[0].id)
    }).catch(() => {})
  }, [])

  // Zuordnungs-Info laden wenn Anlage gewählt
  useEffect(() => {
    if (!selectedAnlageId) {
      setZuordnungInfo(null)
      return
    }
    setIsLoadingZuordnung(true)
    portalImportApi.getZuordnungInfo(selectedAnlageId)
      .then((info) => {
        setZuordnungInfo(info)
        // Defaults initialisieren
        setPvZuordnung(initPvZuordnung(info.pv_module))
        setBatZuordnung(initBatZuordnung(info.speicher))
        setWallboxId(info.wallboxen[0]?.id)
        setEautoId(info.eautos[0]?.id)
      })
      .catch(() => setZuordnungInfo(null))
      .finally(() => setIsLoadingZuordnung(false))
  }, [selectedAnlageId])

  // ── Step 1: Datei-Handling ────────────────────────────────────────────────

  const handleFile = useCallback(async (f: File) => {
    setFile(f)
    setError(null)
    setIsParsing(true)
    try {
      const res = await portalImportApi.preview(f, selectedParserId || undefined)
      setPreview(res)
      setSelectedMonths(new Set(res.monate.map((m) => `${m.jahr}-${m.monat}`)))
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
    if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0])
  }, [handleFile])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) handleFile(e.target.files[0])
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
    setSelectedMonths(
      selectedMonths.size === allKeys.length ? new Set() : new Set(allKeys)
    )
  }, [preview, selectedMonths])

  // ── Step 2 → 3/4: Weiter-Button ──────────────────────────────────────────

  const handleWeiter = useCallback(() => {
    if (zuordnungInfo?.benoetigt_zuordnung) {
      setCurrentStep(2)   // Zuordnungs-Schritt zeigen
    } else {
      handleImport()       // Direkt importieren
    }
  }, [zuordnungInfo])

  // ── Step 3/4: Import ausführen ────────────────────────────────────────────

  const handleImport = useCallback(async () => {
    if (!preview || !selectedAnlageId) return
    setIsImporting(true)
    setError(null)

    const monate = preview.monate.filter((m) =>
      selectedMonths.has(`${m.jahr}-${m.monat}`)
    )

    // Zuordnung nur übergeben wenn Zuordnungs-Schritt angezeigt wurde
    let zuordnung: InvestitionsZuordnung | undefined
    if (zuordnungInfo?.benoetigt_zuordnung) {
      zuordnung = {
        pv: pvZuordnung,
        batterie: batZuordnung,
        wallbox_id: wallboxId,
        eauto_id: eautoId,
      }
    }

    try {
      const res = await portalImportApi.apply(
        selectedAnlageId, monate, ueberschreiben, 'portal_import', zuordnung
      )
      setResult(res)
      setCurrentStep(zuordnungInfo?.benoetigt_zuordnung ? 3 : 2)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import fehlgeschlagen')
    } finally {
      setIsImporting(false)
    }
  }, [preview, selectedAnlageId, selectedMonths, ueberschreiben, zuordnungInfo,
      pvZuordnung, batZuordnung, wallboxId, eautoId])

  // ── Validierung Zuordnungs-Schritt ────────────────────────────────────────

  const pvGueltig = zuordnungInfo && zuordnungInfo.pv_module.length > 1
    ? Math.abs(summeAnteil(pvZuordnung) - 100) <= 0.5
    : true
  const batGueltig = zuordnungInfo && zuordnungInfo.speicher.length > 1
    ? Math.abs(summeAnteil(batZuordnung) - 100) <= 0.5
    : true
  const zuordnungGueltig = pvGueltig && batGueltig

  // ── Render ────────────────────────────────────────────────────────────────

  const hatZuordnung = zuordnungInfo?.benoetigt_zuordnung ?? false
  const steps = hatZuordnung
    ? [
        { title: 'Datei wählen', icon: <Upload className="w-4 h-4" /> },
        { title: 'Vorschau', icon: <Search className="w-4 h-4" /> },
        { title: 'Zuordnung', icon: <GitMerge className="w-4 h-4" /> },
        { title: 'Ergebnis', icon: <CheckCircle className="w-4 h-4" /> },
      ]
    : [
        { title: 'Datei wählen', icon: <Upload className="w-4 h-4" /> },
        { title: 'Vorschau', icon: <Search className="w-4 h-4" /> },
        { title: 'Ergebnis', icon: <CheckCircle className="w-4 h-4" /> },
      ]

  // Ergebnis-Schritt-Index ist 2 ohne Zuordnung, 3 mit
  const ergebnisStep = hatZuordnung ? 3 : 2

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
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium
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

      {/* ── Step 1: Datei & Hersteller ───────────────────────────────────── */}
      {currentStep === 0 && (
        <div className="space-y-6">
          <Card>
            <div className="p-5">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                Hersteller wählen
              </h2>
              <select
                aria-label="Hersteller wählen"
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
                  (*) Ungetestet – Feedback willkommen!
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
                  aria-label="CSV-Datei auswählen"
                  onChange={handleFileSelect}
                  className="hidden"
                />
              </div>
              {file && !isParsing && (
                <div className="mt-3 flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                  <FileSpreadsheet className="w-4 h-4" />
                  {file.name}
                  <button
                    type="button"
                    aria-label="Datei entfernen"
                    onClick={() => { setFile(null); setPreview(null) }}
                    className="ml-auto text-gray-400 hover:text-gray-600"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* ── Step 2: Vorschau & Auswahl ───────────────────────────────────── */}
      {currentStep === 1 && preview && (
        <div className="space-y-4">
          <Alert type="info">
            Erkannt: <strong>{preview.parser.name}</strong> – {preview.anzahl_monate} Monate gefunden
          </Alert>

          <Card>
            <div className="p-5">
              <div className="flex flex-wrap items-end gap-4">
                <div className="flex-1 min-w-[200px]">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Ziel-Anlage
                  </label>
                  <select
                    aria-label="Ziel-Anlage wählen"
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
                  {isLoadingZuordnung && (
                    <p className="text-xs text-gray-400 mt-1 flex items-center gap-1">
                      <Loader2 className="w-3 h-3 animate-spin" /> Investitionen werden geprüft...
                    </p>
                  )}
                  {zuordnungInfo?.benoetigt_zuordnung && !isLoadingZuordnung && (
                    <p className="text-xs text-amber-600 dark:text-amber-400 mt-1 flex items-center gap-1">
                      <GitMerge className="w-3 h-3" />
                      Mehrere Investitionen — Zuordnungs-Schritt folgt
                    </p>
                  )}
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

          <div className="flex items-center justify-between">
            <Button variant="ghost" onClick={() => { setCurrentStep(0); setPreview(null); setFile(null) }}>
              <ChevronLeft className="w-4 h-4 mr-1" /> Zurück
            </Button>
            <div className="text-sm text-gray-500 dark:text-gray-400">
              {selectedMonths.size} von {preview.monate.length} Monaten ausgewählt
            </div>
            <Button
              variant="primary"
              onClick={handleWeiter}
              loading={isImporting}
              disabled={selectedMonths.size === 0 || !selectedAnlageId || isLoadingZuordnung}
            >
              {zuordnungInfo?.benoetigt_zuordnung
                ? <>Weiter <ChevronRight className="w-4 h-4 ml-1" /></>
                : isImporting
                  ? 'Importiere...'
                  : <>{selectedMonths.size} Monate importieren <ChevronRight className="w-4 h-4 ml-1" /></>
              }
            </Button>
          </div>
        </div>
      )}

      {/* ── Step 3: Zuordnung ────────────────────────────────────────────── */}
      {currentStep === 2 && hatZuordnung && zuordnungInfo && (
        <div className="space-y-4">
          <Alert type="info" title="Investitions-Zuordnung">
            Für diese Anlage sind mehrere Investitionen des gleichen Typs vorhanden.
            Bitte legen Sie fest, wie die Import-Werte aufgeteilt werden sollen.
            Die Vorauswahl entspricht der proportionalen Verteilung.
          </Alert>

          {/* PV-Module */}
          {zuordnungInfo.pv_module.length > 1 && (
            <Card>
              <div className="p-5">
                <h3 className="font-semibold text-gray-900 dark:text-white mb-3">
                  PV-Erzeugung aufteilen
                </h3>
                <AnteilEingabe
                  investitionen={zuordnungInfo.pv_module}
                  zuordnung={pvZuordnung}
                  onChange={(id, wert) => setPvZuordnung((prev) => ({ ...prev, [id]: wert }))}
                  einheit="%"
                />
              </div>
            </Card>
          )}

          {/* Speicher */}
          {zuordnungInfo.speicher.length > 1 && (
            <Card>
              <div className="p-5">
                <h3 className="font-semibold text-gray-900 dark:text-white mb-3">
                  Batterie-Werte aufteilen
                </h3>
                <AnteilEingabe
                  investitionen={zuordnungInfo.speicher}
                  zuordnung={batZuordnung}
                  onChange={(id, wert) => setBatZuordnung((prev) => ({ ...prev, [id]: wert }))}
                  einheit="%"
                />
              </div>
            </Card>
          )}

          {/* Wallboxen */}
          {zuordnungInfo.wallboxen.length > 1 && (
            <Card>
              <div className="p-5">
                <h3 className="font-semibold text-gray-900 dark:text-white mb-3">
                  Wallbox auswählen
                </h3>
                <AuswahlRadio
                  investitionen={zuordnungInfo.wallboxen}
                  selectedId={wallboxId}
                  onChange={setWallboxId}
                />
              </div>
            </Card>
          )}

          {/* E-Autos */}
          {zuordnungInfo.eautos.length > 1 && (
            <Card>
              <div className="p-5">
                <h3 className="font-semibold text-gray-900 dark:text-white mb-3">
                  E-Auto auswählen
                </h3>
                <AuswahlRadio
                  investitionen={zuordnungInfo.eautos}
                  selectedId={eautoId}
                  onChange={setEautoId}
                />
              </div>
            </Card>
          )}

          <div className="flex items-center justify-between">
            <Button variant="ghost" onClick={() => setCurrentStep(1)}>
              <ChevronLeft className="w-4 h-4 mr-1" /> Zurück
            </Button>
            <Button
              variant="primary"
              onClick={handleImport}
              loading={isImporting}
              disabled={!zuordnungGueltig}
            >
              {isImporting
                ? 'Importiere...'
                : <>{selectedMonths.size} Monate importieren <ChevronRight className="w-4 h-4 ml-1" /></>
              }
            </Button>
          </div>
        </div>
      )}

      {/* ── Step 4 / 3: Ergebnis ─────────────────────────────────────────── */}
      {currentStep === ergebnisStep && result && (
        <div className="space-y-4">
          <Alert
            type={result.erfolg ? 'success' : 'warning'}
            title={result.erfolg ? 'Import erfolgreich' : 'Import mit Hinweisen'}
          >
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
                (z.B. Wärmepumpe, manuelle Korrekturen).
              </p>
            </Alert>
          )}

          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              onClick={() => {
                setCurrentStep(0); setFile(null); setPreview(null)
                setResult(null); setError(null)
              }}
            >
              <Upload className="w-4 h-4 mr-1" /> Weiteren Import starten
            </Button>
            {selectedAnlageId && (
              <Button variant="secondary" onClick={() => navigate(`/monatsabschluss/${selectedAnlageId}`)}>
                Monatsabschluss starten
              </Button>
            )}
            <Button variant="primary" onClick={() => navigate('/einstellungen/monatsdaten')}>
              <CheckCircle className="w-4 h-4 mr-1" /> Zur Monatsübersicht
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
