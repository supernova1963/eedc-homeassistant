/**
 * Datei-Upload-Komponente für Infothek-Einträge.
 *
 * Unterstützt Bilder (JPEG, PNG, HEIC) und PDFs.
 * Max 15 Dateien pro Eintrag, Drag & Drop oder Klick.
 * Pro ausgewählte Datei kann eine optionale Beschreibung vergeben werden.
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { Upload, FileText, Image as ImageIcon, Trash2, X } from 'lucide-react'
import { Alert } from '../ui'
import { infothekApi } from '../../api/infothek'
import type { InfothekDatei } from '../../types/infothek'

const MAX_DATEIEN = 15
const ERLAUBTE_TYPEN = 'image/jpeg,image/png,image/heic,image/heif,application/pdf'

interface DateiUploadProps {
  eintragId: number
  onDateiChange?: () => void
}

interface PendingFile {
  id: string
  file: File
  beschreibung: string
}

export default function DateiUpload({ eintragId, onDateiChange }: DateiUploadProps) {
  const [dateien, setDateien] = useState<InfothekDatei[]>([])
  const [pending, setPending] = useState<PendingFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadDateien = useCallback(async () => {
    try {
      const result = await infothekApi.listDateien(eintragId)
      setDateien(result)
    } catch {
      // Fehler ignorieren beim Laden
    }
  }, [eintragId])

  useEffect(() => {
    loadDateien()
  }, [loadDateien])

  const handleSelectFiles = (files: FileList | File[]) => {
    const fileArray = Array.from(files)
    const remaining = MAX_DATEIEN - dateien.length - pending.length

    if (remaining <= 0) {
      setError(`Maximal ${MAX_DATEIEN} Dateien pro Eintrag erlaubt.`)
      return
    }

    const toAdd = fileArray.slice(0, remaining).map(file => ({
      id: `${file.name}-${file.size}-${Math.random().toString(36).slice(2)}`,
      file,
      beschreibung: '',
    }))
    setError(null)
    setPending(prev => [...prev, ...toAdd])
  }

  const removePending = (id: string) => {
    setPending(prev => prev.filter(p => p.id !== id))
  }

  const updatePendingBeschreibung = (id: string, beschreibung: string) => {
    setPending(prev => prev.map(p => (p.id === id ? { ...p, beschreibung } : p)))
  }

  const handleUploadPending = async () => {
    if (pending.length === 0) return
    setError(null)
    setUploading(true)

    for (const item of pending) {
      try {
        await infothekApi.uploadDatei(
          eintragId,
          item.file,
          item.beschreibung.trim() || undefined,
        )
      } catch (err) {
        setError(err instanceof Error ? err.message : `Fehler beim Upload von ${item.file.name}`)
      }
    }

    setPending([])
    await loadDateien()
    setUploading(false)
    onDateiChange?.()
  }

  const handleDelete = async (dateiId: number) => {
    try {
      await infothekApi.deleteDatei(eintragId, dateiId)
      await loadDateien()
      onDateiChange?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Löschen')
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files.length > 0) {
      handleSelectFiles(e.dataTransfer.files)
    }
  }

  const canAddMore = dateien.length + pending.length < MAX_DATEIEN

  return (
    <div className="space-y-3">
      {error && (
        <Alert type="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Vorhandene Dateien */}
      {dateien.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {dateien.map(datei => (
            <div
              key={datei.id}
              className="relative group w-28 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden bg-gray-50 dark:bg-gray-800"
              title={datei.beschreibung || datei.dateiname}
            >
              <div className="w-full h-24">
                {datei.dateityp === 'image' ? (
                  <img
                    src={infothekApi.thumbnailUrl(eintragId, datei.id)}
                    alt={datei.dateiname}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center p-2">
                    <FileText className="h-8 w-8 text-red-500" />
                    <span className="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate w-full text-center">
                      {datei.dateiname}
                    </span>
                  </div>
                )}
              </div>
              {datei.beschreibung && (
                <div className="px-1 py-1 text-[10px] leading-tight text-gray-600 dark:text-gray-300 truncate border-t border-gray-200 dark:border-gray-700">
                  {datei.beschreibung}
                </div>
              )}
              {/* Löschen-Overlay */}
              <button
                type="button"
                onClick={() => handleDelete(datei.id)}
                className="absolute top-1 right-1 p-1 bg-red-600 text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                title="Löschen"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Staging-Queue: ausgewählte, noch nicht hochgeladene Dateien */}
      {pending.length > 0 && (
        <div className="space-y-2 border border-dashed border-primary-400 rounded-lg p-3 bg-primary-50/40 dark:bg-primary-900/10">
          <div className="text-xs font-medium text-gray-700 dark:text-gray-300">
            Bereit zum Hochladen ({pending.length}):
          </div>
          {pending.map(item => (
            <div key={item.id} className="flex items-center gap-2">
              {item.file.type.startsWith('image/') ? (
                <ImageIcon className="h-4 w-4 shrink-0 text-gray-500" />
              ) : (
                <FileText className="h-4 w-4 shrink-0 text-red-500" />
              )}
              <span className="text-xs text-gray-600 dark:text-gray-400 truncate max-w-[140px]" title={item.file.name}>
                {item.file.name}
              </span>
              <input
                type="text"
                placeholder="Beschreibung (optional)"
                value={item.beschreibung}
                onChange={e => updatePendingBeschreibung(item.id, e.target.value)}
                className="input flex-1 text-xs py-1"
                disabled={uploading}
              />
              <button
                type="button"
                onClick={() => removePending(item.id)}
                className="p-1 text-gray-400 hover:text-red-600 disabled:opacity-50"
                title="Entfernen"
                disabled={uploading}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => setPending([])}
              disabled={uploading}
              className="btn-secondary text-xs py-1 px-2"
            >
              Abbrechen
            </button>
            <button
              type="button"
              onClick={handleUploadPending}
              disabled={uploading}
              className="btn-primary text-xs py-1 px-2"
            >
              {uploading ? 'Wird hochgeladen…' : `${pending.length} hochladen`}
            </button>
          </div>
        </div>
      )}

      {/* Upload-Bereich */}
      {canAddMore && (
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`
            border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors
            ${dragOver
              ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
              : 'border-gray-300 dark:border-gray-600 hover:border-primary-400 hover:bg-gray-50 dark:hover:bg-gray-800'
            }
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ERLAUBTE_TYPEN}
            multiple
            onChange={e => {
              if (e.target.files) handleSelectFiles(e.target.files)
              e.target.value = ''
            }}
            className="hidden"
            title="Datei auswählen"
          />
          <div className="flex items-center justify-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <Upload className="h-4 w-4" />
            <span>
              <ImageIcon className="h-3.5 w-3.5 inline" /> Fotos oder{' '}
              <FileText className="h-3.5 w-3.5 inline" /> PDFs hochladen
            </span>
            <span className="text-xs">({dateien.length + pending.length}/{MAX_DATEIEN})</span>
          </div>
        </div>
      )}
    </div>
  )
}
