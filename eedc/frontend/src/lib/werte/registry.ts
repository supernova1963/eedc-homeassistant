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

export type WerteGruppe = 'basis' | 'quoten' | 'wetter' | 'speicher' | 'waermepumpe' | 'eauto' | 'sonstiges' | 'finanzen' | 'co2' | 'tagdetail' | 'erzeuger' | 'zaehler'
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
  // ⚠ `aggregation: 'none'` — eine Arbeitszahl ist ein Quotient und wird NICHT
  // gemittelt. Bis 02.09.2026 stand hier `'avg'`, und der Fuss zeigte den
  // Durchschnitt der Monatswerte: an einer realen Anlage **Ø 2,5**, waehrend die
  // Jahresarbeitszahl derselben Zeilen (Sigma Waerme / Sigma Strom) **2,66** ist —
  // zwei Wahrheiten in einer Tabelle. Dieselbe Entscheidung wie bei der
  // Grundlast-Spalte (01.09.), aus demselben Grund.
  { key: 'wp_cop',             label: 'WP COP',            unit: '',        gruppe: 'waermepumpe', decimals: 1, aggregation: 'none', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: true },
  // E-Auto — kein sauberer Tages-Wert (km/Lade-Split) → monat-only
  { key: 'eauto_km',           label: 'E-Auto',            unit: 'km',      gruppe: 'eauto',       decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: undefined },
  { key: 'eauto_ladung',       label: 'E-Auto Ladung',     unit: 'kWh',     gruppe: 'eauto',       decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: undefined },
  { key: 'wallbox_ladung',     label: 'Wallbox Ladung',    unit: 'kWh',     gruppe: 'eauto',       decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: undefined },
  { key: 'wallbox_pv_ladung',  label: 'Wallbox PV-Ladung', unit: 'kWh',     gruppe: 'eauto',       decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: true },
  { key: 'wallbox_pv_anteil',  label: 'Wallbox PV-Anteil', unit: '%',       gruppe: 'eauto',       decimals: 1, aggregation: 'avg', defaultVisible: false, granular: NUR_MONAT, higherIsBetter: true },
  // Sonstiges (BHKW, Heizstab, Pool …) — Melder rapahl, 2026-08-14: ohne diese
  // Spalten ließ sich nicht prüfen, ob die gepflegten Werte eines
  // Sonstiges-Geräts überhaupt ankommen. Bewusst **nicht** `defaultVisible`:
  // wählbar, nicht vorgegeben.
  //
  // ⚠ Die Namen tragen die Einheit, und das ist Absicht (#377 Gas/Öl/Wasser):
  // ein Gas- oder Wasserzähler bringt m³ bzw. l ohne kWh-Bezug. Eine generisch
  // „Sonstiges" genannte Spalte hätte diese Fläche belegt; so bekommt #377
  // eigene Spalten mit eigener Einheit in **derselben Gruppe**.
  //
  // ⚠ Tag und Monat speisen sich aus verschiedenen Quellen: der Monat aus den
  // gepflegten `InvestitionMonatsdaten` (P10-Schicht), der Tag aus dem
  // Komponenten-JSON — dort steht nur, was einen eigenen Sensor hat. Ein nur
  // monatlich gepflegtes Gerät hat deshalb eine Monats- und keine Tageszahl;
  // Σ Tage ≠ Monat ist hier der Normalfall, nicht der Fehler.
  { key: 'sonstiges_erzeugung', label: 'Sonstiges Erzeugung', unit: 'kWh',   gruppe: 'sonstiges',   decimals: 1, aggregation: 'sum', defaultVisible: false, granular: MONAT_TAG, higherIsBetter: true },
  { key: 'sonstiges_verbrauch', label: 'Sonstiges Verbrauch', unit: 'kWh',   gruppe: 'sonstiges',   decimals: 1, aggregation: 'sum', defaultVisible: false, granular: MONAT_TAG, higherIsBetter: undefined },
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
  // Grundlast je Nacht (OB73-gif, #395): der Nacht-Sockel EINES Tages, damit
  // sich ablesen laesst, was ein ueber Nacht abgeschaltetes Geraet bringt. Im
  // Tages-Gesamtverbrauch geht das unter — 50 W ueber acht Stunden sind 0,4 kWh.
  //
  // ⛔ `aggregation: 'none'` wie bei den Peaks, und das ist der Kern: Ein
  // Median laesst sich nicht summieren, und der Durchschnitt der Tagesmediane
  // waere NICHT die Grundlast, die Cockpit → Monat nennt (dort ist es der
  // Median ueber alle Nachtstunden des Monats). Ohne Aggregat gibt es die
  // zweite Zahl gar nicht erst.
  { key: 'grundlast_kw',           label: 'Grundlast',      unit: 'kW',     gruppe: 'tagdetail',   decimals: 2, aggregation: 'none', defaultVisible: false, granular: NUR_TAG, higherIsBetter: false },
  { key: 'performance_ratio',      label: 'Performance Ratio', unit: '',    gruppe: 'tagdetail',   decimals: 2, aggregation: 'avg', defaultVisible: false, granular: NUR_TAG, higherIsBetter: true },
  { key: 'batterie_vollzyklen',    label: 'SoC-Hübe', unit: '',     gruppe: 'tagdetail',   decimals: 2, aggregation: 'sum', defaultVisible: false, granular: NUR_TAG, higherIsBetter: undefined },
  { key: 'boersenpreis_avg_cent',  label: 'Börsenpreis Ø',  unit: 'ct/kWh', gruppe: 'tagdetail',   decimals: 2, aggregation: 'avg', defaultVisible: false, granular: NUR_TAG, higherIsBetter: false },
  { key: 'negative_preis_stunden', label: 'Neg. Preisstd.', unit: 'h',      gruppe: 'tagdetail',   decimals: 0, aggregation: 'sum', defaultVisible: false, granular: NUR_TAG, higherIsBetter: undefined },
  { key: 'einspeisung_neg_preis_kwh', label: 'Einsp. neg. Preis', unit: 'kWh', gruppe: 'tagdetail', decimals: 1, aggregation: 'sum', defaultVisible: false, granular: NUR_TAG, higherIsBetter: undefined },
  { key: 'temperatur_max_c',       label: 'Temp. max',      unit: '°C',     gruppe: 'tagdetail',   decimals: 1, aggregation: 'avg', defaultVisible: false, granular: NUR_TAG, higherIsBetter: undefined },
]

