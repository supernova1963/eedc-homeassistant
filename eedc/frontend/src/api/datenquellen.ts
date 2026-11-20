/**
 * Datenquellen-Zuordnung API (Datenquellen-V4 / B2+B3).
 *
 * Feld-zentrische Fläche: je Anlage die gruppierte eedc-Feldliste (Basis + je
 * Investition, Live + Energie) mit Standard-Inbound-Topic. B3 ergänzt den
 * `#`-Discovery-Scan und die MQTT-Gateway-Quelle (Topic + Transform).
 */
import { api } from './client'

/** Eine Betriebsart des Kanons mit den rohen States, die eedc ihr zuordnet. */
export interface BetriebsmodusWerteGruppe {
  /** Kanon-Wert, z. B. `'heizen'` — `'unbestimmt'` für auto/heat_cool/automatik. */
  kanon: string
  /** Klartext der Betriebsart, z. B. `'Heizen'`. */
  label: string
  /** Rohe States, z. B. `['heat', 'heizen']`. */
  werte: string[]
}

export interface DatenquelleFeld {
  /** Stabile Feld-Kennung (späterer Zuordnungs-Schlüssel). */
  id: string
  feld: string
  /** Investitionstyp der Gruppe ('basis' für Anlagen-Felder) — #343-Vorschläge. */
  typ: string
  label: string
  einheit: string
  kategorie: 'live' | 'energy' | 'preis'
  /** Feld-Hilfetext aus der Registry (field_definitions) — leer wenn keiner. */
  hinweis: string
  standard_topic: string
  /** Nur als HA-Sensor lesbar (Preis-Felder): Gateway/Inbound entfallen. */
  nur_ha?: boolean
  /** #263 K-2: Zustand statt Zahl (Betriebsmodus) — vom Backend schon immer geliefert, hier nachgetragen (P-433-2).
   *  Seit HA-Bauform §9 auch über das Inbound-Topic. Seit P-433-2b K2b reicht das Gateway an ein Zustandsfeld den
   *  Text weiter (ohne Faktor/Offset); nur am Betriebsmodus bleibt der Gateway-Knopf aus (D3). */
  zustand?: boolean
  /** P-433-2b K1: Datenquellen-Abschnitt aus der Registry — `'zustand'` ⇒ «Zustand & Sitzung», sonst nach Einheit. */
  abschnitt?: string | null
  /** Aktive Quelle. */
  quelle: string
  /** Zugeordnetes Gateway-Quell-Topic (nur bei quelle==='mqtt_gateway'). */
  gateway_topic: string | null
  /** Zugeordnete HA-Entity (nur bei quelle ha_app/ha_connector). */
  ha_entity: string | null
  /** Klarname der Entity aus HA (null, wenn HA sie nicht kennt). */
  ha_name?: string | null
  /** Invert-Modell: Vorzeichen der Zuordnung umkehren (HA/Inbound; am Read
   *  angewendet). Bei Gateway steckt der Sign im Transform-Modal. */
  invertieren: boolean
  /** Aktueller Wert aus dem MQTT-Inbound-Cache (null = nichts empfangen). Immer eine Zahl:
   *  ein Zustandsfeld trägt seinen Wert in `wert_text`, auch über MQTT (HA-Bauform §9). */
  wert: number | null
  /**
   * F-53: Roher State eines **Zustandsfelds** (`zustand === true`), z. B.
   * `'cool'` aus HA oder `'2'` vom MQTT-Topic. Bei Zahlenfeldern immer `null` — dort gilt `wert`.
   * Ein Zustand ist nie numerisch; `wert` bleibt für ihn `null`, und ohne
   * dieses Feld sah eine funktionierende Zuordnung wie ein Ausfall aus (#263).
   */
  wert_text?: string | null
  /**
   * F-53: Die Deutung desselben States im Kanon, z. B. `'Kühlen'` — oder
   * `'Unbestimmt'`, wenn eedc die Schreibweise nicht kennt. **Kommt aus dem
   * Backend** (`core/betriebsmodus.py`): eine zweite Tabelle hier wäre Drift.
   */
  wert_klartext?: string | null
  /**
   * P-433-0 (Konzept #433 E12): die Werte, die eedc an diesem Feld versteht —
   * nur am Feld „Betriebsmodus“, sonst `null`. **Kommt aus dem Backend**
   * (`core/betriebsmodus.py::betriebsmodus_werte_je_betriebsart`), abgeleitet
   * aus der Werte-Tabelle des Kanons: eine getippte Liste hier wäre Drift.
   */
  zulaessige_werte?: BetriebsmodusWerteGruppe[] | null
  /** ISO-Zeit des letzten Cache-Werts (null = keiner). */
  wert_zeit: string | null
  /** §2i: diagnostische Zuordnungs-Probleme (leer = sauber). */
  probleme: FeldProblem[]
  /**
   * §2i-6: Ist eine fehlende Quelle hier überhaupt eine Lücke?
   *  - `pflicht`  — ohne Wert fehlt eine Kernauswertung → Pflicht-Marker,
   *                 bei leerer Quelle rot + Hinweis aufgeklappt.
   *  - `optional` — leer ist in Ordnung, zählt nicht als offener Punkt.
   *  - `inaktiv`  — hier nicht zu erfassen, ein anderer Weg gewinnt
   *                 (Alternativ-Gruppe belegt oder vom Anlagen-Kontext verdrängt).
   */
  bedarf: 'pflicht' | 'optional' | 'inaktiv'
  /** Maschinenlesbarer Grund bei `inaktiv` (z. B. 'gruppe:pv_energie'). */
  bedarf_grund: string | null
  /** Erklärsatz bei `inaktiv` — ersetzt „keine Quelle" in der Zeile. */
  bedarf_text: string | null
  /**
   * R1 (SOLL Wärme/Klima §3.2a): Die Größe ist an dieser Bauart **untypisch,
   * aber möglich** — etwa die Kühl-Achse an einer Luft-Wasser-Wärmepumpe. Solche
   * Felder stehen im eigenen Abschnitt „Weitere Größen erfassen" statt in der
   * ersten Reihe.
   *
   * ⚠ **Das Backend setzt es nur, solange keine Quelle zugeordnet ist** — mit
   * Quelle rückt das Feld in seinen Einheiten-Abschnitt vor. Der Client muss
   * die Bedingung also nicht nachbauen; täte er es, wäre es die zweite Stelle
   * für dieselbe Regel.
   */
  erweitert?: boolean
  /**
   * **R-A (WK-16f, Prinzip F-7): wo dieser Wert erscheint** — als fertige
   * Wegbeschreibungen („Cockpit → Monat", „Komponenten → Wärmepumpe").
   *
   * ⚠ **Der Client hält keine eigene Tabelle.** Die Sätze kommen aus
   * `core/feld_auswertungen.py`; sie hier nachzubauen wäre die Drift, die bei
   * `FeldProblem.art` schon einmal passiert ist (N-35/N-40). Leer heißt
   * „dieses Feld hat heute keine Auswertung" — dann steht auch nichts da,
   * statt eines Satzes, der nichts nennt.
   */
  ausgewertet_in?: string[]
  /**
   * P-433-2 (Variante C, #431): die Betriebsart, zu der ein **Wärmepumpen**-Feld gehört
   * (`heizen` · `warmwasser` · `kuehlen` · `lueften` · `entfeuchten` · `geraet`) — Registry-Attribut,
   * vom Backend durchgereicht; an anderen Typen `null`.
   */
  betriebsart?: string | null
  /** P-433-2: `strom` oder `waerme` an kWh-Feldern der Wärmepumpe (Thermisch-SoT des Backends), sonst `null`. */
  menge?: 'strom' | 'waerme' | null
}

