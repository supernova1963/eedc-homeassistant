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
  energieprofil_abdeckung: 'Energieprofil – Zähler-Abdeckung',
  energieprofil_plausibilitaet: 'Energieprofil – Plausibilität',
  mqtt_topic_abdeckung: 'MQTT – Topic-Abdeckung',
  sensor_mapping_lts: 'Sensor-Mapping – HA-Statistics',
  sensor_mapping_einheit: 'Sensor-Mapping – Einheiten (Leistung/Energie)',
  provenance_conflict: 'Daten-Quellen – Konflikte',
  datenquelle_status: 'Datenquelle – aktiver Pfad',
  datenquelle_drift: 'Datenquelle – Drift zu HA-Statistics',
  pv_ueber_erfassung: 'PV – Doppelerfassungs-Verdacht',
  emob_pool_pflege: 'E-Mobilität – Pool-Pflege',
}

/** Anzeige-Reihenfolge der Kategorien (Vollständigkeit → Plausibilität → …). */
export const KATEGORIE_REIHENFOLGE: string[] = [
  'stammdaten',
  'strompreise',
  'investitionen',
  'monatsdaten_vollstaendigkeit',
  'monatsdaten_plausibilitaet',
  'energieprofil_abdeckung',
  'energieprofil_plausibilitaet',
  'mqtt_topic_abdeckung',
  'sensor_mapping_lts',
  'sensor_mapping_einheit',
  'provenance_conflict',
  'datenquelle_status',
  'datenquelle_drift',
  'pv_ueber_erfassung',
  'emob_pool_pflege',
]
