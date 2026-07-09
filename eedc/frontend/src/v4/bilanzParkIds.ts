/**
 * bilanzParkIds — Element-Park-IDs der Cockpit-Bilanz-Blöcke (Monat/Tag/Jahr).
 *
 * Reines Helfer-Modul (kein React-Export) — damit die Sichten (CockpitMonat/Tag/Jahr)
 * den ganzen Bilanz-Block erst ausblenden, wenn ALLE Teil-Anzeigen geparkt sind
 * (Speicher-Muster `alleGeparkt`). Bewusst NICHT in den *Bilanz.tsx-Komponenten,
 * um dort keine zusätzliche react-refresh/only-export-components-Warnung zu erzeugen.
 */
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { TagWerte } from '../api/energie_profil'

/** IDs der tatsächlich gerenderten Teil-Anzeigen des Monats-Bilanz-Blocks.
 *  Auch für Jahr (gleicher `AktuellerMonatResponse`-Aggregat-Shape). */
export function monatBilanzParkIds(d: AktuellerMonatResponse): string[] {
  const ids = ['el:bilanz-vergleich', 'el:bilanz-grundlast']
  if (d.eigenverbrauch_kwh != null && d.einspeisung_kwh != null && (d.pv_erzeugung_kwh ?? 0) > 0) ids.push('el:bilanz-verteilung')
  const pvGeraete = [...(d.komponenten_geraete?.['pv-module'] ?? []), ...(d.komponenten_geraete?.['wechselrichter'] ?? [])]
  if (pvGeraete.length >= 2) ids.push('el:bilanz-geraete')
  return ids
}

/** IDs der tatsächlich gerenderten Teil-Anzeigen des Tag-Bilanz-Blocks. */
export function tagBilanzParkIds(t: TagWerte): string[] {
  const ids = ['el:bilanz-vergleich', 'el:bilanz-pr']
  const hatSpitzen = t.peak_pv_kw != null || (t.temperatur_min_c != null && t.temperatur_max_c != null)
  if (hatSpitzen) ids.push('el:bilanz-spitzen')
  if (t.eigenverbrauch != null && t.einspeisung != null && t.erzeugung > 0) ids.push('el:bilanz-verteilung')
  return ids
}