export const WERTE_GRUPPEN: WerteGruppe[] = ['basis', 'quoten', 'wetter', 'speicher', 'waermepumpe', 'eauto', 'sonstiges', 'finanzen', 'co2', 'tagdetail', 'erzeuger', 'zaehler']

export const GRUPPE_LABELS: Record<WerteGruppe, string> = {
  basis:       'Energie',
  quoten:      'Quoten',
  wetter:      'Wetter',
  speicher:    'Speicher',
  waermepumpe: 'Wärmepumpe',
  eauto:       'E-Auto',
  sonstiges:   'Sonstiges',
  finanzen:    'Finanzen',
  co2:         'CO₂',
  tagdetail:   'Tagesdetail',
  erzeuger:    'Je Erzeuger',
  // #377 — je Gerät, weil ein Zählerstand sich über nichts summiert.
  zaehler:     'Zählerstände',
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

/** Präfix der dynamischen Zähler-Spalten (`zaehler:7`) — kein flaches Feld der
 *  Antwort-Zeile, sondern ein Zugriff in `zaehler_stand` (#377). */
export const ZAEHLER_METRIK_PREFIX = 'zaehler:'

/**
 * Spalten „Zählerstand je Gerät" (#377) — **eine Spalte je Verbrauchszähler**.
 *
 * ⚑ **Warum je Gerät, obwohl jede andere Metrik hier eine anlagenweite Summe
 * ist:** Alle bestehenden Metriken sind **Fluss**größen — kWh, km, €. Sie
 * summieren sich über Geräte und über die Zeit, deshalb trägt dort eine
 * gemeinsame Spalte. Ein Zählerstand ist eine **Bestands**größe und summiert
 * sich über **nichts**: zwei Gaszähler mit 12.345 und 8.900 ergeben nicht
 * 21.245, auch nicht bei gleicher Einheit. Die Registry-Konvention ist auf
 * Flussgrößen zugeschnitten; hier fällt der Wert nicht wegen seiner Einheit
 * heraus, sondern wegen seiner **Größenart**.
 *
 * Daraus folgt der Rest von selbst: `aggregation: 'none'` (die Fußzeile bleibt
 * leer, statt eine sinnlose Summe oder einen sinnlosen Durchschnitt zu zeigen)
 * und `unit` je Gerät statt fest — ein Haushalt kann Gas in m³ und Öl in Litern
 * führen. Und die Frage nach gemischten Einheiten in EINER Spalte stellt sich
 * gar nicht erst.
 *
 * Wie bei {@link erzeugerMetriken} (#350) bewusst **nicht** `defaultVisible`:
 * wer drei Zähler pflegt, bekommt sonst drei Spalten ungefragt dazu.
 */
export function zaehlerMetriken(
  zaehler: { id: number | string; name: string; einheit: string }[],
): WerteMetrik[] {
  return zaehler.map((z) => ({
    key: `${ZAEHLER_METRIK_PREFIX}${z.id}`,
    label: z.name,
    unit: z.einheit,
    gruppe: 'zaehler' as WerteGruppe,
    decimals: 1,
    aggregation: 'none' as WerteAggregation,
    defaultVisible: false,
    granular: MONAT_TAG,
    // Ein Zählerstand steigt immer — „höher ist besser" wäre hier keine
    // Bewertung, sondern eine Selbstverständlichkeit. Bewusst offen gelassen.
    higherIsBetter: undefined,
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
  if (key.startsWith(ZAEHLER_METRIK_PREFIX)) {
    // #377: Der Stand liegt nicht flach in der Zeile, sondern in
    // `zaehler_stand` (Investitions-ID → Stand). Fehlt der Eintrag, wurde in
    // diesem Monat nichts abgelesen — `null` (Display-Token „—"), nicht 0:
    // eine 0 hieße „der Zähler steht auf null".
    const v = row.zaehler_stand?.[key.slice(ZAEHLER_METRIK_PREFIX.length)]
    return v == null ? null : v
  }
  const v = (row as unknown as Record<string, number | null | undefined>)[key]
  return v == null ? null : v
}

/**
 * Granularitäts-Accessor „Tag": liest den Spalten-Wert aus einer `TagWerte`-
 * Zeile (Backend-Tages-Werte-Endpoint). Die Feldnamen sind deckungsgleich mit
 * den Registry-keys (analog `getMonatWert`).
 */
export function getTagWert(row: TagWerte, key: string): number | null {
  if (key.startsWith(ZAEHLER_METRIK_PREFIX)) {
    // #377 — s. `getMonatWert`: Stand statt Menge, `null` statt 0.
    const v = row.zaehler_stand?.[key.slice(ZAEHLER_METRIK_PREFIX.length)]
    return v == null ? null : v
  }
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
