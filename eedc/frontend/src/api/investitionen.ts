/**
 * Investitionen API Client
 */

import { api } from './client'
import type { Investition, InvestitionTyp } from '../types'

export interface InvestitionCreate {
  anlage_id: number
  typ: InvestitionTyp
  bezeichnung: string
  anschaffungsdatum?: string
  stilllegungsdatum?: string
  anschaffungskosten_gesamt?: number
  anschaffungskosten_alternativ?: number
  betriebskosten_jahr?: number
  // Ertragsseite des Jahresbetrags (Konzept §8/1) — nur Wallbox/Sonstiges,
  // dort liest das ROI-Dashboard ihn als Jahres-Einsparung.
  einsparung_prognose_jahr?: number
  parameter?: Record<string, unknown>
  aktiv?: boolean
  parent_investition_id?: number
  // PV-Module Felder
  leistung_kwp?: number
  ausrichtung?: string
  neigung_grad?: number
  ha_entity_id?: string  // Home Assistant Sensor für String-Daten
  graue_last_kg?: number  // #284: Override graue Herstellungs-Last (CO2)
}

/**
 * Update-Nutzlast.
 *
 * `null` heißt „Feld leeren", `undefined` heißt „nicht anfassen". Das Backend
 * arbeitet mit `model_dump(exclude_unset=True)` — ein weggelassener Schlüssel
 * behält den Altwert. Wer ein optionales Feld zurücksetzen will, MUSS deshalb
 * `null` senden (JayJay-Meldung Forum v4.0.0: Wechselrichter-Zuordnung eines
 * Speichers ließ sich nicht mehr lösen).
 */
export interface InvestitionUpdate {
  bezeichnung?: string
  anschaffungsdatum?: string | null
  stilllegungsdatum?: string | null
  anschaffungskosten_gesamt?: number | null
  anschaffungskosten_alternativ?: number | null
  betriebskosten_jahr?: number | null
  einsparung_prognose_jahr?: number | null
  parameter?: Record<string, unknown>
  aktiv?: boolean
  parent_investition_id?: number | null
  // PV-Module Felder
  leistung_kwp?: number | null
  ausrichtung?: string | null
  neigung_grad?: number | null
  ha_entity_id?: string | null
  graue_last_kg?: number | null  // #284: Override graue Herstellungs-Last (CO2)
}

/**
 * Eine Komponente innerhalb eines PV-Systems (WR, PV-Module, DC-Speicher)
 */
export interface ROIKomponente {
  investition_id: number
  bezeichnung: string
  typ: string  // pv-module, wechselrichter, speicher
  kosten: number
  kosten_alternativ: number
  relevante_kosten: number
  einsparung: number | null  // Nur für PV-Module/Speicher, null für WR
  co2_einsparung_kg: number | null
  detail: Record<string, unknown>
}

export interface ROIBerechnung {
  investition_id: number
  investition_bezeichnung: string
  investition_typ: string  // "pv-system" für aggregiert, sonst normal
  anschaffungskosten: number
  anschaffungskosten_alternativ: number
  relevante_kosten: number
  /**
   * F-19 + Bauschritt 7: der tatsächliche Nenner von
   * `roi_prozent`/`amortisation_jahre` — relevante Kosten plus die kumulierten
   * sonstigen **Ausgaben**, minus die kumulierten sonstigen **Erträge**.
   * `relevante_kosten` bleibt die Mehrkosten-Größe (zugleich USt-Grundlage).
   */
  kapitaleinsatz: number
  jahres_einsparung: number
  roi_prozent: number | null
  amortisation_jahre: number | null
  /**
   * Konzept §5/§8-6: die Annahme, unter der `amortisation_jahre` gilt —
   * gebildet im Backend (`kapitalrechnung.annahme_dauer_text`), hier nur
   * angezeigt. Mit gepflegten Betriebskosten lautet sie anders (Modell C).
   */
  amortisation_annahme: string | null
  co2_einsparung_kg: number | null
  detail_berechnung: Record<string, unknown>
  komponenten?: ROIKomponente[]  // Für PV-Systeme: aufklappbare Unterkomponenten
}

