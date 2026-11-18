/**
 * useGrundNachtragen — «Grund nachtragen» an einem verzeichneten Wechsel (Sensorwechsel mit Grund, Sitzung 4, Bauplan B-7).
 *
 * Der Befund «Zuordnung geändert, Grund fehlt» springt mit `?nachtrag=<id>` in die Datenquellen (`EinstellungenV4`,
 * `DATENQUELLEN_SPRUNG`). Der Hook fragt die Prüf-Route (`…/zuordnung-wechsel/{id}/grund/pruefen` — schreibt nichts) und öffnet
 * denselben `SensorwechselDialog` im Nachtrag-Modus; die Vorschau einer Korrektur kommt aus derselben Route mit Grund und
 * «falsch seit» (Vorschau = Lauf), «Übernehmen» trägt ein (`…/grund`). Gestartete Korrektur-Läufe gehen an `merkeLaeufe`
 * (Fortschritt an der Fläche). Der Client rechnet nichts.
 */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { datenquellenApi, type GrundAngabe, type GrundNachtragPruefung, type KorrekturLaufStart } from '../../api/datenquellen'
import { Alert } from '../ui'
import SensorwechselDialog from './SensorwechselDialog'

export const NACHTRAG_LADEFEHLER = 'Der Wechsel ließ sich nicht laden'

export function useGrundNachtragen(anlageId: number | null, wechselId: string | undefined,
  merkeLaeufe: (l?: KorrekturLaufStart[]) => void, neuLaden: () => void): ReactNode {
  const [pruefung, setPruefung] = useState<GrundNachtragPruefung | null>(null)
  const [laeuft, setLaeuft] = useState(false)
  // Zwei Fehler, zwei Orte: der Ladefehler steht an der Fläche (kein Dialog), der Speicherfehler im Dialog — «Abbrechen»
  // verwirft ihn mit dem Dialog (sonst stünde danach ein unwahrer Ladefehler an der Fläche).
  const [ladeFehler, setLadeFehler] = useState<string | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)
  const id = wechselId && /^\d+$/.test(wechselId) ? Number(wechselId) : null

  useEffect(() => {
    if (anlageId == null || id == null) return
    let aus = false
    setLadeFehler(null)
    setFehler(null)
    datenquellenApi.pruefeGrundNachtragen(anlageId, id)
      .then((p) => { if (!aus) setPruefung(p) })
      .catch((e) => { if (!aus) setLadeFehler(e instanceof Error ? e.message : '') })
    return () => { aus = true }
  }, [anlageId, id])

  const vorschau = useCallback((_key: string, falschSeit: string) => {
    if (anlageId == null || id == null) return Promise.resolve(null)
    return datenquellenApi.pruefeGrundNachtragen(anlageId, id, { grund: 'korrektur', falsch_seit: falschSeit })
      .then((p) => p.korrektur)
  }, [anlageId, id])

  const bestaetigen = useCallback((gruende: Record<string, GrundAngabe>) => {
    if (anlageId == null || id == null || !pruefung) return
    setLaeuft(true)
    setFehler(null)
    datenquellenApi.grundNachtragen(anlageId, id, gruende[pruefung.sensor_key ?? ''])
      .then((r) => { merkeLaeufe(r.korrektur); setPruefung(null); neuLaden() })
      .catch((e) => setFehler(e instanceof Error ? e.message : 'Speichern fehlgeschlagen'))
      .finally(() => setLaeuft(false))
  }, [anlageId, id, pruefung, merkeLaeufe, neuLaden])

  // Eine Liste je Prüfung (gleiche Identität über die Renders) — sonst setzte der Dialog bei jedem Render der Fläche die Wahl zurück.
  const fragen = useMemo(() => (pruefung ? [pruefung] : []), [pruefung])

  if (!pruefung) return ladeFehler ? <Alert type="error">{`${NACHTRAG_LADEFEHLER}: ${ladeFehler}`}</Alert> : null
  return (
    <SensorwechselDialog isOpen fragen={fragen} onVorschau={vorschau} onBestaetigen={bestaetigen}
      onAbbrechen={() => { setPruefung(null); setFehler(null) }} laeuft={laeuft} fehler={fehler}
      nachtrag={{ wechselSatz: pruefung.wechsel_satz, gruende: pruefung.gruende, korrekturNicht: pruefung.korrektur_nicht }} />
  )
}
