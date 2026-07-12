/**
 * investitionAktiv — Frontend-Spiegel des Backend-SoT `Investition.ist_aktiv_im_monat`
 * (`backend/models/investition.py`). Beantwortet: war eine Investition in einem
 * gegebenen Kalendermonat (teilweise) in Betrieb?
 *
 * Wird gebraucht, damit Erfassungs-/Bearbeitungsformulare (Monatsabschluss-V4) NUR
 * die im gewählten Monat tatsächlich betriebenen Geräte anzeigen und in die
 * Vollständigkeits-Prüfung einbeziehen — Anschaffungs-/Stilllegungsdatum ist die
 * limitierende Grenze für ALLE Auswertungen ([[feedback_anschaffungsdatum_grenze]]),
 * die 3-Achsen-Semantik aktiv/stillgelegt/nicht-vorhanden ([[feedback_aktiv_inaktiv_semantik]]).
 *
 * Semantik 1:1 aus dem Backend (`ist_aktiv_im_zeitraum`):
 * - `aktiv === false` → nirgends anzeigen, auch nicht historisch (wie gelöscht).
 * - `anschaffungsdatum > Monatsende`  → noch nicht angeschafft → raus.
 * - `stilllegungsdatum < Monatsanfang` → schon stillgelegt → raus.
 * - Anschaffungs-/Stilllegungsmonat zählen als teil-aktiv MIT.
 * - `aktiv` undefined/null (frisch, nicht persistiert) gilt als aktiv (nur `=== false` blendet aus).
 */

export interface AktivPruefbar {
  aktiv?: boolean | null
  anschaffungsdatum?: string | null
  stilllegungsdatum?: string | null
}

/** Letzter Tag des Monats (28–31) — mirror `calendar.monthrange`. */
function letzterTag(jahr: number, monat: number): number {
  // Tag 0 des Folgemonats = letzter Tag des aktuellen Monats.
  return new Date(jahr, monat, 0).getDate()
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`
}

/**
 * True, wenn `inv` im Kalendermonat (jahr, monat) (teilweise) aktiv war.
 * Vergleich über ISO-Datumsstrings 'YYYY-MM-DD' (lexikografisch = chronologisch),
 * keine Zeitzonen-Umrechnung.
 */
export function istAktivImMonat(
  inv: AktivPruefbar,
  jahr: number,
  monat: number,
): boolean {
  if (!Number.isFinite(jahr) || !Number.isFinite(monat) || monat < 1 || monat > 12) {
    // Ohne validen Monat keine Fenster-Aussage → nur das aktiv-Flag entscheidet.
    return inv.aktiv !== false
  }
  if (inv.aktiv === false) return false
  const monatsStart = `${jahr}-${pad2(monat)}-01`
  const monatsEnde = `${jahr}-${pad2(monat)}-${pad2(letzterTag(jahr, monat))}`
  // Nur den Datums-Anteil vergleichen (robust gegen evtl. Zeit-Suffix).
  const anschaffung = inv.anschaffungsdatum?.slice(0, 10)
  const stilllegung = inv.stilllegungsdatum?.slice(0, 10)
  if (anschaffung && anschaffung > monatsEnde) return false
  if (stilllegung && stilllegung < monatsStart) return false
  return true
}
