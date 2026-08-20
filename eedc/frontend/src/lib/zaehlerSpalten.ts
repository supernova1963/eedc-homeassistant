/**
 * Spalten je Verbrauchszähler für die Werte-Tabellen (#377).
 *
 * Gebaut nach dem Muster von {@link baueErzeugerSpalten} (#350) nebenan: die
 * Spalten hängen an der **Anlage**, nicht am Produkt, und werden deshalb zur
 * Laufzeit erzeugt statt in `WERTE_METRIKEN` zu stehen.
 *
 * ⚑ **Warum je Gerät und nicht eine Sammelspalte:** Jede Metrik der Registry
 * ist eine **Fluss**größe (kWh, km, €) und summiert sich über Geräte und Zeit.
 * Ein Zählerstand ist eine **Bestands**größe und summiert sich über nichts —
 * zwei Gaszähler mit 12.345 und 8.900 ergeben nicht 21.245. Damit erledigt sich
 * auch die Frage nach gemischten Einheiten in einer Spalte: jede Spalte trägt
 * die Einheit ihres Geräts.
 *
 * ⚠ **Anders als bei den Erzeugern gibt es keine Mindestanzahl.** Dort war die
 * Regel „ab zwei Geräten", weil bei einem einzigen die Gerätespalte dieselbe
 * wäre wie die PV-Spalte. Ein Zählerstand hat kein solches Gegenstück in der
 * Tabelle — auch ein einzelner Gaszähler bringt eine Spalte, die es sonst
 * nirgends gibt.
 */

import { istZaehlerKategorie } from './fieldDefinitions'
import { PARAM_SONSTIGES_DEFAULTS } from './investitionParameter'
import { zaehlerMetriken, type WerteMetrik } from './werte'
import type { Investition } from '../types'

/** Alle Zähler-Geräte einer Investitionsliste, in stabiler Reihenfolge. */
export function zaehlerInvestitionen(investitionen: Investition[]): Investition[] {
  return investitionen
    .filter((inv) => inv.typ === 'sonstiges')
    .filter((inv) => istZaehlerKategorie(
      (inv.parameter as Record<string, unknown> | null | undefined)?.kategorie as string,
    ))
    .sort((a, b) => a.bezeichnung.localeCompare(b.bezeichnung, 'de-DE'))
}

/**
 * Spalten je Zähler.
 *
 * `staendeVorhanden` sind die IDs, für die im geladenen Zeitraum überhaupt ein
 * Stand vorliegt. Wer nie abgelesen wurde, bekommt keine Spalte — sie bestünde
 * sonst aus lauter „—" und behauptete, es gäbe dort etwas zu sehen.
 */
export function baueZaehlerSpalten(
  investitionen: Investition[],
  staendeVorhanden: Set<string>,
): WerteMetrik[] {
  const zaehler = zaehlerInvestitionen(investitionen)
    .filter((inv) => staendeVorhanden.has(String(inv.id)))
  return zaehlerMetriken(zaehler.map((inv) => ({
    id: inv.id,
    name: inv.bezeichnung,
    einheit: String(
      (inv.parameter as Record<string, unknown> | null | undefined)?.zaehler_einheit
      ?? PARAM_SONSTIGES_DEFAULTS.zaehler_einheit,
    ),
  })))
}

/** IDs mit mindestens einem Stand in den geladenen Zeilen. */
export function zaehlerMitStand(
  rows: Array<{ zaehler_stand?: Record<string, number> | null }>,
): Set<string> {
  const ids = new Set<string>()
  for (const r of rows) {
    for (const [id, wert] of Object.entries(r.zaehler_stand ?? {})) {
      if (wert != null) ids.add(id)
    }
  }
  return ids
}
