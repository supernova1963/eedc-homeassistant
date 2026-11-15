/**
 * Daten-Checker API Client
 *
 * Endpoint für Datenqualitäts-Prüfung.
 */

import { api } from './client'

export interface CheckErgebnis {
  kategorie: string
  schwere: 'error' | 'warning' | 'info' | 'ok'
  meldung: string
  details?: string
  // IA-V4 #243: Komponenten-Zuordnung (nur komponenten-bezogene Befunde) —
  // erlaubt dem Komponenten-Hub, Befunde je Gerät zu filtern.
  investition_id?: number
  // E1 «Diagnose-Paket»: die Zahlen der Meldung strukturiert und der Befund-Schlüssel (an den Melder-Erzeugern).
  werte?: Record<string, unknown> | null
  code?: string | null
  // E2/E3: der eine Handgriff — Sprung-Ziel (Pfad über `lib/zielPfad.ts`) oder Aktion (Plan/Ausführen). Seit E5 ohne
  // die Altfelder `link`/`action_*` (Wächter W-3).
  ziel?: CheckZiel | null
  action?: CheckAktion | null
  /** E5.7 L1: der Knopf-Text aller drei Klassen aus dem Katalog (Aktion · Sprung · «Was gilt»); OK ⇒ null. */
  knopf?: string | null
  /** E5 V2: Gruppenzeile — Befunde mit gleichem `schluessel` stehen als eine Zeile mit Gliedern. */
  gruppe?: CheckGruppe | null
}

/** Gruppenzeile eines Befunds (Backend `services/daten_checker/gruppen.py`). */
export interface CheckGruppe {
  schluessel: string
  titel: string
  glied: string
  weitere: number
  details?: string | null
}

/** E5 V4: eine Prüfung, die in dieser Installation nicht laufen kann (kein Home Assistant, MQTT-Import aus). */
export interface NichtAusfuehrbar {
  pruefung: string
  grund: string
}

/** Sprung-Ziel eines Befunds (Bereich der Einstellungen, Block, Deep-Link-Parameter, Anker). */
export interface CheckZiel {
  bereich: string
  block?: string | null
  params: Record<string, unknown>
  anker?: string | null
}

/** Inline-Handgriff eines Befunds (Operation, Parameter, Knopf-Beschriftung). */
export interface CheckAktion {
  operation: 'reaggregate_day' | 'reaggregate_range' | 'kraftstoffpreis_backfill' | 'wetter_backfill'
    | 'feldwert_entfernen' | 'temperatur_aus_messung' | 'spiegel_abgleich_tag' | string
  params: Record<string, unknown>
  label: string
}

export interface MonatsdatenAbdeckung {
  vorhanden: number
  erwartet: number
  prozent: number
}

export interface DatenCheckResponse {
  anlage_id: number
  anlage_name: string
  ergebnisse: CheckErgebnis[]
  zusammenfassung: {
    error: number
    warning: number
    info: number
    ok: number
  }
  monatsdaten_abdeckung?: MonatsdatenAbdeckung
  nicht_ausfuehrbar?: NichtAusfuehrbar[]
}

/** Diagnose-Paket v4: Zähler der Inhaltsliste (Zeilen je Gruppe, Bauplan §3.4) — der Dialog zeigt sie, rechnet nichts. */
export interface DiagnosePaketInhalt {
  geraete: number
  tarife: number
  zuordnungen: number
  monatswerte: number
  tageswerte: number
  stundenwerte: number
  notizen: number
  protokollzeilen: number
  protokollzeilen_ohne_anlage: number
  befunde: number
}

/** Antwort von `…/bereitstellen`: das Paket liegt fertig bereit und lässt sich mit `marke` herunterladen (gültig `gueltig_s`). */
export interface DiagnosePaketBereit {
  marke: string
  dateiname: string
  bytes: number
  megabyte: number
  gueltig_s: number
  versandweg: 'email' | 'freigabe_link'
  inhalt: DiagnosePaketInhalt
  teilfehler: string[]
}

/** Adresse der bereitgestellten Datei (relativ wie `api/client.ts`, damit Ingress greift). */
export function diagnosePaketUrl(anlageId: number, marke: string): string {
  return `./api/system/diagnose-paket/${anlageId}?marke=${encodeURIComponent(marke)}`
}

/** Prüfabruf vor dem Herunterladen im HA-Rahmen: `true` bei 204 (Marke gültig), `false` bei 404 (abgelaufen, ersetzt, Neustart). */
export async function diagnosePaketPruefen(anlageId: number, marke: string): Promise<boolean> {
  const res = await fetch(`${diagnosePaketUrl(anlageId, marke)}&pruefen=1`)
  if (res.status === 204) return true
  if (res.status === 404) return false
  throw new Error(`HTTP ${res.status}`)
}

export const datenCheckerApi = {
  async check(anlageId: number): Promise<DatenCheckResponse> {
    return api.get<DatenCheckResponse>(`/system/daten-check/${anlageId}`)
  },

  /** Diagnose-Paket v4 bereitstellen (synchron, Variante A): baut die ZIP-Datei und antwortet mit Marke und Inhaltsliste. */
  async diagnosePaketBereitstellen(anlageId: number): Promise<DiagnosePaketBereit> {
    return api.get<DiagnosePaketBereit>(`/system/diagnose-paket/${anlageId}/bereitstellen`)
  },
}
