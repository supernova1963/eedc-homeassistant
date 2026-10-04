/**
 * Erträge je Erzeuger — die EINE Client-Regel, welche Geräte eine eigene Spalte
 * bzw. Serie bekommen und welche in der Anzeige fehlen (#350, Rainer).
 *
 * Auslöser ist Rainers Frage nach dem Ertrag „meines BKW im Vorgarten, meines
 * Süd-Ost-Dachs, meines Nord-West-Dachs" **je Tag**. Die Werte liegen vor
 * (`TagWerte.erzeuger_kwh`) für Geräte mit **eigenem Sensor** — und, wenn ein
 * Anlagen-Gesamtzähler den Tag trägt, auch für die übrigen: die bekommen dann
 * ihren kWp-Anteil am Rest (Backend `pv_tages_praezedenz.loese_aggregat_tag_auf`,
 * Marke `kwp_anteil`), ein Gerät mit eigenem Zähler behält seinen gemessenen
 * Tageswert (N-623, 04.10.2026). **Ohne** Gesamtzähler verteilt der Tag nichts —
 * eine fehlende Spalte ist dann eine Aussage über die Messung, nicht über den
 * Ertrag, und wird benannt statt verschwiegen.
 *
 * Zwei Grenzen stecken hier und nirgends sonst:
 *  - **Ab zwei Erzeugern.** Bei genau einem Gerät ist die Gerätespalte die
 *    Anlagenspalte; eine zweite Zahl derselben Größe nebeneinander ist keine
 *    Information, sondern eine Verwechslungsgefahr.
 *  - **Nur Geräte, die es im Zeitraum gab** ([[feedback_anschaffungsdatum_grenze]]).
 *    Ein im Juni gekauftes BKW fehlt im Januar zu Recht und darf dort nicht als
 *    „ohne Sensor" gemeldet werden.
 *
 * ⭐ **Seit 12.09.2026 steht hier auch die Senken-Hälfte derselben Regel**
 * ({@link wpSplitSerien}/{@link wpRestKw}): Der Butterfly-Stundenverlauf
 * schlüsselt eine Wärmepumpe mit getrennten Leistungssensoren nach Funktion
 * auf, und das ist Aufschlüsselung-plus-Rest wie bei den PV-Strings — nur mit
 * umgekehrtem Vorzeichen. Zwei Dateien für eine Regel mit zwei Vorzeichen
 * wären die Drift, gegen die diese Datei gebaut ist.
 */
import type { Investition } from '../types'
import type { SerieInfo, TagWerte } from '../api/energie_profil'
import { compareTyp } from './constants'
import { erzeugerMetriken, type WerteMetrik } from './werte'

/** Investitionstypen, die Strom erzeugen und je Gerät ausgewiesen werden.
 *  Spiegel: `backend/services/live_sensor_config.py::ERZEUGER_TYPEN`. */
export const ERZEUGER_INVESTITION_TYPEN = ['pv-module', 'balkonkraftwerk']

/** Ab wie vielen Erzeugern eine Aufschlüsselung je Gerät überhaupt etwas sagt. */
export const ERZEUGER_MIN_ANZAHL = 2

export interface ErzeugerSpalten {
  /** Zusatz-Metriken für die `WerteTabelle` (leer, solange es nichts zu trennen gibt). */
  metriken: WerteMetrik[]
  /** Erzeuger im Zeitraum, sortiert nach Typ-Reihenfolge. */
  imZeitraum: Investition[]
  /** Erzeuger im Zeitraum **ohne** einen einzigen Tageswert — die fehlenden Spalten. */
  ohneMessung: Investition[]
}

/** War die Investition im Fenster [von, bis] (ISO-Tage) überhaupt vorhanden? */
function imZeitraumVorhanden(inv: Investition, von: string, bis: string): boolean {
  if (inv.anschaffungsdatum && inv.anschaffungsdatum.slice(0, 10) > bis) return false
  if (inv.stilllegungsdatum && inv.stilllegungsdatum.slice(0, 10) < von) return false
  return true
}

