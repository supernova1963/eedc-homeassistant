/**
 * W1 — Metrik-Registry (Werte/Tabelle-SoT, IA v4 E3 Slice 3.1).
 *
 * Eine Quelle der Wahrheit für alle tabellarischen Kennzahl-Spalten: Label,
 * Einheit, Format, Aggregation, Gruppe und Richtung („mehr ist besser").
 * Verhaltensgleich aus `pages/auswertung/TabelleTab.tsx` (23 Spalten)
 * herausgelöst — die Werkbank UND die read-only Embeds (Cockpit-Zeitsichten,
 * Komponenten) speisen sich künftig aus dieser Registry.
 *
 * Granularitäts-Naht: aktuell nur der Monats-Accessor `getMonatWert`. Tag/
 * Stunde (`get.tag`/`get.stunde`) docken später an dieselbe Registry an
 * (Plan 3.2), ohne die Spalten-Definition zu duplizieren.
 */
import type { MonatsZeitreihe } from '../../pages/auswertung/types'
import type { TagWerte } from '../../api/energie_profil'

export type WerteGruppe = 'basis' | 'quoten' | 'wetter' | 'speicher' | 'waermepumpe' | 'eauto' | 'finanzen' | 'co2' | 'tagdetail' | 'erzeuger'
export type WerteAggregation = 'sum' | 'avg' | 'none'

/**
 * Zeit-Granularität einer Werte-Sicht. Der verfügbare Metrik-Satz **unterscheidet
 * sich** je Granularität (IA v4 E3 O1-Nuance): der Monat trägt saubere
 * Bilanz+Finanzen, der Tag zusätzlich Peaks/PR/Überschuss/Börsenpreis, aber
 * keine WP-Wärme/COP/E-Auto-Kilometer (kein sauberer Tages-Wert). `granular`
 * je Metrik kodiert das.
 */
export type Granularitaet = 'monat' | 'tag'

export interface WerteMetrik {
  key: string
  label: string
  unit: string
  gruppe: WerteGruppe
  decimals: number
  aggregation: WerteAggregation
  defaultVisible: boolean
  /** In welchen Granularitäten verfügbar (mind. eine). */
  granular: Granularitaet[]
  /** true=höher besser, false=niedriger besser, undefined=neutral (Δ grau). */
  higherIsBetter?: boolean
}

const MONAT_TAG: Granularitaet[] = ['monat', 'tag']
const NUR_MONAT: Granularitaet[] = ['monat']
const NUR_TAG: Granularitaet[] = ['tag']

