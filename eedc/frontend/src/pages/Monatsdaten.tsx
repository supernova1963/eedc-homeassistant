import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Calendar, Edit, Trash2, AlertCircle, Columns, AlertTriangle, Database, Loader2 } from 'lucide-react'
import { Button, Card, Modal, EmptyState, LoadingSpinner, Alert, Select } from '../components/ui'
import { Table, TableHead, TableBody, TableRow, TableHeader, TableCell } from '../components/ui'
import { MonatsdatenForm } from '../components/forms'
import { useAnlagen, useMonatsdaten, useInvestitionen } from '../hooks'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
import { haStatisticsApi, type Monatswerte, type VerfuegbarerMonat } from '../api/haStatistics'
import type { Monatsdaten } from '../types'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

// Spalten-Gruppen für bessere Übersicht
interface ColumnConfig {
  key: string
  label: string
  shortLabel?: string
  group: 'zaehler' | 'komponenten' | 'berechnet'
  getValue: (md: AggregierteMonatsdaten) => number | null
  format?: 'kwh' | 'percent'
  className?: string
  defaultVisible: boolean
}

const COLUMN_GROUPS = {
  zaehler: { label: 'Zählerwerte', color: 'bg-blue-500' },
  komponenten: { label: 'Komponenten', color: 'bg-amber-500' },
  berechnet: { label: 'Berechnungen', color: 'bg-green-500' },
}

const COLUMNS: ColumnConfig[] = [
  // Zählerwerte (aus Monatsdaten - direkt gemessen)
  {
    key: 'einspeisung',
    label: 'Einspeisung',
    shortLabel: 'Einsp.',
    group: 'zaehler',
    getValue: (md) => md.einspeisung_kwh,
    format: 'kwh',
    defaultVisible: true,
  },
  {
    key: 'netzbezug',
    label: 'Netzbezug',
    shortLabel: 'Netz',
    group: 'zaehler',
    getValue: (md) => md.netzbezug_kwh,
    format: 'kwh',
    defaultVisible: true,
  },
  // Komponenten (aggregiert aus InvestitionMonatsdaten)
  {
    key: 'pv_erzeugung',
    label: 'PV-Erzeugung',
    shortLabel: 'PV',
    group: 'komponenten',
    getValue: (md) => md.pv_erzeugung_kwh,
    format: 'kwh',
    defaultVisible: true,
  },
  {
    key: 'speicher_ladung',
    label: 'Speicher Ladung',
    shortLabel: 'Sp.Lad',
    group: 'komponenten',
    getValue: (md) => md.speicher_ladung_kwh,
    format: 'kwh',
    defaultVisible: false,
  },
  {
    key: 'speicher_entladung',
    label: 'Speicher Entladung',
    shortLabel: 'Sp.Entl',
    group: 'komponenten',
    getValue: (md) => md.speicher_entladung_kwh,
    format: 'kwh',
    defaultVisible: false,
  },
  {
    key: 'wp_strom',
    label: 'WP Strom',
    shortLabel: 'WP',
    group: 'komponenten',
    getValue: (md) => md.wp_strom_kwh,
    format: 'kwh',
    defaultVisible: false,
  },
  {
    key: 'wp_heizung',
    label: 'WP Heizung',
    shortLabel: 'WP Hz',
    group: 'komponenten',
    getValue: (md) => md.wp_heizung_kwh,
    format: 'kwh',
    defaultVisible: false,
  },
  {
    key: 'wp_warmwasser',
    label: 'WP Warmwasser',
    shortLabel: 'WP WW',
    group: 'komponenten',
    getValue: (md) => md.wp_warmwasser_kwh,
    format: 'kwh',
    defaultVisible: false,
  },
  {
    key: 'eauto_ladung',
    label: 'E-Auto Ladung',
    shortLabel: 'E-Auto',
    group: 'komponenten',
    getValue: (md) => md.eauto_ladung_kwh,
    format: 'kwh',
    defaultVisible: false,
  },
  {
    key: 'eauto_km',
    label: 'E-Auto km',
    shortLabel: 'km',
    group: 'komponenten',
    getValue: (md) => md.eauto_km,
    defaultVisible: false,
  },
  {
    key: 'wallbox_ladung',
    label: 'Wallbox Ladung',
    shortLabel: 'WB',
    group: 'komponenten',
    getValue: (md) => md.wallbox_ladung_kwh,
    format: 'kwh',
    defaultVisible: false,
  },
  // Berechnete Werte
  {
    key: 'direktverbrauch',
    label: 'Direktverbrauch',
    shortLabel: 'Direkt',
    group: 'berechnet',
    getValue: (md) => md.direktverbrauch_kwh,
    format: 'kwh',
    defaultVisible: false,
  },
  {
    key: 'eigenverbrauch',
    label: 'Eigenverbrauch',
    shortLabel: 'Eigen',
    group: 'berechnet',
    getValue: (md) => md.eigenverbrauch_kwh,
    format: 'kwh',
    defaultVisible: true,
  },
  {
    key: 'gesamtverbrauch',
    label: 'Gesamtverbrauch',
    shortLabel: 'Gesamt',
    group: 'berechnet',
    getValue: (md) => md.gesamtverbrauch_kwh,
    format: 'kwh',
    defaultVisible: false,
  },
  {
    key: 'autarkie',
    label: 'Autarkie',
    shortLabel: 'Aut.',
    group: 'berechnet',
    getValue: (md) => md.autarkie_prozent,
    format: 'percent',
    className: 'text-green-600 dark:text-green-400',
    defaultVisible: true,
  },
  {
    key: 'eigenverbrauchsquote',
    label: 'EV-Quote',
    shortLabel: 'EVQ',
    group: 'berechnet',
    getValue: (md) => md.eigenverbrauchsquote_prozent,
    format: 'percent',
    defaultVisible: false,
  },
]