/** Diagnostisches Zuordnungs-Problem (§2i) — rein informativ, keine Sperre. */
export interface FeldProblem {
  /**
   * ⚠ Diese Liste ist eine **Kopie** der Backend-Werte
   * (`services/datenquellen_validierung.py`) und wird von nichts zusammen-
   * gehalten. `teilweise_verdraengt` fehlte hier zunächst, weil schon sein
   * Vorgänger `nur_monat` bei der Einführung nicht nachgetragen wurde —
   * folgenlos nur deshalb, weil die Zeile `p.text` generisch rendert und
   * einzig `redundant` einen Sonderweg hat. Belegfall für die offene
   * Vokabular-Kopplung (N-35/N-40).
   */
  art:
    | 'einheit'
    | 'state_class'
    | 'redundant'
    | 'doppelmapping'
    | 'takt'
    | 'teilweise_verdraengt'
    /** Bauschnitt 7: „Leistung gesamt" verdrängt an derselben Wärmepumpe die
     *  Verlaufs-Aufteilung nach Heizen/Warmwasser. **Bewusst nicht `redundant`** —
     *  dessen Inline-Knopf „auf keine setzen" würde hier das Feld der Zeile
     *  leeren, also die Aufteilung statt der Gesamtleistung. */
    | 'gesamtleistung_verdraengt'
    /** N-537: Ein Balkonkraftwerk mit zugeordneten PV-Modulen hat seine
     *  Erzeugung an sie abgetreten (N-266) — sein Wert füllt nur noch ihre
     *  Lücken. **Bewusst nicht `redundant`**: dessen Knopf „auf keine setzen"
     *  wäre bei teilweise gemessenen Modulen falscher Rat, weil der Wert dann
     *  die einzige Quelle für das ungemessene Modul ist. */
    | 'bkw_fuellt_luecken'
    /** HA-Bauform E4b (Lab 4.1.3-rc1): der kWh-Anlagenzähler, wenn jede PV-Quelle
     *  einen eigenen Zähler hat — Vergleichsseite der Wandlungsverluste und Füller
     *  für Zeiträume ohne String-Werte. **Bewusst nicht `redundant`**: dessen Knopf
     *  „auf keine setzen" nähme die Wandlungsverluste-Zeile weg. */
    | 'anlagenzaehler_vergleich'
  /** `info`: kein Fehler, nur eine Folge der Zuordnung (Bauschnitt 7). */
  schwere: 'error' | 'warning' | 'info'
  text: string
  /**
   * `redundant`: die wirksamen Komponenten-Felder.
   * `teilweise_verdraengt`: umgekehrt die Erzeuger, denen der eigene Zähler
   * FEHLT — sie sind der Weg aus der halben Zuordnung heraus.
   */
  wirksame_felder?: string[]
  /** nur art==='doppelmapping'. */
  entity_id?: string
  andere_felder?: string[]
}

