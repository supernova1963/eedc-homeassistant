/**
 * ZeitraumHinweis — sichtbares Zeitraum-Kennzeichen für Auswertungen-Blöcke,
 * deren Datenbezug vom Jahr-Filter der Steuerleiste abweicht (R18-3, Option B):
 * Blöcke, die dem Filter nicht folgen KÖNNEN (CO₂-Amortisation gegen die graue
 * Last der Gesamt-Historie, Prognose ④/⑤ mit eigenen Tage-Fenstern), und Blöcke,
 * die bei „Alle Jahre" nur ein Einzeljahr abbilden (PVGIS-Jahres-SOLL/IST,
 * T-Konto). Vorher zeigten diese Blöcke STILL etwas anderes als der Kopf
 * behauptete — genau die drei Fehlanzeigen R18-3a/b/c.
 *
 * EINE Zentrale für alle Sub-Sichten (Regel 0a Fall 2) — kein ad-hoc-Hinweistext
 * je Block. CalendarClock ist bewusst KEIN Status-Icon (B17/A5): der Hinweis ist
 * eine neutrale Einordnung, keine Warnung.
 */
import { CalendarClock } from 'lucide-react'

export function ZeitraumHinweis({ text }: { text: string }) {
  return (
    <p className="flex items-start gap-1.5 text-xs text-gray-500 dark:text-gray-400">
      <CalendarClock className="h-3.5 w-3.5 shrink-0 mt-px" aria-hidden="true" />
      <span>{text}</span>
    </p>
  )
}
