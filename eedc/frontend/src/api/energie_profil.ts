import { api } from './client'

export interface SerieInfo {
  key: string
  label: string
  typ: string       // z.B. "sonstiges", "pv-module", "virtual"
  kategorie: string // z.B. "sonstige", "pv", "netz"
  seite: string     // "quelle" | "senke" | "bidirektional"
}

export interface StundenWert {
  stunde: number
  pv_kw: number | null
  verbrauch_kw: number | null
  einspeisung_kw: number | null
  netzbezug_kw: number | null
  batterie_kw: number | null
  waermepumpe_kw: number | null
  wallbox_kw: number | null
  ueberschuss_kw: number | null
  defizit_kw: number | null
  temperatur_c: number | null
  globalstrahlung_wm2: number | null
  soc_prozent: number | null
  komponenten: Record<string, number> | null
  // WP-Kompressor-Starts in dieser Stunde (Summe über alle WPs der Anlage, Issue #136)
  wp_starts_anzahl: number | null
  // WP-Betriebsstunden in dieser Stunde (Summe über alle WPs der Anlage, Issue #238)
  wp_betriebsstunden: number | null
}

export interface StundenAntwort {
  stunden: StundenWert[]
  serien: SerieInfo[]
}

export interface WochenmusterPunkt {
  wochentag: number   // 0=Mo … 6=So
  stunde: number
  pv_kw: number | null
  verbrauch_kw: number | null
  netzbezug_kw: number | null
  einspeisung_kw: number | null
  batterie_kw: number | null
  anzahl_tage: number
}

export interface TagesZusammenfassung {
  datum: string
  ueberschuss_kwh: number | null
  defizit_kwh: number | null
  peak_pv_kw: number | null
  peak_netzbezug_kw: number | null
  peak_einspeisung_kw: number | null
  batterie_vollzyklen: number | null
  temperatur_min_c: number | null
  temperatur_max_c: number | null
  strahlung_summe_wh_m2: number | null
  performance_ratio: number | null
  stunden_verfuegbar: number
  datenquelle: string | null
  komponenten_kwh: Record<string, number> | null
  // Per-Komponente Counter pro Tag (z.B. WP-Kompressor-Starts, Issue #136)
  // Form: { wp_starts_anzahl: { "<inv_id>": <int> } }
  komponenten_starts: Record<string, Record<string, number>> | null
  // Börsenpreis / Negativpreis (§51 EEG)
  boersenpreis_avg_cent: number | null
  boersenpreis_min_cent: number | null
  negative_preis_stunden: number | null
  einspeisung_neg_preis_kwh: number | null
}

/**
 * Tageszeile für die Werte/Tabelle-Embed-Sicht in Tagesgranularität
 * (IA v4 E3, Cockpit/Monat). Feldnamen sind deckungsgleich mit den
 * Registry-Keys (`lib/werte`), damit `getTagWert` direkt `row[key]` liest.
 * Backend: GET /energie-profil/{id}/tage-werte (additiv zur Monatsbilanz).
 */
