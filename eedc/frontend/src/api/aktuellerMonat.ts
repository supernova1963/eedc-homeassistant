/**
 * Aktueller Monat API Client
 *
 * Holt Live-Daten des laufenden Monats aus HA-Sensoren, Connectors und DB.
 */

import { api } from './client'

export interface DatenquelleInfo {
  quelle: string   // "ha_sensor" | "local_connector" | "gespeichert"
  konfidenz: number
  zeitpunkt: string | null
  // Zeitraum, den der Wert tatsächlich misst (ISO). Nur beim Connector gesetzt,
  // dessen Delta aus zwei Zähler-Snapshots stammt; null = unbekannt.
  abdeckung_von?: string | null
  abdeckung_bis?: string | null
}

export interface InvestitionFinancialDetail {
  investition_id: number
  bezeichnung: string
  typ: string
  betriebskosten_monat_euro: number
  erloes_euro: number | null
  ersparnis_euro: number | null
  ersparnis_label: string
  formel: string | null
  berechnung: string | null
  // Sonstige Positionen (z.B. AG-Vergütung Dienstwagen, THG-Quote)
  sonstige_ertraege_euro: number
  sonstige_ausgaben_euro: number
}

export interface SonstigesGeraet {
  bezeichnung: string
  kategorie: 'erzeuger' | 'verbraucher' | string
  erzeugung_kwh?: number | null
  eigenverbrauch_kwh?: number | null
  einspeisung_kwh?: number | null
  verbrauch_kwh?: number | null
  bezug_pv_kwh?: number | null
  bezug_netz_kwh?: number | null
}

export interface AktuellerMonatResponse {
  anlage_id: number
  anlage_name: string
  jahr: number
  monat: number
  monat_name: string
  aktualisiert_um: string

  quellen: Record<string, boolean>
  /** P4-Beschriftung für Teilsummen — über `unvollstaendigHerkunft` rendern. */
  hinweise?: string[]

  // Energie-Bilanz (kWh)
  pv_erzeugung_kwh: number | null
  einspeisung_kwh: number | null
  netzbezug_kwh: number | null
  eigenverbrauch_kwh: number | null
  direktverbrauch_kwh: number | null  // PV direkt verbraucht (ohne Speicher) = EV − Speicher-Entladung
  gesamtverbrauch_kwh: number | null

  // Quoten (%)
  autarkie_prozent: number | null
  eigenverbrauch_quote_prozent: number | null
  // Spez. Ertrag kWh/kWp (Community-Basis) — für die Median-Abweichung im Community-Block.
  spez_ertrag?: number | null

  // Komponenten — Speicher
  speicher_ladung_kwh: number | null
  speicher_entladung_kwh: number | null
  speicher_ladung_netz_kwh: number | null
  speicher_wirkungsgrad_prozent: number | null
  speicher_vollzyklen: number | null
  speicher_kapazitaet_kwh: number | null
  hat_speicher: boolean
  /** F-22: worauf `speicher_wirkungsgrad_prozent` beruht — `soc_korrigiert`
   *  (Ladestand herausgerechnet) · `fenster_lang` · `roh-unkorrigiert` (kein
   *  Ladestand erfasst, Wert plausibel aber ungenau) · `fenster-zu-kurz` /
   *  `nicht-ermittelbar` (kein Wert). `null` bei Antworten vor v4.0.12. */
  speicher_wirkungsgrad_quelle: string | null
  // Etappe C (#264): SoC-Drift-Flag + TEP-basierter effektiver Ladepreis.
  // Seit F-22 bedeutet es „kein belastbarer η", nicht mehr „SoC ist gedriftet".
  speicher_soc_drift_signifikant: boolean
  speicher_effektiver_ladepreis_cent: number | null
  speicher_effektiver_ladepreis_quelle: string | null
  // R15-1 (Rainer-Kostenkacheln): Kosten der Netzladung + verwendeter Preis
  speicher_ladung_netz_kosten_euro: number | null
  speicher_ladung_netz_preis_cent: number | null
  speicher_ladung_netz_preis_quelle: string | null
  /** #358 Phase 1 — Auslastung des Zeitraums und ihre additive Basis
   *  (Kapazität × Tage; im laufenden Monat nur die abgelaufenen Tage).
   *  Über mehrere Monate wird NICHT der Prozentwert gemittelt, sondern
   *  Entladung und Basis summiert und einmal geteilt — ein Februar wiegt
   *  weniger als ein Juli. */
  speicher_auslastungs_basis_kwh: number | null
  speicher_auslastung_prozent: number | null
  /** Σ Speicher-Ersparnis des Zeitraums (Spread-SoT) — dieselbe Zahl wie in
   *  den T-Konto-Zeilen, dort aufgesammelt statt zweitgerechnet. */
  speicher_ersparnis_euro: number | null

