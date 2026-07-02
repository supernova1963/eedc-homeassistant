/**
 * MQTT-Export (IST/V3) — dünner Komposer über die geteilten `HAExportSettingsTeile`.
 *
 * Der gesamte Inhalt (REST-YAML-Snippet, MQTT-Discovery-Publish/Remove, Sensor-
 * Übersicht, Günstig-Schwelle) lebt in {@link ./HAExportSettingsTeile} als EINE
 * Code-Wahrheit — dieselben Teile speisen den IA-V4-Einstellungen-Block
 * „MQTT-Export" (inline wie Strompreise/Solarprognose; `haOnly`). Hier bleibt nur
 * die V3-Seiten-Hülle: Lade-/Leer-Anlage-Guards und die Anlage-Auswahl
 * (Mehr-Anlagen-Fall) im Kopf.
 */
import { useSelectedAnlage } from '../hooks'
import { LoadingSpinner, Alert } from '../components/ui'
import { MqttExportVerwaltung } from './HAExportSettingsTeile'

export default function HAExportSettings() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, selectedAnlage, loading: anlagenLoading, refresh } = useSelectedAnlage()

  if (anlagenLoading) return <LoadingSpinner text="Lade..." />

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  if (selectedAnlageId == null) return <LoadingSpinner text="Lade..." />

  const anlageAuswahl = anlagen.length > 1 ? (
    <select
      value={selectedAnlageId}
      onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
      aria-label="Anlage auswählen"
      className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-sm"
    >
      {anlagen.map((a) => (
        <option key={a.id} value={a.id}>{a.anlagenname}</option>
      ))}
    </select>
  ) : null

  return (
    <MqttExportVerwaltung
      anlageId={selectedAnlageId}
      anlage={selectedAnlage}
      kopfZusatz={anlageAuswahl}
      onAnlageUpdated={refresh}
    />
  )
}
