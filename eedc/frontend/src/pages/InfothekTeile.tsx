/**
 * Infothek — geteilte Teile (Liste + Kategorie-Filter + Anlegen/Bearbeiten/
 * Löschen-Modals + N:M-Investitions-Verknüpfung + Datei-Upload).
 *
 * EINE Code-Wahrheit für IST (`pages/Infothek.tsx`, dünner Komposer) und IA-V4
 * (Einstellungen-Katalog-Block „Infothek", inline wie Strompreise/Monatsdaten —
 * volle native V4-Sicht, Gernot 2026-07-01). Der Aufrufer reicht die bereits
 * aufgelöste `anlageId` und – im Mehr-Anlagen-Fall – einen `kopfZusatz`
 * (Anlage-Auswahl). Zahlen de-DE über `fmtZahl`. Investition≠Infothek strikt
 * getrennt (nur `infothekApi`; N:M-Verknüpfung läuft über `InfothekForm`).
 *
 * Wächter-Ausnahme: die Datei-Thumbnail-Kachel (56×56-Bildvorschau als Klick-
 * fläche zur Lightbox) ist ein roher <button> (Kachel-Optik, kein ui/Button-Fall) —
 * check:v4-migration-Fall-3-Allowlist (Regel 0a Fall 3, Gernot-Freigabe 2026-07-11).
 */
import { useState, useEffect, useCallback, useMemo, type ReactNode } from 'react'
import { Plus, Pencil, Trash2, Archive, BookOpen, FileText, User, Phone, Mail, Download } from 'lucide-react'
import Markdown from 'react-markdown'
import { Button, buttonClasses, Modal, Card, Alert, LoadingSpinner, EmptyState, ConfirmDialog } from '../components/ui'
import InfothekForm from '../components/forms/InfothekForm'
import DateiLightbox from '../components/infothek/DateiLightbox'
import { infothekApi } from '../api/infothek'
import { getKategorieConfig, KATEGORIE_KEYS } from '../config/infothekKategorien'
import { fmtZahl } from '../lib'
import type { InfothekEintrag, InfothekEintragCreate, InfothekEintragUpdate, InfothekDatei } from '../types/infothek'

// ─── Verwaltung (Liste + Filter + Modals + N:M + Dateien) ──────────────────────

/**
 * Volle Infothek. Wird von der IST-Seite (V3-Hülle) und dem V4-Infothek-Block
 * geteilt. `anlageId` ist bereits aufgelöst; `kopfZusatz` (z. B. Anlage-Auswahl)
 * wandert links in die Kopfleiste.
 */
