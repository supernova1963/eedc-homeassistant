/**
 * Datenquellen-Zuordnung API (Datenquellen-V4 / B2+B3).
 *
 * Feld-zentrische Fläche: je Anlage die gruppierte eedc-Feldliste (Basis + je
 * Investition, Live + Energie) mit Standard-Inbound-Topic. B3 ergänzt den
 * `#`-Discovery-Scan und die MQTT-Gateway-Quelle (Topic + Transform).
 */
import { api } from './client'

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
  /** Aktueller Wert aus dem MQTT-Inbound-Cache (null = nichts empfangen). */
  wert: number | null
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
}

/** Diagnostisches Zuordnungs-Problem (§2i) — rein informativ, keine Sperre. */
export interface FeldProblem {
  art: 'einheit' | 'state_class' | 'redundant' | 'doppelmapping' | 'takt'
  schwere: 'error' | 'warning'
  text: string
  /** nur art==='redundant': die wirksamen Komponenten-Felder. */
  wirksame_felder?: string[]
  /** nur art==='doppelmapping'. */
  entity_id?: string
  andere_felder?: string[]
}

export interface DatenquelleGruppe {
  id: string
  titel: string
  typ: string
  felder: DatenquelleFeld[]
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

export const datenquellenApi = {
  getFelder: (anlageId: number) =>
    api.get<DatenquellenResponse>(`/datenquellen/${anlageId}/felder`),

  /** Setzt die Quelle eines Feldes. Bei 'mqtt_gateway' Topic+Transform, bei
   *  ha_app/ha_connector die gewählte `entityId` mitgeben. Vorzeichen-Umkehr ist
   *  NICHT Teil der Quellen-Wahl — dafür `setInvert` (quellen-unabhängig). */
  setQuelle: (
    anlageId: number, fieldId: string, quelle: string,
    gateway?: GatewayQuelleConfig, entityId?: string,
  ) =>
    api.post<QuelleSaveResult>(
      `/datenquellen/${anlageId}/felder/${encodeURIComponent(fieldId)}/quelle`,
      {
        quelle, ...(gateway ?? {}),
        ...(entityId ? { entity_id: entityId } : {}),
      },
    ),

  /** Vorzeichen-Umkehr eines Feldes setzen — QUELLEN-UNABHÄNGIG (Wert-Eigenschaft,
   *  gilt für jede Quelle; am Read-Endwert angewendet). */
  setInvert: (anlageId: number, fieldId: string, invertieren: boolean) =>
    api.post<{ field_id: string; invertieren: boolean }>(
      `/datenquellen/${anlageId}/felder/${encodeURIComponent(fieldId)}/invert`,
      { invertieren },
    ),

  /** HA-Entities für den HA-Sensor-Picker (Supervisor ODER Remote-HA).
   *  feld/invTyp aktivieren die Wissensbasis-Vorschläge (#343 A). */
  haSensoren: (anlageId: number, feld?: string, invTyp?: string) => {
    const q = new URLSearchParams()
    if (feld) q.set('feld', feld)
    if (invTyp) q.set('inv_typ', invTyp)
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return api.get<HaSensorenResponse>(`/datenquellen/${anlageId}/ha/sensoren${suffix}`)
  },

  /** D2: bestätigte Energy-Dashboard-Vorschläge (#197) in die Quellen übernehmen. */
  uebernehmeEnergyVorschlaege: (
    anlageId: number, basis: Record<string, string>, investitionen: Record<string, Record<string, string>>,
  ) =>
    api.post<{ gespeichert: boolean; anzahl: number; felder: string[] }>(
      `/datenquellen/${anlageId}/energy-vorschlaege/uebernehmen`, { basis, investitionen },
    ),

  /** On-Demand-Takt-Check eines kWh-Kandidaten im Pick-Moment (#343 B). */
  taktCheck: (anlageId: number, entityId: string) =>
    api.post<TaktCheckResponse>(`/datenquellen/${anlageId}/ha/takt-check`, { entity_id: entityId }),

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
