import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Calendar, Edit, Trash2, AlertCircle } from 'lucide-react'
import { Button, Card, Modal, EmptyState, LoadingSpinner, Alert, Select } from '../components/ui'
import { Table, TableHead, TableBody, TableRow, TableHeader, TableCell } from '../components/ui'
import { MonatsdatenForm } from '../components/forms'
import { useAnlagen, useMonatsdaten } from '../hooks'
import type { Monatsdaten } from '../types'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

export default function MonatsdatenPage() {
  const navigate = useNavigate()
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>(undefined)
  const { monatsdaten, loading, error, createMonatsdaten, updateMonatsdaten, deleteMonatsdaten } = useMonatsdaten(selectedAnlageId)

  const [showForm, setShowForm] = useState(false)
  const [editingData, setEditingData] = useState<Monatsdaten | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<Monatsdaten | null>(null)

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

  const formatKwh = (val?: number) => val !== undefined ? val.toLocaleString('de-DE', { maximumFractionDigits: 1 }) : '-'

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
        <Card padding="none">
          <Table>
            <TableHead>
              <TableRow>
                <TableHeader>Monat</TableHeader>
                <TableHeader className="text-right">Einspeisung</TableHeader>
                <TableHeader className="text-right">Netzbezug</TableHeader>
                <TableHeader className="text-right">PV-Erzeugung</TableHeader>
                <TableHeader className="text-right">Eigenverbrauch</TableHeader>
                <TableHeader className="text-right">Autarkie</TableHeader>
                <TableHeader className="text-right">Aktionen</TableHeader>
              </TableRow>
            </TableHead>
            <TableBody>
              {monatsdaten.map((md) => {
                const eigenverbrauch = md.eigenverbrauch_kwh || 0
                const gesamtverbrauch = eigenverbrauch + md.netzbezug_kwh
                const autarkie = gesamtverbrauch > 0 ? (eigenverbrauch / gesamtverbrauch) * 100 : 0

                return (
                  <TableRow key={md.id}>
                    <TableCell>
                      <span className="font-medium">{monatNamen[md.monat]} {md.jahr}</span>
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatKwh(md.einspeisung_kwh)}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatKwh(md.netzbezug_kwh)}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatKwh(md.pv_erzeugung_kwh)}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatKwh(md.eigenverbrauch_kwh)}
                    </TableCell>
                    <TableCell className="text-right">
                      <span className={autarkie >= 50 ? 'text-green-600' : 'text-gray-600'}>
                        {autarkie.toFixed(1)}%
                      </span>
                    </TableCell>
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
                )
              })}
            </TableBody>
          </Table>
        </Card>
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
