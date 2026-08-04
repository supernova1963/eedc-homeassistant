/**
 * Erträge je Erzeuger — die EINE Client-Regel, welche Geräte eine eigene Spalte
 * bzw. Serie bekommen und welche in der Anzeige fehlen (#350, Rainer).
 *
 * Auslöser ist Rainers Frage nach dem Ertrag „meines BKW im Vorgarten, meines
 * Süd-Ost-Dachs, meines Nord-West-Dachs" **je Tag**. Die Werte liegen vor
 * (`TagWerte.erzeuger_kwh`), aber nur für Geräte mit **eigenem Sensor**: auf
 * Tagesebene verteilt das Backend bewusst nichts nach kWp — anders als im Monat
 * (`resolve_pv_je_modul`). Eine fehlende Spalte ist deshalb eine Aussage über
 * die Messung, nicht über den Ertrag, und wird benannt statt verschwiegen.
 *
 * Zwei Grenzen stecken hier und nirgends sonst:
 *  - **Ab zwei Erzeugern.** Bei genau einem Gerät ist die Gerätespalte die
 *    Anlagenspalte; eine zweite Zahl derselben Größe nebeneinander ist keine
 *    Information, sondern eine Verwechslungsgefahr.
 *  - **Nur Geräte, die es im Zeitraum gab** ([[feedback_anschaffungsdatum_grenze]]).
 *    Ein im Juni gekauftes BKW fehlt im Januar zu Recht und darf dort nicht als
 *    „ohne Sensor" gemeldet werden.
 */
import type { Investition } from '../types'
import type { TagWerte } from '../api/energie_profil'
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
 */
export function pvRestKw(
  pvKw: number | null | undefined,
  komponenten: Record<string, number> | null | undefined,
  keys: string[],
): number {
  const summe = keys.reduce((a, k) => a + Math.max(0, komponenten?.[k] ?? 0), 0)
  return Math.max(0, (pvKw ?? 0) - summe)
}

/** Wortlaut-SoT des Hinweises unter der Tabelle — eine Formulierung, ein Ort. */
export const ERZEUGER_OHNE_SENSOR_LABEL = 'Ohne eigene Tageswerte'
export const ERZEUGER_OHNE_SENSOR_HINWEIS =
  'Diese Geräte haben keinen eigenen Ertragssensor — ihr Anteil steckt in der '
  + 'Anlagen-Summe. Zuordnen unter Einstellungen → Datenquellen.'