// Reihenfolge + Werte 1:1 aus TabelleTab.COLUMNS (verhaltensgleich).
// `granular`: Monat+Tag, wenn das Backend den Wert pro Tag sauber liefert
// (Tages-Werte-Endpoint, Σ stündl. TEP); nur-Monat bei fehlendem Tages-Wert
// (WP-Wärme/COP, E-Auto). Tag-native Metriken (Peaks/PR/Börsenpreis) stehen im
// Block `tagdetail` und erscheinen nur in Tagessichten.
export const WERTE_METRIKEN: WerteMetrik[] = [
  // Energie
  { key: 'erzeugung',          label: 'PV-Erzeugung',      unit: 'kWh',     gruppe: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: true,  granular: MONAT_TAG, higherIsBetter: true },
  { key: 'eigenverbrauch',     label: 'Eigenverbrauch',    unit: 'kWh',     gruppe: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: true,  granular: MONAT_TAG, higherIsBetter: true },
  { key: 'einspeisung',        label: 'Einspeisung',       unit: 'kWh',     gruppe: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: true,  granular: MONAT_TAG, higherIsBetter: true },
  { key: 'netzbezug',          label: 'Netzbezug',         unit: 'kWh',     gruppe: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: true,  granular: MONAT_TAG, higherIsBetter: false },
  { key: 'gesamtverbrauch',    label: 'Gesamtverbrauch',   unit: 'kWh',     gruppe: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: false, granular: MONAT_TAG, higherIsBetter: undefined },
  { key: 'direktverbrauch',    label: 'Direktverbrauch',   unit: 'kWh',     gruppe: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: false, granular: MONAT_TAG, higherIsBetter: true },
  // Quoten
  { key: 'autarkie',           label: 'Autarkie',          unit: '%',       gruppe: 'quoten',      decimals: 1, aggregation: 'avg', defaultVisible: true,  granular: MONAT_TAG, higherIsBetter: true },
  { key: 'evQuote',            label: 'EV-Quote',          unit: '%',       gruppe: 'quoten',      decimals: 1, aggregation: 'avg', defaultVisible: true,  granular: MONAT_TAG, higherIsBetter: true },
  { key: 'spezErtrag',         label: 'Spez. Ertrag',      unit: 'kWh/kWp', gruppe: 'quoten',      decimals: 0, aggregation: 'sum', defaultVisible: false, granular: MONAT_TAG, higherIsBetter: true },
  // Wetter (Einstrahlungs-Kontext, verfügbar wenn Wetterdaten erfasst)
  { key: 'globalstrahlung',    label: 'Globalstrahlung',   unit: 'kWh/m²',  gruppe: 'wetter',      decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: undefined },
  { key: 'sonnenstunden',      label: 'Sonnenstunden',     unit: 'h',       gruppe: 'wetter',      decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: undefined },
  // Speicher
  { key: 'speicher_ladung',    label: 'Speicher Ladung',    unit: 'kWh',    gruppe: 'speicher',    decimals: 0, aggregation: 'sum', defaultVisible: false, granular: MONAT_TAG, higherIsBetter: undefined },
  { key: 'speicher_entladung', label: 'Speicher Entladung', unit: 'kWh',    gruppe: 'speicher',    decimals: 0, aggregation: 'sum', defaultVisible: false, granular: MONAT_TAG, higherIsBetter: undefined },
  { key: 'speicher_effizienz', label: 'Speicher Effizienz', unit: '%',      gruppe: 'speicher',    decimals: 1, aggregation: 'avg', defaultVisible: false, granular: MONAT_TAG, higherIsBetter: true },
  // Wärmepumpe — nur Strom pro Tag ableitbar; Wärme/COP bleiben monat-only
  { key: 'wp_strom',           label: 'WP Strom',          unit: 'kWh',     gruppe: 'waermepumpe', decimals: 0, aggregation: 'sum', defaultVisible: false, granular: MONAT_TAG, higherIsBetter: undefined },
  { key: 'wp_strom_heizen',    label: 'WP Strom Heizen',   unit: 'kWh',     gruppe: 'waermepumpe', decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: undefined },
  { key: 'wp_strom_warmwasser',label: 'WP Strom WW',       unit: 'kWh',     gruppe: 'waermepumpe', decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: undefined },
  { key: 'wp_waerme',          label: 'WP Wärme',          unit: 'kWh',     gruppe: 'waermepumpe', decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: true },
  { key: 'wp_waerme_heizen',   label: 'WP Wärme Heizen',   unit: 'kWh',     gruppe: 'waermepumpe', decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: true },
  { key: 'wp_waerme_warmwasser',label: 'WP Wärme WW',      unit: 'kWh',     gruppe: 'waermepumpe', decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: true },
  { key: 'wp_cop',             label: 'WP COP',            unit: '',        gruppe: 'waermepumpe', decimals: 1, aggregation: 'avg', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: true },
  // E-Auto — kein sauberer Tages-Wert (km/Lade-Split) → monat-only
  { key: 'eauto_km',           label: 'E-Auto',            unit: 'km',      gruppe: 'eauto',       decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: undefined },
  { key: 'eauto_ladung',       label: 'E-Auto Ladung',     unit: 'kWh',     gruppe: 'eauto',       decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: undefined },
  { key: 'wallbox_ladung',     label: 'Wallbox Ladung',    unit: 'kWh',     gruppe: 'eauto',       decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: undefined },
  { key: 'wallbox_pv_ladung',  label: 'Wallbox PV-Ladung', unit: 'kWh',     gruppe: 'eauto',       decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: true },
  { key: 'wallbox_pv_anteil',  label: 'Wallbox PV-Anteil', unit: '%',       gruppe: 'eauto',       decimals: 1, aggregation: 'avg', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: true },
  // Finanzen — Berechnung via createMonatsZeitreihe mit historisch korrektem Tarif pro Monat
  { key: 'einspeise_erloes',   label: 'Einspeise-Erlös',   unit: '€',       gruppe: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: true,  granular: MONAT_TAG, higherIsBetter: true },
  { key: 'ev_ersparnis',       label: 'EV-Ersparnis',      unit: '€',       gruppe: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: true,  granular: MONAT_TAG, higherIsBetter: true },
  { key: 'netzbezug_kosten',   label: 'Netzbezug-Kosten',  unit: '€',       gruppe: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: true,  granular: MONAT_TAG, higherIsBetter: false },
  // „(PV)" grenzt gegen die T-Konto-Ergebniszeile ab (Gewinn/Verlust Haushalt):
  // hier ohne Netzbezug-Kosten und ohne WP/E-Mobilität. Wortgleich zur
  // Finanz-Seite (AuswertungenFinanzenV4), sonst zwei Namen für eine Zahl.
  // ⚠ Der Monatswert trägt seit N-22 die **USt auf Eigenverbrauch** abgezogen
  // (Regelbesteuerung; sonst 0), der Tageswert nicht — die USt ist eine
  // Jahresgröße (Selbstkosten je kWh aus Investition und Jahres-Erzeugung), sie
  // lässt sich einem Tag nicht zuordnen. Bei Regelbesteuerung gilt deshalb
  // Σ Tage ≠ Monat, wie bei der CO₂-Spalte. Die Spalte daneben macht es sichtbar.
  { key: 'netto_ertrag',       label: 'Netto-Ertrag (PV)', unit: '€',       gruppe: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: false, granular: MONAT_TAG, higherIsBetter: true },
  { key: 'ust_eigenverbrauch', label: 'USt Eigenverbrauch', unit: '€',      gruppe: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: false },
  { key: 'netto_bilanz',       label: 'Netto-Bilanz',      unit: '€',       gruppe: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: true,  granular: MONAT_TAG, higherIsBetter: true },
  { key: 'netzbezug_preis_cent', label: 'Ø Netzpreis',     unit: 'ct/kWh',  gruppe: 'finanzen',    decimals: 2, aggregation: 'avg', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: false },
  // CO₂ — „(PV)" grenzt gegen die vollständige Bilanz ab, wie „Netto-Ertrag (PV)"
  // gegen das T-Konto: hier steht der PV-Anteil (Eigenverbrauch × Strommix,
  // Layer-SoT `berechne_co2_bilanz`), OHNE Wärmepumpe und E-Mobilität. Nur der
  // ist über beide Granularitäten summierbar — am Tag sind WP-Wärme und
  // E-Mob-Kilometer nicht gemessen. Die volle Bilanz (PV + WP + E-Mob) zeigen
  // Cockpit → Jahr und Auswertungen → CO₂.
  { key: 'co2_einsparung',     label: 'CO₂-Einsparung (PV)', unit: 'kg',    gruppe: 'co2',         decimals: 1, aggregation: 'sum', defaultVisible: false, granular: MONAT_TAG, higherIsBetter: true },
  // ── Tag-native Zusatzmetriken (kein Monats-Pendant, nur Tagessichten) ──
  { key: 'ueberschuss_kwh',        label: 'Überschuss',     unit: 'kWh',    gruppe: 'tagdetail',   decimals: 1, aggregation: 'sum', defaultVisible: true,  granular: NUR_TAG, higherIsBetter: undefined },
  { key: 'defizit_kwh',            label: 'Defizit',        unit: 'kWh',    gruppe: 'tagdetail',   decimals: 1, aggregation: 'sum', defaultVisible: false, granular: NUR_TAG, higherIsBetter: false },
  { key: 'peak_pv_kw',             label: 'Peak PV',        unit: 'kW',     gruppe: 'tagdetail',   decimals: 2, aggregation: 'none', defaultVisible: true, granular: NUR_TAG, higherIsBetter: undefined },
  { key: 'peak_netzbezug_kw',      label: 'Peak Bezug',     unit: 'kW',     gruppe: 'tagdetail',   decimals: 2, aggregation: 'none', defaultVisible: false, granular: NUR_TAG, higherIsBetter: false },
  { key: 'peak_einspeisung_kw',    label: 'Peak Einsp.',    unit: 'kW',     gruppe: 'tagdetail',   decimals: 2, aggregation: 'none', defaultVisible: false, granular: NUR_TAG, higherIsBetter: undefined },
  { key: 'performance_ratio',      label: 'Performance Ratio', unit: '',    gruppe: 'tagdetail',   decimals: 2, aggregation: 'avg', defaultVisible: false, granular: NUR_TAG, higherIsBetter: true },
  { key: 'batterie_vollzyklen',    label: 'SoC-Hübe', unit: '',     gruppe: 'tagdetail',   decimals: 2, aggregation: 'sum', defaultVisible: false, granular: NUR_TAG, higherIsBetter: undefined },
  { key: 'boersenpreis_avg_cent',  label: 'Börsenpreis Ø',  unit: 'ct/kWh', gruppe: 'tagdetail',   decimals: 2, aggregation: 'avg', defaultVisible: false, granular: NUR_TAG, higherIsBetter: false },
  { key: 'negative_preis_stunden', label: 'Neg. Preisstd.', unit: 'h',      gruppe: 'tagdetail',   decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_TAG, higherIsBetter: undefined },
  { key: 'einspeisung_neg_preis_kwh', label: 'Einsp. neg. Preis', unit: 'kWh', gruppe: 'tagdetail', decimals: 1, aggregation: 'sum', defaultVisible: false, granular: NUR_TAG, higherIsBetter: undefined },
  { key: 'temperatur_max_c',       label: 'Temp. max',      unit: '°C',     gruppe: 'tagdetail',   decimals: 1, aggregation: 'avg', defaultVisible: false, granular: NUR_TAG, higherIsBetter: undefined },
]

