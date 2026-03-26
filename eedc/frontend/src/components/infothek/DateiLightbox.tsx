/**
 * Lightbox-Komponente für Infothek-Dateien.
 *
 * Zeigt Bilder im Vollbild-Modus. PDFs werden in neuem Tab geöffnet.
 * Navigation mit Pfeiltasten und Klick.
 */

import { useEffect, useCallback } from 'react'
import { X, ChevronLeft, ChevronRight } from 'lucide-react'
import { infothekApi } from '../../api/infothek'
import type { InfothekDatei } from '../../types/infothek'

interface DateiLightboxProps {
  dateien: InfothekDatei[]
  eintragId: number
  currentIndex: number
  onClose: () => void
  onNavigate: (index: number) => void
}

export default function DateiLightbox({
  dateien,
  eintragId,
  currentIndex,
  onClose,
  onNavigate,
}: DateiLightboxProps) {
  const current = dateien[currentIndex]
  const hasPrev = currentIndex > 0
  const hasNext = currentIndex < dateien.length - 1

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    switch (e.key) {
      case 'Escape':
        onClose()
        break
      case 'ArrowLeft':
        if (hasPrev) onNavigate(currentIndex - 1)
        break
      case 'ArrowRight':
        if (hasNext) onNavigate(currentIndex + 1)
        break
    }
  }, [onClose, onNavigate, currentIndex, hasPrev, hasNext])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = ''
    }
  }, [handleKeyDown])

  if (!current) return null

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center"
      onClick={onClose}
    >
      {/* Schließen */}
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2 text-white/80 hover:text-white transition-colors z-10"
      >
        <X className="h-8 w-8" />
      </button>

      {/* Navigation links */}
      {hasPrev && (
        <button
          onClick={e => { e.stopPropagation(); onNavigate(currentIndex - 1) }}
          className="absolute left-4 p-2 text-white/60 hover:text-white transition-colors z-10"
        >
          <ChevronLeft className="h-10 w-10" />
        </button>
      )}

      {/* Bild */}
      <img
        src={infothekApi.dateiUrl(eintragId, current.id)}
        alt={current.dateiname}
        className="max-h-[90vh] max-w-[90vw] object-contain"
        onClick={e => e.stopPropagation()}
      />

      {/* Navigation rechts */}
      {hasNext && (
        <button
          onClick={e => { e.stopPropagation(); onNavigate(currentIndex + 1) }}
          className="absolute right-4 p-2 text-white/60 hover:text-white transition-colors z-10"
        >
          <ChevronRight className="h-10 w-10" />
        </button>
      )}

      {/* Dateiname */}
      <div className="absolute bottom-4 text-white/60 text-sm">
        {current.dateiname} ({currentIndex + 1}/{dateien.length})
      </div>
    </div>
  )
}
