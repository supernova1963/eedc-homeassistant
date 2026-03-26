/**
 * Infothek-Seite — Verträge, Zähler & Dokumentation
 *
 * Karten-Liste mit Kategorie-Filter, Erstellen/Bearbeiten/Löschen.
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import { Plus, Pencil, Trash2, Archive, BookOpen, FileText } from 'lucide-react'
import { Button, Modal, Card, Alert, LoadingSpinner, EmptyState } from '../components/ui'
import { useSelectedAnlage } from '../hooks'
import InfothekForm from '../components/forms/InfothekForm'
import DateiLightbox from '../components/infothek/DateiLightbox'
import { infothekApi } from '../api/infothek'
import { getKategorieConfig, KATEGORIE_KEYS } from '../config/infothekKategorien'
import type { InfothekEintrag, InfothekEintragCreate, InfothekEintragUpdate, InfothekDatei } from '../types/infothek'

export default function Infothek() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const [eintraege, setEintraege] = useState<InfothekEintrag[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editingEintrag, setEditingEintrag] = useState<InfothekEintrag | null>(null)
  const [initialKategorie, setInitialKategorie] = useState<string | undefined>()
  const [deleteConfirm, setDeleteConfirm] = useState<InfothekEintrag | null>(null)
  const [filterKategorie, setFilterKategorie] = useState<string | null>(null)
  const [showArchived, setShowArchived] = useState(false)

  const anlageId = selectedAnlageId

  const loadEintraege = useCallback(async () => {
    if (!anlageId) return
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

  // Gefilterte Einträge
  const filteredEintraege = useMemo(() => {
    let result = eintraege
    if (filterKategorie) {
      result = result.filter(e => e.kategorie === filterKategorie)
    }
    if (!showArchived) {
      result = result.filter(e => e.aktiv)
    }
    return result
  }, [eintraege, filterKategorie, showArchived])

  // Zähle Einträge pro Kategorie (für Filter-Badges)
  const kategorieCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    const aktive = showArchived ? eintraege : eintraege.filter(e => e.aktiv)
    aktive.forEach(e => {
      counts[e.kategorie] = (counts[e.kategorie] || 0) + 1
    })
    return counts
  }, [eintraege, showArchived])

  const archivedCount = useMemo(() => eintraege.filter(e => !e.aktiv).length, [eintraege])
  const vorhandeneKategorien = useMemo(
    () => KATEGORIE_KEYS.filter(k => kategorieCounts[k]),
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
    try {
      await infothekApi.delete(deleteConfirm.id)
      setDeleteConfirm(null)
      await loadEintraege()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Löschen')
    }
  }

  const handleToggleAktiv = async (eintrag: InfothekEintrag) => {
    try {
      await infothekApi.update(eintrag.id, { aktiv: !eintrag.aktiv })
      await loadEintraege()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Archivieren')
    }
  }

  if (anlagenLoading || loading) {
    return <LoadingSpinner text="Lade Infothek..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Infothek</h1>
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an, um die Infothek zu nutzen.
        </Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Infothek
        </h1>
        <div className="flex items-center gap-3">
          {anlagen.length > 1 && (
            <select
              value={anlageId ?? ''}
              onChange={e => setSelectedAnlageId(Number(e.target.value))}
              className="input w-auto"
            >
              {anlagen.map(a => (
                <option key={a.id} value={a.id}>{a.anlagenname}</option>
              ))}
            </select>
          )}
          <Button onClick={() => handleCreate()}>
            <Plus className="h-4 w-4 mr-2" />
            Neuer Eintrag
          </Button>
        </div>
      </div>

      {error && (
        <Alert type="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Kategorie-Filter */}
      {vorhandeneKategorien.length > 1 && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setFilterKategorie(null)}
            className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
              !filterKategorie
                ? 'bg-primary-600 text-white'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}
          >
            Alle ({showArchived ? eintraege.length : eintraege.filter(e => e.aktiv).length})
          </button>
          {vorhandeneKategorien.map(key => {
            const config = getKategorieConfig(key)
            const Icon = config.icon
            return (
              <button
                key={key}
                onClick={() => setFilterKategorie(filterKategorie === key ? null : key)}
                className={`px-3 py-1.5 text-sm rounded-full transition-colors flex items-center gap-1.5 ${
                  filterKategorie === key
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {config.label} ({kategorieCounts[key]})
              </button>
            )
          })}
          {archivedCount > 0 && (
            <button
              onClick={() => setShowArchived(!showArchived)}
              className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
                showArchived
                  ? 'bg-gray-600 text-white'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
              }`}
            >
              <Archive className="h-3.5 w-3.5 inline mr-1" />
              Archiviert ({archivedCount})
            </button>
          )}
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
              <Plus className="h-4 w-4 mr-2" />
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
              onEdit={() => handleEdit(eintrag)}
              onDelete={() => setDeleteConfirm(eintrag)}
              onToggleAktiv={() => handleToggleAktiv(eintrag)}
            />
          ))}
        </div>
      )}

      {/* Formular Modal */}
      <Modal
        isOpen={showForm}
        onClose={() => {
          setShowForm(false)
          setEditingEintrag(null)
        }}
        title={editingEintrag ? 'Eintrag bearbeiten' : 'Neuer Eintrag'}
        size="lg"
      >
        {anlageId && (
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
        )}
      </Modal>

      {/* Löschen bestätigen */}
      <Modal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        title="Eintrag löschen"
        size="sm"
      >
        <p className="text-gray-600 dark:text-gray-400 mb-4">
          Möchtest du "{deleteConfirm?.bezeichnung}" wirklich endgültig löschen?
          Alternativ kannst du den Eintrag archivieren.
        </p>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setDeleteConfirm(null)}>
            Abbrechen
          </Button>
          <Button variant="danger" onClick={handleDelete}>
            Endgültig löschen
          </Button>
        </div>
      </Modal>
    </div>
  )
}


/** Einzelne Infothek-Karte mit Datei-Vorschau */
function InfothekKarte({
  eintrag,
  onEdit,
  onDelete,
  onToggleAktiv,
}: {
  eintrag: InfothekEintrag
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

  // Zeige die wichtigsten Parameter als Details
  const highlights: string[] = []
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
  if (params.betrag_euro) highlights.push(`${Number(params.betrag_euro).toLocaleString('de-DE')} €`)

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
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5 line-clamp-2">
                {eintrag.notizen}
              </p>
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

          {/* Actions */}
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={onToggleAktiv}
              className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              title={eintrag.aktiv ? 'Archivieren' : 'Wiederherstellen'}
            >
              <Archive className="h-4 w-4" />
            </button>
            <button
              onClick={onEdit}
              className="p-2 text-gray-400 hover:text-primary-600 transition-colors"
              title="Bearbeiten"
            >
              <Pencil className="h-4 w-4" />
            </button>
            <button
              onClick={onDelete}
              className="p-2 text-gray-400 hover:text-red-600 transition-colors"
              title="Löschen"
            >
              <Trash2 className="h-4 w-4" />
            </button>
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
