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
  sensor_mapping_lts: 'Sensor-Mapping – HA-Statistics',
  sensor_mapping_einheit: 'Sensor-Mapping – Einheiten (Leistung/Energie)',
  provenance_conflict: 'Daten-Quellen – Konflikte',
  datenquelle_status: 'Datenquelle – aktiver Pfad',
  datenquelle_drift: 'Datenquelle – Drift zu HA-Statistics',
  zeitzone_abweichung: 'Zeitzone – Abweichung zu Home Assistant',
  batterie_vorzeichen_historie: 'Batterie – Vorzeichen-Historie',
  soc_nur_ein_speicher: 'Speicher – Ladestand nur eines Geräts',
  klima_modus_sensor: 'Klimaanlage – Betriebsmodus',
  pv_ueber_erfassung: 'PV – Doppelerfassungs-Verdacht',
  // N-588 (F5): Anlagenzähler gegen String-Zähler — ob eedc die Wandlungsverluste bewerten darf, und warum nicht.
  messpunkt: 'PV – Messpunkt (Anlagenzähler und Strings)',
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
  'provenance_conflict',
  'datenquelle_status',
  'datenquelle_drift',
  'zeitzone_abweichung',
  'batterie_vorzeichen_historie',
  'soc_nur_ein_speicher',
  'klima_modus_sensor',
  'pv_ueber_erfassung',
  'messpunkt',
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