export interface TagWerte {
  datum: string
  stunden_verfuegbar: number
  datenquelle: string | null
  // Energie (kWh).
  // `erzeugung`/`eigenverbrauch` sind `null`, wenn für den Tag keine Stunde
  // einen PV-Wert trug — etwa wenn die PV nur als Anlagen-Aggregat gepflegt
  // ist: das versorgt die Monatswerte, nicht die Tagesebene. Eine 0 wäre dort
  // „nichts erzeugt" statt „nicht gemessen", und beim Eigenverbrauch entstand
  // aus der Differenz zur gemessenen Einspeisung sogar ein negativer Wert.
  erzeugung: number | null
  // R17/Verlauf-Vergleich: PV-Anlage vs. BKW getrennt (Σ == PV+BKW-Anteil).
  pv_anlage: number
  bkw: number
  eigenverbrauch: number | null
  // Ebenso `null`, wenn die Achse an keiner Stunde des Tages einen Wert trug.
  // Vorher standen hier `0`-Werte neben einem korrekten „—" der PV-Spalte
  // derselben Zeile (Striker, T89667 #162). `direktverbrauch` braucht PV und
  // Verbrauch.
  einspeisung: number | null
  netzbezug: number | null
  gesamtverbrauch: number | null
  direktverbrauch: number | null
  // Quoten (%)
  autarkie: number | null
  evQuote: number | null
  spezErtrag: number | null
  // Speicher
  speicher_ladung: number | null
  speicher_entladung: number | null
  /** Vollzyklen des Tages = Entladung ÷ Kapazität (Backend-SoT). */
  speicher_vollzyklen: number | null
  speicher_effizienz: number | null
  /**
   * Worauf der η des Tages beruht — gleiches Vokabular wie im Monat
   * (`soc_korrigiert` · `roh-unkorrigiert` · `keine-ladung` ·
   * `nicht-ermittelbar`). Ein Tag ist kein geschlossenes System: wer voll
   * beginnt und leer endet, entnimmt mehr, als er lädt. Ohne Ladestand am
   * Rand bleibt der Wert deshalb leer statt über 100 % zu stehen
   * (Melder Knallfrosch, Forum T89667 #163).
   */
  speicher_effizienz_quelle: string | null
  // Wärmepumpe (nur Strom je Tag)
  wp_strom: number | null
  /**
   * Sonstiges je Richtung (BHKW, Heizstab, Pool …). ⚠ Andere Quelle als im
   * Monat: der Tag kennt nur Geräte mit **eigenem Sensor/Zähler**. Wer sein
   * Sonstiges nur monatlich pflegt, sieht die Monatsspalte gefüllt und die
   * Tagesspalte leer — `null` heißt „für den Tag nicht gemessen", nicht 0.
   */
  sonstiges_erzeugung: number | null
  sonstiges_verbrauch: number | null
  // Finanzen (€)
  einspeise_erloes: number
  // `null`, wenn die zugrunde liegende Menge nicht erfasst ist — ein Betrag auf
  // einer Menge, die es nicht gibt, ist keine 0. Die beiden Summen erben die
  // Lücke ihres Summanden.
  ev_ersparnis: number | null
  netzbezug_kosten: number | null
  netto_ertrag: number | null
  netto_bilanz: number | null
  // CO₂
  /** `null`, wenn der Eigenverbrauch nicht erfasst ist — ohne ihn keine CO₂-Aussage. */
  co2_einsparung: number | null
  // Tag-native Zusatzmetriken (kein Monats-Pendant)
  ueberschuss_kwh: number | null
  defizit_kwh: number | null
  peak_pv_kw: number | null
  peak_netzbezug_kw: number | null
  peak_einspeisung_kw: number | null
  performance_ratio: number | null
  batterie_vollzyklen: number | null
  temperatur_min_c: number | null
  temperatur_max_c: number | null
  strahlung_summe_wh_m2: number | null
  boersenpreis_avg_cent: number | null
  boersenpreis_min_cent: number | null
  negative_preis_stunden: number | null
  einspeisung_neg_preis_kwh: number | null
  /** Ertrag je Erzeuger-Investition (#350): Investitions-ID → Tages-kWh. Nur
   *  belegt, wo das Gerät einen eigenen Sensor hat — auf Tagesebene wird nichts
   *  nach kWp verteilt. Leer/fehlend heißt „nicht gemessen", nicht „0 kWh". */
  erzeuger_kwh?: Record<string, number> | null
  /**
   * #377 — Zählerstand je Verbrauchszähler (Investitions-ID → Stand) am Ende
   * dieses Tages. **Bestandsgröße**: nirgends mitsummiert, nicht Teil der
   * Bilanz. Fehlt ein Eintrag, wurde an dem Tag nichts abgelesen.
   */
  zaehler_stand?: Record<string, number> | null
}

