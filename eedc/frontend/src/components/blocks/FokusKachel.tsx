/**
 * FokusKachel — Karte mit Fokus/Vollbild-Schalter (⤢), ohne Block-Stack-Beiwerk
 * (kein Einklappen/Sortieren). Für IST-treue Sicht-Layouts wie Cockpit/Live, die
 * NICHT die {@link BlockShell} nutzen, aber dieselbe Fokus-Affordanz haben sollen
 * (Gernot 2026-06-22: durchgängig je Karte). Nutzt dasselbe {@link FokusVollbild}
 * wie die BlockShell → ein Fokus-Verhalten app-weit (Regel 0a).
 *
 * Der Karten-Titel erscheint per Default NUR im Vollbild-Header; im Normalzustand
 * trägt der Inhalt meist seine eigene Überschrift (`zeigeTitel` aktiviert ihn
 * zusätzlich in der Kopfzeile der Karte).
 */
import { useState, type ReactNode } from 'react'
import { Maximize2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { FokusVollbild } from './FokusVollbild'
import { useDeepLinkFokus } from '../../hooks/useDeepLinkFokus'
import { EinbettenKnopf } from './EinbettenKnopf'

export function FokusKachel({ titel, fokusId, icon: Icon, farbe, className = '', zeigeTitel = false, tabelle, aktionen, children }: {
  titel: string
  /** FD-1: Adresse dieser Kachel im Fokus-Deep-Link (`#/…?fokus=<fokusId>`).
   *  **Pflicht**, damit TypeScript jeden Aufrufer zwingt — eine Kachel ohne
   *  Adresse wäre die einzige Anzeige mit ⤢, die niemand verlinken kann.
   *  ⚠ Die IDs der parkbaren Kacheln sind **dieselbe Zeichenkette** wie ihre
   *  Park-ID (`live:wetter-heute` …), aber eine ANDERE Ebene: der Park räumt
   *  weg, der Deep-Link zeigt her. Zusammengelegt, weil zwei Namen für
   *  dieselbe Kachel niemandem helfen. */
  fokusId: string
  icon?: LucideIcon
  farbe?: string
  className?: string
  /** Titel auch in der Karten-Kopfzeile zeigen (sonst nur im Vollbild). */
  zeigeTitel?: boolean
  /** Paket CT: Tabellen-Ablesung des Karten-Charts — durchgereicht ans
   *  {@link FokusVollbild} (Chart-⇄-Tabelle-Umschalter nur dort). */
  tabelle?: ReactNode
  /** Zusatz-Aktionen in der Vollbild-Kopfzeile. Ohne Angabe steht dort der
   *  Einbetten-Knopf (FD-2) — jede fokussierbare Kachel ist verlinkbar. */
  aktionen?: ReactNode | ((ansicht: 'chart' | 'tabelle') => ReactNode)
  children: ReactNode
}) {
  const [fokusState, setFokus] = useState(false)
  // FD-1: Im Deep-Link-Modus entscheidet die Adresse, nicht das ⤢ — und zwar
  // JE RENDER abgeleitet, nicht als Initialisierer (eine Kachel kann erst mit
  // dem zweiten Abruf erscheinen). Ohne `?fokus=` bleibt alles wie bisher.
  const deep = useDeepLinkFokus()
  const fokus = deep.deepLink ? deep.fokusId === fokusId : fokusState
  return (
    <>
      {fokus && (
        <FokusVollbild
          titel={titel} icon={Icon} farbe={farbe} tabelle={tabelle}
          aktionen={aktionen ?? ((ansicht) => <EinbettenKnopf fokusId={fokusId} ansicht={ansicht} />)}
          deepLink={deep.deepLink}
          ansichtStart={deep.deepLink ? deep.ansicht : 'chart'}
          onClose={() => setFokus(false)}
        >
          {children}
        </FokusVollbild>
      )}
      {/* C1/S11 (Flip v4.0.0): auf den Block-Standard rounded-xl/shadow-sm angeglichen.
          D18-3 (detlan #210): Innenpolsterung auf die Gliederungsebene (12 px = p-3)
          statt p-4 sm:p-6 — Charts in Live-Kacheln bekommen denselben Seitenrand
          wie Charts im BlockShell-Body (px-3), keine Doppel-/Überpolsterung. */}
      <div className={`relative bg-white dark:bg-gray-800 rounded-xl shadow-sm p-3 ${className}`}>
        {/* ⤢ sitzt absolut oben rechts — in der Titelzeile, keine eigene Leerzeile.
            (Energiefluss bringt sein ⤢ über `kopfAktion` selbst mit.)
            D14-16 (Gernot-Entscheid): unter 640 px ausgeblendet, NICHT entfernt —
            „die paar Pixel" bringen dort nichts, Desktop-/Breitbild-Nutzen bleibt. */}
        {/* In der Deep-Link-Ansicht gibt es nichts zu vergrößern: das Overlay
            IST die Karte, und es hat keinen Weg zurück. */}
        {!deep.deepLink && (
          <button
            type="button"
            onClick={() => setFokus(true)}
            aria-label={`${titel}: Fokus / Vollbild`}
            className="max-sm:hidden absolute top-2 right-2 z-10 p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700/50"
          >
            <Maximize2 className="h-4 w-4" />
          </button>
        )}
        {zeigeTitel && (
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 pr-8 flex items-center gap-2">
            {Icon && <Icon className={`h-4 w-4 ${farbe ?? 'text-gray-400 dark:text-gray-500'}`} />}
            {titel}
          </h3>
        )}
        {/* Inhalt liegt im Fokus im Overlay → hier nicht doppelt rendern. */}
        {!fokus && children}
      </div>
    </>
  )
}
