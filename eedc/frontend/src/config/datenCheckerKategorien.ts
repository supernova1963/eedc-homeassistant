/**
 * Daten-Checker — Kategorie-Labels, Reihenfolge & Severity-Konfiguration (SoT).
 *
 * Single Source of Truth für die Anzeige von Check-Befunden. Genutzt von der
 * IST-Seite `pages/DatenChecker.tsx` und vom IA-V4-Komponenten-Hub
 * (`v4/KomponentenTypV4.tsx`). Severity-Farben sind Tailwind-Text-Klassen
 * (Status-Achse) — bewusst keine Hex-Werte (Regel 0a, check:design).
 */

import { XCircle, AlertTriangle, Info, CheckCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export type CheckSchwere = 'error' | 'warning' | 'info' | 'ok'

export interface SeverityConfig {
  icon: LucideIcon
  /** Tailwind-Text-Klasse (Status-Achse). */
  colorClass: string
}

/** Severity → Icon + Farbe. Eine Datenrolle = eine Farbe (Regel 0a). */
export const SEVERITY_CONFIG: Record<CheckSchwere, SeverityConfig> = {
  error: { icon: XCircle, colorClass: 'text-red-500' },
  warning: { icon: AlertTriangle, colorClass: 'text-amber-500' },
  info: { icon: Info, colorClass: 'text-blue-500' },
  ok: { icon: CheckCircle, colorClass: 'text-green-500' },
}

/** Sprechende Labels je Backend-Kategorie (CheckKategorie-Enum). */
export const KATEGORIE_LABELS: Record<string, string> = {
  stammdaten: 'Stammdaten',
  strompreise: 'Strompreise',
  investitionen: 'Investitionen',
  monatsdaten_vollstaendigkeit: 'Monatsdaten – Vollständigkeit',
  monatsdaten_plausibilitaet: 'Monatsdaten – Plausibilität',
  geraetewerte_ohne_monatszeile: 'Monatsdaten – Messwerte ohne Monatszeile',
  energieprofil_abdeckung: 'Energieprofil – Zähler-Abdeckung',
  tageswerte_fehlen: 'Energieprofil – fehlende Tageswerte',
  energieprofil_plausibilitaet: 'Energieprofil – Plausibilität',
  mqtt_topic_abdeckung: 'MQTT – Topic-Abdeckung',
  // N-341: Zähler, die zwischendurch auf null zurückspringen („…heute"-Felder).
  // Label nennt die Sache aus Sicht des Anwenders — er sieht ein leeres Feld,
  // nicht eine verletzte Monotonie.
  zaehler_ruecksprung: 'Zählerstände – Rücksprung',
  // N-586 (HA-Bauform E4a-2): Phantomsprung in der HA-Statistik — eedc zeigt ihn wie HA und nennt den Reparaturweg.
  ha_zaehlersprung: 'Zählerstände – Sprung in Home Assistant',
  // N-639: HAs Summe fällt (Anpassung nach unten) — eedc zeigt die negative Menge wie HA und nennt den Weg.
  ha_zaehler_rueckgang: 'Zählerstände – Rückgang in Home Assistant',
  sensor_mapping_lts: 'Datenquellen – HA-Statistics',
  sensor_mapping_einheit: 'Datenquellen – Einheiten (Leistung/Energie)',
  // P-433-3 S1: Vorlauf/Rücklauf/Zusatzheizung ohne `state_class: measurement` — Live ja, Tagesverlauf nein.
  sensor_ohne_langzeitstatistik: 'Sensor ohne Langzeitstatistik',
  provenance_conflict: 'Daten-Quellen – Konflikte',
  datenquelle_status: 'Datenquelle – aktiver Pfad',
  datenquelle_drift: 'Datenquelle – Drift zu HA-Statistics',
  zeitzone_abweichung: 'Zeitzone – Abweichung zu Home Assistant',
  batterie_vorzeichen_historie: 'Batterie – Vorzeichen-Historie',
  soc_nur_ein_speicher: 'Speicher – Ladestand nur eines Geräts',
  klima_modus_sensor: 'Klimaanlage – Betriebsmodus',
  // P-433-0 (Konzept #433 E12 b): der zugeordnete Modus-Sensor liefert einen Wert, den eedc nicht kennt.
  klima_modus_wert: 'Betriebsmodus – unbekannter Wert',
  // P-433-2b K1 (E12-Muster): Ladezustand, Lademodus, Fahrzeug-Ladezustand oder Standort mit unbekanntem Wert.
  emob_zustand_wert: 'E-Mobilität – unbekannter Zustand',
  // P-433-2b K2a (K2-10): die Steuerung meldet ein Fahrzeug, dessen Kennung kein E-Auto trägt.
  emob_kennung_unbekannt: 'E-Mobilität – Fahrzeug der Steuerung unbekannt',
  // N-767/N-770/N-771: eigener WP-/Wallbox-Tarif — Netzbezug zum Komponenten-Tarif fehlt, geklemmt, evcc weicht ab,
  // paralleler Zähler (eine Kategorie für beide Komponenten: dieselbe Ursache, dasselbe Feld).
  wp_eigener_tarif: 'Strompreise – eigener WP-/Wallbox-Tarif',
  pv_ueber_erfassung: 'PV – Doppelerfassungs-Verdacht',
  // N-588 (F5): Anlagenzähler gegen String-Zähler — ob eedc die Wandlungsverluste bewerten darf, und warum nicht.
  messpunkt: 'PV – Messpunkt (Anlagenzähler und Strings)',
  // N-662: der Anlagenzähler „PV gesamt" steht still, während Einspeisung bzw. Strings wachsen.
  pv_zaehler_steht: 'PV – Zähler steht',
  emob_pool_pflege: 'E-Mobilität – Pool-Pflege',
  // F-21 (10.08.): beide fehlten hier UND in der Reihenfolge unten. Der
  // Doppelzählungs-Befund trägt einen Reparatur-Knopf („Zeitraum neu
  // aggregieren", der N-186-Pfad) und war damit unerreichbar.
  emob_doppelzaehlung_tage: 'E-Mobilität – doppelt gezählte Ladetage',
  phev_anteil_unbestimmt: 'E-Auto – elektrischer Anteil unbestimmt',
  position_wiederkehrend: 'Sonstige Positionen – wiederkehrend erfasst',
  position_doppelerfassung: 'Sonstige Positionen – doppelt erfasst',
  // #377/D3: Gas-, Wasser- und Ölzähler. Trägt drei Aussagen — Quelle,
  // Reihenbruch, Inaktiv-Falle. Label nennt das Gerät, nicht die Prüfung:
  // „Reihe" allein sagt dem Anwender nichts.
  zaehlerstand_reihe: 'Verbrauchszähler – Zählerstände',
  // #394 (gruaGit): Monatszeilen ohne Ø-Benzinpreis. Label nennt die Sache aus
  // Sicht des Anwenders — im Monatsabschluss heißt der Abschnitt
  // „Vergleichspreise", und genau dort sieht er das leere Feld.
  vergleichspreis_fehlt: 'Vergleichspreise – Ø Benzinpreis',
  // N-426-Nachtrag: die erste Wetterfeld-Kategorie. Label nennt die **Klasse**,
  // nicht das eine Feld — die Wetter-Route liefert drei Werte, und ein
  // „…Ø Temperatur" würde beim zweiten zur Falschaussage.
  wetterwert_fehlt: 'Wetterwerte – fehlende Monatswerte',
}

/** Anzeige-Reihenfolge der Kategorien (Vollständigkeit → Plausibilität → …). */
export const KATEGORIE_REIHENFOLGE: string[] = [
  'stammdaten',
  'strompreise',
  'wp_eigener_tarif',
  'investitionen',
  'monatsdaten_vollstaendigkeit',
  'monatsdaten_plausibilitaet',
  'geraetewerte_ohne_monatszeile',
  'energieprofil_abdeckung',
  'tageswerte_fehlen',
  'energieprofil_plausibilitaet',
  'mqtt_topic_abdeckung',
  'zaehler_ruecksprung',
  'ha_zaehlersprung',
  'ha_zaehler_rueckgang',
  'sensor_mapping_lts',
  'sensor_mapping_einheit',
  'sensor_ohne_langzeitstatistik',
  'provenance_conflict',
  'datenquelle_status',
  'datenquelle_drift',
  'zeitzone_abweichung',
  'batterie_vorzeichen_historie',
  'soc_nur_ein_speicher',
  'klima_modus_sensor',
  'klima_modus_wert',
  'emob_zustand_wert',
  'emob_kennung_unbekannt',
  'pv_ueber_erfassung',
  'messpunkt',
  'pv_zaehler_steht',
  'emob_pool_pflege',
  'emob_doppelzaehlung_tage',
  'phev_anteil_unbestimmt',
  // Konzept-Wirtschaftlichkeit §8.1. ⚠ Diese Liste ist **kein Sortier-Wunsch,
  // sondern ein Filter**: die Daten-Checker-Seite rendert `map` über sie, eine
  // fehlende Kategorie erscheint dort also gar nicht.
  'position_wiederkehrend',
  'position_doppelerfassung',
  'zaehlerstand_reihe',
  'vergleichspreis_fehlt',
  'wetterwert_fehlt',
]

/**
 * Lösungsweg-Anker je Kategorie (E3, Konzept §3.5): der Abschnitt der Kategorie in `HANDBUCH_DATEN_CHECKER.md` — der
 * Rückfall des Lösungsweg-Panels für einen Befund ohne Code (seit E5 öffnet es am Anker des Codes). Dieselben Anker trägt der
 * Katalog `backend/services/daten_checker/handgriffe.py` je Code; der Wächter
 * `backend/tests/test_daten_checker_texte.py` hält beide und das Handbuch gleich. Kategorien ohne eigenen
 * Abschnitt (E2 ⚑3) fallen auf das Kapitel 4 zurück.
 */
export const KATEGORIE_ANKER: Record<string, string> = {
  stammdaten: '41-stammdaten',
  strompreise: '42-strompreise',
  investitionen: '43-investitionen',
  monatsdaten_vollstaendigkeit: '44-monatsdaten--vollstaendigkeit',
  monatsdaten_plausibilitaet: '45-monatsdaten--plausibilitaet',
  geraetewerte_ohne_monatszeile: '44a-messwerte-ohne-monatszeile',
  energieprofil_abdeckung: '46-energieprofil--zaehler-abdeckung',
  mqtt_topic_abdeckung: '48-mqtt-topic-abdeckung',
  zaehler_ruecksprung: '48a-zaehlerstaende--ruecksprung',
  ha_zaehlersprung: '48b-zaehlerstaende--sprung-in-home-assistant',
  ha_zaehler_rueckgang: '48c-zaehlerstaende--rueckgang-in-home-assistant',
  sensor_mapping_lts: '49-sensor-mapping--ha-statistics',
  energieprofil_plausibilitaet: '47-energieprofil--plausibilitaet',
  provenance_conflict: '416-quellen-konflikte',
  datenquelle_status: '49a-datenquellen--status',
  datenquelle_drift: '417-datenquellen-drift',
  pv_ueber_erfassung: '418-pv-doppelerfassung',
  messpunkt: '48d-pv--messpunkt',
  pv_zaehler_steht: '48e-pv--zaehler-steht',
  emob_pool_pflege: '439-heimladung-je-auto',
  emob_doppelzaehlung_tage: '419-ladung-doppelt-gezaehlt',
  phev_anteil_unbestimmt: '420-phev-anteil',
  sensor_mapping_einheit: '415-sensor-zuordnung--leistung--energie',
  sensor_ohne_langzeitstatistik: '415a-sensor-ohne-langzeitstatistik',
  wetterwert_fehlt: '425-wetterwerte-fehlende-monatswerte',
  batterie_vorzeichen_historie: '421-batterie-vorzeichen-historie',
  soc_nur_ein_speicher: '422-ladestand-mehrere-speicher',
  tageswerte_fehlen: '410-energieprofil--fehlende-tageswerte',
  zeitzone_abweichung: '412-zeitzone--abweichung-zu-home-assistant',
  position_wiederkehrend: '413-sonstige-positionen--der-erfassungsort',
  position_doppelerfassung: '413-sonstige-positionen--der-erfassungsort',
  klima_modus_sensor: '414-klimaanlage--betriebsmodus',
  klima_modus_wert: '414a-betriebsmodus--unbekannter-wert',
  emob_zustand_wert: '426-e-mobilitaet--unbekannter-zustand',
  emob_kennung_unbekannt: '427-e-mobilitaet--fahrzeug-unbekannt',
  wp_eigener_tarif: '42a-eigener-waermepumpen-tarif',
  zaehlerstand_reihe: '423-verbrauchszaehler-zaehlerstaende',
  vergleichspreis_fehlt: '424-vergleichspreise-benzinpreis',
}

/** Der Anker des Lösungswegs eines Befunds (Code vor Kategorie, Rückfall Kapitel 4). */
export function loesungswegAnker(kategorie: string, code?: string | null): string {
  // E5: jeder Code hat seinen Abschnitt im Handbuch (`docs/daten-checker/<code>.md`, Anker = Code); ohne Code die Kategorie.
  return code || KATEGORIE_ANKER[kategorie] || '4-kategorien-im-detail'
}
