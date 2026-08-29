/**
 * Strompreise — geteilte Teile (Daten-Hook + CRUD + Präsentations-Sektionen + Formular).
 *
 * EINE Code-Wahrheit für IST (`pages/Strompreise.tsx`) und IA-V4 (Einstellungen-Katalog-
 * Block, `config/einstellungenKatalog.tsx`). Die Sektionen rendern ihren Inhalt OHNE
 * äußere Card/Block-Hülle (der Aufrufer wickelt: V3 = Seiten-Layout, V4 = BlockShell).
 * Zahlen de-DE (`fmtZahl`), Preis-Farben aus der Zentrale (`GELD_TEXT_CLASS`:
 * Netzbezug = Kosten, Einspeisung = Erlös).
 */
import { useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Plus, Edit, Trash2, Zap, Calendar, Check } from 'lucide-react'
import { Button, Card, Modal, EmptyState, Alert, Input, DatumFeld, Select, RadioGroup, FormSection, SegmentMehrfach } from '../components/ui'
import { Table, TableHead, TableBody, TableRow, TableHeader, TableCell } from '../components/ui'
import { SchalterZeile } from '../components/forms/sections/SchalterZeile'
import { useAnlage, useStrompreise } from '../hooks'
import { GELD_TEXT_CLASS, fmtZahl, heuteIso, monatsersterVon, EINSPEISEVERGUETUNG_FLAT_HINWEIS } from '../lib'
import type { Strompreis, StrompreisVerwendung, StrompreisZeitfenster } from '../types'
import type { StrompreisCreate, StrompreisUpdate } from '../api'

// ─── Helfer ──────────────────────────────────────────────────────────────────

/** Ist ein Tarif zum heutigen Tag gültig (gültig-ab ≤ heute ≤ gültig-bis)? */
export function istGueltigHeute(sp: Strompreis): boolean {
  // Lokales Datum (F-5): mit dem UTC-Datum galt ein heute beginnender Tarif
  // nachts noch nicht — und der abgelöste noch.
  const heute = heuteIso()
  const abOk = sp.gueltig_ab <= heute
  const bisOk = !sp.gueltig_bis || sp.gueltig_bis >= heute
  return abOk && bisOk
}

/**
 * IDs der Tarife, mit denen eedc heute tatsächlich rechnet — je Verwendung genau EINER.
 *
 * Spiegelt `backend/api/routes/strompreise.py::lade_tarife_fuer_anlage`: gültig am
 * Stichtag UND je Verwendung der jüngste `gueltig_ab` (der jüngere Eintrag löst den
 * älteren ab, „Gültig bis" darf leer bleiben). Genau das war vorher nicht abgebildet —
 * `istAktuell` prüfte nur die Gültigkeit des einzelnen Eintrags, also trug JEDER
 * historische Tarif ohne „Gültig bis" das grüne „Aktuell" (Forum simon42 #89667/67,
 * Algie: drei Tarife, drei Badges). Gerechnet wurde immer richtig — die Liste behauptete
 * etwas anderes als die Rechnung, und das ist bei einem Preis die teuerste Sorte Drift.
 */
export function aktuelleTarifIds(strompreise: Strompreis[]): Set<number> {
  const jungster = new Map<string, Strompreis>()
  for (const sp of strompreise) {
    if (!istGueltigHeute(sp)) continue
    const verwendung = sp.verwendung || 'allgemein'
    const bisher = jungster.get(verwendung)
    if (!bisher || sp.gueltig_ab > bisher.gueltig_ab) jungster.set(verwendung, sp)
  }
  return new Set([...jungster.values()].map((sp) => sp.id))
}

