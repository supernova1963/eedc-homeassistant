/**
 * InlineAktion — DER SoT-Baustein für schlanke Inline-Aktionen/Disclosures.
 *
 * Fülllt die Lücke zwischen „nur Text" und dem vollen {@link Button} (der bewusst
 * `min-h-[36px]` erzwingt und für 11-px-Inline-Affordanzen zu schwer ist): kleine
 * Textlinks, Aufklapp-Schalter (▾) und Bestätigungs-Chips, die INLINE in dichten
 * Zeilen leben (Erfassungs-Assistenz, Kopf-Ampel, Legende, Review). Eine
 * Komponenten-Klasse für diese Gattung (Regel 0a: keine SoT vorhanden, aber
 * sinnvoll → Zentrale erweitern), statt roher `<button>` verstreut in den Formularen.
 *
 * Rohes `<button>` ist hier die SoT-Implementierung (wie bei Button/DatumPicker) —
 * per `check:v4-migration`-ROH_INFRA freigegeben, nicht Migrationsschuld.
 *
 * Farbe/Töne ausschließlich über Tailwind-Rollen bzw. `ERFASSUNG_ZUSTAND` (colors.ts,
 * `check:design`) — keine Inline-Hex.
 */
import type { ReactNode, MouseEventHandler } from 'react'
import { ERFASSUNG_ZUSTAND } from '../../lib/colors'

/** Farbrolle der Aktion (nur `variant="link"`). */
export type InlineTon = 'neutral' | 'aktion' | 'bestaetigen' | 'offen' | 'warnung' | 'hinweis'

const TON: Record<InlineTon, string> = {
  // muted: Aufklapper/„andere Quelle", Legende
  neutral: 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200',
  // primärer Sprung-Link („zum Feld")
  aktion: 'text-primary-600 hover:underline dark:text-primary-400',
  // Bestätigen („✓ passt", „alle N bestätigen")
  bestaetigen: 'text-green-600 hover:text-green-700 dark:text-green-400 dark:hover:text-green-300',
  // „n offen" — dieselbe Farb-Achse wie der Zustand „offen" (Vokabular-SoT)
  offen: `${ERFASSUNG_ZUSTAND.fehlt.text} hover:underline`,
  // Abweichungs-Kontext („Sensorwert übernehmen") — Orange wie die Zeile
  warnung: 'text-orange-600 dark:text-orange-400',
  // „Fehlt noch — anlegen"-Aufforderung (z. B. Komponenten-Akte) — dieselbe
  // Amber-Achse wie Stepper/Setup-Gate (Button `amber`).
  hinweis: 'text-amber-500 hover:text-amber-400 dark:text-amber-400 dark:hover:text-amber-300',
}

const CHIP =
  'rounded border border-gray-200 dark:border-gray-700 px-1.5 py-0.5 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
/** Chip im Auswahl-Zustand (Mehrfach-Auswahl-Pillen, z. B. Spalten-Picker). */
const CHIP_AKTIV =
  'rounded border border-primary-500 bg-primary-500 px-1.5 py-0.5 text-white hover:bg-primary-600'

interface InlineAktionProps {
  onClick: MouseEventHandler<HTMLButtonElement>
  children: ReactNode
  /** Farbrolle (nur `variant="link"`). Default `neutral`. */
  ton?: InlineTon
  /** Form: schlanker Textlink (Default) oder umrandeter Auswahl-Chip. */
  variant?: 'link' | 'chip'
  /** Auswahl-Zustand (nur `variant="chip"`): gewählt = primary-gefüllt. */
  aktiv?: boolean
  /** Textgröße: `xs` = 11 px (Default), `sm` = passt sich einer text-sm-Zeile an (Kopf-Ampel). */
  groesse?: 'xs' | 'sm'
  /** Dauerhaft unterstrichen (Hover hebt auf) — für „übernehmen"-Aktionen. */
  unterstrichen?: boolean
  /** Disclosure-Zustand für Aufklapper (setzt `aria-expanded`). */
  ariaExpanded?: boolean
  /** Aktion gesperrt (z. B. während eines laufenden Vorgangs). */
  disabled?: boolean
  title?: string
  className?: string
}

export default function InlineAktion({
  onClick,
  children,
  ton = 'neutral',
  variant = 'link',
  aktiv = false,
  groesse = 'xs',
  unterstrichen = false,
  ariaExpanded,
  disabled = false,
  title,
  className = '',
}: InlineAktionProps) {
  const base = 'inline-flex items-center gap-1 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded-sm'
  const size = groesse === 'sm' ? 'text-sm' : 'text-[11px]'
  const look = variant === 'chip'
    ? (aktiv ? CHIP_AKTIV : CHIP)
    : `${TON[ton]}${unterstrichen ? ' underline hover:no-underline' : ''}`
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={ariaExpanded}
      disabled={disabled}
      title={title}
      className={`${base} ${size} ${look} disabled:opacity-30 disabled:cursor-not-allowed ${className}`.trim()}
    >
      {children}
    </button>
  )
}
