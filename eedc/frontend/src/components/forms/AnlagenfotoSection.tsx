/**
 * Anlagenfoto-Upload-Sektion (Phase 4 — Anlagendokumentation Titelseite).
 *
 * Lädt ein einzelnes Hauptfoto pro Anlage hoch, überschreibt ein vorhandenes.
 * Die Bild-Pipeline (Resize, HEIC→JPEG, EXIF-Rotation) läuft im Backend.
 *
 * Nutzt den {@link BildUpload}-SoT (M7) — die Vorschau kommt direkt aus dem
 * persistierten Bild (GET), NICHT über einen `HEAD`-Check (der Foto-Endpoint
 * kennt nur GET → HEAD lief in 405 → R17-8: Thumbnail nach Reload weg).
 */
import { useState } from 'react'
import { Alert, BildUpload } from '../ui'
import { fetchApi } from '../../api/fetchApi'

interface AnlagenfotoSectionProps {
  anlageId: number
}

export default function AnlagenfotoSection({ anlageId }: AnlagenfotoSectionProps) {
  const [cacheBust, setCacheBust] = useState(() => Date.now())
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const thumbUrl = `./api/anlagen/${anlageId}/foto/thumb?v=${cacheBust}`

  const handleUpload = async (file: File) => {
    setError(null)
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('datei', file)
      const res = await fetchApi(`./api/anlagen/${anlageId}/foto`, { method: 'POST', body: formData })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: 'Upload fehlgeschlagen' }))
        throw new Error(detail.detail || 'Upload fehlgeschlagen')
      }
      setCacheBust(Date.now())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload fehlgeschlagen')
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async () => {
    setError(null)
    try {
      const res = await fetchApi(`./api/anlagen/${anlageId}/foto`, { method: 'DELETE' })
      if (!res.ok && res.status !== 404) throw new Error('Löschen fehlgeschlagen')
      setCacheBust(Date.now())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Löschen fehlgeschlagen')
    }
  }

  return (
    <div className="space-y-3">
      {error && (
        <Alert type="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      <BildUpload
        src={thumbUrl}
        onSelect={handleUpload}
        onDelete={handleDelete}
        uploading={uploading}
        hinweis="Foto hochladen (JPEG, PNG, HEIC)"
        altText="Anlagenfoto"
      />
    </div>
  )
}
