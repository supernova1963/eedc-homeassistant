/**
 * Typgebundene Fixture-Factories für die Frontend-Tests (Etappe E5 / M8).
 *
 * **Warum es sie gibt.** `AktuellerMonatResponse` hat 88 Pflichtfelder,
 * `AggregierteMonatsdaten` und `TagWerte` je 42. Kein Test schreibt das aus —
 * deshalb stand in 38 Testdateien `as unknown as X` (66 Stellen, gemessen
 * 2026-08-24). Ein solcher Cast **entkoppelt die Fixture vom Typsystem**: ein
 * umbenanntes oder neu hinzugekommenes Pflichtfeld im API-Client bricht keinen
 * dieser Tests. Genau das soll hier aufhören.
 *
 * **Wie die Bindung entsteht.** Das Basisobjekt erfüllt den Typ per
 * `satisfies` — es *muss* vollständig sein, sonst meldet `tsc`. Der Aufrufer
 * gibt nur seine Abweichung als `Partial<T>`; ein Tippfehler darin ist ein
 * Compile-Fehler (overschüssige Property gegen `Partial`), kein stiller
 * `undefined`-Wert mehr.
 *
 * **Die Defaults behaupten nichts.** Jede Menge steht auf ihrer Nullstellung:
 * `null` wo der Typ sie zulässt („nicht gemessen"), sonst `0`/`false`/`{}`/`[]`.
 * Es gibt **keine plausiblen Beispielzahlen** — ein Test, der eine Zahl
 * behauptet, muss sie selbst gesetzt haben. Dieselbe Regel wie im Backend
 * (`backend/tests/factories.py`): Defaults nur für das technisch Nötige.
 * Die einzige Setzung mit Bedeutung ist `emob_verbrauch_quelle: 'keine'` —
 * der Typ lässt kein `null` zu, und `'keine'` ist dort die Nullstellung.
 *
 * **Die Identität ist Parameter, kein Default.** Jahr/Monat bzw. Datum stehen
 * in der Signatur, damit keine Fixture stillschweigend im Monat 0 liegt.
 *
 * ⚠ **Nullstellung ist nicht `undefined`.** Ein handgebauter Cast ließ die
 * ungenannten Felder `undefined`; hier stehen sie auf `null`/`0`. Für `??`
 * ist das gleich, für `!== undefined` und `Object.keys` nicht. Wer eine
 * Bestandsdatei umhängt, prüft ihre Fallzahl vor und nach dem Eingriff.
 */
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import type { TagWerte } from '../api/energie_profil'

const MONATSNAMEN = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
] as const

const MONAT_BASIS = {
  anlage_id: 0,
  anlage_name: '',
  jahr: 0,
  monat: 0,
  monat_name: '',
  aktualisiert_um: '',
  quellen: {},
  pv_erzeugung_kwh: null,
  einspeisung_kwh: null,
  netzbezug_kwh: null,
  eigenverbrauch_kwh: null,
  direktverbrauch_kwh: null,
  gesamtverbrauch_kwh: null,
  autarkie_prozent: null,
  eigenverbrauch_quote_prozent: null,
  speicher_ladung_kwh: null,
  speicher_entladung_kwh: null,
  speicher_ladung_netz_kwh: null,
  speicher_wirkungsgrad_prozent: null,
  speicher_vollzyklen: null,
  speicher_kapazitaet_kwh: null,
  hat_speicher: false,
  speicher_wirkungsgrad_quelle: null,
  speicher_soc_drift_signifikant: false,
  speicher_effektiver_ladepreis_cent: null,
  speicher_effektiver_ladepreis_quelle: null,
  speicher_ladung_netz_kosten_euro: null,
  speicher_ladung_netz_preis_cent: null,
  speicher_ladung_netz_preis_quelle: null,
  speicher_auslastungs_basis_kwh: null,
  speicher_auslastung_prozent: null,
  speicher_ersparnis_euro: null,
  wp_strom_kwh: null,
  wp_waerme_kwh: null,
  wp_heizung_kwh: null,
  wp_warmwasser_kwh: null,
  wp_strom_heizen_kwh: null,
  wp_strom_warmwasser_kwh: null,
  wp_starts_max_tag: null,
  wp_starts_summe_monat: null,
  wp_betriebsstunden_max_tag: null,
  wp_betriebsstunden_summe_monat: null,
  hat_waermepumpe: false,
  emob_ladung_kwh: null,
  emob_km: null,
  emob_verbrauch_100km: null,
  emob_verbrauch_quelle: 'keine',
  emob_ladung_pv_kwh: null,
  emob_ladung_netz_kwh: null,
  emob_ladung_extern_kwh: null,
  emob_v2h_kwh: null,
  hat_emobilitaet: false,
  bkw_erzeugung_kwh: null,
  bkw_eigenverbrauch_kwh: null,
  hat_balkonkraftwerk: false,
  sonstiges_erzeugung_kwh: null,
  sonstiges_eigenverbrauch_kwh: null,
  sonstiges_einspeisung_kwh: null,
  sonstiges_verbrauch_kwh: null,
  sonstiges_bezug_pv_kwh: null,
  sonstiges_bezug_netz_kwh: null,
  hat_sonstiges: false,
  einspeise_erloes_euro: null,
  einspeisung_neg_preis_kwh: null,
  nicht_vergueteter_erloes_euro: null,
  netzbezug_kosten_euro: null,
  netzbezug_arbeitspreis_kosten_euro: null,
  ev_ersparnis_euro: null,
  netto_ertrag_euro: null,
  wp_ersparnis_euro: null,
  emob_ersparnis_euro: null,
  sonstige_ertraege_euro: 0,
  sonstige_ausgaben_euro: 0,
  sonstige_netto_euro: 0,
  anlage_sonstige_ertraege_euro: 0,
  anlage_sonstige_ausgaben_euro: 0,
  gesamtnettoertrag_euro: null,
  betriebskosten_anteilig_euro: null,
  netzbezug_preis_cent: null,
  einspeise_preis_cent: null,
  netzbezug_durchschnittspreis_cent: null,
  grundgebuehr_euro: null,
  zaehlergebuehr_euro_jahr: null,
  vorjahr: null,
  soll_pv_kwh: null,
  investitionen_financials: [],
  komponenten_geraete: {},
  feld_quellen: {},
} satisfies AktuellerMonatResponse

