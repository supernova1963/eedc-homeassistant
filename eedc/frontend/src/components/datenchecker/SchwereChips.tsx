/**
 * SchwereChips — die Zählung eines Daten-Checker-Kopfs als Chips (Etappe E5, Mockup): «2 Fehler · 6 Warnungen ·
 * 4 Hinweise · 17 bestanden». Eine Komponente für den Kopf des Checkers und jeden Kategorie-Kopf; Farben der
 * Schwere-Achse (`SEVERITY_CONFIG`), Chip-Form nach Style-Guide B17. Null-Zählungen fehlen.
 */
type Zaehlung = Partial<Record<'error' | 'warning' | 'info' | 'ok', number>>

const CHIPS: { schwere: keyof Zaehlung; eins: string; mehr: string; klasse: string }[] = [
  { schwere: 'error', eins: 'Fehler', mehr: 'Fehler',
    klasse: 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300' },
  { schwere: 'warning', eins: 'Warnung', mehr: 'Warnungen',
    klasse: 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300' },
  { schwere: 'info', eins: 'Hinweis', mehr: 'Hinweise',
    klasse: 'bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300' },
  { schwere: 'ok', eins: 'bestanden', mehr: 'bestanden',
    klasse: 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300' },
]

export default function SchwereChips({ zaehlung }: { zaehlung: Zaehlung }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {CHIPS.filter((c) => (zaehlung[c.schwere] ?? 0) > 0).map((c) => {
        const n = zaehlung[c.schwere] ?? 0
        return (
          <span key={c.schwere} className={`rounded-full px-2 py-0.5 text-xs ${c.klasse}`}>
            {n} {n === 1 ? c.eins : c.mehr}
          </span>
        )
      })}
    </span>
  )
}
