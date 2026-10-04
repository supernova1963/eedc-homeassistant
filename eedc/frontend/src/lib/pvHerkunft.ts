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
import { ZUSTAND_META } from '../components/ui/ErfassungZustandBadge'

export const PV_MODUL_VERTEILT_HERKUNFT: Omit<WertHerkunft, 'bezug'> = {
  zustand: 'geschaetzt',
  quelleLabel: 'kWp-Anteil',
  hinweis: 'Werte je Modul sind nicht gemessen, sondern anteilig nach kWp aus der '
    + 'Gesamterzeugung verteilt — Pro-String-Genauigkeit eingeschränkt. Für gemessene '
    + 'Werte je String braucht jedes Modul einen eigenen Erzeugungs-Sensor.',
}

/** Der Wortlaut des Badges „geschätzt (kWp-Anteil)" als Text — für Stellen ohne Badge (Tooltip-Zeile,
 *  Tabellenspalte). Aus denselben zwei Teilen wie das Badge, damit beide gleich heißen. */
export const KWP_ANTEIL_GESCHAETZT = `${ZUSTAND_META.geschaetzt.label} (${PV_MODUL_VERTEILT_HERKUNFT.quelleLabel})`

/** N-621: Tooltip-Zusatz einer Balkonkraftwerk-Serie, die den Anteil am Anlagenwert mitträgt —
 *  „davon geschätzt (kWp-Anteil): X kWh". `null` ohne Anteil (dann keine Zeile). Der Wert kommt
 *  unverändert aus dem Feld `bkw_aus_anlagenwert_kwh` der Antwort; hier wird nur formatiert. */
export function bkwAnteilZusatz(anteil: unknown, fmt: (v: number) => string): string | null {
  return typeof anteil === 'number' && anteil > 0 ? `davon ${KWP_ANTEIL_GESCHAETZT}: ${fmt(anteil)}` : null
}

/** Kennzeichnung mit sicht-eigenem Bezugslabel. */
export function pvVerteiltHerkunft(bezug: string, hinweis?: string | null): WertHerkunft {
  return { ...PV_MODUL_VERTEILT_HERKUNFT, bezug, hinweis: hinweis || PV_MODUL_VERTEILT_HERKUNFT.hinweis }
}
