import { useState } from 'react'
import { Plus, Edit, Trash2, Sun, MapPin } from 'lucide-react'
import { Button, Card, Modal, EmptyState, LoadingSpinner, Alert } from '../components/ui'
import { Table, TableHead, TableBody, TableRow, TableHeader, TableCell } from '../components/ui'
import AnlageForm from '../components/forms/AnlageForm'
import { useAnlagen } from '../hooks'
import type { Anlage, AnlageCreate } from '../types'

export default function Anlagen() {
  const { anlagen, loading, error, createAnlage, updateAnlage, deleteAnlage } = useAnlagen()
  const [showForm, setShowForm] = useState(false)
  const [editingAnlage, setEditingAnlage] = useState<Anlage | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<Anlage | null>(null)

  const handleCreate = async (data: AnlageCreate) => {
    await createAnlage(data)
    setShowForm(false)
  }

  const handleUpdate = async (data: AnlageCreate) => {
    if (editingAnlage) {
      await updateAnlage(editingAnlage.id, data)
      setEditingAnlage(null)
    }
  }

  const handleDelete = async () => {
    if (deleteConfirm) {
      await deleteAnlage(deleteConfirm.id)
      setDeleteConfirm(null)
    }
  }

  if (loading) {
    return <LoadingSpinner text="Lade Anlagen..." />
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Anlagen
        </h1>
        <Button onClick={() => setShowForm(true)}>
          <Plus className="h-5 w-5 mr-2" />
          Neue Anlage
        </Button>
      </div>

      {error && <Alert type="error">{error}</Alert>}

      {anlagen.length === 0 ? (
        <Card>
          <EmptyState
            icon={Sun}
            title="Keine Anlagen vorhanden"
            description="Lege deine erste PV-Anlage an, um mit der Datenerfassung zu beginnen."
            action={
              <Button onClick={() => setShowForm(true)}>
                Erste Anlage anlegen
              </Button>
            }
          />
        </Card>
      ) : (
        <Card padding="none">
          <Table>
            <TableHead>
              <TableRow>
                <TableHeader>Name</TableHeader>
                <TableHeader>Leistung</TableHeader>
                <TableHeader>Standort</TableHeader>
                <TableHeader>Ausrichtung</TableHeader>
                <TableHeader>Installation</TableHeader>
                <TableHeader className="text-right">Aktionen</TableHeader>
              </TableRow>
            </TableHead>
            <TableBody>
              {anlagen.map((anlage) => (
                <TableRow key={anlage.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Sun className="h-5 w-5 text-energy-solar" />
                      <span className="font-medium">{anlage.anlagenname}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="font-mono">{anlage.leistung_kwp}</span> kWp
                  </TableCell>
                  <TableCell>
                    {anlage.standort_ort ? (
                      <div className="flex items-center gap-1 text-gray-500">
                        <MapPin className="h-4 w-4" />
                        {anlage.standort_plz} {anlage.standort_ort}
                      </div>
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {anlage.ausrichtung || <span className="text-gray-400">-</span>}
                    {anlage.neigung_grad && ` / ${anlage.neigung_grad}°`}
                  </TableCell>
                  <TableCell>
                    {anlage.installationsdatum
                      ? new Date(anlage.installationsdatum).toLocaleDateString('de-DE')
                      : <span className="text-gray-400">-</span>
                    }
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditingAnlage(anlage)}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDeleteConfirm(anlage)}
                      >
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* Create Modal */}
      <Modal
        isOpen={showForm}
        onClose={() => setShowForm(false)}
        title="Neue Anlage erstellen"
        size="lg"
      >
        <AnlageForm
          onSubmit={handleCreate}
          onCancel={() => setShowForm(false)}
        />
      </Modal>

      {/* Edit Modal */}
      <Modal
        isOpen={!!editingAnlage}
        onClose={() => setEditingAnlage(null)}
        title="Anlage bearbeiten"
        size="lg"
      >
        {editingAnlage && (
          <AnlageForm
            anlage={editingAnlage}
            onSubmit={handleUpdate}
            onCancel={() => setEditingAnlage(null)}
          />
        )}
      </Modal>

      {/* Delete Confirmation */}
      <Modal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        title="Anlage löschen"
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-gray-600 dark:text-gray-300">
            Möchtest du die Anlage <strong>"{deleteConfirm?.anlagenname}"</strong> wirklich löschen?
          </p>
          <Alert type="warning">
            Alle zugehörigen Monatsdaten, Investitionen und Strompreise werden ebenfalls gelöscht.
          </Alert>
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setDeleteConfirm(null)}>
              Abbrechen
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              Löschen
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