/**
 * Themen-Kacheln (4.2.0): ein Eintrag eines Themas — eine frei gewählte HA-Entität bzw. ein MQTT-Topic. Der Wert
 * kommt **wie geliefert** (`wert_text`, kein Kanon); `null` ⇒ amber (zugeordnet, aber ohne Wert).
 */
export interface ThemaEintragZeile {
  /** Kennung im Store (`e<n>`). */
  id: string
  label: string
  /** Feld-ID der Quelle (`inv_thema_<inv>_<e>`) — für `setQuelle`. */
  feld_id: string
  quelle: string
  ha_entity: string | null
  ha_name: string | null
  gateway_topic: string | null
  /** Inbound-Topic des Eintrags (`…/live/inv/<id>_<name>/thema_<e>`). */
  standard_topic: string
  wert_text: string | null
  einheit: string
  wert_zeit: string | null
}

/** Themen-Kacheln (4.2.0): ein Thema eines Geräts mit Block «Überblick» — eine Kachel im Schaubild. */
export interface ThemaGruppe {
  /** Kennung im Store (`t<n>`). */
  id: string
  name: string
  eintraege: ThemaEintragZeile[]
}

/** Antwort der Themen-Routen: die Themen des Geräts in der Form von `GET /felder`. */
export interface ThemenAntwort {
  investition_id: number
  themen: ThemaGruppe[]
}

export interface DatenquelleGruppe {
  id: string
  titel: string
  typ: string
  felder: DatenquelleFeld[]
  /** Themen-Kacheln (4.2.0): je Gerät die Themen — `[]` an Typen ohne «Überblick», fehlt an der Basis-Gruppe. */
  themen?: ThemaGruppe[]
  /** P-433-2, nur Wärmepumpe: Stammdatum `kuehlung_art` (`keine` · `passiv` · `aktiv`). */
  kuehlung_art?: string
  /** P-433-2, nur Wärmepumpe: Betriebsarten, die eedc aus einem Betriebsmodus-Sensor ableitet (Kanon). */
  modus_ableitbar?: string[]
}

/** Verfügbarkeit der Quell-Achsen (Schritt B Gating). */
export interface DatenquellenVerfuegbarkeit {
  /** HA-Sensor wählbar (Supervisor ODER Remote-HA verbunden). */
  ha: boolean
  /** Aktiver HA-Transport ('ha_app' | 'ha_connector' | null). */
  ha_quelle: string | null
  /** MQTT-Broker aktiv (Gateway + Inbound wählbar). */
  mqtt: boolean
}

