/**
 * HA-Remote-Verbindung API (Basis) — Datenquellen-V4 / B4a.
 *
 * Verbindungs-Baustein für eedc-Standalone → entfernte Home-Assistant-Installation
 * (Basis-URL + Long-Lived-Token). Dieses Modul deckt Einrichten + Testen ab;
 * die Nutzbarmachung (HA-Sensoren als Quelle) ist mit P3 gebaut (abgeschlossen
 * 2026-08-28) und sitzt backendseitig in `services/ha_connection.py`.
 */
import { api } from './client'

export interface HaRemoteSettings {
  enabled: boolean
  base_url: string
  /** Maskiert (`***`) wenn gesetzt. */
  token: string
  /** true = HA-App (Supervisor) → keine Remote-Verbindung nötig. */
  supervisor_verfuegbar: boolean
}

export interface HaRemoteTestResult {
  connected: boolean
  message?: string
  error?: string
}

/** Was beim Aktivieren mit dem MQTT-Import passiert ist (B7-5c). `null` = kein
 *  Übergang inaktiv→aktiv, also nicht angefasst. */
export interface MqttImportFolge {
  abgeschaltet: boolean
  grund?: 'gateway_in_benutzung' | 'import_war_schon_aus'
  gateway_mappings?: number
  connectoren?: number
}

export interface HaRemoteSaveResult {
  gespeichert: boolean
  base_url: string
  enabled: boolean
  mqtt_import?: MqttImportFolge | null
}

export const haRemoteApi = {
  getSettings: () => api.get<HaRemoteSettings>('/ha/remote/settings'),
  saveSettings: (config: { enabled: boolean; base_url: string; token: string }) =>
    api.post<HaRemoteSaveResult>('/ha/remote/settings', config),
  test: (config: { base_url: string; token: string }) =>
    api.post<HaRemoteTestResult>('/ha/remote/test', config),
}
