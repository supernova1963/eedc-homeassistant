/**
 * AnlagenSelektorView — präsentations-SoT des globalen Anlagen-Kontextwählers.
 *
 * Geteilt (wie {@link IATopNav}): konsumiert von der öffentlichen Vorschau
 * (`components/preview/IASkeleton`, Demo-Daten, KEIN Backend) UND vom verbundenen
 * `v4/AnlagenSelektor` (zieht `useSelectedAnlage`). Liegt bewusst in
 * `components/layout/` (nicht `v4/`), damit die im Prod-Build enthaltene Vorschau
 * keine v4-Symbole hereinzieht (Flag-Reinheit).
 *
 * Sichtbarkeit: NUR ab 2 Anlagen (bei genau einer gibt es nichts zu wählen).
 * Tokens gespiegelt vom Einstellungen-Dropdown (`TopNavigation`): kein neues
 * Panel-Muster, keine Inline-Hex. Responsiv: Desktop-Leiste auto-breit, Mobile-
 * Hamburger volle Breite.
 */
import { useState, useRef, useEffect } from 'react'
import { Home, ChevronDown, Check } from 'lucide-react'

/** Minimal-Form für die View — nur was die Leiste braucht. */
export interface AnlagenSelektorEintrag {
  id: number
  anlagenname: string
}

export function AnlagenSelektorView({
  anlagen,
  selectedId,
  onSelect,
}: {
  anlagen: AnlagenSelektorEintrag[]
  selectedId: number | undefined
  onSelect: (id: number) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Klick außerhalb schließt (Bestands-Muster aus TopNavigation)
  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  // Entscheidung (Gernot 2026-06-20): bei < 2 Anlagen ausblenden.
  if (anlagen.length < 2) return null

  const selected = anlagen.find((a) => a.id === selectedId)

  return (
    <div ref={ref} className="relative w-full lg:w-auto">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="min-h-[44px] w-full lg:w-auto flex items-center justify-between lg:justify-start gap-2 px-3 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-700 transition-colors"
      >
        <Home className="h-4 w-4 shrink-0 text-gray-400 dark:text-gray-500" />
        <span className="truncate lg:max-w-[12rem]">{selected?.anlagenname ?? 'Anlage wählen'}</span>
        <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <ul
          role="listbox"
          aria-label="Anlage wählen"
          className="absolute left-0 right-0 lg:right-auto mt-2 lg:min-w-[16rem] bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-2 z-50 max-h-[calc(100vh-5rem)] overflow-y-auto"
        >
          {anlagen.map((a) => {
            const aktiv = a.id === selectedId
            return (
              <li key={a.id} role="option" aria-selected={aktiv}>
                <button
                  type="button"
                  onClick={() => {
                    onSelect(a.id)
                    setOpen(false)
                  }}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors ${
                    aktiv
                      ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                      : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                  }`}
                >
                  <Check className={`h-4 w-4 shrink-0 ${aktiv ? 'opacity-100' : 'opacity-0'}`} />
                  <span className="truncate">{a.anlagenname}</span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
