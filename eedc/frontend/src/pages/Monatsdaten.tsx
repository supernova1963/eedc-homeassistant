import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Calendar, Edit, Trash2, AlertCircle, Columns, AlertTriangle } from 'lucide-react'
import { Button, Card, Modal, EmptyState, LoadingSpinner, Alert, Select } from '../components/ui'
import { Table, TableHead, TableBody, TableRow, TableHeader, TableCell } from '../components/ui'
import { MonatsdatenForm } from '../components/forms'
import { useAnlagen, useMonatsdaten, useInvestitionen } from '../hooks'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
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
          <Button onClick={() => setShowForm(true)}>
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

      {/* Create Modal */}
      <Modal isOpen={showForm} onClose={() => setShowForm(false)} title="Monatsdaten erfassen" size="lg">
        {selectedAnlageId && (
          <MonatsdatenForm
            anlageId={selectedAnlageId}
            onSubmit={handleCreate}
            onCancel={() => setShowForm(false)}
          />
        )}
      </Modal>

      {/* Edit Modal */}
      <Modal isOpen={!!editingData} onClose={() => setEditingData(null)} title="Monatsdaten bearbeiten" size="lg">
        {editingData && selectedAnlageId && (
          <MonatsdatenForm
            monatsdaten={editingData}
            anlageId={selectedAnlageId}
            onSubmit={handleUpdate}
            onCancel={() => setEditingData(null)}
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