/**
 * Warum liegen für einen Tag keine Werte vor — und was hilft? (F-2)
 *
 * Der Grund kommt aus dem Backend (`services/energie_profil/tag_status.py`),
 * NICHT aus einer Client-eigenen Ableitung: der Client kennt weder das
 * Inbetriebnahme-Datum, noch die Zuordnung des Tages, noch ob Home Assistant
 * für ihn Werte hat. Eine zweite Wahrheit daneben wäre genau die Klasse, die
 * ADR-002 verhindert.
 *
 * `aktion_kind` ist gesetzt, **wo die Handlung wirkt**. Vor der Inbetriebnahme,
 * ohne Zuordnung oder ohne HA-Werte bleibt es leer — ein Knopf verspräche dort
 * eine Wirkung, die es nicht gibt.
 */
export interface TagStatus {
  datum: string
  /** `daten_vorhanden` · `zukunft` · `laeuft_noch` · `vor_inbetriebnahme` ·
   *  `keine_zuordnung` · `keine_ha_statistik` · `ha_ohne_werte` ·
   *  `luecke_ohne_reparaturweg` · `luecke_reparierbar` */
  lage: string
  meldung: string
  details?: string | null
  link?: string | null
  aktion_kind?: string | null
  aktion_label?: string | null
}

/**
 * Tages-Detailwerte (Cockpit/Tag), die NICHT in der Tages-Bilanz stehen, aber
 * snapshot-/TEP-genau pro Tag erhebbar sind (SPEC-COCKPIT-TAG-JAHR Abschnitt F,
 * D1 „maximal erheben"). Ein Aufruf je gewähltem Tag (`getTagDetail`). Felder
 * `null` = Sensor nicht gemappt / keine Daten → Frontend lässt sie weg.
 */
export interface TagDetail {
  datum: string
  wp_strom_heizen_kwh: number | null
  wp_strom_warmwasser_kwh: number | null
  wp_heizung_kwh: number | null
  wp_warmwasser_kwh: number | null
  speicher_ladung_netz_kwh: number | null
  speicher_effektiver_ladepreis_cent: number | null
  speicher_effektiver_ladepreis_quelle: string | null
  emob_ladung_pv_kwh: number | null
  emob_ladung_netz_kwh: number | null
  /** #263/T2 — Aufteilung Heizen/Kühlen DIESES Tages, anlagenweite Σ.
   *  `null` heißt „kein Modus-Signal an diesem Tag" ⇒ der Block fehlt ganz,
   *  statt drei Nullen zu zeigen (ADR-002/P4). Der Rest kommt aus dem
   *  Backend und wird hier NICHT nachgerechnet — welcher Bezug gilt,
   *  entscheidet die Faltung. */
  wp_modus_strom_heizen_kwh: number | null
  wp_modus_strom_kuehlen_kwh: number | null
  wp_modus_nicht_aufgeteilt_kwh: number | null
  wp_modus_abdeckung_h: number | null
  soll_pv_kwh: number | null
  einspeise_preis_cent: number | null
  netzbezug_preis_cent: number | null
}

export interface HeatmapZelle {
  tag: number          // 1..31
  stunde: number       // 0..23
  pv_kw: number | null
  verbrauch_kw: number | null
  netzbezug_kw: number | null
  einspeisung_kw: number | null
  ueberschuss_kw: number | null
}

export interface PeakStunde {
  datum: string
  stunde: number
  wert_kw: number
}

export interface TagesprofilStunde {
  stunde: number
  pv_kw: number | null
  verbrauch_kw: number | null
}

export interface KomponentenEintrag {
  key: string
  label: string
  kategorie: string
  typ: string
  seite: string
  kwh: number
  anteil_prozent: number | null
}

export interface KategorieSumme {
  kategorie: string
  kwh: number
  anteil_prozent: number | null
}

