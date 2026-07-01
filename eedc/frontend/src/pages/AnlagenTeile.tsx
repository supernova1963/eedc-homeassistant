/**
 * Anlagen — geteilte Teile (Tabelle aller Anlagen + Anlegen/Bearbeiten/Löschen +
 * Export + Dokumente-Dialog).
 *
 * EINE Code-Wahrheit für IST (`pages/Anlagen.tsx`, dünner Komposer) und IA-V4
 * (Einstellungen-Katalog-Block „Anlage", `config/einstellungenKatalog.tsx`).
 * Gernot-Entscheid 2026-07-01: der Stammdaten→Anlage-Block ist – wie Strompreise –
 * eine Tabelle mit Bearbeiten-Modal (auch bei einer Anlage), statt eines inline
 * eingebetteten Voll-Formulars. Der Aufrufer wickelt: V3 = Seiten-Layout,
 * V4 = BlockShell-Block. Zahlen de-DE (`fmtZahl`).
 */
import { useState } from 'react'
import { Plus, Edit, Trash2, Sun, MapPin, Download, FolderOpen } from 'lucide-react'
import { Button, Card, Modal, EmptyState, LoadingSpinner, Alert, DestructiveActionDialog } from '../components/ui'
import { Table, TableHead, TableBody, TableRow, TableHeader, TableCell } from '../components/ui'
import AnlageForm from '../components/forms/AnlageForm'
import DokumentationsDialog from '../components/DokumentationsDialog'
import { useAnlagen } from '../hooks'
import { importApi } from '../api/import'
import { downloadFile, fmtZahl } from '../lib'
import type { Anlage, AnlageCreate } from '../types'

/**
 * Voller Anlagen-Manager (Liste ALLER Anlagen). Wird von der IST-Seite (V3-Hülle)
 * und dem V4-Stammdaten-Block geteilt.
 */
export function AnlagenVerwaltung() {
  const { anlagen, loading, error, createAnlage, updateAnlage, deleteAnlage } = useAnlagen()
  const [showForm, setShowForm] = useState(false)
  const [editingAnlage, setEditingAnlage] = useState<Anlage | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<Anlage | null>(null)
  const [dokumenteAnlage, setDokumenteAnlage] = useState<Anlage | null>(null)

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

  // Nach Anlagen-Nr (id = laufende Nummer) aufsteigend (Gernot 2026-07-01).
  const anlagenSortiert = [...anlagen].sort((a, b) => a.id - b.id)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end">
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
        <Card padding="none" className="overflow-hidden">
          <Table>
            <TableHead>
              <TableRow>
                <TableHeader>Anlagen-Nr</TableHeader>
                <TableHeader>Name</TableHeader>
                <TableHeader>Leistung</TableHeader>
                <TableHeader>Standort</TableHeader>
                <TableHeader>Installation</TableHeader>
                <TableHeader className="text-right">Aktionen</TableHeader>
              </TableRow>
            </TableHead>
            <TableBody>
              {anlagenSortiert.map((anlage) => (
                <TableRow key={anlage.id}>
                  <TableCell>
                    {/* Anlagen-Nr = id (Nicht-Menge → kein fmtZahl). */}
                    <span className="font-mono text-gray-500 dark:text-gray-400">{anlage.id}</span>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Sun className="h-5 w-5 text-energy-solar" />
                      <span className="font-medium">{anlage.anlagenname}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="font-mono">{fmtZahl(anlage.leistung_kwp, 1)}</span> kWp
                  </TableCell>
                  <TableCell>
                    {anlage.standort_ort ? (
                      <div className="flex items-center gap-1 text-gray-500">
                        <MapPin className="h-4 w-4" />
                        {anlage.standort_plz} {anlage.standort_ort}
                      </div>
                    ) : (
                      <span className="text-gray-400 dark:text-gray-500">-</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {anlage.installationsdatum
                      ? new Date(anlage.installationsdatum).toLocaleDateString('de-DE')
                      : <span className="text-gray-400 dark:text-gray-500">-</span>
                    }
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDokumenteAnlage(anlage)}
                        title="Dokumente (Jahresbericht, Infothek, Anlagendokumentation, Finanzbericht)"
                      >
                        <FolderOpen className="h-4 w-4 text-orange-500" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          const safeName = anlage.anlagenname.replace(/\s+/g, '_')
                          const datum = new Date().toISOString().slice(0, 10)
                          downloadFile(
                            importApi.getFullExportUrl(anlage.id),
                            `eedc_backup_${safeName}_${datum}.json`,
                          ).catch(() => {/* still better than 401 in Safari */})
                        }}
                        title="Export (JSON)"
                      >
                        <Download className="h-4 w-4 text-blue-500" />
                      </Button>
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

      {/* Delete Confirmation mit Backup-Angebot */}
      <DestructiveActionDialog
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDelete}
        title="Anlage löschen"
        itemLabel={<>Anlage „{deleteConfirm?.anlagenname}" wird unwiderruflich gelöscht.</>}
        warningMessage="Alle zugehörigen Monatsdaten, Investitionen, Strompreise, Sensor-Mappings und Prognosen gehen verloren."
        anlageId={deleteConfirm?.id}
        anlageName={deleteConfirm?.anlagenname || ''}
      />

      {/* Dokumente-Dialog (Phase 4 Beta) */}
      <DokumentationsDialog
        anlage={dokumenteAnlage}
        onClose={() => setDokumenteAnlage(null)}
      />
    </div>
  )
}
