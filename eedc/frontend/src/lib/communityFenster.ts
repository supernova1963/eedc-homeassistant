/**
 * Das Vergleichsfenster des Community-Benchmarks — eine Regel, ein Text.
 *
 * **Anlass: #387 (azywietz-web, 19.08.2026).** Der Community-Server rechnete
 * Teiljahres-Daten auf zwoelf Monate hoch (`Summe ÷ Monate × 12`) und stellte
 * sie neben echte Jahreswerte. Eine 2-kWp-Anlage mit sechs Sommermonaten stand
 * damit auf Rang 3 von 112 — ihre Summe von 636,8 kWh/kWp wurde als 1.273,6
 * ausgewiesen. Seitdem gilt serverseitig: **ein spezifischer Jahresertrag
 * entsteht nur aus zwoelf lueckenlosen Kalendermonaten**, der laufende Monat
 * zaehlt nie mit. Wer die nicht hat, bekommt **keinen Wert und keinen Rang**.
 *
 * Damit koennen `spez_ertrag_anlage`, `rang_gesamt` und ihre Nachbarn `null`
 * sein. Diese Datei haelt die eine Stelle, an der entschieden wird, ob ein
 * Jahresvergleich ueberhaupt gezeigt werden darf, und **wie das Fehlen
 * begruendet wird** — statt an sechs Stellen ein „—" ohne Erklaerung.
 *
 * Was **nicht** betroffen ist: alle **monatlichen** Vergleiche. Sie waren
 * schon immer periodenrichtig und bleiben sichtbar, auch im ersten Jahr.
 */

import type { BenchmarkData } from '../api/community'

const MONATSNAMEN = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
]

/** Hat die Anlage einen belastbaren Jahreswert? */
export function hatJahresfenster(b: BenchmarkData | null | undefined): boolean {
  return !!b && b.spez_ertrag_anlage !== null && b.spez_ertrag_anlage !== undefined
}

/**
 * Warum es keinen Jahreswert gibt — als fertiger Satz, oder `null`, wenn es
 * einen gibt. Bewusst ohne Zusage: „mit dem ersten vollen Jahr", kein Termin.
 */
export function jahresfensterHinweis(b: BenchmarkData | null | undefined): string | null {
  if (!b || hatJahresfenster(b)) return null

  const fenster = b.fenster_monate ?? 12
  if (b.basis_veraltet) {
    return `Deine jüngsten geteilten Daten sind älter als ein Jahr. Der Jahresvergleich `
      + `braucht ${fenster} zusammenhängende Monate, die bis in die letzten zwölf Monate reichen — `
      + `teile deine Daten erneut, dann ist er wieder da.`
  }

  const basis = b.basis_monate ?? 0
  if (basis === 0) {
    return `Für den Jahresvergleich fehlen noch abgeschlossene Monate. `
      + `Er zeigt sich, sobald ${fenster} zusammenhängende Kalendermonate geteilt sind.`
  }
  return `Der Jahresvergleich braucht ${fenster} zusammenhängende Kalendermonate — `
    + `davon liegen ${basis} vor. Der laufende Monat zählt nicht mit, er ist noch nicht zu Ende. `
    + `Die monatlichen Vergleiche unten gelten unabhängig davon.`
}

/** „Stand August 2026" — das Fenster endet je Anlage verschieden. */
export function jahresfensterStand(b: BenchmarkData | null | undefined): string | null {
  if (!b || !b.basis_bis_jahr || !b.basis_bis_monat) return null
  return `Stand ${MONATSNAMEN[b.basis_bis_monat - 1]} ${b.basis_bis_jahr}`
}
