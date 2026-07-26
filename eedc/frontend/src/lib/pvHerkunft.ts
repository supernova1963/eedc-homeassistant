/**
 * Wortlaut-SoT für „diese Modulwerte sind nach kWp gerechnet, nicht gemessen".
 *
 * Zwei Sichten zeigen dieselben PV-Module (Komponenten-Hub ④ „Verlauf" und
 * ⑤ „Vergleich"); beide müssen dieselbe Aussage tragen, sonst entsteht genau der
 * Widerspruch innerhalb einer Karte, den Rainer 2026-07-25 gemeldet hat. Der Text
 * stammt aus dem Daten-Checker (`services/daten_checker/energieprofil.py`) —
 * eine Formulierung, drei Orte (Checker, ④, ⑤).
 *
 * `bezug` setzt die aufrufende Sicht, weil sich die Kennzeichnung dort jeweils
 * auf einen anderen Ausschnitt bezieht.
 */
import type { WertHerkunft } from '../components/blocks'

export const PV_MODUL_VERTEILT_HERKUNFT: Omit<WertHerkunft, 'bezug'> = {
  zustand: 'geschaetzt',
  quelleLabel: 'kWp-Anteil',
  hinweis: 'Werte je Modul sind nicht gemessen, sondern anteilig nach kWp aus der '
    + 'Gesamterzeugung verteilt — Pro-String-Genauigkeit eingeschränkt. Für gemessene '
    + 'Werte je String braucht jedes Modul einen eigenen Erzeugungs-Sensor.',
}

/** Kennzeichnung mit sicht-eigenem Bezugslabel. */
export function pvVerteiltHerkunft(bezug: string, hinweis?: string | null): WertHerkunft {
  return { ...PV_MODUL_VERTEILT_HERKUNFT, bezug, hinweis: hinweis || PV_MODUL_VERTEILT_HERKUNFT.hinweis }
}