/**
 * Spalten je Erzeuger aus den geladenen Tageszeilen und den Stammdaten.
 *
 * `rows` liefert, **was gemessen wurde**, die Investitionen liefern, **was es
 * gibt** — die Differenz ist der Hinweis. Gemeldet wird nur, was auch eine
 * Spalte hätte: unter {@link ERZEUGER_MIN_ANZAHL} Geräten bleibt alles leer.
 */
export function baueErzeugerSpalten(
  rows: TagWerte[],
  investitionen: Investition[],
  von: string,
  bis: string,
): ErzeugerSpalten {
  const imZeitraum = investitionen
    .filter((inv) => ERZEUGER_INVESTITION_TYPEN.includes(inv.typ))
    .filter((inv) => imZeitraumVorhanden(inv, von, bis))
    .sort((a, b) => compareTyp(a, b) || a.bezeichnung.localeCompare(b.bezeichnung, 'de-DE'))

  if (imZeitraum.length < ERZEUGER_MIN_ANZAHL) {
    return { metriken: [], imZeitraum, ohneMessung: [] }
  }

  const gemessen = new Set<string>()
  for (const r of rows) {
    for (const [id, wert] of Object.entries(r.erzeuger_kwh ?? {})) {
      if (wert != null) gemessen.add(id)
    }
  }

  const mitMessung = imZeitraum.filter((inv) => gemessen.has(String(inv.id)))
  return {
    metriken: erzeugerMetriken(mitMessung),
    imZeitraum,
    ohneMessung: imZeitraum.filter((inv) => !gemessen.has(String(inv.id))),
  }
}

/**
 * Ungedeckter PV-Anteil einer Stunde: gemessene Anlagen-PV minus der Summe der
 * aufgeschlüsselten Geräte.
 *
 * Der Rest ist **kein** Rechenfehler, sondern die ehrliche Restgröße: Strings
 * ohne eigenen Sensor stecken darin, und die Betrags-Drift zwischen Leistungs-
 * und Zählerpfad (#356) ebenfalls. Er wird ausgewiesen statt auf die Geräte
 * verteilt — verteilt stünde an einem Dach eine Zahl, die niemand gemessen hat.
 *
 * ⚑ **Die Gegenrichtung deckelt {@link pvSplitKw}** (N-455): Ist Σ Strings
 * größer als `pv_kw`, wird dort skaliert, und dieser Rest ist 0 — die Formel
 * unten bleibt davon unberührt, weil sie ohnehin bei 0 klemmt. Bis zum
 * 13.09.2026 gab es diesen Deckel nicht, und der Quellen-Stapel wuchs in
 * solchen Stunden über die PV-Gesamtlinie hinaus.
 */
export function pvRestKw(
  pvKw: number | null | undefined,
  komponenten: Record<string, number> | null | undefined,
  keys: string[],
): number {
  const summe = keys.reduce((a, k) => a + Math.max(0, komponenten?.[k] ?? 0), 0)
  return Math.max(0, (pvKw ?? 0) - summe)
}

/**
 * Die String-Flächen einer Stunde — **auf die Anlagen-PV gedeckelt** (N-455).
 *
 * ⭐ **Die Quellen-Hälfte von {@link wpSplitKw}, mit derselben Doktrin:**
 * Zähler = Menge, Leistungspfad = Form. `pv_kw` der Stunde ist zählertreu
 * (ΔkWh-Rekonstruktion, die Kurvenform kommt vom Leistungssensor — v3.45.5),
 * die String-Reihen kommen aus dem Leistungspfad (`komponenten`). Melden die
 * Strings zusammen **mehr**, als der Anlagenzähler hergibt, sagen sie nicht
 * mehr, *wie viel* erzeugt wurde, sondern nur noch, *wie es sich verteilt*.
 *
 * ⛔ **Warum es nötig ist (K1).** {@link pvRestKw} klemmt den Rest bei 0 — in
 * der Gegenrichtung hält das die Stapelhöhe **nicht**: Ist Σ Strings größer als
 * `pv_kw`, ragt der Quellen-Stapel über die PV-Gesamtlinie hinaus, während
 * `gesamterzeugung` daneben weiter mit `pv_kw` rechnet. Dieselbe Kante, die
 * N-449 auf der Senkenseite geschlossen hat; der Chart hatte auch hier nur
 * **eine** Richtung übernommen.
 *
 * ⚠ **Nur nach unten.** Ist Σ Strings kleiner, wird nichts gestreckt — die
 * Differenz ist die echte Restgröße „PV (übrige)" ({@link pvRestKw}): Strings
 * ohne eigenen Sensor stecken darin. Eine hochskalierte Stringfläche wäre eine
 * Behauptung über ein Dach, das niemand gemessen hat.
 *
 * ⚠ **Ein Deckel verteilt nichts** — die Memory-Doktrin „die Stunde verteilt
 * nicht" (`project_kwp_verteilung_aggregator`) ist unberührt: Hier wird kein
 * Anlagenwert auf Module aufgeteilt, sondern **Gemessenes** auf die gemessene
 * Gesamtmenge skaliert.
 *
 * Returns:
 *   ``{key: kW}`` je String-Serie, **positiv** wie die Quelle.
 */
