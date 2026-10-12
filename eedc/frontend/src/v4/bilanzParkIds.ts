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
import { zeigeMonatsprognose } from '../lib/sollErfuellung'

/** Die Geräte hinter „PV-Erzeugung aus" — Strings, Wechselrichter und Balkonkraftwerke (Handgriff Nr. 35/46, 12.10.2026).
 *
 *  Die PV-Erzeugung des Monats/Jahres enthält das Balkonkraftwerk (`ErzeugungFakten.pv_kwh`), und das Backend liefert
 *  es in `komponenten_geraete['balkonkraftwerk']` — die Liste nannte es bis dahin nicht („Süd · West" neben einer Zahl
 *  mit Balkon). EINE Stelle für Monat, Jahr und die Park-IDs. */
export function pvErzeugerNamen(d: Pick<AktuellerMonatResponse, 'komponenten_geraete'>): string[] {
  return [
    ...(d.komponenten_geraete?.['pv-module'] ?? []),
    ...(d.komponenten_geraete?.['wechselrichter'] ?? []),
    ...(d.komponenten_geraete?.['balkonkraftwerk'] ?? []),
  ]
}

/** IDs der tatsächlich gerenderten Teil-Anzeigen des Monats-Bilanz-Blocks.
 *  Auch für Jahr (gleicher `AktuellerMonatResponse`-Aggregat-Shape). */
export function monatBilanzParkIds(
  d: AktuellerMonatResponse,
  /** `'jahr'` lässt die Monatsprognose weg — sie wird nur in `MonatBilanz`
   *  gerendert. Ohne diesen Parameter wartete der Jahres-Block auf das Parken
   *  eines Elements, das es dort nicht gibt (beide Sichten teilen sich diese
   *  Funktion, weil sie denselben Aggregat-Shape tragen). */
  sicht: 'monat' | 'jahr' = 'monat',
): string[] {
  const ids = ['el:bilanz-vergleich', 'el:bilanz-grundlast']
  if (sicht === 'monat' && zeigeMonatsprognose(d)) ids.push('el:bilanz-monatsprognose')
  if (d.eigenverbrauch_kwh != null && d.einspeisung_kwh != null && (d.pv_erzeugung_kwh ?? 0) > 0) ids.push('el:bilanz-verteilung')
  if (pvErzeugerNamen(d).length >= 2) ids.push('el:bilanz-geraete')
  return ids
}

/** IDs der tatsächlich gerenderten Teil-Anzeigen des Tag-Bilanz-Blocks. */
export function tagBilanzParkIds(t: TagWerte): string[] {
  const ids = ['el:bilanz-vergleich', 'el:bilanz-pr']
  const hatSpitzen = t.peak_pv_kw != null || (t.temperatur_min_c != null && t.temperatur_max_c != null)
  if (hatSpitzen) ids.push('el:bilanz-spitzen')
  // Gate wortgleich in `TagBilanz.tsx` (PV-Verteilung) — siehe dort.
  if (t.eigenverbrauch != null && t.einspeisung != null && (t.erzeugung ?? 0) > 0) ids.push('el:bilanz-verteilung')
  return ids
}