export interface ROIDashboardResponse {
  anlage_id: number
  anlage_name: string
  gesamt_investition: number
  gesamt_relevante_kosten: number
  /** F-19: kumulierte sonstige AUSGABEN (positiver Betrag) — sie erhöhen den Nenner. */
  gesamt_sonstige_ausgaben_euro: number
  /**
   * Bauschritt 7 (Konzept §8): kumulierte sonstige ERTRÄGE (positiver Betrag)
   * — sie **mindern** den Nenner. Optional, weil ältere Backends das Feld
   * nicht liefern.
   */
  gesamt_sonstige_ertraege_euro?: number
  /**
   * Nenner von ROI/Amortisation = relevante Kosten + sonstige Ausgaben
   * − sonstige Erträge (F-19 + Bauschritt 7).
   */
  gesamt_kapitaleinsatz: number
  gesamt_jahres_einsparung: number
  gesamt_roi_prozent: number | null
  gesamt_amortisation_jahre: number | null
  /** Frühestes Anschaffungsjahr = „Jahr 0" der Break-Even-Kurve; null ohne gepflegtes Datum. */
  basis_jahr: number | null
  /** Voraussichtliches Break-Even-Kalenderjahr (basis_jahr + Amortisationsdauer). */
  gesamt_amortisation_jahr: number | null
  /** Konzept §5/§8-6: die Annahme hinter Kachel, Kurve und Summenzeile. */
  amortisation_annahme: string | null
  gesamt_co2_einsparung_kg: number
  berechnungen: ROIBerechnung[]
  // Vorgeschlagener Slider-Wert: letzter Monatsdaten-Preis (EU Weekly Oil
  // Bulletin) oder Default. Bei E-Auto-Berechnungen löst das Backend pro
  // Investition auf (Slider → per-Inv-Param → Monatsdaten → Default).
  benzinpreis_hinweis_euro: number | null
}

// CO2-Amortisation (#284) — graue Herstellungs-Last
export interface GraueLastPosten {
  investition_id: number | null
  typ: string
  bezeichnung: string
  graue_last_kg: number
  quelle: string  // override | default | fehlt | kein_default
}

export interface CO2AmortisationResponse {
  graue_last_gesamt_kg: number
  posten: GraueLastPosten[]
}

/**
 * Antwort auf „warum steht dieser Hub-Reiter ohne Zahlen da?" (N-247).
 * `leer=false` ⇒ das Gerät hat Monatswerte, die Sicht zeigt nichts an.
 */
export interface HubLeerGrundResponse {
  leer: boolean
  art?: string | null
  meldung?: string | null
  details?: string | null
  link?: string | null
  link_label?: string | null
}

// Investitions-Dashboard Types
export interface InvestitionMonatsdaten {
  id: number
  investition_id: number
  jahr: number
  monat: number
  verbrauch_daten: Record<string, number>
  einsparung_monat_euro: number | null
  co2_einsparung_kg: number | null
}

export interface EAutoDashboardResponse {
  investition: Investition
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: {
    gesamt_km: number
    gesamt_verbrauch_kwh: number
    // Ø Verbrauch (kWh/100 km) — null wenn keine Basis (nie 0,0 erfinden).
    durchschnitt_verbrauch_kwh_100km: number | null
    // Herkunft der Berechnung: 'gemessen' (verbrauch_kwh) | 'ladung' (Näherung) | 'keine'
    verbrauch_quelle: 'gemessen' | 'ladung' | 'keine'
    // Ladung aufgeschlüsselt
    gesamt_ladung_kwh: number
    ladung_heim_kwh: number
    ladung_pv_kwh: number
    ladung_netz_kwh: number
    ladung_extern_kwh: number
    ladung_extern_euro: number
    // PV-Anteile
    pv_anteil_heim_prozent: number
    pv_anteil_gesamt_prozent: number
    // V2H
    v2h_entladung_kwh: number
    v2h_ersparnis_euro: number
    // Kosten-Vergleich
    benzin_kosten_alternativ_euro: number
    verwendeter_benzinpreis_euro: number
    strom_kosten_heim_euro: number
    strom_kosten_extern_euro: number
    strom_kosten_gesamt_euro: number
    ersparnis_vs_benzin_euro: number
    // #331 Plug-in-Hybrid — 0 bzw. 'unbestimmt' bei einem BEV.
    fossile_kosten_euro: number
    km_elektrisch: number
    km_verbrenner: number
    phev_anteil_quelle: 'gemessen' | 'prozent' | 'unbestimmt'
    // Wallbox-Ersparnis
    wallbox_ersparnis_euro: number
    // Gesamt
    gesamt_ersparnis_euro: number
    co2_ersparnis_kg: number
    anzahl_monate: number
  }
}