  // Komponenten — Wärmepumpe
  wp_strom_kwh: number | null
  wp_waerme_kwh: number | null
  wp_heizung_kwh: number | null
  wp_warmwasser_kwh: number | null
  /** Arbeitszahl — **fertig aus dem Layer**, nicht hier gerechnet (R2/W-3).
   *  `null` heißt: es gibt sie nicht, und `wp_jaz_grund` sagt warum. Der
   *  Client bildete den Quotienten bis 26.08.2026 selbst und **konnte** die
   *  Belastbarkeits-Sperre nicht kennen — dieselbe Anlage zeigte im
   *  Komponenten-Hub „—" und im Cockpit eine Zahl (ADR-001). */
  wp_jaz?: number | null
  /** Warum es keine Arbeitszahl gibt — nie ein „—" ohne Grund (SOLL S3). */
  wp_jaz_grund?: string | null
  /** Fall H-B: die Zahl ist richtig und erklärungsbedürftig (Heizstab).
   *  Der Wortlaut kommt aus dem Layer, damit er nicht je Sicht abweicht. */
  wp_jaz_hinweis?: string | null
  /**
   * Die beiden Zahlen, aus denen die Arbeitszahl **tatsächlich** entstanden ist
   * (kWh) — für die Herleitung an der Kachel.
   *
   * ⚠ Der Nenner ist **nicht** `wp_strom_kwh`: der funktionsfremde Anteil
   * (Kühlen, Lüften, Entfeuchten) ist abgezogen. Deshalb kommen beide Zahlen
   * aus dem Layer und werden hier **nicht** nachgerechnet.
   */
  wp_jaz_zaehler_kwh?: number | null
  wp_jaz_nenner_kwh?: number | null
  /** Ist ein Teil der Wärme aus `Strom × JAZ` gerechnet statt gemessen? */
  wp_waerme_abgeleitet?: boolean | null
  // #191: Strom-Aufteilung Heizung/Warmwasser. Nur befüllt wenn mindestens
  // eine WP-Investition `getrennte_strommessung=true` hat.
  wp_strom_heizen_kwh: number | null
  // #263 K-2: Aufteilung nach Betriebsmodus — Teilmengen von `wp_strom_kwh`,
  // nie Summanden. Alle vier fehlen gemeinsam ohne erfassten Modus.
  wp_modus_strom_heizen_kwh?: number | null
  wp_modus_strom_kuehlen_kwh?: number | null
  /** N-336: die dritte **ableitbare** Betriebsart. ⚠ Nicht dasselbe wie
   *  `wp_strom_warmwasser_kwh` — das ist ein Summand aus der getrennten
   *  Strommessung, dies eine Teilmenge des Gesamtstroms. */
  wp_modus_strom_warmwasser_kwh?: number | null
  /** E4 (Konzept §2.3): nur aus **gemessenen** Betriebsart-Zählern — der aus
   *  dem Modus-Signal abgeleitete Split kann sie nicht. Ohne Zähler 0, dann
   *  stecken sie weiterhin in `wp_modus_nicht_aufgeteilt_kwh`. */
  /** W-4 (SOLL §4.1): Arbeitszahl je Funktion. `null` heißt „gibt es nicht" —
   *  dann sagt `*_grund` warum (S3: nie ein „—" ohne Grund). */
  wp_jaz_heizen?: number | null
  wp_jaz_heizen_grund?: string | null
  wp_jaz_warmwasser?: number | null
  wp_jaz_warmwasser_grund?: string | null
  /** W-5: Arbeitszahl **Kühlen** (Kältemenge ÷ Kühlstrom). Bewusst nicht
   *  „SEER" — das ist eine genormte Prüfstandsgröße, dies ein gemessener
   *  Quotient über einen Zeitraum. */
  wp_jaz_kuehlen?: number | null
  wp_jaz_kuehlen_grund?: string | null
  wp_modus_strom_lueften_kwh?: number | null
  wp_modus_strom_entfeuchten_kwh?: number | null
  wp_modus_nicht_aufgeteilt_kwh?: number | null
  wp_modus_abdeckung_h?: number | null
  /** **W-17b** — die Grundmenge, auf die sich die Aufteilung bezieht.
   *  Bewusst **nicht** der WP-Gesamtstrom: dort steckt auch der Strom von
   *  Geräten ohne Modus-Signal. Ohne dieses Feld stand der Balken stumm unter
   *  einer Kachel mit größerer Zahl (dietmar1968, T89667 #210: 30 kWh unter
   *  284 kWh). Nicht nachrechnen — der Bezug entscheidet die Faltung. */
  wp_modus_strom_bezug_kwh?: number | null
  /** #263: Aufteilung GEMESSEN statt aus dem Betriebsmodus abgeleitet. */
  wp_modus_gemessen?: boolean | null
  /** **W-18** — warum die **Tages**-Wärme fehlt, als fertiger Satz aus dem
   *  Backend. Auf Monat/Jahr immer `null`: dort heisst „—" fehlende
   *  Monatsdaten, ein anderer Sachverhalt mit eigenem Pfad. */
  wp_waerme_grund?: string | null
  /** **W-18**, dieselbe Klasse am PV-Anteil der Ladung (nur Tag). */
  emob_ladung_pv_grund?: string | null
  wp_strom_warmwasser_kwh: number | null
  // Issue #169: Kompressor-Starts (aus TagesZusammenfassung über die Tage des Monats)
  wp_starts_max_tag: number | null
  wp_starts_summe_monat: number | null
  // Issue #238: Betriebsstunden analog zu den Starts (gleiche Counter-Quelle)
  wp_betriebsstunden_max_tag: number | null
  wp_betriebsstunden_summe_monat: number | null
  hat_waermepumpe: boolean

