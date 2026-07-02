/**
 * Investitionen (IST/V3) — dünner Komposer über die geteilten `InvestitionenTeile`.
 *
 * Die gesamte Geräte-Verwaltung (Typ-Kacheln, Listen, Formular-/Löschen-Modals, CRUD,
 * Migration) lebt in {@link ./InvestitionenTeile} als EINE Code-Wahrheit — dieselben
 * Teile speisen den IA-V4-Einstellungen-Reiter „Komponenten". Hier bleibt nur die
 * V3-Seiten-Hülle: Lade-/Leer-Anlage-Guards und die Anlage-Auswahl im Kopf.
 */
import { LoadingSpinner, Alert } from '../components/ui'
import { useSelectedAnlage } from '../hooks'
import { InvestitionenVerwaltung } from './InvestitionenTeile'

export default function Investitionen() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const anlageId = selectedAnlageId

  if (anlagenLoading) {
    return <LoadingSpinner text="Lade Investitionen..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an, um Investitionen zu verwalten.
        </Alert>
      </div>
    )
  }

  if (anlageId == null) {
    return <LoadingSpinner text="Lade Investitionen..." />
  }

  const anlage = anlagen.find((a) => a.id === anlageId)
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

  return (
    <InvestitionenVerwaltung
      anlageId={anlageId}
      anlagenname={anlage?.anlagenname}
      kopfZusatz={anlageAuswahl}
    />
  )
}
