/**
 * Beschriftung einer Stunde als **Bereich** — HA-Bauform S4 (Entscheid S4-E2 A, Gernot 16.10.2026).
 *
 * Die Antwort sagt je Zeile, was `stunde` meint (`raster`, Backend
 * `core/berechnungen/slot_konvention.py`):
 *
 * * `"beginn"` — ein **Kanal-Tag** (HAs Statistik-Zeile, Grundsatz „eine Stunde
 *   ist ihr Beginn"): Stunde `h` = `[h, h+1)` ⇒ `11` heißt „11–12".
 * * `"ende"` — ein **Bestandstag** (Backward-Slot #144): Stunde `h` = `[h−1, h)`
 *   ⇒ `11` heißt „10–11", Slot 0 „23–24" (die letzte Stunde des Vortags).
 *
 * Damit zeigen beide Tagesarten dieselbe, ehrliche Form — `h:00` hätte zwischen
 * zwei Tagen stumm die Bedeutung gewechselt. Live (`stundenSlot.ts`,
 * `CockpitLiveV4`) und der Prognose-Vergleich bleiben bei ihrer eigenen Achse.
 */
export type StundenRaster = 'beginn' | 'ende'

/** `"11–12"` für Stunde 11 im Beginn-Raster, `"10–11"` im Ende-Raster. */
export function stundenBereich(h: number, raster: StundenRaster = 'ende'): string {
  const beginn = raster === 'beginn' ? ((h % 24) + 24) % 24 : (((h - 1) % 24) + 24) % 24
  return `${beginn}–${beginn + 1}`
}
