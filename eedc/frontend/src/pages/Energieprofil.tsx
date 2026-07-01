/**
 * Energieprofil (IST/V3) — dünner Komposer über die geteilten `EnergieprofilTeile`.
 *
 * Die Pflege-Funktionen (Datenbestand · Backfill · Kraftstoff · Löschen ·
 * Reparatur-Werkbank) leben in {@link ./EnergieprofilTeile} als EINE Code-Wahrheit
 * — dieselben Teile speisen den IA-V4-Einstellungen-Block „Energieprofil-Pflege"
 * (dort OHNE Tabelle). **Anzeige ≠ Pflege:** die Tages-Tabelle bleibt in V3
 * sichtbar (Gernot-Entscheid: bis der Flip sie ins Cockpit/Zeit-Sicht hebt) und
 * wird hier als `tabelleSlot` gereicht. Hier bleibt nur die V3-Seiten-Hülle:
 * Lade-/Leer-Anlage-Guards und die Anlage-Auswahl im Kopf.
 */
import { useNavigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import { Button, Card, EmptyState, Select } from '../components/ui'
import { PageHeader, DataLoadingState } from '../components/common'
import { useSelectedAnlage } from '../hooks'
import EnergieprofilTageTabelle from '../components/energieprofil/EnergieprofilTageTabelle'
import { EnergieprofilPflege } from './EnergieprofilTeile'

export default function Energieprofil() {
  const navigate = useNavigate()
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()

  if (anlagenLoading) {
    return <DataLoadingState loading={true} error={null}><div /></DataLoadingState>
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader title="Energieprofil" />
        <Card>
          <EmptyState
            icon={AlertCircle}
            title="Keine Anlage vorhanden"
            description="Bitte lege zuerst eine Anlage an, bevor du das Energieprofil verwalten kannst."
            action={<Button onClick={() => navigate('/einstellungen/anlage')}>Zur Anlagen-Verwaltung</Button>}
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

  return (
    <EnergieprofilPflege
      anlageId={selectedAnlageId}
      anlagenname={anlagen.find(a => a.id === selectedAnlageId)?.anlagenname}
      kopfZusatz={anlageAuswahl}
      tabelleSlot={<EnergieprofilTageTabelle anlageId={selectedAnlageId} />}
    />
  )
}
