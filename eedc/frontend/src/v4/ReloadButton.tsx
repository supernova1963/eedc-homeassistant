import { RefreshCw } from 'lucide-react'
import Button from '../components/ui/Button'

/**
 * ReloadButton — DER „Aktualisieren"-Baustein der v4-Sicht-Köpfe (B15, R3b S1
 * 2026-07-05). Löst vier wörtlich kopierte, handgebaute Reload-Chips ab
 * (TagRahmen/MonatRahmen/JahrRahmen/CockpitAussichtV4): sitzt auf `ui/Button`
 * ghost+sm+`loading` (eingebauter Loader2-Spinner statt Hand-Spinner, 36-px-
 * Kontroll-Höhe statt py-1-Improvisation). RefreshCw nur bei `!loading` rendern
 * (sonst Doppel-Icon neben dem Spinner); Icon `max-sm:hidden` gemäß D14-14.
 */
export function ReloadButton({
  onClick, loading, disabled, label = 'Aktualisieren',
}: {
  onClick: () => void
  loading: boolean
  disabled?: boolean
  label?: string
}) {
  return (
    <Button variant="ghost" size="sm" loading={loading} disabled={disabled} onClick={onClick}>
      {!loading && <RefreshCw className="h-4 w-4 mr-1.5 max-sm:hidden" />}
      {label}
    </Button>
  )
}