export interface MonatsAuswertung {
  jahr: number
  monat: number
  tage_im_monat: number
  tage_mit_daten: number
  pv_kwh: number
  verbrauch_kwh: number
  einspeisung_kwh: number
  netzbezug_kwh: number
  ueberschuss_kwh: number
  defizit_kwh: number
  autarkie_prozent: number | null
  eigenverbrauch_prozent: number | null
  performance_ratio_avg: number | null
  batterie_vollzyklen_summe: number | null
  grundbedarf_kw: number | null
  batterie_ladung_kwh: number | null
  batterie_entladung_kwh: number | null
  batterie_wirkungsgrad: number | null
  direkt_eigenverbrauch_kwh: number | null
  pv_tag_best_kwh: number | null
  pv_tag_schnitt_kwh: number | null
  pv_tag_schlecht_kwh: number | null
  typisches_tagesprofil: TagesprofilStunde[]
  kategorien: KategorieSumme[]
  komponenten: KomponentenEintrag[]
  peak_netzbezug: PeakStunde[]
  peak_einspeisung: PeakStunde[]
  peak_pv: PeakStunde | null
  heatmap: HeatmapZelle[]
  // Börsenpreis / Negativpreis (§51 EEG)
  boersenpreis_avg_cent: number | null
  negative_preis_stunden: number | null
  einspeisung_neg_preis_kwh: number | null
}

export interface VollbackfillResult {
  verarbeitet: number
  geschrieben: number
  // #190 Bug B: Skip-Transparenz — Tage ohne HA-Daten bzw. bereits vorhanden
  uebersprungen_keine_daten?: number
  uebersprungen_existiert?: number
  von: string
  bis: string
}

/** Antwort von `POST /energie-profil/{id}/reaggregate-bereich`.
 *
 * `status: "ok"` ist NUR die Aussage „der Lauf ist durchgelaufen". Ob dabei
 * etwas geschrieben wurde, steht in `erfolgreich` — `aggregate_day` liefert
 * `None`, wenn es für den Tag keine Kurvendaten findet (keine Leistungs-
 * Zuordnung, HA-History reicht nicht so weit zurück), und der Tag landet dann
 * in `keine_daten`. Beides bei HTTP 200. */
export interface ReaggregateBereichResponse {
  status: string
  von: string
  bis: string
  verarbeitet: number
  erfolgreich: number
  keine_daten: number
  fehlgeschlagen: number
  fehler_details?: { datum: string; grund: string }[]
}

export interface KraftstoffpreisStatus {
  tages_offen: number
  monats_offen: number
  land: string
}

export interface KraftstoffpreisBackfillResult {
  aktualisiert: number
  land: string
  hinweis?: string
  fehler?: string
}

export interface ProfildatenLoeschResult {
  geloescht_stundenwerte: number
  geloescht_tagessummen: number
}

export interface VerfuegbarerMonat {
  jahr: number
  monat: number
  tage: number
}

export interface AnlageStats {
  stundenwerte: number
  tageszusammenfassungen: number
  monatswerte: number
  zeitraum: {
    von: string
    bis: string
    tage_mit_daten: number
    tage_gesamt: number
    abdeckung_prozent: number
  } | null
  wachstum_pro_monat: number
}

export interface StundenPrognose {
  stunde: number
  pv_kw: number
  /** null, solange keine Verbrauchsprognose vorliegt (A28) — genau wie die
   *  vier Folgefelder. Nicht 0: eine 0 stünde in der Tabelle wie ein Messwert. */
  verbrauch_kw: number | null
  netto_kw: number | null
  netzbezug_kw: number | null
  einspeisung_kw: number | null
  soc_prozent: number | null
}

