/**
 * Anlagenfoto-Upload-Sektion (Phase 4 — Anlagendokumentation Titelseite).
 *
 * Lädt ein einzelnes Hauptfoto pro Anlage hoch, überschreibt ein vorhandenes.
 * Die Bild-Pipeline (Resize, HEIC→JPEG, EXIF-Rotation) läuft im Backend.
 */

import { useState, useRef, useEffect } from 'react'
import { Upload, Image as ImageIcon, Trash2 } from 'lucide-react'
import { Alert } from '../ui'

const ERLAUBTE_TYPEN = 'image/jpeg,image/png,image/heic,image/heif'

interface AnlagenfotoSectionProps {
  anlageId: number
}

export default function AnlagenfotoSection({ anlageId }: AnlagenfotoSectionProps) {
  const [hasFoto, setHasFoto] = useState(false)
  const [cacheBust, setCacheBust] = useState(() => Date.now())
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const thumbUrl = `./api/anlagen/${anlageId}/foto/thumb?v=${cacheBust}`

  // Nur beim Mounten prüfen ob bereits ein Foto existiert — nicht nach Upload erneut
  useEffect(() => {
    let cancelled = false
    fetch(`./api/anlagen/${anlageId}/foto/thumb`, { method: 'HEAD' })
      .then(res => { if (!cancelled) setHasFoto(res.ok) })
      .catch(() => { if (!cancelled) setHasFoto(false) })
    return () => { cancelled = true }
  }, [anlageId])

  const handleUpload = async (file: File) => {
    setError(null)
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('datei', file)
      const res = await fetch(`./api/anlagen/${anlageId}/foto`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: 'Upload fehlgeschlagen' }))
        throw new Error(detail.detail || 'Upload fehlgeschlagen')
      }
      setCacheBust(Date.now())
      setHasFoto(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload fehlgeschlagen')
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async () => {
    setError(null)
    try {
      const res = await fetch(`./api/anlagen/${anlageId}/foto`, { method: 'DELETE' })
      if (!res.ok && res.status !== 404) {
        throw new Error('Löschen fehlgeschlagen')
      }
      setHasFoto(false)
      setCacheBust(Date.now())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Löschen fehlgeschlagen')
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleUpload(file)
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-gray-900 dark:text-white">Anlagenfoto</h3>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        Erscheint auf der Titelseite der Anlagendokumentation (Phase 4 Beta). Ein Foto pro Anlage — ein neues Foto ersetzt das vorherige.
      </p>

      {error && (
        <Alert type="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {hasFoto ? (
        <div className="flex items-start gap-4">
          <img
            src={thumbUrl}
            alt="Anlagenfoto"
            className="w-32 h-32 object-cover rounded-lg border border-gray-200 dark:border-gray-700"
          />
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="btn-secondary text-xs py-1 px-3"
            >
              {uploading ? 'Wird hochgeladen…' : 'Ersetzen'}
            </button>
            <button
              type="button"
              onClick={handleDelete}
              disabled={uploading}
              className="text-xs py-1 px-3 text-red-600 hover:text-red-700 flex items-center gap-1"
            >
              <Trash2 className="h-3 w-3" /> Entfernen
            </button>
          </div>
        </div>
      ) : (
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`
            border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors
            ${dragOver
              ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
              : 'border-gray-300 dark:border-gray-600 hover:border-primary-400 hover:bg-gray-50 dark:hover:bg-gray-800'
            }
          `}
        >
          {uploading ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Wird hochgeladen…</p>
          ) : (
            <div className="flex flex-col items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
              <Upload className="h-5 w-5" />
              <span>
                <ImageIcon className="h-3.5 w-3.5 inline mr-1" />
                Foto hochladen (JPEG, PNG, HEIC)
              </span>
              <span className="text-xs">Klicken oder Datei hierher ziehen</span>
            </div>
          )}
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept={ERLAUBTE_TYPEN}
        onChange={e => {
          const file = e.target.files?.[0]
          if (file) handleUpload(file)
          e.target.value = ''
        }}
        className="hidden"
        title="Anlagenfoto auswählen"
      />
    </div>
  )
}
