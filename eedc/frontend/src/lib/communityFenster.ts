/**
 * Das Vergleichsfenster des Community-Benchmarks — eine Regel, ein Text.
 *
 * **Anlass: #387 (azywietz-web, 19.08.2026).** Der Community-Server rechnete
 * Teiljahres-Daten flach auf zwoelf Monate hoch (`Summe ÷ Monate × 12`) und
 * stellte sie neben echte Jahreswerte. Eine 2-kWp-Anlage mit sechs
 * Sommermonaten stand damit auf Rang 3 von 112 — ihre Summe von 636,8 kWh/kWp
 * wurde als 1.273,6 ausgewiesen.
 *
 * **Was daraus wurde — und warum diese Datei zwei Server-Staende kennen muss.**
 * Ein Teiljahr wird weiterhin hochgerechnet, aber **saisonal**: mit der
 * Ertragserwartung des eigenen Standorts als Massstab statt mit dem Faktor
 * zwoelf. Ein Fruehling zaehlt dann als Fruehling. Die Umstellung passiert am
 * **01.09.2026** in einem eigenen Server-Deploy — der Client wird dabei
 * **nicht** angefasst. Deshalb muss diese Datei ab v4.0.22 beides koennen:
 *
 * - **bis zum 01.09.:** Der Server rechnet flach und sendet `basis_monate`
 *   nicht. Es gibt immer einen Wert, also keine Kennzeichnung und keinen
 *   Hinweis — die Anzeige bleibt, wie sie war.
 * - **ab dem 01.09.:** Der Server sendet `basis_monate`. Liegt es unter zwoelf,
 *   ist der Jahreswert **hochgerechnet** und muss das sagen
 *   ({@link jahresfensterKennzeichnung}) — eine Zahl, die aus fuenf Monaten
 *   entsteht, darf nicht aussehen wie eine aus zwoelf.
 *
 * ⛔ **Was hier bis zum 19.08.2026 stand, galt nie:** „Wer die zwoelf Monate
 * nicht hat, bekommt keinen Wert und keinen Rang." Diese Fassung wurde vom
 * Maintainer abgelehnt, bevor sie ausgeliefert wurde — *„wer < 12 Monate kein
 * Vergleich ist denkbar unguenstig"*. Ein Anwender ohne volles Jahr bekommt
 * einen Wert; er erfaehrt nur, worauf er beruht.
 *
 * {@link jahresfensterHinweis} bleibt fuer den einen Fall, in dem es wirklich
 * keinen Jahreswert gibt: Die geteilten Daten sind aelter als ein Jahr.
 *
 * Was **nicht** betroffen ist: alle **monatlichen** Vergleiche. Sie waren schon
 * immer periodenrichtig und bleiben sichtbar, auch im ersten Jahr.
 */

import type { BenchmarkData } from '../api/community'

const MONATSNAMEN = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
]

/** Hat die Anlage einen Jahreswert? */
export function hatJahresfenster(b: BenchmarkData | null | undefined): boolean {
  return !!b && b.spez_ertrag_anlage !== null && b.spez_ertrag_anlage !== undefined
}

/**
 * Beruht der Jahreswert auf weniger als zwoelf Monaten? Dann sagt er das.
 *
 * `null`, wenn es nichts zu kennzeichnen gibt — auch dann, wenn der Server
 * `basis_monate` gar nicht sendet (so bis zum 01.09.2026). Die Kennzeichnung
 * erscheint damit von selbst, sobald der Server umgestellt ist; der Client
 * braucht dafuer kein Update.
 *
 * Bewusst **neben** dem Wert und nicht statt seiner: Ein hochgerechneter Wert
 * ist eine Aussage, nur eben eine mit duennerer Grundlage — dieselbe Haltung
 * wie bei `anzahl_wirkungsgrad` im Speicher-Vergleich.
 */
export function jahresfensterKennzeichnung(b: BenchmarkData | null | undefined): string | null {
  if (!b || !hatJahresfenster(b)) return null
  const basis = b.basis_monate
  const fenster = b.fenster_monate ?? 12
  if (basis == null || basis <= 0 || basis >= fenster) return null
  return `hochgerechnet aus ${basis} von ${fenster} Monaten`
}

/**
 * Warum es **gar keinen** Jahreswert gibt — als fertiger Satz, oder `null`.
 *
 * Nach der Umstellung bleibt dafuer ein einziger Grund: die geteilten Daten
 * sind aelter als ein Jahr. Wer zu wenige Monate hat, bekommt einen
 * hochgerechneten Wert samt {@link jahresfensterKennzeichnung} — keinen
 * leeren Platz. Bewusst ohne Zusage: kein Termin.
 */
export function jahresfensterHinweis(b: BenchmarkData | null | undefined): string | null {
  if (!b || hatJahresfenster(b)) return null

  if (b.basis_veraltet) {
    return `Deine jüngsten geteilten Daten sind älter als ein Jahr. Teile sie erneut, `
      + `dann ist der Jahresvergleich wieder da.`
  }
  return `Für den Jahresvergleich fehlen noch abgeschlossene Monate. `
    + `Die monatlichen Vergleiche unten gelten unabhängig davon.`
}

/** „Stand August 2026" — das Fenster endet je Anlage verschieden. */
export function jahresfensterStand(b: BenchmarkData | null | undefined): string | null {
  if (!b || !b.basis_bis_jahr || !b.basis_bis_monat) return null
  return `Stand ${MONATSNAMEN[b.basis_bis_monat - 1]} ${b.basis_bis_jahr}`
}
