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
 */
import { useState, useEffect } from 'react'
import { systemApi, type UpdateCheckResponse } from '../../api/system'
import { monatsabschlussApi, type NaechsterMonat } from '../../api/monatsabschluss'
import { liveDashboardApi, type MqttInboundStatus } from '../../api/liveDashboard'
import { datenCheckerApi, type DatenCheckResponse } from '../../api/datenChecker'
import { useSelectedAnlage } from '../../hooks'

const MQTT_POLL_MS = 30_000

type DatenCheckSumme = DatenCheckResponse['zusammenfassung']

export interface GlobalStatus {
  update: UpdateCheckResponse | null
  offenerMonat: NaechsterMonat | null
  mqtt: MqttInboundStatus | null
  datencheck: DatenCheckSumme | null
  anlageId: number | undefined
}

export function useGlobalStatus(): GlobalStatus {
  const { selectedAnlage } = useSelectedAnlage()
  const anlageId = selectedAnlage?.id
  const [update, setUpdate] = useState<UpdateCheckResponse | null>(null)
  const [offenerMonat, setOffenerMonat] = useState<NaechsterMonat | null>(null)
  const [mqtt, setMqtt] = useState<MqttInboundStatus | null>(null)
  const [datencheck, setDatencheck] = useState<DatenCheckSumme | null>(null)

  // Update-Check einmal (wie Produktiv-Layout; ändert sich selten).
  useEffect(() => {
    systemApi.checkUpdate().then(setUpdate).catch(() => {})
  }, [])

  // Offener Monatsabschluss + Daten-Checker-Zusammenfassung je gewählter Anlage.
  useEffect(() => {
    if (!anlageId) { setOffenerMonat(null); setDatencheck(null); return }
    monatsabschlussApi.getNaechsterMonat(anlageId).then(setOffenerMonat).catch(() => {})
    // Voll-Check (wie die Daten-Checker-Seite) — einmal je Anlage, nur fürs Aggregat.
    datenCheckerApi.check(anlageId).then((r) => setDatencheck(r.zusammenfassung)).catch(() => {})
  }, [anlageId])

  // MQTT-Inbound global gepollt; bei inaktivem Subscriber blendet die Fusszeile aus.
  useEffect(() => {
    let aktiv = true
    const laden = () => liveDashboardApi.getMqttStatus().then((s) => { if (aktiv) setMqtt(s) }).catch(() => {})
    laden()
    const iv = setInterval(laden, MQTT_POLL_MS)
    return () => { aktiv = false; clearInterval(iv) }
  }, [])

  return { update, offenerMonat, mqtt, datencheck, anlageId }
}
