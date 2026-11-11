/**
 * befundZeilen — die Zeilen einer Befund-Liste (Etappe E5, Konzept §6 V1/V2): Befunde mit gleicher Gruppe
 * (`gruppe.schluessel`, Backend `gruppen.py`) stehen als **eine** Gruppenzeile an der Stelle ihres ersten Glieds; OK-Zeilen
 * stehen nicht in der Liste (V1 — der Kategorie-Kopf zählt sie). Reine Ordnung der Antwort, keine Rechnung.
 */
import type { CheckErgebnis } from '../../api/datenChecker'

export type BefundZeile =
  | { art: 'einzel'; befund: CheckErgebnis }
  | { art: 'gruppe'; schluessel: string; glieder: CheckErgebnis[] }

export function befundZeilen(ergebnisse: CheckErgebnis[]): BefundZeile[] {
  const zeilen: BefundZeile[] = []
  const gruppen = new Map<string, CheckErgebnis[]>()
  for (const e of ergebnisse) {
    if (e.schwere === 'ok') continue
    const s = e.gruppe?.schluessel
    if (!s) {
      zeilen.push({ art: 'einzel', befund: e })
      continue
    }
    const glieder = gruppen.get(s)
    if (glieder) {
      glieder.push(e)
    } else {
      const neu = [e]
      gruppen.set(s, neu)
      zeilen.push({ art: 'gruppe', schluessel: s, glieder: neu })
    }
  }
  return zeilen
}

/** K1 (Konzept §7): eine Kategorie steht offen, wenn sie einen Fehler, eine Warnung oder eine Aktion trägt. */
export function kategorieOffen(ergebnisse: CheckErgebnis[]): boolean {
  return ergebnisse.some((e) => e.schwere === 'error' || e.schwere === 'warning' || !!e.action)
}
