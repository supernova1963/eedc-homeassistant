import { useState, FormEvent } from 'react'
import { Plus, Edit, Trash2, Zap, Calendar, Check } from 'lucide-react'
import { Button, Card, Modal, EmptyState, LoadingSpinner, Alert, Input } from '../components/ui'
import { Table, TableHead, TableBody, TableRow, TableHeader, TableCell } from '../components/ui'
import { useAnlagen, useStrompreise } from '../hooks'
import type { Strompreis, StrompreisVerwendung } from '../types'
import type { StrompreisCreate, StrompreisUpdate } from '../api'

export default function Strompreise() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)

  const anlageId = selectedAnlageId ?? anlagen[0]?.id
  const { strompreise, loading, error, createStrompreis, updateStrompreis, deleteStrompreis } = useStrompreise(anlageId)

  const [showForm, setShowForm] = useState(false)
  const [editingStrompreis, setEditingStrompreis] = useState<Strompreis | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<Strompreis | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const handleCreate = async (data: StrompreisCreate) => {
    try {
      setFormError(null)
      await createStrompreis(data)
      setShowForm(false)
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Fehler beim Erstellen')
    }
  }

  const handleUpdate = async (data: StrompreisUpdate) => {
    if (!editingStrompreis) return
    try {
      setFormError(null)
      await updateStrompreis(editingStrompreis.id, data)
      setEditingStrompreis(null)
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Fehler beim Aktualisieren')
    }
  }

  const handleDelete = async () => {
    if (!deleteConfirm) return
    try {
      await deleteStrompreis(deleteConfirm.id)
      setDeleteConfirm(null)
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Fehler beim Löschen')
    }
  }

  // Prüfe ob ein Strompreis aktuell gültig ist
  const isAktuell = (sp: Strompreis): boolean => {
    const heute = new Date().toISOString().split('T')[0]
    const abOk = sp.gueltig_ab <= heute
    const bisOk = !sp.gueltig_bis || sp.gueltig_bis >= heute
    return abOk && bisOk
  }

  if (anlagenLoading || loading) {
    return <LoadingSpinner text="Lade Strompreise..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Strompreise</h1>
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an, um Strompreise zu verwalten.
        </Alert>
      </div>
    )
  }

  const verwendungLabel = (v: StrompreisVerwendung) => {
    switch (v) {
      case 'waermepumpe': return 'Warmepumpe'
      case 'wallbox': return 'Wallbox'
      default: return 'Standard'
    }
  }

  // Sortiere: Aktuell + allgemein zuerst, dann Spezialtarife, dann historisch
  const sortedStrompreise = [...strompreise].sort((a, b) => {
    const aAktuell = isAktuell(a)
    const bAktuell = isAktuell(b)
    if (aAktuell !== bAktuell) return aAktuell ? -1 : 1
    const aAllgemein = (a.verwendung || 'allgemein') === 'allgemein'
    const bAllgemein = (b.verwendung || 'allgemein') === 'allgemein'
    if (aAllgemein !== bAllgemein) return aAllgemein ? -1 : 1
    return b.gueltig_ab.localeCompare(a.gueltig_ab)
  })

  // Aktive Spezialtarife für Info-Box
  const aktiveSpezialtarife = sortedStrompreise.filter(sp => isAktuell(sp) && sp.verwendung && sp.verwendung !== 'allgemein')
  const aktuellerStandard = sortedStrompreise.find(sp => isAktuell(sp) && (!sp.verwendung || sp.verwendung === 'allgemein'))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Strompreise
        </h1>
        <div className="flex items-center gap-3">
          {anlagen.length > 1 && (
            <select
              value={anlageId ?? ''}
              onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
              className="input w-auto"
              title="Anlage auswahlen"
            >
              {anlagen.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.anlagenname}
                </option>
              ))}
            </select>
          )}
          <Button onClick={() => setShowForm(true)}>
            <Plus className="h-5 w-5 mr-2" />
            Neuer Tarif
          </Button>
        </div>
      </div>

      {error && <Alert type="error">{error}</Alert>}

      {/* Info-Box für aktuellen Tarif */}
      {aktuellerStandard && (
        <Card className="bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-full bg-green-100 dark:bg-green-800">
              <Check className="h-6 w-6 text-green-600 dark:text-green-400" />
            </div>
            <div className="flex-1">
              <h3 className="font-medium text-green-800 dark:text-green-200">
                Aktueller Tarif: {aktuellerStandard.tarifname || 'Standard'}
              </h3>
              <p className="text-sm text-green-700 dark:text-green-300">
                Netzbezug: <strong>{aktuellerStandard.netzbezug_arbeitspreis_cent_kwh.toFixed(2)} ct/kWh</strong>
                {' · '}
                Einspeisung: <strong>{aktuellerStandard.einspeiseverguetung_cent_kwh.toFixed(2)} ct/kWh</strong>
                {aktuellerStandard.grundpreis_euro_monat ? (
                  <> · Grundpreis: <strong>{aktuellerStandard.grundpreis_euro_monat.toFixed(2)} €/Monat</strong></>
                ) : null}
              </p>
              {aktiveSpezialtarife.length > 0 && (
                <div className="mt-2 pt-2 border-t border-green-200 dark:border-green-700 space-y-1">
                  {aktiveSpezialtarife.map(sp => (
                    <p key={sp.id} className="text-sm text-green-700 dark:text-green-300">
                      <span className={`inline-block text-xs px-1.5 py-0.5 rounded mr-2 ${sp.verwendung === 'waermepumpe' ? 'bg-orange-100 dark:bg-orange-800 text-orange-700 dark:text-orange-300' : 'bg-blue-100 dark:bg-blue-800 text-blue-700 dark:text-blue-300'}`}>
                        {verwendungLabel(sp.verwendung)}
                      </span>
                      <strong>{sp.netzbezug_arbeitspreis_cent_kwh.toFixed(2)} ct/kWh</strong>
                      {' '}
                      <span className="text-green-600 dark:text-green-400">
                        ({(aktuellerStandard.netzbezug_arbeitspreis_cent_kwh - sp.netzbezug_arbeitspreis_cent_kwh).toFixed(2)} ct/kWh gunstiger)
                      </span>
                    </p>
                  ))}
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      {strompreise.length === 0 ? (
        <Card>
          <EmptyState
            icon={Zap}
            title="Keine Strompreise vorhanden"
            description="Lege deinen Stromtarif an, um Einsparungen und Kosten korrekt zu berechnen."
            action={
              <Button onClick={() => setShowForm(true)}>
                Ersten Tarif anlegen
              </Button>
            }
          />
        </Card>
      ) : (
        <Card padding="none">
          <Table>
            <TableHead>
              <TableRow>
                <TableHeader>Tarif</TableHeader>
                <TableHeader>Verwendung</TableHeader>
                <TableHeader>Netzbezug</TableHeader>
                <TableHeader>Einspeisung</TableHeader>
                <TableHeader>Grundpreis</TableHeader>
                <TableHeader>Gültigkeit</TableHeader>
                <TableHeader className="text-right">Aktionen</TableHeader>
              </TableRow>
            </TableHead>
            <TableBody>
              {sortedStrompreise.map((sp) => {
                const aktuell = isAktuell(sp)
                return (
                  <TableRow key={sp.id} className={aktuell ? 'bg-green-50/50 dark:bg-green-900/10' : ''}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Zap className={`h-5 w-5 ${aktuell ? 'text-green-500' : 'text-gray-400'}`} />
                        <div>
                          <span className="font-medium">
                            {sp.tarifname || 'Standard'}
                          </span>
                          {aktuell && (
                            <span className="ml-2 text-xs px-2 py-0.5 bg-green-100 dark:bg-green-800 text-green-700 dark:text-green-300 rounded">
                              Aktuell
                            </span>
                          )}
                          {sp.anbieter && (
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                              {sp.anbieter}
                            </p>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      {(!sp.verwendung || sp.verwendung === 'allgemein') ? (
                        <span className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded">
                          Standard
                        </span>
                      ) : sp.verwendung === 'waermepumpe' ? (
                        <span className="text-xs px-2 py-0.5 bg-orange-100 dark:bg-orange-800 text-orange-700 dark:text-orange-300 rounded">
                          Warmepumpe
                        </span>
                      ) : (
                        <span className="text-xs px-2 py-0.5 bg-blue-100 dark:bg-blue-800 text-blue-700 dark:text-blue-300 rounded">
                          Wallbox
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-red-600 dark:text-red-400">
                        {sp.netzbezug_arbeitspreis_cent_kwh.toFixed(2)}
                      </span>
                      <span className="text-gray-500 text-sm"> ct/kWh</span>
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-green-600 dark:text-green-400">
                        {sp.einspeiseverguetung_cent_kwh.toFixed(2)}
                      </span>
                      <span className="text-gray-500 text-sm"> ct/kWh</span>
                    </TableCell>
                    <TableCell>
                      {sp.grundpreis_euro_monat ? (
                        <>
                          <span className="font-mono">{sp.grundpreis_euro_monat.toFixed(2)}</span>
                          <span className="text-gray-500 text-sm"> €/Mon</span>
                        </>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1 text-sm text-gray-500">
                        <Calendar className="h-4 w-4" />
                        {new Date(sp.gueltig_ab).toLocaleDateString('de-DE')}
                        {sp.gueltig_bis && (
                          <> - {new Date(sp.gueltig_bis).toLocaleDateString('de-DE')}</>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditingStrompreis(sp)}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteConfirm(sp)}
                        >
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

      {/* Hinweis */}
      <Card>
        <h3 className="font-medium text-gray-900 dark:text-white mb-2">Hinweise</h3>
        <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1 list-disc list-inside">
          <li>Der aktuell gültige Tarif wird automatisch für Berechnungen verwendet</li>
          <li>Für historische Auswertungen werden die zum jeweiligen Zeitpunkt gültigen Preise herangezogen</li>
          <li>Bei Tarifwechsel: Neuen Tarif anlegen und Gültigkeitszeitraum korrekt setzen</li>
          <li><strong>Spezialtarife:</strong> Für Warmepumpe oder Wallbox mit separatem Stromtarif kann ein eigener Tarif angelegt werden. Ohne Spezialtarif wird automatisch der Standard-Tarif verwendet.</li>
        </ul>
      </Card>

      {/* Create Modal */}
      <Modal
        isOpen={showForm}
        onClose={() => { setShowForm(false); setFormError(null) }}
        title="Neuen Tarif anlegen"
        size="lg"
      >
        {anlageId && (
          <StrompreisForm
            anlageId={anlageId}
            onCreate={handleCreate}
            onCancel={() => { setShowForm(false); setFormError(null) }}
            error={formError}
          />
        )}
      </Modal>

      {/* Edit Modal */}
      <Modal
        isOpen={!!editingStrompreis}
        onClose={() => { setEditingStrompreis(null); setFormError(null) }}
        title="Tarif bearbeiten"
        size="lg"
      >
        {editingStrompreis && (
          <StrompreisForm
            strompreis={editingStrompreis}
            anlageId={editingStrompreis.anlage_id}
            onUpdate={handleUpdate}
            onCancel={() => { setEditingStrompreis(null); setFormError(null) }}
            error={formError}
          />
        )}
      </Modal>

      {/* Delete Confirmation */}
      <Modal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        title="Tarif löschen"
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-gray-600 dark:text-gray-300">
            Möchtest du den Tarif <strong>"{deleteConfirm?.tarifname || 'Standard'}"</strong> wirklich löschen?
          </p>
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

// Strompreis Form Component
interface StrompreisFormProps {
  strompreis?: Strompreis
  anlageId: number
  onCreate?: (data: StrompreisCreate) => Promise<void>
  onUpdate?: (data: StrompreisUpdate) => Promise<void>
  onCancel: () => void
  error?: string | null
}

function StrompreisForm({ strompreis, anlageId, onCreate, onUpdate, onCancel, error }: StrompreisFormProps) {
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    tarifname: strompreis?.tarifname || '',
    anbieter: strompreis?.anbieter || '',
    netzbezug_arbeitspreis_cent_kwh: strompreis?.netzbezug_arbeitspreis_cent_kwh?.toString() || '30',
    einspeiseverguetung_cent_kwh: strompreis?.einspeiseverguetung_cent_kwh?.toString() || '8.2',
    grundpreis_euro_monat: strompreis?.grundpreis_euro_monat?.toString() || '',
    gueltig_ab: strompreis?.gueltig_ab || new Date().toISOString().split('T')[0],
    gueltig_bis: strompreis?.gueltig_bis || '',
    vertragsart: strompreis?.vertragsart || '',
    verwendung: (strompreis?.verwendung || 'allgemein') as StrompreisVerwendung,
  })

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      const baseData = {
        netzbezug_arbeitspreis_cent_kwh: parseFloat(formData.netzbezug_arbeitspreis_cent_kwh),
        einspeiseverguetung_cent_kwh: parseFloat(formData.einspeiseverguetung_cent_kwh),
        grundpreis_euro_monat: formData.grundpreis_euro_monat ? parseFloat(formData.grundpreis_euro_monat) : undefined,
        gueltig_ab: formData.gueltig_ab,
        gueltig_bis: formData.gueltig_bis || undefined,
        tarifname: formData.tarifname || undefined,
        anbieter: formData.anbieter || undefined,
        vertragsart: formData.vertragsart || undefined,
        verwendung: formData.verwendung,
      }

      if (strompreis && onUpdate) {
        await onUpdate(baseData)
      } else if (onCreate) {
        await onCreate({ ...baseData, anlage_id: anlageId })
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && <Alert type="error">{error}</Alert>}

      {/* Tarif-Verwendung */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Tarif-Verwendung
        </label>
        <select
          name="verwendung"
          value={formData.verwendung}
          onChange={handleChange}
          className="input w-full"
          title="Tarif-Verwendung"
        >
          <option value="allgemein">Standard (allgemein)</option>
          <option value="waermepumpe">Warmepumpe (Spezialtarif)</option>
          <option value="wallbox">Wallbox (Spezialtarif)</option>
        </select>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {formData.verwendung === 'allgemein'
            ? 'Standard-Tarif fur alle Berechnungen. Wird auch als Fallback fur WP/Wallbox ohne Spezialtarif genutzt.'
            : 'Spezialtarif wird nur fur diese Komponente verwendet. Ohne Spezialtarif gilt der Standard-Tarif.'}
        </p>
      </div>

      {/* Tarif-Info */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input
          label="Tarifname"
          name="tarifname"
          value={formData.tarifname}
          onChange={handleChange}
          placeholder="z.B. Grundversorgung, Öko-Strom"
        />
        <Input
          label="Anbieter"
          name="anbieter"
          value={formData.anbieter}
          onChange={handleChange}
          placeholder="z.B. Stadtwerke"
        />
      </div>

      {/* Preise */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Preise</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Input
            label="Netzbezug (ct/kWh)"
            name="netzbezug_arbeitspreis_cent_kwh"
            type="number"
            step="0.01"
            min="0"
            value={formData.netzbezug_arbeitspreis_cent_kwh}
            onChange={handleChange}
            required
            hint="Arbeitspreis für Strombezug"
          />
          <Input
            label="Einspeisevergütung (ct/kWh)"
            name="einspeiseverguetung_cent_kwh"
            type="number"
            step="0.01"
            min="0"
            value={formData.einspeiseverguetung_cent_kwh}
            onChange={handleChange}
            required
            hint="EEG-Vergütung oder PPA-Preis"
          />
          <Input
            label="Grundpreis (€/Monat)"
            name="grundpreis_euro_monat"
            type="number"
            step="0.01"
            min="0"
            value={formData.grundpreis_euro_monat}
            onChange={handleChange}
            hint="Optional"
          />
        </div>
      </div>

      {/* Gültigkeit */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Gültigkeit</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Gültig ab"
            name="gueltig_ab"
            type="date"
            min="2000-01-01"
            max="2099-12-31"
            value={formData.gueltig_ab}
            onChange={handleChange}
            required
          />
          <Input
            label="Gültig bis"
            name="gueltig_bis"
            type="date"
            min="2000-01-01"
            max="2099-12-31"
            value={formData.gueltig_bis}
            onChange={handleChange}
            hint="Leer lassen für unbefristet"
          />
        </div>
      </div>

      {/* Vertragsart */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Vertragsart
        </label>
        <select
          name="vertragsart"
          value={formData.vertragsart}
          onChange={handleChange}
          className="input w-full"
          title="Vertragsart"
        >
          <option value="">Bitte wählen</option>
          <option value="grundversorgung">Grundversorgung</option>
          <option value="sondervertrag">Sondervertrag</option>
          <option value="dynamisch">Dynamischer Tarif</option>
          <option value="oeko">Ökostrom</option>
        </select>
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button type="submit" loading={loading}>
          {strompreis ? 'Speichern' : 'Anlegen'}
        </Button>
      </div>
    </form>
  )
}