export interface WaermepumpeDashboardResponse {
  investition: Investition
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: {
    gesamt_stromverbrauch_kwh: number
    gesamt_heizenergie_kwh: number
    gesamt_warmwasser_kwh: number
    gesamt_waerme_kwh: number
    /** N-379 / SOLL §3.3/S2 — hat dieses Gerät die Warmwasser-Achse überhaupt?
     *  Eine Split-Klimaanlage hat keinen Warmwasserkreis (N-304), und die
     *  Aufteilung stand trotzdem als festes Paar Heizung/Warmwasser da.
     *  ⛔ Sagt NICHT „hier fehlt ein Zähler" — das ist Sache des Daten-Checkers.
     *  Optional, damit ältere Antworten (Cache) das Bisherige zeigen. */
    hat_warmwasser_achse?: boolean
    /** F-42: `null` = nicht bewertet, nicht „0". `durchschnitt_cop` ohne
     *  gemessene Wärme, die drei Vergleichsgrößen ohne ersetzte Heizung —
     *  eine Klimaanlage im Neubau hat weder JAZ noch Gaskessel-Ersparnis.
     *  `wp_kosten_euro` bleibt immer eine Zahl (Strom × Preis). */
    durchschnitt_cop: number | null
    wp_kosten_euro: number
    alte_heizung_kosten_euro: number | null
    ersparnis_euro: number | null
    co2_ersparnis_kg: number | null
    anzahl_monate: number
    // Getrennte Strommessung (optional)
    gesamt_strom_heizen_kwh?: number
    gesamt_strom_warmwasser_kwh?: number
    gesamt_heizung_getrennt_kwh?: number
    gesamt_warmwasser_getrennt_kwh?: number
    /** W-4 (SOLL §4.1): Arbeitszahl je Funktion — `null`, wo es sie nicht gibt,
     *  dann sagt `*_grund` warum. ⚠ Hieß bis 26.08.2026 `cop_heizen` /
     *  `cop_warmwasser`; das Projekt führt Perioden-Kennzahlen durchgängig als
     *  **JAZ** und behält COP technischen Backend-Berechnungen vor (Glossar,
     *  v3.23.4/#167). Der Anzeigename war schon vorher „JAZ …". */
    /** W-15: Warum es die Gesamt-Arbeitszahl nicht gibt — `null`, wenn es sie
     *  gibt. Kommt seit dem 26.08.2026 aus dem Layer statt aus einer eigenen
     *  Division im Endpoint; vorher lieferte der Hub weder Grund noch Hinweis. */
    durchschnitt_cop_grund?: string | null
    /**
     * Arbeitszahl **je Monat**, aus dem Layer (ADR-002/P12). `wert: null` heisst
     * „keine Kennzahl", `grund` sagt warum. Der Client rechnet sie nicht mehr
     * selbst — er kennt weder funktionsfremden Strom noch abgeleitete Waerme.
     */
    jaz_je_monat?: {
      jahr: number; monat: number; wert: number | null; grund: string | null
      /** Bereinigtes Q und E — `nenner_kwh` OHNE funktionsfremden Strom. Fuer
       *  Sigma Q / Sigma E ueber ein Saisonfenster (SOLL Paragraph 5: neu
       *  berechnen, nie mitteln). `null`, wo es keine Kennzahl gibt. */
      zaehler_kwh: number | null; nenner_kwh: number | null
      heizen_zaehler_kwh: number | null; heizen_nenner_kwh: number | null
      /** B3/H-1b: der Stromverbrauch des Monats nach dem SoT (`get_wp_strom_kwh`) —
       *  bei getrennter Strommessung steht er NICHT in `stromverbrauch_kwh`. Optional,
       *  weil eine ältere Antwort ihn nicht trägt; dann liest der Client die Rohspalte. */
      strom_kwh?: number
    }[]
    /** W-6/W-15: Der Heizstab-Satz unterhalb einer Arbeitszahl von 2 — er stand
     *  bis zum 26.08.2026 nur im Cockpit, obwohl die Melder-Antwort ihn für den
     *  Komponenten-Hub zusagt. */
    durchschnitt_cop_hinweis?: string | null
    jaz_heizen?: number | null
    jaz_heizen_grund?: string | null
    jaz_warmwasser?: number | null
    jaz_warmwasser_grund?: string | null
    /** W-5: Arbeitszahl Kühlen. Hängt an den Betriebsart-Zählern, NICHT an der
     *  getrennten Strommessung — eine Klimaanlage hat oft genau diese Zähler. */
    jaz_kuehlen?: number | null
    jaz_kuehlen_grund?: string | null
    gesamt_kaelte_kwh?: number
    // Modus-Split (#263 K-2) — **Teilmengen** von `gesamt_stromverbrauch_kwh`,
    // nie Summanden. Alle vier fehlen gemeinsam, wenn kein Modus erfasst ist:
    // eine 0 hieße „hat nicht geheizt", und das weiß eedc ohne Sensor nicht.
    modus_strom_heizen_kwh?: number
    modus_strom_kuehlen_kwh?: number
    /** N-336: nur aus dem **abgeleiteten** Split. */
    modus_strom_warmwasser_kwh?: number
    /** E4 (Konzept §2.3): nur aus **gemessenen** Betriebsart-Zählern. */
    modus_strom_lueften_kwh?: number
    modus_strom_entfeuchten_kwh?: number
    modus_nicht_aufgeteilt_kwh?: number
    modus_abdeckung_h?: number
    /** **W-17b** — die Grundmenge, auf die sich die Aufteilung bezieht.
     *  Bewusst **nicht** der WP-Gesamtstrom: dort steckt auch der Strom von
     *  Geräten ohne Modus-Signal. Ohne dieses Feld stand der Balken stumm unter
     *  einer Kachel mit größerer Zahl (dietmar1968, T89667 #210: 30 kWh unter
     *  284 kWh). Nicht nachrechnen — der Bezug entscheidet die Faltung. */
    modus_strom_bezug_kwh?: number
    modus_gemessen?: boolean
    /** Ist `gesamt_heizenergie_kwh` aus `Strom × JAZ` gerechnet statt gemessen?
     *  Dann bleibt `durchschnitt_cop` null (Konzept §3.5) und die Anzeige
     *  kennzeichnet die Wärme — wie „geschätzt (kWp-Anteil)" bei der PV. */
    waerme_abgeleitet?: boolean
    waerme_abgeleitet_faktor?: number | null
    /** B3/H-2 (SOLL §3.3 Hub-Zeile): Herkunft der Wärme, fertig formuliert aus dem
     *  Layer — „gemessen" oder „geschätzt: Strom × JAZ 3,5". */
    waerme_herkunft?: string | null
    /** B3/H-2 + F12: der Satz neben Ersparnis und CO₂ — bei geschätzter Wärme und/oder
     *  einem zweiten Erzeuger am Wärmezähler; `null`, wenn nichts vorzubehalten ist. */
    ersparnis_vorbehalt?: string | null
    // Kompressor-Starts (#238/#290): _summe_erfasst = seit Anschaffung von eedc
    // erfasst (Kachel-Hauptwert), _gesamt = roher Lebensdauer-Zählerstand aus
    // dem Hersteller-Sensor (Kachel-Tooltip/Info), Max/Tag aus Tagesinkrementen.
    kompressor_starts_summe_erfasst?: number | null
    kompressor_starts_gesamt?: number | null
    kompressor_starts_max_tag?: number | null
    // Betriebsstunden (#238 detLAN): analog. Die zwei abgeleiteten KPIs setzen
    // voraus, dass Starts UND Stunden gepflegt sind, und rechnen mit den
    // seit-Anschaffung erfassten Summen.
    betriebsstunden_summe_erfasst?: number | null
    betriebsstunden_gesamt?: number | null
    betriebsstunden_max_tag?: number | null
    oe_laufzeit_pro_start_h?: number | null
    starts_pro_betriebsstunde?: number | null
  }
}

