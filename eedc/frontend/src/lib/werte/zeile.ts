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
  /** Schlüssel zum Matchen der Vergleichszeile. Das ist ein **gemeinsamer
   *  Schlüsselraum beider Seiten**, kein Zeitstempel: Primär- und Vergleichszeile
   *  tragen denselben Wert genau dann, wenn sie einander gegenüberstehen. Die
   *  Fabriken vergeben ihn **eindeutig** (Monat: `jahr·100+monat` · Tag:
   *  `jahr·10000+monat·100+tag`); in den Raum der Primärseite hebt ihn die
   *  jeweilige Ausrichtung — {@link richteMonateAus} hier, `richteAus`
   *  (AuswertungenTabelleV4) für Tage. */
  vergleichKey: number
  /** Metrik-Wert-Accessor (Registry-key → Wert). */
  wert: (key: string) => number | null
  /**
   * Warum eine Metrik **keinen** Wert hat (S3: „nicht ‚—', sondern der Grund").
   *
   * Optional und pro Metrik: Nur wo der Layer eine Kennzahl bewusst verweigert,
   * steht hier ein Satz — heute die Arbeitszahl (R2/ADR-002/P12).
   *
   * ⛔ Hier stand bis 2026-09-04: „Die Tabelle haengt ihn als Tooltip an die
   * Zelle; eine sichtbare Zeile hat eine Tabellenzelle nicht." Der zweite
   * Halbsatz war eine Behauptung, kein Befund (**N-374**): Die Zelle hat keine
   * sichtbare Zeile, die *Tabelle* sehr wohl — `WerteTabelle` traegt den
   * Fuss-Grund seit jeher genau so darunter. Der Grund steht deshalb jetzt
   * sichtbar unter der Tabelle; der Tooltip an der Zelle bleibt als Zugabe fuer
   * den Desktop. Warum das noetig war: ein Tooltip verlangt, dass man ihn SUCHT
   * — auf dem Telefon zeigt nichts darauf hin, dass hinter dem „—" etwas steht
   * (das Info-Icon von `FormelTooltip` traegt `hidden sm:`). Ein Grund neben der
   * Zahl verlangt das nicht, und ein nacktes „—" ist die haeufigste Beschwerde
   * dieser Flaeche (S3).
   * ⛔ Hier stand bis 2026-09-04 als erster Grund: „ein natives `title=` hat auf
   * dem Telefon keine Entsprechung". **Das war falsch** (**N-390**, gemessen):
   * `App.tsx` ruft `useTouchTitleTooltip` auf — einen app-globalen Touch-Ersatz
   * fuer `title=`/`data-title`. Ich hatte eine Abwesenheit behauptet, statt sie
   * zu messen. Der Bau bleibt richtig, seine Begruendung ist es jetzt auch.
   */
  grund?: (key: string) => string | null
}

/** Monats-Zeitreihe → normalisierte Zeile. */
export function monatsZeile(r: MonatsZeitreihe): WerteZeile {
  return {
    id: `${r.jahr}-${r.monat}`,
    sortKey: r.jahr * 100 + r.monat,
    label: `${MONAT_KURZ[r.monat]} ${r.jahr}`,
    zeitLinks: MONAT_KURZ[r.monat],
    zeitRechts: String(r.jahr),
    vergleichKey: r.jahr * 100 + r.monat,
    wert: (key) => getMonatWert(r, key),
    grund: (key) => (key === 'wp_cop' ? r.wp_cop_grund ?? null : null),
  }
}

/**
 * Monats-Ausrichtung „selber Monat, ein Jahr früher": die **Vergleichs**-Zeilen
 * werden um ein Jahr vorwärts auf ihre Primärzeile abgebildet (Schlüssel
 * `jahr·100+monat` ⇒ ein Jahr = +100), die Primärseite behält ihren eigenen
 * Schlüssel. Findet eine Zeile kein Vorjahr, bleibt ihre Vergleichsspalte leer.
 *
 * Bis v4.0.5 war der Schlüssel die blanke Monatsnummer 1–12. Über einen
 * mehrjährigen Zeitraum („Alle Jahre") lagen dadurch mehrere Jahrgänge desselben
 * Monats im Vergleichsfenster, der Lookup behielt den letzten — jede Zeile verglich
 * sich mit dem jüngsten Jahrgang, Dez 2025 im Extremfall mit sich selbst (Δ 0,0 %;
 * PN 90204, Rainer).
 */
export function richteMonateAus(vergleichsZeilen: WerteZeile[] | null): WerteZeile[] | null {
  if (!vergleichsZeilen) return null
  return vergleichsZeilen.map((z) => ({ ...z, vergleichKey: z.vergleichKey + 100 }))
}

/** Tages-Werte → normalisierte Zeile. */
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
    vergleichKey: y * 10000 + m * 100 + d,
    wert: (key) => getTagWert(r, key),
  }
}
