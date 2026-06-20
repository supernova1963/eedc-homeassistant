/**
 * AnlagenSelektor — verbundener globaler Anlagen-Kontextwähler für `/v4`.
 *
 * Zieht den Bestands-Hook `useSelectedAnlage` (localStorage + globales
 * CustomEvent) und rendert die geteilte präsentations-SoT
 * {@link AnlagenSelektorView} (liegt in `components/layout/`, damit die
 * im Prod-Build enthaltene Vorschau keine v4-Symbole hereinzieht).
 *
 * Setzt die EINE aktive Anlage für ALLE Sichten/Achsen — reine UI über dem
 * bestehenden Daten-Layer, kein eigener State, kein Rewiring.
 */
import { AnlagenSelektorView } from '../components/layout/AnlagenSelektorView'
import { useSelectedAnlage } from '../hooks/useSelectedAnlage'

export function AnlagenSelektor() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId } = useSelectedAnlage()
  return (
    <AnlagenSelektorView
      anlagen={anlagen}
      selectedId={selectedAnlageId}
      onSelect={setSelectedAnlageId}
    />
  )
}
