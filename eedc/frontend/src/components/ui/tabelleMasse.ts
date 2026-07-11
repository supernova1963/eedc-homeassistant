/**
 * Tabellen-SoT — Maße und Zell-Typo (Regel T, `docs/drafts/KONZEPT-TABELLEN-SOT.md`).
 *
 * Eigene Datei, weil `Table.tsx` nur Komponenten exportieren darf (react-refresh).
 * Werte sind auf der Dev-Box gemessen (Playwright, 2026-07-10); ändern sie sich,
 * müssen ZELLE/KOPF_ZELLE und das Konzept gemeinsam nachgezogen werden.
 */

/** Startwerte für den ersten Frame + Tests. Die WIRKLICHE Fensterhöhe misst
 *  `Table` zur Laufzeit aus dem DOM (Köpfe sind mal ein-, mal zweizeilig).
 *  Zeile = line-height(text-sm 20) + 2×py-0.5(2) + 1px Border = 25 */
export const ZEILE_PX = 25
export const KOPF_PX = 21
export const FUSS_PX = 25

/** Deckel — Basis-Bildschirmgröße ist **FullHD** (Gernot 2026-07-10).
 *  Er greift nur als Notbremse; die Fensterhöhe kommt aus der DOM-Messung. */
export const DECKEL = '85dvh'

/** T6 — eine Zell-Typo. Zahlen zusätzlich `text-right tabular-nums` am Aufrufer.
 *
 *  `py-0.5` (nicht py-1/py-1.5): Unter dem Blockkopf bleiben auf FullHD ~715 px.
 *  Die Stundentabelle hat einen ZWEIZEILIGEN Kopf (~44 px) + Summenzeile:
 *    py-1.5 → Zeile 33 px → 24 Std = 865 px  (‑150 zu viel)
 *    py-1   → Zeile 29 px → 24 Std = 769 px  (‑54 zu viel)
 *    py-0.5 → Zeile 25 px → 24 Std = 673 px  ✓
 *  Die Schriftgröße bleibt `text-sm` (14 px, lesbar) — verkleinert wird NUR das
 *  vertikale Padding. 12 Monatszeilen brauchen damit 350 px. */
export const ZELLE = 'px-3 py-0.5 text-sm whitespace-nowrap'
/** Kopfzelle bewusst OHNE `uppercase`/`tracking-wider`: die Alt-Version von
 *  `ui/Table` trug das, hatte aber null Nutzer — beide echten Tabellen haben es
 *  sofort überschrieben. Wer Versalien will, ergänzt sie am Aufrufer. */
export const KOPF_ZELLE = 'px-3 py-0.5 text-xs font-medium whitespace-nowrap'

/** Summenzeile: eigener, deckender Grund + Abgrenzung — auf den ZELLEN (s. TableHead). */
export const FUSS_GRUND =
  'border-t-2 border-gray-300 dark:border-gray-600 font-semibold ' +
  '[&_th]:bg-gray-50 [&_td]:bg-gray-50 dark:[&_th]:bg-gray-700 dark:[&_td]:bg-gray-700'

/** Flächenfarbe des Containers — bestimmt Fade UND den Grund der klebenden
 *  Kopf-/Fußzeile. `zellGrund` malt auf th/td, nicht auf thead/tr: ein
 *  `background` auf dem Sektions-Element wird beim Sticky nicht gemalt, die
 *  Datenzeilen schienen durch (Dev-Box 2026-07-10; jsdom fängt das nicht). */
export type Flaeche = 'karte' | 'seite'
export const FLAECHE: Record<Flaeche, { fade: string; zellGrund: string }> = {
  karte: {
    fade: 'from-white dark:from-gray-800',
    zellGrund: '[&_th]:bg-white [&_td]:bg-white dark:[&_th]:bg-gray-800 dark:[&_td]:bg-gray-800',
  },
  seite: {
    fade: 'from-gray-50 dark:from-gray-900',
    zellGrund: '[&_th]:bg-gray-50 [&_td]:bg-gray-50 dark:[&_th]:bg-gray-900 dark:[&_td]:bg-gray-900',
  },
}

/** Fensterhöhe nach T2. */
export function fensterHoehe(zeilen: number, mitFuss: boolean): string {
  const px = zeilen * ZEILE_PX + KOPF_PX + (mitFuss ? FUSS_PX : 0)
  return `min(${px}px, ${DECKEL})`
}
