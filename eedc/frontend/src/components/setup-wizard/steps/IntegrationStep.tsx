/**
 * IntegrationStep — umgebungsabhängiger Integrations-Schritt im Erst-Setup (D2).
 *
 * Spec: PLAN-IA-V4-RESTWEG.md §2 D2 (Gernot 2026-07-18) + KONZEPT-DATENQUELLEN-P2 §3.
 * Drei Zweige:
 *   • Add-on (Supervisor): Energy-Dashboard-Vorschläge (#197) mit BESTÄTIGTER
 *     Übernahme in die Datenquellen (nie stumm) + MQTT nur-Export optional.
 *   • Standalone + „externe HA-Instanz? → Ja": LL-Token (mit Kurzanleitung),
 *     danach Energy-Vorschläge über die Remote-API + MQTT nur-Export.
 *   • Standalone + „Nein": EIN Broker, Richtungen Export UND Import — explizit
 *     und sichtbar (ENV MQTT_ENABLED bleibt stiller Bestands-Default, §4).
 * Alles optional/überspringbar — der Schritt legt nichts ungefragt an.
 */
import { useCallback, useEffect, useState } from 'react'
import { Plug, ArrowLeft, ArrowRight, CheckCircle2, Lightbulb } from 'lucide-react'
import { Alert, Button, Checkbox, Input } from '../../ui'
import { useHAAvailable } from '../../../hooks/useHAAvailable'
import { sensorMappingApi, type HAEnergySuggestResponse } from '../../../api/sensorMapping'
import { datenquellenApi } from '../../../api/datenquellen'
import { haRemoteApi } from '../../../api/haRemote'
import { liveDashboardApi } from '../../../api/liveDashboard'
import { haApi } from '../../../api/ha'

interface IntegrationStepProps {
  anlageId: number | null
  onNext: () => void
  onBack: () => void
  onSkip: () => void
}

type StandaloneWahl = 'offen' | 'remote_ha' | 'nur_mqtt'

