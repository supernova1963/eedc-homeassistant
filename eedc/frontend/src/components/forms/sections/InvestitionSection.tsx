import type { ElementType } from 'react'
import { Check } from 'lucide-react'
import type { Investition } from '../../../types'
import type { FeldStatus } from '../../../api/monatsabschluss'
import type { SonstigePosition } from './types'
import { SonstigePositionenFields } from '../SonstigePositionenFields'
import { readFeldWert, type FeldDefinition } from '../../../lib/fieldDefinitions'
import { fmtZahl } from '../../../lib/einheiten'
import { ermittleZustand, rollupBadge } from '../../../lib/erfassungZustand'
import { FormSection, ErfassungZustandBadge, InlineAktion } from '../../ui'
import AssistenzFeld from '../AssistenzFeld'

interface InvestitionSectionProps {
  title: string
  icon: ElementType
  iconColor: string
  investitionen: Investition[]
  investitionsDaten: Record<string, Record<string, string>>
  onInvChange: (invId: number, field: string, value: string) => void
  /** Statische Felder (für alle Investitionen gleich) */
  felder?: FeldDefinition[]
  /** Dynamische Felder pro Investition (hat Vorrang vor felder) */
  felderFn?: (inv: Investition) => FeldDefinition[]
  sonstigePositionen: Record<string, SonstigePosition[]>
  onPositionenChange: (invId: number, positionen: SonstigePosition[]) => void
  /** Optionaler Hinweistext unter dem Titel */
  hinweisFn?: (inv: Investition) => string | null
  /** Optionale Zusatzinfo pro Investition (z.B. leistung_kwp) */
  subtitleFn?: (inv: Investition) => string | null
  /** Monatsabschluss-V4: Backend-FeldStatus je (invId, feld) für die Ampel-Zustände. */
  feldStatus?: (invId: number, feld: string) => FeldStatus | undefined
  /** Monatsschlüssel — wechselt beim Statusladen, damit die Auto-Einklapp-Defaults greifen. */
  statusMonthKey?: string
  /** Ist das Feld (invId, feld) vom Nutzer als „geprüft" bestätigt? */
  istBestaetigt?: (invId: number, feld: string) => boolean
  /** Ein oder mehrere Felder einer Investition als geprüft markieren. */
  onBestaetigen?: (invId: number, felder: string[]) => void
}

/**
 * Rekursive Ampel-Blöcke (Monatsabschluss-V4 §6.7): Typ-Sektion (primär, gerahmt) mit
 * Rollup über ihre Geräte-Einträge (flach, untergeordnet). Feld-Badge + „✓ passt"
 * erscheinen NUR an Aufmerksamkeits-Feldern (geschätzt/weicht-ab/offen) — ruhige
 * Felder bleiben badge-frei (Gernot 2026-07-12). Grün klappt beim Laden zu.
 */
