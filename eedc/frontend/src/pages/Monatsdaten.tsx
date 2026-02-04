import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Calendar, Edit, Trash2, AlertCircle, Download, CheckCircle, XCircle, RefreshCw, Home } from 'lucide-react'
import { Button, Card, Modal, EmptyState, LoadingSpinner, Alert, Select } from '../components/ui'
import { Table, TableHead, TableBody, TableRow, TableHeader, TableCell } from '../components/ui'
import { MonatsdatenForm } from '../components/forms'
import { useAnlagen, useMonatsdaten } from '../hooks'
import { haApi, type HAImportPreview, type HAImportPreviewMonth } from '../api'
import type { Monatsdaten } from '../types'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
const monatNamenVoll = ['', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

export default function MonatsdatenPage() {
  const navigate = useNavigate()
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>(undefined)
  const { monatsdaten, loading, error, createMonatsdaten, updateMonatsdaten, deleteMonatsdaten, refresh } = useMonatsdaten(selectedAnlageId)

  const [showForm, setShowForm] = useState(false)
  const [editingData, setEditingData] = useState<Monatsdaten | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<Monatsdaten | null>(null)

  // HA Import States
  const [showHAImport, setShowHAImport] = useState(false)
  const [haPreview, setHaPreview] = useState<HAImportPreview | null>(null)
  const [haPreviewLoading, setHaPreviewLoading] = useState(false)
  const [haPreviewError, setHaPreviewError] = useState<string | null>(null)
  const [haImporting, setHaImporting] = useState(false)
  const [haImportSuccess, setHaImportSuccess] = useState<string | null>(null)
  const [selectedHAYear, setSelectedHAYear] = useState(new Date().getFullYear())

  // Erste Anlage als Default auswählen
  if (!selectedAnlageId && anlagen.length > 0 && !anlagenLoading) {
    setSelectedAnlageId(anlagen[0].id)
  }

  // HA Import Vorschau laden
  const loadHAPreview = async () => {
    if (!selectedAnlageId) return
    try {
      setHaPreviewLoading(true)
      setHaPreviewError(null)
      setHaImportSuccess(null)
      const preview = await haApi.getImportPreview(selectedAnlageId, selectedHAYear)
      setHaPreview(preview)
    } catch (e) {
      setHaPreviewError(e instanceof Error ? e.message : 'Fehler beim Laden der HA-Vorschau')
      setHaPreview(null)
    } finally {
      setHaPreviewLoading(false)
    }
  }

  // HA Import durchführen
  const handleHAImport = async (monat?: number, ueberschreiben = false) => {
    if (!selectedAnlageId) return
    try {
      setHaImporting(true)
      setHaPreviewError(null)
      const result = await haApi.importMonatsdaten(selectedAnlageId, selectedHAYear, monat, ueberschreiben)
      if (result.erfolg) {
        setHaImportSuccess(`${result.monate_importiert} Monat${result.monate_importiert !== 1 ? 'e' : ''} importiert`)
        await loadHAPreview() // Vorschau aktualisieren
        await refresh() // Monatsdaten neu laden
      } else {
        setHaPreviewError(result.fehler || 'Import fehlgeschlagen')
      }
    } catch (e) {
      setHaPreviewError(e instanceof Error ? e.message : 'Fehler beim Import')
    } finally {
      setHaImporting(false)
    }
  }

  // Vorschau laden wenn Dialog geöffnet wird
  useEffect(() => {
    if (showHAImport && selectedAnlageId) {
      loadHAPreview()
    }
  }, [showHAImport, selectedAnlageId, selectedHAYear])

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
          <Button variant="secondary" onClick={() => setShowHAImport(true)}>
            <Home className="h-5 w-5 mr-2" />
            Aus HA importieren
          </Button>
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

      {/* HA Import Modal */}
      <Modal
        isOpen={showHAImport}
        onClose={() => {
          setShowHAImport(false)
          setHaPreview(null)
          setHaPreviewError(null)
          setHaImportSuccess(null)
        }}
        title="Monatsdaten aus Home Assistant importieren"
        size="lg"
      >
        <div className="space-y-4">
          {/* Jahr auswählen */}
          <div className="flex items-center gap-4">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Jahr:</label>
            <Select
              value={selectedHAYear.toString()}
              onChange={(e) => setSelectedHAYear(parseInt(e.target.value))}
              options={Array.from({ length: 10 }, (_, i) => {
                const year = new Date().getFullYear() - i
                return { value: year.toString(), label: year.toString() }
              })}
            />
            <Button variant="ghost" size="sm" onClick={loadHAPreview} disabled={haPreviewLoading}>
              <RefreshCw className={`h-4 w-4 ${haPreviewLoading ? 'animate-spin' : ''}`} />
            </Button>
          </div>

          {/* Status Messages */}
          {haPreviewError && <Alert type="error">{haPreviewError}</Alert>}
          {haImportSuccess && <Alert type="success">{haImportSuccess}</Alert>}

          {/* Loading */}
          {haPreviewLoading && (
            <div className="flex justify-center py-8">
              <LoadingSpinner text="Lade HA-Daten..." />
            </div>
          )}

          {/* Preview */}
          {haPreview && !haPreviewLoading && (
            <>
              {/* Connection Status */}
              <div className="flex items-center gap-4 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <div className="flex items-center gap-2">
                  {haPreview.ha_verbunden ? (
                    <>
                      <CheckCircle className="w-4 h-4 text-green-500" />
                      <span className="text-sm text-green-600 dark:text-green-400">HA verbunden</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="w-4 h-4 text-red-500" />
                      <span className="text-sm text-red-600 dark:text-red-400">HA nicht verbunden</span>
                    </>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {haPreview.sensor_konfiguriert ? (
                    <>
                      <CheckCircle className="w-4 h-4 text-green-500" />
                      <span className="text-sm text-green-600 dark:text-green-400">PV-Sensor konfiguriert</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="w-4 h-4 text-yellow-500" />
                      <span className="text-sm text-yellow-600 dark:text-yellow-400">Kein PV-Sensor konfiguriert</span>
                    </>
                  )}
                </div>
              </div>

              {/* Monatsliste */}
              {haPreview.monate.length > 0 ? (
                <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-100 dark:bg-gray-800">
                      <tr>
                        <th className="text-left p-3 font-medium">Monat</th>
                        <th className="text-right p-3 font-medium">In DB</th>
                        <th className="text-right p-3 font-medium">In HA</th>
                        <th className="text-center p-3 font-medium">Status</th>
                        <th className="text-right p-3 font-medium">Aktion</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                      {haPreview.monate.map((m) => (
                        <HAImportRow
                          key={m.monat}
                          monat={m}
                          jahr={selectedHAYear}
                          onImport={(ueberschreiben) => handleHAImport(m.monat, ueberschreiben)}
                          importing={haImporting}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500">
                  Keine Daten für {selectedHAYear} verfügbar
                </div>
              )}

              {/* Alle importieren Button */}
              {haPreview.monate.some((m) => m.kann_importieren) && (
                <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                  <Button
                    onClick={() => handleHAImport(undefined, false)}
                    disabled={haImporting}
                  >
                    <Download className="h-4 w-4 mr-2" />
                    Alle fehlenden importieren
                  </Button>
                </div>
              )}
            </>
          )}

          {/* Nicht verbunden */}
          {!haPreview && !haPreviewLoading && !haPreviewError && (
            <div className="text-center py-8">
              <Home className="h-12 w-12 mx-auto text-gray-400 mb-4" />
              <p className="text-gray-600 dark:text-gray-300">
                Home Assistant Integration nicht verfügbar.
              </p>
              <p className="text-sm text-gray-500 mt-2">
                Bitte konfiguriere die HA-Sensoren in den Add-on-Einstellungen.
              </p>
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}

// Hilfskomponente für eine Importzeile
function HAImportRow({
  monat,
  jahr,
  onImport,
  importing,
}: {
  monat: HAImportPreviewMonth
  jahr: number
  onImport: (ueberschreiben: boolean) => void
  importing: boolean
}) {
  const formatKwh = (val: number | null) =>
    val !== null ? val.toLocaleString('de-DE', { maximumFractionDigits: 1 }) + ' kWh' : '-'

  return (
    <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
      <td className="p-3 font-medium">{monatNamenVoll[monat.monat]} {jahr}</td>
      <td className="p-3 text-right font-mono text-gray-600 dark:text-gray-400">
        {formatKwh(monat.pv_erzeugung_db)}
        {monat.datenquelle && (
          <span className="ml-1 text-xs text-gray-400">({monat.datenquelle})</span>
        )}
      </td>
      <td className="p-3 text-right font-mono text-cyan-600 dark:text-cyan-400">
        {formatKwh(monat.pv_erzeugung_ha)}
      </td>
      <td className="p-3 text-center">
        {monat.existiert_in_db ? (
          monat.kann_aktualisieren ? (
            <span className="inline-flex items-center gap-1 text-xs text-yellow-600 dark:text-yellow-400">
              <RefreshCw className="w-3 h-3" />
              Aktualisierbar
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
              <CheckCircle className="w-3 h-3" />
              Vorhanden
            </span>
          )
        ) : monat.pv_erzeugung_ha !== null ? (
          <span className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400">
            <Download className="w-3 h-3" />
            Importierbar
          </span>
        ) : (
          <span className="text-xs text-gray-400">Keine Daten</span>
        )}
      </td>
      <td className="p-3 text-right">
        {monat.kann_importieren && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onImport(false)}
            disabled={importing}
          >
            <Download className="h-4 w-4" />
          </Button>
        )}
        {monat.kann_aktualisieren && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onImport(true)}
            disabled={importing}
            title="Mit HA-Daten überschreiben"
          >
            <RefreshCw className="h-4 w-4 text-yellow-500" />
          </Button>
        )}
      </td>
    </tr>
  )
}