/**
 * Ein Monat der Speicher-Potentialanalyse (#358 Phase 2) — eine Spalte der Grafik.
 *
 * ⚠ **`soc_bins` ist entfallen.** Die Sicht malte daraus eine Heatmap, deren
 * Deckkraft **global** über alle Monate normiert war: ein Winter-Extremwert im
 * untersten Bin bestimmte die Skala, benachbarte Monate wurden ununterscheidbar
 * (Rainer, 13.08.). `soc_p10/p50/p90` je Monat kennen die anderen Monate nicht.
 */
export interface MonatsPotential {
  jahr: number
  monat: number
  nutzbares_zusatzpotential_kwh: number
  ueberschuss_kwh: number
  stunden_voll: number
  zyklen_gesamt: number
  zyklen_leergelaufen: number
  /** Stunden mit gemessenem Ladestand — Nenner der beiden Anteile. */
  stunden_mit_soc: number
  soc_p10: number | null
  soc_p50: number | null
  soc_p90: number | null
  /** Anteil der Stunden am oberen bzw. unteren Anschlag. `null` ohne Messung. */
  anteil_voll_prozent: number | null
  anteil_leer_prozent: number | null
  /** Durchsatz als Vollzyklen-Äquivalent — derselbe Kanon wie Cockpit/HA/PDF. */
  vollzyklen: number | null
  ladung_kwh: number
  /** Teil der Ladung, der **höchstens** aus dem Netz kam. Obergrenze, keine Messung. */
  netz_ladung_kwh: number
  netz_ladung_anteil_prozent: number | null
}

/**
 * „Hätte mehr Kapazität geholfen?" — gedeckelte Antwort.
 *
 * `nutzbares_zusatzpotential_kwh` ist die Zahl, an der eine Kaufentscheidung
 * hängen darf; `ueberschuss_kwh` ist die **Obergrenze** (was ein beliebig großer
 * Speicher höchstens hätte aufnehmen können) und regelmäßig um ein Vielfaches
 * größer. `deckelung_greift` sagt, ob sie auseinanderliegen.
 */
export interface SpeicherPotentialResponse {
  nutzbares_zusatzpotential_kwh: number
  ueberschuss_kwh: number
  stunden_voll: number
  zyklen_gesamt: number
  zyklen_leergelaufen: number
  deckelung_greift: boolean
  tage_mit_daten: number
  von: string | null
  bis: string | null
  monate: MonatsPotential[]
  /** Ab 2 ist der Ladestand ein anlagenweiter Mischwert, keine Geräteaussage. */
  anzahl_speicher: number
  kapazitaet_kwh: number | null
  /** Brutto — der Nenner der Vollzyklen. `null` = keine Kapazität gepflegt. */
  kapazitaet_brutto_kwh: number | null
  soc_voll_prozent: number
  /** Anlagenspezifisch seit #379 — abgeleitet aus der gepflegten nutzbaren Kapazität. */
  soc_leer_prozent: number
  /** true = aus der nutzbaren Kapazität abgeleitet, false = Rückfall auf 5 %. */
  soc_leer_ist_abgeleitet?: boolean
  /** Kleinster gemessener Ladestand des Zeitraums. */
  soc_min_prozent?: number | null
  /**
   * true = „mehr Kapazität hätte nichts gebracht" ist unbelegt (N-254): nie leer,
   * dem Boden aber auch nie nahe, und ohne gepflegte nutzbare Kapazität lässt sich
   * „groß genug" nicht von „eigene Entlade-Untergrenze" trennen.
   */
  boden_nie_erreicht?: boolean
}

