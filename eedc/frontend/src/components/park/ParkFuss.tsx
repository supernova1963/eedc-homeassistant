/**
 * ParkFuss — Sicht-Fußzeile der Element-Park-Ebene: dezente Hinweiszeile
 * (Discoverability der versteckten Geste, Gernot-Abnahme 2026-06-25) + der
 * {@link GeparktBlock} („Geparkt (n)"). Eine Komponente pro v4-Sicht ans Ende.
 *
 * Inert ohne ParkProvider (`!aktiv`) → rendert nichts (Produktion/v3).
 *
 * `bereit={false}` hält ihn zurück, solange die Sicht noch lädt (N-385, rapahl per PN
 * am 03.09.2026). Grund: Der Park-Zustand kommt SYNCHRON aus `localStorage`
 * (`ParkContext`, `useState(() => laden(...))`), der Seiteninhalt asynchron. In den fünf
 * Cockpit-Sichten steht der Skeleton INLINE in einem Ternär und `<ParkFuss />` daneben —
 * der Parkplatz stand dort für 0,5–1 s neben dem Ladezeichen und rutschte danach an
 * seinen Platz. Das liest sich, als werde der Inhalt überschrieben.
 *
 * ⭐ Zweite Runde: dieselbe Sache wurde am 13.08.2026 für den Börsenpreis-Block gelöst
 * (`CockpitLiveV4.tsx`, `!loading`) — derselbe Melder, dieselbe Seite. Der Fix saß dort an
 * EINEM Block; hier sitzt er an der Fußzeile, die alle Sichten teilen.
 *
 * ⛔ KEIN Skeleton als Platzhalter: die Höhe des Energieflusses müsste geraten werden —
 * das ist die Begründung, die im Börsenpreis-Kommentar schon steht.
 *
 * ⛔ Default `true`: die dreizehn Sichten, die bei `loading` früh zurückkehren, erreichen
 * diese Zeile während des Ladens gar nicht und dürfen unverändert bleiben.
 *
 * SoT: docs/drafts/archive/flip-v4/SPEC-ELEMENT-LAYOUT-PAPIERKORB.md
 */
import { MousePointerClick } from 'lucide-react'
import { usePark } from './ParkContext'
import { GeparktBlock } from './GeparktBlock'

export function ParkFuss(
  { hinweis = true, bereit = true }: { hinweis?: boolean; bereit?: boolean } = {},
) {
  const park = usePark()
  if (!park.aktiv) return null
  // N-385: solange die Sicht lädt, steht hier nichts — weder Parkplatz noch Tipp.
  // Vor `park.parkbareAnzahl` geprüft, weil die Registrierung der Parkbar-Elemente
  // selbst erst mit dem Inhalt kommt.
  if (!bereit) return null
  // R17-5: Der Discoverability-Hinweis erscheint NUR, wenn die Sicht überhaupt
  // parkbare Elemente hat (z. B. reine Einstellungs-Sichten haben keine → kein
  // irreführender „lange drücken"-Tipp). Der GeparktBlock versteckt sich separat,
  // wenn nichts geparkt ist.
  // R17-5-Nachzug (Gernot 2026-07-09): `hinweis={false}` unterdrückt den Tipp ganz —
  // die Einstellungs-Sicht hat zwar EIN parkbares Element (Solar-Prognose), der Tipp
  // wirkt dort aber trotzdem fehl am Platz. Der GeparktBlock (Entparken) bleibt.
  const zeigeHinweis = hinweis && park.parkbareAnzahl > 0
  return (
    <div className="space-y-3">
      <GeparktBlock />
      {zeigeHinweis && (
        <p className="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1.5 px-1">
          <MousePointerClick className="h-3 w-3 flex-shrink-0" />
          <span>
            {/* N-390: „oben" gehört seit dem 04.09. dazu — auf dem Telefon greift
                die Geste nur noch in der Kopf-Zone, damit sie den Tooltip im Körper
                nicht mehr zudeckt. Der Klammerzusatz trägt bewusst KEINE Ortsangabe:
                per Rechtsklick gilt weiterhin die ganze Fläche. */}
            Tipp: eine Anzeige oben lange drücken (oder rechtsklicken) → auf den Parkplatz.
          </span>
        </p>
      )}
    </div>
  )
}