export function pvSplitKw(
  pvKw: number | null | undefined,
  komponenten: Record<string, number> | null | undefined,
  keys: string[],
): Record<string, number> {
  const roh = keys.map((k) => Math.max(0, komponenten?.[k] ?? 0))
  const summe = roh.reduce((a, v) => a + v, 0)
  const anlage = Math.max(0, pvKw ?? 0)
  const faktor = summe > anlage && summe > 0 ? anlage / summe : 1
  const werte: Record<string, number> = {}
  keys.forEach((k, i) => { werte[k] = roh[i] * faktor })
  return werte
}

/** Suffixe, mit denen der Leistungspfad **eine** Wärmepumpe je Funktion führt.
 *  Spiegel: `backend/services/live_sensor_config.py::baue_investitions_serien`
 *  (`waermepumpe_<id>_heizen` / `_warmwasser` / `_kuehlen`, nur ohne
 *  „Leistung gesamt").
 *
 *  ⭐ `kuehlen` kam am 13.09.2026 dazu (N-439). Ohne den Eintrag fiele die
 *  Kühl-Fläche aus {@link wpSplitSerien} heraus und läge damit **zusätzlich**
 *  zur Wärmepumpen-Fläche im Stapel — dieselbe Energie zweimal, genau der
 *  Grund, aus dem diese Liste existiert. */
const WP_SPLIT_SUFFIX = /_(heizen|warmwasser|kuehlen)$/

/**
 * Die Funktions-Serien einer Wärmepumpe aus der Serienliste eines Tages.
 *
 * Sie tragen die Kategorie `waermepumpe` und fallen deshalb aus `extraSerien`
 * heraus (`DEDIZIERTE_KATEGORIEN`) — das ist richtig so: dort lägen sie
 * **zusätzlich** zur `wp`-Fläche im Stapel, also dieselbe Energie zweimal.
 * Als eigene Prop schlüsseln sie die vorhandene WP-Fläche auf, genau wie
 * {@link baueErzeugerSpalten} es für die PV-Seite tut.
 */
export function wpSplitSerien(serien: SerieInfo[]): SerieInfo[] {
  return serien.filter((s) => s.kategorie === 'waermepumpe' && WP_SPLIT_SUFFIX.test(s.key))
}

