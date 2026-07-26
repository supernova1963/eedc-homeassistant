/**
 * Kennzeichnung für Prognose-Antworten, die weniger enthalten als ihr Name sagt.
 *
 * Wurzelmuster **P4**: „ein Wert-Pfad darf nie eine Null oder eine Teilsumme als
 * gültiges Ergebnis ausliefern, ohne dass die Antwort selbst es sagt". Das
 * Backend füllt dafür seit A17 das vorhandene `hinweise`-Feld (14-Tage-Prognose:
 * `SolarPrognose.hinweise`, Tagesprognose: `TagesPrognose.hinweise`) — ein
 * `hinweise`-Eintrag, den keine Sicht rendert, wäre aber dasselbe Schweigen mit
 * mehr Code. Diese Datei ist die eine Stelle, die daraus eine Anzeige macht.
 *
 * Gerendert wird über die geteilte {@link HerkunftZeile} (Regel 0a — dieselbe
 * Zeile, die im Komponenten-Hub „nach kWp gerechnet" trägt), nicht über eine
 * zweite Komponente. Zustand ist `weicht_ab`: die Zahl ist nicht geschätzt, sie
 * ist unvollständig — und damit systematisch zu niedrig bzw. ohne Aussage.
 */
import type { WertHerkunft } from '../components/blocks'

/**
 * `WertHerkunft` aus einer `hinweise`-Liste, oder `undefined` wenn die Antwort
 * vollständig ist (dann rendert die Zeile nichts).
 *
 * @param hinweise Backend-Hinweise (leere Liste = vollständig)
 * @param bezug    Worauf sich die Kennzeichnung in DIESER Sicht bezieht
 */
export function unvollstaendigHerkunft(
  hinweise: string[] | null | undefined,
  bezug?: string,
): WertHerkunft | undefined {
  if (!hinweise || hinweise.length === 0) return undefined
  return {
    zustand: 'weicht_ab',
    quelleLabel: 'unvollständig',
    bezug,
    hinweis: hinweise.join(' '),
  }
}
