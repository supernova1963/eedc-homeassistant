/**
 * AppErrorBoundary — DIE app-weite Render-Fehlergrenze (R18-1, rapahl #207).
 *
 * Vorher gab es in src/ KEINE ErrorBoundary: ein Render-Fehler oder ein
 * ChunkLoadError (veralteter Hash-Chunk nach einem Deploy — Tab hielt die alten
 * Chunk-Namen, der erste Klick in eine ungeladene Rubrik lief auf 404) hat den
 * kompletten Baum unmountet ⇒ dauerhaft schwarzer Bildschirm, heilbar nur per
 * manuellem Reload. Genau Rainers Befund „nach Aktualisieren war alles in
 * Ordnung".
 *
 * Verhalten:
 *  • Chunk-/Modul-Ladefehler (Vite: „Failed to fetch dynamically imported
 *    module", Webpack-Konvention „ChunkLoadError"/„Loading chunk … failed",
 *    Safari: „Importing a module script failed") → Erklärung „neue Version
 *    installiert" + „Neu laden"-Button (window.location.reload()).
 *  • Sonstige Render-Fehler → Fehlertext + „Neu laden".
 * Gilt V3 UND V4 (umschließt den ganzen Routenbaum in App.tsx).
 *
 * Bewusst eine Klassen-Komponente — Error Boundaries gibt es in React nur so
 * (getDerivedStateFromError/componentDidCatch, keine Hook-Entsprechung).
 */
import { Component, type ReactNode } from 'react'
import { RefreshCw } from 'lucide-react'
import Alert from './ui/Alert'
import Button from './ui/Button'

function istChunkFehler(error: Error): boolean {
  return (
    error.name === 'ChunkLoadError' ||
    /Failed to fetch dynamically imported module|Importing a module script failed|Loading chunk [^ ]+ failed|error loading dynamically imported module/i.test(
      `${error.message}`,
    )
  )
}

interface State {
  error: Error | null
}

export class AppErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error): void {
    // Sichtbarkeit im Log (stille Bugs → sofort Logs); kein externer Report.
    console.error('AppErrorBoundary:', error)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    const chunk = istChunkFehler(error)
    return (
      <div className="min-h-dvh flex items-center justify-center p-4 bg-gray-50 dark:bg-gray-900">
        <div className="w-full max-w-lg">
          <Alert type="error" title={chunk ? 'eedc wurde aktualisiert' : 'Unerwarteter Fehler'}>
            <div className="space-y-3">
              <p>
                {chunk
                  ? 'Diese Seite hält noch einen alten Stand im Browser — vermutlich wurde gerade eine neue Version installiert. Einmal neu laden genügt.'
                  : `Die Ansicht konnte nicht dargestellt werden (${error.message || 'unbekannter Fehler'}). Neu laden stellt die Anwendung wieder her.`}
              </p>
              <Button variant="primary" size="sm" onClick={() => window.location.reload()}>
                <RefreshCw className="h-4 w-4 mr-1.5" />
                Neu laden
              </Button>
            </div>
          </Alert>
        </div>
      </div>
    )
  }
}