export interface DatenquellenResponse {
  anlage_id: number
  gruppen: DatenquelleGruppe[]
  verfuegbarkeit: DatenquellenVerfuegbarkeit
}

/** Ein HA-Sensor-Kandidat für den HA-Sensor-Picker (Schritt B). */
export interface HaSensor {
  entity_id: string
  friendly_name: string | null
  unit: string | null
  device_class: string | null
  state: string | null
  /** Themen-Kacheln (4.2.0): HA-Domain (`lock`, `sensor` …) — der Themen-Picker zeigt sie an der Zeile. */
  domain?: string | null
}

/** Kuratierter Feld-Vorschlag aus der Integrations-Wissensbasis (#343 A, D2). */
export interface HaVorschlag {
  integration: string
  label: string
  entity_id: string
  hinweis: string
}

export interface HaSensorenResponse {
  verfuegbar: boolean
  quelle: string | null
  sensoren: HaSensor[]
  fehler: string | null
  /** #343 A: erkannte Integrationen + Feld-Vorschläge + Anti-Empfehlungen. */
  integrationen: string[]
  vorschlaege: HaVorschlag[]
  warnungen: Record<string, string>
}

/** Takt-Check-Ergebnis (#343 B): geprueft=false = nicht prüfbar (still). */
export interface TaktCheckResponse {
  geprueft: boolean
  problem: { art: string; schwere: string; text: string } | null
}

export interface QuelleSaveResult {
  gespeichert: boolean
  field_id: string
  quelle: string
  /** Sensorwechsel mit Grund: je Korrektur der Hintergrund-Lauf (leer ohne Korrektur); U2 Lauf b: auch der Lauf eines
   *  Wechsels «bleiben» (`art: 'ansetzen'`). */
  korrektur: KorrekturLaufStart[]
  /** U2 Lauf b: je Wechsel «bleiben», den eedc noch nicht wie Home Assistant rechnet, der Grund als Satz. */
  wartet?: WartenderWechsel[]
}

/** Grund einer fragepflichtigen Quellen-Änderung (Sensorwechsel mit Grund, Bauplan B-2). */
export type WechselGrund = 'fortsetzung' | 'korrektur'

export interface GrundAngabe {
  grund: WechselGrund
  /** Nur bei Korrektur: erste falsche Stunde (örtlich, ISO ohne Zone). */
  falsch_seit?: string
  /** Nur bei «bleiben» zwischen zwei HA-Sensoren mit Überlappung: «Der neue Sensor zählt ab» (örtlich, ISO ohne Zone). */
  zaehlt_ab?: string
}

/** U2 Lauf b: was «Bisherige Werte bleiben» zwischen zwei HA-Sensoren tut (Backend `zuordnung_wechsel/bleiben.angaben`) —
 *  jede Zahl, Stunde und jeder Satz kommt vom Backend, der Client rechnet nichts. */
export interface BleibenAngaben {
  /** Warum eedc den Wechsel noch nicht wie Home Assistant rechnet (`null` = es rechnet ihn). */
  wartet: string | null
  /** Beginn der ersten Stundenzeile des neuen Sensors in Home Assistant. */
  seit: string | null
  ueberlappung: boolean | null
  /** Die Stunde, ab der der neue Sensor zählt. */
  zaehlt_ab: string | null
  /** Nur bei Überlappung: Vorgabe und zulässiger Bereich für «Der neue Sensor zählt ab». */
  zaehlt_ab_vorgabe: string | null
  zaehlt_ab_frueheste: string | null
  zaehlt_ab_spaeteste: string | null
  stunden: number | null
  tage: number | null
  monate: string[]
  saetze: string[]
}

/** U2 Lauf b: ein Wechsel «bleiben», den eedc noch nicht wie Home Assistant rechnet (`GET …/wartende-wechsel`). */
export interface WartenderWechsel {
  sensor_key: string
  label: string
  wartet: string
  satz: string
}

/** Vorschau des Korrektur-Dienstes (Sätze und Zahlen kommen aus dem Backend — der Client rechnet nichts). */
export interface KorrekturVorschau {
  saetze: string[]
  startbar: boolean
  zaehlerstaende?: number
  tage_neu?: string[]
}

