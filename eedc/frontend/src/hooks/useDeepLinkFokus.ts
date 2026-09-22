/**
 * useDeepLinkFokus — liest den Fokus-Deep-Link aus der Adresse (FD-1).
 *
 * Vertrag (KONZEPT-FOKUS-DEEPLINK §1):
 * ```
 * #/<sicht-pfad>?fokus=<block-id>[&ansicht=tabelle]
 * ```
 * `fokus` öffnet beim Laden genau diese Anzeige im Fokus/Vollbild — als
 * **Deep-Link-Ansicht**: ohne Zurück-Knopf, ESC ohne Wirkung, Park read-only,
 * System-Theme. Gedacht für die Webseiten-Karte eines HA-Dashboards.
 *
 * ⛔ **Der Parameter ist ein Eingang, kein Spiegel des Zustands.** Das ⤢ im
 * normalen Betrieb schreibt die Adresse NICHT, und das Schließen ändert sie
 * nicht — der Fokus bleibt lokaler State wie bisher. Darum steht hier kein
 * `useSearchParams`/`setSearchParams`: Eine Sicht, die ihre eigenen Parameter
 * neu setzt (`datum`, `jahr`, `monat`, `h`), darf die Deep-Link-Ansicht nicht
 * umwerfen, und unbekannte Parameter bleiben unangetastet.
 *
 * ⚠ **Instanz-Memo, kein Modul-Memo.** Gelesen wird je **Mount des Aufrufers**
 * einmal (`useState`-Initialisierer). Ein Modul-Memo wäre falsch: Unter
 * `HashRouter` ist ein Hash-Wechsel same-document, die Sicht mountet dabei neu,
 * das Modul aber nicht — die zweite Karte im selben Dokument bekäme den Fokus
 * der ersten. Umgekehrt ändert ein Hash-Wechsel OHNE Remount den Wert bewusst
 * nicht (es gibt keinen Zuhörer): der Deep-Link ist ein Startzustand.
 *
 * ⚠ Gelesen wird `window.location.hash`, nicht der Router — unter `HashRouter`
 * steht die Query des Deep-Links im Hash, und der Hook läuft auch außerhalb
 * eines Routers (Kacheln in Vorschauen, Proben ohne `MemoryRouter`).
 */
import { useState } from 'react'

export interface DeepLinkFokus {
  /** Gewünschte Fokus-ID aus `?fokus=` — `null`, wenn kein Deep-Link vorliegt. */
  fokusId: string | null
  /** Start-Ablesung des Overlays (`?ansicht=tabelle`), sonst `chart` (CT-5). */
  ansicht: 'chart' | 'tabelle'
  /** true ⇒ Deep-Link-Ansicht (kein Zurück, kein ESC, Park read-only). */
  deepLink: boolean
}

/** Query-Teil eines Hash-Pfads (`#/cockpit/jahr?fokus=bilanz` → `fokus=bilanz`). */
export function leseDeepLinkFokus(hash: string): DeepLinkFokus {
  const frage = hash.indexOf('?')
  const params = new URLSearchParams(frage >= 0 ? hash.slice(frage + 1) : '')
  const roh = params.get('fokus')?.trim()
  const fokusId = roh ? roh : null
  return {
    fokusId,
    // Nur `tabelle` wird angenommen; jeder andere Wert (auch `chart`) fällt auf
    // die Chart-Ablesung zurück — dasselbe Muster wie `?h=` in der Aussicht.
    ansicht: params.get('ansicht') === 'tabelle' ? 'tabelle' : 'chart',
    deepLink: fokusId !== null,
  }
}

export function useDeepLinkFokus(): DeepLinkFokus {
  const [wert] = useState<DeepLinkFokus>(() =>
    leseDeepLinkFokus(typeof window === 'undefined' ? '' : window.location.hash),
  )
  return wert
}

export default useDeepLinkFokus
