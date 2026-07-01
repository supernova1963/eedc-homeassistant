/**
 * Solarprognose (IST/V3) — dünner Komposer über die geteilten `PVGISSettingsTeile`.
 *
 * Der gesamte Inhalt (aktive Prognose, Horizontprofil, neue Prognose abrufen,
 * optimale Ausrichtung, gespeicherte Prognosen, Wetter-Provider-Info) lebt in
 * {@link ./PVGISSettingsTeile} als EINE Code-Wahrheit — dieselben Teile speisen
 * den IA-V4-Einstellungen-Block „Solarprognose" (inline wie Strompreise/
 * Monatsdaten). Hier bleibt nur die V3-Seiten-Hülle: Lade-/Leer-Anlage-Guards und
 * die Anlage-Auswahl (Mehr-Anlagen-Fall) im Kopf.
 */
import { useSelectedAnlage } from '../hooks'
import { LoadingSpinner, Alert, Select } from '../components/ui'
import { SolarprognoseVerwaltung } from './PVGISSettingsTeile'

export default function PVGISSettings() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, selectedAnlage, loading: anlagenLoading } = useSelectedAnlage()

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
    <Select
      value={selectedAnlageId.toString()}
      onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
      options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
    />
  ) : null

  return (
    <SolarprognoseVerwaltung
      anlageId={selectedAnlageId}
      anlage={selectedAnlage}
      kopfZusatz={anlageAuswahl}
    />
  )
}