/** Ein simulierter Kapazitäts-Punkt der Sizing-Kurve (#358 Phase 3). */
export interface SizingPunkt {
  /** Vielfaches der heutigen Kapazität (0,5 … 2,0). */
  faktor: number
  kapazitaet_kwh: number
  einspeisung_kwh: number
  netzbezug_kwh: number
  eigenverbrauch_kwh: number
  /** Gegen heute; negativ = weniger Netzbezug. */
  delta_netzbezug_kwh: number
  delta_einspeisung_kwh: number
  /**
   * Netto auf ein Jahr hochgerechnet: gesparter Netzbezug **minus** entgangene
   * Einspeisung (Spread-Kanon). Bewusst NICHT der gesparte Netzbezug allein —
   * der wäre um die Einspeisevergütung zu hoch.
   */
  nutzen_euro_jahr: number | null
  mehrkosten_euro: number | null
  /** `null`, wenn es nichts zu amortisieren gibt oder der Nutzen ≤ 0 ist. */
  amortisation_jahre: number | null
}

/**
 * Welchen Ladestands-Bereich die Anlage im Alltag fährt (N-238).
 *
 * Sie trennt die beiden Ursachen, aus denen gepflegte und gemessene Kapazität
 * auseinanderliegen können: **gewollte Ladegrenze** (der Speicher wird gar
 * nicht voll geladen) oder **Ladeverlust** (er wird voll, es kommt trotzdem
 * weniger heraus). `laedt_planmaessig_voll` ist die fertige Unterscheidung.
 */
export interface SocNutzung {
  soc_p5: number
  soc_median: number
  soc_p95: number
  /** Median des Tages-Maximums: „wie weit lädt sie an einem typischen Tag?" */
  tages_max_median: number
  tage_bis_voll: number
  tage_bis_leer: number
  tage_mit_soc: number
  /** Ladestands-Median je Speicher (`{investition_id: prozent}`). Leer, solange
   *  die Historie nur den Anlagenwert kennt (Tage vor der N-239-Umstellung). */
  median_je_speicher: Record<string, number>
  laedt_planmaessig_voll: boolean
}

/**
 * „Lohnt sich ein größerer Speicher?" — rückblickende Simulation.
 *
 * `basis_kalibriert` entscheidet, wie belastbar die Kurve ist: `true` = die
 * Basis wurde aus der **gemessenen** Speicherbewegung abgeleitet, `false` = es
 * wird mit den gepflegten Parametern gerechnet (an der Referenzanlage verfehlte
 * das den Netzbezug um −17,5 % statt −4,3 %). Die Sicht muss den Unterschied
 * sagen, statt eine Genauigkeit zu suggerieren.
 */
export interface SpeicherSizingResponse {
  kurve: SizingPunkt[]
  basis_kapazitaet_kwh: number
  basis_roundtrip_prozent: number
  basis_kalibriert: boolean
  kalibrierung_paare_laden: number | null
  kalibrierung_paare_entladen: number | null
  kalibrierung_stunden_verworfen: number | null
  gepflegte_kapazitaet_kwh: number | null
  gepflegter_wirkungsgrad_prozent: number
  /** `null`, solange gar kein Ladestand erfasst ist. */
  soc_nutzung: SocNutzung | null
  tage_mit_daten: number
  tage_simuliert: number
  historie_reicht: boolean
  min_tage_fuer_aussage: number
  von: string | null
  bis: string | null
  anzahl_speicher: number
  /** Der HEUTE gültige Tarif — die Frage ist nach vorn gerichtet, nicht historisch. */
  bezug_preis_cent: number | null
  einspeise_verg_cent: number | null
  richtpreis_eur_je_kwh: number
}

export interface SpeicherDashboardResponse {
  investition: Investition
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: {
    gesamt_ladung_kwh: number
    gesamt_entladung_kwh: number
    effizienz_prozent: number
    // N127: alle drei sind `null`, wenn keine Kapazität gepflegt ist — ohne sie
    // gibt es keine Zyklenzahl. Vorher rechnete das Backend still mit 10 kWh.
    vollzyklen: number | null
    zyklen_pro_monat: number | null
    kapazitaet_kwh: number | null
    kapazitaet_fehlt?: boolean
    ersparnis_euro: number
    /** PV-Hälfte von `ersparnis_euro` (#358) — die andere ist
     *  `arbitrage_gewinn_euro`. Beide sind disjunkt und summieren sich auf
     *  `ersparnis_euro`; die Aufstellung addiert sie, deshalb darf hier NICHT
     *  wieder `ersparnis_euro` als PV-Posten stehen. */
    pv_anteil_euro: number
    anzahl_monate: number
    // Arbitrage-Daten
    arbitrage_faehig: boolean
    arbitrage_kwh: number
    arbitrage_avg_preis_cent: number | null
    arbitrage_gewinn_euro: number
    // Etappe C (#264): TEP-basierte KPIs — optional, Backend liefert sie nur
    // bei vorhandener Datenbasis (sonst Fallback auf arbitrage_avg_preis_cent
    // bzw. effizienz_prozent).
    effektiver_ladepreis_cent?: number | null
    effektiver_ladepreis_quelle?: string
    ladepreis_abdeckung_prozent?: number
    ist_wirkungsgrad_prozent?: number | null
    wirkungsgrad_quelle?: string
    param_wirkungsgrad_prozent?: number
    eta_degradation_alarm?: boolean
    // Invariante: Σentladung > Σladung kumulativ (physikalisch unmöglich).
    durchsatz_inkonsistent?: boolean
  }
  // Gleitende 12-Monats-Effizienz (carry-over-immun) — siehe SpeicherBlock.
  effizienz_verlauf: { jahr: number; monat: number; effizienz_prozent: number | null; fenster_monate: number }[]
}