  // Komponenten — E-Mobilität
  emob_ladung_kwh: number | null
  emob_km: number | null
  emob_verbrauch_100km: number | null
  emob_verbrauch_quelle: 'gemessen' | 'ladung' | 'keine'
  emob_ladung_pv_kwh: number | null
  emob_ladung_netz_kwh: number | null
  emob_ladung_extern_kwh: number | null
  emob_v2h_kwh: number | null
  hat_emobilitaet: boolean

  // Komponenten — BKW
  bkw_erzeugung_kwh: number | null
  bkw_eigenverbrauch_kwh: number | null
  hat_balkonkraftwerk: boolean

  // Komponenten — Sonstiges
  sonstiges_erzeugung_kwh: number | null
  sonstiges_eigenverbrauch_kwh: number | null
  sonstiges_einspeisung_kwh: number | null
  sonstiges_verbrauch_kwh: number | null
  sonstiges_bezug_pv_kwh: number | null
  sonstiges_bezug_netz_kwh: number | null
  // Pro-Gerät-Aufschlüsselung (2 Blöcke Erzeuger/Verbraucher, je Gerät eine Zeile)
  sonstiges_geraete?: SonstigesGeraet[]
  hat_sonstiges: boolean

  // Finanzen (Euro)
  einspeise_erloes_euro: number | null
  // §51 EEG: Abzugsvolumen + entgangener Erlös. null = Anlage nicht §51-pflichtig
  // bzw. keine Börsenpreis-Mitschrift; 0 = betroffen, aber nichts abgezogen.
  einspeisung_neg_preis_kwh: number | null
  nicht_vergueteter_erloes_euro: number | null
  netzbezug_kosten_euro: number | null
  // Arbeitspreis-Anteil OHNE Grundpreis (kWh × Ø-Preis). Wo kWh und € so
  // nebeneinander stehen, dass ein Leser sie dividiert, gehört DIESES Feld
  // hin — mit den Gesamtkosten kommt nie der Ø-Preis heraus. Kein zweiter
  // Posten: verrechnet wird weiter netzbezug_kosten_euro.
  netzbezug_arbeitspreis_kosten_euro: number | null
  ev_ersparnis_euro: number | null
  netto_ertrag_euro: number | null
  wp_ersparnis_euro: number | null
  emob_ersparnis_euro: number | null
  // Sonstige Positionen aggregiert (z.B. AG-Vergütung Dienstwagen, THG-Quote).
  // Detail-Zeilen pro Investition stehen in investitionen_financials.
  sonstige_ertraege_euro: number
  sonstige_ausgaben_euro: number
  sonstige_netto_euro: number
  // G19-1: davon Anlage-Ebene (Monatsdaten.sonstige_positionen) — reiner
  // Ausweis für die T-Konto-Zeile „Anlage — Sonstige …", bereits in den
  // sonstige_*-Totals enthalten.
  anlage_sonstige_ertraege_euro: number
  anlage_sonstige_ausgaben_euro: number
  gesamtnettoertrag_euro: number | null
  betriebskosten_anteilig_euro: number | null