/** Antwort der Prüf-Route je Zählerschlüssel (`…/quelle/pruefen`, `…/presets/apply/pruefen`). */
export interface QuellePruefung {
  grund_erforderlich: boolean
  erster_wert: string | null
  tage: number
  stand_alt: number | null
  stand_neu: number | null
  sensor_key: string | null
  label: string | null
  /** Die Änderung wird verzeichnet (eigene Werte, die wirksame Quelle wechselt). */
  verzeichnet: boolean
  vorgabe_falsch_seit: string | null
  korrektur: KorrekturVorschau | null
  /** U2 Lauf b: nur zwischen zwei HA-Sensoren — was «Bisherige Werte bleiben» tut. */
  bleiben?: BleibenAngaben | null
  /** U3 b: bei MQTT bzw. zwischen Home Assistant und MQTT der Satz zu «Bisherige Werte bleiben» (sonst der allgemeine). */
  bleiben_satz?: string | null
}

export interface KorrekturLaufStart {
  lauf: string
  sensor_key: string
  label: string
  tage_neu: number
  zaehlerstaende_geloescht: number
  /** `ansetzen` = der Lauf eines Wechsels «bleiben» (U2 Lauf b); fehlt bei einer Korrektur. */
  art?: LaufArt
}

/** Wer einen Lauf angelegt hat: eine Korrektur oder das Ansetzen eines Wechsels «bleiben» (U2 Lauf b). */
export type LaufArt = 'korrektur' | 'ansetzen'

/** Fortschritt eines Korrektur-Laufs (`GET …/korrektur-lauf/{lauf}`). */
export interface KorrekturLaufStand {
  lauf: string
  sensor_key: string | null
  status: 'laeuft' | 'fertig'
  tage: number
  erledigt: number
  fehler: { tag: string | null; grund: string }[]
  beginn: string | null
  ende: string | null
  fuellen_offen: boolean
  /** U2 Lauf b: `ansetzen` = der Nachlauf eines Wechsels «bleiben» (kein «Korrektur»-Text). */
  art?: LaufArt
}

/** Ein laufender Korrektur-Lauf der Anlage (`GET …/korrektur-laeufe`) — die Fläche zeigt beim Laden seinen Fortschritt. */
export interface KorrekturLaufLaufend {
  lauf: string
  sensor_key: string | null
  label: string
  beginn: string | null
}

/** «Grund nachtragen» an einem verzeichneten Wechsel (`…/zuordnung-wechsel/{id}/grund/pruefen`, Sitzung 4): dieselben
 *  Angaben wie die Prüf-Route der Quelle, dazu der Wechsel als Satz und die zulässigen Gründe. */
export interface GrundNachtragPruefung extends QuellePruefung {
  /** `null` am versetzten Abschnitt (Befund `zaehler_versatz`, Sitzung 4b-1 — dort gibt es keine Wechsel-Zeile). */
  wechsel_id: number | null
  feld_id: string | null
  grund: WechselGrund | null
  wechsel_satz: string
  gruende: WechselGrund[]
  korrektur_nicht: string | null
  /** Korrektur über ein festes Stück (Befund `zaehler_versatz` bzw. A → X → A an einem früheren Wechsel): «Falsch seit»
   *  steht fest (Sprung), die Korrektur endet am Rückgang. */
  stueck?: { sprung: string; rueckgang: string } | null
}

/** Das Stück des Befunds `zaehler_versatz` (aus `stueck=<schlüssel>~<sprung>~<rückgang>`). */
export interface StueckAngabe {
  sensor_key: string
  sprung: string
  rueckgang: string
}

/** Antwort nach dem Eintragen: `korrektur` = die gestarteten Läufe (Fortschritt an der Fläche). */
export type GrundNachtragErgebnis = Omit<GrundNachtragPruefung, 'korrektur'> & {
  eingetragen: boolean
  korrektur: KorrekturLaufStart[]
  wartet?: WartenderWechsel[]
}

/** Einstieg «Zähler getauscht (gleiche Quelle)»: Weg je Quelle zur Stunde des Tauschs (Backend `zaehler_getauscht.py`). */
export interface ZaehlerGetauschtAntwort {
  weg: 'home_assistant' | 'fortsetzung' | 'ohne_werte' | 'keine_quelle' | 'vor_erstem_wert' | 'nicht_moeglich' | 'kein_sprung' | 'negative_menge'
  sensor_key: string | null
  saetze: string[]
  eintragen: boolean
  getauscht_am: string | null
  eingetragen?: boolean
}

