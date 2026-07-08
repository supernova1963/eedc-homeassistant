import { ReactNode, useEffect, useRef, useState } from 'react'
import { Upload, Image as ImageIcon, Trash2 } from 'lucide-react'
import Button from './Button'

/**
 * BildUpload — DER Bild-Upload-SoT (Style-Guide Teil D, M7).
 *
 * Zeigt eine Dropzone, solange kein Bild vorhanden ist, sonst das Thumbnail
 * mit „Ersetzen"/„Entfernen". Konsolidiert das Muster aus `infothek/DateiUpload`.
 *
 * **Heilt R17-8:** die Vorschau wird direkt aus dem persistierten Bild geladen
 * (`<img>` GET → 200/404 via `onError`), NIE über einen `HEAD`-Existenz-Check —
 * der frühere `AnlagenfotoSection`-HEAD lief in ein `405 Method Not Allowed`
 * (der Foto-Endpoint kennt nur GET) und blendete das Thumbnail nach jedem Reload
 * aus. Präsentational: Upload/Löschen/Cache-Bust liegen beim Aufrufer.
 */
interface BildUploadProps {
  /** Thumbnail-URL inkl. Cache-Bust. Ein 404 fällt sauber auf die Dropzone zurück. */
  src: string
  onSelect: (file: File) => void
  onDelete: () => void
  uploading?: boolean
  /** MIME-Liste; Default gängige Bildtypen. */
  accept?: string
  /** Kurzer Aufforderungstext in der Dropzone (z. B. erlaubte Formate). */
  hinweis?: ReactNode
  altText?: string
}

export default function BildUpload({
  src, onSelect, onDelete, uploading = false,
  accept = 'image/jpeg,image/png,image/heic,image/heif',
  hinweis = 'Bild hochladen', altText = 'Bild',
}: BildUploadProps) {
  // 'pruefen' = Probe-Img lädt noch · 'da' = Bild vorhanden · 'weg' = 404/kein Bild.
  const [status, setStatus] = useState<'pruefen' | 'da' | 'weg'>('pruefen')
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // Neue URL (nach Upload/Löschen) → erneut prüfen, ob das Bild lädt.
  useEffect(() => { setStatus('pruefen') }, [src])

  const waehlen = () => inputRef.current?.click()
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) onSelect(file)
  }

  return (
    <div className="space-y-3">
      {/* Verstecktes Probe-Img: entscheidet 200→'da' / 404→'weg' ohne Broken-Image-Flackern. */}
      <img src={src} alt="" aria-hidden className="hidden" onLoad={() => setStatus('da')} onError={() => setStatus('weg')} />

      {status === 'pruefen' ? (
        <div className="w-32 h-32 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 animate-pulse" />
      ) : status === 'da' ? (
        <div className="flex items-start gap-4">
          <img
            src={src}
            alt={altText}
            className="w-32 h-32 object-cover rounded-lg border border-gray-200 dark:border-gray-700"
          />
          <div className="flex flex-col gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={waehlen} disabled={uploading}>
              {uploading ? 'Wird hochgeladen…' : 'Ersetzen'}
            </Button>
            <button
              type="button"
              onClick={onDelete}
              disabled={uploading}
              className="text-xs py-1 px-3 text-red-600 hover:text-red-700 flex items-center gap-1 disabled:opacity-50"
            >
              <Trash2 className="h-3 w-3" /> Entfernen
            </button>
          </div>
        </div>
      ) : (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={waehlen}
          className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
            dragOver
              ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
              : 'border-gray-300 dark:border-gray-600 hover:border-primary-400 hover:bg-gray-50 dark:hover:bg-gray-800'
          }`}
        >
          {uploading ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Wird hochgeladen…</p>
          ) : (
            <div className="flex flex-col items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
              <Upload className="h-5 w-5" />
              <span>
                <ImageIcon className="h-3.5 w-3.5 inline mr-1" />
                {hinweis}
              </span>
              <span className="text-xs">Klicken oder Datei hierher ziehen</span>
            </div>
          )}
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onSelect(file)
          e.target.value = ''
        }}
        className="hidden"
        title="Bild auswählen"
      />
    </div>
  )
}
