/**
 * HAImportSettings - Wizard für automatisierten HA-Datenimport
 *
 * v0.9.8: Erweitert um Sensor-Auswahl aus Home Assistant
 *
 * Schritte:
 * 1. Investitionen - Übersicht der erwarteten Felder
 * 2. Sensoren - Zuordnung von HA-Sensoren zu Feldern
 * 3. YAML - Generierte Konfiguration
 * 4. Anleitung - Setup-Guide
 */

import { useState, useEffect, useMemo } from 'react'
import {
  Home,
  RefreshCw,
  Loader2,
  Copy,
  CheckCircle,
  ChevronRight,
  ChevronLeft,
  FileCode,
  Settings,
  Zap,
  Info,
  AlertTriangle,
  Link,
  LinkOff,
  Search,
} from 'lucide-react'
import { haImportApi, anlagenApi } from '../api'
import type {
  InvestitionMitSensorFeldern,
  YamlResponse,
  HASensor,
  BasisSensorMapping,
  SensorMapping,
  SensorSuggestionsResponse,
} from '../api/haImport'
import type { Anlage } from '../types'

// Wizard Steps
type WizardStep = 'investitionen' | 'sensoren' | 'yaml' | 'anleitung'

// Sensor-Dropdown Komponente
interface SensorSelectProps {
  value: string
  onChange: (value: string) => void
  sensoren: HASensor[]
  suggestion?: string
  label: string
  placeholder?: string
}