/**
 * Vorbelegung für „Gültig ab" — **nur beim ersten Tarif einer Anlage**.
 *
 * Zwei Regeln in einer Funktion, weil sie sich gegenseitig begrenzen:
 *
 * 1. **Erster Tarif → Inbetriebnahme-Datum**, damit importierte Altmonate nicht
 *    hinter den Tarif fallen (Forum #89667/60, Algie).
 * 2. **Auf den Monatsersten gezogen (N-257)** — die Monatsrechnung fragt mit dem
 *    Monatsersten nach dem Tarif, ein Tarif ab dem 03.08. deckt den August also
 *    nicht ab. Wer die Vorbelegung stehen ließ, verlor reproduzierbar seinen
 *    ersten Monat.
 *
 * ⚠ **Ab dem zweiten Tarif `undefined`, und das ist der Punkt.** Dort ist
 * „heute" die richtige Annahme (Tarifwechsel); ihn auf den Monatsersten zu
 * ziehen würde den Wechsel **rückdatieren** und dem laufenden Monat den neuen
 * Preis geben. Die Regel darf also ausdrücklich nicht weiter gefasst werden.
 */
export function erstTarifVorbelegung(
  anzahlTarife: number,
  installationsdatum: string | null | undefined,
): string | undefined {
  if (anzahlTarife > 0) return undefined
  return monatsersterVon(installationsdatum)
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
  /** IDs der Tarife, mit denen heute gerechnet wird — je Verwendung genau einer. */
  aktuelleIds: Set<number>
  aktuellerStandard: Strompreis | undefined
  aktiveSpezialtarife: Strompreis[]
  createStrompreis: (data: StrompreisCreate) => Promise<Strompreis>
  updateStrompreis: (id: number, data: StrompreisUpdate) => Promise<Strompreis>
  deleteStrompreis: (id: number) => Promise<void>
}

export function useStrompreiseTeile(anlageId?: number): StrompreiseTeileDaten {
  const { strompreise, loading, error, createStrompreis, updateStrompreis, deleteStrompreis } =
    useStrompreise(anlageId)

  const aktuelleIds = useMemo(() => aktuelleTarifIds(strompreise), [strompreise])

  const sorted = useMemo(() => {
    return [...strompreise].sort((a, b) => {
      const aAktuell = aktuelleIds.has(a.id)
      const bAktuell = aktuelleIds.has(b.id)
      if (aAktuell !== bAktuell) return aAktuell ? -1 : 1
      const aAllgemein = (a.verwendung || 'allgemein') === 'allgemein'
      const bAllgemein = (b.verwendung || 'allgemein') === 'allgemein'
      if (aAllgemein !== bAllgemein) return aAllgemein ? -1 : 1
      return b.gueltig_ab.localeCompare(a.gueltig_ab)
    })
  }, [strompreise, aktuelleIds])

  const aktiveSpezialtarife = useMemo(
    () => sorted.filter((sp) => aktuelleIds.has(sp.id) && sp.verwendung && sp.verwendung !== 'allgemein'),
    [sorted, aktuelleIds],
  )
  const aktuellerStandard = useMemo(
    () => sorted.find((sp) => aktuelleIds.has(sp.id) && (!sp.verwendung || sp.verwendung === 'allgemein')),
    [sorted, aktuelleIds],
  )

  return {
    strompreise, loading, error, sorted, aktuelleIds, aktuellerStandard, aktiveSpezialtarife,
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
  aktuelleIds,
  onEdit,
  onDelete,
}: {
  sorted: Strompreis[]
  /** Aus `useStrompreiseTeile` — je Verwendung genau ein Tarif (s. `aktuelleTarifIds`). */
  aktuelleIds: Set<number>
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
        const aktuell = aktuelleIds.has(sp.id)
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
            const aktuell = aktuelleIds.has(sp.id)
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
        <li><strong>Dynamische Tarife:</strong> Der Netzbezugspreis bleibt auch hier Pflicht — er ist der Referenzwert. Vorrang hat immer der stündlich mitgeschriebene Preis; der eingetragene Wert greift für Monate ohne Aufzeichnung und für ROI-/Investitionsrechnungen, die keinen Stundenpreis kennen.</li>
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
    sorted, aktuelleIds, aktuellerStandard, aktiveSpezialtarife, error,
    createStrompreis, updateStrompreis, deleteStrompreis,
  } = useStrompreiseTeile(anlageId)
  const { anlage } = useAnlage(anlageId)

  // Nur beim ERSTEN Tarif vorbelegen: ab dem zweiten ist „heute" die richtige
  // Annahme (Tarifwechsel), und ein bestehender Eintrag darf nicht überschrieben
  // wirken. Siehe `gueltigAbVorbelegung` in StrompreisFormProps.
  // Benannte Regel statt Inline-Ausdruck, damit ein Rückbau nicht stumm bleibt:
  // die Grenze „nur beim ERSTEN Tarif" ist die eigentliche Aussage (N-257).
  const gueltigAbVorbelegung = erstTarifVorbelegung(sorted.length, anlage?.installationsdatum)

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
        <StrompreisTabelle sorted={sorted} aktuelleIds={aktuelleIds} onEdit={setEditingStrompreis} onDelete={setDeleteConfirm} />
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
          gueltigAbVorbelegung={gueltigAbVorbelegung}
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
  /**
   * Vorbelegung für „Gültig ab" beim ERSTEN Tarif einer Anlage (Inbetriebnahme-
   * Datum). Ohne sie stand dort das heutige Datum — bei einer Neuinstallation
   * mit Statistik-Import systematisch falsch: alle importierten Altmonate fielen
   * hinter den Tarif und rechneten still mit der 30-ct-Vorbelegung (Forum
   * simon42 #89667/60). Der Setup-Wizard belegt seit jeher so vor
   * (`StrompreiseStep`), die Einzelseite folgt jetzt derselben Mechanik.
   */
  gueltigAbVorbelegung?: string
}

