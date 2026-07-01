/**
 * Backup & Restore (IST/V3) — dünner Komposer über die geteilten `BackupTeile`.
 *
 * Der gesamte Inhalt (JSON-Voll-Export + Drag-&-Drop-Restore) lebt in
 * {@link ./BackupTeile} als EINE Code-Wahrheit — dieselben Teile speisen den
 * IA-V4-Einstellungen-Block „Backup" (inline wie Strompreise/Monatsdaten). Hier
 * bleibt nur die V3-Seiten-Hülle: Lade-/Leer-Anlage-Guards und die Anlage-Auswahl
 * (Mehr-Anlagen-Fall) im Kopf.
 */
import { useSelectedAnlage } from '../hooks'
import { fmtZahl } from '../lib'
import { DataLoadingState } from '../components/common'
import { BackupVerwaltung } from './BackupTeile'

export default function Backup() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading, refresh: refreshAnlagen } = useSelectedAnlage()

  if (anlagenLoading) return <DataLoadingState loading={true} error={null}><div /></DataLoadingState>

  if (anlagen.length === 0) {
    return (
      <p className="text-gray-500 dark:text-gray-400">
        Keine Anlagen vorhanden. Lege zuerst eine Anlage an.
      </p>
    )
  }

  const anlageId = selectedAnlageId ?? anlagen[0].id
  const anlage = anlagen.find(a => a.id === anlageId)

  const anlageAuswahl = anlagen.length > 1 ? (
    <select
      value={anlageId}
      onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
      aria-label="Anlage auswählen"
      className="input w-auto"
    >
      {anlagen.map((a) => (
        <option key={a.id} value={a.id}>
          {a.anlagenname} ({fmtZahl(a.leistung_kwp, 1)} kWp)
        </option>
      ))}
    </select>
  ) : null

  return (
    <BackupVerwaltung
      anlageId={anlageId}
      anlagenname={anlage?.anlagenname}
      kopfZusatz={anlageAuswahl}
      onRestored={refreshAnlagen}
    />
  )
}