function SensorSelect({ value, onChange, sensoren, suggestion, label, placeholder }: SensorSelectProps) {
  const [search, setSearch] = useState('')
  const [isOpen, setIsOpen] = useState(false)

  const filteredSensoren = useMemo(() => {
    if (!search) return sensoren
    const searchLower = search.toLowerCase()
    return sensoren.filter(
      s => s.entity_id.toLowerCase().includes(searchLower) ||
           (s.friendly_name || '').toLowerCase().includes(searchLower)
    )
  }, [sensoren, search])

  const selectedSensor = sensoren.find(s => s.entity_id === value)

  return (
    <div className="relative">
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
        {label}
      </label>
      <div className="relative">
        <input
          type="text"
          value={isOpen ? search : (value || '')}
          onChange={(e) => {
            setSearch(e.target.value)
            setIsOpen(true)
          }}
          onFocus={() => setIsOpen(true)}
          onBlur={() => setTimeout(() => setIsOpen(false), 200)}
          placeholder={placeholder || 'Sensor auswählen...'}
          className="input w-full pr-20"
        />
        {suggestion && !value && (
          <button
            type="button"
            onClick={() => onChange(suggestion)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-xs bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 px-2 py-1 rounded hover:bg-blue-200 dark:hover:bg-blue-800"
          >
            Vorschlag
          </button>
        )}
        {value && (
          <button
            type="button"
            onClick={() => onChange('')}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            ×
          </button>
        )}
      </div>
      {isOpen && filteredSensoren.length > 0 && (
        <div className="absolute z-10 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-60 overflow-auto">
          {suggestion && (
            <div
              className="px-3 py-2 bg-blue-50 dark:bg-blue-900/30 border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-blue-100 dark:hover:bg-blue-900/50"
              onClick={() => {
                onChange(suggestion)
                setIsOpen(false)
              }}
            >
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4 text-blue-500" />
                <span className="text-sm font-medium text-blue-700 dark:text-blue-300">
                  Vorschlag: {suggestion}
                </span>
              </div>
            </div>
          )}
          {filteredSensoren.map((sensor) => (
            <div
              key={sensor.entity_id}
              className={`px-3 py-2 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 ${
                sensor.entity_id === value ? 'bg-gray-100 dark:bg-gray-700' : ''
              }`}
              onClick={() => {
                onChange(sensor.entity_id)
                setIsOpen(false)
                setSearch('')
              }}
            >
              <div className="text-sm font-medium text-gray-900 dark:text-white">
                {sensor.entity_id}
              </div>
              {sensor.friendly_name && (
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  {sensor.friendly_name}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {selectedSensor && selectedSensor.friendly_name && (
        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {selectedSensor.friendly_name} ({selectedSensor.unit_of_measurement || 'N/A'})
        </div>
      )}
    </div>
  )
}

export default function HAImportSettings() {
  // State
  const [anlagen, setAnlagen] = useState<Anlage[]>([])
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)
  const [investitionen, setInvestitionen] = useState<InvestitionMitSensorFeldern[]>([])
  const [yamlData, setYamlData] = useState<YamlResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Wizard State
  const [currentStep, setCurrentStep] = useState<WizardStep>('investitionen')
  const [copiedYaml, setCopiedYaml] = useState(false)

  // HA-Sensoren State
  const [haSensors, setHaSensors] = useState<HASensor[]>([])
  const [haConnected, setHaConnected] = useState(false)
  const [haError, setHaError] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<SensorSuggestionsResponse | null>(null)

  // Sensor-Mapping State
  const [basisMapping, setBasisMapping] = useState<BasisSensorMapping>({})
  const [invMappings, setInvMappings] = useState<Record<number, Record<string, string>>>({})

  // Daten laden
  const loadAnlagen = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await anlagenApi.list()
      setAnlagen(data)
      if (data.length > 0 && !selectedAnlageId) {
        setSelectedAnlageId(data[0].id)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden')
    } finally {
      setLoading(false)
    }
  }

  const loadInvestitionen = async () => {
    if (!selectedAnlageId) return
    try {
      setLoading(true)
      const data = await haImportApi.getInvestitionenMitFeldern(selectedAnlageId)
      setInvestitionen(data)

      // Existierende Mappings aus parameter['ha_sensors'] laden
      const existingMappings: Record<number, Record<string, string>> = {}
      data.forEach(inv => {
        if (inv.parameter?.ha_sensors) {
          existingMappings[inv.id] = inv.parameter.ha_sensors as Record<string, string>
        }
      })
      setInvMappings(existingMappings)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden der Investitionen')
    } finally {
      setLoading(false)
    }
  }

  const loadHASensors = async () => {
    try {
      const response = await haImportApi.getHASensors()
      setHaSensors(response.sensoren)
      setHaConnected(response.connected)
      setHaError(response.fehler || null)

      // Vorschläge laden wenn verbunden
      if (response.connected && selectedAnlageId) {
        const suggestionsData = await haImportApi.getSensorSuggestions(selectedAnlageId)
        setSuggestions(suggestionsData)

        // Vorschläge als initiale Werte setzen wenn noch keine Mappings
        if (Object.keys(basisMapping).length === 0) {
          const newBasisMapping: BasisSensorMapping = {}
          if (suggestionsData.basis.einspeisung?.vorschlag) {
            newBasisMapping.einspeisung = suggestionsData.basis.einspeisung.vorschlag
          }
          if (suggestionsData.basis.netzbezug?.vorschlag) {
            newBasisMapping.netzbezug = suggestionsData.basis.netzbezug.vorschlag
          }
          if (suggestionsData.basis.pv_erzeugung?.vorschlag) {
            newBasisMapping.pv_erzeugung = suggestionsData.basis.pv_erzeugung.vorschlag
          }
          setBasisMapping(newBasisMapping)
        }
      }
    } catch (e) {
      setHaError(e instanceof Error ? e.message : 'Fehler beim Laden der HA-Sensoren')
    }
  }

  const saveMappingsAndGenerateYaml = async () => {
    if (!selectedAnlageId) return
    try {
      setLoading(true)

      // Mappings speichern
      const invMappingsList: SensorMapping[] = Object.entries(invMappings).map(([id, mappings]) => ({
        investition_id: parseInt(id),
        mappings,
      }))

      await haImportApi.saveCompleteSensorMapping(selectedAnlageId, {
        basis: basisMapping,
        investitionen: invMappingsList,
      })

      // YAML generieren mit Basis-Sensoren
      const data = await haImportApi.generateYaml(selectedAnlageId, basisMapping)
      setYamlData(data)
      setCurrentStep('yaml')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Generieren der YAML')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAnlagen()
  }, [])

  useEffect(() => {
    if (selectedAnlageId) {
      loadInvestitionen()
      setYamlData(null)
      setCurrentStep('investitionen')
      setSuggestions(null)
      setBasisMapping({})
      setInvMappings({})
    }
  }, [selectedAnlageId])

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedYaml(true)
      setTimeout(() => setCopiedYaml(false), 2000)
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = text
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      setCopiedYaml(true)
      setTimeout(() => setCopiedYaml(false), 2000)
    }
  }

  // Investitionstyp zu Icon und Farbe
  const getTypInfo = (typ: string) => {
    const mapping: Record<string, { label: string; color: string }> = {
      'e-auto': { label: 'E-Auto', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' },
      'speicher': { label: 'Speicher', color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' },
      'wallbox': { label: 'Wallbox', color: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200' },
      'waermepumpe': { label: 'Wärmepumpe', color: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200' },
      'pv-module': { label: 'PV-Module', color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200' },
      'balkonkraftwerk': { label: 'Balkonkraftwerk', color: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200' },
      'sonstiges': { label: 'Sonstiges', color: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200' },
    }
    return mapping[typ] || { label: typ, color: 'bg-gray-100 text-gray-800' }
  }

  const updateInvMapping = (invId: number, field: string, value: string) => {
    setInvMappings(prev => ({
      ...prev,
      [invId]: {
        ...prev[invId],
        [field]: value,
      },
    }))
  }

  // Zähle zugeordnete Sensoren
  const mappedCount = useMemo(() => {
    let count = 0
    if (basisMapping.einspeisung) count++
    if (basisMapping.netzbezug) count++
    if (basisMapping.pv_erzeugung) count++
    Object.values(invMappings).forEach(mapping => {
      count += Object.values(mapping).filter(v => v).length
    })
    return count
  }, [basisMapping, invMappings])

  // Zähle erwartete Felder
  const totalFields = useMemo(() => {
    let count = 3 // Basis: einspeisung, netzbezug, pv
    investitionen.forEach(inv => {
      count += inv.felder.length
    })
    return count
  }, [investitionen])

  if (loading && anlagen.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Home className="w-6 h-6" />
            HA Daten-Import
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Automatisierter Import von Monatsdaten aus Home Assistant
          </p>
        </div>
        <button
          onClick={loadAnlagen}
          className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          title="Neu laden"
        >
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      {/* Anlagen-Auswahl */}
      {anlagen.length > 1 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Anlage auswählen
          </label>
          <select
            value={selectedAnlageId || ''}
            onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
            className="input max-w-md"
          >
            {anlagen.map((a) => (
              <option key={a.id} value={a.id}>
                {a.anlagenname}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Wizard Steps */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        {/* Step Navigation */}
        <div className="border-b border-gray-200 dark:border-gray-700 px-6 py-4">
          <div className="flex items-center gap-2 overflow-x-auto">
            {[
              { key: 'investitionen', label: 'Investitionen', icon: Settings },
              { key: 'sensoren', label: 'Sensoren zuordnen', icon: Link },
              { key: 'yaml', label: 'YAML', icon: FileCode },
              { key: 'anleitung', label: 'Anleitung', icon: Info },
            ].map((step, idx) => (
              <button
                key={step.key}
                onClick={() => {
                  if (step.key === 'sensoren' && !haConnected) {
                    loadHASensors()
                  }
                  setCurrentStep(step.key as WizardStep)
                }}
                disabled={step.key === 'yaml' && !yamlData}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors whitespace-nowrap ${
                  currentStep === step.key
                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200'
                    : step.key === 'yaml' && !yamlData
                    ? 'text-gray-400 cursor-not-allowed'
                    : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700'
                }`}
              >
                <span className="flex items-center justify-center w-6 h-6 rounded-full bg-gray-200 dark:bg-gray-700 text-sm font-medium">
                  {idx + 1}
                </span>
                <step.icon className="w-4 h-4" />
                <span className="hidden sm:inline">{step.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Step Content */}
        <div className="p-6">
          {/* Step 1: Investitionen */}
          {currentStep === 'investitionen' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Aktive Investitionen
                </h2>
                <span className="text-sm text-gray-500">
                  {investitionen.length} Investitionen
                </span>
              </div>

              {investitionen.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <Settings className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>Keine aktiven Investitionen gefunden.</p>
                  <p className="text-sm mt-1">
                    Bitte legen Sie zuerst Investitionen unter Einstellungen → Investitionen an.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {investitionen.map((inv) => {
                    const typInfo = getTypInfo(inv.typ)
                    return (
                      <div
                        key={inv.id}
                        className="border border-gray-200 dark:border-gray-700 rounded-lg p-4"
                      >
                        <div className="flex items-center gap-3 mb-3">
                          <span className={`px-2 py-1 rounded text-xs font-medium ${typInfo.color}`}>
                            {typInfo.label}
                          </span>
                          <h3 className="font-medium text-gray-900 dark:text-white">
                            {inv.bezeichnung}
                          </h3>
                        </div>

                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                          {inv.felder.map((feld) => (
                            <div
                              key={feld.key}
                              className="text-sm bg-gray-50 dark:bg-gray-900 rounded px-3 py-2"
                            >
                              <span className="text-gray-600 dark:text-gray-400">
                                {feld.label}
                              </span>
                              <span className="text-gray-400 dark:text-gray-500 ml-1">
                                ({feld.unit})
                              </span>
                              {feld.required && (
                                <span className="text-red-500 ml-1">*</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}

              <div className="flex justify-end pt-4 border-t border-gray-200 dark:border-gray-700">
                <button
                  onClick={() => {
                    loadHASensors()
                    setCurrentStep('sensoren')
                  }}
                  disabled={loading || investitionen.length === 0}
                  className="btn btn-primary flex items-center gap-2"
                >
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                  Sensoren zuordnen
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Sensoren zuordnen */}
          {currentStep === 'sensoren' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  HA-Sensoren zuordnen
                </h2>
                <div className="flex items-center gap-4">
                  <span className="text-sm text-gray-500">
                    {mappedCount} / {totalFields} zugeordnet
                  </span>
                  {haConnected ? (
                    <span className="flex items-center gap-1 text-sm text-green-600 dark:text-green-400">
                      <Link className="w-4 h-4" />
                      HA verbunden
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-sm text-red-600 dark:text-red-400">
                      <LinkOff className="w-4 h-4" />
                      Nicht verbunden
                    </span>
                  )}
                </div>
              </div>

              {haError && (
                <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-yellow-700 dark:text-yellow-300">{haError}</p>
                      <p className="text-sm text-yellow-600 dark:text-yellow-400 mt-1">
                        Sie können die Sensor-IDs auch manuell eingeben.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Basis-Sensoren */}
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <h3 className="font-medium text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                  <Zap className="w-4 h-4 text-yellow-500" />
                  Basis-Energiedaten
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <SensorSelect
                    label="Einspeisung (kWh)"
                    value={basisMapping.einspeisung || ''}
                    onChange={(v) => setBasisMapping(prev => ({ ...prev, einspeisung: v }))}
                    sensoren={haSensors}
                    suggestion={suggestions?.basis.einspeisung?.vorschlag}
                    placeholder="sensor.grid_export_energy"
                  />
                  <SensorSelect
                    label="Netzbezug (kWh)"
                    value={basisMapping.netzbezug || ''}
                    onChange={(v) => setBasisMapping(prev => ({ ...prev, netzbezug: v }))}
                    sensoren={haSensors}
                    suggestion={suggestions?.basis.netzbezug?.vorschlag}
                    placeholder="sensor.grid_import_energy"
                  />
                  <SensorSelect
                    label="PV-Erzeugung (kWh)"
                    value={basisMapping.pv_erzeugung || ''}
                    onChange={(v) => setBasisMapping(prev => ({ ...prev, pv_erzeugung: v }))}
                    sensoren={haSensors}
                    suggestion={suggestions?.basis.pv_erzeugung?.vorschlag}
                    placeholder="sensor.pv_energy_total"
                  />
                </div>
              </div>

              {/* Investitions-Sensoren */}
              {investitionen.map((inv) => {
                const typInfo = getTypInfo(inv.typ)
                const invSuggestions = suggestions?.investitionen[String(inv.id)]

                return (
                  <div
                    key={inv.id}
                    className="border border-gray-200 dark:border-gray-700 rounded-lg p-4"
                  >
                    <h3 className="font-medium text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${typInfo.color}`}>
                        {typInfo.label}
                      </span>
                      {inv.bezeichnung}
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {inv.felder.map((feld) => (
                        <SensorSelect
                          key={feld.key}
                          label={`${feld.label} (${feld.unit})`}
                          value={invMappings[inv.id]?.[feld.key] || ''}
                          onChange={(v) => updateInvMapping(inv.id, feld.key, v)}
                          sensoren={haSensors}
                          suggestion={invSuggestions?.felder[feld.key]?.vorschlag}
                          placeholder={`sensor.${inv.bezeichnung.toLowerCase().replace(/\s+/g, '_')}_${feld.key}`}
                        />
                      ))}
                    </div>
                  </div>
                )
              })}

              <div className="flex justify-between pt-4 border-t border-gray-200 dark:border-gray-700">
                <button
                  onClick={() => setCurrentStep('investitionen')}
                  className="btn btn-secondary flex items-center gap-2"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Zurück
                </button>
                <button
                  onClick={saveMappingsAndGenerateYaml}
                  disabled={loading}
                  className="btn btn-primary flex items-center gap-2"
                >
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                  YAML generieren
                </button>
              </div>
            </div>
          )}

          {/* Step 3: YAML */}
          {currentStep === 'yaml' && yamlData && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                    YAML-Konfiguration für {yamlData.anlage_name}
                  </h2>
                  {yamlData.has_placeholders && (
                    <p className="text-sm text-yellow-600 dark:text-yellow-400 mt-1">
                      ⚠️ Enthält noch Platzhalter - bitte in Schritt 2 zuordnen
                    </p>
                  )}
                </div>
                <button
                  onClick={() => copyToClipboard(yamlData.yaml)}
                  className="btn btn-secondary flex items-center gap-2"
                >
                  {copiedYaml ? (
                    <CheckCircle className="w-4 h-4 text-green-500" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                  {copiedYaml ? 'Kopiert!' : 'Kopieren'}
                </button>
              </div>

              <div className="bg-gray-900 rounded-lg overflow-hidden">
                <pre className="p-4 text-sm text-gray-100 overflow-x-auto max-h-[500px]">
                  <code>{yamlData.yaml}</code>
                </pre>
              </div>

              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                <h3 className="font-medium text-blue-800 dark:text-blue-200 flex items-center gap-2 mb-2">
                  <Info className="w-4 h-4" />
                  Hinweise
                </h3>
                <ul className="list-disc list-inside text-sm text-blue-700 dark:text-blue-300 space-y-1">
                  {yamlData.hinweise.map((h, i) => (
                    <li key={i}>{h}</li>
                  ))}
                </ul>
              </div>

              <div className="flex justify-between pt-4 border-t border-gray-200 dark:border-gray-700">
                <button
                  onClick={() => setCurrentStep('sensoren')}
                  className="btn btn-secondary flex items-center gap-2"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Sensoren bearbeiten
                </button>
                <button
                  onClick={() => setCurrentStep('anleitung')}
                  className="btn btn-primary flex items-center gap-2"
                >
                  <ChevronRight className="w-4 h-4" />
                  Weiter zur Anleitung
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Anleitung */}
          {currentStep === 'anleitung' && (
            <div className="space-y-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Einrichtung in Home Assistant
              </h2>

              <div className="space-y-4">
                {[
                  {
                    step: 1,
                    title: 'YAML kopieren',
                    description: 'Kopiere die generierte YAML-Konfiguration aus dem vorherigen Schritt.',
                  },
                  {
                    step: 2,
                    title: 'In configuration.yaml einfügen',
                    description: 'Füge die Konfiguration am Ende deiner configuration.yaml Datei ein. Falls du noch Platzhalter hast, ersetze diese mit deinen Sensor-IDs.',
                  },
                  {
                    step: 3,
                    title: 'Home Assistant neu starten',
                    description: 'Starte Home Assistant neu, damit die neuen Sensoren und die Automation aktiv werden.',
                  },
                  {
                    step: 4,
                    title: 'Utility Meter prüfen',
                    description: 'Prüfe unter Entwicklerwerkzeuge → Zustände, ob die neuen eedc_* Sensoren existieren.',
                  },
                  {
                    step: 5,
                    title: 'Automation testen (optional)',
                    description: 'Du kannst die Automation manuell auslösen oder auf den 1. des Monats warten.',
                  },
                ].map((item) => (
                  <div
                    key={item.step}
                    className="flex gap-4 p-4 bg-gray-50 dark:bg-gray-900 rounded-lg"
                  >
                    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-900 flex items-center justify-center">
                      <span className="text-sm font-bold text-blue-700 dark:text-blue-300">
                        {item.step}
                      </span>
                    </div>
                    <div>
                      <h3 className="font-medium text-gray-900 dark:text-white">
                        {item.title}
                      </h3>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        {item.description}
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
                <h3 className="font-medium text-yellow-800 dark:text-yellow-200 flex items-center gap-2 mb-2">
                  <AlertTriangle className="w-4 h-4" />
                  Wichtig
                </h3>
                <ul className="list-disc list-inside text-sm text-yellow-700 dark:text-yellow-300 space-y-1">
                  <li>Die Quell-Sensoren müssen Gesamtzähler sein (state_class: total_increasing)</li>
                  <li>Die Automation wird am 1. jeden Monats um 00:05 ausgeführt</li>
                  <li>Falls der Import fehlschlägt, prüfe das Home Assistant Log</li>
                  <li>EEDC muss unter der konfigurierten URL erreichbar sein</li>
                </ul>
              </div>

              <div className="flex justify-between pt-4 border-t border-gray-200 dark:border-gray-700">
                <button
                  onClick={() => setCurrentStep('yaml')}
                  className="btn btn-secondary flex items-center gap-2"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Zurück zur YAML
                </button>
                <button
                  onClick={() => setCurrentStep('investitionen')}
                  className="btn btn-primary flex items-center gap-2"
                >
                  <Zap className="w-4 h-4" />
                  Fertig
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