/**
 * Die Funktions-Flächen einer Stunde — **auf den Zähler gedeckelt** (N-449).
 *
 * ⭐ **Zähler = Menge, Leistungspfad = Form.** Liegt neben den getrennten
 * Leistungssensoren ein kWh-Zähler am Gerät, ist er die Wahrheit über die
 * **Menge** dieser Stunde (`geraete_spalte_kw`: „Zähler schlägt Leistungspfad").
 * Die beiden Leistungsreihen sagen dann nicht mehr, *wie viel* verbraucht
 * wurde, sondern *wie es sich verteilt* — genau die Doktrin, mit der der
 * Wärme/Klima-Verlauf seine Stunden bildet (`tages_stapel.py`: *„Die Stunde
 * verteilt den Tag — sie rechnet ihn nicht neu"*).
 *
 * ⛔ **Warum das nötig ist (K1, SOLL §3.2).** Ist Σ|Split| **größer** als der
 * Zähler, kann keine nicht-negative Rest-Fläche die Stapelhöhe halten — der
 * Senken-Stapel stünde um die Drift höher als die Gesamtmenge, und
 * `hausverbrauch` daneben rechnet weiter mit dem Zähler. Gemessen 12.09.2026 an
 * einer gestellten Stunde: Zähler 2,4 kW gegen Σ Split 3,0 kW ⇒ 0,6 kW zu viel
 * im Stapel. Skaliert liegen dort 1,6 und 0,8 — Σ exakt 2,4.
 *
 * ⚠ **Nur nach unten.** Ist Σ|Split| **kleiner** als der Zähler, wird nichts
 * gestreckt: Was die beiden Reihen nicht erklären, ist eine echte Restgröße und
 * heißt {@link wpRestKw} — eine hochskalierte Funktionsfläche wäre dagegen eine
 * Behauptung über eine Verteilung, die niemand gemessen hat.
 *
 * Returns:
 *   ``{key: kW}`` je Funktions-Serie, **negativ** wie die Quelle (Senke, N-261).
 */
export function wpSplitKw(
  wpKw: number | null | undefined,
  komponenten: Record<string, number> | null | undefined,
  keys: string[],
): Record<string, number> {
  const roh = keys.map((k) => Math.min(0, komponenten?.[k] ?? 0))
  const summe = roh.reduce((a, v) => a + Math.abs(v), 0)
  const zaehler = Math.abs(wpKw ?? 0)
  const faktor = summe > zaehler && summe > 0 ? zaehler / summe : 1
  const werte: Record<string, number> = {}
  keys.forEach((k, i) => { werte[k] = roh[i] * faktor })
  return werte
}

/**
 * Ungedeckter Wärmepumpen-Anteil einer Stunde: die Sammelspalte minus der
 * Summe der aufgeschlüsselten Funktions-Serien — die **Senken-Hälfte** von
 * {@link pvRestKw}, mit demselben Zweck und demselben Vorzeichen-Vorbehalt.
 *
 * Zwei Unterschiede zur Quellen-Seite, beide gemessen (12.09.2026):
 *  - `TagesEnergieProfil.komponenten` führt Senken **negativ** (Leistungspfad,
 *    `seite: "senke"` ⇒ `-abs(...)`, N-261) — deshalb `Math.abs` je Key statt
 *    `Math.max(0, …)`. Mit der PV-Regel käme hier immer Σ = 0 heraus.
 *  - Ohne kWh-Zähler ist `waermepumpe_kw` **exakt** `|Σ Split|`
 *    (`geraete_spalte_kw`-Fallback) ⇒ der Rest ist 0 und erscheint nicht.
 *    Er entsteht nur, wo ein Zähler danebensteht (Fall R-a) und beide Pfade
 *    auseinanderliegen — dann ist er die ehrliche Restgröße statt einer
 *    stillen Differenz.
 *
 * ⚑ **Die Gegenrichtung deckelt {@link wpSplitKw}** (N-449): Ist Σ|Split|
 * größer als der Zähler, wird dort skaliert, und dieser Rest ist 0 — die
 * Formel unten bleibt davon unberührt, weil sie ohnehin bei 0 klemmt.
 */
export function wpRestKw(
  wpKw: number | null | undefined,
  komponenten: Record<string, number> | null | undefined,
  keys: string[],
): number {
  const summe = keys.reduce((a, k) => a + Math.abs(komponenten?.[k] ?? 0), 0)
  return Math.max(0, Math.abs(wpKw ?? 0) - summe)
}

/** Wortlaut-SoT des Hinweises unter der Tabelle — eine Formulierung, ein Ort. */
export const ERZEUGER_OHNE_SENSOR_LABEL = 'Ohne eigene Tageswerte'
export const ERZEUGER_OHNE_SENSOR_HINWEIS =
  'Diese Geräte haben keinen eigenen Ertragssensor — ihr Anteil steckt in der '
  + 'Anlagen-Summe. Zuordnen unter Einstellungen → Datenquellen.'
