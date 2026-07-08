import { type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle } from 'lucide-react'
import { Alert, Button } from '../ui'
import { useWizardHost } from '../../v4/wizardHost'

/**
 * ImportErgebnis — geteilter Ergebnis-Schritt (W4) für die Import-Wizards
 * (Cloud/Custom/Portal). Rendert Erfolgs-/Fehler-/Hinweis-Alerts + die Terminal-
 * Navigation. Die Terminal-Aktion ist Overlay-bewusst (W2): im
 * {@link useWizardHost}-Overlay schließt „Fertig" den Assistenten statt in eine
 * V3-Route zu navigieren; auf der Standalone-Route bleiben die alten
 * Navigations-Buttons. So lebt die W2/W4-Logik an EINER Stelle statt dreifach.
 */

/** Strukturell kompatibel zu `ApplyResult` aus custom-/portalImport. */
export interface ImportErgebnisData {
  erfolg: boolean
  importiert: number
  uebersprungen: number
  fehler: string[]
  warnungen: string[]
}

interface ImportErgebnisProps {
  result: ImportErgebnisData
  selectedAnlageId: number | null
  /** „Weiteren Import starten" — setzt den Wizard auf Schritt 1 zurück. */
  onWeiter: () => void
  /** Beschriftung/Icon des Reset-Buttons (Cloud = „Cloud", Datei-Importe = „Upload"). */
  weiterLabel?: string
  weiterIcon?: ReactNode
  /** Optionaler „Nächster Schritt: Monatsabschluss"-Hinweis (nur bei Erfolg). */
  hinweis?: ReactNode
  /** Optionaler Zusatzblock über der Navigation (z. B. Cloud: Credentials speichern). */
  extra?: ReactNode
}

export default function ImportErgebnis({
  result,
  selectedAnlageId,
  onWeiter,
  weiterLabel = 'Weiteren Import starten',
  weiterIcon,
  hinweis,
  extra,
}: ImportErgebnisProps) {
  const navigate = useNavigate()
  const host = useWizardHost()

  return (
    <div className="space-y-4">
      <Alert
        type={result.erfolg ? 'success' : 'warning'}
        title={result.erfolg ? 'Import erfolgreich' : 'Import mit Hinweisen'}
      >
        <div className="space-y-1">
          <p>{result.importiert} Monate importiert</p>
          {result.uebersprungen > 0 && (
            <p>{result.uebersprungen} Monate übersprungen (bereits vorhanden)</p>
          )}
        </div>
      </Alert>

      {result.warnungen.length > 0 && (
        <Alert type="info" title="Hinweise">
          <ul className="list-disc list-inside space-y-1">
            {result.warnungen.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </Alert>
      )}

      {result.fehler.length > 0 && (
        <Alert type="error" title="Fehler">
          <ul className="list-disc list-inside space-y-1">
            {result.fehler.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
        </Alert>
      )}

      {extra}

      {result.erfolg && hinweis && (
        <Alert type="info" title="Nächster Schritt: Monatsabschluss">
          {hinweis}
        </Alert>
      )}

      {/* Terminal-Navigation (W2/W4): im Overlay schließen statt in V3-Route navigieren. */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" onClick={onWeiter}>
          {weiterIcon}
          {weiterLabel}
        </Button>
        {host.imOverlay ? (
          <Button variant="primary" onClick={host.schliessen}>
            <CheckCircle className="w-4 h-4 mr-1" />
            Fertig
          </Button>
        ) : (
          <>
            {selectedAnlageId && (
              <Button variant="secondary" onClick={() => navigate(`/monatsabschluss/${selectedAnlageId}`)}>
                Monatsabschluss starten
              </Button>
            )}
            <Button variant="primary" onClick={() => navigate('/einstellungen/monatsdaten')}>
              <CheckCircle className="w-4 h-4 mr-1" />
              Zur Monatsübersicht
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
