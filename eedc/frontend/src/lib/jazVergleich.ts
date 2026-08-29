/**
 * SoT für den Community-JAZ-Vergleich einer Wärmepumpe (N-350).
 *
 * **Das Problem, das er löst.** Der Server liefert ZWEI Vergleichswerte für dieselbe
 * Kennzahl: `jaz` ist der Schnitt über **alle** Wärmepumpen-Arten,
 * `jaz_typ` der über Anlagen **derselben** Art
 * (`eedc-community/backend/api/benchmark.py:698-704` — zweimal
 * `berechne_community_avg_jaz`, einmal mit und einmal ohne `wp_art`).
 * Welcher davon gezeigt wird, stand bis zum 29.08.2026 an **zwei** Stellen inline in
 * `CommunityUebersichtTeile.tsx` — und an einer dritten (`CommunityKomponentenTeile.tsx`)
 * gar nicht: die Komponenten-Seite las `wp.jaz` und zeigte deshalb für dieselbe Anlage
 * eine **andere** Prozent-Abweichung als die Übersicht.
 *
 * ⛔ **Die Regel war schon zweimal gebaut worden** — `e36758b7` (Issue #85) und
 * `3717c7c0`, beide Male ausschließlich in `UebersichtTab.tsx`. Die Komponenten-Seite
 * entstand später im V4-Umbau (`de423238`) und hat sie nie geerbt. Genau dagegen steht
 * dieser eine Ort.
 *
 * ⭐ **Warum Vergleich und Beschriftung aus EINER Entscheidung kommen.** Vorher hing das
 * Art-Suffix an `wp.wp_art`, nicht daran, ob `jaz_typ` tatsächlich verwendet wurde. Fehlt
 * `jaz_typ` (zu wenige Anlagen derselben Art), stand „JAZ · Luft/Wasser" über einem
 * Vergleich gegen **alle** Arten — die Beschriftung behauptete eine Bezugsgruppe, gegen
 * die nicht gerechnet wurde. Deshalb gibt es hier nur den einen Rückgabewert, aus dem
 * beides folgt.
 */
import { WP_ART_LABELS } from './constants'
import type { KPIVergleich, WaermepumpeBenchmark } from '../api/community'

export interface JazVergleichAnzeige {
  /** Der anzuzeigende Vergleich — art-spezifisch, wenn vorhanden, sonst der Gesamtschnitt. */
  kpi: KPIVergleich | null
  /**
   * `true`, wenn `kpi` gegen Anlagen **derselben** Wärmepumpen-Art vergleicht.
   * Nur dann darf die Art an der Zahl genannt werden.
   */
  artSpezifisch: boolean
  /**
   * Klartext-Art (z. B. `'Luft/Wasser'`) — **nur gesetzt, wenn `artSpezifisch`**.
   * Quelle ist `WP_ART_LABELS` (SoT, `lib/constants.ts`); die früheren Inline-Ketten
   * kannten vier der fünf Arten und ließen `brauchwasser` ohne Label durchfallen,
   * obwohl der Server ihn als gültigen `wp_art` führt.
   */
  artLabel: string | null
}

/**
 * Entscheidet, welcher Community-Vergleich für die JAZ gezeigt wird — und ob dabei
 * die Wärmepumpen-Art genannt werden darf.
 *
 * @param wp        Der Wärmepumpen-Block aus dem Benchmark (darf fehlen).
 * @param wpArtFallback `anlage.wp_art` — greift, wenn der Block selbst keine Art trägt.
 */
export function jazVergleichAnzeige(
  wp: WaermepumpeBenchmark | null | undefined,
  wpArtFallback?: string | null,
): JazVergleichAnzeige {
  const leer: JazVergleichAnzeige = { kpi: null, artSpezifisch: false, artLabel: null }
  if (!wp) return leer

  // Ein Vergleich zählt nur mit `community_avg` — ohne ihn hat die Kachel nichts
  // zu vergleichen und fiele auf die reine Wertanzeige zurück.
  const artSpezifisch = wp.jaz_typ?.community_avg != null
  const kpi = artSpezifisch ? wp.jaz_typ! : (wp.jaz ?? null)
  if (!kpi) return leer

  const art = wp.wp_art ?? wpArtFallback
  return {
    kpi,
    artSpezifisch,
    // Bewusst nur bei `artSpezifisch`: sonst benennt das Label eine Bezugsgruppe,
    // gegen die gar nicht gerechnet wurde.
    artLabel: artSpezifisch && art ? (WP_ART_LABELS[art] ?? art) : null,
  }
}