export default function IntegrationStep({ anlageId, onNext, onBack, onSkip }: IntegrationStepProps) {
  const haAvailable = useHAAvailable()
  const [wahl, setWahl] = useState<StandaloneWahl>('offen')

  // ── Remote-HA (Standalone-Ja) ────────────────────────────────────────────
  const [remoteUrl, setRemoteUrl] = useState('')
  const [remoteToken, setRemoteToken] = useState('')
  const [remoteStatus, setRemoteStatus] = useState<'offen' | 'testet' | 'ok' | 'fehler'>('offen')
  const [remoteFehler, setRemoteFehler] = useState<string | null>(null)

  const speichereRemote = useCallback(async () => {
    setRemoteStatus('testet')
    setRemoteFehler(null)
    try {
      const test = await haRemoteApi.test({ base_url: remoteUrl.trim(), token: remoteToken.trim() })
      if (!test.connected) {
        setRemoteStatus('fehler')
        setRemoteFehler(test.error ?? 'Verbindung fehlgeschlagen')
        return
      }
      await haRemoteApi.saveSettings({ enabled: true, base_url: remoteUrl.trim(), token: remoteToken.trim() })
      setRemoteStatus('ok')
    } catch (e) {
      setRemoteStatus('fehler')
      setRemoteFehler(e instanceof Error ? e.message : 'Verbindung fehlgeschlagen')
    }
  }, [remoteUrl, remoteToken])

  // ── Energy-Dashboard-Vorschläge (#197 — Add-on ODER Remote nach Token) ───
  const haVerbunden = haAvailable || remoteStatus === 'ok'
  const [vorschlaege, setVorschlaege] = useState<HAEnergySuggestResponse | null>(null)
  const [auswahl, setAuswahl] = useState<Record<string, boolean>>({})
  const [uebernommen, setUebernommen] = useState<number | null>(null)
  const [uebernehmeLaeuft, setUebernehmeLaeuft] = useState(false)

  useEffect(() => {
    if (!haVerbunden || anlageId == null) return
    sensorMappingApi.getHAEnergySuggestions(anlageId)
      .then((r) => {
        setVorschlaege(r)
        if (r.available) {
          const alle: Record<string, boolean> = {}
          for (const feld of Object.keys(r.basis)) alle[`basis:${feld}`] = true
          for (const [invId, felder] of Object.entries(r.investitionen)) {
            for (const feld of Object.keys(felder)) alle[`inv:${invId}:${feld}`] = true
          }
          setAuswahl(alle)
        }
      })
      .catch(() => setVorschlaege(null))
  }, [haVerbunden, anlageId])

  const uebernehmeVorschlaege = useCallback(async () => {
    if (!vorschlaege?.available || anlageId == null) return
    setUebernehmeLaeuft(true)
    try {
      const basis: Record<string, string> = {}
      for (const [feld, entity] of Object.entries(vorschlaege.basis)) {
        if (auswahl[`basis:${feld}`]) basis[feld] = entity
      }
      const investitionen: Record<string, Record<string, string>> = {}
      for (const [invId, felder] of Object.entries(vorschlaege.investitionen)) {
        for (const [feld, entity] of Object.entries(felder)) {
          if (auswahl[`inv:${invId}:${feld}`]) {
            investitionen[invId] = { ...(investitionen[invId] ?? {}), [feld]: entity }
          }
        }
      }
      const r = await datenquellenApi.uebernehmeEnergyVorschlaege(anlageId, basis, investitionen)
      setUebernommen(r.anzahl)
    } catch {
      setUebernommen(null)
    } finally {
      setUebernehmeLaeuft(false)
    }
  }, [vorschlaege, auswahl, anlageId])

  // ── MQTT (EIN Broker, Richtungen je Zweig) ───────────────────────────────
  const mitImport = !haAvailable && wahl === 'nur_mqtt'
  const [mqttAktiv, setMqttAktiv] = useState(false)
  const [broker, setBroker] = useState({ host: '', port: '1883', username: '', password: '' })
  const [mqttStatus, setMqttStatus] = useState<'offen' | 'speichert' | 'ok' | 'fehler'>('offen')
  const [mqttFehler, setMqttFehler] = useState<string | null>(null)

  const speichereMqtt = useCallback(async () => {
    setMqttStatus('speichert')
    setMqttFehler(null)
    try {
      // EIN Broker (P1-Konsolidierung): Export-Richtung zuerst (schneller
      // Settings-Write, B7-5b), dann Broker + Import-Richtung — der Save startet
      // ggf. den Subscriber und kann bei nicht erreichbarem Broker dauern.
      await haApi.setAutoPublish(true)
      await liveDashboardApi.saveMqttSettings({
        enabled: mitImport,
        host: broker.host.trim(),
        port: Number(broker.port) || 1883,
        username: broker.username.trim(),
        password: broker.password,
      })
      setMqttStatus('ok')
    } catch (e) {
      setMqttStatus('fehler')
      setMqttFehler(e instanceof Error ? e.message : 'Speichern fehlgeschlagen')
    }
  }, [broker, mitImport])

  const vorschlagZeilen = (() => {
    if (!vorschlaege?.available) return []
    const zeilen: { key: string; label: string; entity: string }[] = []
    for (const [feld, entity] of Object.entries(vorschlaege.basis)) {
      zeilen.push({ key: `basis:${feld}`, label: `Anlage · ${feld}`, entity })
    }
    for (const match of vorschlaege.investition_matches) {
      zeilen.push({
        key: `inv:${match.inv_id}:${match.feld}`,
        label: `${match.bezeichnung} · ${match.feld}`,
        entity: match.sensor_id,
      })
    }
    return zeilen
  })()

  return (
    <div className="p-4 sm:p-8">
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 bg-amber-100 dark:bg-amber-900/40 rounded-lg">
          <Plug className="w-6 h-6 text-amber-600 dark:text-amber-400" />
        </div>
        <h2 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white">Integration</h2>
      </div>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
        Optional: Datenquellen anbinden — alles hier lässt sich später unter
        Einstellungen → Datenquellen ändern.
      </p>

      {(
        <div className="space-y-6">
          {/* Standalone: Grundfrage externe HA-Instanz */}
          {!haAvailable && (
            <div>
              <p className="text-sm font-medium text-gray-800 dark:text-gray-200 mb-2">
                Nutzt du eine externe Home-Assistant-Instanz?
              </p>
              <div className="flex gap-2">
                <Button type="button" variant={wahl === 'remote_ha' ? 'primary' : 'secondary'} onClick={() => setWahl('remote_ha')}>
                  Ja, HA verbinden
                </Button>
                <Button type="button" variant={wahl === 'nur_mqtt' ? 'primary' : 'secondary'} onClick={() => setWahl('nur_mqtt')}>
                  Nein, nur MQTT
                </Button>
              </div>
            </div>
          )}

          {/* Remote-HA: LL-Token mit Kurzanleitung */}
          {!haAvailable && wahl === 'remote_ha' && (
            <div className="space-y-3 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <p className="text-sm font-medium text-gray-800 dark:text-gray-200">Home-Assistant-Verbindung</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Den langlebigen Zugriffstoken legst du in HA an unter: Profil → Sicherheit →
                „Langlebige Zugriffstoken" → Token erstellen.
              </p>
              <Input label="HA-Basis-URL" value={remoteUrl} onChange={(e) => setRemoteUrl(e.target.value)} placeholder="http://homeassistant.local:8123" />
              <Input label="Langlebiger Zugriffstoken" type="password" value={remoteToken} onChange={(e) => setRemoteToken(e.target.value)} />
              <div className="flex items-center gap-3">
                <Button type="button" variant="secondary" loading={remoteStatus === 'testet'} disabled={!remoteUrl.trim() || !remoteToken.trim()} onClick={speichereRemote}>
                  Verbinden & testen
                </Button>
                {remoteStatus === 'ok' && (
                  <span className="flex items-center gap-1 text-sm text-green-600 dark:text-green-400">
                    <CheckCircle2 className="w-4 h-4" /> verbunden
                  </span>
                )}
              </div>
              {remoteStatus === 'fehler' && <Alert type="error">{remoteFehler}</Alert>}
            </div>
          )}

          {/* Energy-Dashboard-Vorschläge (#197) — Add-on oder verbundene Remote-HA */}
          {haVerbunden && (
            <div className="space-y-3 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <p className="flex items-center gap-1.5 text-sm font-medium text-gray-800 dark:text-gray-200">
                <Lightbulb className="w-4 h-4 text-amber-500" /> Sensor-Vorschläge aus deinem HA-Energy-Dashboard
              </p>
              {vorschlaege == null && <p className="text-xs text-gray-500 dark:text-gray-400">Vorschläge werden geladen …</p>}
              {vorschlaege != null && !vorschlaege.available && (
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Keine Energy-Dashboard-Konfiguration gefunden — Sensoren später unter
                  Einstellungen → Datenquellen zuordnen.
                </p>
              )}
              {vorschlaege?.available && uebernommen == null && (
                <>
                  <div className="space-y-1">
                    {vorschlagZeilen.map((z) => (
                      <Checkbox
                        key={z.key}
                        id={`energie-vorschlag-${z.key}`}
                        checked={auswahl[z.key] ?? false}
                        onChange={(e) => setAuswahl((prev) => ({ ...prev, [z.key]: e.target.checked }))}
                        label={<span className="min-w-0">{z.label} <span className="font-mono text-xs text-gray-500 dark:text-gray-400">→ {z.entity}</span></span>}
                      />
                    ))}
                  </div>
                  <Button type="button" variant="secondary" loading={uebernehmeLaeuft}
                    disabled={!Object.values(auswahl).some(Boolean)} onClick={uebernehmeVorschlaege}>
                    Ausgewählte übernehmen
                  </Button>
                </>
              )}
              {uebernommen != null && (
                <p className="flex items-center gap-1 text-sm text-green-600 dark:text-green-400">
                  <CheckCircle2 className="w-4 h-4" /> {uebernommen} Zuordnung(en) übernommen.
                </p>
              )}
            </div>
          )}

          {/* MQTT — Export immer, Import nur im Nur-MQTT-Zweig */}
          {(haAvailable || wahl !== 'offen') && (
            <div className="space-y-3 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <Checkbox
                id="setup-mqtt-aktiv"
                checked={mqttAktiv}
                onChange={(e) => setMqttAktiv(e.target.checked)}
                label={mitImport ? 'MQTT einrichten (Empfangen + Export)' : 'MQTT-Export einrichten (optional)'}
              />
              {mqttAktiv && (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <Input label="Broker-Host" value={broker.host} onChange={(e) => setBroker((b) => ({ ...b, host: e.target.value }))} placeholder="z.B. 192.168.1.10" />
                    <Input label="Port" value={broker.port} onChange={(e) => setBroker((b) => ({ ...b, port: e.target.value }))} />
                    <Input label="Benutzer (optional)" value={broker.username} onChange={(e) => setBroker((b) => ({ ...b, username: e.target.value }))} />
                    <Input label="Passwort (optional)" type="password" value={broker.password} onChange={(e) => setBroker((b) => ({ ...b, password: e.target.value }))} />
                  </div>
                  <div className="flex items-center gap-3">
                    <Button type="button" variant="secondary" loading={mqttStatus === 'speichert'} disabled={!broker.host.trim()} onClick={speichereMqtt}>
                      Speichern
                    </Button>
                    {mqttStatus === 'ok' && (
                      <span className="flex items-center gap-1 text-sm text-green-600 dark:text-green-400">
                        <CheckCircle2 className="w-4 h-4" /> gespeichert
                      </span>
                    )}
                  </div>
                  {mqttStatus === 'fehler' && <Alert type="error">{mqttFehler}</Alert>}
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Navigation — Abbrechen-Kanon: sekundär/links Zurück, rechts Weiter. */}
      <div className="mt-8 flex items-center justify-between">
        <Button type="button" variant="ghost" onClick={onBack}>
          <ArrowLeft className="w-4 h-4 mr-2" /> Zurück
        </Button>
        <div className="flex gap-2">
          <Button type="button" variant="ghost" onClick={onSkip}>Überspringen</Button>
          <Button type="button" onClick={onNext}>
            Weiter <ArrowRight className="w-4 h-4 ml-2" />
          </Button>
        </div>
      </div>
    </div>
  )
}
