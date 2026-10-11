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

/** N-653 (10.10.2026): der Mischfall — ein Teil der Module gemessen, der Rest nach kWp verteilt.
 *  Der Satz oben („Werte je Modul sind nicht gemessen …") widerspricht dort den gemessenen Zeilen.
 *  Spiegel von `RANKING_TEILWEISE_VERTEILT` in `api/routes/cockpit/pv_strings.py` (Block ⑤ liest ihn
 *  aus `vergleich_hinweis`), hier ohne den Ranking-Satz, weil Block ④ keine Platzierung zeigt. */
export const PV_MODUL_TEILWEISE_VERTEILT_HINWEIS =
  'Nicht alle Module haben gemessene Werte — ein Teil ist anteilig nach kWp aus der '
  + 'Gesamterzeugung verteilt, Pro-String-Genauigkeit eingeschränkt. Für gemessene Werte '
  + 'je String braucht jedes Modul einen eigenen Erzeugungs-Sensor.'

/** Der Wortlaut des Badges „geschätzt (kWp-Anteil)" als Text — für Stellen ohne Badge (Tooltip-Zeile,
 *  Tabellenspalte). Aus denselben zwei Teilen wie das Badge, damit beide gleich heißen. */
export const KWP_ANTEIL_GESCHAETZT = `${ZUSTAND_META.geschaetzt.label} (${PV_MODUL_VERTEILT_HERKUNFT.quelleLabel})`

/** N-621: Tooltip-Zusatz einer Balkonkraftwerk-Serie, die den Anteil am Anlagenwert mitträgt —
 *  „davon geschätzt (kWp-Anteil): X kWh". `null` ohne Anteil (dann keine Zeile). Der Wert kommt
 *  unverändert aus dem Feld `bkw_aus_anlagenwert_kwh` der Antwort; hier wird nur formatiert. */
export function bkwAnteilZusatz(anteil: unknown, fmt: (v: number) => string): string | null {
  return typeof anteil === 'number' && anteil > 0 ? `davon ${KWP_ANTEIL_GESCHAETZT}: ${fmt(anteil)}` : null
}

/** N-664 (K4): ein Balkonkraftwerk ohne eigenen Zähler — der Hub zeigt seinen kWp-Anteil am Anlagenzähler,
 *  wie das Cockpit. Dasselbe Badge wie bei den PV-Modulen (Zustand + Quell-Label), eigener Erklärsatz. */
export const BKW_KWP_ANTEIL_HINWEIS =
  'Dieses Balkonkraftwerk hat in diesen Monaten keinen eigenen Wert — seine Erzeugung ist anteilig nach kWp aus '
  + 'dem Anlagenzähler verteilt, nicht gemessen. Eigenverbrauch und Einspeisung folgen daraus. Für gemessene Werte '
  + 'braucht es einen eigenen Erzeugungs-Sensor.'

/** N-671 (K4): an Modul-Kinder abgetreten (ADR-002/P11) — die Erzeugung steht dort, hier 0 wie in den Monats-Fakten. */
export const BKW_ABGETRETEN_HINWEIS =
  'Die Erzeugung dieses Balkonkraftwerks steht bei seinen Modul-Kindern (Komponenten → PV-Module) — '
  + 'hier zählt sie deshalb nicht noch einmal.'

/** Kennzeichnung des BKW-Verlaufs, wenn mindestens ein Monat den kWp-Anteil trägt; sonst `undefined`. */
export function bkwAnteilHerkunft(monatsreihe: readonly { erzeugung_quelle?: string }[]): WertHerkunft | undefined {
  return monatsreihe.some((m) => m.erzeugung_quelle === 'kwp_anteil')
    ? { ...PV_MODUL_VERTEILT_HERKUNFT, bezug: 'Erzeugung', hinweis: BKW_KWP_ANTEIL_HINWEIS }
    : undefined
}

/** Kennzeichnung mit sicht-eigenem Bezugslabel. */
export function pvVerteiltHerkunft(bezug: string, hinweis?: string | null): WertHerkunft {
  return { ...PV_MODUL_VERTEILT_HERKUNFT, bezug, hinweis: hinweis || PV_MODUL_VERTEILT_HERKUNFT.hinweis }
}
