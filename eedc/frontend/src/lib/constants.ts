/**
 * Zentrale Konstanten für das gesamte Frontend.
 *
 * Monatsnamen, Investitionstyp-Labels und andere wiederverwendbare
 * Definitionen, die in vielen Seiten dupliziert waren.
 */

import type { InvestitionTyp } from '../types'

// ─── z-Index-Skala ───────────────────────────────────────────────────────────

/**
 * Tooltip-Layer (P3-Kanon): über Modals (z-50) und Popovers. Für className
 * die Tailwind-Entsprechung `z-[10000]` verwenden — dieser Wert ist die SoT
 * für JS-Inline-Styles (z. B. `useTouchTitleTooltip`).
 */
export const Z_TOOLTIP = 10000

// ─── Monatsnamen ─────────────────────────────────────────────────────────────

/** Kurze Monatsnamen, 1-basiert (Index 0 = leer). Für Chart-Labels, Tabellen. */
export const MONAT_KURZ = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

/** Volle Monatsnamen, 1-basiert (Index 0 = leer). Für Überschriften, Formulare. */
export const MONAT_NAMEN = ['', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

// ─── Wochentagsnamen (R3b S7: SoT statt 7 lokaler Kopien) ────────────────────

/**
 * Kurze Wochentagsnamen — **Index = `Date.getDay()` (0 = Sonntag)**.
 * Mo-first-Ansichten (Kalender-Header, Backend-`wochentag` = Python-weekday
 * 0 = Montag) leiten per Rotation ab: `[...WT_KURZ.slice(1), WT_KURZ[0]]` —
 * KEINE zweite Basis-Konstante (Off-by-one-Falle, s. DatumPicker/EnergieprofilTab).
 */
export const WT_KURZ = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']

/** Volle Wochentagsnamen — Index = `Date.getDay()` (0 = Sonntag). */
export const WT_LANG = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag']

// ─── Investitionstyp-Labels ──────────────────────────────────────────────────

/** Lesbare Labels für Investitionstypen. */
export const TYP_LABELS: Record<string, string> = {
  'pv-module': 'PV-Module',
  'wechselrichter': 'Wechselrichter',
  'speicher': 'Speicher',
  'e-auto': 'E-Auto',
  'wallbox': 'Wallbox',
  'waermepumpe': 'Wärmepumpe',
  'balkonkraftwerk': 'Balkonkraftwerk',
  'sonstiges': 'Sonstiges',
  'pv-system': 'PV-System',
}

/** Lesbare Labels für Wärmepumpen-Arten (`WPArt` in lib/investitionParameter.ts). */
export const WP_ART_LABELS: Record<string, string> = {
  luft_wasser: 'Luft/Wasser',
  sole_wasser: 'Sole/Wasser',
  grundwasser: 'Grundwasser',
  luft_luft: 'Luft/Luft',
}

/**
 * Daten-Provenance: Roh-Enum → Klartext-Label (R3b S7/ORD-4 — vorher 3 lokale,
 * bereits gedriftete Kopien in Tag-/Monat-/JahrRahmen). EINE Map für BEIDE
 * Enums: `TagWerte.datenquelle` UND `feld_quellen[*].quelle`
 * (`api/routes/aktueller_monat.py` emittiert ha_statistics/local_connector/
 * gespeichert/mqtt_inbound — die alten 6-Key-Maps kannten KEINEN davon, daher
 * standen Roh-Enums in der UI, [[feedback_typ_labels_pattern]]).
 * Unbekannte Werte: Konsumenten fallen auf den Roh-Wert zurück (`?? quelle`).
 */
export const DATENQUELLE_LABELS: Record<string, string> = {
  ha_sensor: 'HA',
  ha_statistics: 'HA-Statistik',
  ha_statistiken: 'HA-Statistik',
  mqtt: 'MQTT',
  mqtt_inbound: 'MQTT',
  connector: 'Connector',
  local_connector: 'Connector',
  scheduler: 'gespeichert',
  gespeichert: 'gespeichert',
  monatsabschluss: 'Abschluss',
  manuell: 'manuell',
  wetter_prognose: 'Prognose',
  csv: 'CSV',
  custom_import: 'Import',
  portal_import: 'Import',
}

/** Sonstiges-Investitionen: `kategorie`-Enum → Label (R3b S7/ORD-5 — vorher 3 lokale Kopien). */
export const SONSTIGES_KATEGORIE_LABELS: Record<string, string> = {
  erzeuger: 'Erzeuger',
  verbraucher: 'Verbraucher',
  speicher: 'Speicher',
}

/**
 * Anzeige-Reihenfolge der DB-Investitions-Typen — Single Source of Truth.
 * Reihenfolge: Wechselrichter → PV-Module → Speicher → Balkonkraftwerk →
 * Verbraucher nach Wirkung auf Hausverbrauch (#214 detLAN: WP vor Wallbox).
 * `pv-system` ist nicht enthalten — virtueller Aggregat-Typ in der ROI-Tabelle
 * mit eigenem Container, wird nicht in dieser Reihe sortiert.
 * Spiegel im Backend: `backend/utils/investition_filter.py:INVESTITION_TYP_ORDER`.
 */
export const INVESTITION_TYP_ORDER: InvestitionTyp[] = [
  'wechselrichter',
  'pv-module',
  'speicher',
  'balkonkraftwerk',
  'waermepumpe',
  'wallbox',
  'e-auto',
  'sonstiges',
]

/** Sort-Comparator für Listen mit `.typ`-Feld. Unbekannte Typen ans Ende. */
export function compareTyp(a: { typ?: string | null }, b: { typ?: string | null }): number {
  const len = INVESTITION_TYP_ORDER.length
  const idxA = a.typ ? (INVESTITION_TYP_ORDER as readonly string[]).indexOf(a.typ) : -1
  const idxB = b.typ ? (INVESTITION_TYP_ORDER as readonly string[]).indexOf(b.typ) : -1
  return (idxA === -1 ? len : idxA) - (idxB === -1 ? len : idxB)
}

// ─── Regionen (Bundesländer + DACH) ─────────────────────────────────────────

/** Kurzcode → Klartext für deutsche Bundesländer + AT/CH. */
export const REGION_NAMEN: Record<string, string> = {
  BW: 'Baden-Württemberg',
  BY: 'Bayern',
  BE: 'Berlin',
  BB: 'Brandenburg',
  HB: 'Bremen',
  HH: 'Hamburg',
  HE: 'Hessen',
  MV: 'Mecklenburg-Vorpommern',
  NI: 'Niedersachsen',
  NW: 'Nordrhein-Westfalen',
  RP: 'Rheinland-Pfalz',
  SL: 'Saarland',
  SN: 'Sachsen',
  ST: 'Sachsen-Anhalt',
  SH: 'Schleswig-Holstein',
  TH: 'Thüringen',
  AT: 'Österreich',
  CH: 'Schweiz',
  XX: 'Unbekannt',
}

// ─── Komponenten-Aggregation ─────────────────────────────────────────────────

/**
 * Key-Prefixe in `TagesZusammenfassung.komponenten_kwh`, die zur PV-Tages-
 * erzeugung beitragen (z. B. für die PV-Ertrag-Spalte der Energieprofil-
 * Tagestabelle).
 *
 * Spiegel im Backend: `backend/core/berechnungen/energie.py:PV_KOMPONENTEN_PREFIXE`
 * (Berechnungs-Layer, ADR-001). Ein neues PV-Prefix muss in BEIDEN Dateien
 * ergänzt werden — sonst entsteht Drift wie bei der BKW-Doppelzählung.
 */
export const PV_KOMPONENTEN_PREFIXE = ['pv_', 'bkw_'] as const

// ─── Saison-Fenster ──────────────────────────────────────────────────────────

/**
 * Fokus-Fenster für Saison-Vergleiche (WP-Saisonvergleich im Cockpit, #195).
 *
 * `startMonat` ist der erste Monat der Saison; Monate kleiner als `startMonat`
 * zählen zum Folgejahr (Jahresgrenzen-Überlauf bei Winter/Heizperiode). Die
 * Fenster überlappen bewusst — es sind alternative Fokus-Fenster, keine
 * Partition des Jahres. Bekommt #195 Punkt 3 (HDD) ein Backend-Pendant, ist
 * diese Map die Spiegel-Vorlage.
 */
export const SAISON_FENSTER = {
  winter:      { label: 'Winter',      bereich: 'Nov–Feb', startMonat: 11, monate: [11, 12, 1, 2] },
  heizperiode: { label: 'Heizperiode', bereich: 'Okt–Apr', startMonat: 10, monate: [10, 11, 12, 1, 2, 3, 4] },
  sommer:      { label: 'Sommer',      bereich: 'Jun–Aug', startMonat: 6,  monate: [6, 7, 8] },
} as const

// ─── Speicher-Wirtschaftlichkeit: Quellen-Labels (Etappe C, #264) ────────────

/**
 * Klartext-Labels für die `quelle`-Felder der Speicher-KPIs (effektiver
 * Ladepreis, η-IST). Roh-Enum-Werte gehören nie in die UI — diese Maps sind
 * die Spiegel-Vorlage zum Backend (`speicher_wirtschaftlichkeit.py`).
 */
export const LADEPREIS_QUELLE_LABELS: Record<string, string> = {
  'dyn-tarif': 'dyn. Tarif',
  'boersenpreis': 'Börsenpreis',
  // Festpreis-Tarif: kein stündlicher Ladepreis ermittelbar, die Kosten laufen
  // über den Arbeitspreis. NICHT „Datenbasis dünn" — es fehlt nichts.
  'kein-dyn-tarif': 'Festpreis-Tarif',
  'datenbasis-zu-duenn': 'Datenbasis dünn',
  'keine-netzladung': 'keine Netzladung',
  'keine-tep-daten': 'keine Profildaten',
  'bezugspreis-fallback': 'Bezugspreis',
  'param': 'Parameter',
}

/**
 * Herkunft des Netzladungs-Preises (Backend `speicher_ladung_netz_preis_quelle`,
 * Preis-Kette in `core/berechnungen/speicher_wirtschaftlichkeit.py`). Als
 * Halbsatz formuliert — die Kachel setzt ihn in Klammern hinter den Kennwert.
 */
export const NETZLADUNG_PREIS_HERKUNFT: Record<string, string> = {
  tep: 'aus der Strompreis-Mitschrift',
  imd: 'aus deiner Eingabe im Monatsabschluss',
  bezugspreis: 'Arbeitspreis deines Tarifs',
  keine: 'keine Netzladung',
}

export const WIRKUNGSGRAD_QUELLE_LABELS: Record<string, string> = {
  'fenster_lang': 'Langzeit-Messung',
  'soc_korrigiert': 'SoC-korrigiert',
  'fenster-zu-kurz': 'Fenster zu kurz',
  'keine-ladung': 'keine Ladung',
  'param': 'Parameter',
}

/** Quellen, deren KPI-Wert belastbar ist (Badge neutral statt amber). */
export const QUELLE_BELASTBAR: ReadonlySet<string> = new Set([
  'dyn-tarif', 'boersenpreis', 'fenster_lang', 'soc_korrigiert',
])

/** Werte-Quelle der Solar-Prognose-Anzeige (Backend `anzeige_quelle`).
 *  Beschriftung muss zur Zahl passen: wo der eedc-korrigierte Wert steht, darf
 *  nicht „Open-Meteo" darüberstehen — und beim Fallback nicht „eedc". */
export const PROGNOSE_QUELLE_LABEL: Record<string, string> = {
  'eedc': 'eedc-Prognose (Open-Meteo + Korrektur)',
  'openmeteo': 'Open-Meteo (ohne Korrektur)',
  'gemischt': 'teils eedc-Prognose, teils Open-Meteo',
}

// ─── Sonstige Konstanten ─────────────────────────────────────────────────────

/** CO2-Emissionsfaktor Strommix Deutschland (kg CO2 pro kWh). */
export const CO2_FAKTOR_KG_KWH = 0.38