// LocalStorage Key für Spalten-Einstellungen (v3: alle Komponenten)
const COLUMNS_STORAGE_KEY = 'eedc-monatsdaten-columns-v3'

export default function MonatsdatenPage() {
  const navigate = useNavigate()
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>(undefined)
  const { monatsdaten, loading, error, createMonatsdaten, updateMonatsdaten, deleteMonatsdaten } = useMonatsdaten(selectedAnlageId)
  // Hook wird für MonatsdatenForm benötigt
  useInvestitionen(selectedAnlageId)

  // Aggregierte Daten
  const [aggregierteDaten, setAggregierteDaten] = useState<AggregierteMonatsdaten[]>([])
  const [aggregiertLoading, setAggregiertLoading] = useState(false)

  const [showForm, setShowForm] = useState(false)
  const [editingData, setEditingData] = useState<Monatsdaten | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<Monatsdaten | null>(null)
  const [showColumnSelector, setShowColumnSelector] = useState(false)

  // HA-Statistik Laden
  const [showHaModal, setShowHaModal] = useState(false)
  const [haVerfuegbar, setHaVerfuegbar] = useState<boolean | null>(null)
  const [haCheckDone, setHaCheckDone] = useState(false)
  const [verfuegbareMonate, setVerfuegbareMonate] = useState<VerfuegbarerMonat[]>([])
  const [haLoading, setHaLoading] = useState(false)
  const [haError, setHaError] = useState<string | null>(null)
  const [selectedHaJahr, setSelectedHaJahr] = useState<number>(new Date().getFullYear())
  const [selectedHaMonat, setSelectedHaMonat] = useState<number>(new Date().getMonth()) // Vormonat
  const [haVorausfuellung, setHaVorausfuellung] = useState<Monatswerte | null>(null)
  const [showHaVergleich, setShowHaVergleich] = useState(false) // Vergleichsansicht für existierende Monate
  const [haVergleichsDaten, setHaVergleichsDaten] = useState<{
    haWerte: Monatswerte
    vorhandeneDaten: Monatsdaten
  } | null>(null)

  // Sichtbare Spalten aus LocalStorage laden
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem(COLUMNS_STORAGE_KEY)
      if (stored) {
        return new Set(JSON.parse(stored))
      }
    } catch {
      // Ignore parse errors
    }
    return new Set(COLUMNS.filter(c => c.defaultVisible).map(c => c.key))
  })

  // Spalten-Einstellungen in LocalStorage speichern
  useEffect(() => {
    localStorage.setItem(COLUMNS_STORAGE_KEY, JSON.stringify([...visibleColumns]))
  }, [visibleColumns])

  // Aggregierte Daten laden
  useEffect(() => {
    if (!selectedAnlageId) return

    const loadAggregiert = async () => {
      setAggregiertLoading(true)
      try {
        const data = await monatsdatenApi.listAggregiert(selectedAnlageId)
        setAggregierteDaten(data)
      } catch (e) {
        console.error('Fehler beim Laden der aggregierten Daten:', e)
      } finally {
        setAggregiertLoading(false)
      }
    }

    loadAggregiert()
  }, [selectedAnlageId, monatsdaten]) // Neu laden wenn sich monatsdaten ändern

  // HA-Statistik Status prüfen (einmalig)
  useEffect(() => {
    if (haCheckDone) return

    const checkHa = async () => {
      try {
        const status = await haStatisticsApi.getStatus()
        setHaVerfuegbar(status.verfuegbar)
      } catch {
        setHaVerfuegbar(false)
      } finally {
        setHaCheckDone(true)
      }
    }
    checkHa()
  }, [haCheckDone])

  // Verfügbare Monate laden wenn Modal geöffnet wird
  useEffect(() => {
    if (!showHaModal || !selectedAnlageId) return

    const loadMonate = async () => {
      setHaLoading(true)
      setHaError(null)
      try {
        const monate = await haStatisticsApi.getVerfuegbareMonate(selectedAnlageId)
        setVerfuegbareMonate(monate)
      } catch (e) {
        setHaError('Fehler beim Laden der verfügbaren Monate')
        console.error(e)
      } finally {
        setHaLoading(false)
      }
    }
    loadMonate()
  }, [showHaModal, selectedAnlageId])

  // HA-Monatswerte laden
  const handleLoadFromHa = async () => {
    if (!selectedAnlageId || !selectedHaJahr || !selectedHaMonat) return

    setHaLoading(true)
    setHaError(null)

    try {
      const werte = await haStatisticsApi.getMonatswerte(selectedAnlageId, selectedHaJahr, selectedHaMonat)

      // Prüfe ob Monat bereits existiert
      const vorhandeneDaten = monatsdaten.find(
        md => md.jahr === selectedHaJahr && md.monat === selectedHaMonat
      )

      if (vorhandeneDaten) {
        // Zeige Vergleichsansicht
        setHaVergleichsDaten({ haWerte: werte, vorhandeneDaten })
        setShowHaModal(false)
        setShowHaVergleich(true)
      } else {
        // Direkt zum Formular
        setHaVorausfuellung(werte)
        setShowHaModal(false)
        setShowForm(true)
      }
    } catch (e) {
      setHaError('Fehler beim Laden der Monatswerte aus HA-Statistik')
      console.error(e)
    } finally {
      setHaLoading(false)
    }
  }

  // Nach Vergleich: Mit HA-Werten fortfahren
  const handleProceedWithHa = () => {
    if (!haVergleichsDaten) return
    setHaVorausfuellung(haVergleichsDaten.haWerte)
    setEditingData(haVergleichsDaten.vorhandeneDaten) // Bearbeiten statt Neu
    setShowHaVergleich(false)
    setHaVergleichsDaten(null)
  }

  // Vergleich abbrechen
  const handleCancelVergleich = () => {
    setShowHaVergleich(false)
    setHaVergleichsDaten(null)
  }

  const toggleColumn = (key: string) => {
    setVisibleColumns(prev => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  const toggleGroup = (group: keyof typeof COLUMN_GROUPS) => {
    const groupColumns = COLUMNS.filter(c => c.group === group)
    const allVisible = groupColumns.every(c => visibleColumns.has(c.key))

    setVisibleColumns(prev => {
      const next = new Set(prev)
      groupColumns.forEach(c => {
        if (allVisible) {
          next.delete(c.key)
        } else {
          next.add(c.key)
        }
      })
      return next
    })
  }

  const activeColumns = COLUMNS.filter(c => visibleColumns.has(c.key))

  // Erste Anlage als Default auswählen
  if (!selectedAnlageId && anlagen.length > 0 && !anlagenLoading) {
    setSelectedAnlageId(anlagen[0].id)
  }

  // Prüfe ob Legacy-Daten existieren
  const legacyCount = useMemo(() => {
    return aggregierteDaten.filter(md => md.hat_legacy_daten).length
  }, [aggregierteDaten])

  const handleCreate = async (data: Parameters<typeof createMonatsdaten>[0]) => {
    await createMonatsdaten(data)
    setShowForm(false)
  }

  const handleUpdate = async (data: Parameters<typeof createMonatsdaten>[0]) => {
    if (editingData) {
      await updateMonatsdaten(editingData.id, data)
      setEditingData(null)
    }
  }

  const handleDelete = async () => {
    if (deleteConfirm) {
      await deleteMonatsdaten(deleteConfirm.id)
      setDeleteConfirm(null)
    }
  }

  // Finde Original-Monatsdaten für Edit/Delete
  const findOriginalMonatsdaten = (aggregiert: AggregierteMonatsdaten): Monatsdaten | undefined => {
    return monatsdaten.find(md => md.id === aggregiert.id)
  }

  const formatValue = (val: number | null, format?: 'kwh' | 'percent') => {
    if (val === null || val === undefined) return '-'
    if (isNaN(val)) return '-'

    switch (format) {
      case 'kwh':
        return val.toLocaleString('de-DE', { maximumFractionDigits: 1 })
      case 'percent':
        return `${val.toFixed(1)}%`
      default:
        return val.toLocaleString('de-DE', { maximumFractionDigits: 1 })
    }
  }

  if (anlagenLoading || loading) {
    return <LoadingSpinner text="Lade Daten..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Monatsdaten</h1>
        <Card>
          <EmptyState
            icon={AlertCircle}
            title="Keine Anlage vorhanden"
            description="Bitte lege zuerst eine Anlage an, bevor du Monatsdaten erfassen kannst."
            action={
              <Button onClick={() => navigate('/anlagen')}>
                Zur Anlagen-Verwaltung
              </Button>
            }
          />
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Monatsdaten</h1>
        <div className="flex items-center gap-4">
          <Select
            value={selectedAnlageId?.toString() || ''}
            onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
            options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
          />
          {haVerfuegbar && (
            <Button variant="secondary" onClick={() => setShowHaModal(true)}>
              <Database className="h-5 w-5 mr-2" />
              Aus HA laden
            </Button>
          )}
          <Button onClick={() => { setHaVorausfuellung(null); setShowForm(true) }}>
            <Plus className="h-5 w-5 mr-2" />
            Neuer Monat
          </Button>
        </div>
      </div>

      {error && <Alert type="error">{error}</Alert>}

      {/* Migrations-Hinweis für Legacy-Daten */}
      {legacyCount > 0 && (
        <Alert type="warning" className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium">Legacy-Daten gefunden</p>
            <p className="text-sm mt-1">
              {legacyCount} Monat{legacyCount > 1 ? 'e' : ''} enthält
              {legacyCount > 1 ? 'en' : ''} Daten im alten Format (PV-Erzeugung/Speicher in Monatsdaten statt InvestitionMonatsdaten).
              Bitte jeden betroffenen Monat einmal öffnen und speichern.
            </p>
          </div>
        </Alert>
      )}

      {aggregiertLoading ? (
        <LoadingSpinner text="Lade aggregierte Daten..." />
      ) : aggregierteDaten.length === 0 ? (
        <Card>
          <EmptyState
            icon={Calendar}
            title="Keine Monatsdaten vorhanden"
            description="Erfasse deine ersten Monatsdaten manuell oder importiere eine CSV-Datei."
            action={
              <div className="flex gap-4">
                <Button onClick={() => setShowForm(true)}>Manuell erfassen</Button>
                <Button variant="secondary" onClick={() => navigate('/import')}>CSV importieren</Button>
              </div>
            }
          />
        </Card>
      ) : (
        <>
          {/* Spalten-Auswahl */}
          <div className="flex justify-end">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowColumnSelector(!showColumnSelector)}
            >
              <Columns className="h-4 w-4 mr-2" />
              Spalten ({activeColumns.length}/{COLUMNS.length})
            </Button>
          </div>

          {/* Spalten-Auswahl Panel mit Gruppen */}
          {showColumnSelector && (
            <Card className="bg-gray-50 dark:bg-gray-800/50">
              <div className="space-y-4">
                {(Object.keys(COLUMN_GROUPS) as Array<keyof typeof COLUMN_GROUPS>).map((groupKey) => {
                  const group = COLUMN_GROUPS[groupKey]
                  const groupColumns = COLUMNS.filter(c => c.group === groupKey)
                  const visibleCount = groupColumns.filter(c => visibleColumns.has(c.key)).length

                  return (
                    <div key={groupKey}>
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`w-3 h-3 rounded-full ${group.color}`} />
                        <button
                          onClick={() => toggleGroup(groupKey)}
                          className="text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-primary-600"
                        >
                          {group.label} ({visibleCount}/{groupColumns.length})
                        </button>
                      </div>
                      <div className="flex flex-wrap gap-2 ml-5">
                        {groupColumns.map((col) => (
                          <button
                            key={col.key}
                            onClick={() => toggleColumn(col.key)}
                            className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
                              visibleColumns.has(col.key)
                                ? 'bg-primary-500 text-white'
                                : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                            }`}
                          >
                            {col.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-4">
                Klicke auf Gruppen-Namen um alle Spalten ein-/auszublenden, oder auf einzelne Spalten.
              </p>
            </Card>
          )}

          {/* Tabelle */}
          <Card padding="none">
            <div className="overflow-x-auto">
              <Table>
                <TableHead>
                  <TableRow>
                    <TableHeader>Monat</TableHeader>
                    {activeColumns.map((col) => (
                      <TableHeader key={col.key} className="text-right">
                        <span className="hidden sm:inline">{col.label}</span>
                        <span className="sm:hidden">{col.shortLabel || col.label}</span>
                      </TableHeader>
                    ))}
                    <TableHeader className="text-right">Aktionen</TableHeader>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {aggregierteDaten.map((md) => (
                    <TableRow key={md.id} className={md.hat_legacy_daten ? 'bg-amber-50 dark:bg-amber-900/10' : ''}>
                      <TableCell>
                        <span className="font-medium">{monatNamen[md.monat]} {md.jahr}</span>
                        {md.hat_legacy_daten && (
                          <span title="Legacy-Daten">
                            <AlertTriangle className="h-3 w-3 text-amber-500 inline ml-1" />
                          </span>
                        )}
                      </TableCell>
                      {activeColumns.map((col) => {
                        const value = col.getValue(md)
                        return (
                          <TableCell key={col.key} className={`text-right font-mono ${col.className || ''}`}>
                            {formatValue(value, col.format)}
                          </TableCell>
                        )
                      })}
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              const original = findOriginalMonatsdaten(md)
                              if (original) setEditingData(original)
                            }}
                          >
                            <Edit className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              const original = findOriginalMonatsdaten(md)
                              if (original) setDeleteConfirm(original)
                            }}
                          >
                            <Trash2 className="h-4 w-4 text-red-500" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </Card>
        </>
      )}

      {/* HA-Statistik Modal */}
      <Modal
        isOpen={showHaModal}
        onClose={() => setShowHaModal(false)}
        title="Monatsdaten aus HA-Statistik laden"
        size="md"
      >
        <div className="space-y-4">
          {haError && <Alert type="error">{haError}</Alert>}

          {haLoading && !verfuegbareMonate.length ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-primary-500" />
            </div>
          ) : verfuegbareMonate.length === 0 ? (
            <Alert type="warning">
              Keine Daten in HA-Statistik gefunden. Stellen Sie sicher, dass das Sensor-Mapping
              konfiguriert ist und die Sensoren Langzeit-Statistiken haben.
            </Alert>
          ) : (
            <>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Wählen Sie einen Monat aus, dessen Daten aus der Home Assistant
                Langzeitstatistik geladen werden sollen. Die Werte werden im
                Formular vorausgefüllt und können vor dem Speichern angepasst werden.
              </p>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Jahr
                  </label>
                  <select
                    value={selectedHaJahr}
                    onChange={(e) => setSelectedHaJahr(parseInt(e.target.value))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                  >
                    {[...new Set(verfuegbareMonate.map(m => m.jahr))].sort((a, b) => b - a).map(jahr => (
                      <option key={jahr} value={jahr}>{jahr}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Monat
                  </label>
                  <select
                    value={selectedHaMonat}
                    onChange={(e) => setSelectedHaMonat(parseInt(e.target.value))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                  >
                    {verfuegbareMonate
                      .filter(m => m.jahr === selectedHaJahr)
                      .sort((a, b) => b.monat - a.monat)
                      .map(m => (
                        <option key={m.monat} value={m.monat}>
                          {m.monat_name} {m.hat_daten ? '' : '(keine Daten)'}
                        </option>
                      ))}
                  </select>
                </div>
              </div>

              {/* Info über vorhandene Daten */}
              {monatsdaten.some(md => md.jahr === selectedHaJahr && md.monat === selectedHaMonat) && (
                <Alert type="info">
                  Für diesen Monat existieren bereits Daten. Nach dem Laden wird ein
                  Vergleich angezeigt, damit Sie die Unterschiede prüfen können.
                </Alert>
              )}

              <div className="flex justify-end gap-3 pt-4">
                <Button variant="secondary" onClick={() => setShowHaModal(false)}>
                  Abbrechen
                </Button>
                <Button onClick={handleLoadFromHa} disabled={haLoading}>
                  {haLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Lade...
                    </>
                  ) : (
                    <>
                      <Database className="h-4 w-4 mr-2" />
                      Werte laden
                    </>
                  )}
                </Button>
              </div>
            </>
          )}
        </div>
      </Modal>

      {/* Vergleichs-Modal: HA vs. Vorhandene Daten */}
      <Modal
        isOpen={showHaVergleich}
        onClose={handleCancelVergleich}
        title={`Vergleich: ${haVergleichsDaten?.haWerte.monat_name} ${haVergleichsDaten?.haWerte.jahr}`}
        size="lg"
      >
        {haVergleichsDaten && (
          <div className="space-y-4">
            <Alert type="warning">
              Für diesen Monat existieren bereits Daten. Bitte prüfen Sie die Unterschiede
              und entscheiden Sie, ob die HA-Werte übernommen werden sollen.
            </Alert>

            {/* Basis-Werte Vergleich */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-gray-900 dark:text-white">Basis-Werte (kWh)</h4>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b dark:border-gray-700">
                      <th className="text-left py-2 px-3 font-medium">Feld</th>
                      <th className="text-right py-2 px-3 font-medium text-blue-600">Vorhanden</th>
                      <th className="text-right py-2 px-3 font-medium text-green-600">HA-Statistik</th>
                      <th className="text-right py-2 px-3 font-medium">Diff</th>
                    </tr>
                  </thead>
                  <tbody>
                    <VergleichsZeile
                      label="Einspeisung"
                      vorhanden={haVergleichsDaten.vorhandeneDaten.einspeisung_kwh}
                      haWert={haVergleichsDaten.haWerte.basis.find(b => b.feld === 'einspeisung')?.wert}
                    />
                    <VergleichsZeile
                      label="Netzbezug"
                      vorhanden={haVergleichsDaten.vorhandeneDaten.netzbezug_kwh}
                      haWert={haVergleichsDaten.haWerte.basis.find(b => b.feld === 'netzbezug')?.wert}
                    />
                  </tbody>
                </table>
              </div>
            </div>

            {/* Investitions-Werte Vergleich */}
            {haVergleichsDaten.haWerte.investitionen.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-gray-900 dark:text-white">Komponenten-Werte</h4>
                {haVergleichsDaten.haWerte.investitionen.map(inv => (
                  <div key={inv.investition_id} className="border rounded-lg p-3 dark:border-gray-700">
                    <h5 className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
                      {inv.bezeichnung} ({inv.typ})
                    </h5>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
                      {inv.felder.filter(f => f.wert !== null).map(f => (
                        <div key={f.feld} className="flex justify-between bg-green-50 dark:bg-green-900/20 px-2 py-1 rounded">
                          <span className="text-gray-600 dark:text-gray-400">{f.feld}:</span>
                          <span className="font-medium text-green-700 dark:text-green-300">
                            {f.wert?.toLocaleString('de-DE', { maximumFractionDigits: 1 })}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-end gap-3 pt-4 border-t dark:border-gray-700">
              <Button variant="secondary" onClick={handleCancelVergleich}>
                Abbrechen
              </Button>
              <Button onClick={handleProceedWithHa}>
                <Database className="h-4 w-4 mr-2" />
                Mit HA-Werten fortfahren
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Create Modal */}
      <Modal
        isOpen={showForm}
        onClose={() => { setShowForm(false); setHaVorausfuellung(null) }}
        title={haVorausfuellung ? `Monatsdaten aus HA laden - ${haVorausfuellung.monat_name} ${haVorausfuellung.jahr}` : "Monatsdaten erfassen"}
        size="lg"
      >
        {selectedAnlageId && (
          <MonatsdatenForm
            anlageId={selectedAnlageId}
            onSubmit={handleCreate}
            onCancel={() => { setShowForm(false); setHaVorausfuellung(null) }}
            haVorausfuellung={haVorausfuellung}
          />
        )}
      </Modal>

      {/* Edit Modal */}
      <Modal
        isOpen={!!editingData}
        onClose={() => { setEditingData(null); setHaVorausfuellung(null) }}
        title={haVorausfuellung ? `HA-Werte übernehmen - ${haVorausfuellung.monat_name} ${haVorausfuellung.jahr}` : "Monatsdaten bearbeiten"}
        size="lg"
      >
        {editingData && selectedAnlageId && (
          <MonatsdatenForm
            monatsdaten={editingData}
            anlageId={selectedAnlageId}
            onSubmit={handleUpdate}
            onCancel={() => { setEditingData(null); setHaVorausfuellung(null) }}
            haVorausfuellung={haVorausfuellung}
          />
        )}
      </Modal>

      {/* Delete Confirmation */}
      <Modal isOpen={!!deleteConfirm} onClose={() => setDeleteConfirm(null)} title="Monatsdaten löschen" size="sm">
        <div className="space-y-4">
          <p className="text-gray-600 dark:text-gray-300">
            Möchtest du die Daten für <strong>{monatNamen[deleteConfirm?.monat || 0]} {deleteConfirm?.jahr}</strong> wirklich löschen?
          </p>
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setDeleteConfirm(null)}>Abbrechen</Button>
            <Button variant="danger" onClick={handleDelete}>Löschen</Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

// Hilfsfunktion für Vergleichszeilen
function VergleichsZeile({
  label,
  vorhanden,
  haWert,
}: {
  label: string
  vorhanden: number | null | undefined
  haWert: number | null | undefined
}) {
  const vorhandenVal = vorhanden ?? null
  const haVal = haWert ?? null

  // Berechne Differenz
  let diff: number | null = null
  let diffClass = ''
  if (vorhandenVal !== null && haVal !== null) {
    diff = haVal - vorhandenVal
    if (Math.abs(diff) < 0.1) {
      diffClass = 'text-gray-500'
    } else if (diff > 0) {
      diffClass = 'text-green-600 dark:text-green-400'
    } else {
      diffClass = 'text-red-600 dark:text-red-400'
    }
  }

  const formatVal = (val: number | null) =>
    val !== null ? val.toLocaleString('de-DE', { maximumFractionDigits: 1 }) : '–'

  // Hervorhebung wenn unterschiedlich
  const isDifferent = vorhandenVal !== null && haVal !== null && Math.abs((haVal - vorhandenVal)) > 0.1

  return (
    <tr className={`border-b dark:border-gray-700 ${isDifferent ? 'bg-amber-50 dark:bg-amber-900/10' : ''}`}>
      <td className="py-2 px-3 font-medium">{label}</td>
      <td className="py-2 px-3 text-right text-blue-600 dark:text-blue-400">
        {formatVal(vorhandenVal)}
      </td>
      <td className="py-2 px-3 text-right text-green-600 dark:text-green-400 font-medium">
        {formatVal(haVal)}
      </td>
      <td className={`py-2 px-3 text-right font-medium ${diffClass}`}>
        {diff !== null ? (diff >= 0 ? '+' : '') + diff.toLocaleString('de-DE', { maximumFractionDigits: 1 }) : '–'}
      </td>
    </tr>
  )
}
