/**
 * VerbindungStatusBadge — Status im Block-Kopf (BlockShell-`badge`), auch im
 * zugeklappten Zustand sichtbar.
 *
 * **Grundregel (Gernot 2026-07-16): jedes Badge beschreibt NUR seinen eigenen
 * Block.** Vorher trug der Broker-Block ein kombiniertes Richtungs-Badge
 * („aktiv · nur Import"), dessen Export-Anteil in einem ANDEREN Block geschaltet
 * wird — das las sich als Fähigkeits-Einschränkung („kann nur Import") statt als
 * Momentaufnahme, und man konnte im Block nicht sehen, woher die Aussage kommt.
 *
 *   `mqtt`        → MQTT-Broker-Verbindung: Verbindung + Import-Richtung
 *                   (beides wird in diesem Block gepflegt)
 *   `mqtt-export` → MQTT-Export: die Export-Richtung
 *   `ha`          → HA-Verbindung
 *
 * Aktualisiert sich ohne F5 über `VERBINDUNG_GEAENDERT_EVENT` (dispatcht von den
 * Verbindungs-Forms und vom Export-Toggle).
 */
import { useState, useEffect } from 'react'
import { liveDashboardApi } from '../../api/liveDashboard'
import { haRemoteApi } from '../../api/haRemote'
import { haApi } from '../../api/ha'
import { VERBINDUNG_GEAENDERT_EVENT } from '../../api/datenquellen'

type Kind = 'mqtt' | 'mqtt-export' | 'ha'
type Ton = 'gut' | 'warn' | 'aus'

interface Props {
  kind: Kind
}

const TON_KLASSE: Record<Ton, string> = {
  gut: 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300',
  warn: 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300',
  aus: 'bg-gray-50 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
}

export default function VerbindungStatusBadge({ kind }: Props) {
  const [label, setLabel] = useState<string | null>(null)
  const [ton, setTon] = useState<Ton>('aus')

  useEffect(() => {
    let lebt = true
    const setzen = (t: Ton, l: string) => { if (lebt) { setTon(t); setLabel(l) } }

    const ladeBroker = () =>
      Promise.all([
        liveDashboardApi.getMqttSettings(),           // .enabled = Import-Richtung
        liveDashboardApi.getMqttStatus().catch(() => null),
        haApi.getMqttConfig().catch(() => null),      // nur für „ist ein Broker hinterlegt?"
      ]).then(([settings, status, cfg]) => {
        // Kein Broker hinterlegt → der Block ist schlicht noch nicht eingerichtet.
        if (cfg && !cfg.broker_konfiguriert) return setzen('aus', 'nicht eingerichtet')
        if (!settings.enabled) return setzen('aus', 'Import aus')
        // Import gewollt, aber der Subscriber läuft nicht → das ist ein Problem,
        // kein Normalzustand (bewusst der Prozess-, nicht der Einstellungs-Zustand:
        // hier ist „läuft es wirklich?" die Frage, nicht „darf es?").
        if (status && !status.subscriber_aktiv) return setzen('warn', 'Import an · nicht verbunden')
        return setzen('gut', 'verbunden · Import an')
      })

    const ladeExport = () =>
      haApi.getMqttConfig().then((cfg) => {
        if (!cfg.auto_publish) return setzen('aus', 'Export aus')
        // Export an, aber kein Broker → die Sensoren erscheinen nie in HA.
        if (!cfg.broker_konfiguriert) return setzen('warn', 'Export an · kein Broker')
        return setzen('gut', 'Export an')
      })

    const ladeHa = () =>
      haRemoteApi.getSettings().then((s) => {
        if (s.supervisor_verfuegbar) return setzen('gut', 'aktiv · Supervisor')
        if (s.enabled) return setzen('gut', 'aktiv')
        return setzen('aus', 'inaktiv')
      })

    const laden = () => {
      const p = kind === 'mqtt' ? ladeBroker() : kind === 'mqtt-export' ? ladeExport() : ladeHa()
      p.catch(() => setzen('aus', 'inaktiv'))
    }

    laden()
    const handler = () => laden()
    window.addEventListener(VERBINDUNG_GEAENDERT_EVENT, handler)
    return () => { lebt = false; window.removeEventListener(VERBINDUNG_GEAENDERT_EVENT, handler) }
  }, [kind])

  if (label === null) return null
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${TON_KLASSE[ton]}`}>
      {label}
    </span>
  )
}
