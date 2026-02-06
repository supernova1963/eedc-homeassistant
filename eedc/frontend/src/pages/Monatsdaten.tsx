import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Calendar, Edit, Trash2, AlertCircle, Columns } from 'lucide-react'
import { Button, Card, Modal, EmptyState, LoadingSpinner, Alert, Select } from '../components/ui'
import { Table, TableHead, TableBody, TableRow, TableHeader, TableCell } from '../components/ui'
import { MonatsdatenForm } from '../components/forms'
import { useAnlagen, useMonatsdaten } from '../hooks'
import type { Monatsdaten } from '../types'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

// Verfügbare Spalten-Konfiguration
interface ColumnConfig {
  key: string
  label: string
  shortLabel?: string  // Kürzerer Label für schmale Bildschirme
  getValue: (md: Monatsdaten) => string | number | null | undefined
  format?: 'kwh' | 'percent' | 'euro'
  className?: string
  defaultVisible: boolean
}

const COLUMNS: ColumnConfig[] = [
  {
    key: 'einspeisung',
    label: 'Einspeisung',
    shortLabel: 'Einsp.',
    getValue: (md) => md.einspeisung_kwh,
    format: 'kwh',
    defaultVisible: true,
  },
  {
    key: 'netzbezug',
    label: 'Netzbezug',
    shortLabel: 'Netz',
    getValue: (md) => md.netzbezug_kwh,
    format: 'kwh',
    defaultVisible: true,
  },
  {
    key: 'pv_erzeugung',
    label: 'PV-Erzeugung',
    shortLabel: 'PV',
    getValue: (md) => md.pv_erzeugung_kwh,
    format: 'kwh',
    defaultVisible: true,
  },
  {
    key: 'direktverbrauch',
    label: 'Direktverbrauch',
    shortLabel: 'Direkt',
    getValue: (md) => md.direktverbrauch_kwh,
    format: 'kwh',
    defaultVisible: false,
  },
  {
    key: 'eigenverbrauch',
    label: 'Eigenverbrauch',
    shortLabel: 'Eigen',
    getValue: (md) => md.eigenverbrauch_kwh,
    format: 'kwh',
    defaultVisible: true,
  },
  {
    key: 'gesamtverbrauch',
    label: 'Gesamtverbrauch',
    shortLabel: 'Gesamt',
    getValue: (md) => md.gesamtverbrauch_kwh,
    format: 'kwh',
    defaultVisible: false,
  },
  {
    key: 'batterie_ladung',
    label: 'Batt. Ladung',
    shortLabel: 'B.Lad',
    getValue: (md) => md.batterie_ladung_kwh,
    format: 'kwh',
    defaultVisible: false,
  },
  {
    key: 'batterie_entladung',
    label: 'Batt. Entladung',
    shortLabel: 'B.Entl',
    getValue: (md) => md.batterie_entladung_kwh,
    format: 'kwh',
    defaultVisible: false,
  },
  {
    key: 'autarkie',
    label: 'Autarkie',
    shortLabel: 'Aut.',
    getValue: (md) => {
      const eigenverbrauch = md.eigenverbrauch_kwh || 0
      const gesamtverbrauch = eigenverbrauch + md.netzbezug_kwh
      return gesamtverbrauch > 0 ? (eigenverbrauch / gesamtverbrauch) * 100 : 0
    },
    format: 'percent',
    className: 'text-green-600 dark:text-green-400',
    defaultVisible: true,
  },
  {
    key: 'eigenverbrauchsquote',
    label: 'EV-Quote',
    shortLabel: 'EVQ',
    getValue: (md) => {
      const eigenverbrauch = md.eigenverbrauch_kwh || 0
      const pvErzeugung = md.pv_erzeugung_kwh || 0
      return pvErzeugung > 0 ? (eigenverbrauch / pvErzeugung) * 100 : 0
    },
    format: 'percent',
    defaultVisible: false,
  },
]

// LocalStorage Key für Spalten-Einstellungen
const COLUMNS_STORAGE_KEY = 'eedc-monatsdaten-columns'

export default function MonatsdatenPage() {
  const navigate = useNavigate()
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>(undefined)
  const { monatsdaten, loading, error, createMonatsdaten, updateMonatsdaten, deleteMonatsdaten } = useMonatsdaten(selectedAnlageId)

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
    // Default: alle Spalten mit defaultVisible=true
    return new Set(COLUMNS.filter(c => c.defaultVisible).map(c => c.key))
  })

  // Spalten-Einstellungen in LocalStorage speichern
  useEffect(() => {
    localStorage.setItem(COLUMNS_STORAGE_KEY, JSON.stringify([...visibleColumns]))
  }, [visibleColumns])

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

  const activeColumns = COLUMNS.filter(c => visibleColumns.has(c.key))

  // Erste Anlage als Default auswählen
  if (!selectedAnlageId && anlagen.length > 0 && !anlagenLoading) {
    setSelectedAnlageId(anlagen[0].id)
  }

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

  const formatValue = (val: string | number | null | undefined, format?: 'kwh' | 'percent' | 'euro') => {
    if (val === undefined || val === null) return '-'
    const num = typeof val === 'string' ? parseFloat(val) : val
    if (isNaN(num)) return '-'

    switch (format) {
      case 'kwh':
        return num.toLocaleString('de-DE', { maximumFractionDigits: 1 })
      case 'percent':
        return `${num.toFixed(1)}%`
      case 'euro':
        return `${num.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`
      default:
        return num.toLocaleString('de-DE', { maximumFractionDigits: 1 })
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

      {monatsdaten.length === 0 ? (
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
          {/* Spalten-Auswahl Button */}
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

          {/* Spalten-Auswahl Panel */}
          {showColumnSelector && (
            <Card className="bg-gray-50 dark:bg-gray-800/50">
              <div className="flex flex-wrap gap-2">
                {COLUMNS.map((col) => (
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
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                Klicke auf eine Spalte um sie ein-/auszublenden. Die Auswahl wird gespeichert.
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
                  {monatsdaten.map((md) => (
                    <TableRow key={md.id}>
                      <TableCell>
                        <span className="font-medium">{monatNamen[md.monat]} {md.jahr}</span>
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
                          <Button variant="ghost" size="sm" onClick={() => setEditingData(md)}>
                            <Edit className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setDeleteConfirm(md)}>
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
