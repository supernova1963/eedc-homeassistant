/**
 * FehlerZustand — DER B8-Fehler-Baustein (Style-Guide B8; R3b S15, 2026-07-05).
 *
 * „Was ist schief, was tun": rendert den IST-Fehlertext in der etablierten
 * Alert-error-Optik (v4-Kanon: Prognose-Blöcke, ROI, Community-Sichten) plus
 * optionaler Retry-Affordance. Bewusst layout-neutral OHNE eigene Seiten-Shell —
 * die stellt der Aufrufer; so deckt EIN Baustein Seiten- UND Sektions-/Block-
 * Ebene ab. Löst die nackten text-red-500-<p>-Kopien ab (A2-11 → S15);
 * Wächter: check:b8 (Fehlertext-Zähler).
 */
import { RefreshCw } from 'lucide-react'
import Alert from './Alert'
import Button from './Button'

interface FehlerZustandProps {
  /** IST-Fehlertext aus Hook/Catch — unverändert durchreichen, kein neuer Wortlaut. */
  text: string
  /** Optionale Überschrift (Alert-title). */
  titel?: string
  /** Retry nur anbieten, wenn der Refetch wirklich möglich ist (sonst Fassade). */
  onRetry?: () => void
  className?: string
}

export default function FehlerZustand({ text, titel, onRetry, className }: FehlerZustandProps) {
  return (
    <Alert type="error" title={titel} className={className}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="flex-1 min-w-[12rem]">{text}</span>
        {onRetry && (
          <Button variant="ghost" size="sm" onClick={onRetry} className="shrink-0 -my-1">
            <RefreshCw className="h-4 w-4 mr-1.5 max-sm:hidden" />
            Erneut versuchen
          </Button>
        )}
      </div>
    </Alert>
  )
}