export function InvestitionSection({
  title, icon: Icon, iconColor, investitionen, investitionsDaten, onInvChange,
  felder, felderFn, sonstigePositionen, onPositionenChange, hinweisFn, subtitleFn,
  feldStatus, statusMonthKey = 'x', istBestaetigt, onBestaetigen,
}: InvestitionSectionProps) {
  if (investitionen.length === 0) return null

  const eintraege = investitionen.map((inv) => {
    const aktiveFelder = felderFn ? felderFn(inv) : (felder ?? [])
    const daten = investitionsDaten[inv.id] ?? {}
    const felderMitZustand = aktiveFelder.map((f) => {
      const wert = readFeldWert(daten, f.feld)
      const fs = feldStatus?.(inv.id, f.feld)
      const bestaetigt = istBestaetigt?.(inv.id, f.feld) ?? false
      return { f, wert, fs, bestaetigt, zustand: ermittleZustand(wert, fs, bestaetigt).zustand }
    })
    // Rollup über alle Feld-Zustände; `optional` blendet der Rollup selbst aus.
    return { inv, daten, felderMitZustand, zustaende: felderMitZustand.map((x) => x.zustand) }
  })

  const typBadge = rollupBadge(eintraege.flatMap((e) => e.zustaende))

  return (
    <div data-erfassung-offen={typBadge.zustand === 'fehlt' ? 'true' : undefined}>
    <FormSection
      key={`typ-${title}-${statusMonthKey}-${typBadge.zustand === 'gemessen' ? 'zu' : 'auf'}`}
      variant="erweitert"
      ebene="typ"
      title={title}
      icon={Icon}
      iconColor={iconColor}
      defaultOpen={typBadge.zustand !== 'gemessen'}
      statusSlot={<ErfassungZustandBadge zustand={typBadge.zustand} label={typBadge.label} />}
    >
      <div className="space-y-1">
        {eintraege.map(({ inv, felderMitZustand, zustaende }) => {
          const eb = rollupBadge(zustaende)
          const subtitle = subtitleFn?.(inv)
          const hinweis = hinweisFn?.(inv)
          const zuPruefen = felderMitZustand.filter((x) => x.zustand === 'geschaetzt').map((x) => x.f.feld)
          return (
            <FormSection
              key={`inv-${inv.id}-${statusMonthKey}-${eb.zustand === 'gemessen' ? 'zu' : 'auf'}`}
              variant="erweitert"
              ebene="geraet"
              defaultOpen={eb.zustand !== 'gemessen'}
              title={
                <>
                  {inv.bezeichnung}
                  {subtitle && <span className="text-xs text-gray-500 ml-2">({subtitle})</span>}
                </>
              }
              statusSlot={<ErfassungZustandBadge zustand={eb.zustand} label={eb.label} />}
            >
              {hinweis && <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">{hinweis}</p>}
              {/* Eintrags-Schnellweg: alle Schätzungen dieses Geräts als geprüft bestätigen. */}
              {zuPruefen.length > 1 && onBestaetigen && (
                <InlineAktion ton="bestaetigen" className="mb-2" onClick={() => onBestaetigen(inv.id, zuPruefen)}>
                  <Check className="w-3 h-3" /> alle {zuPruefen.length} Schätzungen bestätigen
                </InlineAktion>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-x-3 gap-y-2 items-start">
                {felderMitZustand.map(({ f, wert, fs, bestaetigt }) => (
                  <AssistenzFeld
                    key={f.feld}
                    nurBeiAufmerksamkeit
                    label={f.einheit ? `${f.label} (${f.einheit})` : f.label}
                    name={`inv-${inv.id}-${f.feld}`}
                    value={wert}
                    onChange={(v) => onInvChange(inv.id, f.feld, v)}
                    feldStatus={fs}
                    min="0"
                    placeholder={f.placeholder}
                    hint={f.hint}
                    bestaetigt={bestaetigt}
                    onBestaetigen={onBestaetigen ? () => onBestaetigen(inv.id, [f.feld]) : undefined}
                  />
                ))}
              </div>
              {/* #407: Stand → Menge. Für jedes Stand-Feld mit `differenzZiel` die
                  Rechnung live zeigen — Anfang = `stand_vormonat` aus dem Status. */}
              {felderMitZustand.filter((x) => x.f.differenzZiel).map(({ f, wert, fs }) => {
                const ziel = f.differenzZiel as string
                const zielFeld = felderMitZustand.find((x) => x.f.feld === ziel)
                if (!zielFeld || wert == null || String(wert).trim() === '') return null
                const stand = parseFloat(String(wert).replace(',', '.'))
                if (!Number.isFinite(stand)) return null
                const anfang = fs?.stand_vormonat ?? null
                const einheit = f.einheit
                if (anfang == null) {
                  return (
                    <p key={`stand-${f.feld}`} className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                      Erster {f.label} — {zielFeld.f.label} trägst du diesen Monat noch selbst ein;
                      ab dem nächsten rechnet eedc die Differenz.
                    </p>
                  )
                }
                const diff = Math.round(stand - anfang)
                if (diff < 0) {
                  return (
                    <p key={`stand-${f.feld}`} className="text-xs text-amber-600 dark:text-amber-400 mt-2">
                      {f.label} liegt unter dem des Vormonats ({fmtZahl(anfang, 0)} {einheit}) —
                      ein Zähler läuft nicht rückwärts. Ist das Gerät gewechselt, beginnt die Reihe hier neu.
                    </p>
                  )
                }
                const zielWert = parseFloat(String(zielFeld.wert ?? '').replace(',', '.'))
                const uebernommen = Number.isFinite(zielWert) && Math.round(zielWert) === diff
                return (
                  <p key={`stand-${f.feld}`} className="text-xs text-gray-600 dark:text-gray-300 mt-2 flex flex-wrap items-center gap-x-2">
                    <span>
                      Aus {f.label}: {fmtZahl(stand, 0)} − {fmtZahl(anfang, 0)} (Vormonat) ={' '}
                      <span className="font-semibold">{fmtZahl(diff, 0)} {einheit}</span>
                    </span>
                    {uebernommen ? (
                      <span className="text-gray-400">· übernommen</span>
                    ) : (
                      <InlineAktion ton="bestaetigen" onClick={() => onInvChange(inv.id, ziel, String(diff))}>
                        <Check className="w-3 h-3" /> als {zielFeld.f.label} übernehmen
                      </InlineAktion>
                    )}
                  </p>
                )
              })}
              <SonstigePositionenFields
                invId={inv.id}
                positionen={sonstigePositionen[String(inv.id)] || []}
                onChange={(pos) => onPositionenChange(inv.id, pos)}
              />
            </FormSection>
          )
        })}
      </div>
    </FormSection>
    </div>
  )
}
