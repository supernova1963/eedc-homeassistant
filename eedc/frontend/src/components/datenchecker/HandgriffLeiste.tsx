/**
 * HandgriffLeiste — «Das kannst du jetzt tun» (Etappe E5, Konzept §7 K2, Mockup): alle Befunde mit einer **Aktion** über
 * alle Kategorien oben im Daten-Checker, jede Zeile mit demselben Handgriff (`BefundHandgriff` bzw. `BefundGruppe`,
 * Vorschau-Kasten), die Kategorie vor dem Lösungsweg-Link. Ohne Aktion keine Leiste. Handy: volle Breite, der Knopf
 * unter dem Text (die Zeile stapelt unterhalb `sm`).
 */
import type { CheckErgebnis } from '../../api/datenChecker'
import { KATEGORIE_LABELS } from '../../config/datenCheckerKategorien'
import BefundGruppe from './BefundGruppe'
import BefundHandgriff, { type HandgriffProps } from './BefundHandgriff'
import { befundZeilen } from './befundZeilen'

export default function HandgriffLeiste({ ergebnisse, ...handgriff }: HandgriffProps & { ergebnisse: CheckErgebnis[] }) {
  const zeilen = befundZeilen(ergebnisse.filter((e) => !!e.action))
  if (zeilen.length === 0) return null
  return (
    <section aria-label="Das kannst du jetzt tun" data-testid="handgriff-leiste"
      className="rounded-lg border border-primary-200 dark:border-primary-800 bg-primary-50/40 dark:bg-primary-900/10">
      <div className="flex flex-wrap items-baseline gap-x-3 px-4 pt-3">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Das kannst du jetzt tun</h3>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {zeilen.length} {zeilen.length === 1 ? 'Handgriff' : 'Handgriffe'} aus allen Kategorien
        </span>
      </div>
      <div className="divide-y divide-gray-100 dark:divide-gray-800">
        {zeilen.map((z) => {
          const kontext = KATEGORIE_LABELS[(z.art === 'einzel' ? z.befund : z.glieder[0]).kategorie]
          return z.art === 'einzel'
            ? <BefundHandgriff key={`${z.befund.code}-${z.befund.meldung}`} befund={z.befund} kontext={kontext} {...handgriff} />
            : <BefundGruppe key={z.schluessel} glieder={z.glieder} kontext={kontext} {...handgriff} />
        })}
      </div>
    </section>
  )
}
