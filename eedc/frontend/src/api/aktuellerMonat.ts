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
  /** Jahresbetrag, aus dem `betriebskosten_monat_euro` der Zwölftel ist (A6). */
  betriebskosten_jahr_euro?: number
  erloes_euro: number | null
  /** Herleitung der Erlös-Zeile — je Typ verschieden (gerechnet vs. gepflegt). */
  erloes_formel: string | null
  /**
   * Die **eingesetzten Werte** zur Formel darüber (A6). `null` bei den
   * gepflegten Erlösen — dort gibt es keine Rechnung, nur eine Herkunftsangabe.
   * Optional, damit ältere Antworten ohne das Feld weiter gelten.
   */
  erloes_berechnung?: string | null
  /**
   * Anzeigename der Erlös-Zeile („{Gerät} — {erloes_label}"). Kommt aus dem
   * Backend, weil ihn die **Kategorie** entscheidet: „Einspeisung" für BKW und
   * sonstige Erzeuger, „Abgabe an Dritte" für den dritten Weg (§9.2). Optional,
   * damit ältere Antworten den Fallback des Clients behalten.
   */
  erloes_label?: string
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
  /** §9.2 — Abgabe an Dritte (kategorie 'abgabe'). */
  abgabe_kwh?: number | null
  erloes_euro?: number | null
}

/** Eine Zeile der Tabelle „Zahlen je Gerät" im Wärme/Klima-Block (D-Sicht 3).
 *  Aus **derselben** Rechenstelle wie der Komponenten-Hub. */
export interface WpGeraetZeile {
  investition_id: number
  name: string
  strom_kwh?: number | null
  waerme_kwh?: number | null
  /** Warum die Wärme-Zelle leer ist (WK-16h/R-4) — aus dem Layer, nicht aus
   *  dem Client. */
  waerme_grund?: string | null
  jaz?: number | null
  jaz_grund?: string | null
  jaz_heizen?: number | null
  jaz_heizen_grund?: string | null
  jaz_warmwasser?: number | null
  jaz_warmwasser_grund?: string | null
  jaz_kuehlen?: number | null
  jaz_kuehlen_grund?: string | null
  /** Die **Wärme-Achsen** dieses Geräts (WK-16h/R-1) — `'heizen'` und/oder
   *  `'warmwasser'`, Spiegel von `services/waerme_klima_block.py`.
   *
   *  Eine Zelle ohne Zahl hat zwei Bedeutungen, und nur dieses Feld trennt
   *  sie: fehlt die Achse, bleibt die Zelle **leer** (kein Strich, kein
   *  Tooltip — „gilt nicht" ist kein Mangel); gilt sie, steht dort „—" mit
   *  dem Grund als Tooltip. */
  achsen?: string[] | null
}

/** Eine Zeile des Kastens „Was noch möglich wäre" (D-Sicht 1) — **eine je
 *  Grund**, nicht je Kachel. `groesse` nennt alle betroffenen Größen. */
export interface WpMoeglichZeile {
  /** Die betroffenen Größen als **Bezeichner** — womit der Client abfragt,
   *  ob eine Kachel in den Kasten gewandert ist. Ein Bezeichner ist ein
   *  Schlüssel, ein Grund-Satz ist eine Formulierung. */
  groessen: string[]
  /** Dieselben Größen als Anzeigetext („A · B"). */
  groesse: string
  grund: string
  handgriff?: string | null
  link?: string | null
}

/** Ein Summand der Ergebnis-Herleitung — Betrag MIT Vorzeichen, Antwortfeld als Quelle (A6). */
export interface ErgebnisPostenWert {
  name: string
  betrag_euro: number | null
  feld: string
  /** +1 Ertrag, −1 Aufwand — unabhängig vom Betrag. */
  vorzeichen: number
}

/** Eine Stufe der Ergebnis-Leiter: Formel, eingesetzte Werte, Ergebnis — aus derselben Rechnung wie der Wert. */
export interface ErgebnisStufe {
  formel: string
  eingesetzte_werte: ErgebnisPostenWert[]
  ergebnis_euro: number | null
}

export interface ErgebnisHerleitung {
  netto_ertrag: ErgebnisStufe
  vor_betriebskosten: ErgebnisStufe
  ergebnis: ErgebnisStufe
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
  /** HA-Bauform E4b (N-588 — angezeigt, nicht bewertet): Σ String-Zähler − Anlagenzähler; `null` ohne
   *  Anlagenzähler oder ohne Kanal-Deckung. Prozent aus dem Layer (Bezug: Σ der String-Zähler). */
  wandlungsverluste_kwh?: number | null
  wandlungsverluste_bezug_kwh?: number | null
  wandlungsverluste_prozent?: number | null

