/**
 * ErfassungZustandBadge — kleines Zustands-Etikett für die Herkunft eines Werts.
 *
 * DIE eine Zustands-Anzeige (Feld-Badge) für das Vokabular gemessen/geschätzt/
 * fehlt/weicht-ab (Konzept `KONZEPT-MONATSABSCHLUSS-V4.md` §5). Farb-/Tönungs-SoT
 * kommt aus `ERFASSUNG_ZUSTAND` (lib/colors.ts) — keine Inline-Farben. Icon + Label
 * liegen zentral in {@link ZUSTAND_META}, damit Kopf-Ampel und Monatsdaten-Tabelle
 * (spätere Bündel) dieselbe Icon-/Text-Quelle nutzen — kein zweiter Satz.
 *
 * Zwei Gebrauchslagen, gleiches Vokabular, unterschiedliche Lautstärke:
 *  • **Monatsabschluss-Erfassung** (Feld-Badges, Kopf-Ampel): voller Pill —
 *    `geschaetzt` gelb heißt dort „prüfen", also ein Handlungsauftrag.
 *  • **Anzeige-Herkunft in Blöcken/Charts** (`WertHerkunft`, z. B. PV je Modul
 *    nach kWp gerechnet): bewusst `iconOnly` + Erklärsatz daneben. Dort ist
 *    „geschätzt" eine Eigenschaft der Anzeige, kein Auftrag — ein halb gelber
 *    Block wäre ein Fehlsignal.
 *
 * Modelliert nach `QuelleBadge` (gleiches Pill-Muster, hell/dunkel), keine zweite
 * Badge-Art (Regel 0a; [[feedback_kpicard_drei_versionen]]).
 */

import { CheckCircle2, BadgeCheck, AlertTriangle, Circle, CircleDashed, AlertCircle, type LucideIcon } from 'lucide-react'
import { ERFASSUNG_ZUSTAND } from '../../lib/colors'

/**
 * Erfassungs-Zustände (aus `FeldStatus.quelle` + Vergleich + Bestätigung abgeleitet).
 * 6 Labels auf 4 Farb-Achsen (Gernot 2026-07-12): grün = fertig (gemessen | geprüft),
 * gelb = prüfen (geschätzt), orange = weicht ab, grau = offen; „optional" = leises Grau
 * für quellenlose Leerfelder (zählt nicht).
 */
export type ErfassungZustand = 'gemessen' | 'geprueft' | 'geschaetzt' | 'weicht_ab' | 'fehlt' | 'optional'

/** Zentrale Icon-/Label-Quelle je Zustand — von Badge, Kopf-Ampel und Tabelle geteilt. */
export const ZUSTAND_META: Record<ErfassungZustand, { label: string; Icon: LucideIcon }> = {
  gemessen:   { label: 'gemessen',  Icon: CheckCircle2 },  // automatisch (Sensor/Import)
  geprueft:   { label: 'geprüft',   Icon: BadgeCheck },    // von dir eingegeben/bestätigt
  geschaetzt: { label: 'geschätzt', Icon: AlertTriangle }, // Schätzung → „prüfen"
  weicht_ab:  { label: 'weicht ab', Icon: AlertCircle },
  fehlt:      { label: 'offen',     Icon: Circle },
  optional:   { label: 'optional',  Icon: CircleDashed },
}

interface ErfassungZustandBadgeProps {
  zustand: ErfassungZustand
  /** Optionaler Quell-Zusatz, z. B. „Vorjahr" bei geschätzt (getQuelleLabel). */
  quelleLabel?: string
  /** Überschreibt den Standard-Zustandstext (z. B. Rollup „alles gemessen" / „1 offen"). */
  label?: string
  /** Nur Icon (für dichte Sektions-Köpfe/Tabellenzellen), ohne Text-Pill. */
  iconOnly?: boolean
  className?: string
}

export default function ErfassungZustandBadge({
  zustand,
  quelleLabel,
  label: labelOverride,
  iconOnly = false,
  className = '',
}: ErfassungZustandBadgeProps) {
  const { label: defaultLabel, Icon } = ZUSTAND_META[zustand]
  const label = labelOverride ?? defaultLabel
  const farbe = ERFASSUNG_ZUSTAND[zustand]
  const text = quelleLabel ? `${label} (${quelleLabel})` : label

  if (iconOnly) {
    return (
      <Icon
        className={`w-4 h-4 ${farbe.text} ${className}`}
        aria-label={text}
        role="img"
      />
    )
  }

  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] leading-tight px-1.5 py-0.5 rounded font-medium ${farbe.badge} ${className}`}
    >
      <Icon className="w-3 h-3 flex-shrink-0" aria-hidden="true" />
      {text}
    </span>
  )
}