export interface TagesPrognose {
  datum: string
  stunden: StundenPrognose[]
  /** Die PV-Hälfte steht immer — sie braucht nur Wetterdienst + kWp. */
  pv_summe_kwh: number
  /** A28: alle verbrauchsabhängigen Felder sind null, solange die Historie für
   *  die Verbrauchsprognose fehlt (< 3 vollständige Tage, frische Installation).
   *  Der Grund steht dann in `hinweise`; die Anzeige zeigt „—". */
  verbrauch_summe_kwh: number | null
  netzbezug_summe_kwh: number | null
  einspeisung_summe_kwh: number | null
  eigenverbrauch_kwh: number | null
  autarkie_prozent: number | null
  speicher_kapazitaet_kwh: number | null
  speicher_voll_um: string | null
  speicher_leer_um: string | null
  verbrauch_basis: string | null
  pv_quelle: string
  daten_tage: number | null
  /** P4: nichtleer, wenn die Antwort nicht das ist, was ihr Name verspricht
   *  (keine PV-Prognose → 24 Nullen; Solcast-Profil von heute als Näherung;
   *  seit A28 auch: keine Verbrauchshistorie → PV-Hälfte allein).
   *  Angezeigt über `unvollstaendigHerkunft` + `HerkunftZeile`. */
  hinweise: string[]
}

export interface ReaggregatePreviewBoundary {
  sensor_key: string
  kategorie: string | null
  zeitpunkt: string
  alt_kwh: number | null
  neu_kwh: number | null
}

export interface ReaggregatePreviewSlot {
  stunde: number
  kategorie: string
  alt_kwh: number | null
  neu_kwh: number | null
}

export interface ReaggregatePreviewCounterTagesdelta {
  feld: string
  alt: number | null
  neu: number | null
}

export interface ReaggregatePreviewResponse {
  datum: string
  boundaries: ReaggregatePreviewBoundary[]
  slot_deltas: ReaggregatePreviewSlot[]
  tagesumme_alt: Record<string, number | null>
  tagesumme_neu: Record<string, number | null>
  ha_verfuegbar: boolean
  counter_tagesdelta: ReaggregatePreviewCounterTagesdelta[]
}

/** Eine Komponente im Ergebnis eines Tages-Laufs (N-58). */
export interface ReaggregateTagKomponente {
  key: string
  /** Anwender-Name („Dach Süd", „Einspeisung") — Backend-SoT `komponenten_key_label`. */
  name: string
  /** Hat DIESER Lauf für die Komponente einen Wert geschrieben? */
  geschrieben: boolean
  kwh: number | null
}

/**
 * Antwort des Einzeltag-Laufs.
 *
 * `status: "ok"` ist der Transport-Status und heißt nur „durchgelaufen" — die
 * Aussage, ob etwas geschrieben wurde, steht in den Komponenten-Zählern
 * daneben (gleiche Linie wie `ReaggregateBereichResponse`, N-58).
 */
export interface ReaggregateTagResponse {
  status: string
  datum: string
  stunden_verfuegbar: number
  stunden_mit_messdaten: number
  pv_kwh_alt: number | null
  pv_kwh_neu: number | null
  komponenten: ReaggregateTagKomponente[]
  komponenten_erwartet: number
  komponenten_geschrieben: number
  /** Namen der Komponenten, für die der Lauf nichts schreiben konnte. */
  komponenten_ohne_wert: string[]
}