export const WERTE_GRUPPEN: WerteGruppe[] = ['basis', 'quoten', 'wetter', 'speicher', 'waermepumpe', 'eauto', 'finanzen', 'co2', 'tagdetail', 'erzeuger']

export const GRUPPE_LABELS: Record<WerteGruppe, string> = {
  basis:       'Energie',
  quoten:      'Quoten',
  wetter:      'Wetter',
  speicher:    'Speicher',
  waermepumpe: 'Wärmepumpe',
  eauto:       'E-Auto',
  finanzen:    'Finanzen',
  co2:         'CO₂',
  tagdetail:   'Tagesdetail',
  erzeuger:    'Je Erzeuger',
}

/** Präfix der dynamischen Erzeuger-Spalten (`erzeuger:7`) — kein Feld der
 *  Antwort-Zeile, sondern ein Zugriff in `TagWerte.erzeuger_kwh`. */
export const ERZEUGER_METRIK_PREFIX = 'erzeuger:'

/**
 * Spalten „Ertrag je Erzeuger" (#350, Rainer) — eine Metrik je PV-String bzw.
 * Balkonkraftwerk, gebaut aus den Investitionen, die im geladenen Zeitraum
 * überhaupt Tageswerte haben.
 *
 * Warum dynamisch statt in {@link WERTE_METRIKEN}: die Spalten hängen an der
 * Anlage, nicht am Produkt. Sie sind bewusst **nicht** `defaultVisible` — wer
 * fünf Strings hat, bekommt sonst fünf Spalten ungefragt dazu; der Spalten-
 * Picker führt sie unter „Je Erzeuger".
 */
