/**
 * Vergleichs-Auflösung der Werte-Tabelle — die EINE Regel, nach der eine Zeile
 * ihre Vergleichszeile findet. Tabelle (`WerteTabelle`), CSV-Export und
 * Summenzeile teilen sie sich; zwei Kopien derselben Regel waren genau der Weg,
 * auf dem Tabelle und Export auseinanderlaufen konnten.
 *
 * Gematcht wird über {@link WerteZeile.vergleichKey} — ein gemeinsamer
 * Schlüsselraum beider Seiten (s. Doku dort), NICHT über die Reihenfolge der
 * Zeilen.
 */
import type { WerteZeile } from './zeile'

/** Vergleichszeile je Schlüssel. Fehlt der Schlüssel, gibt es kein Vorjahr. */
export function vergleichLookup(vergleichsZeilen: WerteZeile[] | null): Map<number, WerteZeile> {
  const m = new Map<number, WerteZeile>()
  if (vergleichsZeilen) for (const z of vergleichsZeilen) m.set(z.vergleichKey, z)
  return m
}

/** Die Vergleichszeilen, die wirklich einer **angezeigten** Zeile gegenüberstehen. */
export function gepaarteVergleichsZeilen(
  rows: WerteZeile[],
  vergleichsZeilen: WerteZeile[] | null,
): WerteZeile[] {
  if (!vergleichsZeilen) return []
  const lookup = vergleichLookup(vergleichsZeilen)
  const out: WerteZeile[] = []
  for (const r of rows) {
    const p = lookup.get(r.vergleichKey)
    if (p) out.push(p)
  }
  return out
}

/**
 * Grundgesamtheit der **Summenzeile** — oder `null`, wenn der Fuß keinen Vergleich
 * behaupten darf.
 *
 * Die „aktuell"-Zelle des Fußes ist die Summe der Spalte darüber, also **aller**
 * angezeigten Zeilen; daran darf sich nichts ändern, sonst stimmt die Tabelle mit
 * sich selbst nicht überein. Die Vergleichs-Zelle kann das nur einhalten, wenn
 * jede dieser Zeilen auch ein Gegenstück hat. Hat sie es nicht, stünde dort eine
 * Summe über eine andere Zeitspanne — bei „Alle Jahre" 37 Monate gegen 25, im
 * laufenden Jahr 6 Monate gegen die vollen 12 des Vorjahrs. Beides läse sich als
 * Aussage über die Anlage und wäre keine. Dann lieber `—`: die Δ-Werte der
 * einzelnen Zeilen stehen ja vollständig darüber.
 */
export function vergleichsAggregatBasis(
  rows: WerteZeile[],
  vergleichsZeilen: WerteZeile[] | null,
): WerteZeile[] | null {
  if (!vergleichsZeilen) return null
  const paare = gepaarteVergleichsZeilen(rows, vergleichsZeilen)
  return paare.length === rows.length ? paare : null
}
