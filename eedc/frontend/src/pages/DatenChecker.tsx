/**
 * Daten-Checker (IST/V3) — dünner Komposer über die geteilten `DatenCheckerTeile`.
 *
 * Der gesamte Inhalt (Prüf-Lauf, KPI-Karten, Monatsdaten-Abdeckung, Kategorie-
 * Sektionen, Reparatur-Werkbank) lebt in {@link ./DatenCheckerTeile} als EINE
 * Code-Wahrheit — dieselben Teile speisen den IA-V4-Einstellungen-Block
 * „Daten-Checker" (inline wie Strompreise/Monatsdaten). Hier bleibt nur die
 * V3-Seiten-Hülle: Lade-/Leer-Anlage-Guards und die Anlage-Auswahl (Mehr-Anlagen-
 * Fall) im Kopf.
 */
import { useSelectedAnlage } from '../hooks'
import { LoadingSpinner } from '../components/ui'
import { DatenCheckerVerwaltung } from './DatenCheckerTeile'

export default function DatenChecker() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()

  if (anlagenLoading) {
    return (
      <div className="flex justify-center py-12">
        <LoadingSpinner />
      </div>
    )
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <div className="text-center py-12 text-gray-500">
          Keine Anlagen vorhanden. Bitte zuerst eine Anlage anlegen.
        </div>
      </div>
    )
  }

  if (selectedAnlageId == null) {
    return (
      <div className="flex justify-center py-12">
        <LoadingSpinner />
      </div>
    )
  }

  const anlageAuswahl = anlagen.length > 1 ? (
    <select
      value={selectedAnlageId}
      onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
      aria-label="Anlage auswählen"
      className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
    >
      {anlagen.map((a) => (
        <option key={a.id} value={a.id}>{a.anlagenname}</option>
      ))}
    </select>
  ) : null

  return <DatenCheckerVerwaltung anlageId={selectedAnlageId} kopfZusatz={anlageAuswahl} />
}
