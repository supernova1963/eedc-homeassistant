/**
 * useDeepLinkFokus — liest den Fokus-Deep-Link aus der Adresse (FD-1).
 *
 * Vertrag (KONZEPT-FOKUS-DEEPLINK §1):
 * ```
 * #/<sicht-pfad>?fokus=<block-id>[&ansicht=tabelle][&geraet=<investition_id>]
 * ```
 * `fokus` öffnet beim Laden genau diese Anzeige im Fokus/Vollbild — als
 * **Deep-Link-Ansicht**: ohne Zurück-Knopf, ESC ohne Wirkung, Park read-only,
 * System-Theme. Gedacht für die Webseiten-Karte eines HA-Dashboards.
 *
 * `geraet` (Nachlauf 4.2.1 N5, Entscheid Gernot 2.11.2026) wählt auf einer
 * Typ-Seite mit mehreren Geräten (`#/komponenten/<typ>`) das Gerät mit dieser
 * Investitions-ID — sonst zeigte eine Dashboard-Karte immer das erste. Nur eine
 * ganze Zahl > 0 gilt, alles andere ist `null`; eine ID, die es auf der Seite
 * nicht gibt, fällt dort still auf das erste Gerät zurück. Der Einbetten-Knopf
 * schreibt den Parameter nur bei ≥ 2 Geräten des Typs.
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
  /** Gewähltes Gerät aus `?geraet=` (N5) — ganze Zahl > 0, sonst `null`. */
  geraetId: number | null
}

/** `?geraet=` als Investitions-ID: nur Ziffern, Wert > 0 — `0`, `abc`, `3.5`, `-2` und fehlend ⇒ `null`. */
function leseGeraetId(roh: string | null): number | null {
  const t = roh?.trim() ?? ''
  if (!/^\d+$/.test(t)) return null
  const id = Number(t)
  return Number.isSafeInteger(id) && id > 0 ? id : null
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
    geraetId: leseGeraetId(params.get('geraet')),
  }
}

export function useDeepLinkFokus(): DeepLinkFokus {
  const [wert] = useState<DeepLinkFokus>(() =>
    leseDeepLinkFokus(typeof window === 'undefined' ? '' : window.location.hash),
  )
  return wert
}

export default useDeepLinkFokus
