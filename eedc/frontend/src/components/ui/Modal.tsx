import { ReactNode, useEffect, useId, useRef } from 'react'
import { X } from 'lucide-react'

interface ModalProps {
  isOpen: boolean
  onClose: () => void
  title: string
  children: ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl'
}

export default function Modal({ isOpen, onClose, title, children, size = 'md' }: ModalProps) {
  // Style-Guide B16: der Dialog trägt seinen Titel als zugänglichen Namen. `useId`
  // statt eigenem Zähler — mehrere Dialoge können gleichzeitig im Baum stehen
  // (z. B. Wizard-Modal + Rückfrage-Dialog in `v4/EinstellungenModalHost`).
  const titelId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  const rueckgabeRef = useRef<HTMLElement | null>(null)

  // ESC zum Schließen
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      // „Wer ESC verbraucht, meldet es an": Zuhörer auf `document` laufen in der
      // Reihenfolge ihrer Registrierung, ein später geöffnetes Overlay also NACH
      // einem früheren. Der Dialog liegt oben, nimmt die Taste und markiert sie —
      // ein darunterliegendes `blocks/FokusVollbild` lässt sie daraufhin liegen.
      e.preventDefault()
      onClose()
    }

    if (isOpen) {
      document.addEventListener('keydown', handleEsc)
      document.body.style.overflow = 'hidden'
    }

    return () => {
      document.removeEventListener('keydown', handleEsc)
      document.body.style.overflow = ''
    }
  }, [isOpen, onClose])

  // Anfangsfokus + Rückgabe. Fokussiert wird der Dialog SELBST, nicht sein erstes
  // Bedienelement: welches das ist, entscheidet der Inhalt, und in den Lösch-Dialogen
  // wäre es die zerstörende Aktion. Beim Schließen geht der Fokus an das auslösende
  // Element zurück — sonst steht er nach dem Dialog am Dokumentanfang.
  useEffect(() => {
    if (!isOpen) return
    rueckgabeRef.current = document.activeElement as HTMLElement | null
    dialogRef.current?.focus()

    return () => {
      const ziel = rueckgabeRef.current
      rueckgabeRef.current = null
      // Nur zurückgeben, wenn es das Element noch gibt: die auslösende Schaltfläche
      // kann durch die Aktion des Dialogs selbst verschwunden sein (Zeile gelöscht).
      if (ziel && document.contains(ziel)) ziel.focus()
    }
  }, [isOpen])

  if (!isOpen) return null

  const sizes = {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-2 sm:p-4">
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titelId}
          tabIndex={-1}
          className={`relative flex flex-col w-full ${sizes[size]} max-h-[90dvh] bg-white dark:bg-gray-800 rounded-xl shadow-xl`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="shrink-0 flex items-center justify-between px-4 sm:px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <h2 id={titelId} className="text-lg font-semibold text-gray-900 dark:text-white">
              {title}
            </h2>
            <button
              onClick={onClose}
              aria-label="Schließen"
              className="p-1 rounded-lg text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 min-h-0 overflow-y-auto px-4 sm:px-6 py-4">
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