/** Speicher-spezifische Felder im ROI-`detail`/`detail_berechnung`-Dict (Etappe C, #264).
 *
 * ⚠ **Zwei Bezugsobjekte in einem Dict, und das ist kein Versehen:**
 * `effektiver_ladepreis_cent` kommt aus `speicher_ladepreis_anlage` und ist
 * **anlagenweit** — für jeden Speicher derselbe Wert. `verwendetes_wirkungsgrad_prozent`
 * kommt aus `speicher_eta_by_inv[inv.id]` und gehört **diesem einen Gerät**.
 * Wer das nebeneinanderstellt, muss dazuschreiben, was wozu gehört.
 *
 * ⛔ `eta_degradation_alarm`/`param_wirkungsgrad_prozent` standen hier bis zum
 * 03.09.2026 und sind entfallen (Entscheid Gernot) — der gepflegte Parameter
 * geht in DIESE Sicht gar nicht ein, sobald gemessen wird. Die Warnung bleibt
 * im Komponenten-Hub, wo der gepflegte Wert zählt.
 */
export interface SpeicherRoiDetail {
  modus?: string
  effektiver_ladepreis_cent?: number | null
  ladepreis_quelle?: string
  verwendetes_wirkungsgrad_prozent?: number
  wirkungsgrad_quelle?: string
  ladepreis_abdeckung_prozent?: number
}

export interface WallboxDashboardResponse {
  investition: Investition
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: {
    // Heimladung (aus E-Auto-Daten)
    gesamt_heim_ladung_kwh: number
    ladung_pv_kwh: number
    ladung_netz_kwh: number
    pv_anteil_prozent: number
    // Externe Ladung zum Vergleich
    extern_ladung_kwh: number
    extern_kosten_euro: number
    extern_preis_kwh_euro: number
    // Kostenvergleich
    heim_kosten_euro: number
    heim_als_extern_kosten_euro: number
    ersparnis_vs_extern_euro: number
    // Amortisation — kommt aus dem Backend-SoT (Kapitalrechnung), NICHT aus
    // Anschaffung ÷ Ersparnis im Client (N-230). `null` heißt „nicht
    // bewertbar" und ist nicht 0.
    kapitaleinsatz_euro: number
    jahres_ersparnis_euro: number
    amortisation_jahre: number | null
    amortisation_annahme: string
    // Wallbox-Info
    leistung_kw: number
    gesamt_ladevorgaenge: number
    ladevorgaenge_pro_monat: number
    anzahl_monate: number
  }
}

export interface BalkonkraftwerkDashboardResponse {
  investition: Investition
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: {
    gesamt_erzeugung_kwh: number
    gesamt_eigenverbrauch_kwh: number
    gesamt_einspeisung_kwh: number
    eigenverbrauch_quote_prozent: number
    spezifischer_ertrag_kwh_kwp: number
    // Leistung
    leistung_wp: number
    anzahl_module: number
    // Speicher
    hat_speicher: boolean
    speicher_kapazitaet_wh: number
    speicher_ladung_kwh: number
    speicher_entladung_kwh: number
    speicher_effizienz_prozent: number
    // Finanzen
    ersparnis_eigenverbrauch_euro: number
    erloes_einspeisung_euro: number
    gesamt_ersparnis_euro: number
    // CO2
    co2_ersparnis_kg: number
    anzahl_monate: number
  }
}

