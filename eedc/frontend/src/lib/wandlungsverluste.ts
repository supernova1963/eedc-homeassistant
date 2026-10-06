/**
 * Wandlungsverluste — Anzeige-SoT (HA-Bauform E4b, Wortlaut Gernot 06.10.2026; N-588: angezeigt, NICHT bewertet).
 *
 * Der Wert kommt fertig aus dem Backend (`wandlungsverluste_kwh`, `wandlungsverluste_prozent` — Layer
 * `core/berechnungen/pv_verteilung.wandlungsverluste_prozent`): Σ String-Zähler − Anlagenzähler, Prozent bezogen auf
 * die Σ der String-Zähler. Hier wird nur formatiert und entschieden, OB eine Zeile erscheint — gerechnet wird nichts.
 *
 * Drei Orte zeigen dieselbe Zeile mit demselben Hinweistext: Cockpit → Monat und Cockpit → Jahr (Unterzeile am
 * Label „PV-Erzeugung" in der Vergleichstabelle) und Komponenten → PV-Anlage → Verlauf (gesamte Historie).
 */
import { fmtZahl, formatProzent } from './einheiten'

/** Bezeichnung der Zeile. */
export const WANDLUNGSVERLUSTE_LABEL = 'Wandlungsverluste'

/** Hinweistext (Tooltip) — wortgleich an allen drei Orten. */
export const WANDLUNGSVERLUSTE_HINWEIS =
  'Differenz zwischen der Summe der String-Zähler (vor dem Wechselrichter) und dem Anlagenzähler (dahinter). '
  + 'Wird angezeigt, nicht bewertet: Ersparnis und CO₂ rechnen weiter mit der Summe der Strings.'

/**
 * Der Wert der Zeile, z. B. „36,0 kWh (5,7 %)" — kWh mit einer, Prozent mit einer Nachkommastelle (Leerzeichen
 * vor %). `null` heißt: keine Zeile. Das ist der Fall ohne Anlagenzähler bzw. ohne Kanal-Deckung (das Backend
 * liefert `null`) und bei einem Wert, der angezeigt 0 wäre (kein „0,0 kWh", kein „—").
 */
export function wandlungsverlusteWert(
  kwh: number | null | undefined,
  prozent: number | null | undefined,
): string | null {
  if (kwh == null || !Number.isFinite(kwh)) return null
  const text = fmtZahl(kwh, 1)
  if (kwh <= 0 || text === fmtZahl(0, 1)) return null
  return prozent != null ? `${text} kWh (${formatProzent(prozent).text})` : `${text} kWh`
}

/** Die ganze Zeile „Wandlungsverluste 36,0 kWh (5,7 %)" — oder `null`. */
export function wandlungsverlusteZeile(
  kwh: number | null | undefined,
  prozent: number | null | undefined,
): string | null {
  const wert = wandlungsverlusteWert(kwh, prozent)
  return wert ? `${WANDLUNGSVERLUSTE_LABEL} ${wert}` : null
}

/** Eine Unterzeile am Label einer Tabellenzeile: Text und Hinweistext (Tooltip). */
export interface Unterzeile { text: string; hinweis: string }

/** Die Unterzeile „Wandlungsverluste …" unter „PV-Erzeugung" (Cockpit → Monat/Jahr) — `null` heißt keine Zeile. */
export function wandlungsverlusteUnterzeile(
  d: { wandlungsverluste_kwh?: number | null; wandlungsverluste_prozent?: number | null },
): Unterzeile | null {
  const text = wandlungsverlusteZeile(d.wandlungsverluste_kwh, d.wandlungsverluste_prozent)
  return text ? { text, hinweis: WANDLUNGSVERLUSTE_HINWEIS } : null
}

/** Die Zeile im Block „Verlauf" des PV-Hubs (gesamte Historie, Übersicht ohne Jahr) — `null` heißt keine Zeile. */
export function wandlungsverlusteVerlaufZeile(
  u: { wandlungsverluste_kwh?: number | null; wandlungsverluste_prozent?: number | null },
): (Unterzeile & { titel: string }) | null {
  const z = wandlungsverlusteUnterzeile(u)
  return z ? { ...z, titel: WANDLUNGSVERLUSTE_LABEL } : null
}
