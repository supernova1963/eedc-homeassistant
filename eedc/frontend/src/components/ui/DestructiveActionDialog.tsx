import { useState, useEffect, ReactNode } from 'react'
import { AlertTriangle, Download, Check, ShieldCheck } from 'lucide-react'
import Modal from './Modal'
import Button from './Button'
import Alert from './Alert'
import { importApi } from '../../api/import'
import { downloadFile } from '../../lib'

interface DestructiveActionDialogProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void | Promise<void>
  title: string
  itemLabel: ReactNode
  warningMessage: ReactNode
  anlageId: number | undefined
  anlageName: string
  confirmLabel?: string
  backupHint?: ReactNode
}

export default function DestructiveActionDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  itemLabel,
  warningMessage,
  anlageId,
  anlageName,
  confirmLabel = 'Endgültig löschen',
  backupHint,
}: DestructiveActionDialogProps) {
  const [backupCreated, setBackupCreated] = useState(false)
  const [backupRunning, setBackupRunning] = useState(false)
  const [backupError, setBackupError] = useState<string | null>(null)
  const [skipBackup, setSkipBackup] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmError, setConfirmError] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen) {
      setBackupCreated(false)
      setBackupRunning(false)
      setBackupError(null)
      setSkipBackup(false)
      setDeleting(false)
      setConfirmError(null)
    }
  }, [isOpen])

  const handleBackup = async () => {
    if (!anlageId) return
    setBackupError(null)
    setBackupRunning(true)
    try {
      const safeName = (anlageName || 'anlage').replace(/\s+/g, '_')
      const datum = new Date().toISOString().slice(0, 10)
      await downloadFile(
        importApi.getFullExportUrl(anlageId),
        `eedc_backup_${safeName}_${datum}.json`,
      )
      setBackupCreated(true)
    } catch (e) {
      setBackupError(e instanceof Error ? e.message : 'Backup fehlgeschlagen')
    } finally {
      setBackupRunning(false)
    }
  }

  const handleConfirm = async () => {
    setConfirmError(null)
    setDeleting(true)
    try {
      await onConfirm()
    } catch (e) {
      // Fehler im Dialog zeigen statt hinter dem Modal — Dialog bleibt offen
      setConfirmError(e instanceof Error ? e.message : 'Löschen fehlgeschlagen')
    } finally {
      setDeleting(false)
    }
  }

  const canDelete = backupCreated || skipBackup

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="sm">
      <div className="space-y-4">
        {/* Warnhinweis */}
        <div className="flex gap-3 p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
          <AlertTriangle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-red-800 dark:text-red-200 space-y-1">
            <p className="font-medium">{itemLabel}</p>
            <p>{warningMessage}</p>
            <p className="text-xs opacity-80 mt-1">Diese Aktion kann nicht rückgängig gemacht werden.</p>
          </div>
        </div>

        {/* Backup-Sektion */}
        {!backupCreated && !skipBackup && (
          <div className="p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
            <div className="flex items-start gap-3 mb-3">
              <ShieldCheck className="h-5 w-5 text-blue-500 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-blue-900 dark:text-blue-100">
                <p className="font-medium">Vorher ein Backup herunterladen?</p>
                <p className="opacity-90 mt-0.5">
                  {backupHint ?? (
                    <>Lädt einen vollständigen JSON-Export der Anlage <strong>„{anlageName}"</strong> herunter. So lässt sich der Zustand jederzeit wiederherstellen.</>
                  )}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={handleBackup}
                disabled={backupRunning || !anlageId}
                loading={backupRunning}
                size="sm"
              >
                <Download className="h-4 w-4 mr-2" />
                {backupRunning ? 'Backup wird erstellt…' : 'Backup erstellen & herunterladen'}
              </Button>
              <button
                type="button"
                onClick={() => setSkipBackup(true)}
                className="text-xs text-gray-500 dark:text-gray-400 hover:underline self-center"
              >
                Ohne Backup fortfahren
              </button>
            </div>
            {backupError && (
              <Alert type="error" className="mt-3">{backupError}</Alert>
            )}
          </div>
        )}

        {backupCreated && (
          <div className="flex items-start gap-3 p-3 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
            <Check className="h-5 w-5 text-green-500 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-green-800 dark:text-green-200">
              <p className="font-medium">Backup heruntergeladen.</p>
              <p className="opacity-90 mt-0.5 text-xs">Du kannst jetzt sicher löschen.</p>
            </div>
          </div>
        )}

        {skipBackup && (
          <div className="flex items-start gap-3 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
            <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-amber-800 dark:text-amber-200 flex-1">
              <p>Fortfahren ohne Backup.{' '}
                <button
                  type="button"
                  onClick={() => setSkipBackup(false)}
                  className="underline hover:no-underline"
                >
                  Doch ein Backup erstellen?
                </button>
              </p>
            </div>
          </div>
        )}

        {confirmError && (
          <Alert type="error">{confirmError}</Alert>
        )}

        {/* Aktionen */}
        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" onClick={onClose} disabled={deleting}>
            Abbrechen
          </Button>
          <Button
            variant="danger"
            onClick={handleConfirm}
            disabled={!canDelete || deleting}
            loading={deleting}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