  // Quoten (%)
  autarkie_prozent: number | null
  eigenverbrauch_quote_prozent: number | null
  /** Nur im Jahr (R-Q, N-584): Zähler, Nenner, Fenster der paarweise gebildeten Quoten. */
  autarkie_zaehler_kwh?: number | null
  autarkie_nenner_kwh?: number | null
  autarkie_fenster?: string | null
  eigenverbrauch_quote_zaehler_kwh?: number | null
  eigenverbrauch_quote_nenner_kwh?: number | null
  eigenverbrauch_quote_fenster?: string | null
  speicher_auslastung_zaehler_kwh?: number | null
  speicher_auslastung_nenner_kwh?: number | null
  speicher_auslastung_fenster?: string | null
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
  /** Steht mindestens eine hier gesperrte Kennzahl im Komponenten-Hub?
   *  Die Entscheidung fällt im Layer (`GRUENDE_HUB_HILFT`) — der Client
   *  vergleicht bewusst keine Grund-Texte. */
  wp_hub_hilft?: boolean | null
  /** **Wie viel** davon gerechnet ist. Das Flag darüber sagt „irgendein Teil"
   *  und ist für die **Kennzahl** richtig so (alles-oder-nichts, sonst käme
   *  gemessene Wärme ÷ Gesamtstrom heraus). Für eine **Menge** — etwa die
   *  Wärmelinie im Verlauf, die nur Gemessenes zeigen darf — ist die Differenz
   *  `wp_waerme_kwh − wp_waerme_abgeleitet_kwh` die richtige Größe. */
  wp_waerme_abgeleitet_kwh?: number | null
  /** B4 (C-2): Herkunft der Wärme („gemessen" | „geschätzt: Strom × JAZ 3,5") und der
   *  Vorbehalt an Ersparnis/CO₂ — fertig aus dem Layer, dieselben Worte wie im Hub. */
  wp_waerme_herkunft?: string | null
  /** R-4/N-491 (**nur Cockpit → Tag**): „gemessen ab 11:00 Uhr", wenn der Tag
   *  nicht von 0 bis 24 Uhr gemessen ist — erster Tag nach der Zuordnung bzw.
   *  laufender Tag. `null`/undefined überall sonst. Der Satz kommt fertig aus
   *  dem Layer (`core/tageswert_grund.py`). */
  wp_abdeckung_hinweis?: string | null
  wp_ersparnis_vorbehalt?: string | null
  /** B6/Y-3: der Rechenweg hinter der Ersparnis, aus dem Layer-Ergebnis. */
  wp_ersparnis_berechnung?: string | null
  /** N-555: der Rechenweg hinter `emob_ersparnis_euro` je Fahrzeug, aus dem Backend
   *  (km × Vergleichsverbrauch × Benzinpreis des Monats) — kein fester Default im Client. */
  emob_ersparnis_berechnung?: string | null
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
  /** E1b — siehe {@link WpGeraetZeile}. */
  wp_jaz_ist_schranke?: boolean | null
  /** Der EINE Satz unter der Schranke: „Klimaanlage: Strom ohne Wärmemessung
   *  enthalten". Fertig formuliert aus dem Layer. */
  wp_jaz_schranke_hinweis?: string | null
  /** D-Sicht 3: die Kennzahlen **je Gerät**, im Block selbst. */
  wp_geraete?: WpGeraetZeile[] | null
  /** D-Sicht 1: was die Ausstattung nicht hergibt — **einmal je Sicht**, mit
   *  Handgriff. Eine Größe, deren Grund hier steht, bekommt **keine** Kachel
   *  mit „—"; eine Größe mit einem Zeitraum-Grund bleibt als „—" ohne Text. */
  wp_moeglich?: WpMoeglichZeile[] | null
  /** Bauschnitt 6b: gemessene **Kälte** des Monats — der Zähler der
   *  Arbeitszahl Kühlen daneben. `null`, wo kein Kältemengenzähler etwas
   *  gemeldet hat (keine 0 ohne Messung). */
  wp_kaelte_kwh?: number | null
  wp_modus_strom_lueften_kwh?: number | null
  wp_modus_strom_entfeuchten_kwh?: number | null
  /** **R-C (WK-16f, N-398): die abgegebene Nutzenergie** derselben zwei
   *  Betriebsarten — als **Menge** neben ihrem Strom. E4 bleibt: daraus
   *  entsteht keine Arbeitszahl, weil eedc den Nutzen von Lüften und
   *  Entfeuchten nicht bewerten kann. Nur gesetzt, wenn ein Zähler etwas
   *  gemeldet hat; sonst steht die Zeile nicht da (D-Sicht). */
  wp_modus_nutzenergie_lueften_kwh?: number | null
  wp_modus_nutzenergie_entfeuchten_kwh?: number | null
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
  /** N-557: „Ladung gesamt" = Heimladung + Extern, soweit Extern bekannt ist —
   *  eine eigene Anzeige-Größe; `emob_ladung_kwh` bleibt die Heimladung (PV-Anteil,
   *  T-Konto rechnen mit ihr). Optional: der Tag kennt kein Extern. */
  emob_ladung_gesamt_kwh?: number | null
  /** N-557: die Menge hinter `emob_verbrauch_100km` — damit ein Zeitraum
   *  Σ Monatswerte ÷ Σ km bilden kann (Backend `eauto_effizienz_zeitraum`, Jahresroute). */
  emob_verbrauch_basis_kwh?: number | null
  hat_emobilitaet: boolean