/** Transform-Konfiguration für eine MQTT-Gateway-Quelle (§2b). */
export interface GatewayQuelleConfig {
  quell_topic: string
  payload_typ?: 'plain' | 'json' | 'json_array'
  json_pfad?: string | null
  array_index?: number | null
  faktor?: number
  offset?: number
}

// ─── B3: MQTT-Topic-Discovery (#-Scan) ───────────────────────────────

export interface DiscoveryTopic {
  topic: string
  payload_sample: string
  payload_typ: 'plain' | 'json' | 'json_array'
  wert: number | null
}

export interface DiscoveryResponse {
  topics: DiscoveryTopic[]
  anzahl: number
  /** true = max_topics erreicht (Ergebnis abgeschnitten). */
  begrenzt: boolean
  wartezeit_s: number
  fehler: string | null
}

/** Ein direktes Kind einer Baum-Ebene (serverseitig aggregiert). */
export interface LevelChild {
  segment: string
  has_children: boolean
  /** Gesetzt, wenn dieses Segment selbst ein Topic mit Payload ist. */
  leaf: DiscoveryTopic | null
}

export interface LevelResponse {
  praefix: string
  children: LevelChild[]
  /** Gesetzt, wenn der Pfad selbst ein Topic ist (Zweig+Wert). */
  self_leaf: DiscoveryTopic | null
  begrenzt: boolean
  gelesen: number
  fehler: string | null
}

/** Cross-Block-Signal: eine Verbindungs-Einstellung (MQTT-Broker oder HA-Verbindung)
 *  wurde gespeichert → die Datenquellen-Fläche lädt `verfuegbarkeit` neu, ohne F5.
 *  Idiom wie `useAnlagen`/`useSelectedAnlage` (window CustomEvent). */
export const VERBINDUNG_GEAENDERT_EVENT = 'eedc:verbindung-geaendert'

/**
 * Pfad einer Themen-Route mit dem Gerät als Query (`?investition_id=`): ohne `eintragId` das Thema, mit `''` die
 * Eintragsliste, sonst der Eintrag.
 */
function themaPfad(anlageId: number, investitionId: number, themaId: string, eintragId?: string): string {
  const basis = `/datenquellen/${anlageId}/themen/${encodeURIComponent(themaId)}`
  const pfad = eintragId == null ? basis : eintragId === '' ? `${basis}/eintraege` : `${basis}/eintraege/${encodeURIComponent(eintragId)}`
  return `${pfad}?investition_id=${investitionId}`
}

/** Der Body der Quellen-Route — derselbe für Prüfen und Senden (Vorschau = Lauf). */
function quelleBody(quelle: string, gateway?: GatewayQuelleConfig, entityId?: string, grund?: GrundAngabe) {
  return {
    quelle, ...(gateway ?? {}),
    ...(entityId ? { entity_id: entityId } : {}),
    ...(grund ? {
      grund: grund.grund, ...(grund.falsch_seit ? { falsch_seit: grund.falsch_seit } : {}),
      ...(grund.zaehlt_ab ? { zaehlt_ab: grund.zaehlt_ab } : {}),
    } : {}),
  }
}

