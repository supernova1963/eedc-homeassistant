/**
 * useGlobalStatus — installations-/anlage-weite Status-Quellen der Fusszeile (G11, P2).
 *
 * SPEC: `docs/drafts/SPEC-STATUS-FUSSZEILE.md` §5/§7. Holt die Global-Zone-Daten
 * **einmal auf Shell-Ebene** (nicht pro Sicht) aus bestehenden IST-Endpoints —
 * kein Backend-Neubau:
 *   - **Versions-Update**: `systemApi.checkUpdate()` (GitHub-Releases) — faltet das
 *     Produktiv-Banner (`components/layout/Layout.tsx`) in ein Symbol ein.
 *   - **Offener Monatsabschluss**: `monatsabschlussApi.getNaechsterMonat()` —
 *     dieselbe Quelle wie die Produktiv-`TopNavigation`-Badge.
 *   - **MQTT-Inbound**: `liveDashboardApi.getMqttStatus()` (global gepollt, nicht
 *     mehr Live-gebunden wie in P1).
 *
 * Paket Q (Doppel-Fetch-Bereinigung): das „einmal auf Shell-Ebene" wird jetzt
 * technisch ERZWUNGEN — `GlobalStatusProvider` (in `LayoutV4`) hält die EINE
 * fetchende Instanz, `useGlobalStatus()` liest den Context. Vorher fetchte
 * jede Hook-Instanz selbst (Fusszeile + useEinstellungenStatus = alle 5
 * Endpunkte ×2 + doppeltes MQTT-Polling auf einstellungen/*). Ohne Provider
 * (Tests, exotische Mounts) fällt der Hook aufs lokale Fetching zurück.
 */
import { createContext, useContext, useState, useEffect } from 'react'
import { systemApi, type UpdateCheckResponse } from '../../api/system'
import { monatsabschlussApi, type NaechsterMonat } from '../../api/monatsabschluss'
import { liveDashboardApi, type MqttInboundStatus } from '../../api/liveDashboard'
import { datenCheckerApi, type DatenCheckResponse, type CheckErgebnis } from '../../api/datenChecker'
import { anlagenApi } from '../../api/anlagen'
import { useSelectedAnlage } from '../../hooks'

const MQTT_POLL_MS = 30_000

type DatenCheckSumme = DatenCheckResponse['zusammenfassung']

export interface GlobalStatus {
  update: UpdateCheckResponse | null
  offenerMonat: NaechsterMonat | null
  mqtt: MqttInboundStatus | null
  datencheck: DatenCheckSumme | null
  /**
   * Voll-Befunde des Daten-Checks (pro Kategorie) — additiv aus DERSELBEN
   * `check()`-Antwort wie {@link datencheck}. Nutzt u. a. `useEinstellungenStatus`
   * für Einträge, die eine Kategorie-Schwere brauchen (Strompreise/Sensor-Mapping).
   */
  datencheckErgebnisse: CheckErgebnis[] | null
  /**
   * Community-Teilen-Status der gewählten Anlage (Gernot 2026-07-03):
   * true = geteilt (`community_hash` gesetzt) · false = nicht geteilt ·
   * null = unbekannt (keine Anlage / lädt / Fehler). Frisch je Anlage geholt
   * (wie CommunityV4) — der Selektor-Kontext kann nach dem Teilen stale sein.
   */
  communityGeteilt: boolean | null
  anlageId: number | undefined
}

/** Context der EINEN fetchenden Instanz (Provider: `GlobalStatusProvider` in LayoutV4). */
export const GlobalStatusContext = createContext<GlobalStatus | null>(null)

/**
 * Interner Fetch-Kern — läuft nur bei `enabled` (Provider bzw. Provider-loser
 * Fallback). Bei enabled=false bleiben alle States null und werden nie gelesen.
 */
function useGlobalStatusFetch(enabled: boolean): GlobalStatus {
  const { selectedAnlage } = useSelectedAnlage()
  const anlageId = selectedAnlage?.id
  const [update, setUpdate] = useState<UpdateCheckResponse | null>(null)
  const [offenerMonat, setOffenerMonat] = useState<NaechsterMonat | null>(null)
  const [mqtt, setMqtt] = useState<MqttInboundStatus | null>(null)
  const [datencheck, setDatencheck] = useState<DatenCheckSumme | null>(null)
  const [datencheckErgebnisse, setDatencheckErgebnisse] = useState<CheckErgebnis[] | null>(null)
  const [communityGeteilt, setCommunityGeteilt] = useState<boolean | null>(null)

  // Update-Check einmal (wie Produktiv-Layout; ändert sich selten).
  useEffect(() => {
    if (!enabled) return
    systemApi.checkUpdate().then(setUpdate).catch(() => {})
  }, [enabled])

  // Offener Monatsabschluss + Daten-Checker-Zusammenfassung je gewählter Anlage.
  useEffect(() => {
    if (!enabled) return
    if (!anlageId) { setOffenerMonat(null); setDatencheck(null); setDatencheckErgebnisse(null); setCommunityGeteilt(null); return }
    monatsabschlussApi.getNaechsterMonat(anlageId).then(setOffenerMonat).catch(() => {})
    // Community-Teilen-Status frisch je Anlage (community_hash), Fehler = unbekannt.
    setCommunityGeteilt(null)
    anlagenApi.get(anlageId).then((a) => setCommunityGeteilt(!!a.community_hash)).catch(() => {})
    // Voll-Check (wie die Daten-Checker-Seite) — einmal je Anlage: Aggregat + Befunde.
    datenCheckerApi.check(anlageId)
      .then((r) => { setDatencheck(r.zusammenfassung); setDatencheckErgebnisse(r.ergebnisse) })
      .catch(() => {})
  }, [anlageId, enabled])

  // MQTT-Inbound global gepollt; bei inaktivem Subscriber blendet die Fusszeile aus.
  useEffect(() => {
    if (!enabled) return
    let aktiv = true
    const laden = () => liveDashboardApi.getMqttStatus().then((s) => { if (aktiv) setMqtt(s) }).catch(() => {})
    laden()
    const iv = setInterval(laden, MQTT_POLL_MS)
    return () => { aktiv = false; clearInterval(iv) }
  }, [enabled])

  return { update, offenerMonat, mqtt, datencheck, datencheckErgebnisse, communityGeteilt, anlageId }
}

/** NUR für den Provider: die eine fetchende Instanz. */
export function useGlobalStatusQuelle(): GlobalStatus {
  return useGlobalStatusFetch(true)
}

/**
 * Öffentliche API (Signatur unverändert): liest die Provider-Instanz; ohne
 * Provider (Tests, Mounts außerhalb der V4-Shell) fetcht lokal wie zuvor.
 * `ctx` ist pro Mount-Position konstant → `enabled` flackert nicht.
 */
export function useGlobalStatus(): GlobalStatus {
  const ctx = useContext(GlobalStatusContext)
  const lokal = useGlobalStatusFetch(ctx === null)
  return ctx ?? lokal
}