  // Komponenten — BKW
  bkw_erzeugung_kwh: number | null
  bkw_eigenverbrauch_kwh: number | null
  hat_balkonkraftwerk: boolean

  // Komponenten — Sonstiges
  sonstiges_erzeugung_kwh: number | null
  /** §9.2 — an Dritte abgegebene kWh (dritter Weg der Verwendung). */
  abgabe_dritte_kwh?: number | null
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
  /** N-633: dienstliche Ladekosten (Aufwand, positiv) — eigener Posten der Ergebnis-Leiter, NICHT in den
   *  `sonstige_*`-Feldern. Optional für Antworten vor diesem Feld. */
  dienstliche_ladekosten_euro?: number
  /** Eingesetzte Werte dazu (A6), z. B. „60,0 kWh PV × 30,00 ct/kWh + 30,0 kWh Netz × 30,00 ct/kWh"; im Jahr null. */
  dienstliche_ladekosten_berechnung?: string | null
  // G19-1: davon Anlage-Ebene (Monatsdaten.sonstige_positionen) — reiner
  // Ausweis für die T-Konto-Zeile „Anlage — Sonstige …", bereits in den
  // sonstige_*-Totals enthalten.
  anlage_sonstige_ertraege_euro: number
  anlage_sonstige_ausgaben_euro: number
  // ── Ergebnis-Leiter (Backend-Layer `core/berechnungen/ergebnis.py`, 03.10.2026) ──
  // Der Client RECHNET diese Größen nicht (Wächter `check:ergebnis-roh`); er liest Wert und Herleitung.
  /** USt-Anteil auf den Eigenverbrauch (EV × Satz des Jahres); `null` ohne Regelbesteuerung. */
  ust_eigenverbrauch_euro?: number | null
  /** Satz und Grundlage als fertiger Satz. */
  ust_herleitung?: string | null
  /** BKW-Rest-Ersparnis (nur BKW-Monate ohne erfasste Erzeugung, P9). */
  bkw_ersparnis_euro?: number | null
  /** Eingesetzte Werte zur BKW-Ersparnis („40,0 kWh × 30,00 ct/kWh“), A6; im Jahr null. */
  bkw_ersparnis_berechnung?: string | null
  /** N-607 (A-2): Preis der Eigenverbrauchs-Ersparnis — EV-gewichteter Ø der gemessenen Stunden, sonst Bezugspreis. */
  ev_preis_cent?: number | null
  /** „ev_gemessen“ oder die Herkunft des Bezugspreises. */
  ev_preis_herkunft?: string | null
  /** Erlös von Erzeugern mit eigenem Vergütungssatz. */
  erzeuger_erloes_euro?: number | null
  /** Stufe 2 — ohne eigenen UI-Namen, nur Zwischenzeile der Herleitung. */
  ergebnis_vor_betriebskosten_euro?: number | null
  /** Stufe 3 — das Monats-/Jahresergebnis. */
  ergebnis_euro?: number | null
  ergebnis_herleitung?: ErgebnisHerleitung | null
  /** Fehlende Posten (Pflicht ⇒ Stufe `null`; optional ⇒ als 0 gerechnet, hier genannt). */
  fehlende_posten?: string[]
  betriebskosten_anteilig_euro: number | null
  /** Σ der Jahresbeträge hinter `betriebskosten_anteilig_euro` und ihre Anzahl (A6). */
  betriebskosten_anteilig_jahr_euro?: number | null
  betriebskosten_anteilig_anzahl?: number | null

