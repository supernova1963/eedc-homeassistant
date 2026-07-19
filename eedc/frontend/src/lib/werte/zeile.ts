/**
 * Normalisierte Werte-Zeile — die granularitäts-agnostische Eingabe der
 * `WerteTabelle`. Monats- wie Tageszeilen werden auf dieselbe Form gebracht,
 * damit die EINE Tabelle (Picker/CSV/Vergleich/Footer) ohne Sonderpfade über
 * beide Granularitäten läuft (IA v4 E3, O1: „gleiche Funktion + Aussehen, nur
 * Zeiträume variieren").
 */
import { MONAT_KURZ, WT_KURZ } from '../constants'
import type { MonatsZeitreihe } from '../../pages/auswertung/types'
import type { TagWerte } from '../../api/energie_profil'
import { getMonatWert, getTagWert } from './registry'

export interface WerteZeile {
  /** Eindeutige Zeilen-ID (React-key). */
  id: string
  /** Numerischer Schlüssel für aufsteigende Zeit-Sortierung. */
  sortKey: number
  /** Anzeige-Label der Zeitraum-Spalte (z. B. „Mai 2026" / „Mo 10.05."). */
  label: string
  /** Zeitraum-Teil links (Wochentag / Monatskürzel) — R20-1: eigene Teil-Spalte,
   *  linksbündig, damit Datum/Jahr sauber rechtsbündig danebensteht. */
  zeitLinks: string
  /** Zeitraum-Teil rechts (Datum / Jahr) — R20-1: rechtsbündig. */
  zeitRechts: string
  /** Schlüssel zum Matchen der Vergleichszeile (Monat 1–12 / Tag-im-Monat 1–31). */
  vergleichKey: number
  /** Metrik-Wert-Accessor (Registry-key → Wert). */
  wert: (key: string) => number | null
}

/** Monats-Zeitreihe → normalisierte Zeile. */
export function monatsZeile(r: MonatsZeitreihe): WerteZeile {
  return {
    id: `${r.jahr}-${r.monat}`,
    sortKey: r.jahr * 100 + r.monat,
    label: `${MONAT_KURZ[r.monat]} ${r.jahr}`,
    zeitLinks: MONAT_KURZ[r.monat],
    zeitRechts: String(r.jahr),
    vergleichKey: r.monat,
    wert: (key) => getMonatWert(r, key),
  }
}

/** Tages-Werte → normalisierte Zeile. Vergleich = gleicher Tag-im-Monat. */
export function tagesZeile(r: TagWerte): WerteZeile {
  // r.datum = ISO 'YYYY-MM-DD' → ohne TZ-Drift zerlegen.
  const [y, m, d] = r.datum.split('-').map(Number)
  const wt = new Date(Date.UTC(y, m - 1, d)).getUTCDay()
  const dd = String(d).padStart(2, '0')
  const mm = String(m).padStart(2, '0')
  return {
    id: r.datum,
    sortKey: y * 10000 + m * 100 + d,
    label: `${WT_KURZ[wt]} ${dd}.${mm}.`,
    zeitLinks: WT_KURZ[wt],
    zeitRechts: `${dd}.${mm}.`,
    vergleichKey: d,
    wert: (key) => getTagWert(r, key),
  }
}