export const datenquellenApi = {
  getFelder: (anlageId: number) =>
    api.get<DatenquellenResponse>(`/datenquellen/${anlageId}/felder`),

  /** Setzt die Quelle eines Feldes. Bei 'mqtt_gateway' Topic+Transform, bei
   *  ha_app/ha_connector die gewählte `entityId` mitgeben. Vorzeichen-Umkehr ist
   *  NICHT Teil der Quellen-Wahl — dafür `setInvert` (quellen-unabhängig). */
  setQuelle: (
    anlageId: number, fieldId: string, quelle: string,
    gateway?: GatewayQuelleConfig, entityId?: string, grund?: GrundAngabe,
  ) =>
    api.post<QuelleSaveResult>(
      `/datenquellen/${anlageId}/felder/${encodeURIComponent(fieldId)}/quelle`,
      quelleBody(quelle, gateway, entityId, grund),
    ),

  /** Sensorwechsel mit Grund: dieselbe Änderung prüfen, BEVOR sie gesendet wird (schreibt nichts). Mit `grund`
   *  `korrektur` und `falsch_seit` liefert das Backend die Vorschau des Korrektur-Laufs. */
  pruefeQuelle: (
    anlageId: number, fieldId: string, quelle: string,
    gateway?: GatewayQuelleConfig, entityId?: string, grund?: GrundAngabe,
  ) =>
    api.post<QuellePruefung>(
      `/datenquellen/${anlageId}/felder/${encodeURIComponent(fieldId)}/quelle/pruefen`,
      quelleBody(quelle, gateway, entityId, grund),
    ),

  /** Einstieg «Zähler getauscht (gleiche Quelle)»: erst prüfen (Weg und Sätze), dann eintragen. */
  pruefeZaehlerGetauscht: (anlageId: number, fieldId: string, getauschtAm?: string) =>
    api.post<ZaehlerGetauschtAntwort>(
      `/datenquellen/${anlageId}/felder/${encodeURIComponent(fieldId)}/zaehler-getauscht/pruefen`,
      getauschtAm ? { getauscht_am: getauschtAm } : {},
    ),
  zaehlerGetauscht: (anlageId: number, fieldId: string, getauschtAm?: string) =>
    api.post<ZaehlerGetauschtAntwort>(
      `/datenquellen/${anlageId}/felder/${encodeURIComponent(fieldId)}/zaehler-getauscht`,
      getauschtAm ? { getauscht_am: getauschtAm } : {},
    ),

  /** Fortschritt eines Korrektur-Laufs (Dialog und Werkbank). */
  korrekturLauf: (anlageId: number, lauf: string) =>
    api.get<KorrekturLaufStand>(`/datenquellen/${anlageId}/korrektur-lauf/${encodeURIComponent(lauf)}`),

  /** U2 Lauf b: die Wechsel «bleiben», die eedc noch nicht wie Home Assistant rechnet, je mit dem Grund (Fläche). */
  wartendeWechsel: (anlageId: number) =>
    api.get<WartenderWechsel[]>(`/datenquellen/${anlageId}/wartende-wechsel`),

  /** Die laufenden Korrektur-Läufe der Anlage (die Fläche zeigt sie beim Laden, auch nach dem Neuladen der Seite). */
  /** «Grund nachtragen»: prüfen (schreibt nichts; mit Grund «korrektur» und «falsch seit» die Vorschau des Diensts). */
  pruefeGrundNachtragen: (anlageId: number, wechselId: number, grund?: GrundAngabe) =>
    api.post<GrundNachtragPruefung>(`/datenquellen/${anlageId}/zuordnung-wechsel/${wechselId}/grund/pruefen`, grund ?? {}),

  /** «Grund nachtragen»: eintragen (Fortsetzung) bzw. die Korrektur ausführen. */
  grundNachtragen: (anlageId: number, wechselId: number, grund: GrundAngabe) =>
    api.post<GrundNachtragErgebnis>(`/datenquellen/${anlageId}/zuordnung-wechsel/${wechselId}/grund`, grund),

  /** «Grund nachtragen» am versetzten Abschnitt (Befund `zaehler_versatz`): prüfen — schreibt nichts; mit `grund:
   *  'korrektur'` die Vorschau der Korrektur über das Stück (Vorschau = Lauf). */
  pruefeStueck: (anlageId: number, stueck: StueckAngabe, grund?: WechselGrund) =>
    api.post<GrundNachtragPruefung>(`/datenquellen/${anlageId}/zaehler-versatz/pruefen`, { ...stueck, grund: grund ?? null }),

  /** «Grund nachtragen» am versetzten Abschnitt: die Korrektur über das Stück ausführen. */
  stueckKorrigieren: (anlageId: number, stueck: StueckAngabe, grund: WechselGrund = 'korrektur') =>
    api.post<GrundNachtragErgebnis>(`/datenquellen/${anlageId}/zaehler-versatz`, { ...stueck, grund }),

  korrekturLaeufe: (anlageId: number) =>
    api.get<KorrekturLaufLaufend[]>(`/datenquellen/${anlageId}/korrektur-laeufe`),

  /** Vorzeichen-Umkehr eines Feldes setzen — QUELLEN-UNABHÄNGIG (Wert-Eigenschaft,
   *  gilt für jede Quelle; am Read-Endwert angewendet). */
  setInvert: (anlageId: number, fieldId: string, invertieren: boolean) =>
    api.post<{ field_id: string; invertieren: boolean }>(
      `/datenquellen/${anlageId}/felder/${encodeURIComponent(fieldId)}/invert`,
      { invertieren },
    ),

  /** HA-Entities für den HA-Sensor-Picker (Supervisor ODER Remote-HA).
   *  feld/invTyp aktivieren die Wissensbasis-Vorschläge (#343 A). */
  haSensoren: (anlageId: number, feld?: string, invTyp?: string, alle?: boolean) => {
    const q = new URLSearchParams()
    if (feld) q.set('feld', feld)
    if (invTyp) q.set('inv_typ', invTyp)
    // Themen-Kacheln (4.2.0): jede Entität mit State, ohne Energie-Filter und ohne Wissensbasis-Vorschläge.
    if (alle) q.set('alle', 'true')
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return api.get<HaSensorenResponse>(`/datenquellen/${anlageId}/ha/sensoren${suffix}`)
  },

  /** D2: bestätigte Energy-Dashboard-Vorschläge (#197) in die Quellen übernehmen. */
  uebernehmeEnergyVorschlaege: (
    anlageId: number, basis: Record<string, string>, investitionen: Record<string, Record<string, string>>,
  ) =>
    api.post<{
      gespeichert: boolean; anzahl: number; felder: string[]
      /** Sensorwechsel mit Grund: Felder mit eigenen Werten, deren Quelle gewechselt hätte — nicht übernommen. */
      uebersprungen: { field_id: string; label: string }[]
    }>(
      `/datenquellen/${anlageId}/energy-vorschlaege/uebernehmen`, { basis, investitionen },
    ),

  /** On-Demand-Takt-Check eines kWh-Kandidaten im Pick-Moment (#343 B). */
  taktCheck: (anlageId: number, entityId: string) =>
    api.post<TaktCheckResponse>(`/datenquellen/${anlageId}/ha/takt-check`, { entity_id: entityId }),

  // ── Themen-Kacheln (4.2.0): Themen und Einträge je Gerät. Die Quelle eines Eintrags setzt `setQuelle(feld_id)`. ──
  // Kennungen `t<n>`/`e<n>` sind nur je Gerät eindeutig — jede Route an einem Thema nennt das Gerät (`?investition_id=`,
  // Pflicht im Backend; Nachlauf 4.2.0 H2).
  themaAnlegen: (anlageId: number, investitionId: number, name?: string) =>
    api.post<ThemenAntwort>(`/datenquellen/${anlageId}/themen`, { investition_id: investitionId, ...(name ? { name } : {}) }),
  themaAendern: (anlageId: number, investitionId: number, themaId: string, aenderung: { name?: string; position?: number }) =>
    api.patch<ThemenAntwort>(themaPfad(anlageId, investitionId, themaId), aenderung),
  themaEntfernen: (anlageId: number, investitionId: number, themaId: string) =>
    api.delete<ThemenAntwort>(themaPfad(anlageId, investitionId, themaId)),
  eintragAnlegen: (anlageId: number, investitionId: number, themaId: string, label?: string) =>
    api.post<ThemenAntwort>(themaPfad(anlageId, investitionId, themaId, ''), label ? { label } : {}),
  eintragAendern: (
    anlageId: number, investitionId: number, themaId: string, eintragId: string, aenderung: { label?: string; position?: number },
  ) =>
    api.patch<ThemenAntwort>(themaPfad(anlageId, investitionId, themaId, eintragId), aenderung),
  eintragEntfernen: (anlageId: number, investitionId: number, themaId: string, eintragId: string) =>
    api.delete<ThemenAntwort>(themaPfad(anlageId, investitionId, themaId, eintragId)),

  /**
   * `#`-Scan des Brokers (zeit-/mengenbegrenzt) für den Gateway-Quell-Picker.
   * `anlageId` schließt die EIGENEN Topic-Pfade dieser Anlage aus (kein Selbstbezug).
   */
  discovery: (praefix = '#', timeoutS = 4, maxTopics = 300, anlageId?: number) =>
    api.post<DiscoveryResponse>('/datenquellen/mqtt/discovery', {
      praefix, timeout_s: timeoutS, max_topics: maxTopics, anlage_id: anlageId ?? null,
    }),

  /**
   * Direkte Kinder einer Baum-Ebene (Durchhangeln) — serverseitig aggregiert,
   * vollständig (kein Topic-Cap). `praefix` = Pfad ('' = Root, 'shellies/em').
   */
  level: (praefix: string, anlageId?: number) =>
    api.post<LevelResponse>('/datenquellen/mqtt/level', {
      praefix, anlage_id: anlageId ?? null,
    }),
}