const VERWENDUNG_OPTIONEN: readonly { value: StrompreisVerwendung; label: string; description: string }[] = [
  { value: 'allgemein', label: 'Standard (allgemein)', description: 'Für alle Berechnungen; Fallback für WP/Wallbox ohne eigenen Tarif.' },
  { value: 'waermepumpe', label: 'Wärmepumpe (Spezialtarif)', description: 'Wird nur für die Wärmepumpe verwendet.' },
  { value: 'wallbox', label: 'Wallbox (Spezialtarif)', description: 'Wird nur für die Wallbox verwendet.' },
]

// Roh-Enum nie sichtbar → Label-Map (Style-Guide D1 / TYP_LABELS-Muster).
const VERTRAGSART_OPTIONEN: { value: string; label: string }[] = [
  { value: 'grundversorgung', label: 'Grundversorgung' },
  { value: 'sondervertrag', label: 'Sondervertrag' },
  { value: 'dynamisch', label: 'Dynamischer Tarif' },
  { value: 'oeko', label: 'Ökostrom' },
]

// V7-Plausibilität: dieselben Schwellen wie der Daten-Checker
// (backend/services/daten_checker/stammdaten.py:_check_strompreise) — SoT dort;
// hier nur als weicher Hinweis gespiegelt, NICHT als Blockier-Logik.
const NETZBEZUG_MIN = 5
const NETZBEZUG_MAX = 80
const EINSPEISUNG_MAX = 30

type PflichtFeld = 'netzbezug_arbeitspreis_cent_kwh' | 'einspeiseverguetung_cent_kwh' | 'gueltig_ab'

/** Wochentage in der Reihenfolge, in der man sie liest — Montag zuerst. */
const WOCHENTAGE: ReadonlyArray<readonly [string, string]> = [
  ['0', 'Mo'], ['1', 'Di'], ['2', 'Mi'], ['3', 'Do'],
  ['4', 'Fr'], ['5', 'Sa'], ['6', 'So'],
] as const

const ALLE_TAGE = '0123456'

