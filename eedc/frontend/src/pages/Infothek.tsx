/**
 * Infothek (IST/V3) — dünner Komposer über die geteilten `InfothekTeile`.
 *
 * Der gesamte Inhalt (Liste, Kategorie-Filter, Anlegen/Bearbeiten/Löschen-Modals,
 * N:M-Investitions-Verknüpfung, Datei-Upload) lebt in {@link ./InfothekTeile} als
 * EINE Code-Wahrheit — dieselben Teile speisen den IA-V4-Einstellungen-Block
 * „Infothek" (volle native V4-Sicht, inline wie Strompreise/Monatsdaten). Hier
 * bleibt nur die V3-Seiten-Hülle: Lade-/Leer-Anlage-Guards und die Anlage-Auswahl
 * (Mehr-Anlagen-Fall) im Kopf.
 */
import { useSelectedAnlage } from '../hooks'
import { Alert, LoadingSpinner } from '../components/ui'
import { InfothekVerwaltung } from './InfothekTeile'

export default function Infothek() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()

  if (anlagenLoading) {
    return <LoadingSpinner text="Lade Infothek..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an, um die Infothek zu nutzen.
        </Alert>
      </div>
    )
  }

  if (selectedAnlageId == null) {
    return <LoadingSpinner text="Lade Infothek..." />
  }

  const anlageAuswahl = anlagen.length > 1 ? (
    <select
      value={selectedAnlageId}
      onChange={e => setSelectedAnlageId(Number(e.target.value))}
      aria-label="Anlage auswählen"
      className="input w-auto"
    >
      {anlagen.map(a => (
        <option key={a.id} value={a.id}>{a.anlagenname}</option>
      ))}
    </select>
  ) : null

  return <InfothekVerwaltung anlageId={selectedAnlageId} kopfZusatz={anlageAuswahl} />
}