  // Tarif-Info
  netzbezug_preis_cent: number | null
  /** N-267: Ist der Preis daneben ein über die Stunden GEWICHTETER Wert
   *  (Zeittarif HT/NT) statt des Arbeitspreises aus den Stammdaten? */
  netzbezug_preis_zeittarif?: boolean
  einspeise_preis_cent: number | null
  netzbezug_durchschnittspreis_cent: number | null
  /** Der Preis, mit dem das Geld dieses Monats gerechnet wurde — Ergebnis der
   *  vollen Kaskade, zu dem `_herkunft` und `_abdeckung` gehören.
   *
   *  ⚠ **Diesen Wert zeigt die Kachel**, nicht `netzbezug_preis_cent` (das ist
   *  der verwendete Tarif). Bis 2026-09-17 fehlte er in der Antwort, und die
   *  Kachel zeigte im laufenden Monat den Stammpreis unter einer Formelzeile,
   *  die „gemessen" sagte (OB73-gif). SOLL Flex-Tarife H-2. */
  netzbezug_preis_effektiv_cent?: number | null
  /** Welche Stufe der Preis-Kaskade gegriffen hat (#412):
   *  `gepflegt` (abgerechneter Ø aus dem Monatsabschluss) · `gemessen` (Ø der
   *  mitgeschriebenen Stundenpreise) · `zeitfenster` (HT/NT, über den Netzbezug
   *  gewichtet) · `stamm` (Tarifspalte). Ohne diese Angabe wäre ein gemessener
   *  Preis von einem Stammpreis nicht zu unterscheiden. */
  netzbezug_preis_herkunft?: 'gepflegt' | 'gemessen' | 'zeitfenster' | 'stamm' | null
  /** Anteil der Monatsstunden mit Preisdaten (0..1) — nur bei `gemessen`. */
  netzbezug_preis_abdeckung?: number | null
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
    netzbezug_durchschnittspreis_cent?: number
    /** Ergebnis-Leiter des Vorjahresmonats — dieselbe Regel wie der Monat (E5): ohne Stromrechnung kein Ergebnis. */
    netto_ertrag_euro?: number | null
    ust_eigenverbrauch_euro?: number | null
    bkw_ersparnis_euro?: number | null
    erzeuger_erloes_euro?: number | null
    sonstige_netto_euro?: number | null
    dienstliche_ladekosten_euro?: number | null
    betriebskosten_anteilig_euro?: number | null
    ergebnis_vor_betriebskosten_euro?: number | null
    ergebnis_euro?: number | null
    ergebnis_herleitung?: ErgebnisHerleitung | null
    fehlende_posten?: string[]
  } | null
  // PVGIS-SOLL. Im LAUFENDEN Monat nur der Anteil der abgelaufenen Tage (N-69) —
  // `soll_pv_tage < soll_pv_tage_gesamt` heißt „anteilig". Wer die Zahl anzeigt,
  // nimmt `lib/sollErfuellung.ts`, nicht die Felder direkt.
  soll_pv_kwh: number | null
  /** SOLL-Erfüllung aus dem Layer (`soll_erfuellung`) — der Client teilt nicht selbst (N-356). */
  soll_erfuellung_prozent?: number | null
  soll_erfuellung_monat_prozent?: number | null
  soll_fenster_text?: string | null
  soll_pv_tage?: number | null
  soll_pv_tage_gesamt?: number | null
  /** Dasselbe SOLL ungekürzt = Prognose für den ganzen Monat (dietmar1968,
   *  T89667 #155). Kommt fertig aus der Antwort und wird **nicht** aus
   *  `soll_pv_kwh` zurückgerechnet — das würde dessen Rundung mit
   *  `tage_gesamt ÷ tage` vergrößern. Im Jahres-Aggregat nicht belegt. */
  soll_pv_kwh_monat?: number | null

  // Grundlast (Nacht-Sockel; R12-1 ersetzt PVGIS-SOLL/IST). grundlast_kwh additiv
  // → Cockpit/Jahr (Jahresroute, `falte_zeitraum`) summiert die Monate.
  grundlast_kw?: number | null              // Median der Nacht-Stunden-Leistung
  grundlast_kwh?: number | null             // geschätzte Grundlast-Energie (kW × 24 × Tage)
  grundlast_anteil_prozent?: number | null  // Anteil am Gesamtverbrauch

  // Per-Investition Finanzdetails (T-Konto)
  investitionen_financials: InvestitionFinancialDetail[]
  // Aktive Geräte je Typ im Monat (Namen) — für „aggregiert aus …"-Hinweise
  komponenten_geraete: Record<string, string[]>

  // Quellenangabe pro Feld
  feld_quellen: Record<string, DatenquelleInfo>
  /**
   * Warum eine Kachel **leer** bleibt — je Basis-Größe der fertige Satz aus
   * `core/monatswert_grund.py` (N-472). Nur für Größen ohne Wert gesetzt.
   *
   * ⛔ **Der Client baut hier keinen Text.** Die Route liefert den Satz, nicht
   * den Schlüssel — eine TS-Kopie der Textliste wäre eine zweite Wahrheit über
   * denselben Sachverhalt und driftet, sobald jemand einen Fall ergänzt (die
   * Klasse, die F-56 und W-14 erzeugt hat; dieselbe Regel wie bei den
   * Tageswert-Gründen aus W-18).
   */
  datenlage_gruende?: Record<string, string>
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
