/**
 * FokusFehltOverlay — die Degradation des Fokus-Deep-Links (FD-5).
 *
 * Ein `#/…?fokus=<id>` kann ins Leere zeigen: die ID ist unbekannt oder
 * veraltet, der Block gibt es an diesem Tag nicht (Lücken-Tag), die Kachel ist
 * geparkt oder hat keine Daten. Dann steht **dieses** Overlay da statt der
 * nackten Sicht — eine Webseiten-Karte im HA-Dashboard soll sagen, was los ist,
 * und nicht klaglos etwas anderes zeigen als bestellt.
 *
 * Es ist bewusst EINE Komponente für beide Fundstellen ({@link BlockShell} und
 * die Live-Sicht): zwei Formulierungen desselben Falls wären zwei Wahrheiten
 * (Regel 0a).
 *
 * ⛔ **Ohne Schließen-Satz und ohne „zur Sicht"-Knopf.** In der Deep-Link-Ansicht
 * gibt es keinen Ausweg — sie IST die ganze Karte. Der Bestandssatz des
 * Lücken-Tags („… oder schließe die Vollansicht") gilt nur im normalen Betrieb,
 * wo das „Zurück" tatsächlich existiert.
 */
import type { ReactNode } from 'react'
import { FokusVollbild } from './FokusVollbild'

export function FokusFehltOverlay({ fokusId, kopf, mitZeitraum = false }: {
  /** Die angefragte, nicht auflösbare ID — sie ist zugleich der Titel: wer die
   *  Karte gebaut hat, soll sehen, welche Adresse er korrigieren muss. */
  fokusId: string
  /** Zeitraum-Nav der Sicht; läuft mit, damit man sich zu einem Zeitraum MIT
   *  Daten blättern kann — kommt der Block zurück, rendert er (FD-5 Fall 2). */
  kopf?: ReactNode
  /** true, wenn die Sicht einen Zeitraum hat (Cockpit) — dann ist „nicht für
   *  diesen Zeitraum" eine mögliche Ursache. Auf der Live-Sicht nicht. */
  mitZeitraum?: boolean
}) {
  return (
    <FokusVollbild titel={fokusId} kopf={kopf} deepLink onClose={() => {}}>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Die Anzeige „{fokusId}" gibt es in dieser Sicht nicht (mehr)
        {mitZeitraum ? ' oder nicht für diesen Zeitraum' : ''}.
      </p>
    </FokusVollbild>
  )
}

export default FokusFehltOverlay
