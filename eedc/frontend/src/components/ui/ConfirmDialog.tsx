import { useEffect, useState, ReactNode } from 'react'
import Modal from './Modal'
import Button from './Button'
import Alert from './Alert'

/**
 * ConfirmDialog — leichter Bestätigungsdialog (Style-Guide Teil D, M9).
 *
 * Für einfache/umkehrbare Aktionen (Archivieren, Zurücksetzen) und leichte
 * Löschungen: Titel + Meldung + Bestätigen/Abbrechen. Async-Fehler bleiben im
 * Dialog. Der schwere {@link DestructiveActionDialog} (mit erzwungenem Backup +
 * „irreversibel") bleibt der Anlage-Löschung vorbehalten — nicht für reversibles
 * Archivieren verwenden.
 */
interface ConfirmDialogProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void | Promise<void>
  title: string
  message: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** 'danger' = roter Bestätigen-Button (Löschen); 'primary' = Standard (Archivieren …). */
  variant?: 'primary' | 'danger'
}

export default function ConfirmDialog({
  isOpen, onClose, onConfirm, title, message,
  confirmLabel = 'Bestätigen', cancelLabel = 'Abbrechen', variant = 'primary',
}: ConfirmDialogProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen) { setBusy(false); setError(null) }
  }, [isOpen])

  const handleConfirm = async () => {
    setError(null)
    setBusy(true)
    try {
      await onConfirm()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Aktion fehlgeschlagen')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="sm">
      <div className="space-y-4">
        <div className="text-sm text-gray-600 dark:text-gray-400">{message}</div>
        {error && <Alert type="error">{error}</Alert>}
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button variant={variant === 'danger' ? 'danger' : 'primary'} onClick={handleConfirm} loading={busy}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