const ZEILE_BASIS = {
  id: null,
  anlage_id: 0,
  jahr: 0,
  monat: 0,
  einspeisung_kwh: 0,
  netzbezug_kwh: 0,
  globalstrahlung_kwh_m2: null,
  sonnenstunden: null,
  pv_erzeugung_kwh: null,
  pv_module_kwh: null,
  bkw_kwh: null,
  sonstige_erzeugung_kwh: null,
  sonstige_verbrauch_kwh: null,
  erzeugung_hinter_zaehler_kwh: null,
  speicher_ladung_kwh: null,
  speicher_entladung_kwh: null,
  speicher_netzladung_kwh: null,
  wp_strom_kwh: null,
  wp_strom_heizen_kwh: null,
  wp_strom_warmwasser_kwh: null,
  wp_heizung_kwh: null,
  wp_warmwasser_kwh: null,
  eauto_ladung_kwh: null,
  eauto_km: null,
  wallbox_ladung_kwh: null,
  wallbox_ladung_pv_kwh: null,
  direktverbrauch_kwh: 0,
  eigenverbrauch_kwh: 0,
  gesamtverbrauch_kwh: 0,
  autarkie_prozent: 0,
  eigenverbrauchsquote_prozent: 0,
  einspeisung_neg_preis_kwh: null,
  einspeise_erloes_euro: 0,
  einspeise_nicht_verguetet_euro: 0,
  ev_ersparnis_euro: 0,
  bkw_ersparnis_euro: 0,
  ust_eigenverbrauch_euro: 0,
  netzbezug_kosten_euro: 0,
  netto_ertrag_euro: 0,
  netto_bilanz_euro: 0,
  netzbezug_preis_cent: 0,
  hat_legacy_daten: false,
} satisfies AggregierteMonatsdaten

const TAG_BASIS = {
  datum: '',
  stunden_verfuegbar: 0,
  datenquelle: null,
  erzeugung: null,
  pv_anlage: 0,
  bkw: 0,
  eigenverbrauch: null,
  einspeisung: null,
  netzbezug: null,
  gesamtverbrauch: null,
  direktverbrauch: null,
  autarkie: null,
  evQuote: null,
  spezErtrag: null,
  speicher_ladung: null,
  speicher_entladung: null,
  speicher_vollzyklen: null,
  speicher_effizienz: null,
  speicher_effizienz_quelle: null,
  wp_strom: null,
  sonstiges_erzeugung: null,
  sonstiges_verbrauch: null,
  einspeise_erloes: 0,
  ev_ersparnis: null,
  netzbezug_kosten: null,
  netto_ertrag: null,
  netto_bilanz: null,
  co2_einsparung: null,
  ueberschuss_kwh: null,
  defizit_kwh: null,
  peak_pv_kw: null,
  peak_netzbezug_kw: null,
  peak_einspeisung_kw: null,
  grundlast_kw: null,
  performance_ratio: null,
  batterie_vollzyklen: null,
  temperatur_min_c: null,
  temperatur_max_c: null,
  strahlung_summe_wh_m2: null,
  boersenpreis_avg_cent: null,
  boersenpreis_min_cent: null,
  negative_preis_stunden: null,
  einspeisung_neg_preis_kwh: null,
} satisfies TagWerte

/**
 * Eine Monatsantwort (`GET /cockpit/aktueller-monat`) auf Nullstellung.
 * `anlage_id`/`anlage_name` sind gesetzt, weil die Sichten sie als Kopf
 * anzeigen; `monat_name` ist aus `monat` abgeleitet, keine eigene Angabe.
 */
export function aktuellerMonat(
  jahr: number,
  monat: number,
  over: Partial<AktuellerMonatResponse> = {},
): AktuellerMonatResponse {
  return {
    ...MONAT_BASIS,
    anlage_id: 1,
    anlage_name: 'Testanlage',
    jahr,
    monat,
    monat_name: MONATSNAMEN[monat - 1] ?? String(monat),
    ...over,
  }
}

/**
 * Eine Zeile aus `GET /monatsdaten/aggregiert`. `id` bleibt gesetzt
 * (= Monat MIT Zählerzeile); wer einen Monat ohne Monatsabschluss braucht,
 * übergibt `{ id: null }` — das ist dessen ganze Kennzeichnung.
 */
export function monatsZeile(
  jahr: number,
  monat: number,
  over: Partial<AggregierteMonatsdaten> = {},
): AggregierteMonatsdaten {
  return {
    ...ZEILE_BASIS,
    id: jahr * 100 + monat,
    anlage_id: 1,
    jahr,
    monat,
    ...over,
  }
}

/** Ein Tag aus `GET /energie-profil/werte`. `datum` als `YYYY-MM-DD`. */
export function tagWerte(datum: string, over: Partial<TagWerte> = {}): TagWerte {
  return { ...TAG_BASIS, datum, ...over }
}