  // Tarif-Info
  netzbezug_preis_cent: number | null
  /** N-267: Ist der Preis daneben ein über die Stunden GEWICHTETER Wert
   *  (Zeittarif HT/NT) statt des Arbeitspreises aus den Stammdaten? */
  netzbezug_preis_zeittarif?: boolean
  einspeise_preis_cent: number | null
  netzbezug_durchschnittspreis_cent: number | null
  // G19-1 K3: Grundgebühr des Monats (steckt bereits in netzbezug_kosten_euro,
  // reiner Ausweis) + jährliche Zählergebühr vom Tarif (nur Jahresaufstellung,
  // nicht verrechnet).
  grundgebuehr_euro: number | null
  zaehlergebuehr_euro_jahr: number | null

  // Vergleiche
  vorjahr: {
    pv_erzeugung_kwh?: number
    einspeisung_kwh?: number
    netzbezug_kwh?: number
    eigenverbrauch_kwh?: number
    direktverbrauch_kwh?: number
    gesamtverbrauch_kwh?: number
    autarkie_prozent?: number
    wp_strom_kwh?: number
    wp_waerme_kwh?: number
    emob_ladung_kwh?: number
    emob_km?: number
    speicher_ladung_kwh?: number
    speicher_entladung_kwh?: number
    einspeise_erloes_euro?: number
    netzbezug_kosten_euro?: number
    netzbezug_arbeitspreis_kosten_euro?: number
    ev_ersparnis_euro?: number
    gesamtnettoertrag_euro?: number
    netzbezug_durchschnittspreis_cent?: number
  } | null
  // PVGIS-SOLL. Im LAUFENDEN Monat nur der Anteil der abgelaufenen Tage (N-69) —
  // `soll_pv_tage < soll_pv_tage_gesamt` heißt „anteilig". Wer die Zahl anzeigt,
  // nimmt `lib/sollErfuellung.ts`, nicht die Felder direkt.
  soll_pv_kwh: number | null
  soll_pv_tage?: number | null
  soll_pv_tage_gesamt?: number | null
  /** Dasselbe SOLL ungekürzt = Prognose für den ganzen Monat (dietmar1968,
   *  T89667 #155). Kommt fertig aus der Antwort und wird **nicht** aus
   *  `soll_pv_kwh` zurückgerechnet — das würde dessen Rundung mit
   *  `tage_gesamt ÷ tage` vergrößern. Im Jahres-Aggregat nicht belegt. */
  soll_pv_kwh_monat?: number | null

  // Grundlast (Nacht-Sockel; R12-1 ersetzt PVGIS-SOLL/IST). grundlast_kwh additiv
  // → Cockpit/Jahr (JahrAggregat) summiert die Monate.
  grundlast_kw?: number | null              // Median der Nacht-Stunden-Leistung
  grundlast_kwh?: number | null             // geschätzte Grundlast-Energie (kW × 24 × Tage)
  grundlast_anteil_prozent?: number | null  // Anteil am Gesamtverbrauch

  // Per-Investition Finanzdetails (T-Konto)
  investitionen_financials: InvestitionFinancialDetail[]
  // Aktive Geräte je Typ im Monat (Namen) — für „aggregiert aus …"-Hinweise
  komponenten_geraete: Record<string, string[]>

  // Quellenangabe pro Feld
  feld_quellen: Record<string, DatenquelleInfo>
}

export const aktuellerMonatApi = {
  getData: (anlageId: number, jahr?: number, monat?: number) => {
    const params = new URLSearchParams()
    if (jahr !== undefined) params.set('jahr', String(jahr))
    if (monat !== undefined) params.set('monat', String(monat))
    const query = params.toString()
    return api.get<AktuellerMonatResponse>(`/aktueller-monat/${anlageId}${query ? '?' + query : ''}`)
  },
}