export interface SonstigesDashboardResponse {
  investition: Investition
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: {
    kategorie: 'erzeuger' | 'verbraucher' | 'speicher' | 'zaehler'
    beschreibung: string
    // Erzeuger-Felder
    gesamt_erzeugung_kwh?: number
    gesamt_eigenverbrauch_kwh?: number
    gesamt_einspeisung_kwh?: number
    eigenverbrauch_quote_prozent?: number
    ersparnis_eigenverbrauch_euro?: number
    erloes_einspeisung_euro?: number
    // Verbraucher-Felder
    gesamt_verbrauch_kwh?: number
    bezug_pv_kwh?: number
    bezug_netz_kwh?: number
    pv_anteil_prozent?: number
    kosten_netz_euro?: number
    ersparnis_pv_euro?: number
    // Speicher-Felder
    gesamt_ladung_kwh?: number
    gesamt_entladung_kwh?: number
    effizienz_prozent?: number
    ersparnis_euro?: number
    // Zähler-Felder (#377) — erfasst, nicht bewertet. Sie stehen bewusst
    // OHNE `gesamt_*`-Nachbarn: Für einen Gas- oder Wasserzähler gibt es keine
    // Ersparnis und kein CO₂, und ein Feld mit 0 wäre eine Behauptung.
    zaehler_art?: string
    /** Die Einheit, die neben der Zahl steht — vom Gerät, nie zum Rechnen. */
    einheit?: string
    stand_anfang?: number | null
    stand_ende?: number | null
    /** `null`, wenn ein Stand fehlt — nicht 0 (ADR-002/P4). */
    differenz?: number | null
    anfang_vollstaendig?: boolean
    verlauf?: Array<{ zeitpunkt: string; stand: number }>
    /** Verbrauch je Monat (Flussgröße, im Backend gerechnet). */
    monatsverbrauch?: Array<{ jahr: number; monat: number; verbrauch: number; stand: number }>
    /** `false` = nicht bewertbar, nicht bloß unbekannt. */
    bewertet?: boolean
    nicht_bewertet_grund?: string
    // Gemeinsame Felder
    gesamt_ersparnis_euro?: number
    co2_ersparnis_kg?: number
    sonderkosten_euro: number
    sonstige_ertraege_euro?: number
    sonstige_ausgaben_euro?: number
    sonstige_netto_euro?: number
    anzahl_monate: number
  }
}

