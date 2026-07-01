/**
 * Strompreise (IST/V3) — dünner Komposer über die geteilten `StrompreiseTeile`.
 *
 * Der gesamte Inhalt (Tabelle, Info-Box, Formular, Modals, CRUD) lebt in
 * {@link ./StrompreiseTeile} als EINE Code-Wahrheit — dieselben Teile speisen den
 * IA-V4-Einstellungen-Block. Hier bleibt nur die V3-Seiten-Hülle: Lade-/Leer-Anlage-
 * Guards und die Anlage-Auswahl (Mehr-Anlagen-Fall) im Kopf.
 */
import { LoadingSpinner, Alert } from '../components/ui'
import { useSelectedAnlage } from '../hooks'
import { StrompreiseVerwaltung } from './StrompreiseTeile'

export default function Strompreise() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const anlageId = selectedAnlageId

  if (anlagenLoading) {
    return <LoadingSpinner text="Lade Strompreise..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an, um Strompreise zu verwalten.
        </Alert>
      </div>
    )
  }

  if (anlageId == null) {
    return <LoadingSpinner text="Lade Strompreise..." />
  }

  // #218: Überschrift „Strompreise" entfernt — der Sub-Tab benennt den Bereich.
  const anlageAuswahl = anlagen.length > 1 ? (
    <select
      value={anlageId}
      onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
      className="input w-auto"
      title="Anlage auswählen"
    >
      {anlagen.map((a) => (
        <option key={a.id} value={a.id}>
          {a.anlagenname}
        </option>
      ))}
    </select>
  ) : null

  return <StrompreiseVerwaltung anlageId={anlageId} kopfZusatz={anlageAuswahl} />
}