export const energieProfilApi = {
  getStunden: (anlageId: number, datum: string): Promise<StundenAntwort> =>
    api.get(`/energie-profil/${anlageId}/stunden?datum=${datum}`),

  getWochenmuster: (anlageId: number, von: string, bis: string): Promise<WochenmusterPunkt[]> =>
    api.get(`/energie-profil/${anlageId}/wochenmuster?von=${von}&bis=${bis}`),

  getTage: (anlageId: number, von: string, bis: string): Promise<TagesZusammenfassung[]> =>
    api.get(`/energie-profil/${anlageId}/tage?von=${von}&bis=${bis}`),

  getTageWerte: (anlageId: number, von: string, bis: string): Promise<TagWerte[]> =>
    api.get(`/energie-profil/${anlageId}/tage-werte?von=${von}&bis=${bis}`),

  getTagDetail: (anlageId: number, datum: string): Promise<TagDetail> =>
    api.get(`/energie-profil/${anlageId}/tag-detail?datum=${datum}`),

  /** Warum ist die Tagessicht leer? Nur aus dem leeren Zustand heraus abrufen —
   *  die Antwort kostet im letzten Zweig einen HA-LTS-Read für den Tag. */
  getTagStatus: (anlageId: number, datum: string): Promise<TagStatus> =>
    api.get(`/energie-profil/${anlageId}/tag-status?datum=${datum}`),

  getKomponentenSerien: (anlageId: number, von: string, bis: string): Promise<SerieInfo[]> =>
    api.get(`/energie-profil/${anlageId}/komponenten-serien?von=${von}&bis=${bis}`),

  getMonat: (anlageId: number, jahr: number, monat: number): Promise<MonatsAuswertung> =>
    api.get(`/energie-profil/${anlageId}/monat?jahr=${jahr}&monat=${monat}`),

  vollbackfill: (anlageId: number): Promise<VollbackfillResult> =>
    api.post(`/energie-profil/${anlageId}/vollbackfill`),

  reaggregateTag: (anlageId: number, datum: string, mitResnap: boolean = true, signal?: AbortSignal): Promise<ReaggregateTagResponse> =>
    api.post(`/energie-profil/${anlageId}/reaggregate-tag?datum=${datum}&mit_resnap=${mitResnap}`, undefined, { signal }),

  reaggregateTagPreview: (anlageId: number, datum: string, signal?: AbortSignal): Promise<ReaggregatePreviewResponse> =>
    api.get(`/energie-profil/${anlageId}/reaggregate-tag/preview?datum=${datum}`, { signal }),

  // v3.45.9: Bereichs-Reaggregation (max 31 Tage/Lauf) — Bulk-Reparatur z. B.
  // der Batterie-Vorzeichen-Historie aus dem Daten-Checker.
  // Die Zähler sind getypt, weil `status: "ok"` NICHT heißt, dass Werte
  // geschrieben wurden: `aggregate_day` liefert `None`, wenn es für den Tag
  // keine Kurvendaten findet — dann steht `erfolgreich: 0, keine_daten: n`
  // bei HTTP 200. Am 2026-07-30 E2E gemessen; der Aufrufer MUSS das auswerten,
  // sonst meldet die Oberfläche einen Erfolg, den es nicht gab.
  reaggregateBereich: (anlageId: number, von: string, bis: string, mitResnap: boolean = true, signal?: AbortSignal): Promise<ReaggregateBereichResponse> =>
    api.post(`/energie-profil/${anlageId}/reaggregate-bereich?von=${von}&bis=${bis}&mit_resnap=${mitResnap}`, undefined, { signal }),

  getTagesprognose: (anlageId: number, datum?: string): Promise<TagesPrognose> =>
    api.get(`/energie-profil/${anlageId}/tagesprognose${datum ? `?datum=${datum}` : ''}`),

  getKraftstoffpreisStatus: (anlageId: number): Promise<KraftstoffpreisStatus> =>
    api.get(`/energie-profil/${anlageId}/kraftstoffpreis-status`),

  kraftstoffpreisBackfillTages: (anlageId: number): Promise<KraftstoffpreisBackfillResult> =>
    api.post(`/energie-profil/${anlageId}/kraftstoffpreis-backfill/tages`),

  kraftstoffpreisBackfillMonats: (anlageId: number): Promise<KraftstoffpreisBackfillResult> =>
    api.post(`/energie-profil/${anlageId}/kraftstoffpreis-backfill/monats`),

  deleteRohdaten: (): Promise<ProfildatenLoeschResult> =>
    api.delete(`/energie-profil/rohdaten`),

  getAnlageStats: (anlageId: number): Promise<AnlageStats> =>
    api.get(`/energie-profil/${anlageId}/stats`),

  getVerfuegbareMonate: (anlageId: number): Promise<VerfuegbarerMonat[]> =>
    api.get(`/energie-profil/${anlageId}/verfuegbare-monate`),

  deleteRohdatenAnlage: (anlageId: number): Promise<ProfildatenLoeschResult> =>
    api.delete(`/energie-profil/${anlageId}/rohdaten`),
}