/** Ein Fenster in Worten — dieselbe Aussage wie die Felder, nur lesbar. */
function fensterText(f: StrompreisZeitfenster, hochtarifCent: number): string {
  const tage = f.wochentage === ALLE_TAGE
    ? 'täglich'
    : WOCHENTAGE.filter(([k]) => f.wochentage.includes(k)).map(([, l]) => l).join(', ')
  const spanne = `${f.von_stunde}–${f.bis_stunde} Uhr`
  const ueberMitternacht = f.von_stunde > f.bis_stunde ? ' (über Mitternacht)' : ''
  const vergleich = hochtarifCent > 0 && f.arbeitspreis_cent_kwh < hochtarifCent
    ? ` statt ${fmtZahl(hochtarifCent, 2)}`
    : ''
  return `${tage} ${spanne}${ueberMitternacht}: ${fmtZahl(f.arbeitspreis_cent_kwh, 2)} ct/kWh${vergleich}`
}

/** Der Fenster-Editor (N-267, MeinerB in Discussion #380).
 *
 * ⚠ **Die Felder sind Uhrzeiten, keine Slot-Indizes.** Die Umrechnung auf die
 * Backward-Slots des Energieprofils (#144) macht ausschließlich das Backend
 * (`core/berechnungen/zeittarif.py`); der Client rechnet hier nichts — er
 * sammelt Eingaben. Das ist nicht Kosmetik: Bernds Fenster 19–20 Uhr ist dort
 * Slot 20, und wer das im Client nachbaut, baut die zweite Wahrheit.
 */
function ZeitfensterFelder({ fenster, onChange, hochtarifCent }: {
  fenster: StrompreisZeitfenster[]
  onChange: (f: StrompreisZeitfenster[]) => void
  hochtarifCent: number
}) {
  const setzeFeld = (idx: number, teil: Partial<StrompreisZeitfenster>) =>
    onChange(fenster.map((f, i) => (i === idx ? { ...f, ...teil } : f)))

  const tagUmschalten = (idx: number, tag: string) => {
    const aktuell = fenster[idx].wochentage
    const neu = aktuell.includes(tag)
      ? aktuell.split('').filter(t => t !== tag).join('')
      : [...aktuell.split(''), tag].sort().join('')
    // Die „mindestens eine"-Regel haelt der SoT (`SegmentMehrfach`); diese
    // Zeile ist der Gurt dazu, falls der Umschalter je woanders sitzt.
    if (neu.length > 0) setzeFeld(idx, { wochentage: neu })
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Zahlst du zu bestimmten Uhrzeiten einen anderen Arbeitspreis? Dann trag das Fenster
        hier ein. Ohne Eintrag gilt der Preis oben rund um die Uhr.
      </p>

      {fenster.map((f, idx) => (
        <div
          key={idx}
          className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-3"
        >
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Input
              label="Von (Uhr)" name={`zeitfenster-${idx}-von`}
              type="number" min="0" max="23" step="1"
              value={String(f.von_stunde)}
              onChange={(e) => setzeFeld(idx, { von_stunde: Number(e.target.value) })}
            />
            <Input
              label="Bis (Uhr)" name={`zeitfenster-${idx}-bis`}
              type="number" min="1" max="24" step="1"
              value={String(f.bis_stunde)}
              onChange={(e) => setzeFeld(idx, { bis_stunde: Number(e.target.value) })}
              hint="24 = Mitternacht"
            />
            <Input
              label="Arbeitspreis" name={`zeitfenster-${idx}-preis`}
              type="number" min="0" step="0.01"
              value={String(f.arbeitspreis_cent_kwh)}
              onChange={(e) => setzeFeld(idx, { arbeitspreis_cent_kwh: Number(e.target.value) })}
              hint="ct/kWh in diesem Fenster"
            />
          </div>

          <div>
            <span className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              An diesen Tagen
            </span>
            {/* Regel 0a Fall 2: der erste Entwurf baute die Pillen hier von
                Hand — `check:roh-controls` hat es gemeldet, und zu Recht. Die
                Mehrfach-Variante wohnt jetzt als SoT neben `SegmentControl`. */}
            <SegmentMehrfach
              ariaLabel="Wochentage des Zeitfensters"
              optionen={WOCHENTAGE.map(([key, label]) => ({ key, label }))}
              werte={f.wochentage.split('')}
              onToggle={(tag) => tagUmschalten(idx, tag)}
              size="sm"
            />
          </div>

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {fensterText(f, hochtarifCent)}
            </p>
            <Button
              type="button" variant="ghost" size="sm"
              onClick={() => onChange(fenster.filter((_, i) => i !== idx))}
            >
              Entfernen
            </Button>
          </div>
        </div>
      ))}

      <Button
        type="button" variant="secondary" size="sm"
        onClick={() => onChange([
          ...fenster,
          // Vorbelegung ist der gemeldete Fall: täglich, ein Abendfenster.
          { von_stunde: 19, bis_stunde: 20, wochentage: ALLE_TAGE, arbeitspreis_cent_kwh: 0 },
        ])}
      >
        <Plus className="w-4 h-4" />
        {fenster.length === 0 ? 'Zeitfenster hinzufügen' : 'Weiteres Fenster'}
      </Button>

      {fenster.length > 0 && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Der gewichtete Monatspreis entsteht aus deinen <strong>gemessenen</strong> Stundenwerten.
          Trägst du Monatswerte von Hand ein, gibt es die Stundenaufteilung nicht — dann rechnet
          eedc mit dem Preis oben. Deinen tatsächlichen Ø-Preis kannst du im Monatsabschluss
          unter „Ø Strompreis" eintragen; er schlägt beides.
        </p>
      )}
    </div>
  )
}