export function InfothekVerwaltung({ anlageId, kopfZusatz }: { anlageId: number; kopfZusatz?: ReactNode }) {
  const [eintraege, setEintraege] = useState<InfothekEintrag[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editingEintrag, setEditingEintrag] = useState<InfothekEintrag | null>(null)
  const [initialKategorie, setInitialKategorie] = useState<string | undefined>()
  const [deleteConfirm, setDeleteConfirm] = useState<InfothekEintrag | null>(null)
  const [archiveConfirm, setArchiveConfirm] = useState<InfothekEintrag | null>(null)
  const [filterKategorie, setFilterKategorie] = useState<string | null>(null)
  const [showArchived, setShowArchived] = useState(false)

  const loadEintraege = useCallback(async () => {
    setLoading(true)
    try {
      const data = await infothekApi.list(anlageId)
      setEintraege(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Laden')
    } finally {
      setLoading(false)
    }
  }, [anlageId])

  useEffect(() => {
    loadEintraege()
  }, [loadEintraege])

  // Vertragspartner und Einträge trennen
  const vertragspartner = useMemo(
    () => eintraege.filter(e => e.kategorie === 'ansprechpartner'),
    [eintraege]
  )
  const normalEintraege = useMemo(
    () => eintraege.filter(e => e.kategorie !== 'ansprechpartner'),
    [eintraege]
  )

  // Gefilterte Einträge (ohne Ansprechpartner)
  const filteredEintraege = useMemo(() => {
    let result = normalEintraege
    if (filterKategorie) {
      result = result.filter(e => e.kategorie === filterKategorie)
    }
    if (!showArchived) {
      result = result.filter(e => e.aktiv)
    }
    return result
  }, [normalEintraege, filterKategorie, showArchived])

  // Zähle Einträge pro Kategorie (ohne Ansprechpartner)
  const kategorieCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    const aktive = showArchived ? normalEintraege : normalEintraege.filter(e => e.aktiv)
    aktive.forEach(e => {
      counts[e.kategorie] = (counts[e.kategorie] || 0) + 1
    })
    return counts
  }, [normalEintraege, showArchived])

  const archivedCount = useMemo(() => normalEintraege.filter(e => !e.aktiv).length, [normalEintraege])
  const vorhandeneKategorien = useMemo(
    () => KATEGORIE_KEYS.filter(k => k !== 'ansprechpartner' && kategorieCounts[k]),
    [kategorieCounts]
  )

  const handleCreate = (kategorie?: string) => {
    setEditingEintrag(null)
    setInitialKategorie(kategorie)
    setShowForm(true)
  }

  const handleEdit = (eintrag: InfothekEintrag) => {
    setEditingEintrag(eintrag)
    setInitialKategorie(undefined)
    setShowForm(true)
  }

  const handleSubmit = async (data: InfothekEintragCreate | InfothekEintragUpdate) => {
    if (editingEintrag) {
      await infothekApi.update(editingEintrag.id, data as InfothekEintragUpdate)
    } else {
      await infothekApi.create(data as InfothekEintragCreate)
    }
    setShowForm(false)
    setEditingEintrag(null)
    await loadEintraege()
  }

  const handleDelete = async () => {
    if (!deleteConfirm) return
    // Fehler propagieren → der ConfirmDialog zeigt ihn im Dialog (bleibt offen).
    await infothekApi.delete(deleteConfirm.id)
    setDeleteConfirm(null)
    await loadEintraege()
  }

  const doToggleAktiv = async (eintrag: InfothekEintrag) => {
    await infothekApi.update(eintrag.id, { aktiv: !eintrag.aktiv })
    await loadEintraege()
  }

  // Archivieren (aktiv→false) fragt nach (R17-4 #344: „Bearbeiten" liegt daneben →
  // Fehlklick); Wiederherstellen (→aktiv) ist harmlos und läuft sofort.
  const handleToggleAktiv = (eintrag: InfothekEintrag) => {
    if (eintrag.aktiv) {
      setArchiveConfirm(eintrag)
    } else {
      doToggleAktiv(eintrag).catch(err =>
        setError(err instanceof Error ? err.message : 'Fehler beim Wiederherstellen'),
      )
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">{kopfZusatz}</div>
        {/* D14-15: wrap statt Quetschen — jeder Button bleibt einzeilig 36 px. */}
        <div className="flex flex-wrap items-center gap-3">
          {eintraege.length > 0 && (
            // D14-15 (detLAN #116): Button-SoT-Höhe (36 px) wie die Nachbarn;
            // PDF behält als Export-Aktion Icon + Wort (Kontext-Regel).
            <a
              href={`./api/infothek/export/pdf?anlage_id=${anlageId}${filterKategorie ? `&kategorie=${filterKategorie}` : ''}`}
              className={buttonClasses({ variant: 'secondary', className: 'gap-2 no-underline' })}
              title="Als PDF exportieren"
            >
              <Download className="h-4 w-4" />
              PDF
            </a>
          )}
          <Button variant="secondary" onClick={() => handleCreate('ansprechpartner')}>
            <User className="max-sm:hidden h-4 w-4 mr-2" />
            Neuer Vertragspartner
          </Button>
          <Button onClick={() => handleCreate()}>
            <Plus className="max-sm:hidden h-4 w-4 mr-2" />
            Neuer Eintrag
          </Button>
        </div>
      </div>

      {error && (
        <Alert type="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <div className="flex justify-center py-8">
          <LoadingSpinner text="Lade Infothek..." />
        </div>
      ) : (
        <>
          {/* Kategorie-Filter + Archiv-Toggle. Der Archiv-Toggle hängt NICHT an der
              Kategorie-Zahl (R17-4 #344: sonst verschwindet er bei nur 1 Kategorie →
              archivierte Einträge unauffindbar). */}
          {(vorhandeneKategorien.length > 1 || archivedCount > 0) && (
            <div className="flex flex-wrap gap-2">
              {vorhandeneKategorien.length > 1 && (
                <>
                  <Button
                    type="button"
                    size="sm"
                    variant={!filterKategorie ? 'primary' : 'secondary'}
                    aria-pressed={!filterKategorie}
                    onClick={() => setFilterKategorie(null)}
                  >
                    Alle ({showArchived ? eintraege.length : eintraege.filter(e => e.aktiv).length})
                  </Button>
                  {vorhandeneKategorien.map(key => {
                    const config = getKategorieConfig(key)
                    const Icon = config.icon
                    return (
                      <Button
                        key={key}
                        type="button"
                        size="sm"
                        variant={filterKategorie === key ? 'primary' : 'secondary'}
                        aria-pressed={filterKategorie === key}
                        onClick={() => setFilterKategorie(filterKategorie === key ? null : key)}
                      >
                        <Icon className="h-3.5 w-3.5 mr-1.5" />
                        {config.label} ({kategorieCounts[key]})
                      </Button>
                    )
                  })}
                </>
              )}
              {archivedCount > 0 && (
                <Button
                  type="button"
                  size="sm"
                  variant={showArchived ? 'primary' : 'secondary'}
                  aria-pressed={showArchived}
                  onClick={() => setShowArchived(!showArchived)}
                >
                  <Archive className="h-3.5 w-3.5 mr-1" />
                  {showArchived ? `Archiv ausblenden (${archivedCount})` : `Archivierte anzeigen (${archivedCount})`}
                </Button>
              )}
            </div>
          )}

          {/* Vertragspartner-Sektion */}
          {vertragspartner.length > 0 && (
            <div>
              <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
                Vertragspartner
              </h2>
              <div className="flex flex-wrap gap-2">
                {vertragspartner.map(vp => {
                  const p = (vp.parameter ?? {}) as Record<string, unknown>
                  return (
                    <div
                      key={vp.id}
                      className="group flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700"
                    >
                      <User className="h-4 w-4 text-gray-400 dark:text-gray-500 shrink-0" />
                      <span className="font-medium text-sm text-gray-900 dark:text-white">
                        {vp.bezeichnung}
                      </span>
                      {p.telefon ? (
                        <a href={`tel:${String(p.telefon)}`} className="text-gray-400 dark:text-gray-500 hover:text-primary-600" title={String(p.telefon)}>
                          <Phone className="h-3.5 w-3.5" />
                        </a>
                      ) : null}
                      {p.email ? (
                        <a href={`mailto:${String(p.email)}`} className="text-gray-400 dark:text-gray-500 hover:text-primary-600" title={String(p.email)}>
                          <Mail className="h-3.5 w-3.5" />
                        </a>
                      ) : null}
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={() => handleEdit(vp)}
                        aria-label="Vertragspartner bearbeiten"
                        title="Bearbeiten"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={() => setDeleteConfirm(vp)}
                        aria-label="Vertragspartner löschen"
                        title="Löschen"
                      >
                        <Trash2 className="h-3.5 w-3.5 text-red-500" />
                      </Button>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Einträge */}
          {filteredEintraege.length === 0 ? (
            <EmptyState
              icon={BookOpen}
              title="Keine Einträge vorhanden"
              description="Verwalte Verträge, Zähler, Kontakte und Dokumentation zu deiner PV-Anlage."
              action={
                <Button onClick={() => handleCreate()}>
                  <Plus className="max-sm:hidden h-4 w-4 mr-2" />
                  Ersten Eintrag anlegen
                </Button>
              }
            />
          ) : (
            <div className="space-y-3">
              {filteredEintraege.map(eintrag => (
                <InfothekKarte
                  key={eintrag.id}
                  eintrag={eintrag}
                  alleEintraege={eintraege}
                  onEdit={() => handleEdit(eintrag)}
                  onDelete={() => setDeleteConfirm(eintrag)}
                  onToggleAktiv={() => handleToggleAktiv(eintrag)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Formular Modal */}
      <Modal
        isOpen={showForm}
        onClose={() => {
          setShowForm(false)
          setEditingEintrag(null)
        }}
        title={
          editingEintrag
            ? (editingEintrag.kategorie === 'ansprechpartner' ? 'Vertragspartner bearbeiten' : 'Eintrag bearbeiten')
            : (initialKategorie === 'ansprechpartner' ? 'Neuer Vertragspartner' : 'Neuer Eintrag')
        }
        size="lg"
      >
        <InfothekForm
          eintrag={editingEintrag}
          anlageId={anlageId}
          initialKategorie={initialKategorie}
          onSubmit={handleSubmit}
          onCancel={() => {
            setShowForm(false)
            setEditingEintrag(null)
          }}
        />
      </Modal>

      {/* Archivieren bestätigen (R17-4 #344) — reversibel, daher leichter Dialog */}
      <ConfirmDialog
        isOpen={!!archiveConfirm}
        onClose={() => setArchiveConfirm(null)}
        onConfirm={async () => {
          if (archiveConfirm) await doToggleAktiv(archiveConfirm)
          setArchiveConfirm(null)
        }}
        title="Eintrag archivieren"
        confirmLabel="Archivieren"
        message={
          <>Möchtest du „{archiveConfirm?.bezeichnung}" archivieren? Du kannst ihn jederzeit
          über „Archivierte anzeigen" wiederherstellen.</>
        }
      />

      {/* Löschen bestätigen */}
      <ConfirmDialog
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDelete}
        title="Eintrag löschen"
        confirmLabel="Endgültig löschen"
        variant="danger"
        message={
          <>Möchtest du „{deleteConfirm?.bezeichnung}" wirklich endgültig löschen?
          Alternativ kannst du den Eintrag archivieren.</>
        }
      />
    </div>
  )
}


/** Einzelne Infothek-Karte mit Datei-Vorschau */
function InfothekKarte({
  eintrag,
  alleEintraege,
  onEdit,
  onDelete,
  onToggleAktiv,
}: {
  eintrag: InfothekEintrag
  alleEintraege: InfothekEintrag[]
  onEdit: () => void
  onDelete: () => void
  onToggleAktiv: () => void
}) {
  const [dateien, setDateien] = useState<InfothekDatei[]>([])
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const config = getKategorieConfig(eintrag.kategorie)
  const Icon = config.icon
  const params = (eintrag.parameter ?? {}) as Record<string, unknown>

  // Dateien laden
  useEffect(() => {
    infothekApi.listDateien(eintrag.id).then(setDateien).catch(() => {})
  }, [eintrag.id])

  const bilderDateien = dateien.filter(d => d.dateityp === 'image')

  // Verknüpfter Ansprechpartner
  const ansprechpartner = eintrag.ansprechpartner_id
    ? alleEintraege.find(e => e.id === eintrag.ansprechpartner_id)
    : null

  // Zeige die wichtigsten Parameter als Details
  const highlights: string[] = []
  if (ansprechpartner) highlights.push(`↗ ${ansprechpartner.bezeichnung}`)
  if (params.zaehler_nummer) highlights.push(`Zähler: ${params.zaehler_nummer}`)
  if (params.anbieter) highlights.push(String(params.anbieter))
  if (params.firma) highlights.push(String(params.firma))
  if (params.name) highlights.push(String(params.name))
  if (params.mastr_nummer) highlights.push(`MaStR: ${params.mastr_nummer}`)
  if (params.versicherungsnummer) highlights.push(`Nr. ${params.versicherungsnummer}`)
  if (params.hersteller) highlights.push(String(params.hersteller))
  if (params.foerderprogramm) highlights.push(String(params.foerderprogramm))
  if (params.lieferant) highlights.push(String(params.lieferant))
  if (params.kundennummer) highlights.push(`Kd-Nr. ${params.kundennummer}`)
  // Beträge
  if (params.tarif_ct_kwh) highlights.push(`${params.tarif_ct_kwh} ct/kWh`)
  if (params.verguetung_ct_kwh) highlights.push(`${params.verguetung_ct_kwh} ct/kWh`)
  if (params.jahresbeitrag_euro) highlights.push(`${params.jahresbeitrag_euro} €/Jahr`)
  if (params.jahreskosten_euro) highlights.push(`${params.jahreskosten_euro} €/Jahr`)
  if (params.betrag_euro) highlights.push(`${fmtZahl(Number(params.betrag_euro), 0)} €`)

  const handleDateiClick = (datei: InfothekDatei) => {
    if (datei.dateityp === 'pdf') {
      window.open(infothekApi.dateiUrl(eintrag.id, datei.id), '_blank')
    } else {
      const idx = bilderDateien.findIndex(d => d.id === datei.id)
      setLightboxIndex(idx >= 0 ? idx : 0)
    }
  }

  return (
    <>
      <Card className={!eintrag.aktiv ? 'opacity-50' : undefined}>
        <div className="flex items-start gap-4">
          {/* Icon */}
          <div className={`p-2.5 rounded-lg shrink-0 ${config.bgColor}`}>
            <Icon className={`h-5 w-5 ${config.color}`} />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="font-medium text-gray-900 dark:text-white truncate">
                {eintrag.bezeichnung}
              </h3>
              {!eintrag.aktiv && (
                <span className="text-xs px-2 py-0.5 bg-gray-200 dark:bg-gray-700 rounded text-gray-600 dark:text-gray-400">
                  Archiviert
                </span>
              )}
            </div>

            {highlights.length > 0 && (
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                {highlights.slice(0, 4).join(' · ')}
              </p>
            )}

            {eintrag.notizen && (
              <div className="text-sm text-gray-500 dark:text-gray-400 mt-1.5 line-clamp-3 prose prose-sm dark:prose-invert max-w-none prose-p:my-0.5 prose-ul:my-0.5">
                <Markdown>{eintrag.notizen}</Markdown>
              </div>
            )}

            {/* Datei-Vorschau */}
            {dateien.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {dateien.map(datei => (
                  <button
                    key={datei.id}
                    onClick={() => handleDateiClick(datei)}
                    className="w-14 h-14 rounded border border-gray-200 dark:border-gray-700 overflow-hidden bg-gray-50 dark:bg-gray-800 hover:ring-2 hover:ring-primary-400 transition-all"
                    title={datei.dateiname}
                  >
                    {datei.dateityp === 'image' ? (
                      <img
                        src={infothekApi.thumbnailUrl(eintrag.id, datei.id)}
                        alt={datei.dateiname}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center">
                        <FileText className="h-6 w-6 text-red-500" />
                      </div>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Actions — Reihenfolge Bearbeiten · Archivieren · Löschen (#344):
              destruktive Aktion ganz rechts, weg vom Bearbeiten. */}
          <div className="flex items-center gap-1 shrink-0">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onEdit}
              aria-label="Eintrag bearbeiten"
              title="Bearbeiten"
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onToggleAktiv}
              aria-label={eintrag.aktiv ? 'Eintrag archivieren' : 'Eintrag wiederherstellen'}
              title={eintrag.aktiv ? 'Archivieren' : 'Wiederherstellen'}
            >
              <Archive className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onDelete}
              aria-label="Eintrag löschen"
              title="Löschen"
            >
              <Trash2 className="h-4 w-4 text-red-500" />
            </Button>
          </div>
        </div>
      </Card>

      {/* Lightbox */}
      {lightboxIndex !== null && bilderDateien.length > 0 && (
        <DateiLightbox
          dateien={bilderDateien}
          eintragId={eintrag.id}
          currentIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={setLightboxIndex}
        />
      )}
    </>
  )
}
