/**
 * Strompreise — geteilte Teile (Daten-Hook + CRUD + Präsentations-Sektionen + Formular).
 *
 * EINE Code-Wahrheit für IST (`pages/Strompreise.tsx`) und IA-V4 (Einstellungen-Katalog-
 * Block, `config/einstellungenKatalog.tsx`). Die Sektionen rendern ihren Inhalt OHNE
 * äußere Card/Block-Hülle (der Aufrufer wickelt: V3 = Seiten-Layout, V4 = BlockShell).
 * Zahlen de-DE (`fmtZahl`), Preis-Farben aus der Zentrale (`GELD_TEXT_CLASS`:
 * Netzbezug = Kosten, Einspeisung = Erlös).
 */
import { useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { Plus, Edit, Trash2, Zap, Calendar, Check } from 'lucide-react'
import { Button, Card, Modal, EmptyState, Alert, Input, DatumFeld } from '../components/ui'
import { Table, TableHead, TableBody, TableRow, TableHeader, TableCell } from '../components/ui'
import { useStrompreise } from '../hooks'
import { GELD_TEXT_CLASS, fmtZahl } from '../lib'
import type { Strompreis, StrompreisVerwendung } from '../types'
import type { StrompreisCreate, StrompreisUpdate } from '../api'

// ─── Helfer ──────────────────────────────────────────────────────────────────

/** Ist ein Tarif zum heutigen Tag gültig (gültig-ab ≤ heute ≤ gültig-bis)? */
export function istAktuell(sp: Strompreis): boolean {
  const heute = new Date().toISOString().split('T')[0]
  const abOk = sp.gueltig_ab <= heute
  const bisOk = !sp.gueltig_bis || sp.gueltig_bis >= heute
  return abOk && bisOk
}

export function verwendungLabel(v: StrompreisVerwendung): string {
  switch (v) {
    case 'waermepumpe': return 'Wärmepumpe'
    case 'wallbox': return 'Wallbox'
    default: return 'Standard'
  }
}

// ─── Daten-Hook (Strompreise + abgeleitete Sortierung/Aktuell-Auswahl + CRUD) ──

export interface StrompreiseTeileDaten {
  strompreise: Strompreis[]
  loading: boolean
  error: string | null
  /** Aktuell + allgemein zuerst, dann Spezialtarife, dann historisch (absteigend). */
  sorted: Strompreis[]
  aktuellerStandard: Strompreis | undefined
  aktiveSpezialtarife: Strompreis[]
  createStrompreis: (data: StrompreisCreate) => Promise<Strompreis>
  updateStrompreis: (id: number, data: StrompreisUpdate) => Promise<Strompreis>
  deleteStrompreis: (id: number) => Promise<void>
}

export function useStrompreiseTeile(anlageId?: number): StrompreiseTeileDaten {
  const { strompreise, loading, error, createStrompreis, updateStrompreis, deleteStrompreis } =
    useStrompreise(anlageId)

  const sorted = useMemo(() => {
    return [...strompreise].sort((a, b) => {
      const aAktuell = istAktuell(a)
      const bAktuell = istAktuell(b)
      if (aAktuell !== bAktuell) return aAktuell ? -1 : 1
      const aAllgemein = (a.verwendung || 'allgemein') === 'allgemein'
      const bAllgemein = (b.verwendung || 'allgemein') === 'allgemein'
      if (aAllgemein !== bAllgemein) return aAllgemein ? -1 : 1
      return b.gueltig_ab.localeCompare(a.gueltig_ab)
    })
  }, [strompreise])

  const aktiveSpezialtarife = useMemo(
    () => sorted.filter((sp) => istAktuell(sp) && sp.verwendung && sp.verwendung !== 'allgemein'),
    [sorted],
  )
  const aktuellerStandard = useMemo(
    () => sorted.find((sp) => istAktuell(sp) && (!sp.verwendung || sp.verwendung === 'allgemein')),
    [sorted],
  )

  return {
    strompreise, loading, error, sorted, aktuellerStandard, aktiveSpezialtarife,
    createStrompreis, updateStrompreis, deleteStrompreis,
  }
}

// ─── Sektion: Info-Box aktueller Tarif ────────────────────────────────────────

export function StrompreisAktuellInfo({
  aktuellerStandard,
  aktiveSpezialtarife,
}: {
  aktuellerStandard: Strompreis
  aktiveSpezialtarife: Strompreis[]
}) {
  return (
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
            Netzbezug: <strong>{fmtZahl(aktuellerStandard.netzbezug_arbeitspreis_cent_kwh, 2)} ct/kWh</strong>
            {' · '}
            Einspeisung: <strong>{fmtZahl(aktuellerStandard.einspeiseverguetung_cent_kwh, 2)} ct/kWh</strong>
            {aktuellerStandard.grundpreis_euro_monat ? (
              <> · Grundpreis: <strong>{fmtZahl(aktuellerStandard.grundpreis_euro_monat, 2)} €/Monat</strong></>
            ) : null}
          </p>
          {aktiveSpezialtarife.length > 0 && (
            <div className="mt-2 pt-2 border-t border-green-200 dark:border-green-700 space-y-1">
              {aktiveSpezialtarife.map((sp) => (
                <p key={sp.id} className="text-sm text-green-700 dark:text-green-300">
                  <span className={`inline-block text-xs px-1.5 py-0.5 rounded mr-2 ${sp.verwendung === 'waermepumpe' ? 'bg-orange-100 dark:bg-orange-800 text-orange-700 dark:text-orange-300' : 'bg-blue-100 dark:bg-blue-800 text-blue-700 dark:text-blue-300'}`}>
                    {verwendungLabel(sp.verwendung)}
                  </span>
                  <strong>{fmtZahl(sp.netzbezug_arbeitspreis_cent_kwh, 2)} ct/kWh</strong>
                  {' '}
                  <span className="text-green-600 dark:text-green-400">
                    ({fmtZahl(aktuellerStandard.netzbezug_arbeitspreis_cent_kwh - sp.netzbezug_arbeitspreis_cent_kwh, 2)} ct/kWh günstiger)
                  </span>
                </p>
              ))}
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}

// ─── Sektion: Tarif-Tabelle ───────────────────────────────────────────────────

export function StrompreisTabelle({
  sorted,
  onEdit,
  onDelete,
}: {
  sorted: Strompreis[]
  onEdit: (sp: Strompreis) => void
  onDelete: (sp: Strompreis) => void
}) {
  // Verwendungs-Badge — EINE Wahrheit für Tabellen-Zeile und Kachel.
  const verwendungBadge = (sp: Strompreis) =>
    (!sp.verwendung || sp.verwendung === 'allgemein') ? (
      <span className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded">Standard</span>
    ) : sp.verwendung === 'waermepumpe' ? (
      <span className="text-xs px-2 py-0.5 bg-orange-100 dark:bg-orange-800 text-orange-700 dark:text-orange-300 rounded">Wärmepumpe</span>
    ) : (
      <span className="text-xs px-2 py-0.5 bg-blue-100 dark:bg-blue-800 text-blue-700 dark:text-blue-300 rounded">Wallbox</span>
    )

  return (
    <>
    {/* Abnahme-Fund R14 (Gernot 2026-07-03): < lg Kachel-Darstellung statt
        gequetschter Tabelle. */}
    <div className="lg:hidden space-y-3">
      {sorted.map((sp) => {
        const aktuell = istAktuell(sp)
        return (
          <Card key={sp.id} padding="sm" className={aktuell ? 'bg-green-50/50 dark:bg-green-900/10' : ''}>
            <div className="flex items-center gap-2 flex-wrap">
              <Zap className={`h-5 w-5 shrink-0 ${aktuell ? 'text-green-500' : 'text-gray-400 dark:text-gray-500'}`} />
              <span className="font-medium text-gray-900 dark:text-white">{sp.tarifname || 'Standard'}</span>
              {aktuell && (
                <span className="text-xs px-2 py-0.5 bg-green-100 dark:bg-green-800 text-green-700 dark:text-green-300 rounded">Aktuell</span>
              )}
              {verwendungBadge(sp)}
            </div>
            {sp.anbieter && <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{sp.anbieter}</p>}
            <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <div><span className="text-gray-500 dark:text-gray-400">Netzbezug</span><br /><span className={`font-mono ${GELD_TEXT_CLASS.kosten}`}>{fmtZahl(sp.netzbezug_arbeitspreis_cent_kwh, 2)}</span> <span className="text-gray-500 text-xs">ct/kWh</span></div>
              <div><span className="text-gray-500 dark:text-gray-400">Einspeisung</span><br /><span className={`font-mono ${GELD_TEXT_CLASS.ertrag}`}>{fmtZahl(sp.einspeiseverguetung_cent_kwh, 2)}</span> <span className="text-gray-500 text-xs">ct/kWh</span></div>
              <div><span className="text-gray-500 dark:text-gray-400">Grundpreis</span><br />{sp.grundpreis_euro_monat ? <><span className="font-mono">{fmtZahl(sp.grundpreis_euro_monat, 2)}</span> <span className="text-gray-500 text-xs">€/Mon</span></> : '—'}</div>
              <div><span className="text-gray-500 dark:text-gray-400">Gültigkeit</span><br />{new Date(sp.gueltig_ab).toLocaleDateString('de-DE')}{sp.gueltig_bis && <> – {new Date(sp.gueltig_bis).toLocaleDateString('de-DE')}</>}</div>
            </div>
            <div className="mt-2 border-t border-gray-100 dark:border-gray-700 pt-1 flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => onEdit(sp)} aria-label="Tarif bearbeiten">
                <Edit className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="sm" onClick={() => onDelete(sp)} aria-label="Tarif löschen">
                <Trash2 className="h-4 w-4 text-red-500" />
              </Button>
            </div>
          </Card>
        )
      })}
    </div>
    <Card padding="none" className="overflow-hidden hidden lg:block">
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
          {sorted.map((sp) => {
            const aktuell = istAktuell(sp)
            return (
              <TableRow key={sp.id} className={aktuell ? 'bg-green-50/50 dark:bg-green-900/10' : ''}>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <Zap className={`h-5 w-5 ${aktuell ? 'text-green-500' : 'text-gray-400 dark:text-gray-500'}`} />
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
                <TableCell>{verwendungBadge(sp)}</TableCell>
                <TableCell>
                  <span className={`font-mono ${GELD_TEXT_CLASS.kosten}`}>
                    {fmtZahl(sp.netzbezug_arbeitspreis_cent_kwh, 2)}
                  </span>
                  <span className="text-gray-500 text-sm"> ct/kWh</span>
                </TableCell>
                <TableCell>
                  <span className={`font-mono ${GELD_TEXT_CLASS.ertrag}`}>
                    {fmtZahl(sp.einspeiseverguetung_cent_kwh, 2)}
                  </span>
                  <span className="text-gray-500 text-sm"> ct/kWh</span>
                </TableCell>
                <TableCell>
                  {sp.grundpreis_euro_monat ? (
                    <>
                      <span className="font-mono">{fmtZahl(sp.grundpreis_euro_monat, 2)}</span>
                      <span className="text-gray-500 text-sm"> €/Mon</span>
                    </>
                  ) : (
                    <span className="text-gray-400 dark:text-gray-500">—</span>
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1 text-sm text-gray-500">
                    <Calendar className="h-4 w-4" />
                    {new Date(sp.gueltig_ab).toLocaleDateString('de-DE')}
                    {sp.gueltig_bis && (
                      <> – {new Date(sp.gueltig_bis).toLocaleDateString('de-DE')}</>
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" size="sm" onClick={() => onEdit(sp)} aria-label="Tarif bearbeiten">
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => onDelete(sp)} aria-label="Tarif löschen">
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
    </>
  )
}

// ─── Sektion: Leer-Zustand ────────────────────────────────────────────────────

export function StrompreisEmpty({ onCreate }: { onCreate: () => void }) {
  return (
    <Card>
      <EmptyState
        icon={Zap}
        title="Keine Strompreise vorhanden"
        description="Lege deinen Stromtarif an, um Einsparungen und Kosten korrekt zu berechnen."
        action={<Button onClick={onCreate}>Ersten Tarif anlegen</Button>}
      />
    </Card>
  )
}

// ─── Sektion: Hinweise ────────────────────────────────────────────────────────

export function StrompreisHinweise() {
  return (
    <Card>
      <h3 className="font-medium text-gray-900 dark:text-white mb-2">Hinweise</h3>
      <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1 list-disc list-inside">
        <li>Der aktuell gültige Tarif wird automatisch für Berechnungen verwendet</li>
        <li>Für historische Auswertungen werden die zum jeweiligen Zeitpunkt gültigen Preise herangezogen</li>
        <li>Bei Tarifwechsel: Neuen Tarif anlegen und Gültigkeitszeitraum korrekt setzen</li>
        <li><strong>Spezialtarife:</strong> Für Wärmepumpe oder Wallbox mit separatem Stromtarif kann ein eigener Tarif angelegt werden. Ohne Spezialtarif wird automatisch der Standard-Tarif verwendet.</li>
      </ul>
    </Card>
  )
}

// ─── Komplett-Verwaltung (von V3-Seite UND V4-Block genutzt) ──────────────────

/**
 * Interaktive Strompreis-Verwaltung: Kopfzeile (optionaler Zusatz + „Neuer Tarif"),
 * Info-Box, Tabelle/Leer-Zustand, Hinweise und die Create-/Edit-/Delete-Modals.
 * Hält den eigenen UI-State (offenes Formular, Bearbeitung, Lösch-Bestätigung) und
 * fährt CRUD über {@link useStrompreiseTeile}. `kopfZusatz` = links neben „Neuer Tarif"
 * (V3: Anlage-Auswahl; V4: leer).
 */
export function StrompreiseVerwaltung({
  anlageId,
  kopfZusatz,
}: {
  anlageId: number
  kopfZusatz?: ReactNode
}) {
  const {
    sorted, aktuellerStandard, aktiveSpezialtarife, error,
    createStrompreis, updateStrompreis, deleteStrompreis,
  } = useStrompreiseTeile(anlageId)

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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end">
        <div className="flex items-center gap-3">
          {kopfZusatz}
          <Button onClick={() => setShowForm(true)}>
            <Plus className="h-5 w-5 mr-2" />
            Neuer Tarif
          </Button>
        </div>
      </div>

      {error && <Alert type="error">{error}</Alert>}

      {aktuellerStandard && (
        <StrompreisAktuellInfo aktuellerStandard={aktuellerStandard} aktiveSpezialtarife={aktiveSpezialtarife} />
      )}

      {sorted.length === 0 ? (
        <StrompreisEmpty onCreate={() => setShowForm(true)} />
      ) : (
        <StrompreisTabelle sorted={sorted} onEdit={setEditingStrompreis} onDelete={setDeleteConfirm} />
      )}

      <StrompreisHinweise />

      {/* Create Modal */}
      <Modal
        isOpen={showForm}
        onClose={() => { setShowForm(false); setFormError(null) }}
        title="Neuen Tarif anlegen"
        size="lg"
      >
        <StrompreisForm
          anlageId={anlageId}
          onCreate={handleCreate}
          onCancel={() => { setShowForm(false); setFormError(null) }}
          error={formError}
        />
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

// ─── Tarif-Formular ───────────────────────────────────────────────────────────

interface StrompreisFormProps {
  strompreis?: Strompreis
  anlageId: number
  onCreate?: (data: StrompreisCreate) => Promise<void>
  onUpdate?: (data: StrompreisUpdate) => Promise<void>
  onCancel: () => void
  error?: string | null
}

export function StrompreisForm({ strompreis, anlageId, onCreate, onUpdate, onCancel, error }: StrompreisFormProps) {
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
          <option value="waermepumpe">Wärmepumpe (Spezialtarif)</option>
          <option value="wallbox">Wallbox (Spezialtarif)</option>
        </select>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {formData.verwendung === 'allgemein'
            ? 'Standard-Tarif für alle Berechnungen. Wird auch als Fallback für WP/Wallbox ohne Spezialtarif genutzt.'
            : 'Spezialtarif wird nur für diese Komponente verwendet. Ohne Spezialtarif gilt der Standard-Tarif.'}
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
        {/* D14-6 (detLAN #113): items-end — das zweizeilig umbrechende
            „Einspeisevergütung"-Label drückte sein Feld sonst unter die Nachbarn. */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
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
          {/* D14-13: DatumPicker-SoT statt nativem Datumsfeld (Einstellungen-Formulare). */}
          <DatumFeld
            label="Gültig ab"
            value={formData.gueltig_ab}
            onChange={(v) => setFormData(prev => ({ ...prev, gueltig_ab: v }))}
            required
          />
          <DatumFeld
            label="Gültig bis"
            value={formData.gueltig_bis}
            onChange={(v) => setFormData(prev => ({ ...prev, gueltig_bis: v }))}
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
