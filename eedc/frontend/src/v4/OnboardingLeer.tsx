/**
 * OnboardingLeer — B8-Leerzustände mit CTA (R3b S15, 2026-07-05).
 *
 * Klasse (a) „Anlage fehlt" ({@link AnlageLeer}) und Klasse (b) „Daten fehlen
 * komplett" ({@link DatenLeer} bzw. generisch): EmptyState-SoT in Card, der
 * IST-Text bleibt als title erhalten, der CTA führt auf die zuständige
 * Einstellungs-Kategorie (kein Wizard-Deep-Link — existiert nicht, s.
 * VERIFIKATION-S15). Klasse (c) — Blätter-Lücken („Keine Daten für diesen Tag")
 * und Block-Innen-Kontexte — bleibt bewusst die kleine graue Card.
 */
import { ArrowRight, Database, Sun } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Card, EmptyState, buttonClasses } from '../components/ui'

export function OnboardingLeer({ icon, titel, beschreibung, ctaHref, ctaLabel }: {
  icon: LucideIcon
  /** IST-Text der Stelle — unverändert übernehmen (Restrukturierung ≠ Neudesign). */
  titel: string
  beschreibung: string
  ctaHref: string
  ctaLabel: string
}) {
  return (
    <Card>
      <EmptyState
        icon={icon}
        title={titel}
        description={beschreibung}
        action={
          <a href={ctaHref} className={buttonClasses({ variant: 'primary', size: 'sm', className: 'gap-1.5' })}>
            {ctaLabel} <ArrowRight className="h-4 w-4" />
          </a>
        }
      />
    </Card>
  )
}

/** Klasse (a): „Noch keine Anlage angelegt/gewählt" → CTA Stammdaten. */
export function AnlageLeer({ titel }: { titel: string }) {
  return (
    <OnboardingLeer
      icon={Sun}
      titel={titel}
      beschreibung="Lege deine Anlage unter Einstellungen → Stammdaten an — die Sichten füllen sich dann automatisch."
      ctaHref="#/einstellungen/stammdaten"
      ctaLabel="Anlage anlegen"
    />
  )
}

/** Klasse (b): „Noch keine …daten erfasst" → CTA Daten-Reiter (Import/Erfassung). */
export function DatenLeer({ titel }: { titel: string }) {
  return (
    <OnboardingLeer
      icon={Database}
      titel={titel}
      beschreibung="Importiere Statistik-Daten aus Home Assistant oder erfasse Monatswerte unter Einstellungen → Daten."
      ctaHref="#/einstellungen/daten"
      ctaLabel="Daten importieren"
    />
  )
}