export const investitionenApi = {
  /**
   * Investitionen abrufen (optional gefiltert)
   */
  async list(anlageId?: number, typ?: string, aktiv?: boolean): Promise<Investition[]> {
    const params = new URLSearchParams()
    if (anlageId) params.append('anlage_id', anlageId.toString())
    if (typ) params.append('typ', typ)
    if (aktiv !== undefined) params.append('aktiv', aktiv.toString())
    const query = params.toString()
    return api.get<Investition[]>(`/investitionen/${query ? '?' + query : ''}`)
  },

  /**
   * Einzelne Investition abrufen
   */
  async get(id: number): Promise<Investition> {
    return api.get<Investition>(`/investitionen/${id}`)
  },

  /**
   * Neue Investition erstellen
   */
  async create(data: InvestitionCreate): Promise<Investition> {
    return api.post<Investition>('/investitionen/', data)
  },

  /**
   * Investition aktualisieren
   */
  async update(id: number, data: InvestitionUpdate): Promise<Investition> {
    return api.put<Investition>(`/investitionen/${id}`, data)
  },

  /**
   * Investition löschen
   */
  async delete(id: number): Promise<void> {
    return api.delete(`/investitionen/${id}`)
  },

  /**
   * ROI-Dashboard für eine Anlage abrufen
   */
  async getROIDashboard(
    anlageId: number,
    strompreisCent?: number,
    einspeiseverguetungCent?: number,
    benzinpreisEuro?: number,
    jahr?: number | 'all'
  ): Promise<ROIDashboardResponse> {
    const params = new URLSearchParams()
    if (strompreisCent) params.append('strompreis_cent', strompreisCent.toString())
    if (einspeiseverguetungCent) params.append('einspeiseverguetung_cent', einspeiseverguetungCent.toString())
    if (benzinpreisEuro !== undefined) params.append('benzinpreis_euro', benzinpreisEuro.toString())
    if (jahr && jahr !== 'all') params.append('jahr', jahr.toString())
    const query = params.toString()
    return api.get<ROIDashboardResponse>(`/investitionen/roi/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * CO2-Amortisation: Σ graue Herstellungs-Last (CO2) der Anlage (#284)
   */
  async getCO2Amortisation(anlageId: number): Promise<CO2AmortisationResponse> {
    return api.get<CO2AmortisationResponse>(`/investitionen/co2-amortisation/${anlageId}`)
  },

  /**
   * Warum ein Gerät im Komponenten-Hub keine Monatswerte zeigt (N-247).
   * Der Grund kommt aus dem Backend — keine Client-Ableitung.
   */
  async getHubLeerGrund(anlageId: number, investitionId: number): Promise<HubLeerGrundResponse> {
    return api.get<HubLeerGrundResponse>(
      `/investitionen/hub-leer-grund/${anlageId}/${investitionId}`,
    )
  },

  /**
   * E-Auto Dashboard
   */
  async getEAutoDashboard(anlageId: number, strompreisCent?: number, benzinpreisEuro?: number): Promise<EAutoDashboardResponse[]> {
    const params = new URLSearchParams()
    if (strompreisCent) params.append('strompreis_cent', strompreisCent.toString())
    if (benzinpreisEuro) params.append('benzinpreis_euro', benzinpreisEuro.toString())
    const query = params.toString()
    return api.get<EAutoDashboardResponse[]>(`/investitionen/dashboard/e-auto/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * Wärmepumpe Dashboard
   */
  async getWaermepumpeDashboard(anlageId: number, strompreisCent?: number): Promise<WaermepumpeDashboardResponse[]> {
    const params = new URLSearchParams()
    if (strompreisCent) params.append('strompreis_cent', strompreisCent.toString())
    const query = params.toString()
    return api.get<WaermepumpeDashboardResponse[]>(`/investitionen/dashboard/waermepumpe/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * Speicher Dashboard
   */
  async getSpeicherDashboard(anlageId: number, strompreisCent?: number, einspeiseverguetungCent?: number): Promise<SpeicherDashboardResponse[]> {
    const params = new URLSearchParams()
    if (strompreisCent) params.append('strompreis_cent', strompreisCent.toString())
    if (einspeiseverguetungCent) params.append('einspeiseverguetung_cent', einspeiseverguetungCent.toString())
    const query = params.toString()
    return api.get<SpeicherDashboardResponse[]>(`/investitionen/dashboard/speicher/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * Speicher-Potentialanalyse — „hätte mehr Kapazität geholfen?" (#358 Phase 2).
   * Liest Stundendaten über die Lebensdauer; deutlich teurer als die Dashboards,
   * deshalb nur auf Anforderung der Sicht.
   */
  async getSpeicherPotential(anlageId: number, von?: string, bis?: string): Promise<SpeicherPotentialResponse> {
    const params = new URLSearchParams()
    if (von) params.append('von', von)
    if (bis) params.append('bis', bis)
    const query = params.toString()
    return api.get<SpeicherPotentialResponse>(`/investitionen/speicher-potential/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * Sizing-Simulator — „lohnt sich ein größerer Speicher?" (#358 Phase 3).
   * Die vollständige Kurve (50 %–200 %) kommt in EINER Antwort; der Slider in
   * der Sicht liest daraus und fragt nicht bei jedem Schritt nach.
   */
  async getSpeicherSizing(
    anlageId: number,
    von?: string,
    bis?: string,
    /**
     * Eigener Nachrüstpreis je kWh (N-274). `undefined` = Richtwert des Backends.
     * Bewusst NICHT gespeichert — der Wert gehört zur Frage, nicht zum Gerät.
     */
    richtpreisEurJeKwh?: number,
  ): Promise<SpeicherSizingResponse> {
    const params = new URLSearchParams()
    if (von) params.append('von', von)
    if (bis) params.append('bis', bis)
    // ⚠ `if (x)` waere hier falsch: 0 ist zwar kein gueltiger Preis (die Route
    // verlangt > 0), aber die Pruefung soll die GUELTIGKEIT abfragen, nicht die
    // Wahrheitswertigkeit — sonst steht hier die naechste 0-Werte-Falle.
    if (richtpreisEurJeKwh != null) params.append('richtpreis_eur_je_kwh', String(richtpreisEurJeKwh))
    const query = params.toString()
    return api.get<SpeicherSizingResponse>(`/investitionen/speicher-sizing/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * Wallbox Dashboard
   */
  async getWallboxDashboard(anlageId: number): Promise<WallboxDashboardResponse[]> {
    return api.get<WallboxDashboardResponse[]>(`/investitionen/dashboard/wallbox/${anlageId}`)
  },

  /**
   * Balkonkraftwerk Dashboard
   */
  // N-114 (05.09.2026): kein Vergütungs-Parameter mehr — die Route hat ihn nie
  // gelesen, BKW-Einspeisung ist unvergütet.
  async getBalkonkraftwerkDashboard(anlageId: number, strompreisCent?: number): Promise<BalkonkraftwerkDashboardResponse[]> {
    const params = new URLSearchParams()
    if (strompreisCent) params.append('strompreis_cent', strompreisCent.toString())
    const query = params.toString()
    return api.get<BalkonkraftwerkDashboardResponse[]>(`/investitionen/dashboard/balkonkraftwerk/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * Sonstiges Dashboard
   */
  async getSonstigesDashboard(anlageId: number, strompreisCent?: number, einspeiseverguetungCent?: number): Promise<SonstigesDashboardResponse[]> {
    const params = new URLSearchParams()
    if (strompreisCent) params.append('strompreis_cent', strompreisCent.toString())
    if (einspeiseverguetungCent) params.append('einspeiseverguetung_cent', einspeiseverguetungCent.toString())
    const query = params.toString()
    return api.get<SonstigesDashboardResponse[]>(`/investitionen/dashboard/sonstiges/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * InvestitionMonatsdaten für einen bestimmten Monat laden
   * Wird vom MonatsdatenForm benötigt, um beim Bearbeiten die vorhandenen Daten zu laden
   */
  async getMonatsdatenByMonth(anlageId: number, jahr: number, monat: number): Promise<InvestitionMonatsdaten[]> {
    return api.get<InvestitionMonatsdaten[]>(`/investitionen/monatsdaten/${anlageId}/${jahr}/${monat}`)
  },
}
