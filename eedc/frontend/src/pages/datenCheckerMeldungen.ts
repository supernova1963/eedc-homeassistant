/**
 * Daten-Checker — Rückmeldungs-Texte der Reparatur-Aktionen (reines Modul).
 *
 * Getrennt von `DatenCheckerTeile.tsx`, damit die Entscheidung „Erfolg /
 * Hinweis / Fehler" ohne Komponenten-Mount prüfbar bleibt (gleiches Muster wie
 * `baueTagKpis`) und die Seite kein react-refresh-Treffer wird.
 */
import type { ReaggregateBereichResponse } from '../api/energie_profil'

export type MeldungsArt = 'ok' | 'hinweis' | 'fehler'

export interface ReparaturMeldung {
  art: MeldungsArt
  text: string
}

/**
 * Baut die Rückmeldung zum Bereichs-Lauf aus den TATSÄCHLICHEN Zählern.
 *
 * `status: "ok"` heißt nur „durchgelaufen". Bis 2026-07-30 meldete die Seite
 * unbedingt Erfolg — auch bei `erfolgreich: 0, keine_daten: 11` (E2E gemessen
 * an der lokalen Box). `aggregate_day` liefert `None`, wenn es für den Tag
 * keine Kurvendaten findet; der Endpoint antwortet dann trotzdem mit HTTP 200.
 * Ein Knopf, der nichts geholt hat, darf das nicht als Erfolg ausgeben —
 * sonst sucht der Anwender den Fehler bei sich.
 */
export function baueBereichsMeldung(
  r: Partial<ReaggregateBereichResponse>,
  von: string,
  bis: string,
): ReparaturMeldung {
  const ok = r.erfolgreich ?? 0
  const leer = r.keine_daten ?? 0
  const kaputt = r.fehlgeschlagen ?? 0
  const fehlerTeil = kaputt > 0 ? `, ${kaputt} mit Fehler` : ''

  if (ok === 0 && (leer > 0 || kaputt > 0)) {
    return {
      art: 'hinweis',
      text:
        `Zeitraum ${von} bis ${bis}: kein Tag konnte nachgerechnet werden ` +
        `(${leer} ohne verwertbare Daten${fehlerTeil}). Häufigste Ursache: für ` +
        `diese Anlage ist kein Leistungssensor zugeordnet, oder die ` +
        `Home-Assistant-Historie reicht nicht so weit zurück. Der Zählerstand ` +
        `allein genügt dem Tages-Lauf nicht.`,
    }
  }
  if (leer > 0 || kaputt > 0) {
    return {
      art: 'hinweis',
      text:
        `Zeitraum ${von} bis ${bis}: ${ok} Tag(e) neu aus HA-Statistics ` +
        `aggregiert, ${leer} ohne verwertbare Daten übersprungen${fehlerTeil}.`,
    }
  }
  return {
    art: 'ok',
    text: `Zeitraum ${von} bis ${bis}: ${ok} Tag(e) neu aus HA-Statistics aggregiert.`,
  }
}
