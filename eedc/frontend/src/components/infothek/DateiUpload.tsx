/**
 * Datei-Upload-Komponente für Infothek-Einträge.
 *
 * Unterstützt Bilder (JPEG, PNG, HEIC) und PDFs.
 * Max 3 Dateien pro Eintrag, Drag & Drop oder Klick.
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { Upload, FileText, Image as ImageIcon, Trash2 } from 'lucide-react'
import { Alert } from '../ui'
import { infothekApi } from '../../api/infothek'
import type { InfothekDatei } from '../../types/infothek'

const MAX_DATEIEN = 3
const ERLAUBTE_TYPEN = 'image/jpeg,image/png,image/heic,image/heif,application/pdf'

interface DateiUploadProps {
  eintragId: number
  onDateiChange?: () => void
}

export default function DateiUpload({ eintragId, onDateiChange }: DateiUploadProps) {
  const [dateien, setDateien] = useState<InfothekDatei[]>([])
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

  const handleUpload = async (files: FileList | File[]) => {
    const fileArray = Array.from(files)
    const remaining = MAX_DATEIEN - dateien.length

    if (remaining <= 0) {
      setError(`Maximal ${MAX_DATEIEN} Dateien pro Eintrag erlaubt.`)
      return
    }

    const toUpload = fileArray.slice(0, remaining)
    setError(null)
    setUploading(true)

    for (const file of toUpload) {
      try {
        await infothekApi.uploadDatei(eintragId, file)
      } catch (err) {
        setError(err instanceof Error ? err.message : `Fehler beim Upload von ${file.name}`)
      }
    }

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
      handleUpload(e.dataTransfer.files)
    }
  }

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
              className="relative group w-24 h-24 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden bg-gray-50 dark:bg-gray-800"
            >
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
              {/* Löschen-Overlay */}
              <button
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

      {/* Upload-Bereich */}
      {dateien.length < MAX_DATEIEN && (
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
            onChange={e => e.target.files && handleUpload(e.target.files)}
            className="hidden"
            title="Datei auswählen"
          />
          {uploading ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Wird hochgeladen...</p>
          ) : (
            <div className="flex items-center justify-center gap-2 text-sm text-gray-500 dark:text-gray-400">
              <Upload className="h-4 w-4" />
              <span>
                <ImageIcon className="h-3.5 w-3.5 inline" /> Fotos oder{' '}
                <FileText className="h-3.5 w-3.5 inline" /> PDFs hochladen
              </span>
              <span className="text-xs">({dateien.length}/{MAX_DATEIEN})</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
