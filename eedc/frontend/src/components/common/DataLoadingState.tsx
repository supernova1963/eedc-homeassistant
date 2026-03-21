/**
 * Wrapper für Loading/Error/Empty-States.
 *
 * Ersetzt das duplizierte Pattern:
 *   if (loading) return <div>Laden...</div>
 *   if (error) return <div>Fehler: {error}</div>
 *   if (!data) return <div>Keine Daten</div>
 */

interface DataLoadingStateProps {
  loading: boolean
  error: string | null
  isEmpty?: boolean
  emptyMessage?: string
  onRetry?: () => void
  children: React.ReactNode
}

export default function DataLoadingState({
  loading, error, isEmpty, emptyMessage = 'Keine Daten vorhanden.', onRetry, children,
}: DataLoadingStateProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 text-gray-400 dark:text-gray-500">
        <svg className="animate-spin h-5 w-5 mr-3" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        Daten werden geladen…
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-red-500 dark:text-red-400">
        <p className="mb-2">Fehler: {error}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="text-sm px-3 py-1 rounded bg-red-100 dark:bg-red-900/30 hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors"
          >
            Erneut versuchen
          </button>
        )}
      </div>
    )
  }

  if (isEmpty) {
    return (
      <div className="flex items-center justify-center p-12 text-gray-400 dark:text-gray-500">
        {emptyMessage}
      </div>
    )
  }

  return <>{children}</>
}
