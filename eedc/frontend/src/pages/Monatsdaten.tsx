/**
 * Monatsdaten (IST/V3) — dünner Komposer über die geteilten `MonatsdatenTeile`.
 *
 * Der gesamte Inhalt (Tabelle, Spalten-Auswahl, HA-Import, Formular-/Vergleichs-/
 * Lösch-Modals, Kraftstoffpreis-Backfill) lebt in {@link ./MonatsdatenTeile} als
 * EINE Code-Wahrheit — dieselben Teile speisen die native IA-V4-Monatsdaten-Seite
 * ({@link ../v4/MonatsdatenV4}). Hier bleibt nur die V3-Seiten-Hülle: Lade-/Leer-
 * Anlage-Guards und die Anlage-Auswahl (Mehr-Anlagen-Fall) im Kopf.
 */
import { useNavigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import { Button, Card, EmptyState, Select } from '../components/ui'
import { PageHeader, DataLoadingState } from '../components/common'
import { useSelectedAnlage } from '../hooks'
import { MonatsdatenVerwaltung } from './MonatsdatenTeile'

export default function MonatsdatenPage() {
  const navigate = useNavigate()
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()

  if (anlagenLoading) {
    return <DataLoadingState loading={true} error={null}><div /></DataLoadingState>
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader title="Monatsdaten" />
        <Card>
          <EmptyState
            icon={AlertCircle}
            title="Keine Anlage vorhanden"
            description="Bitte lege zuerst eine Anlage an, bevor du Monatsdaten erfassen kannst."
            action={
              <Button onClick={() => navigate('/anlagen')}>
                Zur Anlagen-Verwaltung
              </Button>
            }
          />
        </Card>
      </div>
    )
  }

  if (selectedAnlageId == null) {
    return <DataLoadingState loading={true} error={null}><div /></DataLoadingState>
  }

  const anlageAuswahl = anlagen.length > 1 ? (
    <Select
      value={selectedAnlageId.toString()}
      onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
      options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
      aria-label="Anlage wählen"
    />
  ) : null

  return <MonatsdatenVerwaltung anlageId={selectedAnlageId} kopfZusatz={anlageAuswahl} />
}