export function StrompreisForm({
  strompreis, anlageId, onCreate, onUpdate, onCancel, error, gueltigAbVorbelegung,
}: StrompreisFormProps) {
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    tarifname: strompreis?.tarifname || '',
    anbieter: strompreis?.anbieter || '',
    netzbezug_arbeitspreis_cent_kwh: strompreis?.netzbezug_arbeitspreis_cent_kwh?.toString() || '30',
    // Vorbelegung 0 statt eines geschätzten EEG-Satzes: den geltenden Satz
    // kennt nur der Betreiber, und eine Zahl im Feld sähe gepflegt aus
    // (Entscheid 08.08.2026, T89667 #122). `plausibelWarnung` sagt daneben,
    // was 0 bedeutet.
    einspeiseverguetung_cent_kwh: strompreis?.einspeiseverguetung_cent_kwh?.toString() || '0',
    grundpreis_euro_monat: strompreis?.grundpreis_euro_monat?.toString() || '',
    zaehlergebuehr_euro_jahr: strompreis?.zaehlergebuehr_euro_jahr?.toString() || '',
    gueltig_ab: strompreis?.gueltig_ab || gueltigAbVorbelegung || new Date().toISOString().split('T')[0],
    gueltig_bis: strompreis?.gueltig_bis || '',
    vertragsart: strompreis?.vertragsart || '',
    verwendung: (strompreis?.verwendung || 'allgemein') as StrompreisVerwendung,
    // #392: „Einspeisevergütung wechselt monatlich" (z. B. OeMAG-Marktpreis)
    einspeisung_variabel: strompreis?.einspeisung_variabel || false,
  })

  // N-267: Zeitfenster als eigener Zustand — sie sind eine Liste, kein Feld.
  const [fenster, setFenster] = useState<StrompreisZeitfenster[]>(
    () => strompreis?.zeitfenster?.map(f => ({ ...f })) ?? [],
  )

  // V1/V2: Inline-Fehler erst nach Berührung (touched) bzw. nach Absende-Versuch.
  const [touched, setTouched] = useState<Set<string>>(new Set())
  const [submitted, setSubmitted] = useState(false)
  const feldRefs = useRef<Record<PflichtFeld, HTMLDivElement | null>>({
    netzbezug_arbeitspreis_cent_kwh: null,
    einspeiseverguetung_cent_kwh: null,
    gueltig_ab: null,
  })

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const markTouched = (name: string) => setTouched(prev => new Set(prev).add(name))

  // Harte Validierung (blockiert Absenden).
  const feldFehler = (name: PflichtFeld): string | undefined => {
    if (name === 'gueltig_ab') {
      return formData.gueltig_ab ? undefined : 'Bitte ein Gültig-ab-Datum wählen'
    }
    const roh = formData[name]
    if (roh === '') return 'Pflichtfeld'
    const n = parseFloat(roh)
    if (Number.isNaN(n)) return 'Bitte eine Zahl eingeben'
    if (n < 0) return 'Darf nicht negativ sein'
    return undefined
  }

  const zeigeFehler = (name: PflichtFeld): string | undefined =>
    (submitted || touched.has(name)) ? feldFehler(name) : undefined

  // V7 weiche Plausibilität (blockiert NICHT) — Schwellen s. o.
  const plausibelWarnung = (name: 'netzbezug_arbeitspreis_cent_kwh' | 'einspeiseverguetung_cent_kwh'): string | undefined => {
    if (feldFehler(name)) return undefined
    const n = parseFloat(formData[name])
    if (Number.isNaN(n)) return undefined
    if (name === 'netzbezug_arbeitspreis_cent_kwh' && (n < NETZBEZUG_MIN || n > NETZBEZUG_MAX)) {
      return `Ungewöhnlich – erwartet ${NETZBEZUG_MIN}–${NETZBEZUG_MAX} ct/kWh`
    }
    if (name === 'einspeiseverguetung_cent_kwh' && n > EINSPEISUNG_MAX) {
      return `Ungewöhnlich – erwartet 0–${EINSPEISUNG_MAX} ct/kWh`
    }
    // 0 ist die Vorbelegung eines neuen Tarifs und damit der Normalfall eines
    // noch nicht gepflegten Feldes — sie darf nicht still bleiben: mit 0 ct
    // ist der Einspeise-Erlös des Zeitraums 0 €, und das fällt in den
    // Auswertungen erst Monate später auf. Weich, weil 0 legitim sein kann
    // (Volleinspeisung ohne Vergütung, ausgelaufene EEG-Förderung).
    if (name === 'einspeiseverguetung_cent_kwh' && n === 0) {
      return 'Mit 0 ct wird für diesen Zeitraum kein Einspeise-Erlös berechnet'
    }
    return undefined
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitted(true)

    // V2: alle Pflichtfelder prüfen, bei Fehler blockieren + zum ersten scrollen.
    const pflicht: PflichtFeld[] = ['netzbezug_arbeitspreis_cent_kwh', 'einspeiseverguetung_cent_kwh', 'gueltig_ab']
    const ersterFehler = pflicht.find(feldFehler)
    if (ersterFehler) {
      feldRefs.current[ersterFehler]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }

    setLoading(true)
    try {
      const baseData = {
        netzbezug_arbeitspreis_cent_kwh: parseFloat(formData.netzbezug_arbeitspreis_cent_kwh),
        einspeiseverguetung_cent_kwh: parseFloat(formData.einspeiseverguetung_cent_kwh),
        grundpreis_euro_monat: formData.grundpreis_euro_monat ? parseFloat(formData.grundpreis_euro_monat) : undefined,
        zaehlergebuehr_euro_jahr: formData.zaehlergebuehr_euro_jahr ? parseFloat(formData.zaehlergebuehr_euro_jahr) : undefined,
        gueltig_ab: formData.gueltig_ab,
        gueltig_bis: formData.gueltig_bis || undefined,
        tarifname: formData.tarifname || undefined,
        anbieter: formData.anbieter || undefined,
        vertragsart: formData.vertragsart || undefined,
        verwendung: formData.verwendung,
        einspeisung_variabel: formData.einspeisung_variabel,
        // N-267: die Fenster werden als GANZE Liste geschickt — `[]` entfernt sie.
        zeitfenster: fenster.map(({ von_stunde, bis_stunde, wochentage, arbeitspreis_cent_kwh }) => ({
          von_stunde, bis_stunde, wochentage, arbeitspreis_cent_kwh,
        })),
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
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      {/* V4: Async/Server-Fehler ohne Feld-Zuordnung als Formular-Alert. */}
      {error && <Alert type="error">{error}</Alert>}

      <FormSection title="Verwendung">
        <RadioGroup
          name="verwendung"
          options={VERWENDUNG_OPTIONEN}
          value={formData.verwendung}
          onChange={(v) => setFormData(prev => ({ ...prev, verwendung: v }))}
        />
      </FormSection>

      <FormSection title="Preise">
        {/* D17-7 / D14-6 (detLAN #113): labelClassName reserviert eine
            Zwei-Zeilen-Höhe → das umbrechende „Einspeisevergütung"-Label
            verschiebt die Felder nicht mehr; items-start hält die Felder oben
            bündig, unabhängig von Hinweis/V7/Fehler-Höhe darunter. */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-start">
          <div ref={(el) => { feldRefs.current.netzbezug_arbeitspreis_cent_kwh = el }}>
            <Input
              label="Netzbezug (ct/kWh)"
              labelClassName="md:min-h-[2.5rem]"
              name="netzbezug_arbeitspreis_cent_kwh"
              type="number"
              step="0.01"
              min="0"
              value={formData.netzbezug_arbeitspreis_cent_kwh}
              onChange={handleChange}
              onBlur={() => markTouched('netzbezug_arbeitspreis_cent_kwh')}
              required
              error={zeigeFehler('netzbezug_arbeitspreis_cent_kwh')}
              hint={(zeigeFehler('netzbezug_arbeitspreis_cent_kwh') || plausibelWarnung('netzbezug_arbeitspreis_cent_kwh'))
                ? undefined
                // Bei dynamischem Tarif ist der feste Preis kein „der Preis",
                // sondern der Referenzwert (Rainer-PN 2026-07-25). Er bleibt
                // Pflicht: der mitgeschriebene Stundenpreis fehlt für Monate ohne
                // Aufzeichnung und für ROI-/Investitionsrechnungen komplett.
                : formData.vertragsart === 'dynamisch'
                  ? 'Referenzpreis — der mitgeschriebene Stundenpreis geht vor'
                  : 'Arbeitspreis für Strombezug'}
            />
            {!zeigeFehler('netzbezug_arbeitspreis_cent_kwh') && plausibelWarnung('netzbezug_arbeitspreis_cent_kwh') && (
              <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">{plausibelWarnung('netzbezug_arbeitspreis_cent_kwh')}</p>
            )}
          </div>
          <div ref={(el) => { feldRefs.current.einspeiseverguetung_cent_kwh = el }}>
            <Input
              label="Einspeisevergütung (ct/kWh)"
              labelClassName="md:min-h-[2.5rem]"
              name="einspeiseverguetung_cent_kwh"
              type="number"
              step="0.01"
              min="0"
              value={formData.einspeiseverguetung_cent_kwh}
              onChange={handleChange}
              onBlur={() => markTouched('einspeiseverguetung_cent_kwh')}
              required
              error={zeigeFehler('einspeiseverguetung_cent_kwh')}
              // Anders als beim Netzbezug bleibt der Hinweis auch neben einer
              // Plausibilitäts-Warnung stehen: die häufigste Warnung ist „0 ct"
              // — also genau der Moment, in dem der Eingebende erfahren muss,
              // dass eedc flat rechnet und ein Mischsatz zulässig ist. Bei
              // einem echten Feld-Fehler unterdrückt `Input` den Hinweis selbst.
              hint={`EEG-Vergütung oder PPA-Preis. ${EINSPEISEVERGUETUNG_FLAT_HINWEIS}`}
            />
            {!zeigeFehler('einspeiseverguetung_cent_kwh') && plausibelWarnung('einspeiseverguetung_cent_kwh') && (
              <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">{plausibelWarnung('einspeiseverguetung_cent_kwh')}</p>
            )}
          </div>
          <Input
            label="Grundpreis (€/Monat)"
            labelClassName="md:min-h-[2.5rem]"
            name="grundpreis_euro_monat"
            type="number"
            step="0.01"
            min="0"
            value={formData.grundpreis_euro_monat}
            onChange={handleChange}
            hint="Optional"
          />
          {/* G19-1 K3 (R19-3): jährliche Zähler-/Messstellengebühr — erscheint
              als nachrichtliche Zeile in der Jahresaufstellung (Cockpit/Jahr),
              wird NICHT in Kosten/Netto-Ertrag verrechnet. */}
          <Input
            label="Zählergebühr (€/Jahr)"
            labelClassName="md:min-h-[2.5rem]"
            name="zaehlergebuehr_euro_jahr"
            type="number"
            step="0.01"
            min="0"
            value={formData.zaehlergebuehr_euro_jahr}
            onChange={handleChange}
            hint="Optional — Ausweis in der Jahresaufstellung"
          />
        </div>
        {/* #392 (gruaGit, OeMAG): die EIGENSCHAFT „wechselt monatlich" statt
            eines Vertragsmodells „Direktvermarktung" — Begründung im Auftrag.
            Nur beim allgemeinen Tarif: Spezialtarife (WP/Wallbox) tragen keine
            Einspeisevergütung. */}
        {formData.verwendung === 'allgemein' && (
          <SchalterZeile
            checked={formData.einspeisung_variabel}
            onChange={(an) => setFormData(prev => ({ ...prev, einspeisung_variabel: an }))}
            label="Einspeisevergütung wechselt monatlich"
            hint={'Z. B. OeMAG-Marktpreis: der Monatsabschluss bietet dann das Feld „Einspeisevergütung (Monat)“ an. Der gepflegte Monatssatz schlägt den Stammwert oben; Monate ohne Eintrag rechnen mit dem Stammwert.'}
          />
        )}
      </FormSection>

      {/* N-267 (MeinerB, Discussion #380): HT/NT-Zeitfenster.
          Die Fläche startet leer und schmal — ein Fenster genügt für den
          gemeldeten Fall („täglich 19–20 Uhr"). Das MODELL trägt mehr
          (Wochentage, mehrere Fenster, über Mitternacht), die ANSICHT bietet
          es an, sobald ein Fenster da ist. */}
      <FormSection title="Zeitfenster (HT/NT)">
        <ZeitfensterFelder
          fenster={fenster}
          onChange={setFenster}
          hochtarifCent={parseFloat(formData.netzbezug_arbeitspreis_cent_kwh) || 0}
        />
      </FormSection>

      <FormSection title="Gültigkeit">
        <div ref={(el) => { feldRefs.current.gueltig_ab = el }}>
          <DatumFeld
            label="Gültig ab"
            value={formData.gueltig_ab}
            onChange={(v) => { setFormData(prev => ({ ...prev, gueltig_ab: v })); markTouched('gueltig_ab') }}
            required
            hint="Gilt ab dem 1. des Monats — Monate davor rechnen mit der Vorbelegung (30 ct). Reicht deine Historie weiter zurück, hier den Beginn deiner Daten eintragen."
          />
          {zeigeFehler('gueltig_ab') && (
            <p className="mt-1 text-xs text-red-500">{zeigeFehler('gueltig_ab')}</p>
          )}
        </div>
      </FormSection>

      <FormSection variant="erweitert" title="Erweitert (optional)">
        <div className="space-y-4">
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
          <DatumFeld
            label="Gültig bis"
            value={formData.gueltig_bis}
            onChange={(v) => setFormData(prev => ({ ...prev, gueltig_bis: v }))}
            hint="Leer lassen für unbefristet"
          />
          <Select
            label="Vertragsart"
            name="vertragsart"
            value={formData.vertragsart}
            onChange={(e) => setFormData(prev => ({ ...prev, vertragsart: e.target.value }))}
            placeholder="Bitte wählen"
            options={VERTRAGSART_OPTIONEN}
          />
        </div>
      </FormSection>

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