export function erzeugerMetriken(
  erzeuger: { id: number | string; bezeichnung: string }[],
): WerteMetrik[] {
  return erzeuger.map((e) => ({
    key: `${ERZEUGER_METRIK_PREFIX}${e.id}`,
    label: e.bezeichnung,
    unit: 'kWh',
    gruppe: 'erzeuger' as WerteGruppe,
    decimals: 1,
    aggregation: 'sum' as WerteAggregation,
    defaultVisible: false,
    granular: NUR_TAG,
    higherIsBetter: true,
  }))
}

/** Metriken, die in der gegebenen Granularität verfügbar sind (Reihenfolge erhalten). */
export function metrikenFuer(granularitaet: Granularitaet): WerteMetrik[] {
  return WERTE_METRIKEN.filter((m) => m.granular.includes(granularitaet))
}

/** Schnell-Lookup Metrik per key. */
export const METRIK_BY_KEY: Record<string, WerteMetrik> = Object.fromEntries(
  WERTE_METRIKEN.map((m) => [m.key, m]),
)

/**
 * Granularitäts-Accessor „Monat": liest den Spalten-Wert aus einer
 * `MonatsZeitreihe`-Zeile. Die Registry-keys sind deckungsgleich mit den
 * Zeilen-Properties (verhaltensgleich zu TabelleTab `row[col.key]`).
 */
export function getMonatWert(row: MonatsZeitreihe, key: string): number | null {
  const v = (row as unknown as Record<string, number | null | undefined>)[key]
  return v == null ? null : v
}

/**
 * Granularitäts-Accessor „Tag": liest den Spalten-Wert aus einer `TagWerte`-
 * Zeile (Backend-Tages-Werte-Endpoint). Die Feldnamen sind deckungsgleich mit
 * den Registry-keys (analog `getMonatWert`).
 */
export function getTagWert(row: TagWerte, key: string): number | null {
  if (key.startsWith(ERZEUGER_METRIK_PREFIX)) {
    // Erzeuger-Spalten liegen nicht flach in der Zeile, sondern in
    // `erzeuger_kwh` (Investitions-ID → kWh). Fehlt der Eintrag, ist an dem Tag
    // für dieses Gerät **nichts gemessen** — `null` (das Display-Token „—"),
    // nicht 0: eine 0 hieße „lief, brachte nichts".
    const v = row.erzeuger_kwh?.[key.slice(ERZEUGER_METRIK_PREFIX.length)]
    return v == null ? null : v
  }
  const v = (row as unknown as Record<string, number | null | undefined>)[key]
  return v == null ? null : v
}
